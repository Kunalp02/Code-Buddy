import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from server.config import settings


def project_db_path(project_id: str) -> Path:
    return settings.data_dir / project_id / "graph.db"


def project_meta_path(project_id: str) -> Path:
    return settings.data_dir / project_id / "meta.json"


@contextmanager
def get_db(project_id: str) -> Iterator[sqlite3.Connection]:
    db_path = project_db_path(project_id)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            language TEXT,
            line_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            signature TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
        CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);

        CREATE TABLE IF NOT EXISTS imports (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            imported_name TEXT,
            line INTEGER,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY,
            file_id INTEGER,
            method TEXT,
            path TEXT NOT NULL,
            handler TEXT,
            line INTEGER,
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS modules (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            file_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS module_deps (
            id INTEGER PRIMARY KEY,
            from_module_id INTEGER NOT NULL,
            to_module_id INTEGER NOT NULL,
            weight INTEGER DEFAULT 1,
            FOREIGN KEY (from_module_id) REFERENCES modules(id) ON DELETE CASCADE,
            FOREIGN KEY (to_module_id) REFERENCES modules(id) ON DELETE CASCADE,
            UNIQUE(from_module_id, to_module_id)
        );

        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            title TEXT
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS components (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            component_type TEXT NOT NULL,
            technology TEXT,
            evidence_file TEXT,
            evidence_line INTEGER,
            detail TEXT
        );

        CREATE TABLE IF NOT EXISTS component_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            connection_type TEXT,
            label TEXT,
            evidence_file TEXT,
            evidence_line INTEGER
        );
        """
    )


def save_meta(project_id: str, meta: dict[str, Any]) -> None:
    path = project_meta_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2))


def load_meta(project_id: str) -> dict[str, Any] | None:
    path = project_meta_path(project_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())
