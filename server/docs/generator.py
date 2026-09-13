import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from server.agent.orchestrator import _client
from server.config import settings
from server.docs.context import compact_context_for_prompt, gather_documentation_context
from server.graph.queries import get_project

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
CUSTOM_TEMPLATES_DIR = settings.data_dir / "custom-templates"
TEMPLATE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$|^[a-z0-9]$")
DEFAULT_EXPORT_PATH = "DOCUMENTATION.md"

DOC_SYSTEM_PROMPT = """You are a senior technical writer generating professional project documentation.

Rules:
1. Follow the provided template structure EXACTLY — keep all section headings.
2. Replace bracket placeholders like [Project Name] with real values from the evidence.
3. Write clear, professional prose suitable for developers and stakeholders.
4. Base every claim on the provided project context — do NOT invent features, endpoints, or dependencies.
5. If information is missing, write "Not detected in codebase" or "TBD" — never guess.
6. Use real API routes, env vars, databases, and modules from the context when available.
7. Keep the Overview to 1-2 paragraphs; be concise but complete.
8. Output ONLY the final Markdown document — no preamble or explanation.
9. Use today's date from context for "Last Updated".
10. For API Reference, document discovered HTTP routes with method, path, and handler file when known.
"""


def _normalize_template_id(template_id: str) -> str:
    tid = template_id.strip().lower().replace("_", "-").replace(" ", "-")
    tid = re.sub(r"[^a-z0-9-]", "", tid)
    if not tid or not TEMPLATE_ID_RE.match(tid):
        raise ValueError("Template id must be 1-50 lowercase letters, numbers, or hyphens")
    return tid


def _template_path(template_id: str) -> Path | None:
    custom = CUSTOM_TEMPLATES_DIR / f"{template_id}.md"
    if custom.exists():
        return custom
    builtin = TEMPLATES_DIR / f"{template_id}.md"
    if builtin.exists():
        return builtin
    return None


def list_templates() -> list[dict[str, str]]:
    templates: list[dict[str, str]] = []
    seen: set[str] = set()

    for directory, source in ((TEMPLATES_DIR, "builtin"), (CUSTOM_TEMPLATES_DIR, "custom")):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            tid = path.stem
            if tid in seen:
                continue
            seen.add(tid)
            display_name = path.stem.replace("-", " ").title()
            if source == "custom":
                meta_file = directory / f"{tid}.json"
                if meta_file.exists():
                    try:
                        display_name = json.loads(meta_file.read_text()).get("name", display_name)
                    except Exception:
                        pass
            templates.append(
                {
                    "id": tid,
                    "name": display_name,
                    "filename": path.name,
                    "source": source,
                }
            )
    return templates


def get_template(template_id: str = "default") -> str:
    path = _template_path(template_id)
    if not path:
        path = TEMPLATES_DIR / "default.md"
    if not path.exists():
        raise FileNotFoundError("Documentation template not found")
    return path.read_text(encoding="utf-8")


def get_template_detail(template_id: str) -> dict[str, Any]:
    path = _template_path(template_id)
    if not path:
        raise FileNotFoundError(f"Template not found: {template_id}")
    source = "custom" if path.parent == CUSTOM_TEMPLATES_DIR else "builtin"
    return {
        "id": template_id,
        "name": template_id.replace("-", " ").title(),
        "filename": path.name,
        "source": source,
        "content": path.read_text(encoding="utf-8"),
    }


def save_custom_template(template_id: str, content: str, name: str | None = None) -> dict[str, str]:
    tid = _normalize_template_id(template_id)
    if not content.strip():
        raise ValueError("Template content cannot be empty")
    if len(content) > 100_000:
        raise ValueError("Template too large (max 100KB)")

    CUSTOM_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    path = CUSTOM_TEMPLATES_DIR / f"{tid}.md"
    path.write_text(content, encoding="utf-8")

    meta_path = CUSTOM_TEMPLATES_DIR / f"{tid}.json"
    meta_path.write_text(
        json.dumps({"name": name or tid.replace("-", " ").title(), "created_at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )
    return {"id": tid, "name": name or tid.replace("-", " ").title(), "source": "custom"}


def delete_custom_template(template_id: str) -> None:
    tid = _normalize_template_id(template_id)
    path = CUSTOM_TEMPLATES_DIR / f"{tid}.md"
    if not path.exists():
        raise FileNotFoundError(f"Custom template not found: {tid}")
    path.unlink()
    meta = CUSTOM_TEMPLATES_DIR / f"{tid}.json"
    if meta.exists():
        meta.unlink()


def export_documentation_to_project(project_id: str, relative_path: str = DEFAULT_EXPORT_PATH) -> dict[str, str]:
    meta = get_project(project_id)
    if not meta:
        raise ValueError("Project not found")

    doc = load_documentation(project_id)
    if not doc or not doc.get("content"):
        raise ValueError("No documentation generated yet — generate documentation first")

    rel = relative_path.strip().lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("Invalid export path")

    root = Path(meta["path"]).resolve()
    target = (root / rel).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError("Export path must be inside the project directory")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(doc["content"], encoding="utf-8")
    record_export(project_id, rel)

    return {"path": str(target), "relative_path": rel, "bytes": len(doc["content"])}


def documentation_path(project_id: str) -> Path:
    return settings.data_dir / project_id / "documentation.md"


def documentation_meta_path(project_id: str) -> Path:
    return settings.data_dir / project_id / "documentation.json"


def load_documentation(project_id: str) -> dict[str, Any] | None:
    meta_path = documentation_meta_path(project_id)
    doc_path = documentation_path(project_id)
    if not doc_path.exists():
        return None
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
    return {
        "content": doc_path.read_text(encoding="utf-8"),
        "generated_at": meta.get("generated_at"),
        "template": meta.get("template", "default"),
        "model": meta.get("model"),
        "exported_path": meta.get("exported_path"),
    }


def save_documentation(project_id: str, content: str, template: str, model: str) -> None:
    doc_path = documentation_path(project_id)
    meta_path = documentation_meta_path(project_id)
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(content, encoding="utf-8")

    existing_meta: dict[str, Any] = {}
    if meta_path.exists():
        existing_meta = json.loads(meta_path.read_text())

    meta_path.write_text(
        json.dumps(
            {
                **existing_meta,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "template": template,
                "model": model,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def record_export(project_id: str, relative_path: str) -> None:
    meta_path = documentation_meta_path(project_id)
    existing: dict[str, Any] = {}
    if meta_path.exists():
        existing = json.loads(meta_path.read_text())
    existing["exported_path"] = relative_path
    existing["exported_at"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def _build_user_prompt(template: str, context_json: str) -> str:
    return f"""Generate complete project documentation using this template structure.

TEMPLATE:
{template}

---
PROJECT CONTEXT (from indexed codebase — use as sole source of truth):
{context_json}

---
Fill every section of the template with accurate content derived from the context.
Return the complete Markdown document only."""


def generate_documentation_sync(project_id: str, template_id: str = "default", model: str | None = None) -> str:
    if not get_project(project_id):
        raise ValueError("Project not found")

    ctx = gather_documentation_context(project_id)
    template = get_template(template_id)
    context_json = compact_context_for_prompt(ctx)
    model_name = model or settings.ollama_model_deep or settings.ollama_model

    client = _client()
    response = client.chat(
        model=model_name,
        messages=[
            {"role": "system", "content": DOC_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(template, context_json)},
        ],
        stream=False,
    )
    content = (response.message.content or "").strip()
    if not content:
        raise RuntimeError("Documentation generation returned empty content")

    save_documentation(project_id, content, template_id, model_name)
    return content


async def documentation_stream(
    project_id: str,
    template_id: str = "default",
    model: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    if not get_project(project_id):
        yield {"type": "error", "content": "Project not found"}
        return

    try:
        ctx = gather_documentation_context(project_id)
        template = get_template(template_id)
        context_json = compact_context_for_prompt(ctx)
        model_name = model or settings.ollama_model_deep or settings.ollama_model

        yield {"type": "meta", "template": template_id, "model": model_name, "project": ctx["project"]["name"]}

        client = _client()
        stream = client.chat(
            model=model_name,
            messages=[
                {"role": "system", "content": DOC_SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(template, context_json)},
            ],
            stream=True,
        )

        full_content: list[str] = []
        for chunk in stream:
            token = chunk.message.content or ""
            if token:
                full_content.append(token)
                yield {"type": "token", "content": token}

        content = "".join(full_content).strip()
        if content:
            save_documentation(project_id, content, template_id, model_name)
            yield {"type": "saved", "generated_at": datetime.now(timezone.utc).isoformat()}
        yield {"type": "done"}
    except Exception as exc:
        hint = ""
        if "401" in str(exc).lower() or "unauthorized" in str(exc).lower():
            hint = " Set OLLAMA_API_KEY."
        yield {"type": "error", "content": f"Documentation generation failed: {exc}.{hint}"}
