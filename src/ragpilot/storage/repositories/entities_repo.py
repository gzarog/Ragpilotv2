"""CRUD for ``entities`` and its ``code_fts`` shadow index in a project's
``knowledge.db``.

Regenerating a file's entities is delete-then-insert under one caller-held
transaction (see ``code/processor.py``), mirroring the generational pattern
``files_repo.mark_indexed`` established in Phase 1.
"""

from __future__ import annotations

import sqlite3

from ragpilot.core.models import Entity, EntityType
from ragpilot.storage.repositories import links_repo


def _row_to_entity(row: sqlite3.Row) -> Entity:
    return Entity(
        id=row["id"],
        source_id=row["source_id"],
        file_id=row["file_id"],
        kind=EntityType(row["kind"]),
        name=row["name"],
        qualified_name=row["qualified_name"],
        language=row["language"],
        parent_id=row["parent_id"],
        signature=row["signature"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        start_col=row["start_col"],
        end_col=row["end_col"],
        generation=row["generation"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def delete_by_file(conn: sqlite3.Connection, file_id: str) -> None:
    """Removes a file's previous generation of entities and their FTS rows.

    Caller-managed transaction: this is always run inside the same
    ``with transaction(conn):`` block as the subsequent inserts so a reader
    never observes a file with zero or partial entities mid-reindex.
    """
    links_repo.delete_by_entity_file(conn, file_id)
    conn.execute(
        "DELETE FROM code_fts WHERE entity_id IN (SELECT id FROM entities WHERE file_id = ?)",
        (file_id,),
    )
    conn.execute("DELETE FROM relationships WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM entities WHERE file_id = ?", (file_id,))


def insert(conn: sqlite3.Connection, entity: Entity, *, snippet: str) -> None:
    conn.execute(
        """
        INSERT INTO entities (
            id, source_id, file_id, kind, name, qualified_name, language,
            parent_id, signature, start_line, end_line, start_col, end_col,
            generation, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entity.id,
            entity.source_id,
            entity.file_id,
            entity.kind.value,
            entity.name,
            entity.qualified_name,
            entity.language,
            entity.parent_id,
            entity.signature,
            entity.start_line,
            entity.end_line,
            entity.start_col,
            entity.end_col,
            entity.generation,
            entity.created_at,
            entity.updated_at,
        ),
    )
    conn.execute(
        "INSERT INTO code_fts (entity_id, name, qualified_name, snippet) VALUES (?, ?, ?, ?)",
        (entity.id, entity.name, entity.qualified_name, snippet),
    )


def get(conn: sqlite3.Connection, entity_id: str) -> Entity | None:
    row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    return _row_to_entity(row) if row is not None else None


def list_all(conn: sqlite3.Connection) -> list[Entity]:
    """Every entity in this project's ``knowledge.db`` -- the "full
    existing corpus" side of ``knowledge/linker.py``'s cross-domain match
    (one knowledge.db always holds exactly one source's data, see
    ``core/paths.py``'s one-project-per-source layout, so no further
    scoping is needed here).
    """
    rows = conn.execute("SELECT * FROM entities ORDER BY file_id, start_line").fetchall()
    return [_row_to_entity(row) for row in rows]


def list_by_file(conn: sqlite3.Connection, file_id: str) -> list[Entity]:
    rows = conn.execute(
        "SELECT * FROM entities WHERE file_id = ? ORDER BY start_line", (file_id,)
    ).fetchall()
    return [_row_to_entity(row) for row in rows]


def find_by_qualified_name(conn: sqlite3.Connection, qualified_name: str) -> list[Entity]:
    rows = conn.execute(
        "SELECT * FROM entities WHERE qualified_name = ? ORDER BY qualified_name, file_id, "
        "start_line",
        (qualified_name,),
    ).fetchall()
    return [_row_to_entity(row) for row in rows]


def find_by_name(conn: sqlite3.Connection, name: str) -> list[Entity]:
    """Bare-name lookup, e.g. the last dotted segment of a call target.

    Used both by the resolver (cross-file, name-only fallback) and by the
    ``ragpilot symbol`` CLI command (a user rarely types a fully qualified
    name). Ordered deterministically by qualified name so repeated runs and
    ``--json`` output are stable.
    """
    rows = conn.execute(
        "SELECT * FROM entities WHERE name = ? ORDER BY qualified_name, file_id, start_line",
        (name,),
    ).fetchall()
    return [_row_to_entity(row) for row in rows]


def search(conn: sqlite3.Connection, name_or_qualified_name: str) -> list[Entity]:
    """Symbol lookup by exact name OR exact qualified name, deduplicated."""
    rows = conn.execute(
        "SELECT * FROM entities WHERE name = ? OR qualified_name = ? "
        "ORDER BY qualified_name, file_id, start_line",
        (name_or_qualified_name, name_or_qualified_name),
    ).fetchall()
    return [_row_to_entity(row) for row in rows]


def search_fts(conn: sqlite3.Connection, query: str, *, limit: int = 25) -> list[Entity]:
    rows = conn.execute(
        """
        SELECT e.* FROM code_fts
        JOIN entities e ON e.id = code_fts.entity_id
        WHERE code_fts MATCH ?
        ORDER BY bm25(code_fts)
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()
    return [_row_to_entity(row) for row in rows]
