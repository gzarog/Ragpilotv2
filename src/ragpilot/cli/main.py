"""Root Typer application wiring every RAGpilot subcommand."""

from __future__ import annotations

import typer

from ragpilot.cli import (
    callees,
    callers,
    config_cmd,
    docs,
    doctor,
    explore,
    impact,
    index,
    init,
    install_agent,
    link,
    references,
    search,
    serve,
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
app.add_typer(link.app, name="link")

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
app.command("search", help="Lexical search across code and documents.")(search.search)
app.command("impact", help="Show blast-radius impact analysis for a symbol.")(impact.impact)
app.command(
    "explore", help="Explore a query using all deterministic retrieval strategies."
)(explore.explore)
app.command("serve", help="Start RAGpilot as a server (MCP over stdio).")(serve.serve)
app.command(
    "install-agent", help="Print (and optionally write) the MCP client config snippet."
)(install_agent.install_agent)


if __name__ == "__main__":
    app()
