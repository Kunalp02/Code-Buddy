"""Cross-language semantic analysis: references, callers, and call hints."""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from pathlib import Path

# Language-specific call patterns: identifier before ( or .identifier(
CALL_PATTERNS = {
    "python": re.compile(r"\b([A-Za-z_][\w]*)\s*\("),
    "javascript": re.compile(r"\b([A-Za-z_$][\w$]*)\s*\("),
    "typescript": re.compile(r"\b([A-Za-z_$][\w$]*)\s*\("),
    "go": re.compile(r"\b([A-Za-z_][\w]*)\s*\("),
    "java": re.compile(r"\b([A-Za-z_][\w]*)\s*\("),
    "rust": re.compile(r"\b([A-Za-z_][\w]*)\s*\("),
    "csharp": re.compile(r"\b([A-Za-z_][\w]*)\s*\("),
    "dart": re.compile(r"\b([A-Za-z_][\w]*)\s*\("),
}

# Words that look like calls but aren't
STOP_NAMES = frozenset(
    {
        "if", "for", "while", "switch", "catch", "return", "new", "typeof", "sizeof",
        "await", "async", "def", "class", "import", "from", "print", "len", "str",
        "int", "float", "bool", "list", "dict", "set", "tuple", "range", "super",
        "self", "this", "base", "using", "namespace", "public", "private", "static",
        "void", "var", "let", "const", "function", "export", "default", "case",
        "try", "except", "finally", "with", "pass", "raise", "yield", "lambda",
        "true", "false", "null", "none", "not", "and", "or", "in", "is", "as",
    }
)


def _ensure_semantic_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(symbols)").fetchall()}
    if "qualified_name" not in cols:
        conn.execute("ALTER TABLE symbols ADD COLUMN qualified_name TEXT")
    if "container" not in cols:
        conn.execute("ALTER TABLE symbols ADD COLUMN container TEXT")


def build_semantic_graph(conn: sqlite3.Connection, root_path: Path) -> dict[str, int]:
    """Build symbol_refs from syntactic cross-file usage. Returns stats."""
    _ensure_semantic_columns(conn)
    conn.execute("DELETE FROM symbol_refs")

    rows = conn.execute(
        """
        SELECT s.id, s.name, s.kind, s.start_line, s.end_line, s.qualified_name,
               f.path AS file_path, f.language
        FROM symbols s
        JOIN files f ON f.id = s.file_id
        """
    ).fetchall()

    if not rows:
        return {"symbols": 0, "references": 0}

    by_name: dict[str, list[dict]] = defaultdict(list)
    by_file: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        item = dict(row)
        by_name[item["name"]].append(item)
        by_file[item["file_path"]].append(item)

    ref_count = 0
    seen: set[tuple[int, int, int]] = set()

    for file_path, file_symbols in by_file.items():
        abs_path = root_path / file_path
        if not abs_path.exists():
            continue
        try:
            lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        lang = _guess_lang(file_path)
        pattern = CALL_PATTERNS.get(lang, CALL_PATTERNS["python"])

        for line_no, line in enumerate(lines, start=1):
            # Skip lines inside string-only contexts (rough heuristic)
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("#"):
                continue

            for match in pattern.finditer(line):
                name = match.group(1)
                if name in STOP_NAMES or len(name) < 2:
                    continue

                candidates = by_name.get(name, [])
                if not candidates:
                    continue

                # Prefer symbols defined in other files (cross-file refs)
                targets = [c for c in candidates if c["file_path"] != file_path] or candidates

                for target in targets[:3]:
                    from_sym = _nearest_symbol(file_symbols, line_no)
                    from_id = from_sym["id"] if from_sym else None
                    to_id = target["id"]
                    key = (from_id or 0, to_id, line_no)
                    if key in seen:
                        continue
                    seen.add(key)
                    conn.execute(
                        """
                        INSERT INTO symbol_refs
                        (from_symbol_id, to_symbol_id, ref_kind, file_path, line)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (from_id, to_id, "call", file_path, line_no),
                    )
                    ref_count += 1

    return {"symbols": len(rows), "references": ref_count}


def _nearest_symbol(symbols: list[dict], line: int) -> dict | None:
    best = None
    for sym in symbols:
        if sym["start_line"] <= line <= sym["end_line"]:
            return sym
        if sym["start_line"] <= line and (best is None or sym["start_line"] > best["start_line"]):
            best = sym
    return best


def _guess_lang(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".java": "java",
        ".rs": "rust",
        ".cs": "csharp",
        ".dart": "dart",
    }
    return mapping.get(ext, "python")
