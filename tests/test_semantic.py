"""Tests for semantic indexing and parsers."""

import sqlite3
from pathlib import Path

from server.db import init_schema
from server.indexer.parser import parse_file, _extract_csharp_minimal_apis
from server.indexer.semantic import build_semantic_graph


def test_csharp_minimal_api_routes():
    text = 'app.MapGet("/health", () => Results.Ok());\napp.MapPost("/api/users", CreateUser);'
    routes = _extract_csharp_minimal_apis(text)
    paths = {r.path for r in routes}
    assert "/health" in paths
    assert "/api/users" in paths


def test_semantic_graph_builds_references(tmp_path: Path):
    root = tmp_path
    svc = root / "svc.py"
    main = root / "main.py"
    svc.write_text("def process():\n    return 1\n")
    main.write_text("from svc import process\n\ndef run():\n    process()\n")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)

    for rel, content in [("svc.py", svc.read_text()), ("main.py", main.read_text())]:
        cur = conn.execute("INSERT INTO files (path, language, line_count) VALUES (?, ?, ?)", (rel, "py", 10))
        file_id = cur.lastrowid
        if rel == "svc.py":
            conn.execute(
                "INSERT INTO symbols (file_id, name, kind, start_line, end_line) VALUES (?, ?, ?, ?, ?)",
                (file_id, "process", "function", 1, 2),
            )
        else:
            conn.execute(
                "INSERT INTO symbols (file_id, name, kind, start_line, end_line) VALUES (?, ?, ?, ?, ?)",
                (file_id, "run", "function", 3, 4),
            )

    stats = build_semantic_graph(conn, root)
    assert stats["symbols"] >= 2
    row = conn.execute("SELECT COUNT(*) AS c FROM symbol_refs").fetchone()
    assert row["c"] >= 1


def test_parse_python_symbols(tmp_path: Path):
    f = tmp_path / "app.py"
    f.write_text(
        '''
from fastapi import APIRouter
router = APIRouter()

@router.get("/items")
def list_items():
    return []
'''
    )
    result = parse_file(f)
    names = {s.name for s in result.symbols}
    assert "list_items" in names
    assert any(r.path == "/items" for r in result.routes)
