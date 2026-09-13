import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.graph.queries import (
    get_file_tree,
    get_module_deps,
    get_modules,
    get_project,
    get_routes,
    get_system_architecture,
)

CONTEXT_FILES = [
    "README.md",
    "README.rst",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "pubspec.yaml",
    ".env.example",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "Dockerfile",
    "Makefile",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "LICENSE",
    "LICENSE.md",
]

MAX_FILE_CHARS = 6000
MAX_TREE_DEPTH = 3


def _read_bounded(path: Path, max_chars: int = MAX_FILE_CHARS) -> str | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if len(text) > max_chars:
        return text[:max_chars] + "\n...(truncated)"
    return text


def _folder_tree(root: Path, max_depth: int = MAX_TREE_DEPTH) -> str:
    lines: list[str] = [root.name + "/"]

    def walk(dir_path: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return
        skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "target", ".arcfold-data", ".code-buddy-data"}
        dirs = [e for e in entries if e.is_dir() and e.name not in skip and not e.name.startswith(".")]
        files = [e for e in entries if e.is_file() and not e.name.startswith(".")]
        for d in dirs[:12]:
            lines.append(f"{prefix}{d.name}/")
            walk(d, prefix + "  ", depth + 1)
        for f in files[:8]:
            lines.append(f"{prefix}{f.name}")
        if len(dirs) > 12 or len(files) > 8:
            lines.append(f"{prefix}...")

    walk(root, "  ", 1)
    return "\n".join(lines[:80])


def _parse_env_example(text: str) -> list[dict[str, str]]:
    vars_found: list[dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([A-Z_][A-Z0-9_]*)=(.*)", line)
        if m:
            key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
            vars_found.append({"name": key, "default": val or ""})
    return vars_found[:30]


def _detect_license(root: Path) -> str | None:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
        p = root / name
        if p.exists():
            head = _read_bounded(p, 500) or ""
            if "MIT" in head:
                return "MIT"
            if "Apache" in head:
                return "Apache-2.0"
            if "GPL" in head:
                return "GPL"
            return name
    return None


def gather_documentation_context(project_id: str) -> dict[str, Any]:
    meta = get_project(project_id) or {}
    root = Path(meta.get("path", ""))
    if not root.exists():
        raise FileNotFoundError(f"Project path not found: {root}")

    arch = get_system_architecture(project_id)
    modules = get_modules(project_id)
    deps = get_module_deps(project_id)
    routes = get_routes(project_id)
    files = get_file_tree(project_id)

    existing_files: dict[str, str] = {}
    for name in CONTEXT_FILES:
        content = _read_bounded(root / name)
        if content:
            existing_files[name] = content

    env_vars = []
    if ".env.example" in existing_files:
        env_vars = _parse_env_example(existing_files[".env.example"])

    top_modules = sorted(modules, key=lambda m: m["file_count"], reverse=True)[:15]
    hub_modules = sorted(
        deps,
        key=lambda d: d.get("weight", 0),
        reverse=True,
    )[:10]

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "project": {
            "name": meta.get("name", root.name),
            "path": str(root),
            "framework": meta.get("framework"),
            "status": meta.get("status", "indexed"),
            "indexed_at": meta.get("indexed_at"),
            "entry_points": meta.get("entry_points", []),
            "stats": meta.get("stats", {}),
        },
        "folder_tree": _folder_tree(root),
        "license": _detect_license(root),
        "existing_readme": existing_files.get("README.md") or existing_files.get("README.rst"),
        "config_files": {k: v for k, v in existing_files.items() if k not in ("README.md", "README.rst")},
        "env_variables": env_vars,
        "system_architecture": arch,
        "modules": top_modules,
        "module_dependencies": hub_modules,
        "routes": routes[:40],
        "file_summary": {
            "total_indexed": len(files),
            "languages": meta.get("stats", {}).get("languages", {}),
        },
    }


def compact_context_for_prompt(ctx: dict[str, Any]) -> str:
    """Serialize context for LLM prompt, staying within reasonable size."""
    slim = {
        "project": ctx["project"],
        "generated_at": ctx["generated_at"],
        "license": ctx["license"],
        "folder_tree": ctx["folder_tree"],
        "env_variables": ctx["env_variables"],
        "system_architecture": {
            "framework": ctx["system_architecture"].get("framework"),
            "summary": ctx["system_architecture"].get("summary"),
            "components": ctx["system_architecture"].get("components", [])[:20],
            "connections": ctx["system_architecture"].get("connections", [])[:20],
        },
        "modules": ctx["modules"],
        "module_dependencies": ctx["module_dependencies"],
        "routes": ctx["routes"],
        "file_summary": ctx["file_summary"],
        "existing_readme_excerpt": (ctx.get("existing_readme") or "")[:2500],
        "config_excerpts": {k: v[:1500] for k, v in ctx.get("config_files", {}).items()},
    }
    return json.dumps(slim, indent=2, default=str)
