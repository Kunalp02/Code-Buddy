import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from server.agent.orchestrator import chat_stream
from server.config import settings
from server.diagram.generator import generate_l1_diagram, generate_l3_flow
from server.graph.queries import (
    get_file_symbols,
    get_file_tree,
    get_module_deps,
    get_modules,
    get_project,
    get_routes,
    list_projects,
    read_snippet,
    search_symbols,
)
from server.indexer.engine import create_project, get_progress

app = FastAPI(title="Code-Buddy", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateProjectRequest(BaseModel):
    path: str = Field(..., description="Absolute or relative local project path")


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    model: str | None = None


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "ollama_host": settings.ollama_host,
        "ollama_model": settings.ollama_model,
        "has_api_key": bool(settings.ollama_api_key),
    }


@app.get("/api/projects")
def api_list_projects():
    return list_projects()


@app.post("/api/projects")
def api_create_project(body: CreateProjectRequest):
    path = Path(body.path).expanduser()
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {path}")
    try:
        meta = create_project(str(path.resolve()))
        return meta
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}")
def api_get_project(project_id: str):
    meta = get_project(project_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Project not found")
    progress = get_progress(project_id)
    return {**meta, "progress": {"status": progress.status, "processed": progress.processed, "total": progress.total, "message": progress.message, "error": progress.error}}


@app.get("/api/projects/{project_id}/files")
def api_files(project_id: str):
    _require_project(project_id)
    return get_file_tree(project_id)


@app.get("/api/projects/{project_id}/search")
def api_search(project_id: str, q: str, limit: int = 50):
    _require_project(project_id)
    return search_symbols(project_id, q, limit)


@app.get("/api/projects/{project_id}/snippet")
def api_snippet(project_id: str, path: str, start: int = 1, end: int | None = None):
    _require_project(project_id)
    try:
        return read_snippet(project_id, path, start, end)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/symbols")
def api_file_symbols(project_id: str, path: str):
    _require_project(project_id)
    return get_file_symbols(project_id, path)


@app.get("/api/projects/{project_id}/routes")
def api_routes(project_id: str):
    _require_project(project_id)
    return get_routes(project_id)


@app.get("/api/projects/{project_id}/modules")
def api_modules(project_id: str):
    _require_project(project_id)
    return {"modules": get_modules(project_id), "dependencies": get_module_deps(project_id)}


@app.get("/api/projects/{project_id}/diagrams/l1")
def api_diagram_l1(project_id: str):
    _require_project(project_id)
    return generate_l1_diagram(project_id)


@app.get("/api/projects/{project_id}/diagrams/l3")
def api_diagram_l3(project_id: str, route: str | None = None):
    _require_project(project_id)
    return generate_l3_flow(project_id, route)


@app.post("/api/projects/{project_id}/chat")
async def api_chat(project_id: str, body: ChatRequest):
    _require_project(project_id)

    async def event_stream():
        async for event in chat_stream(project_id, body.message, body.session_id, body.model):
            yield json.dumps(event) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


def _require_project(project_id: str):
    if not get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")


WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="static")
