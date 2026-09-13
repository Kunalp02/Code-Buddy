from pathlib import Path

from server.config import settings
from server.db import get_db, load_meta


def list_projects() -> list[dict]:
    projects = []
    data_dir = settings.data_dir
    if not data_dir.exists():
        return []
    for child in sorted(data_dir.iterdir()):
        if child.is_dir():
            meta = load_meta(child.name)
            if meta:
                projects.append(meta)
    return sorted(projects, key=lambda p: p.get("indexed_at", p.get("created_at", "")), reverse=True)


def get_project(project_id: str) -> dict | None:
    return load_meta(project_id)


def search_symbols(project_id: str, query: str, limit: int = 50) -> list[dict]:
    with get_db(project_id) as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.name, s.kind, s.start_line, s.end_line, s.signature, f.path AS file_path
            FROM symbols s
            JOIN files f ON f.id = s.file_id
            WHERE s.name LIKE ? OR f.path LIKE ?
            ORDER BY
                CASE WHEN s.name = ? THEN 0 WHEN s.name LIKE ? THEN 1 ELSE 2 END,
                s.name
            LIMIT ?
            """,
            (f"%{query}%", f"%{query}%", query, f"{query}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_symbol(project_id: str, symbol_id: int) -> dict | None:
    with get_db(project_id) as conn:
        row = conn.execute(
            """
            SELECT s.*, f.path AS file_path
            FROM symbols s
            JOIN files f ON f.id = s.file_id
            WHERE s.id = ?
            """,
            (symbol_id,),
        ).fetchone()
        return dict(row) if row else None


def get_file_tree(project_id: str) -> list[dict]:
    with get_db(project_id) as conn:
        rows = conn.execute("SELECT path, language, line_count FROM files ORDER BY path").fetchall()
        return [dict(r) for r in rows]


def read_snippet(project_id: str, file_path: str, start_line: int = 1, end_line: int | None = None) -> dict:
    meta = load_meta(project_id)
    if not meta:
        raise FileNotFoundError("Project not found")
    root = Path(meta["path"])
    abs_path = root / file_path
    if not abs_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if end_line is None:
        end_line = min(start_line + settings.max_snippet_lines - 1, len(lines))
    end_line = min(end_line, start_line + settings.max_snippet_lines - 1)
    snippet = "\n".join(lines[start_line - 1 : end_line])
    return {
        "path": file_path,
        "start_line": start_line,
        "end_line": end_line,
        "content": snippet,
        "total_lines": len(lines),
    }


def get_routes(project_id: str) -> list[dict]:
    with get_db(project_id) as conn:
        rows = conn.execute(
            """
            SELECT r.method, r.path, r.handler, r.line, f.path AS file_path
            FROM routes r
            LEFT JOIN files f ON f.id = r.file_id
            ORDER BY r.path
            """
        ).fetchall()
        return [dict(r) for r in rows]


def get_modules(project_id: str) -> list[dict]:
    with get_db(project_id) as conn:
        rows = conn.execute(
            "SELECT id, path, name, file_count FROM modules ORDER BY file_count DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_module_deps(project_id: str) -> list[dict]:
    with get_db(project_id) as conn:
        rows = conn.execute(
            """
            SELECT
                m1.path AS from_module,
                m1.name AS from_name,
                m2.path AS to_module,
                m2.name AS to_name,
                d.weight
            FROM module_deps d
            JOIN modules m1 ON m1.id = d.from_module_id
            JOIN modules m2 ON m2.id = d.to_module_id
            ORDER BY d.weight DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def get_file_symbols(project_id: str, file_path: str) -> list[dict]:
    with get_db(project_id) as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.name, s.kind, s.start_line, s.end_line, s.signature
            FROM symbols s
            JOIN files f ON f.id = s.file_id
            WHERE f.path = ?
            ORDER BY s.start_line
            """,
            (file_path,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_stats(project_id: str) -> dict:
    meta = load_meta(project_id) or {}
    return meta.get("stats", {})
