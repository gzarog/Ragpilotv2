from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragpilot.retrieval import ann
from ragpilot.retrieval import cache as search_cache


@pytest.fixture
def ragpilot_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "ragpilot_home"
    monkeypatch.setenv("RAGPILOT_HOME", str(home))
    return home


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def _reset_search_caches() -> None:
    """``retrieval/cache.py``'s query-result/query-embedding caches, and
    ``retrieval/ann.py``'s warm ANN index cache, are all deliberately
    process-global state (see each module's own docstring) so they
    actually help a long-lived process like ``ragpilot serve`` -- but
    that means they would otherwise leak between test functions sharing
    this one pytest process (e.g. two tests both querying
    "AnimalService" against unrelated fixture databases). Clearing them
    before every test keeps each test's cache state as fresh as a real
    new process would see.
    """
    search_cache.reset_caches()
    ann.reset_warm_cache()
