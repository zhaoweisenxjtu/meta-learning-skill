"""Database connection and initialization."""

import sqlite3
import os
import json
from pathlib import Path

DB_DIR = Path.home() / ".meta-learning"
DB_PATH = DB_DIR / "meta_learning.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Columns to add to knowledge_nodes if missing (v1 → v2 migration)
_CONTENT_COLUMNS = [
    ("content", "TEXT NOT NULL DEFAULT ''"),
    ("content_format", "TEXT NOT NULL DEFAULT 'markdown'"),
    ("source_url", "TEXT NOT NULL DEFAULT ''"),
    ("source_title", "TEXT NOT NULL DEFAULT ''"),
    ("quality_score", "INTEGER DEFAULT 0"),
    ("cached_at", "TEXT"),
    ("tags", "TEXT NOT NULL DEFAULT '[]'"),
]


def get_db_path() -> str:
    """Return the database file path."""
    return str(DB_PATH)


def ensure_db_dir():
    """Create the database directory if it doesn't exist."""
    DB_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Get a new SQLite connection with WAL mode and foreign keys."""
    ensure_db_dir()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(c["name"] == column for c in cols)


def _migrate_knowledge_nodes(conn: sqlite3.Connection):
    """Add content-related columns to knowledge_nodes if missing."""
    existing = {c["name"] for c in conn.execute("PRAGMA table_info(knowledge_nodes)").fetchall()}
    for col_name, col_def in _CONTENT_COLUMNS:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE knowledge_nodes ADD COLUMN {col_name} {col_def}")


def _init_fts(conn: sqlite3.Connection):
    """Create FTS5 virtual table and triggers if they don't exist."""
    # Check if FTS table already exists
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_fts'"
    ).fetchone()
    if exists:
        return

    # Verify content column exists before creating FTS
    if not _column_exists(conn, "knowledge_nodes", "content"):
        return  # migration hasn't run yet

    # Only create FTS if content column exists
    conn.executescript("""
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
            name, content, tags, source_title,
            content='knowledge_nodes',
            content_rowid='id',
            tokenize='unicode61'
        );

        CREATE TRIGGER IF NOT EXISTS knowledge_fts_insert AFTER INSERT ON knowledge_nodes BEGIN
            INSERT INTO knowledge_fts(rowid, name, content, tags, source_title)
            VALUES (new.id, new.name, new.content, new.tags, new.source_title);
        END;

        CREATE TRIGGER IF NOT EXISTS knowledge_fts_delete AFTER DELETE ON knowledge_nodes BEGIN
            INSERT INTO knowledge_fts(knowledge_fts, rowid, name, content, tags, source_title)
            VALUES ('delete', old.id, old.name, old.content, old.tags, old.source_title);
        END;

        CREATE TRIGGER IF NOT EXISTS knowledge_fts_update AFTER UPDATE ON knowledge_nodes BEGIN
            INSERT INTO knowledge_fts(knowledge_fts, rowid, name, content, tags, source_title)
            VALUES ('delete', old.id, old.name, old.content, old.tags, old.source_title);
            INSERT INTO knowledge_fts(rowid, name, content, tags, source_title)
            VALUES (new.id, new.name, new.content, new.tags, new.source_title);
        END;
    """)


def init_db(force: bool = False):
    """Initialize the database schema and run migrations."""
    ensure_db_dir()
    exists = DB_PATH.exists()
    if exists and not force:
        # Run migrations on existing DB
        conn = get_connection()
        try:
            _migrate_knowledge_nodes(conn)
            _init_fts(conn)
            conn.commit()
        finally:
            conn.close()
        return

    # Fresh initialization
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        conn.executescript(schema)
        conn.commit()
        # Now add content columns + FTS (fresh DB still needs migration for columns)
        _migrate_knowledge_nodes(conn)
        _init_fts(conn)
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return None
    return dict(row)


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    """Convert a list of sqlite3.Row to a list of dicts."""
    return [dict(r) for r in rows]
