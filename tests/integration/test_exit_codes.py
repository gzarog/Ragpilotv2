from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import ragpilot.indexing.coordinator as coordinator_module
from ragpilot.cli.main import app
from ragpilot.core.errors import (
    EXIT_CONFIG_ERROR,
    EXIT_HEALTH_CHECK_FAILURE,
    EXIT_INDEXING_PARTIAL_FAILURE,
    EXIT_INVALID_ARGUMENTS,
    EXIT_SOURCE_UNAVAILABLE,
)


def test_missing_required_argument_is_invalid_arguments(
    ragpilot_home: Path, runner: CliRunner
) -> None:
    result = runner.invoke(app, ["source", "add"])
    assert result.exit_code == EXIT_INVALID_ARGUMENTS


def test_malformed_config_is_config_error(
    ragpilot_home: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    ragpilot_home.mkdir(parents=True, exist_ok=True)
    (ragpilot_home / "config.yaml").write_text("runtime:\n  max_workers: \"not-an-int\"\n")
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == EXIT_CONFIG_ERROR


def test_add_nonexistent_source_is_source_unavailable(
    ragpilot_home: Path, runner: CliRunner, tmp_path: Path
) -> None:
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["source", "add", str(tmp_path / "does-not-exist")])
    assert result.exit_code == EXIT_SOURCE_UNAVAILABLE


def test_partial_indexing_failure_is_reported_and_does_not_crash(
    ragpilot_home: Path,
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Non-code extensions: cli/index.py routes FileKind.CODE through the
    # real Tree-sitter CodeProcessor (Phase 2), so this generic "a poisoned
    # processor must not crash the CLI" test uses document-kind files to
    # keep exercising the default registry's raw_processor path it patches
    # below. Phase 2's own code/parser crash-isolation is covered by
    # tests/integration/test_code_indexing.py.
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "good1.md").write_text("ok")
    (source_dir / "good2.md").write_text("ok too")
    (source_dir / "poison.md").write_text("boom")
    monkeypatch.chdir(tmp_path)

    original_raw_processor = coordinator_module.raw_processor

    def poisoned_processor(
        ctx: coordinator_module.ProcessorContext,
    ) -> coordinator_module.ProcessingOutcome:
        if ctx.path.name == "poison.md":
            raise ValueError("simulated permanent parser failure")
        return original_raw_processor(ctx)

    # Force every attempt to look permanent so the test doesn't depend on
    # the real retry attempt threshold.
    monkeypatch.setattr(coordinator_module.retry, "is_permanent", lambda attempt: True)
    monkeypatch.setattr(coordinator_module, "raw_processor", poisoned_processor)

    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["source", "add", str(source_dir)]).exit_code == 0

    result = runner.invoke(app, ["index"])
    # A controlled exit (SystemExit carrying our code) proves the process
    # did not crash on an unhandled traceback despite the poisoned file.
    assert result.exception is None or isinstance(result.exception, SystemExit), result.output
    assert result.exit_code == EXIT_INDEXING_PARTIAL_FAILURE

    status = runner.invoke(app, ["status", "--json"])
    totals = json.loads(status.output)["data"]["totals"]["by_status"]
    assert totals.get("indexed", 0) == 2
    assert totals.get("failed", 0) == 1


def test_doctor_reports_unhealthy_when_source_unreachable(
    ragpilot_home: Path, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "a.py").write_text("print('a')")
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["source", "add", str(source_dir)]).exit_code == 0
    shutil.rmtree(source_dir)

    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == EXIT_HEALTH_CHECK_FAILURE

    payload = json.loads(result.output)
    assert payload["data"]["result"] == "UNHEALTHY"
