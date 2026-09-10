"""``ragpilot search QUERY [--limit N] [--json]``."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from ragpilot.core.lifecycle import AppContext
from ragpilot.retrieval import lexical

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

        if json_output:
            print_json({"query": query, "results": [r.to_dict() for r in results]})
            return
        if not results:
            console.print(f"[yellow]No results for '{query}'.[/yellow]")
            return

        table = Table("Kind", "Tier", "Title", "Path", "Source")
        for result in results:
            table.add_row(
                result.kind, result.tier.name.lower(), result.title, result.path, result.source_id
            )
        console.print(table)
