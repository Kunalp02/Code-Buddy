import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from server.agent.orchestrator import _client
from server.config import settings
from server.docs.context import compact_context_for_prompt, gather_documentation_context
from server.graph.queries import get_project

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

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


def list_templates() -> list[dict[str, str]]:
    templates = []
    if not TEMPLATES_DIR.exists():
        return templates
    for path in sorted(TEMPLATES_DIR.glob("*.md")):
        templates.append({"id": path.stem, "name": path.stem.replace("-", " ").title(), "filename": path.name})
    return templates


def get_template(template_id: str = "default") -> str:
    path = TEMPLATES_DIR / f"{template_id}.md"
    if not path.exists():
        path = TEMPLATES_DIR / "default.md"
    if not path.exists():
        raise FileNotFoundError("Documentation template not found")
    return path.read_text(encoding="utf-8")


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
    }


def save_documentation(project_id: str, content: str, template: str, model: str) -> None:
    doc_path = documentation_path(project_id)
    meta_path = documentation_meta_path(project_id)
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(content, encoding="utf-8")
    meta_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "template": template,
                "model": model,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


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
