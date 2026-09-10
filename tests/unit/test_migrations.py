from __future__ import annotations

from pathlib import Path

from ragpilot.storage.migrations import apply_migrations, current_version
from ragpilot.storage.schema import CURRENT_SCHEMA_VERSION
from ragpilot.storage.sqlite import connect


def test_apply_migrations_creates_expected_tables(tmp_path: Path) -> None:
    conn = connect(tmp_path / "sources.db")
    try:
        apply_migrations(conn, "sources")
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"sources", "schema_migrations", "metadata"} <= tables
        assert current_version(conn) == CURRENT_SCHEMA_VERSION
    finally:
        conn.close()


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "knowledge.db")
    try:
        apply_migrations(conn, "knowledge")
        apply_migrations(conn, "knowledge")
        rows = conn.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()
        assert rows["n"] == 1
    finally:
        conn.close()


def test_knowledge_db_has_expected_tables(tmp_path: Path) -> None:
    conn = connect(tmp_path / "knowledge.db")
    try:
        apply_migrations(conn, "knowledge")
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"files", "index_jobs", "index_errors", "schema_migrations", "metadata"} <= tables
    finally:
        conn.close()


def test_wal_mode_is_active(tmp_path: Path) -> None:
    conn = connect(tmp_path / "db.sqlite")
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
    finally:
        conn.close()
