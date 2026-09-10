"""``ragpilot references NAME [--max-depth N] [--limit N] [--json]``."""

from __future__ import annotations

from typing import Annotated

import typer

from ragpilot.code.graph import (
    DEFAULT_LIMIT,
    DEFAULT_MAX_DEPTH,
    TraversalEdge,
    conn_for_source_path,
    find_symbol_matches,
    traverse,
)
from ragpilot.core.lifecycle import AppContext
from ragpilot.core.models import RelationshipType

from ._code_common import edge_to_dict, match_to_dict, no_matches_message, render_edges_table
from ._common import cli_command, console, print_json

_REL_TYPES = (RelationshipType.CALLS, RelationshipType.IMPORTS, RelationshipType.REFERENCES)


@cli_command
def references(
    name: Annotated[str, typer.Argument(help="Symbol name or fully qualified name.")],
    max_depth: Annotated[int, typer.Option("--max-depth", min=1, max=10)] = DEFAULT_MAX_DEPTH,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = DEFAULT_LIMIT,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """All CALLS/IMPORTS/REFERENCES edges touching ``name``, either way."""
    with AppContext.bootstrap() as ctx:
        matches = find_symbol_matches(ctx, name)
        edges: list[TraversalEdge] = []
        for match in matches:
            conn = conn_for_source_path(ctx, match.source_path)
            edges.extend(
                traverse(
                    conn,
                    match.entity.id,
                    direction="incoming",
                    relationship_types=_REL_TYPES,
                    max_depth=max_depth,
                    limit=limit,
                )
            )
            edges.extend(
                traverse(
                    conn,
                    match.entity.id,
                    direction="outgoing",
                    relationship_types=_REL_TYPES,
                    max_depth=max_depth,
                    limit=limit,
                )
            )
        edges.sort(
            key=lambda e: (
                e.depth,
                e.relationship.relationship_type.value,
                e.relationship.target_entity_id or e.relationship.target_symbol or "",
                e.relationship.id,
            )
        )
        edges = edges[:limit]

        if json_output:
            print_json(
                {
                    "query": name,
                    "matches": [match_to_dict(m) for m in matches],
                    "edges": [edge_to_dict(e) for e in edges],
                }
            )
            return
        if not matches:
            console.print(f"[yellow]{no_matches_message(name)}[/yellow]")
            return
        render_edges_table(edges)
