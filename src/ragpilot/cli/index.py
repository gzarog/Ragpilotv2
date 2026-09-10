"""``ragpilot index`` -- scan registered sources and process pending files."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from ragpilot.core import paths
from ragpilot.core.errors import IndexingPartialFailureError
from ragpilot.core.lifecycle import AppContext
from ragpilot.indexing.coordinator import IndexCoordinator
from ragpilot.sources.registry import SourceRegistry
from ragpilot.storage.repositories import sources_repo

from ._common import cli_command, console


@cli_command
def index(
    source_id: Annotated[
        str | None, typer.Option("--source", help="Only index this source id.")
    ] = None,
) -> None:
    with AppContext.bootstrap() as ctx:
        lock = ctx.acquire_lock("index")
        try:
            registry = SourceRegistry(ctx.sources_conn, home=ctx.home)
            if source_id is not None:
                sources = [registry.get(source_id)]
            else:
                sources = registry.list(enabled_only=True)

            if not sources:
                console.print("[yellow]No enabled sources to index.[/yellow]")
                return

            total_failed = 0
            for source in sources:
                project_id = paths.project_id_for_path(Path(source.path))
                conn = ctx.project_conn(project_id)
                coordinator = IndexCoordinator(
                    conn,
                    source.id,
                    source.path,
                    source.include_patterns,
                    source.exclude_patterns,
                    ctx.config,
                )
                result = coordinator.run()
                total_failed += result.failed
                now = datetime.now(UTC).isoformat()
                sources_repo.update_scan_result(
                    ctx.sources_conn,
                    source.id,
                    last_scan_at=now,
                    last_error=(f"{result.failed} file(s) failed" if result.failed else None),
                    updated_at=now,
                )
                console.print(
                    f"[bold]{source.id}[/bold] {source.path}: "
                    f"scanned={result.scanned} new={result.new} changed={result.changed} "
                    f"unchanged={result.unchanged} deleted={result.deleted} "
                    f"indexed={result.indexed} skipped={result.skipped_limit} "
                    f"failed={result.failed}"
                )

            if total_failed:
                raise IndexingPartialFailureError(
                    f"{total_failed} file(s) failed to index; see 'ragpilot doctor' for details"
                )
        finally:
            lock.release()
