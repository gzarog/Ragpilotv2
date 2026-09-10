from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def ragpilot_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "ragpilot_home"
    monkeypatch.setenv("RAGPILOT_HOME", str(home))
    return home


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()
