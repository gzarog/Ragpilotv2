"""Direct unit test of ``document_fts``: proves it is populated and
queryable independently of the CLI, mirroring ``test_code_fts.py``.
"""

from __future__ import annotations

from pathlib import Path

from ragpilot.core.models import (
    Document,
    DocumentFormat,
    FileKind,
    FileRecord,
    FileStatus,
    Paragraph,
    Section,
)
from ragpilot.storage.migrations import apply_migrations
from ragpilot.storage.repositories import documents_repo, files_repo
from ragpilot.storage.sqlite import connect, transaction


def _seed_file(conn) -> None:  # noqa: ANN001 - test helper
    files_repo.insert(
        conn,
        FileRecord(
            id="f1",
            source_id="s1",
            path="/tmp/docs/manual.md",
            kind=FileKind.DOCUMENT,
            size=10,
            mtime=0.0,
            status=FileStatus.QUEUED,
            created_at="now",
            updated_at="now",
        ),
    )


def _seed_document(conn) -> None:  # noqa: ANN001 - test helper
    documents_repo.insert_document(
        conn,
        Document(
            id="d1",
            source_id="s1",
            file_id="f1",
            format=DocumentFormat.MARKDOWN,
            title="Manual",
            section_count=1,
            paragraph_count=1,
            generation=1,
            created_at="now",
            updated_at="now",
        ),
    )


def test_fts_returns_matching_paragraph(tmp_path: Path) -> None:
    conn = connect(tmp_path / "knowledge.db")
    try:
        apply_migrations(conn, "knowledge")
        _seed_file(conn)
        with transaction(conn):
            _seed_document(conn)
            documents_repo.insert_section(
                conn,
                Section(
                    id="sec1",
                    document_id="d1",
                    file_id="f1",
                    heading_level=1,
                    text="Installation",
                    order_index=0,
                    generation=1,
                    created_at="now",
                ),
                doc_title="Manual",
            )
            documents_repo.insert_paragraph(
                conn,
                Paragraph(
                    id="p1",
                    document_id="d1",
                    file_id="f1",
                    text="Run the bootstrap script to configure everything.",
                    heading_path=["Installation"],
                    parent_id="sec1",
                    order_index=1,
                    generation=1,
                    created_at="now",
                ),
                doc_title="Manual",
            )

        results = documents_repo.search_fts(conn, "bootstrap")
        assert [r["section_id"] for r in results] == ["p1"]
        assert results[0]["document_id"] == "d1"
        assert results[0]["heading_text"] == "Installation"
        assert results[0]["doc_title"] == "Manual"

        heading_hits = documents_repo.search_fts(conn, "Installation")
        assert {r["section_id"] for r in heading_hits} == {"sec1", "p1"}
    finally:
        conn.close()


def test_fts_rows_removed_when_file_regenerated(tmp_path: Path) -> None:
    conn = connect(tmp_path / "knowledge.db")
    try:
        apply_migrations(conn, "knowledge")
        _seed_file(conn)
        with transaction(conn):
            _seed_document(conn)
            documents_repo.insert_paragraph(
                conn,
                Paragraph(
                    id="p1",
                    document_id="d1",
                    file_id="f1",
                    text="bootstrap the environment",
                    order_index=0,
                    generation=1,
                    created_at="now",
                ),
                doc_title="Manual",
            )

        assert documents_repo.search_fts(conn, "bootstrap") != []

        with transaction(conn):
            documents_repo.delete_by_file(conn, "f1")

        assert documents_repo.search_fts(conn, "bootstrap") == []
        assert documents_repo.get_document_by_file(conn, "f1") is None
    finally:
        conn.close()
