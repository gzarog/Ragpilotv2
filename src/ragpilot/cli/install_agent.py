"""``ragpilot install-agent [--write PATH]``.

Blueprint section 74 names this command "connect AI agent" but gives no
further behavior -- kept deliberately modest and safe: it PRINTS the
standard ``{"mcpServers": {"ragpilot": {...}}}`` JSON snippet most MCP
clients (Claude Desktop, Claude Code, ...) expect for registering a local
stdio MCP server, and, only with an explicit ``--write PATH``, writes that
same snippet to the given file. It never searches for, discovers, or
edits a real client config file on its own (e.g. ``~/.claude.json``) --
silently rewriting a file the user did not name is exactly the kind of
surprising, hard-to-reverse action this command avoids. Pointing
``--write`` at an existing client config file (to merge the snippet in)
is left to the user, or to that client's own import flow.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from ._common import cli_command, error_console


def _snippet() -> dict[str, object]:
    return {
        "mcpServers": {
            "ragpilot": {
                "command": "ragpilot",
                "args": ["serve", "--mcp"],
            }
        }
    }


@cli_command
def install_agent(
    write: Annotated[
        Path | None,
        typer.Option(
            "--write",
            help=(
                "Also write the snippet to this exact file path. No existing "
                "MCP client config is ever discovered or edited automatically."
            ),
        ),
    ] = None,
) -> None:
    # Plain ``print`` (not the Rich console) so stdout carries exactly this
    # JSON and nothing else -- pipeable (``ragpilot install-agent > x.json``)
    # and stable for tests, matching cli/_common.py's ``print_json`` for the
    # same reason.
    snippet = json.dumps(_snippet(), indent=2)
    print(snippet)

    if write is not None:
        write.parent.mkdir(parents=True, exist_ok=True)
        write.write_text(snippet + "\n", encoding="utf-8")
        error_console.print(f"[bold green]Wrote[/bold green] {write}")
