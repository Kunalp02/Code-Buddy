# Arcfold

Local-first codebase intelligence — index a repository, map its architecture, search the graph, and export documentation.

## What it does

1. **Load** a project from a local path, GitHub, or GitLab (remote repos read via API — no git clone)
2. **Index** files with Tree-sitter (symbols, imports, routes, modules) — Python, JavaScript/TypeScript, Go, Java, Rust, C#, Dart, Docker
3. **Explore** the codebase with search, file tree, and symbol navigation
4. **Visualize** system architecture (DB, cache, Docker), module maps, and route flows
5. **Search** the codebase with graph-backed Q&A and cited file references
6. **Generate** project documentation from a customizable template
7. **Build context packs** — compact prompts for your editor workflow (whole project or task-specific)

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

## Data directory

Indexed project data is stored in `.arcfold-data/` (legacy installs may still use `.code-buddy-data/`).

```
.arcfold-data/   Per-project SQLite + metadata
```

## API highlights

- `POST /api/projects` — index a local, GitHub, or GitLab project
- `GET /api/projects/{id}/diagrams/system` — system architecture diagram
- `POST /api/projects/{id}/documentation/stream` — generate project docs (NDJSON stream)
- `PUT /api/projects/{id}/documentation` — save edited documentation
- `POST /api/documentation/templates` — upload a custom documentation template
- `POST /api/projects/{id}/documentation/export` — save generated docs into the project repo

## License

MIT
