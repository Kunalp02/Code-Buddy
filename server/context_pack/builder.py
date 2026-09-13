import re
from datetime import datetime, timezone
from typing import Any

from server.docs.context import (
    CONTEXT_FILES,
    _detect_license,
    _folder_tree,
    _parse_env_example,
    _read_bounded,
    gather_documentation_context,
)
from server.graph.queries import (
    get_file_symbols,
    get_module_deps,
    get_module_enrichment,
    get_modules,
    get_project,
    get_routes,
    read_snippet,
    search_symbols,
)

STOP_WORDS = {
    "a", "an", "the", "and", "or", "for", "to", "in", "on", "at", "of", "with",
    "is", "are", "was", "be", "this", "that", "it", "we", "i", "my", "our", "add",
    "create", "implement", "build", "make", "new", "using", "use", "from", "by",
}

SIZE_PRESETS = {
    "compact": 8000,
    "standard": 14000,
    "large": 22000,
}


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n\n...(truncated)"


def _keywords_from_task(task: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{1,}", task.lower())
    seen: set[str] = set()
    result: list[str] = []
    for w in words:
        if w in STOP_WORDS or len(w) < 3:
            continue
        if w not in seen:
            seen.add(w)
            result.append(w)
    return result[:12]


def _score_file_for_task(file_path: str, keywords: list[str], symbol_names: list[str]) -> int:
    path_lower = file_path.lower()
    score = 0
    for kw in keywords:
        if kw in path_lower:
            score += 3
        for sym in symbol_names:
            if kw in sym.lower():
                score += 2
    return score


def _format_architecture_summary(arch: dict[str, Any]) -> str:
    lines: list[str] = []
    summary = arch.get("summary", {})
    if arch.get("framework"):
        lines.append(f"- **Framework:** {arch['framework']}")

    for label, key in [
        ("Databases", "databases"),
        ("Cache", "caches"),
        ("Queues", "queues"),
        ("Auth", "auth"),
        ("ORM", "orms"),
    ]:
        items = summary.get(key, [])
        if items:
            names = ", ".join(f"{i['name']} ({i.get('technology', '')})" for i in items[:5])
            lines.append(f"- **{label}:** {names}")

    components = arch.get("components", [])
    containers = [c for c in components if c.get("component_type") == "container"]
    if containers:
        lines.append(f"- **Containers:** {', '.join(c['name'] for c in containers[:6])}")

    if summary.get("route_count"):
        lines.append(f"- **API routes:** {summary['route_count']} discovered")

    connections = arch.get("connections", [])
    if connections:
        lines.append(f"- **Connections:** {len(connections)} component links mapped")

    return "\n".join(lines) if lines else "- No system components detected — re-index if needed."


def _format_routes_table(routes: list[dict], limit: int = 30) -> str:
    if not routes:
        return "_No HTTP routes detected._"
    lines = ["| Method | Path | Handler | File |", "|--------|------|---------|------|"]
    for r in routes[:limit]:
        method = r.get("method") or "GET"
        path = r.get("path", "")
        handler = r.get("handler") or "—"
        file_path = r.get("file_path") or "—"
        line = r.get("line")
        loc = f"`{file_path}:{line}`" if file_path != "—" and line else f"`{file_path}`"
        lines.append(f"| {method} | `{path}` | {handler} | {loc} |")
    if len(routes) > limit:
        lines.append(f"\n_...and {len(routes) - limit} more routes._")
    return "\n".join(lines)


def _format_modules(modules: list[dict], enrichment: dict[str, dict], limit: int = 20) -> str:
    if not modules:
        return "_No modules detected._"
    lines = ["| Module | Files | Symbols | Routes |", "|--------|-------|---------|--------|"]
    for m in modules[:limit]:
        extra = enrichment.get(m["path"], {})
        lines.append(
            f"| `{m['path']}` | {m['file_count']} | {extra.get('symbol_count', 0)} | {extra.get('route_count', 0)} |"
        )
    return "\n".join(lines)


def _format_env_table(env_vars: list[dict]) -> str:
    if not env_vars:
        return "_No `.env.example` detected._"
    lines = ["| Variable | Default |", "|----------|---------|"]
    for v in env_vars[:20]:
        lines.append(f"| `{v['name']}` | `{v.get('default', '')}` |")
    return "\n".join(lines)


def _section_header(title: str) -> str:
    return f"\n## {title}\n\n"


def build_project_context_pack(project_id: str, max_chars: int | None = None) -> dict[str, Any]:
    budget = max_chars or SIZE_PRESETS["standard"]
    ctx = gather_documentation_context(project_id)
    meta = ctx["project"]
    arch = ctx["system_architecture"]
    routes = get_routes(project_id)
    modules = get_modules(project_id)
    enrichment = get_module_enrichment(project_id)
    deps = get_module_deps(project_id)

    parts: list[str] = []
    files_included: list[str] = []

    parts.append(f"# Context Pack: {meta['name']} (Full Project — Compact)\n")
    parts.append(
        "> **Usage:** Paste this into Claude, Cursor, or any AI coding assistant before asking "
        "questions or requesting changes about this codebase.\n"
    )
    parts.append(f"- **Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    parts.append(f"- **Project path:** `{meta.get('path', '')}`")
    parts.append(f"- **Indexed:** {meta.get('indexed_at', 'unknown')}")

    parts.append(_section_header("Project Overview"))
    stats = meta.get("stats", {})
    langs = ", ".join(f"{k} ({v})" for k, v in stats.get("languages", {}).items())
    parts.append(
        f"This is **{meta['name']}**, a **{meta.get('framework') or 'multi-language'}** project "
        f"with **{stats.get('files_parsed', 0)}** parsed files, **{stats.get('symbols', 0)}** symbols, "
        f"**{stats.get('modules', 0)}** modules, and **{stats.get('routes', 0)}** API routes.\n"
    )
    if langs:
        parts.append(f"**Languages:** {langs}")
    if meta.get("entry_points"):
        parts.append(f"**Entry points:** {', '.join(f'`{e}`' for e in meta['entry_points'][:8])}")
    if ctx.get("license"):
        parts.append(f"**License:** {ctx['license']}")

    parts.append(_section_header("System Architecture"))
    parts.append(_format_architecture_summary(arch))

    parts.append(_section_header("Modules"))
    parts.append(_format_modules(modules, enrichment, limit=15))

    if deps:
        parts.append("\n**Top module dependencies:**\n")
        for d in deps[:8]:
            parts.append(f"- `{d['from_module']}` → `{d['to_module']}` (weight {d['weight']})")

    parts.append(_section_header("API Routes"))
    parts.append(_format_routes_table(routes, limit=25))

    parts.append(_section_header("Environment Variables"))
    parts.append(_format_env_table(ctx.get("env_variables", [])))

    parts.append(_section_header("Folder Structure"))
    parts.append(f"```\n{ctx['folder_tree']}\n```")

    readme = ctx.get("existing_readme")
    if readme:
        parts.append(_section_header("README Excerpt"))
        parts.append(_truncate(readme, 2000))
        files_included.append("README.md")

    config_excerpts = ctx.get("config_files", {})
    if config_excerpts:
        parts.append(_section_header("Key Configuration"))
        for name, content in list(config_excerpts.items())[:4]:
            parts.append(f"### `{name}`\n```\n{_truncate(content, 1200)}\n```")
            files_included.append(name)

    parts.append(_section_header("Instructions for AI"))
    parts.append(
        "When answering or generating code for this project:\n"
        "1. Match existing patterns in the files and routes above.\n"
        "2. Do not invent dependencies, env vars, or routes not evidenced here.\n"
        "3. Cite file paths when referencing existing code.\n"
        "4. Ask clarifying questions if the task conflicts with detected architecture.\n"
    )

    content = "\n".join(parts)
    content = _truncate(content, budget)

    return {
        "mode": "project",
        "content": content,
        "char_count": len(content),
        "estimated_tokens": _estimate_tokens(content),
        "max_chars": budget,
        "files_referenced": files_included,
        "project_name": meta["name"],
    }


def build_task_context_pack(
    project_id: str,
    task: str,
    max_chars: int | None = None,
) -> dict[str, Any]:
    if not task.strip():
        raise ValueError("Task description is required for task-specific context packs")

    budget = max_chars or SIZE_PRESETS["standard"]
    ctx = gather_documentation_context(project_id)
    meta = ctx["project"]
    arch = ctx["system_architecture"]
    keywords = _keywords_from_task(task)

    # Gather relevant symbols across keywords
    symbol_hits: list[dict] = []
    seen_sym_ids: set[int] = set()
    for kw in keywords:
        for hit in search_symbols(project_id, kw, limit=8):
            if hit["id"] not in seen_sym_ids:
                seen_sym_ids.add(hit["id"])
                symbol_hits.append(hit)

    # Score routes by keyword relevance
    all_routes = get_routes(project_id)
    scored_routes: list[tuple[int, dict]] = []
    for r in all_routes:
        text = f"{r.get('path', '')} {r.get('handler', '')}".lower()
        score = sum(1 for kw in keywords if kw in text)
        if score:
            scored_routes.append((score, r))
    scored_routes.sort(key=lambda x: x[0], reverse=True)
    relevant_routes = [r for _, r in scored_routes[:10]]

    # Score files from symbol hits
    file_scores: dict[str, int] = {}
    file_symbols: dict[str, list[str]] = {}
    for hit in symbol_hits:
        fp = hit["file_path"]
        file_symbols.setdefault(fp, []).append(hit["name"])
        file_scores[fp] = file_scores.get(fp, 0) + 2

    for fp in file_scores:
        file_scores[fp] += _score_file_for_task(fp, keywords, file_symbols.get(fp, []))

    for r in relevant_routes:
        fp = r.get("file_path")
        if fp:
            file_scores[fp] = file_scores.get(fp, 0) + 5

    # Entry points as fallback context
    for ep in meta.get("entry_points", [])[:3]:
        file_scores.setdefault(ep, 1)

    ranked_files = sorted(file_scores.items(), key=lambda x: x[1], reverse=True)[:6]

    parts: list[str] = []
    snippets_included: list[str] = []

    parts.append(f"# Context Pack: {meta['name']} (Task-Specific)\n")
    parts.append(
        "> **Usage:** Paste this into Claude/Cursor along with your task. "
        "It contains relevant patterns and files from this codebase.\n"
    )

    parts.append(_section_header("Your Task"))
    parts.append(task.strip())

    parts.append(_section_header("Detected Keywords"))
    parts.append(", ".join(f"`{k}`" for k in keywords) if keywords else "_No specific keywords — using general context._")

    parts.append(_section_header("Project Snapshot"))
    parts.append(_format_architecture_summary(arch))

    if relevant_routes:
        parts.append(_section_header("Related API Routes"))
        parts.append(_format_routes_table(relevant_routes, limit=10))

    if symbol_hits:
        parts.append(_section_header("Relevant Symbols"))
        parts.append("| Name | Kind | Location |")
        parts.append("|------|------|----------|")
        for hit in symbol_hits[:15]:
            parts.append(
                f"| `{hit['name']}` | {hit['kind']} | `{hit['file_path']}:{hit['start_line']}` |"
            )

    parts.append(_section_header("Similar Patterns (copy these styles)"))
    snippet_budget = min(5000, budget // 3)
    used = 0
    for file_path, score in ranked_files:
        if used >= snippet_budget:
            break
        try:
            snippet = read_snippet(project_id, file_path, 1, None)
            content = snippet["content"]
            max_snip = min(800, snippet_budget - used)
            if len(content) > max_snip:
                content = content[:max_snip] + "\n...(truncated)"
            parts.append(f"### `{file_path}` (relevance {score})\n```\n{content}\n```")
            snippets_included.append(file_path)
            used += len(content)
        except FileNotFoundError:
            continue

    if not snippets_included and meta.get("entry_points"):
        parts.append("_No keyword-matched files — showing entry point instead._\n")
        try:
            ep = meta["entry_points"][0]
            snippet = read_snippet(project_id, ep, 1, None)
            parts.append(f"### `{ep}`\n```\n{_truncate(snippet['content'], 800)}\n```")
            snippets_included.append(ep)
        except FileNotFoundError:
            pass

    env_vars = ctx.get("env_variables", [])
    if env_vars:
        parts.append(_section_header("Environment Variables"))
        parts.append(_format_env_table(env_vars[:10]))

    parts.append(_section_header("Output Instructions for AI"))
    parts.append(
        f"Complete the task above for **{meta['name']}**.\n\n"
        "**Rules:**\n"
        "- Match naming, error handling, and structure from the pattern files above.\n"
        "- Reuse existing modules and imports — do not duplicate utilities.\n"
        "- If the task needs new routes, follow the style in Related API Routes.\n"
        "- Output only the files needed; prefer minimal diffs when editing.\n"
        "- If information is missing, list assumptions before generating code.\n"
    )

    content = "\n".join(parts)
    content = _truncate(content, budget)

    return {
        "mode": "task",
        "task": task.strip(),
        "content": content,
        "char_count": len(content),
        "estimated_tokens": _estimate_tokens(content),
        "max_chars": budget,
        "keywords": keywords,
        "files_referenced": snippets_included,
        "symbols_found": len(symbol_hits),
        "routes_found": len(relevant_routes),
        "project_name": meta["name"],
    }


def build_context_pack(
    project_id: str,
    mode: str = "project",
    task: str | None = None,
    size: str = "standard",
    max_chars: int | None = None,
) -> dict[str, Any]:
    if not get_project(project_id):
        raise ValueError("Project not found")

    budget = max_chars or SIZE_PRESETS.get(size, SIZE_PRESETS["standard"])

    if mode == "task":
        return build_task_context_pack(project_id, task or "", budget)
    if mode == "project":
        return build_project_context_pack(project_id, budget)
    raise ValueError(f"Unknown mode: {mode}. Use 'project' or 'task'.")
