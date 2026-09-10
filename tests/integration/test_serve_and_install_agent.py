"""``ragpilot serve --mcp`` (fast-fail paths only -- the success path
blocks on stdio forever and is deliberately not exercised here, see
``mcp/server.py``'s ``run_stdio`` docstring) and ``ragpilot install-agent``.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer.main
from typer.testing import CliRunner

from ragpilot.cli.main import app
from ragpilot.core.errors import EXIT_CONFIG_ERROR, EXIT_INVALID_ARGUMENTS


def test_serve_without_mcp_flag_is_invalid_arguments(
    ragpilot_home: Path, runner: CliRunner
) -> None:
    result = runner.invoke(app, ["serve"])

    assert result.exit_code == EXIT_INVALID_ARGUMENTS
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_serve_mcp_fails_fast_when_mcp_disabled(
    ragpilot_home: Path, runner: CliRunner
) -> None:
    assert runner.invoke(app, ["init"]).exit_code == 0
    set_result = runner.invoke(app, ["config", "set", "mcp.enabled", "false"])
    assert set_result.exit_code == 0, set_result.output

    result = runner.invoke(app, ["serve", "--mcp"])

    assert result.exit_code == EXIT_CONFIG_ERROR
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "disabled" in result.output.lower()


def test_install_agent_prints_the_expected_mcp_client_snippet(
    ragpilot_home: Path, runner: CliRunner
) -> None:
    result = runner.invoke(app, ["install-agent"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {
        "mcpServers": {
            "ragpilot": {
                "command": "ragpilot",
                "args": ["serve", "--mcp"],
            }
        }
    }


def test_install_agent_write_writes_exactly_that_content_and_nothing_else(
    ragpilot_home: Path, runner: CliRunner, tmp_path: Path
) -> None:
    sentinel = tmp_path / "untouched.json"
    sentinel.write_text('{"unrelated": true}', encoding="utf-8")

    target = tmp_path / "mcp-config" / "ragpilot.json"
    result = runner.invoke(app, ["install-agent", "--write", str(target)])

    assert result.exit_code == 0, result.output
    assert target.is_file()
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written == {
        "mcpServers": {
            "ragpilot": {
                "command": "ragpilot",
                "args": ["serve", "--mcp"],
            }
        }
    }
    printed = json.loads(result.stdout)
    assert printed == written
    # Rich soft-wraps long paths across lines in a narrow captured
    # console, so compare after collapsing hard line breaks.
    unwrapped_stderr = result.stderr.replace("\n", "")
    assert "Wrote" in unwrapped_stderr
    assert target.name in unwrapped_stderr

    # The command must never discover or edit any other file.
    assert sentinel.read_text(encoding="utf-8") == '{"unrelated": true}'


def test_serve_help_documents_the_mcp_flag(ragpilot_home: Path, runner: CliRunner) -> None:
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0

    # Not a substring check on the rendered --help text: Rich's console
    # width detection (and therefore where/whether it wraps or truncates
    # a long option row) varies by environment in ways collapsing "\n"
    # alone doesn't reliably fix -- observed passing locally under a
    # forced COLUMNS=80 but still failing on GitHub Actions' actual
    # (narrower, differently-detected) width. Ask Click directly instead,
    # which is exact and width-independent.
    serve_command = typer.main.get_command(app).get_command(None, "serve")  # type: ignore[union-attr]
    assert serve_command is not None
    assert any("--mcp" in opt.opts for opt in serve_command.params)
