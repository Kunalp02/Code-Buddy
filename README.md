# Arcfold

Local-first codebase intelligence — index a repository, map its architecture, search the graph, and export documentation.

## What it does

1. **Load** a project from a local path, GitHub, or GitLab (remote repos read via API — no git clone)
2. **Index** with Tree-sitter + semantic reference graph — Python, JS/TS, Go, Java, Rust, C#, Dart, Docker
3. **C# / .NET** — Roslyn compiler analysis when .NET SDK is installed (references, routes, qualified symbols)
4. **Explore** with search, file tree, symbol navigation, and find-references
5. **Visualize** system architecture (zones + request flow), module maps, and route flows
6. **Search** the codebase with graph-backed Q&A — every answer cites `file:line` evidence
7. **Generate** documentation with architecture diagrams; edit and export as MD/DOCX/PDF
8. **Build context packs** for editor workflows (whole project or task-specific)

## Quick start

### 1. Setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r server/requirements.txt

cd web && npm install && cd ..
```

**Windows:** `tree-sitter-dockerfile` and `tree-sitter-dart` have no Windows wheels and are skipped automatically. Dockerfile indexing still works via line-based parsing. Dart files use regex fallback.

### 2. Configure Ollama Cloud (for chat)

```bash
cp .env.example .env
# Add your key from https://ollama.com/settings/keys
export OLLAMA_API_KEY=your_key
```

### 3. Run

```bash
chmod +x scripts/dev.sh
./scripts/dev.sh
```

- UI: http://localhost:5173
- API: http://127.0.0.1:8000

## Code intelligence

Arcfold builds a **two-tier index**:

| Tier | Engine | Provides |
|------|--------|----------|
| **Syntactic** | Tree-sitter | Symbols, imports, routes, modules |
| **Semantic** | Cross-file reference graph | Callers, usages, hub symbols |
| **C# deep** | Roslyn (requires .NET 8 SDK) | Qualified names, Find References, ASP.NET routes |

Agent tools: `search_symbol`, `find_references`, `get_callers`, `get_routes`, `get_system_architecture`.

### C# / Roslyn setup

```bash
# Install .NET 8 SDK, then index a C# project — Roslyn runs automatically
dotnet --version
```

The Roslyn analyzer lives in `analyzers/roslyn/Arcfold.Roslyn/`.

## Data directory

Indexed project data is stored in `.arcfold-data/` (legacy installs may still use `.code-buddy-data/`).

```
.arcfold-data/   Per-project SQLite graph + metadata
```

## API highlights

- `POST /api/projects` — index a local, GitHub, or GitLab project
- `GET /api/projects/{id}/diagrams/system` — system architecture diagram
- `GET /api/projects/{id}/references?q=SymbolName` — find symbol references
- `GET /api/projects/{id}/callers?q=SymbolName` — list callers of a symbol
- `GET /api/projects/{id}/summary` — compact index summary (hub symbols, stats)
- `POST /api/projects/{id}/documentation/stream` — generate project docs (NDJSON stream)
- `PUT /api/projects/{id}/documentation` — save edited documentation
- `POST /api/documentation/templates` — upload a custom documentation template
- `POST /api/projects/{id}/documentation/export` — save generated docs into the project repo

## License

MIT
