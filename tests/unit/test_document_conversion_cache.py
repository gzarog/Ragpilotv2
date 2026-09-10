"""Storage-level tests for ``document_conversion_cache``: get/put
round-trip, cache_version mismatch treated as a miss, and upsert
overwrite -- pure SQLite, no Docling/PDF/ML model involved (see
``test_docling_pdf.py`` for the real end-to-end cache proof).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ragpilot.storage.migrations import apply_migrations
from ragpilot.storage.repositories import document_conversion_cache_repo
from ragpilot.storage.repositories.document_conversion_cache_repo import CachedConversion
from ragpilot.storage.sqlite import connect, transaction


@pytest.fixture
def conn(tmp_path: Path):  # noqa: ANN201
    connection = connect(tmp_path / "knowledge.db")
    apply_migrations(connection, "knowledge")
    yield connection
    connection.close()


def test_get_on_empty_cache_is_a_miss(conn) -> None:  # noqa: ANN001
    assert document_conversion_cache_repo.get(conn, "deadbeef", cache_version=1) is None


def test_put_then_get_round_trips(conn) -> None:  # noqa: ANN001
    with transaction(conn):
        document_conversion_cache_repo.put(
            conn,
            CachedConversion(content_hash="hash-a", markdown="# Title\n\nBody.", page_count=3),
            cache_version=1,
            created_at="2026-01-01T00:00:00+00:00",
        )

    cached = document_conversion_cache_repo.get(conn, "hash-a", cache_version=1)
    assert cached is not None
    assert cached.content_hash == "hash-a"
    assert cached.markdown == "# Title\n\nBody."
    assert cached.page_count == 3


def test_get_with_mismatched_cache_version_is_a_miss(conn) -> None:  # noqa: ANN001
    with transaction(conn):
        document_conversion_cache_repo.put(
            conn,
            CachedConversion(content_hash="hash-a", markdown="# Title", page_count=1),
            cache_version=1,
            created_at="2026-01-01T00:00:00+00:00",
        )

    # A row written under an older cache_version must never be handed back
    # as if it matched the caller's current marker/export options.
    assert document_conversion_cache_repo.get(conn, "hash-a", cache_version=2) is None


def test_put_upserts_overwriting_the_existing_row(conn) -> None:  # noqa: ANN001
    with transaction(conn):
        document_conversion_cache_repo.put(
            conn,
            CachedConversion(content_hash="hash-a", markdown="old markdown", page_count=1),
            cache_version=1,
            created_at="2026-01-01T00:00:00+00:00",
        )
    with transaction(conn):
        document_conversion_cache_repo.put(
            conn,
            CachedConversion(content_hash="hash-a", markdown="new markdown", page_count=2),
            cache_version=1,
            created_at="2026-01-02T00:00:00+00:00",
        )

    cached = document_conversion_cache_repo.get(conn, "hash-a", cache_version=1)
    assert cached is not None
    assert cached.markdown == "new markdown"
    assert cached.page_count == 2

    row_count = conn.execute("SELECT COUNT(*) AS n FROM document_conversion_cache").fetchone()["n"]
    assert row_count == 1
