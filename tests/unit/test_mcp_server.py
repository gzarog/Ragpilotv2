"""``mcp/server.py``'s ``build_server`` -- pure construction, no stdio/
sockets, so it is exercised directly rather than through a real client.
"""

from __future__ import annotations

import asyncio

from ragpilot import __version__
from ragpilot.mcp.server import build_server

EXPECTED_TOOL_NAMES = {
    "ragpilot_explore",
    "ragpilot_search",
    "ragpilot_symbol",
    "ragpilot_callers",
    "ragpilot_callees",
    "ragpilot_impact",
    "ragpilot_documents",
    "ragpilot_status",
}


def test_build_server_registers_all_eight_tools() -> None:
    server = build_server()

    tool_list = asyncio.run(server.list_tools())
    names = {tool.name for tool in tool_list}

    assert names == EXPECTED_TOOL_NAMES


def test_build_server_carries_version_and_readonly_annotations() -> None:
    server = build_server()

    assert __version__ in server.name
    assert server.instructions is not None
    assert "ragpilot_explore" in server.instructions

    tool_list = asyncio.run(server.list_tools())
    for tool in tool_list:
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False


def test_explore_is_marked_as_the_primary_tool_in_its_description() -> None:
    server = build_server()
    tool_list = asyncio.run(server.list_tools())
    explore = next(t for t in tool_list if t.name == "ragpilot_explore")

    assert explore.description is not None
    assert "primary" in explore.description.lower()
