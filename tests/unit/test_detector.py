from __future__ import annotations

from pathlib import Path

from ragpilot.core.models import FileKind
from ragpilot.sources.detector import classify


def test_python_file_is_code() -> None:
    assert classify(Path("app.py")) is FileKind.CODE


def test_markdown_file_is_document() -> None:
    assert classify(Path("README.md")) is FileKind.DOCUMENT


def test_unknown_extension_is_unknown() -> None:
    assert classify(Path("data.bin")) is FileKind.UNKNOWN
