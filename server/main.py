import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from server.agent.orchestrator import chat_stream
from server.config import settings
from server.diagram.generator import generate_l1_diagram, generate_l3_flow, generate_system_diagram
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
from server.context_pack.builder import SIZE_PRESETS, build_context_pack
from server.docs.generator import (
    DEFAULT_EXPORT_PATH,
    delete_custom_template,
    documentation_stream,
    export_documentation_to_project,
    generate_documentation_sync,
    get_template_detail,
    list_templates,
    load_documentation,
    save_custom_template,
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
    source: str = Field("local", description="local | github | gitlab")
    path: str | None = Field(None, description="Local directory path (required for source=local)")
    url: str | None = Field(None, description="Repository URL or namespace (optional)")
    branch: str | None = Field(None, description="Git branch to read via API")
    token: str | None = Field(None, description="PAT to read remote repo via API (not stored)")
    owner: str | None = Field(None, description="GitHub owner/org")
    repo: str | None = Field(None, description="GitHub repository name")
    gitlab_project_id: int | None = Field(None, description="GitLab numeric project id")
    gitlab_host: str = Field("https://gitlab.com", description="GitLab instance URL")


class GitHubTokenRequest(BaseModel):
    token: str


class GitHubBranchesRequest(BaseModel):
    token: str
    owner: str
    repo: str


class GitLabTokenRequest(BaseModel):
    token: str
    host: str = "https://gitlab.com"


class GitLabBranchesRequest(BaseModel):
    token: str
    project_id: int
    host: str = "https://gitlab.com"


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    model: str | None = None


class GenerateDocsRequest(BaseModel):
    template: str = "default"
    model: str | None = None


class UploadTemplateRequest(BaseModel):
    id: str = Field(..., description="Template id (lowercase, hyphens)")
    content: str = Field(..., description="Markdown template content")
    name: str | None = Field(None, description="Display name")


class ExportDocsRequest(BaseModel):
    path: str = Field(DEFAULT_EXPORT_PATH, description="Relative path inside project root")


class ContextPackRequest(BaseModel):
    mode: str = Field("project", description="'project' for full compact pack, 'task' for task-specific")
    task: str | None = Field(None, description="Task description (required when mode=task)")
    size: str = Field("standard", description="compact | standard | large")
    max_chars: int | None = Field(None, description="Override character budget")


@app.post("/api/integrations/github/repos")
def api_github_repos(body: GitHubTokenRequest):
    try:
        from server.integrations.github import list_repositories

        return list_repositories(body.token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/integrations/github/branches")
def api_github_branches(body: GitHubBranchesRequest):
    try:
        from server.integrations.github import list_branches

        return list_branches(body.token, body.owner, body.repo)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/integrations/gitlab/projects")
def api_gitlab_projects(body: GitLabTokenRequest):
    try:
        from server.integrations.gitlab import list_projects

        return list_projects(body.token, body.host)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/integrations/gitlab/branches")
def api_gitlab_branches(body: GitLabBranchesRequest):
    try:
        from server.integrations.gitlab import list_branches

        return list_branches(body.token, body.project_id, body.host)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    source = (body.source or "local").lower()
    if source == "local" and not body.path:
        raise HTTPException(status_code=400, detail="path is required for local projects")
    if source == "github" and not ((body.owner and body.repo) or body.url):
        raise HTTPException(status_code=400, detail="GitHub owner+repo or url is required")
    if source == "gitlab" and not body.gitlab_project_id:
        raise HTTPException(status_code=400, detail="gitlab_project_id is required for GitLab")
    if source in {"github", "gitlab"} and not body.token:
        raise HTTPException(status_code=400, detail="token is required to read remote repositories via API")
    try:
        meta = create_project(
            path=body.path,
            source=source,
            url=body.url,
            branch=body.branch,
            token=body.token,
            owner=body.owner,
            repo=body.repo,
            gitlab_project_id=body.gitlab_project_id,
            gitlab_host=body.gitlab_host,
        )
        return meta
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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


@app.get("/api/projects/{project_id}/diagrams/system")
def api_diagram_system(project_id: str):
    _require_project(project_id)
    return generate_system_diagram(project_id)


@app.get("/api/projects/{project_id}/diagrams/l1")
def api_diagram_l1(project_id: str):
    _require_project(project_id)
    return generate_l1_diagram(project_id)


@app.get("/api/projects/{project_id}/architecture")
def api_architecture(project_id: str):
    _require_project(project_id)
    from server.graph.queries import get_system_architecture

    return get_system_architecture(project_id)


@app.get("/api/projects/{project_id}/diagrams/l3")
def api_diagram_l3(project_id: str, route: str | None = None):
    _require_project(project_id)
    return generate_l3_flow(project_id, route)


@app.get("/api/documentation/templates")
def api_doc_templates():
    return list_templates()


@app.get("/api/documentation/templates/{template_id}")
def api_get_doc_template(template_id: str):
    try:
        return get_template_detail(template_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/documentation/templates")
def api_upload_doc_template(body: UploadTemplateRequest):
    try:
        return save_custom_template(body.id, body.content, body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/documentation/templates/{template_id}")
def api_delete_doc_template(template_id: str):
    try:
        delete_custom_template(template_id)
        return {"deleted": template_id}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/documentation")
def api_get_documentation(project_id: str):
    _require_project(project_id)
    doc = load_documentation(project_id)
    if not doc:
        raise HTTPException(status_code=404, detail="No documentation generated yet")
    return doc


@app.post("/api/projects/{project_id}/documentation/generate")
def api_generate_documentation_sync(project_id: str, body: GenerateDocsRequest):
    _require_project(project_id)
    try:
        content = generate_documentation_sync(project_id, body.template, body.model)
        return load_documentation(project_id) or {"content": content}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/context-pack/sizes")
def api_context_pack_sizes():
    return {"presets": {k: v for k, v in SIZE_PRESETS.items()}}


@app.post("/api/projects/{project_id}/context-pack")
def api_build_context_pack(project_id: str, body: ContextPackRequest):
    _require_project(project_id)
    try:
        return build_context_pack(
            project_id,
            mode=body.mode,
            task=body.task,
            size=body.size,
            max_chars=body.max_chars,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/documentation/export")
def api_export_documentation(project_id: str, body: ExportDocsRequest):
    _require_project(project_id)
    try:
        return export_documentation_to_project(project_id, body.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/documentation/stream")
async def api_generate_documentation_stream(project_id: str, body: GenerateDocsRequest):
    _require_project(project_id)

    async def event_stream():
        async for event in documentation_stream(project_id, body.template, body.model):
            yield json.dumps(event) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


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
