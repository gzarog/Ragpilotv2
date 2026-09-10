"""CRUD for the ``files`` table in a project's ``knowledge.db``."""

from __future__ import annotations

import sqlite3

from ragpilot.core.models import FileKind, FileRecord, FileStatus
from ragpilot.storage.repositories import links_repo
from ragpilot.storage.sqlite import transaction


def _row_to_file(row: sqlite3.Row) -> FileRecord:
    return FileRecord(
        id=row["id"],
        source_id=row["source_id"],
        path=row["path"],
        kind=FileKind(row["kind"]),
        size=row["size"],
        mtime=row["mtime"],
        content_hash=row["content_hash"],
        status=FileStatus(row["status"]),
        generation=row["generation"],
        parser_version=row["parser_version"],
        last_indexed_at=row["last_indexed_at"],
        last_error=row["last_error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_by_path(conn: sqlite3.Connection, source_id: str, path: str) -> FileRecord | None:
    row = conn.execute(
        "SELECT * FROM files WHERE source_id = ? AND path = ?", (source_id, path)
    ).fetchone()
    return _row_to_file(row) if row is not None else None


def get(conn: sqlite3.Connection, file_id: str) -> FileRecord | None:
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    return _row_to_file(row) if row is not None else None


def list_by_source(conn: sqlite3.Connection, source_id: str) -> list[FileRecord]:
    rows = conn.execute(
        "SELECT * FROM files WHERE source_id = ? ORDER BY path", (source_id,)
    ).fetchall()
    return [_row_to_file(row) for row in rows]


def search_by_substring(
    conn: sqlite3.Connection, query: str, *, limit: int = 25
) -> list[FileRecord]:
    """Files whose path contains ``query``, path-ordered.

    A plain ``LIKE`` scan, not a new index: Phase 5's ``ragpilot search``
    is the only caller of this "match by path fragment" lookup, and at
    the scale one local ``knowledge.db`` holds, a sequential scan is fast
    enough without paying index-maintenance cost on every file write for
    a read path this narrow.
    """
    rows = conn.execute(
        "SELECT * FROM files WHERE path LIKE ? ORDER BY path LIMIT ?",
        (f"%{query}%", limit),
    ).fetchall()
    return [_row_to_file(row) for row in rows]


def insert(conn: sqlite3.Connection, file: FileRecord) -> None:
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO files (
                id, source_id, path, kind, size, mtime, content_hash, status,
                generation, parser_version, last_indexed_at, last_error,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file.id,
                file.source_id,
                file.path,
                file.kind.value,
                file.size,
                file.mtime,
                file.content_hash,
                file.status.value,
                file.generation,
                file.parser_version,
                file.last_indexed_at,
                file.last_error,
                file.created_at,
                file.updated_at,
            ),
        )


def update_status(
    conn: sqlite3.Connection, file_id: str, status: FileStatus, *, updated_at: str
) -> None:
    with transaction(conn):
        conn.execute(
            "UPDATE files SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, updated_at, file_id),
        )


def mark_indexed(
    conn: sqlite3.Connection,
    file_id: str,
    *,
    size: int,
    mtime: float,
    content_hash: str | None,
    status: FileStatus,
    indexed_at: str,
) -> None:
    """Atomically advances a file to its next generation.

    Phase 1 has no derived-entity tables yet, so "delete old generation,
    insert new" collapses to a single row update -- but it still runs
    inside one transaction so readers never observe a half-updated file.
    """
    with transaction(conn):
        conn.execute(
            """
            UPDATE files
            SET size = ?, mtime = ?, content_hash = ?, status = ?,
                generation = generation + 1, last_indexed_at = ?,
                last_error = NULL, updated_at = ?
            WHERE id = ?
            """,
            (size, mtime, content_hash, status.value, indexed_at, indexed_at, file_id),
        )


def mark_failed(conn: sqlite3.Connection, file_id: str, *, error: str, updated_at: str) -> None:
    with transaction(conn):
        conn.execute(
            "UPDATE files SET status = ?, last_error = ?, updated_at = ? WHERE id = ?",
            (FileStatus.FAILED.value, error, updated_at, file_id),
        )


def delete(conn: sqlite3.Connection, file_id: str) -> None:
    """Deletes a file and cascades its derived-content rows.

    ``entities``/``relationships`` (Phase 2), ``documents``/
    ``document_sections`` (Phase 3) and ``cross_links`` (Phase 4) all
    carry a ``file_id`` foreign key into ``files`` (``cross_links``
    indirectly, via ``entities``/``documents``), but were added by later,
    already-applied migrations without an ``ON DELETE CASCADE`` clause --
    so with ``PRAGMA foreign_keys = ON`` (storage/sqlite.py), deleting a
    ``files`` row with surviving derived rows would raise
    ``IntegrityError`` instead of reconciling a source's deleted file
    away. Clearing them here, in the same transaction (``cross_links``
    first, since it references ``entities``/``documents``), keeps that
    reconciliation crash-free without touching those migrations.
    """
    with transaction(conn):
        conn.execute("DELETE FROM index_jobs WHERE file_id = ?", (file_id,))
        links_repo.delete_by_entity_file(conn, file_id)
        links_repo.delete_by_document_file(conn, file_id)
        conn.execute(
            "DELETE FROM code_fts WHERE entity_id IN "
            "(SELECT id FROM entities WHERE file_id = ?)",
            (file_id,),
        )
        conn.execute("DELETE FROM relationships WHERE file_id = ?", (file_id,))
        conn.execute("DELETE FROM entities WHERE file_id = ?", (file_id,))
        conn.execute(
            "DELETE FROM document_fts WHERE section_id IN "
            "(SELECT id FROM document_sections WHERE file_id = ?)",
            (file_id,),
        )
        conn.execute("DELETE FROM document_sections WHERE file_id = ?", (file_id,))
        conn.execute("DELETE FROM documents WHERE file_id = ?", (file_id,))
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))


def count_by_status(conn: sqlite3.Connection, source_id: str) -> dict[str, int]:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM files WHERE source_id = ? GROUP BY status",
        (source_id,),
    ).fetchall()
    return {row["status"]: row["n"] for row in rows}
