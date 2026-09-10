"""Builds the stdio MCP server (blueprint: "MCP over stdio as the default
agent transport, no external listening port"). ``build_server`` is pure
construction -- no I/O, no blocking loop -- so it is unit-testable on its
own; ``run_stdio`` is the actual blocking entrypoint ``cli/serve.py`` calls.

Uses the high-level ``mcp.server.fastmcp.FastMCP`` API: decorator/registry-
style tool registration with input/output schemas derived from typed
Python signatures and the ``schemas.py`` Pydantic models, rather than the
low-level ``mcp.server.lowlevel.Server`` API's hand-written JSON-RPC
handlers -- simpler and directly testable (a FastMCP tool is just the
underlying Python coroutine, see ``mcp/tools.py``'s docstring).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ragpilot import __version__

from . import tools

INSTRUCTIONS = (
    "RAGpilot exposes code and document knowledge already indexed locally "
    "on this machine (see `ragpilot index`). Start with ragpilot_explore "
    "for a natural-language or identifier query -- it is the primary tool "
    "and runs RAGpilot's deterministic query planner. The other tools "
    "(ragpilot_search/symbol/callers/callees/impact/documents/status) are "
    "narrower, single-purpose lookups. Every tool is read-only, returns a "
    "bounded, versioned JSON result (schema_version/ok/error), and never "
    "calls an LLM or the network -- results are retrieved/structured data "
    "for the calling agent to reason over."
)

# All 8 tools only read the local index -- never write, never touch the
# network -- so one shared annotation set covers every registration below.
_READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)

_TOOLS: tuple[tuple[str, str], ...] = (
    (
        "ragpilot_explore",
        "Primary retrieval tool: plan + run the best deterministic strategies for a "
        "query and assemble a budgeted evidence package.",
    ),
    ("ragpilot_search", "Lexical search across indexed code and documents."),
    ("ragpilot_symbol", "Look up a code symbol by name or fully qualified name."),
    ("ragpilot_callers", "List entities that call the given symbol (incoming CALLS edges)."),
    ("ragpilot_callees", "List entities the given symbol calls (outgoing CALLS edges)."),
    (
        "ragpilot_impact",
        "Blast-radius impact analysis for a symbol: callers, callees, tests, documentation.",
    ),
    ("ragpilot_documents", "List indexed documents, optionally filtered to one source."),
    ("ragpilot_status", "Indexing status: sources, per-status file counts, queue depth."),
)


def build_server() -> FastMCP:
    """Constructs the FastMCP server and registers all 8 tools. Pure and
    side-effect free (no stdio, no sockets) so tests can call it directly.
    """
    server = FastMCP(name=f"ragpilot v{__version__}", instructions=INSTRUCTIONS)
    for tool_name, description in _TOOLS:
        server.add_tool(
            getattr(tools, tool_name),
            name=tool_name,
            description=description,
            annotations=_READ_ONLY,
        )
    return server


def run_stdio() -> None:
    """Blocks running the stdio MCP server loop. Not covered by tests
    (would require a real client speaking JSON-RPC over stdio); ``cli/
    serve.py`` is the only caller, kept as this one thin, deliberately
    untested line so ``build_server``'s construction stays testable
    in isolation.
    """
    build_server().run(transport="stdio")
