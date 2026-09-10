"""Root Typer application wiring every RAGpilot subcommand."""

from __future__ import annotations

import typer

from ragpilot.cli import (
    callees,
    callers,
    config_cmd,
    docs,
    doctor,
    index,
    init,
    references,
    source,
    status,
    symbol,
    version_cmd,
)

app = typer.Typer(
    name="ragpilot",
    no_args_is_help=True,
    add_completion=False,
    help="Local-first knowledge compiler and retrieval engine.",
)

app.add_typer(source.app, name="source")
app.add_typer(config_cmd.app, name="config")

app.command("init", help="Bootstrap the RAGpilot runtime directory.")(init.init)
app.command("index", help="Scan sources and process pending files.")(index.index)
app.command("status", help="Show indexing status.")(status.status)
app.command("doctor", help="Run health checks.")(doctor.doctor)
app.command("health", help="Show a condensed health summary.")(doctor.health)
app.command("version", help="Show the RAGpilot version.")(version_cmd.version)
app.command("symbol", help="Look up a code symbol by name.")(symbol.symbol)
app.command("callers", help="Show entities that call the given symbol.")(callers.callers)
app.command("callees", help="Show entities the given symbol calls.")(callees.callees)
app.command("references", help="Show all edges touching the given symbol.")(references.references)
app.command("docs", help="List indexed documents.")(docs.docs)


if __name__ == "__main__":
    app()
