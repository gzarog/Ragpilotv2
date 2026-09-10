"""Walks a source root and yields candidate files, honoring ignore rules
and refusing to cross the allowed root via symlinks or traversal.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from ragpilot.core.errors import SecurityViolationError
from ragpilot.core.models import ScannedFile
from ragpilot.security.path_guard import PathGuard
from ragpilot.sources.ignore import IgnoreMatcher


def check_root_accessible(root: Path) -> str | None:
    """Returns ``None`` if ``root`` is currently reachable (exists, is a
    directory, and its entries can be listed), else a short reason.

    ``os.walk()`` -- what ``scan()`` below is built on -- silently yields
    nothing for a root it cannot list (its default ``onerror`` is a
    no-op): to a caller only watching ``scan()``'s output, an unmounted
    network share is indistinguishable from a directory that is
    genuinely empty. This performs the one real syscall ``os.walk``
    itself skips (listing the root) so a caller can tell those two cases
    apart *before* trusting ``scan()``'s result for deletion
    reconciliation -- see ``indexing/coordinator.py``.
    """
    try:
        resolved = root.resolve()
    except OSError as exc:
        return f"cannot resolve path: {exc}"
    if not resolved.exists():
        return "path does not exist"
    if not resolved.is_dir():
        return "path is not a directory"
    try:
        with os.scandir(resolved) as entries:
            next(iter(entries), None)
    except OSError as exc:
        return f"cannot list directory: {exc}"
    return None


def scan(
    root: Path,
    *,
    guard: PathGuard,
    ignore_matcher: IgnoreMatcher,
    follow_symlinks: bool = False,
) -> Iterator[ScannedFile]:
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        current = Path(dirpath)
        kept_dirs = []
        for dirname in dirnames:
            candidate = current / dirname
            if not follow_symlinks and candidate.is_symlink():
                continue
            if ignore_matcher.is_ignored(candidate, is_dir=True):
                continue
            try:
                guard.resolve(candidate)
            except SecurityViolationError:
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in filenames:
            candidate = current / filename
            if not follow_symlinks and candidate.is_symlink():
                continue
            if ignore_matcher.is_ignored(candidate, is_dir=False):
                continue
            try:
                resolved = guard.resolve(candidate)
            except SecurityViolationError:
                continue
            try:
                stat = resolved.stat()
            except OSError:
                continue
            yield ScannedFile(path=str(resolved), size=stat.st_size, mtime=stat.st_mtime)
