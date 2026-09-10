"""``ragpilot status [--json]``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer
from rich.table import Table

from ragpilot.core import paths
from ragpilot.core.lifecycle import AppContext
from ragpilot.sources.registry import SourceRegistry
from ragpilot.storage.repositories import files_repo, jobs_repo

from ._common import cli_command, console, print_json


def _run(ctx: AppContext) -> dict[str, Any]:
    """Shared with Phase 6's ``ragpilot_status`` MCP tool."""
    registry = SourceRegistry(ctx.sources_conn, home=ctx.home)
    sources = registry.list()

    per_source: list[dict[str, Any]] = []
    totals: dict[str, int] = {}
    total_queue_depth = 0

    for source in sources:
        project_id = paths.project_id_for_path(Path(source.path))
        conn = ctx.project_conn(project_id)
        counts = files_repo.count_by_status(conn, source.id)
        depth = jobs_repo.queue_depth(conn)
        total_queue_depth += depth
        for key, value in counts.items():
            totals[key] = totals.get(key, 0) + value
        per_source.append(
            {
                "id": source.id,
                "path": source.path,
                "enabled": source.enabled,
                "status": source.status.value,
                "counts": counts,
                "queue_depth": depth,
                "last_scan_at": source.last_scan_at,
                "last_error": source.last_error,
            }
        )

    return {
        "sources": per_source,
        "totals": {"by_status": totals, "queue_depth": total_queue_depth},
    }


@cli_command
def status(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    with AppContext.bootstrap() as ctx:
        data = _run(ctx)
        per_source = data["sources"]

        if json_output:
            print_json(data)
            return

        table = Table("Source", "Status", "Indexed", "Queued", "Failed", "Queue Depth", "Last Scan")
        for row in per_source:
            counts = row["counts"]
            table.add_row(
                row["id"],
                row["status"],
                str(counts.get("indexed", 0)),
                str(counts.get("queued", 0)),
                str(counts.get("failed", 0)),
                str(row["queue_depth"]),
                row["last_scan_at"] or "-",
            )
        console.print(table)
