"""Source registration: validates a path, assigns a stable id, and keeps
the global ``sources`` table plus that source's project directory in sync.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ragpilot.core import paths
from ragpilot.core.errors import SourceUnavailableError, UsageError
from ragpilot.core.models import IndexingMode, Source, SourceType
from ragpilot.storage.migrations import apply_migrations
from ragpilot.storage.repositories import sources_repo
from ragpilot.storage.sqlite import connect

_NETWORK_PREFIXES = ("\\\\", "//", "smb://", "nfs://", "afp://")


def detect_source_type(raw_path: str) -> SourceType:
    if raw_path.startswith(_NETWORK_PREFIXES) and not raw_path.startswith("///"):
        return SourceType.NETWORK
    return SourceType.LOCAL


def make_source_id(canonical_path: str) -> str:
    return "src_" + hashlib.sha256(canonical_path.encode("utf-8")).hexdigest()[:10]


class SourceRegistry:
    def __init__(self, conn: sqlite3.Connection, *, home: Path | None = None) -> None:
        self._conn = conn
        self._home = home

    def add(
        self,
        raw_path: str,
        *,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> Source:
        source_type = detect_source_type(raw_path)
        path = Path(raw_path).expanduser()
        if not path.exists():
            raise SourceUnavailableError(f"source path does not exist: {raw_path}")
        canonical = str(path.resolve())
        if not path.is_dir():
            raise SourceUnavailableError(f"source path is not a directory: {canonical}")

        existing = sources_repo.get_by_path(self._conn, canonical)
        if existing is not None:
            return existing

        now = datetime.now(UTC).isoformat()
        source = Source(
            id=make_source_id(canonical),
            path=canonical,
            source_type=source_type,
            enabled=True,
            indexing_mode=IndexingMode.FULL,
            include_patterns=include_patterns or [],
            exclude_patterns=exclude_patterns or [],
            created_at=now,
            updated_at=now,
        )
        sources_repo.create(self._conn, source)

        project_id = paths.project_id_for_path(path)
        paths.ensure_project_layout(project_id, self._home)
        project_conn = connect(paths.project_db_path(project_id, self._home))
        try:
            apply_migrations(project_conn, "knowledge")
        finally:
            project_conn.close()
        return source

    def get(self, source_id: str) -> Source:
        source = sources_repo.get(self._conn, source_id)
        if source is None:
            raise UsageError(f"no such source: {source_id}")
        return source

    def list(self, *, enabled_only: bool = False) -> list[Source]:
        return sources_repo.list_all(self._conn, enabled_only=enabled_only)

    def set_enabled(self, source_id: str, enabled: bool) -> Source:
        self.get(source_id)
        sources_repo.set_enabled(
            self._conn, source_id, enabled, updated_at=datetime.now(UTC).isoformat()
        )
        return self.get(source_id)

    def remove(self, source_id: str) -> None:
        self.get(source_id)
        sources_repo.delete(self._conn, source_id)
