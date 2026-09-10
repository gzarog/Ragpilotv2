from __future__ import annotations

from pathlib import Path

import pytest

from ragpilot.core.errors import SourceUnavailableError, UsageError
from ragpilot.core.models import SourceType
from ragpilot.sources.registry import SourceRegistry, detect_source_type, make_source_id
from ragpilot.storage.migrations import apply_migrations
from ragpilot.storage.sqlite import connect


@pytest.mark.parametrize(
    "raw_path,expected",
    [
        ("/home/user/project", SourceType.LOCAL),
        ("C:\\Users\\me\\project", SourceType.LOCAL),
        ("//fileserver/share", SourceType.NETWORK),
        ("\\\\fileserver\\share", SourceType.NETWORK),
        ("smb://fileserver/share", SourceType.NETWORK),
    ],
)
def test_detect_source_type(raw_path: str, expected: SourceType) -> None:
    assert detect_source_type(raw_path) is expected


def test_make_source_id_is_stable_and_prefixed() -> None:
    assert make_source_id("/a/b") == make_source_id("/a/b")
    assert make_source_id("/a/b").startswith("src_")


def test_add_rejects_missing_path(tmp_path: Path) -> None:
    conn = connect(tmp_path / "sources.db")
    apply_migrations(conn, "sources")
    registry = SourceRegistry(conn, home=tmp_path / "home")
    with pytest.raises(SourceUnavailableError):
        registry.add(str(tmp_path / "missing"))


def test_add_is_idempotent_for_same_path(tmp_path: Path) -> None:
    conn = connect(tmp_path / "sources.db")
    apply_migrations(conn, "sources")
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    registry = SourceRegistry(conn, home=tmp_path / "home")
    first = registry.add(str(source_dir))
    second = registry.add(str(source_dir))
    assert first.id == second.id


def test_get_unknown_source_is_usage_error(tmp_path: Path) -> None:
    conn = connect(tmp_path / "sources.db")
    apply_migrations(conn, "sources")
    registry = SourceRegistry(conn, home=tmp_path / "home")
    with pytest.raises(UsageError):
        registry.get("does-not-exist")
