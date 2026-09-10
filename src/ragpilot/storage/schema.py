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

# Phase 2: code entities/relationships extracted by Tree-sitter, plus an
# FTS5 index over their names for lexical lookup. Additive-only migration
# layered on top of KNOWLEDGE_DB_V1 -- see storage/migrations.
KNOWLEDGE_DB_V2: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS entities (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        file_id TEXT NOT NULL REFERENCES files(id),
        kind TEXT NOT NULL,
        name TEXT NOT NULL,
        qualified_name TEXT NOT NULL,
        language TEXT NOT NULL,
        parent_id TEXT REFERENCES entities(id),
        signature TEXT,
        start_line INTEGER NOT NULL,
        end_line INTEGER NOT NULL,
        start_col INTEGER NOT NULL DEFAULT 0,
        end_col INTEGER NOT NULL DEFAULT 0,
        generation INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(file_id, qualified_name, start_line)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_entities_file ON entities(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)",
    "CREATE INDEX IF NOT EXISTS idx_entities_qualified_name ON entities(qualified_name)",
    "CREATE INDEX IF NOT EXISTS idx_entities_parent ON entities(parent_id)",
    """
    CREATE TABLE IF NOT EXISTS relationships (
        id TEXT PRIMARY KEY,
        relationship_type TEXT NOT NULL,
        source_entity_id TEXT NOT NULL REFERENCES entities(id),
        target_entity_id TEXT REFERENCES entities(id),
        target_symbol TEXT,
        resolver TEXT NOT NULL,
        confidence TEXT NOT NULL,
        file_id TEXT NOT NULL REFERENCES files(id),
        source_location TEXT,
        evidence TEXT,
        generation INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_relationships_file ON relationships(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_relationships_target_symbol ON relationships(target_symbol)",
    "CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(relationship_type)",
    # Not an external-content FTS table: rows are written explicitly by the
    # code processor alongside entities (not via SQL triggers) so the
    # "delete old generation, insert new, all in one transaction" atomicity
    # rule in coordinator.py stays a single, auditable code path.
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS code_fts USING fts5(
        entity_id UNINDEXED,
        name,
        qualified_name,
        snippet
    )
    """,
)
