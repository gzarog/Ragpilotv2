"""CRUD for ``document_conversion_cache`` in a project's ``knowledge.db``.

Caches Docling's PDF -> Markdown export (see ``documents/docling_adapter
.py``'s module docstring) so re-indexing an unchanged PDF never re-runs
Docling's real, expensive layout/table-structure ML pipeline. Keyed by
content hash rather than file id/path, and never actively pruned --
purely derived, disposable state, mirroring ``embeddings_repo``'s own
"never actively GC'd" precedent.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class CachedConversion:
    content_hash: str
    markdown: str
    page_count: int | None


def get(
    conn: sqlite3.Connection, content_hash: str, *, cache_version: int
) -> CachedConversion | None:
    """Returns the cached Markdown for ``content_hash``, or ``None`` on a
    miss. A row whose ``cache_version`` no longer matches the caller's
    (the marker string or ``export_to_markdown`` options changed since it
    was written) is treated as a miss too, not returned as if still
    valid -- the caller would otherwise reparse Markdown that no longer
    matches how it interprets the result.
    """
    row = conn.execute(
        "SELECT content_hash, markdown, page_count FROM document_conversion_cache "
        "WHERE content_hash = ? AND cache_version = ?",
        (content_hash, cache_version),
    ).fetchone()
    if row is None:
        return None
    return CachedConversion(
        content_hash=row["content_hash"], markdown=row["markdown"], page_count=row["page_count"]
    )


def put(
    conn: sqlite3.Connection,
    cached: CachedConversion,
    *,
    cache_version: int,
    created_at: str,
) -> None:
    """Upserts the cache row for ``cached.content_hash``. A conflicting
    existing row (a stale ``cache_version``, or any other inconsistency)
    is simply overwritten -- always run inside the caller's own
    ``with transaction(conn):`` block, mirroring every other repo write
    in this project; this function never commits itself.
    """
    conn.execute(
        """
        INSERT INTO document_conversion_cache (
            content_hash, markdown, page_count, cache_version, created_at
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(content_hash) DO UPDATE SET
            markdown = excluded.markdown,
            page_count = excluded.page_count,
            cache_version = excluded.cache_version,
            created_at = excluded.created_at
        """,
        (cached.content_hash, cached.markdown, cached.page_count, cache_version, created_at),
    )
