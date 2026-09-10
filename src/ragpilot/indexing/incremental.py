"""Decides new/changed/unchanged/deleted by comparing a scan against the
file records already stored for a source.

Mtime+size is checked first (the "fast-skip"); the content hash is only
computed when that stat comparison can't already prove the file is
unchanged, and even then a hash match still counts as unchanged (handles
a touch that bumps mtime without changing content).
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from ragpilot.core.models import FileRecord, ScannedFile
from ragpilot.sources.fingerprint import stat_unchanged


class ChangeType(StrEnum):
    NEW = "new"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


def classify_change(
    existing: FileRecord | None,
    size: int,
    mtime: float,
    compute_hash: Callable[[], str],
) -> tuple[ChangeType, str]:
    if existing is None:
        return ChangeType.NEW, compute_hash()
    if stat_unchanged(existing.size, existing.mtime, size, mtime):
        return ChangeType.UNCHANGED, existing.content_hash or compute_hash()
    new_hash = compute_hash()
    if existing.content_hash is not None and new_hash == existing.content_hash:
        return ChangeType.UNCHANGED, new_hash
    return ChangeType.CHANGED, new_hash


def find_deleted(
    existing_by_path: dict[str, FileRecord], scanned: list[ScannedFile]
) -> list[FileRecord]:
    seen = {sf.path for sf in scanned}
    return [record for path, record in existing_by_path.items() if path not in seen]
