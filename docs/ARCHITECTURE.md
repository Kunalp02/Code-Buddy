# Arcfold — Architecture Deep Dive

This document explains how Arcfold works behind the scenes: how a repository becomes a queryable code graph, how the agent answers questions with evidence, and how diagrams, documentation, and context packs are produced.

---

## Table of contents

1. [What Arcfold is](#1-what-arcfold-is)
2. [System overview](#2-system-overview)
3. [Project lifecycle](#3-project-lifecycle)
4. [Indexing pipeline](#4-indexing-pipeline)
5. [Code intelligence tiers](#5-code-intelligence-tiers)
6. [Database schema](#6-database-schema)
7. [Graph query layer](#7-graph-query-layer)
8. [HTTP API](#8-http-api)
9. [Agent and chat](#9-agent-and-chat)
10. [Diagram generation](#10-diagram-generation)
11. [Documentation generation](#11-documentation-generation)
12. [Context packs](#12-context-packs)
13. [Remote indexing (GitHub / GitLab)](#13-remote-indexing-github--gitlab)
14. [Web frontend](#14-web-frontend)
15. [Configuration and data storage](#15-configuration-and-data-storage)
16. [Extension points](#16-extension-points)

---

## 1. What Arcfold is

Arcfold is a **local-first codebase intelligence tool**. You point it at a repository (local path, GitHub, or GitLab), and it:

1. **Indexes** source files into a SQLite graph (symbols, imports, routes, modules, references, infrastructure components).
2. **Visualizes** architecture as interactive diagrams.
3. **Answers questions** via an LLM agent that queries the graph and cites `file:line` evidence.
4. **Generates documentation** from templates, with architecture diagrams embedded.
5. **Exports context packs** — compact markdown blocks for editor workflows.

Nothing requires a remote database or git clone. All indexed data lives on disk under `.arcfold-data/`.

---

## 2. System overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Web UI (React + Vite)                           │
│  HomePage ──► ProjectPage ──► [Diagram | Explorer | Chat | Docs | Ctx] │
│                              api/client.ts (fetch + NDJSON streams)     │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ HTTP /api/*
┌───────────────────────────────────▼─────────────────────────────────────┐
│                      FastAPI backend (server/main.py)                     │
│                                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────────┐ │
│  │  indexer/   │  │ graph/       │  │  agent/    │  │ diagram/ docs/   │ │
│  │  (write)    │  │ queries.py   │  │ orchestrator│  │ context_pack/   │ │
│  │             │  │ (read)       │  │ + tools    │  │                  │ │
│  └──────┬──────┘  └──────┬───────┘  └─────┬──────┘  └────────┬─────────┘ │
│         │                 │                │                   │          │
└─────────┼─────────────────┼────────────────┼───────────────────┼──────────┘
          │                 │                │                   │
          ▼                 ▼                ▼                   ▼
   graph.db +          read_snippet      Ollama Cloud        SVG assets
   meta.json           reads disk        (chat + docs)       + markdown
```

### Key directories

| Path | Role |
|------|------|
| `server/` | Python backend — indexing, graph, agent, diagrams, docs |
| `web/` | React SPA — project UI, explorer, chat, diagrams |
| `analyzers/roslyn/` | .NET Roslyn sidecar for deep C# analysis |
| `scripts/dev.sh` | Starts uvicorn (`:8000`) + Vite dev server (`:5173`) |
| `docs/` | Project documentation (this file) |

### Runtime

- **Backend:** `uvicorn server.main:app` — serves REST + NDJSON streams; mounts `web/dist` in production.
- **Frontend (dev):** Vite proxies `/api` → `127.0.0.1:8000`.
- **LLM:** Ollama Cloud via the `ollama` Python SDK. Chat uses `qwen3:8b`; documentation uses `gpt-oss:120b` by default.

---

## 3. Project lifecycle

### 3.1 Creating a project

**Entry:** `POST /api/projects` → `create_project()` in `server/indexer/engine.py`

```
create_project()
  │
  ├─ source = "local"
  │    └─ resolve_local_root(path)          [sources.py]
  │
  ├─ source = "github"
  │    └─ fetch_github_workspace(...)       [integrations/github.py]
  │         └─ write_workspace(...)         [remote_store.py]
  │
  └─ source = "gitlab"
       └─ fetch_gitlab_workspace(...)      [integrations/gitlab.py]
            └─ write_workspace(...)
  │
  └─ index_project(project_id, root_path)
       └─ save_meta(project_id, meta)
```

Each project gets a random 8-character hex ID (e.g. `56e0c591`). Metadata is written to `.arcfold-data/{id}/meta.json`; the graph goes to `.arcfold-data/{id}/graph.db`.

### 3.2 What gets stored

**`meta.json`** — project-level metadata (not in SQLite):

```json
{
  "id": "56e0c591",
  "path": "/workspace",
  "name": "workspace",
  "status": "ready",
  "source": "local",
  "framework": "python",
  "entry_points": ["server/main.py"],
  "indexed_at": "2026-09-13T14:30:00+00:00",
  "stats": {
    "files_total": 71,
    "files_parsed": 63,
    "symbols": 358,
    "symbol_refs": 949,
    "routes": 37,
    "modules": 14,
    "languages": { "py": 26, "tsx": 16, "ts": 3 },
    "semantic_refs": 949,
    "roslyn": { "success": true, "symbols_added": 0 }
  }
}
```

### 3.3 Progress tracking

During indexing, `IndexProgress` is held in an in-memory dict (`_progress`). `GET /api/projects/{id}` merges this into the response so the UI can show status while parsing runs.

---

## 4. Indexing pipeline

`index_project()` in `server/indexer/engine.py` is the heart of Arcfold. It runs these phases in order:

```
walk → parse → persist → modules → semantic graph → Roslyn → infra/docker scan → meta
```

### 4.1 Walker (`server/indexer/walker.py`)

| Function | Purpose |
|----------|---------|
| `walk_project(root)` | Recursively walks the directory tree |
| `should_skip_dir(name)` | Skips `.git`, `node_modules`, `.arcfold-data`, etc. |
| `should_skip_file(path)` | Skips binaries, images, lock files; **never** skips Dockerfiles or compose files |
| `detect_language(path)` | Maps extension → language key (`py` → `python`, `tsx` → `typescript`, etc.) |
| `module_key(root, file)` | Derives module path for dependency graph (`server/indexer`, `web/src`, etc.) |

**Indexed languages:** Python, JavaScript, TypeScript (incl. JSX/TSX), Go, Java, Rust, C#, Dart, Dockerfile, Compose YAML, plus regex fallback for others.

### 4.2 Parser (`server/indexer/parser.py`)

Each file is parsed by `parse_file(path)`, which dispatches to a language-specific function backed by **Tree-sitter** grammars.

**Output types:**

| Type | Fields | Example |
|------|--------|---------|
| `ParsedSymbol` | name, kind, start_line, end_line, signature | `create_project`, function, 327–400 |
| `ParsedImport` | source, imported_name, line | `fastapi`, `FastAPI`, 4 |
| `ParsedRoute` | method, path, handler, line | `GET`, `/api/health`, 160 |

**Per-language extractors:**

| Language | Function | Symbols | Routes |
|----------|----------|---------|--------|
| Python | `parse_python()` | functions, classes | `@app.get`, `@router.post` decorators |
| JS/TS | `parse_js_ts()` | functions, classes, interfaces, React components | `app.get()`, `.post()` call expressions |
| Go | `parse_go()` | functions, methods, types | regex fallback |
| Java | `parse_java()` | classes, methods, interfaces | Spring `@GetMapping` via regex |
| Rust | `parse_rust()` | functions, structs, impls | regex fallback |
| C# | `parse_csharp()` | classes, methods, properties, records | `[HttpGet]`, `app.MapGet()` |
| Dart | `parse_dart()` | classes, widgets, functions | regex fallback |
| Dockerfile | `parse_dockerfile()` | base images, exposed ports | line-based |

If Tree-sitter has no grammar for a file, `regex_fallback()` extracts basic function/class patterns.

### 4.3 Persistence (inside `index_project`)

For each walked file:

1. `INSERT INTO files` — path, language, line count
2. `INSERT INTO symbols` — one row per parsed symbol
3. `INSERT INTO imports` — import statements
4. `INSERT INTO routes` — HTTP route definitions
5. Aggregate `module_files` and `module_imports` for the module graph

**Entry point detection:** filenames like `main.py`, `app.py`, `index.ts`, `server.py` are recorded in `meta.entry_points`.

### 4.4 Module dependency graph

After all files are parsed:

1. `INSERT INTO modules` — one row per module path with file count
2. For each import in each module, `_import_to_module()` resolves the import string to a module path
3. `INSERT INTO module_deps` — weighted edges between modules

Example: `from server.indexer.engine import create_project` in `server/main.py` creates an edge `server` → `server/indexer`.

### 4.5 Semantic reference graph (`server/indexer/semantic.py`)

`build_semantic_graph(conn, root_path)` scans every source line for call patterns like `symbolName(`:

```
for each file:
  for each line:
    match identifier( pattern
    lookup identifier in global symbol name index
    prefer cross-file targets over same-file
    INSERT INTO symbol_refs (ref_kind = 'call')
```

This works for **all indexed languages** — Python, JavaScript, TypeScript, Go, Java, Rust, C#, Dart. It is name-based (not type-aware), so symbols with the same name in different files may both match.

### 4.6 Roslyn bridge (`server/indexer/roslyn_bridge.py`)

For repositories containing `*.csproj` or `*.sln`:

1. Locates `dotnet` (PATH or `~/.dotnet/dotnet`)
2. Builds `analyzers/roslyn/Arcfold.Roslyn/` if needed
3. Runs the analyzer DLL, which outputs JSON
4. Merges qualified symbol names, ASP.NET routes, and compiler-accurate references into the graph (`ref_kind = 'roslyn'`)

The C# analyzer (`Program.cs`) uses `MSBuildWorkspace` to open solutions, extracts symbols with `QualifiedName`, finds HTTP attributes on methods, and runs `SymbolFinder.FindReferencesAsync()`.

### 4.7 Infrastructure scanners

**`server/indexer/infra_scanner.py`** — pattern-matches source and config files for:

- Databases (PostgreSQL, MySQL, MongoDB, SQLite, etc.)
- Caches (Redis, Memcached)
- Queues (RabbitMQ, Kafka, SQS)
- Auth providers (Auth0, Firebase, JWT)
- ORMs (SQLAlchemy, Prisma, Entity Framework)
- Search (Elasticsearch, Solr)

Results are stored in `components` and `component_connections` tables.

**`server/indexer/docker_scanner.py`** — parses Dockerfiles and `docker-compose.yml`:

- Service images → component types (`postgres` image → `database` component)
- `depends_on` → connection edges
- Exposed ports

Both scanners merge via `_merge_components()` before insertion.

### 4.8 Framework detection

`_detect_framework()` checks for marker files (`package.json`, `pyproject.toml`, `go.mod`, `*.csproj`) and inspects dependencies (e.g. `next` in package.json → `nextjs`).

---

## 5. Code intelligence tiers

Arcfold builds understanding in layers:

```
┌─────────────────────────────────────────────────────────────┐
│ Tier 3: Roslyn (C# only)                                    │
│ Qualified names, compiler FindReferences, ASP.NET routes      │
├─────────────────────────────────────────────────────────────┤
│ Tier 2: Semantic graph (all languages)                      │
│ Cross-file call references via identifier( pattern matching  │
├─────────────────────────────────────────────────────────────┤
│ Tier 1: Tree-sitter syntactic index (all languages)         │
│ Symbols, imports, routes, module dependency graph             │
├─────────────────────────────────────────────────────────────┤
│ Tier 0: Infrastructure scanners                             │
│ Databases, caches, queues, Docker services, connections     │
└─────────────────────────────────────────────────────────────┘
```

| Language | Tier 1 (parse) | Tier 2 (refs) | Tier 3 (deep) |
|----------|:-:|:-:|:-:|
| Python | ✅ Tree-sitter | ✅ call graph | — |
| JavaScript | ✅ Tree-sitter | ✅ call graph | — |
| TypeScript | ✅ Tree-sitter | ✅ call graph | — |
| Go, Java, Rust, Dart | ✅ Tree-sitter | ✅ call graph | — |
| C# | ✅ Tree-sitter | ✅ call graph | ✅ Roslyn |

### What each tier enables

| Capability | Tier 1 | Tier 2 | Tier 3 |
|------------|:-:|:-:|:-:|
| Symbol search | ✅ | | |
| File tree + per-file symbols | ✅ | | |
| API route listing | ✅ | | |
| Module dependency map | ✅ | | |
| Find references / callers | | ✅ | ✅ (C#) |
| Hub symbol ranking | | ✅ | |
| Architecture components | Tier 0 | | |
| Qualified C# names | | | ✅ |

### Known limitations (Tier 2)

- Matches by **symbol name**, not import scope — `utils.helper` and `other.helper` may collide.
- Only catches `identifier(` patterns — not `obj.method()` chains (only `method(` is matched).
- Anonymous arrow functions and default exports may not appear as named symbols.
- No type inference — a call to `process()` links to every symbol named `process`.

---

## 6. Database schema

Each project has its own SQLite database at `.arcfold-data/{id}/graph.db`. Schema is defined in `server/db.py` → `init_schema()`.

### Entity relationships

```
files ──┬── symbols ──┬── symbol_refs (from)
        │             └── symbol_refs (to)
        ├── imports
        └── routes

modules ─── module_deps (from/to)

components ─── component_connections (source/target)

chat_sessions ─── chat_messages
```

### Tables

| Table | Key columns | Purpose |
|-------|-------------|---------|
| `files` | `path` UNIQUE, `language`, `line_count` | Indexed source files |
| `symbols` | `file_id`, `name`, `kind`, `start_line`, `end_line`, `signature` | Functions, classes, interfaces, etc. |
| `imports` | `file_id`, `source`, `imported_name`, `line` | Import statements |
| `routes` | `file_id`, `method`, `path`, `handler`, `line` | HTTP/API routes |
| `modules` | `path` UNIQUE, `name`, `file_count` | Folder/package modules |
| `module_deps` | `from_module_id`, `to_module_id`, `weight` | Cross-module import edges |
| `symbol_refs` | `from_symbol_id`, `to_symbol_id`, `ref_kind`, `file_path`, `line` | Call graph + Roslyn refs |
| `components` | `id`, `name`, `component_type`, `technology`, `evidence_file` | Infra/docker components |
| `component_connections` | `source_id`, `target_id`, `connection_type`, `label` | System architecture edges |
| `chat_sessions` | `id`, `created_at`, `title` | Agent chat sessions |
| `chat_messages` | `session_id`, `role`, `content`, `metadata` | Chat history (JSON metadata) |

### Indexes

- `idx_symbols_name` — fast symbol search
- `idx_symbols_file` — per-file symbol lookup
- `idx_symbol_refs_to` / `idx_symbol_refs_from` — reference traversal

### Runtime columns

`qualified_name` and `container` are added to `symbols` via `ALTER TABLE` when semantic or Roslyn analysis runs.

---

## 7. Graph query layer

All read operations go through `server/graph/queries.py`. The API and agent tools call these functions — they never query SQLite directly.

| Function | What it does |
|----------|-------------|
| `list_projects()` | Scans `.arcfold-data/`, loads each `meta.json` |
| `get_project(id)` | Returns `meta.json` contents |
| `search_symbols(id, q)` | `LIKE` search on symbol name + file path, ranked by exact/prefix match |
| `get_file_tree(id)` | All indexed files ordered by path |
| `get_file_symbols(id, path)` | Symbols in one file |
| `read_snippet(id, path, start, end)` | Reads source from disk at `meta.path`, max 120 lines |
| `get_routes(id)` | All HTTP routes with file paths |
| `get_modules(id)` | Module list with file counts |
| `get_module_deps(id)` | Weighted edges between modules |
| `get_module_enrichment(id)` | Per-module symbol/route counts, fan-in/out, hub score |
| `find_references(id, q)` | Resolve symbol by name or ID → return `symbol_refs` rows |
| `get_callers(id, q)` | Deduplicated caller list from `find_references` |
| `get_codebase_summary(id)` | Stats + top 10 hub symbols by reference count |
| `get_components(id)` | Infrastructure components ordered by type |
| `get_component_connections(id)` | All component edges |
| `get_system_architecture(id)` | Aggregated view: databases, caches, routes, connections |

**Important:** `read_snippet()` reads from the **filesystem** at `meta.path`, not from the database. This means snippets always reflect the current file contents, even if the index is stale.

---

## 8. HTTP API

All routes are defined in `server/main.py`. Responses are JSON except for streaming endpoints (NDJSON) and file downloads.

### Projects

| Method | Endpoint | Handler |
|--------|----------|---------|
| `GET` | `/api/projects` | List all indexed projects |
| `POST` | `/api/projects` | Create + index a project |
| `GET` | `/api/projects/{id}` | Project metadata + indexing progress |

### Graph queries

| Method | Endpoint | Handler |
|--------|----------|---------|
| `GET` | `/api/projects/{id}/files` | File tree |
| `GET` | `/api/projects/{id}/search?q=` | Symbol search |
| `GET` | `/api/projects/{id}/references?q=` | Find references |
| `GET` | `/api/projects/{id}/callers?q=` | List callers |
| `GET` | `/api/projects/{id}/summary` | Codebase summary |
| `GET` | `/api/projects/{id}/snippet?path=&start=` | Source snippet |
| `GET` | `/api/projects/{id}/symbols?path=` | Per-file symbols |
| `GET` | `/api/projects/{id}/routes` | API routes |
| `GET` | `/api/projects/{id}/modules` | Modules + dependencies |
| `GET` | `/api/projects/{id}/architecture` | System architecture JSON |

### Diagrams

| Method | Endpoint | Generator |
|--------|----------|-----------|
| `GET` | `/api/projects/{id}/diagrams/system` | Zone-based system flow |
| `GET` | `/api/projects/{id}/diagrams/l1` | Module dependency map |
| `GET` | `/api/projects/{id}/diagrams/l3?route=` | Single-route request flow |

### Agent

| Method | Endpoint | Protocol |
|--------|----------|----------|
| `POST` | `/api/projects/{id}/chat` | NDJSON stream |

### Documentation

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/projects/{id}/documentation` | Load generated docs |
| `PUT` | `/api/projects/{id}/documentation` | Save edited docs |
| `POST` | `/api/projects/{id}/documentation/stream` | Generate (NDJSON stream) |
| `POST` | `/api/projects/{id}/documentation/export` | Write docs into project repo |
| `GET` | `/api/projects/{id}/documentation/download?format=` | Download MD/TXT/DOCX/PDF |
| `GET/POST/DELETE` | `/api/documentation/templates/*` | Template CRUD |

### Context packs

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/projects/{id}/context-pack` | Build project or task pack |
| `GET` | `/api/context-pack/sizes` | Size presets |

### Integrations

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/integrations/github/repos` | List repos (requires PAT) |
| `POST` | `/api/integrations/github/branches` | List branches |
| `POST` | `/api/integrations/gitlab/projects` | List GitLab projects |
| `POST` | `/api/integrations/gitlab/branches` | List branches |

---

## 9. Agent and chat

### Architecture

```
User message
    │
    ▼
chat_stream()                    [orchestrator.py]
    │
    ├─ Build system prompt + project context (stats, framework, entry points)
    ├─ Load chat history from SQLite (last 20 messages)
    │
    └─ Tool loop (max 16 iterations):
         │
         ├─ Ollama chat(model, messages, tools=TOOL_DEFINITIONS)
         │
         ├─ If no tool_calls → stream response tokens → done
         │
         └─ For each tool_call:
              ├─ execute_tool(project_id, name, args)    [tools.py]
              ├─ Collect evidence items (path + line)
              ├─ compact_tool_result() → truncate to 8000 chars
              └─ Append role=tool message → loop
```

### System prompt routing

The agent is instructed to use specific tools for specific question types:

| Question type | Tool |
|---------------|------|
| "How does this project work?" | `get_codebase_summary` |
| Architecture / database / infra | `get_system_architecture` |
| "Where is X?" / "Find X" | `search_symbol` |
| "Who calls X?" / references | `find_references` or `get_callers` |
| API endpoints | `get_routes` |
| Module structure | `get_modules` + `get_module_deps` |
| Code details | `read_snippet` (max 120 lines) |

Every claim must cite `path:line` from tool results. The agent is forbidden from guessing.

### Available tools

Defined in `server/agent/tools.py` as `TOOL_DEFINITIONS`:

| Tool | Backend function |
|------|-----------------|
| `get_system_architecture` | `get_system_architecture()` |
| `get_codebase_summary` | `get_codebase_summary()` |
| `find_references` | `find_references()` |
| `get_callers` | `get_callers()` |
| `search_symbol` | `search_symbols()` |
| `get_routes` | `get_routes()` |
| `get_modules` | `get_modules()` |
| `get_module_deps` | `get_module_deps()` |
| `read_snippet` | `read_snippet()` |
| `get_file_symbols` | `get_file_symbols()` |
| `generate_diagram` | `generate_l1_diagram()` or `generate_l3_flow()` |

### NDJSON event protocol

The chat endpoint streams newline-delimited JSON events:

| Event | Payload | When |
|-------|---------|------|
| `session` | `{session_id}` | Session established |
| `tool_start` | `{name, arguments}` | Tool call begins |
| `tool_end` | `{name, result_preview}` | Tool call completes |
| `evidence` | `{items: [{type, label, path, line}]}` | Citation items for UI |
| `meta` | `{tool_calls, model}` | Metadata |
| `token` | `{content}` | Streamed response text |
| `done` | — | Stream complete |
| `error` | `{content}` | Error message |

### Session persistence

Chat sessions and messages are stored in the per-project SQLite database (`chat_sessions`, `chat_messages`). Message metadata includes tool call count and evidence items as JSON.

---

## 10. Diagram generation

Arcfold produces three diagram levels, all returned as JSON with pre-computed node positions for React Flow rendering.

### System diagram (`/diagrams/system`)

**Generator:** `build_system_flow_diagram()` in `server/diagram/system_flow.py`

Organizes components into three zones with left-to-right request flow:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│   FRONTEND   │────►│   BACKEND    │────►│  DATA & SERVICES │
│  (React UI)  │     │  (API, Auth) │     │  (DB, Cache, Q)  │
└──────────────┘     └──────────────┘     └──────────────────┘
```

**Data sources:** `get_components()`, `get_component_connections()`, `get_routes()`, `get_modules()`, project metadata.

**Zone assignment:**
- Frontend: detected if framework is React/Next/Vue or `web/` module exists
- Backend: API, auth, ORM, proxy, container components
- Data: databases, caches, queues, storage, search

Edges are labeled (`HTTPS`, `authenticate`, `query`, `cache data`, etc.).

### L1 module map (`/diagrams/l1`)

**Generator:** `generate_architecture_diagram()` in `server/diagram/generator.py`

- One node per module from `get_modules()`
- Layer classification: presentation → api → security → core → data → config → test
- Edges from `module_deps` with weight
- Enrichment: symbol/route counts, fan-in/out, hub scoring via `get_module_enrichment()`
- Clusters grouped by layer with color legend

### L3 request flow (`/diagrams/l3`)

**Generator:** `generate_l3_flow()` in `server/diagram/generator.py`

Traces a single HTTP route through the codebase:

```
Client → Route node → symbols in handler file (up to 5)
```

Select route via `?route=/api/health` query parameter.

### Frontend rendering

`web/src/components/DiagramView.tsx` uses **React Flow** (`@xyflow/react`):

- `ZoneNode` — zone containers (system diagram)
- `ArchitectureNode` — module/component nodes
- `DiagramInspector` — detail panel; click → open file in Explorer
- View switcher: System / Modules / Request flow

### SVG export for documentation

`server/docs/diagram_embed.py` renders the system diagram to `architecture-diagram.svg`, which is embedded in generated documentation via the `{{ARCHITECTURE_DIAGRAM}}` placeholder.

---

## 11. Documentation generation

### Flow

```
documentation_stream(project_id, template_id, model)
  │
  ├─ gather_documentation_context()       [context.py]
  │    ├─ Graph: architecture, modules, routes, file tree
  │    └─ Filesystem: README, package.json, docker-compose, .env.example
  │
  ├─ get_template(template_id)           [generator.py]
  │    ├─ Built-in: server/docs/templates/*.md
  │    └─ Custom: .arcfold-data/custom-templates/{id}.md
  │
  ├─ compact_context_for_prompt()        → JSON for LLM
  │
  ├─ Ollama chat(stream=True)            → DOC_SYSTEM_PROMPT + template + context
  │    └─ yield token events (NDJSON)
  │
  ├─ finalize_documentation_content()     → inject architecture SVG
  │
  └─ save_documentation()                 → documentation.md + documentation.json
```

### Context gathering (`server/docs/context.py`)

Pulls structured evidence from the graph and filesystem:

| Source | Data |
|--------|------|
| Graph | System architecture, modules, deps, routes, file tree |
| Filesystem | README, `package.json`, `pyproject.toml`, `docker-compose.yml`, `.env.example` |
| Derived | Folder tree (depth 3), license detection, env var parsing |

### Templates

- **Built-in:** `server/docs/templates/default.md` (and others)
- **Custom:** uploaded via UI or API, stored in `.arcfold-data/custom-templates/`
- **Placeholder:** `{{ARCHITECTURE_DIAGRAM}}` — auto-injected after `## Architecture` if not present
- **Import formats:** MD, TXT, DOCX, PDF (`server/docs/template_import.py`)

### Export formats (`server/docs/format_export.py`)

| Format | Implementation |
|--------|----------------|
| Markdown | Raw UTF-8 |
| TXT | Strip markdown formatting |
| DOCX | `python-docx`, embeds architecture diagram as PNG (via `cairosvg`) |
| PDF | `fpdf2`, same SVG→PNG path |

Docs can be exported into the project repo (`POST /documentation/export`) or downloaded directly.

### Stored files

```
.arcfold-data/{id}/documentation.md       — generated content
.arcfold-data/{id}/documentation.json       — metadata (template, dates, export path)
.arcfold-data/{id}/architecture-diagram.svg — rendered system diagram
```

---

## 12. Context packs

**File:** `server/context_pack/builder.py`  
**Endpoint:** `POST /api/projects/{id}/context-pack`

Context packs are compact markdown blocks designed to be pasted into an editor's AI context window.

### Modes

| Mode | Function | Purpose |
|------|----------|---------|
| `project` | `build_project_context_pack()` | Full codebase snapshot |
| `task` | `build_task_context_pack()` | Task-scoped relevant files |

### Size presets

| Size | Character budget | ~Tokens |
|------|-----------------:|--------:|
| `compact` | 8,000 | ~2,000 |
| `standard` | 14,000 | ~3,500 |
| `large` | 22,000 | ~5,500 |

### Project pack sections

1. Header + usage instructions
2. Project overview (stats, languages, entry points, license)
3. System architecture summary
4. Modules table with enrichment data
5. Module dependencies
6. API routes table
7. Environment variables
8. Folder structure
9. README excerpt
10. Key config file excerpts

### Task pack algorithm

1. Extract keywords from task description (filter stop words)
2. `search_symbols()` per keyword → symbol hits
3. Score routes by keyword match in path/handler
4. Score files by path + symbol relevance
5. Include top 6 file snippets via `read_snippet()` (~5000 char budget)
6. Fallback to entry points if no matches

---

## 13. Remote indexing (GitHub / GitLab)

### Design: no git clone

Remote repositories are read via API — files are listed, filtered, fetched individually, and written to a sparse workspace. No `git clone` is performed.

```
GitHub/GitLab API
    │
    ├─ List repository tree (recursive)
    ├─ Filter paths (same rules as local walker)
    ├─ Fetch file content (base64 for GitHub, raw for GitLab)
    │
    └─ write_workspace(project_id, {path: bytes})
         └─ .arcfold-data/{id}/workspace/
              └─ index_project() runs on workspace/
```

### GitHub (`server/integrations/github.py`)

| Function | API endpoint |
|----------|-------------|
| `list_repositories(token)` | `GET /user/repos` (paginated) |
| `list_branches(token, owner, repo)` | `GET /repos/{owner}/{repo}/branches` |
| `_tree_paths()` | `GET /repos/.../git/trees/{sha}?recursive=1` |
| `fetch_file_content()` | `GET /repos/.../contents/{path}?ref=` (max 1 MB) |

### GitLab (`server/integrations/gitlab.py`)

| Function | API endpoint |
|----------|-------------|
| `list_projects(token, host)` | `GET /api/v4/projects?membership=true` |
| `list_branches(token, project_id, host)` | `GET /projects/{id}/repository/branches` |
| `_tree_paths()` | `GET /projects/{id}/repository/tree?recursive=true` |
| `fetch_file_content()` | `GET /projects/{id}/repository/files/{path}/raw?ref=` |

### Token handling

- Required for `source=github|gitlab` on project creation
- **Never stored** — used only for the indexing session
- UI collects token → lists repos → selects branch → submits

### Remote project metadata

```json
{
  "source": "github",
  "source_url": "https://github.com/owner/repo",
  "branch": "main",
  "read_mode": "api"
}
```

---

## 14. Web frontend

### Routing

| Route | Component | Purpose |
|-------|-----------|---------|
| `/` | `HomePage` | Import projects, list recent |
| `/project/:id` | `ProjectPage` | Main workspace with tabs |

### Project workspace tabs

| Tab | Component | What it does |
|-----|-----------|-------------|
| Architecture | `DiagramView` | System / module / route flow diagrams |
| Explorer | `Explorer` + `CodeViewer` | File tree, symbol search, find-references, code view |
| Search | `ChatPanel` | Agent Q&A with evidence citations |
| Documentation | `DocsPanel` | Generate, edit, export docs |
| Context Pack | `ContextPackPanel` | Build project/task context blocks |

### Cross-panel navigation

Evidence items from chat (symbols, routes, references) are clickable — they open the referenced file at the correct line in the Explorer tab. Diagram node clicks do the same.

### API client (`web/src/api/client.ts`)

- `request<T>()` — standard JSON fetch with error handling
- `streamChat()` — NDJSON parser for `POST /chat`
- `streamDocumentation()` — NDJSON parser for `POST /documentation/stream`
- Typed interfaces for all API responses

### Dev setup

```bash
./scripts/dev.sh
# Backend: http://127.0.0.1:8000
# Frontend: http://localhost:5173 (proxies /api → backend)
```

---

## 15. Configuration and data storage

### Environment variables (`.env`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_API_KEY` | — | Ollama Cloud API key (required for chat/docs) |
| `OLLAMA_HOST` | `https://ollama.com` | Ollama endpoint |
| `OLLAMA_MODEL` | `qwen3:8b` | Chat agent model |
| `OLLAMA_MODEL_DEEP` | `gpt-oss:120b` | Documentation generation model |

Settings are loaded via `pydantic-settings` in `server/config.py`.

### Other settings

| Setting | Default | Purpose |
|---------|---------|---------|
| `max_snippet_lines` | 120 | Max lines per snippet read |
| `max_agent_tool_calls` | 16 | Agent tool loop budget |
| `skip_dirs` | `.git`, `node_modules`, etc. | Walker directory exclusions |
| `skip_extensions` | `.png`, `.min.js`, etc. | Walker file exclusions |

### Data directory layout

```
.arcfold-data/                          # (legacy: .code-buddy-data/)
├── custom-templates/
│   ├── {template-id}.md
│   └── {template-id}.json
└── {project_id}/                       # 8-char hex
    ├── graph.db                        # SQLite code graph
    ├── meta.json                       # Project metadata + stats
    ├── workspace/                      # Remote API-fetched files only
    ├── documentation.md                # Generated docs
    ├── documentation.json              # Docs metadata
    └── architecture-diagram.svg        # Rendered system diagram
```

Resolution: prefers `.arcfold-data` if it exists, falls back to `.code-buddy-data` for legacy installs.

---

## 16. Extension points

The highest-leverage files for extending Arcfold:

| Goal | File(s) to modify |
|------|-------------------|
| Add a new language parser | `server/indexer/parser.py` — add Tree-sitter grammar + parse function |
| Improve reference accuracy | `server/indexer/semantic.py` — add import-scoped resolution or method chain patterns |
| Add deep analysis for a language | New analyzer sidecar (like `analyzers/roslyn/`) + bridge in `server/indexer/` |
| Add agent capabilities | `server/agent/tools.py` — new tool definition + `execute_tool` handler |
| Add API endpoints | `server/main.py` + `server/graph/queries.py` |
| Add diagram types | `server/diagram/generator.py` or new file |
| Add doc template formats | `server/docs/format_export.py`, `server/docs/template_import.py` |
| Add infra detection patterns | `server/indexer/infra_scanner.py` |
| Add UI panels | `web/src/pages/ProjectPage.tsx` + new component |

### Adding a new language (checklist)

1. Add Tree-sitter grammar to `server/requirements.txt`
2. Register in `_get_language()` in `parser.py`
3. Write `parse_{language}()` extracting symbols, imports, routes
4. Add call pattern to `CALL_PATTERNS` in `semantic.py`
5. Add extension mapping in `_guess_lang()` and `walker.py` `LANGUAGE_MAP`
6. Add test case in `tests/`

---

## Data flow summary

```
Repository (local / GitHub / GitLab)
    │
    ▼
walk_project() ──► parse_file() ──► SQLite (files, symbols, imports, routes, modules)
    │                                      │
    │                                      ├── build_semantic_graph() → symbol_refs
    │                                      ├── run_roslyn_analysis() → symbol_refs (C#)
    │                                      └── infra + docker scanners → components
    │
    ▼
meta.json (stats, framework, entry_points)
    │
    ├── graph/queries.py ──► REST API ──► React UI
    │                         │
    │                         ├── DiagramView (React Flow)
    │                         ├── Explorer (file tree + refs)
    │                         └── ChatPanel (agent Q&A)
    │
    ├── agent/tools.py ──► Ollama chat loop ──► cited answers
    │
    ├── docs/generator.py ──► Ollama doc gen ──► markdown + SVG
    │
    └── context_pack/builder.py ──► compact markdown for editors
```
