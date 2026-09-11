"""``ragpilot update [check|status|install]`` -- real Typer CLI dispatch,
with ``checker.fetch_latest_release`` (the one real network call) mocked
out. Proves the CLI wiring, cache read/write-through, JSON output, and
the "not implemented yet" install stub's exit code -- not the checker's
own HTTP handling, which ``tests/unit/test_update_checker.py`` covers
directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragpilot import __version__
from ragpilot.cli.main import app
from ragpilot.core.errors import EXIT_GENERIC_FAILURE
from ragpilot.update import checker
from ragpilot.update.models import ReleaseInfo


def _fake_release(version: str) -> ReleaseInfo:
    return ReleaseInfo(
        version=version,
        tag_name=f"v{version}",
        html_url=f"https://github.com/gzarog/Ragpilotv2/releases/tag/v{version}",
    )


def test_check_reports_update_available_and_writes_cache(
    ragpilot_home: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    newer = "999.0.0"
    monkeypatch.setattr(checker, "fetch_latest_release", lambda **_: _fake_release(newer))

    result = runner.invoke(app, ["update", "check"])

    assert result.exit_code == 0, result.output
    assert f"Installed: {__version__}" in result.output
    assert f"Latest:    {newer}" in result.output
    assert "Update available." in result.output
    assert "ragpilot update install" in result.output

    status_result = runner.invoke(app, ["update", "status", "--json"])
    payload = json.loads(status_result.output)["data"]
    assert payload["latest_version"] == newer
    assert payload["status"] == "update available"


def test_check_reports_up_to_date(
    ragpilot_home: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checker, "fetch_latest_release", lambda **_: _fake_release(__version__))

    result = runner.invoke(app, ["update", "check"])

    assert result.exit_code == 0, result.output
    assert "is up to date." in result.output
    assert "Update available." not in result.output


def test_check_json_output(
    ragpilot_home: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checker, "fetch_latest_release", lambda **_: _fake_release("999.0.0"))

    result = runner.invoke(app, ["update", "check", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)["data"]
    assert payload["installed_version"] == __version__
    assert payload["latest_version"] == "999.0.0"
    assert payload["update_available"] is True
    assert payload["release_url"].endswith("v999.0.0")


def test_check_surfaces_a_clear_error_when_github_is_unreachable(
    ragpilot_home: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(**_: object) -> ReleaseInfo:
        raise checker.UpdateCheckError("GitHub is unreachable: simulated")

    monkeypatch.setattr(checker, "fetch_latest_release", _raise)

    result = runner.invoke(app, ["update", "check"])

    assert result.exit_code == EXIT_GENERIC_FAILURE
    assert "could not check for updates" in result.output
    assert "GitHub is unreachable" in result.output


def test_bare_update_behaves_like_check(
    ragpilot_home: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checker, "fetch_latest_release", lambda **_: _fake_release("999.0.0"))

    result = runner.invoke(app, ["update"])

    assert result.exit_code == 0, result.output
    assert "Update available." in result.output


def test_status_with_no_prior_check_reports_unknown(
    ragpilot_home: Path, runner: CliRunner
) -> None:
    result = runner.invoke(app, ["update", "status"])

    assert result.exit_code == 0, result.output
    assert f"Installed: {__version__}" in result.output
    assert "unknown" in result.output


def test_status_json_with_no_prior_check(ragpilot_home: Path, runner: CliRunner) -> None:
    result = runner.invoke(app, ["update", "status", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)["data"]
    assert payload["latest_version"] is None
    assert payload["status"] == "unknown"


def test_install_reports_not_implemented_yet(ragpilot_home: Path, runner: CliRunner) -> None:
    result = runner.invoke(app, ["update", "install"])

    assert result.exit_code == EXIT_GENERIC_FAILURE
    assert "not implemented yet" in result.output
    assert "install.sh" in result.output
