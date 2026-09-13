# Code-Buddy

Local-first codebase intelligence: point at a project folder, get a searchable code graph, interactive architecture diagrams, and an AI agent powered by Ollama Cloud.

## What it does

1. **Load** a local project path
2. **Index** files with Tree-sitter (symbols, imports, routes, modules)
3. **Explore** the codebase with search, file tree, and symbol navigation
4. **Visualize** L1 module maps and L3 route flows
5. **Chat** with a graph-first agent that cites evidence (`path:line`)

## Quick start

### 1. Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt

cd web && npm install && cd ..
```

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
2. Enter a local project path (e.g. `/home/you/projects/my-app`)
3. Click **Scan & Index**
4. Explore **Diagram**, **Explorer**, and **Agent Chat**

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

## Notes

- Runs locally: the backend reads your filesystem directly
- Chat requires `OLLAMA_API_KEY` for Ollama Cloud
- Indexing works without an API key
