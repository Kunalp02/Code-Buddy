# Code-Buddy

Local-first codebase intelligence: point at a project folder, get a searchable code graph, interactive architecture diagrams, and an AI agent powered by Ollama Cloud.

## What it does

1. **Load** a project from a local path, GitHub, or GitLab (remote repos read via API — no git clone)
2. **Index** files with Tree-sitter (symbols, imports, routes, modules) — Python, JavaScript/TypeScript, Go, Java, Rust, C#, Dart, Docker
3. **Explore** the codebase with search, file tree, and symbol navigation
4. **Visualize** system architecture (DB, cache, Docker), module maps, and route flows
5. **Chat** with a graph-first agent that cites evidence (`path:line`)
6. **Generate** professional project documentation from a customizable template
7. **Build context packs** — compact paste-ready prompts for Claude/Cursor (whole project or task-specific)

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

- Web UI: http://localhost:5173
- API: http://127.0.0.1:8000

### 4. Use

1. Open http://localhost:5173
2. Choose **Local**, **GitHub**, or **GitLab**
3. For GitHub/GitLab: enter PAT → **List repositories** → select repo & branch
4. Click **Scan & index project** (files fetched read-only via API)
4. Explore **Diagram**, **Explorer**, **Agent Chat**, **Documentation**, and **Context Pack**

## Architecture

```
web/          React UI (Vite)
server/       FastAPI backend
  indexer/    File walk + Tree-sitter parsing
  graph/      SQLite graph queries
  diagram/    L1/L3 diagram generation
  agent/      Ollama Cloud tool-calling agent
.code-buddy-data/   Per-project SQLite + metadata
```

## API highlights

- `POST /api/projects` — index a local path
- `GET /api/projects/{id}/diagrams/l1` — module architecture map
- `GET /api/projects/{id}/search?q=Auth` — symbol search
- `POST /api/projects/{id}/chat` — streaming agent (NDJSON)
- `POST /api/projects/{id}/documentation/stream` — generate project docs (NDJSON stream)
- `GET /api/projects/{id}/documentation` — retrieve last generated documentation
- `POST /api/documentation/templates` — upload a custom documentation template
- `POST /api/projects/{id}/documentation/export` — save generated docs into the project repo
- `POST /api/projects/{id}/context-pack` — build whole-project or task-specific context pack for AI tools

## Notes

- Runs locally: the backend reads your filesystem directly
- Chat requires `OLLAMA_API_KEY` for Ollama Cloud
- Indexing works without an API key
