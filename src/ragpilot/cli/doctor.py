"""``ragpilot doctor [--json]`` and ``ragpilot health [--json]``."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import typer

from ragpilot import __version__
from ragpilot.core import paths
from ragpilot.core.errors import EXIT_HEALTH_CHECK_FAILURE
from ragpilot.core.lifecycle import AppContext
from ragpilot.sources.registry import SourceRegistry
from ragpilot.storage import schema
from ragpilot.storage.migrations import current_version
from ragpilot.storage.repositories import jobs_repo

from ._common import cli_command, console, print_json

Status = Literal["ok", "warn", "fail"]

_LOW_DISK_WARN_GB = 1.0
_QUEUE_DEPTH_WARN = 1000


@dataclass
class CheckResult:
    name: str
    status: Status
    detail: str


@dataclass
class CheckSection:
    name: str
    checks: list[CheckResult]


def _overall(sections: list[CheckSection]) -> str:
    statuses = {check.status for section in sections for check in section.checks}
    if "fail" in statuses:
        return "UNHEALTHY"
    if "warn" in statuses:
        return "HEALTHY WITH WARNINGS"
    return "HEALTHY"


def run_checks(ctx: AppContext) -> list[CheckSection]:
    sections: list[CheckSection] = []

    sections.append(
        CheckSection("Core", [CheckResult("version", "ok", f"version {__version__}")])
    )

    journal_mode = ctx.sources_conn.execute("PRAGMA journal_mode").fetchone()[0]
    schema_version = current_version(ctx.sources_conn)
    db_checks = [
        CheckResult("sqlite", "ok", "SQLite"),
        CheckResult(
            "wal", "ok" if journal_mode == "wal" else "warn", f"WAL ({journal_mode})"
        ),
        CheckResult(
            "schema",
            "ok" if schema_version == schema.CURRENT_SCHEMA_VERSION else "fail",
            f"schema v{schema_version}",
        ),
    ]
    sections.append(CheckSection("Database", db_checks))

    registry = SourceRegistry(ctx.sources_conn, home=ctx.home)
    sources = registry.list(enabled_only=True)
    unreachable = [s for s in sources if not os.access(s.path, os.R_OK)]
    sources_status: Status = "ok" if not unreachable else "fail"
    sections.append(
        CheckSection(
            "Sources",
            [
                CheckResult(
                    "reachability",
                    sources_status,
                    f"{len(sources) - len(unreachable)}/{len(sources)} reachable",
                )
            ],
        )
    )

    total_queue = 0
    for source in sources:
        project_id = paths.project_id_for_path(Path(source.path))
        conn = ctx.project_conn(project_id)
        total_queue += jobs_repo.queue_depth(conn)
    queue_status: Status = "ok" if total_queue < _QUEUE_DEPTH_WARN else "warn"
    detail = "queue empty" if total_queue == 0 else f"queue depth {total_queue}"
    sections.append(CheckSection("Index", [CheckResult("queue", queue_status, detail)]))

    free_bytes = shutil.disk_usage(ctx.home).free
    free_gb = free_bytes / (1024**3)
    disk_status: Status = "ok" if free_gb >= _LOW_DISK_WARN_GB else "warn"
    sections.append(
        CheckSection("Disk", [CheckResult("free_space", disk_status, f"{free_gb:.0f} GB free")])
    )

    return sections


def _overall_colour(overall: str) -> str:
    if overall == "HEALTHY":
        return "green"
    if overall == "UNHEALTHY":
        return "red"
    return "yellow"


def _render_human(sections: list[CheckSection], overall: str) -> None:
    console.print("\n[bold]RAGpilot Doctor[/bold]\n")
    style = {"ok": "green", "warn": "yellow", "fail": "red"}
    for section in sections:
        console.print(f"[bold]{section.name}[/bold]")
        for check in section.checks:
            colour = style[check.status]
            console.print(f"  [{colour}]{check.status.upper()}[/{colour}] {check.detail}")
        console.print()
    overall_colour = _overall_colour(overall)
    console.print(f"Result:\n  [bold {overall_colour}]{overall}[/bold {overall_colour}]")


def _sections_to_json(sections: list[CheckSection], overall: str) -> dict[str, Any]:
    return {
        "result": overall,
        "sections": [
            {
                "name": section.name,
                "checks": [
                    {"name": c.name, "status": c.status, "detail": c.detail} for c in section.checks
                ],
            }
            for section in sections
        ],
    }


@cli_command
def doctor(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    with AppContext.bootstrap() as ctx:
        sections = run_checks(ctx)
        overall = _overall(sections)
        if json_output:
            print_json(_sections_to_json(sections, overall))
        else:
            _render_human(sections, overall)
        if overall == "UNHEALTHY":
            raise typer.Exit(code=EXIT_HEALTH_CHECK_FAILURE)


@cli_command
def health(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    with AppContext.bootstrap() as ctx:
        sections = run_checks(ctx)
        overall = _overall(sections)
        if json_output:
            print_json({"result": overall})
        else:
            colour = _overall_colour(overall)
            console.print(f"[bold {colour}]{overall}[/bold {colour}]")
        if overall == "UNHEALTHY":
            raise typer.Exit(code=EXIT_HEALTH_CHECK_FAILURE)
