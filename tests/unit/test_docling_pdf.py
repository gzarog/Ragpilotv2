"""PDF golden test -- gated behind the ``docling_pdf`` marker because it
exercises Docling's real PDF pipeline, which downloads layout/table-
structure model weights from Hugging Face on first use. Run explicitly
with ``pytest -m docling_pdf``; excluded from the default ``pytest -q``
run (see ``pyproject.toml``'s ``addopts`` and CONTRIBUTING.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ragpilot.documents import chunker, docling_adapter, normalizer
from ragpilot.documents.metadata import extract_metadata

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

    doc = docling_adapter.convert(path)
    normalized = normalizer.normalize(doc, doc_format)
    chunks = chunker.chunk_document(normalized)
    meta = extract_metadata(doc, normalized, doc_format, path)

    assert meta.page_count == 1
    assert meta.is_scanned is False
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.kind == "paragraph"
    assert "Sample PDF Title" in chunk.text
    assert "This is a line of body text in the sample PDF." in chunk.text
    assert chunk.page_start == 1
    assert chunk.page_end == 1
