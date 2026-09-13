import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from server.db import get_db, init_schema, save_meta
from server.indexer.parser import parse_file
from server.indexer.walker import module_key, walk_project


class IndexProgress:
    def __init__(self) -> None:
        self.status = "idle"
        self.total = 0
        self.processed = 0
        self.message = ""
        self.error: str | None = None


_progress: dict[str, IndexProgress] = {}


def get_progress(project_id: str) -> IndexProgress:
    return _progress.get(project_id, IndexProgress())


def index_project(project_id: str, root_path: Path) -> dict:
    progress = IndexProgress()
    progress.status = "indexing"
    _progress[project_id] = progress

    try:
        files = walk_project(root_path)
        progress.total = len(files)

        languages: Counter[str] = Counter()
        module_files: dict[str, int] = defaultdict(int)
        module_imports: dict[str, set[str]] = defaultdict(set)
        entry_points: list[str] = []
        parsed_count = 0
        skipped_count = 0

        with get_db(project_id) as conn:
            init_schema(conn)
            conn.execute("DELETE FROM module_deps")
            conn.execute("DELETE FROM modules")
            conn.execute("DELETE FROM routes")
            conn.execute("DELETE FROM imports")
            conn.execute("DELETE FROM symbols")
            conn.execute("DELETE FROM files")

            for file_path in files:
                rel = str(file_path.relative_to(root_path))
                progress.processed += 1
                progress.message = f"Parsing {rel}"

                parsed = parse_file(file_path)
                if not parsed.symbols and not parsed.imports and parsed.line_count == 0:
                    skipped_count += 1
                    continue

                lang = file_path.suffix.lstrip(".")
                languages[lang] += 1
                parsed_count += 1

                cur = conn.execute(
                    "INSERT INTO files (path, language, line_count) VALUES (?, ?, ?)",
                    (rel, lang, parsed.line_count),
                )
                file_id = cur.lastrowid

                mod = module_key(root_path, file_path)
                module_files[mod] += 1

                lower_name = file_path.name.lower()
                if lower_name in {
                    "main.py",
                    "app.py",
                    "index.ts",
                    "index.js",
                    "main.go",
                    "server.py",
                    "manage.py",
                }:
                    entry_points.append(rel)

                for sym in parsed.symbols:
                    conn.execute(
                        """
                        INSERT INTO symbols (file_id, name, kind, start_line, end_line, signature)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (file_id, sym.name, sym.kind, sym.start_line, sym.end_line, sym.signature),
                    )

                for imp in parsed.imports:
                    conn.execute(
                        "INSERT INTO imports (file_id, source, imported_name, line) VALUES (?, ?, ?, ?)",
                        (file_id, imp.source, imp.imported_name, imp.line),
                    )
                    module_imports[mod].add(imp.source)

                for route in parsed.routes:
                    conn.execute(
                        """
                        INSERT INTO routes (file_id, method, path, handler, line)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (file_id, route.method, route.path, route.handler, route.line),
                    )

            module_id_map: dict[str, int] = {}
            known_modules = set(module_files.keys())
            for mod_path, count in sorted(module_files.items()):
                cur = conn.execute(
                    "INSERT INTO modules (path, name, file_count) VALUES (?, ?, ?)",
                    (mod_path, mod_path.split("/")[-1], count),
                )
                module_id_map[mod_path] = cur.lastrowid

            resolved_deps: dict[tuple[str, str], int] = defaultdict(int)
            for from_mod, import_sources in module_imports.items():
                for source in import_sources:
                    to_mod = _import_to_module(source, known_modules)
                    if to_mod and to_mod != from_mod:
                        resolved_deps[(from_mod, to_mod)] += 1

            for (from_mod, to_mod), weight in resolved_deps.items():
                from_id = module_id_map.get(from_mod)
                to_id = module_id_map.get(to_mod)
                if not from_id or not to_id:
                    continue
                conn.execute(
                    """
                    INSERT INTO module_deps (from_module_id, to_module_id, weight)
                    VALUES (?, ?, ?)
                    ON CONFLICT(from_module_id, to_module_id)
                    DO UPDATE SET weight = weight + excluded.weight
                    """,
                    (from_id, to_id, weight),
                )

        framework = _detect_framework(languages, root_path)
        meta = {
            "id": project_id,
            "path": str(root_path),
            "name": root_path.name,
            "status": "ready",
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            "stats": {
                "files_total": len(files),
                "files_parsed": parsed_count,
                "files_skipped": skipped_count,
                "symbols": _count_symbols(project_id),
                "modules": len(module_files),
                "routes": _count_routes(project_id),
                "languages": dict(languages),
            },
            "framework": framework,
            "entry_points": entry_points[:10],
        }
        save_meta(project_id, meta)
        progress.status = "ready"
        progress.message = "Indexing complete"
        return meta
    except Exception as exc:
        progress.status = "failed"
        progress.error = str(exc)
        raise
    finally:
        _progress[project_id] = progress


def _import_to_module(source: str, known_modules: set[str]) -> str | None:
    source = source.strip().strip("'\"")
    if not source or source.startswith("@") or source in {"os", "sys", "json", "re", "typing", "pathlib", "datetime", "collections", "dataclasses", "asyncio", "uuid", "math", "sqlite3", "contextlib"}:
        return None

    slash = source.replace(".", "/")
    parts = source.split(".")

    candidates: list[str] = []
    for i in range(len(parts), 0, -1):
        candidates.append("/".join(parts[:i]))

    for candidate in candidates:
        if candidate in known_modules:
            return candidate

    if "/" in slash:
        return slash.split("/")[0]
    if parts:
        return parts[0]
    return None


def _detect_framework(languages: Counter[str], root: Path) -> str | None:
    markers = {
        "package.json": "nodejs",
        "pyproject.toml": "python",
        "requirements.txt": "python",
        "go.mod": "go",
        "Cargo.toml": "rust",
    }
    for marker, fw in markers.items():
        if (root / marker).exists():
            if marker == "package.json":
                try:
                    import json

                    pkg = json.loads((root / marker).read_text())
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    if "next" in deps:
                        return "nextjs"
                    if "@nestjs/core" in deps:
                        return "nestjs"
                    if "express" in deps:
                        return "express"
                    if "react" in deps:
                        return "react"
                except Exception:
                    pass
            return fw
    return None


def _count_symbols(project_id: str) -> int:
    with get_db(project_id) as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM symbols").fetchone()
        return row["c"] if row else 0


def _count_routes(project_id: str) -> int:
    with get_db(project_id) as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM routes").fetchone()
        return row["c"] if row else 0


def create_project(path: str) -> dict:
    root = Path(path).resolve()
    project_id = str(uuid.uuid4())[:8]
    meta = {
        "id": project_id,
        "path": str(root),
        "name": root.name,
        "status": "indexing",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_meta(project_id, meta)
    return index_project(project_id, root)
