"""``ragpilot source add|list|info|enable|disable|remove``."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from ragpilot.core.lifecycle import AppContext
from ragpilot.sources.registry import SourceRegistry

from ._common import cli_command, console

app = typer.Typer(no_args_is_help=True, help="Manage registered sources.")


@app.command("add")
@cli_command
def add(
    path: Annotated[str, typer.Argument(help="Directory to register as a source.")],
    include: Annotated[list[str], typer.Option("--include", help="Include glob pattern.")] = [],  # noqa: B006
    exclude: Annotated[list[str], typer.Option("--exclude", help="Exclude glob pattern.")] = [],  # noqa: B006
) -> None:
    with AppContext.bootstrap() as ctx:
        registry = SourceRegistry(ctx.sources_conn, home=ctx.home)
        source = registry.add(path, include_patterns=list(include), exclude_patterns=list(exclude))
        console.print(f"[bold green]Added source[/bold green] {source.id} -> {source.path}")


@app.command("list")
@cli_command
def list_sources() -> None:
    with AppContext.bootstrap() as ctx:
        registry = SourceRegistry(ctx.sources_conn, home=ctx.home)
        sources = registry.list()
        table = Table("ID", "Path", "Type", "Enabled", "Status", "Last Scan")
        for source in sources:
            table.add_row(
                source.id,
                source.path,
                source.source_type.value,
                "yes" if source.enabled else "no",
                source.status.value,
                source.last_scan_at or "-",
            )
        console.print(table)


@app.command("info")
@cli_command
def info(source_id: Annotated[str, typer.Argument()]) -> None:
    with AppContext.bootstrap() as ctx:
        registry = SourceRegistry(ctx.sources_conn, home=ctx.home)
        source = registry.get(source_id)
        console.print_json(data=source.model_dump(mode="json"))


@app.command("enable")
@cli_command
def enable(source_id: Annotated[str, typer.Argument()]) -> None:
    with AppContext.bootstrap() as ctx:
        registry = SourceRegistry(ctx.sources_conn, home=ctx.home)
        registry.set_enabled(source_id, True)
        console.print(f"[green]Enabled[/green] {source_id}")


@app.command("disable")
@cli_command
def disable(source_id: Annotated[str, typer.Argument()]) -> None:
    with AppContext.bootstrap() as ctx:
        registry = SourceRegistry(ctx.sources_conn, home=ctx.home)
        registry.set_enabled(source_id, False)
        console.print(f"[yellow]Disabled[/yellow] {source_id}")


@app.command("remove")
@cli_command
def remove(source_id: Annotated[str, typer.Argument()]) -> None:
    with AppContext.bootstrap() as ctx:
        registry = SourceRegistry(ctx.sources_conn, home=ctx.home)
        registry.remove(source_id)
        console.print(f"[bold red]Removed[/bold red] {source_id}")
