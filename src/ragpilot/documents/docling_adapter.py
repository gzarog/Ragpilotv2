"""Thin wrapper around Docling's Python API.

Docling's PDF pipeline downloads layout/table-structure model weights from
Hugging Face on first use -- real, but a CI/sandbox reliability risk (see
the ``docling_pdf`` pytest marker registered in ``pyproject.toml``). Every
other format handled here (DOCX, PPTX, XLSX, HTML, Markdown, TXT, EML) is
converted by Docling's rule-based backends and never touches that download
path, so only PDF conversion needs to be gated behind that marker in
tests.
"""

from __future__ import annotations

from pathlib import Path

from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.document import DoclingDocument

from ragpilot.core.errors import RagpilotError
from ragpilot.core.models import DocumentFormat

# Phase 3's supported extensions. Anything else that ``sources.detector``
# still classifies as ``FileKind.DOCUMENT`` (legacy .doc/.ppt/.xls,
# OpenDocument, .rtf, .csv, .rst) is deliberately out of scope -- see
# ``UnsupportedDocumentFormatError``.
EXTENSION_TO_FORMAT: dict[str, DocumentFormat] = {
    ".pdf": DocumentFormat.PDF,
    ".docx": DocumentFormat.DOCX,
    ".pptx": DocumentFormat.PPTX,
    ".xlsx": DocumentFormat.XLSX,
    ".html": DocumentFormat.HTML,
    ".htm": DocumentFormat.HTML,
    ".md": DocumentFormat.MARKDOWN,
    ".markdown": DocumentFormat.MARKDOWN,
    ".txt": DocumentFormat.TXT,
    ".eml": DocumentFormat.EML,
}

_FORMAT_TO_INPUT_FORMAT: dict[DocumentFormat, InputFormat] = {
    DocumentFormat.PDF: InputFormat.PDF,
    DocumentFormat.DOCX: InputFormat.DOCX,
    DocumentFormat.PPTX: InputFormat.PPTX,
    DocumentFormat.XLSX: InputFormat.XLSX,
    DocumentFormat.HTML: InputFormat.HTML,
    # Docling itself has no distinct "plain text" InputFormat -- .md and
    # .txt both route to InputFormat.MD (see docling.datamodel.base_models
    # .FormatToExtensions), and plain text is valid (trivial) Markdown.
    DocumentFormat.MARKDOWN: InputFormat.MD,
    DocumentFormat.TXT: InputFormat.MD,
    DocumentFormat.EML: InputFormat.EMAIL,
}

_SUCCESS_STATUSES = (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS)


class UnsupportedDocumentFormatError(RagpilotError):
    """A ``FileKind.DOCUMENT`` file whose extension is outside Phase 3's
    supported format list. The processor catches this specifically and
    indexes the file without derived document content instead of failing
    the run, mirroring ``code/processor.py``'s "recognized extension, no
    grammar wired up yet" fallback.
    """


class DocumentConversionError(RagpilotError):
    """Docling itself failed to convert an otherwise-supported file
    (corrupt, password-protected, malformed, ...). Left to propagate to
    the coordinator's existing per-file isolation/retry handling, exactly
    like ``code.processor.CodeParseError``.
    """


def detect_format(path: Path) -> DocumentFormat:
    fmt = EXTENSION_TO_FORMAT.get(path.suffix.lower())
    if fmt is None:
        raise UnsupportedDocumentFormatError(
            f"{path}: unsupported document extension "
            f"'{path.suffix or '<none>'}' (Phase 3 supports PDF, DOCX, "
            "PPTX, XLSX, HTML, Markdown, TXT, EML)"
        )
    return fmt


_converter: DocumentConverter | None = None


def _get_converter() -> DocumentConverter:
    """Module-level singleton: constructing a ``DocumentConverter`` is what
    loads the (lazy) layout/table-structure model handles, so building one
    per file would repeat that cost for every PDF in a run.
    """
    global _converter
    if _converter is None:
        pdf_options = PdfPipelineOptions()
        # OCR is explicitly out of scope for Phase 3 (config.documents.ocr
        # is read only for the future -- see docs/CHANGELOG). Turning it
        # off also means PDF conversion never needs an OCR engine's own
        # model weights on top of the layout/table-structure ones.
        pdf_options.do_ocr = False
        pdf_options.do_table_structure = True
        _converter = DocumentConverter(
            allowed_formats=list(_FORMAT_TO_INPUT_FORMAT.values()),
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)},
        )
    return _converter


def pdf_page_count(path: Path) -> int:
    """Page count via ``pypdfium2`` alone -- no layout/table-structure
    model weights are loaded for this. Lets a ``documents.max_pages``
    check reject an oversized PDF before ``convert()`` would trigger
    Docling's model download at all.
    """
    import pypdfium2 as pdfium

    handle = pdfium.PdfDocument(str(path))
    try:
        return len(handle)
    finally:
        handle.close()


def convert(path: Path) -> DoclingDocument:
    """Converts ``path`` (already confirmed supported by ``detect_format``)
    to a Docling ``DoclingDocument``, or raises ``DocumentConversionError``.
    """
    converter = _get_converter()
    try:
        result = converter.convert(str(path))
    except Exception as exc:  # noqa: BLE001 - Docling's own exception types vary by backend
        raise DocumentConversionError(
            f"{path}: Docling failed to convert this file: {exc}"
        ) from exc
    if result.status not in _SUCCESS_STATUSES:
        raise DocumentConversionError(
            f"{path}: Docling conversion did not succeed (status={result.status})"
        )
    return result.document
