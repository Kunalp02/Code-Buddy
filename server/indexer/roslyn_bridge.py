"""Roslyn semantic analyzer bridge for C# / .NET projects."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

ROSLYN_PROJECT = Path(__file__).resolve().parents[2] / "analyzers" / "roslyn" / "Arcfold.Roslyn"


def _find_dotnet() -> str | None:
    dotnet = shutil.which("dotnet")
    if dotnet:
        return dotnet
    home = Path.home() / ".dotnet" / "dotnet"
    return str(home) if home.exists() else None


def _build_analyzer(dotnet: str) -> bool:
    if not ROSLYN_PROJECT.exists():
        return False
    try:
        subprocess.run(
            [dotnet, "build", str(ROSLYN_PROJECT), "-c", "Release", "-v", "q"],
            check=True,
            capture_output=True,
            timeout=180,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.warning("Roslyn analyzer build failed: %s", exc)
        return False


def _analyzer_dll() -> Path | None:
    dll = ROSLYN_PROJECT / "bin" / "Release" / "net8.0" / "Arcfold.Roslyn.dll"
    return dll if dll.exists() else None


def has_csharp_project(root: Path) -> bool:
    return any(root.rglob("*.csproj")) or any(root.rglob("*.sln"))


def run_roslyn_analysis(conn, root_path: Path) -> dict:
    """Run Roslyn analyzer and merge symbols, routes, references into the graph."""
    if not has_csharp_project(root_path):
        return {"skipped": True, "reason": "no csharp project"}

    dotnet = _find_dotnet()
    if not dotnet:
        return {"skipped": True, "reason": "dotnet not installed"}

    if not _analyzer_dll() and not _build_analyzer(dotnet):
        return {"skipped": True, "reason": "roslyn build failed"}

    dll = _analyzer_dll()
    if not dll:
        return {"skipped": True, "reason": "analyzer dll missing"}

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        out_path = tmp.name

    try:
        env = os.environ.copy()
        env["DOTNET_ROOT"] = str(Path(dotnet).parent)
        result = subprocess.run(
            [dotnet, str(dll), str(root_path.resolve()), out_path],
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        if result.returncode not in (0, 2) or not Path(out_path).exists():
            return {"skipped": True, "reason": result.stderr[:200] or "roslyn failed"}

        data = json.loads(Path(out_path).read_text(encoding="utf-8"))
        if data.get("skipped"):
            return {"skipped": True, "reason": data.get("reason", "skipped")}

        return _merge_roslyn_results(conn, root_path, data)
    except Exception as exc:
        logger.warning("Roslyn analysis error: %s", exc)
        return {"skipped": True, "reason": str(exc)}
    finally:
        Path(out_path).unlink(missing_ok=True)


def _merge_roslyn_results(conn, root_path: Path, data: dict) -> dict:
    from server.indexer.semantic import _ensure_semantic_columns

    _ensure_semantic_columns(conn)
    file_map = {
        row["path"]: row["id"]
        for row in conn.execute("SELECT id, path FROM files").fetchall()
    }

    symbols_added = 0
    routes_added = 0
    refs_added = 0

    sym_by_qname: dict[str, int] = {}

    for sym in data.get("symbols", []):
        rel = sym.get("file", "").replace("\\", "/")
        if not rel:
            continue
        file_id = file_map.get(rel)
        if not file_id:
            continue

        qname = sym.get("qualifiedName") or sym.get("QualifiedName") or ""
        name = sym.get("name") or sym.get("Name") or ""
        kind = (sym.get("kind") or sym.get("Kind") or "symbol").lower()
        line = sym.get("line") or sym.get("Line") or 1
        end_line = sym.get("endLine") or sym.get("EndLine") or line
        container = sym.get("container") or sym.get("Container")
        signature = sym.get("signature") or sym.get("Signature")

        existing = conn.execute(
            """
            SELECT id FROM symbols
            WHERE file_id = ? AND name = ? AND start_line = ?
            """,
            (file_id, name, line),
        ).fetchone()

        if existing:
            sym_id = existing["id"]
            conn.execute(
                "UPDATE symbols SET qualified_name = ?, container = ?, signature = COALESCE(?, signature) WHERE id = ?",
                (qname, container, signature, sym_id),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO symbols (file_id, name, kind, start_line, end_line, signature, qualified_name, container)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (file_id, name, kind, line, end_line, signature, qname, container),
            )
            sym_id = cur.lastrowid
            symbols_added += 1

        if qname:
            sym_by_qname[qname] = sym_id

    for route in data.get("routes", []):
        rel = route.get("file", "").replace("\\", "/")
        file_id = file_map.get(rel)
        if not file_id:
            continue
        method = (route.get("method") or route.get("Method") or "GET").upper()
        path = route.get("path") or route.get("Path") or ""
        handler = route.get("handler") or route.get("Handler")
        line = route.get("line") or route.get("Line")
        if not path:
            continue
        dup = conn.execute(
            "SELECT id FROM routes WHERE file_id = ? AND method = ? AND path = ?",
            (file_id, method, path),
        ).fetchone()
        if dup:
            continue
        conn.execute(
            "INSERT INTO routes (file_id, method, path, handler, line) VALUES (?, ?, ?, ?, ?)",
            (file_id, method, path, handler, line),
        )
        routes_added += 1

    conn.execute("DELETE FROM symbol_refs WHERE ref_kind = 'roslyn'")

    for ref in data.get("references", []):
        to_qname = ref.get("toQualifiedName") or ref.get("ToQualifiedName") or ""
        to_name = ref.get("toName") or ref.get("ToName") or ""
        from_file = (ref.get("fromFile") or ref.get("FromFile") or "").replace("\\", "/")
        from_line = ref.get("fromLine") or ref.get("FromLine") or 0

        to_id = sym_by_qname.get(to_qname)
        if not to_id and to_name:
            row = conn.execute(
                """
                SELECT s.id FROM symbols s
                JOIN files f ON f.id = s.file_id
                WHERE s.name = ? AND f.path != ?
                LIMIT 1
                """,
                (to_name, from_file),
            ).fetchone()
            to_id = row["id"] if row else None
        if not to_id:
            continue

        from_id = None
        if from_file:
            row = conn.execute(
                """
                SELECT s.id FROM symbols s
                JOIN files f ON f.id = s.file_id
                WHERE f.path = ? AND s.start_line <= ? AND s.end_line >= ?
                LIMIT 1
                """,
                (from_file, from_line, from_line),
            ).fetchone()
            from_id = row["id"] if row else None

        conn.execute(
            """
            INSERT INTO symbol_refs (from_symbol_id, to_symbol_id, ref_kind, file_path, line)
            VALUES (?, ?, ?, ?, ?)
            """,
            (from_id, to_id, "roslyn", from_file, from_line),
        )
        refs_added += 1

    return {
        "success": True,
        "projects": len(data.get("projects", [])),
        "symbols_added": symbols_added,
        "routes_added": routes_added,
        "references_added": refs_added,
    }
