"""Architectural regression test (CLI performance improvement plan, Phase
1/2): a lightweight command -- ``version``, ``--help``, ``config --help``,
``search --help`` -- must never import Docling/torch/transformers/mcp/
openai/anthropic/usearch. Those belong to subsystems (document indexing,
MCP serving, ``ask``, semantic search) a lightweight command never
touches; loading them anyway is exactly the startup-latency regression
this plan exists to prevent, so this checks the import graph directly
rather than a timing number a shared CI runner cannot reliably gate on
(see ``benchmarks/cli_startup/targets.py``).

Runs each command in a fresh subprocess -- inspecting the current
process's ``sys.modules`` would be polluted by whatever the rest of the
test suite already imported.

Marked ``xfail(strict=True)``: ``ragpilot.cli.main`` currently imports
every CLI submodule (``ask``, ``index``, ``serve``, ``watch``, ``vectors``,
...) eagerly at module load time, which transitively loads the full heavy
stack regardless of which command is invoked. Flip to a plain assertion
once the lazy-import/minimal-bootstrap work (Phase 2) removes those eager
imports -- an unexpected pass here would mean the regression was fixed
without anyone noticing, which ``strict=True`` turns into a failure
instead of a silently-stale xfail.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

HEAVY_MODULES = (
    "torch",
    "transformers",
    "docling",
    "mcp",
    "usearch",
    "openai",
    "anthropic",
)

LIGHTWEIGHT_INVOCATIONS = (
    ["version"],
    ["--help"],
    ["config", "--help"],
    ["search", "--help"],
)


def _loaded_heavy_modules(cli_args: list[str]) -> list[str]:
    script = (
        "import sys\n"
        "from ragpilot.cli.main import app\n"
        "try:\n"
        f"    app({cli_args!r})\n"
        "except SystemExit:\n"
        "    pass\n"
        f"heavy = {list(HEAVY_MODULES)!r}\n"
        "print(','.join(sorted(m for m in heavy if m in sys.modules)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    loaded = result.stdout.strip()
    return loaded.split(",") if loaded else []


@pytest.mark.xfail(
    reason=(
        "ragpilot.cli.main currently imports every CLI submodule eagerly, "
        "which transitively loads Docling/torch/transformers/mcp/openai/"
        "anthropic/usearch regardless of the command invoked; fixed by the "
        "lazy-import/minimal-bootstrap work (Phase 2)."
    ),
    strict=True,
)
@pytest.mark.parametrize("cli_args", LIGHTWEIGHT_INVOCATIONS, ids=lambda a: " ".join(a))
def test_lightweight_command_does_not_load_heavy_dependencies(cli_args: list[str]) -> None:
    loaded = _loaded_heavy_modules(cli_args)
    assert loaded == [], f"{cli_args} loaded heavy modules: {loaded}"
