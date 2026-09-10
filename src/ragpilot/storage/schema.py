"""DDL for the two SQLite databases RAGpilot maintains.

``sources.db`` is the single global registry of sources. Each registered
source gets its own ``knowledge.db`` ("project") holding the files it has
discovered plus that project's job queue and error log.
"""

from __future__ import annotations

CURRENT_SCHEMA_VERSION = 1

_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""

_METADATA_TABLE = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

SOURCES_DB_V1: tuple[str, ...] = (
    _MIGRATIONS_TABLE,
    _METADATA_TABLE,
    """
    CREATE TABLE IF NOT EXISTS sources (
        id TEXT PRIMARY KEY,
        path TEXT NOT NULL UNIQUE,
        source_type TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        indexing_mode TEXT NOT NULL DEFAULT 'full',
        include_patterns TEXT NOT NULL DEFAULT '[]',
        exclude_patterns TEXT NOT NULL DEFAULT '[]',
        last_scan_at TEXT,
        last_error TEXT,
        fingerprint TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
)

KNOWLEDGE_DB_V1: tuple[str, ...] = (
    _MIGRATIONS_TABLE,
    _METADATA_TABLE,
    """
    CREATE TABLE IF NOT EXISTS files (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        path TEXT NOT NULL,
        kind TEXT NOT NULL,
        size INTEGER NOT NULL,
        mtime REAL NOT NULL,
        content_hash TEXT,
        status TEXT NOT NULL,
        generation INTEGER NOT NULL DEFAULT 0,
        parser_version TEXT NOT NULL DEFAULT '1',
        last_indexed_at TEXT,
        last_error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(source_id, path)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS index_jobs (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        file_id TEXT NOT NULL REFERENCES files(id),
        job_type TEXT NOT NULL,
        status TEXT NOT NULL,
        priority INTEGER NOT NULL DEFAULT 0,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        next_attempt_at TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        error_code TEXT,
        error_message TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_index_jobs_status ON index_jobs(status)",
    """
    CREATE TABLE IF NOT EXISTS index_errors (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        file_id TEXT,
        path TEXT,
        error_code TEXT NOT NULL,
        error_message TEXT NOT NULL,
        occurred_at TEXT NOT NULL
    )
    """,
)
