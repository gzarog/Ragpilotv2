"""``ragpilot index`` -- scan registered sources and process pending files."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from ragpilot.code.processor import code_processor
from ragpilot.core import paths
from ragpilot.core.config import RagpilotConfig
from ragpilot.core.errors import IndexingPartialFailureError
from ragpilot.core.lifecycle import AppContext
from ragpilot.core.models import FileKind
from ragpilot.documents.pipeline import document_processor
from ragpilot.indexing.coordinator import IndexCoordinator, ProcessorRegistry, default_registry
from ragpilot.knowledge.linker import link_touched_files
from ragpilot.sources.registry import SourceRegistry
from ragpilot.storage.repositories import sources_repo
from ragpilot.storage.sqlite import transaction

from ._common import cli_command, console


def _processor_registry(config: RagpilotConfig) -> ProcessorRegistry:
    registry = default_registry()
    registry.register(FileKind.CODE, code_processor)
    # Respects documents.enabled (core/config.py) -- when off, document-kind
    # files still index via the default raw processor (recorded, marked
    # INDEXED) just without Docling-derived content.
    if config.documents.enabled:
        registry.register(FileKind.DOCUMENT, document_processor)
    return registry


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
            processors = _processor_registry(ctx.config)
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
                    processors=processors,
                )
                result = coordinator.run()
                total_failed += result.failed

                # Phase 4's cross-domain linking pass: deliberately run
                # here, after the per-file processor queue has fully
                # drained, rather than inside IndexCoordinator itself --
                # a link needs both a code entity and a document to
                # exist, so it cannot be computed per-file the way
                # Phase 2/3's atomic generational writes are, and
                # IndexCoordinator stays kind-agnostic (it does not import
                # anything from code/ or documents/ directly).
                linked = 0
                if result.touched_code_file_ids or result.touched_document_file_ids:
                    with transaction(conn):
                        linked = link_touched_files(
                            conn,
                            touched_code_file_ids=result.touched_code_file_ids,
                            touched_document_file_ids=result.touched_document_file_ids,
                        )

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
                    f"failed={result.failed} linked={linked}"
                )

            if total_failed:
                raise IndexingPartialFailureError(
                    f"{total_failed} file(s) failed to index; see 'ragpilot doctor' for details"
                )
        finally:
            lock.release()
