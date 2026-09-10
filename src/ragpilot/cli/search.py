"""``ragpilot search QUERY [--limit N] [--json]``."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from ragpilot.core.lifecycle import AppContext
from ragpilot.retrieval import lexical, semantic

from ._common import cli_command, console, print_json


@cli_command
def search(
    query: Annotated[
        str, typer.Argument(help="Identifier, phrase, or path fragment to search for.")
    ],
    limit: Annotated[int, typer.Option("--limit", min=1, max=200)] = lexical.DEFAULT_LIMIT,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    with AppContext.bootstrap() as ctx:
        results = lexical.search(ctx, query, limit=limit)

        # Only called (and only imports torch/transformers, see
        # retrieval/embedder.py) when search.semantic is actually on --
        # the default, disabled path behaves exactly like Phase 5 left
        # it. Kept as its own section rather than merged into
        # ``results`` above: a similarity score is a distinct signal
        # from lexical rank, never mixed into the same ranked list (see
        # retrieval/semantic.py's docstring).
        semantic_result = (
            semantic.semantic_search(ctx, query, config=ctx.config.search, limit=limit)
            if ctx.config.search.semantic
            else None
        )

        if json_output:
            payload: dict[str, object] = {
                "query": query,
                "results": [r.to_dict() for r in results],
            }
            if semantic_result is not None:
                payload["semantic"] = {
                    "available": semantic_result.available,
                    "reason": semantic_result.reason,
                    "results": [h.to_dict() for h in semantic_result.results],
                }
            print_json(payload)
            return

        if not results:
            console.print(f"[yellow]No results for '{query}'.[/yellow]")
        else:
            table = Table("Kind", "Tier", "Title", "Path", "Source")
            for result in results:
                table.add_row(
                    result.kind,
                    result.tier.name.lower(),
                    result.title,
                    result.path,
                    result.source_id,
                )
            console.print(table)

        if semantic_result is not None:
            if semantic_result.results:
                console.print("[bold]Semantic matches[/bold]")
                sem_table = Table("Kind", "Score", "Title", "Path", "Source")
                for hit in semantic_result.results:
                    sem_table.add_row(
                        hit.kind, f"{hit.score:.3f}", hit.title, hit.path, hit.source_id
                    )
                console.print(sem_table)
            elif not semantic_result.available:
                console.print(f"[dim]Semantic search unavailable: {semantic_result.reason}[/dim]")
