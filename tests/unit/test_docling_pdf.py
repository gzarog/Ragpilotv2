"""PDF golden test -- gated behind the ``docling_pdf`` marker because it
exercises Docling's real PDF pipeline, which downloads layout/table-
structure model weights from Hugging Face on first use. Run explicitly
with ``pytest -m docling_pdf``; excluded from the default ``pytest -q``
run (see ``pyproject.toml``'s ``addopts`` and CONTRIBUTING.md).

Also proves the PDF-to-Markdown conversion cache (``document_conversion_
cache``, see ``docling_adapter``'s module docstring): that a first
``convert()`` populates it, and that a second ``convert()`` against the
same connection reuses it rather than re-running the real PDF pipeline.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ragpilot.documents import chunker, docling_adapter, normalizer
from ragpilot.documents.metadata import extract_metadata
from ragpilot.sources.fingerprint import hash_file
from ragpilot.storage.migrations import apply_migrations
from ragpilot.storage.repositories import document_conversion_cache_repo
from ragpilot.storage.sqlite import connect

FIXTURES = Path(__file__).parent.parent / "fixtures" / "documents"

pytestmark = pytest.mark.docling_pdf


def test_pdf_page_count_without_conversion() -> None:
    # No ML model weights are loaded for this -- see docling_adapter
    # .pdf_page_count -- but it is still exercised only under this marker
    # to keep the default suite's document tests entirely self-contained.
    assert docling_adapter.pdf_page_count(FIXTURES / "sample.pdf") == 1


def test_pdf_converts_to_a_paragraph_with_page_provenance() -> None:
    path = FIXTURES / "sample.pdf"
    doc_format = docling_adapter.detect_format(path)
    assert doc_format.value == "pdf"

    conversion = docling_adapter.convert(path)
    normalized = normalizer.normalize(
        conversion.document,
        doc_format,
        page_count_override=conversion.page_count,
        page_break_marker=conversion.page_break_marker,
    )
    chunks = chunker.chunk_document(normalized)
    meta = extract_metadata(conversion.document, normalized, doc_format, path)

    assert meta.page_count == 1
    assert meta.is_scanned is False
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.kind == "paragraph"
    assert "Sample PDF Title" in chunk.text
    assert "This is a line of body text in the sample PDF." in chunk.text
    assert chunk.page_start == 1
    assert chunk.page_end == 1


def test_convert_caches_markdown_by_content_hash(tmp_path: Path) -> None:
    path = FIXTURES / "sample.pdf"
    conn = connect(tmp_path / "knowledge.db")
    try:
        apply_migrations(conn, "knowledge")
        assert (
            document_conversion_cache_repo.get(
                conn, hash_file(path), cache_version=docling_adapter._CACHE_VERSION
            )
            is None
        )

        docling_adapter.convert(path, conn=conn)

        cached = document_conversion_cache_repo.get(
            conn, hash_file(path), cache_version=docling_adapter._CACHE_VERSION
        )
        assert cached is not None
        assert cached.page_count == 1
        assert "Sample PDF Title" in cached.markdown
    finally:
        conn.close()


def test_convert_reuses_cached_markdown_without_reconverting(tmp_path: Path) -> None:
    path = FIXTURES / "sample.pdf"
    conn = connect(tmp_path / "knowledge.db")
    try:
        apply_migrations(conn, "knowledge")

        # First call: real, unpatched conversion -- populates the cache.
        first = docling_adapter.convert(path, conn=conn)

        # Second call: the PDF-pipeline singleton must never be touched --
        # a real reconversion would raise here instead of being reused.
        with patch.object(docling_adapter, "_get_converter") as get_converter:
            get_converter.return_value.convert.side_effect = AssertionError(
                "should not reconvert"
            )
            second = docling_adapter.convert(path, conn=conn)

        get_converter.assert_not_called()
        assert second.page_count == first.page_count == 1
        assert second.page_break_marker == docling_adapter.PAGE_BREAK_MARKER
        assert first.page_break_marker == docling_adapter.PAGE_BREAK_MARKER
        assert second.document.export_to_markdown() == first.document.export_to_markdown()
    finally:
        conn.close()
