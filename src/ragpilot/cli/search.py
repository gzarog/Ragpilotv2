"""``ragpilot search QUERY [--limit N] [--json] [--explain]``."""

from __future__ import annotations

import time
from typing import Annotated

import typer
from rich.table import Table

from ragpilot.core.lifecycle import AppContext
from ragpilot.retrieval import lexical, query_classifier, semantic

from ._common import cli_command, console, print_json


@cli_command
def search(
    query: Annotated[
        str, typer.Argument(help="Identifier, phrase, or path fragment to search for.")
    ],
    limit: Annotated[int, typer.Option("--limit", min=1, max=200)] = lexical.DEFAULT_LIMIT,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    explain: Annotated[
        bool, typer.Option("--explain", help="Show per-stage timing diagnostics.")
    ] = False,
) -> None:
    with AppContext.bootstrap() as ctx:
        search_config = ctx.config.search
        timed = lexical.search_with_timings(ctx, query, limit=limit)
        results = timed.results
        timings = list(timed.timings)

        # Blueprint section 18: when ``lazy_semantic`` is on, a
        # high-confidence lexical hit (exact/qualified/alias symbol, or
        # an exact title match) skips semantic search entirely --
        # off by default, since ``search.semantic``'s existing contract
        # is "always attach a semantic section when this is on" (see
        # ``SearchConfig.lazy_semantic``'s docstring).
        confidence = query_classifier.estimate_confidence(results)
        run_semantic = search_config.semantic and not (
            search_config.lazy_semantic and confidence == query_classifier.SearchConfidence.HIGH
        )

        # Only called (and only imports torch/transformers, see
        # retrieval/embedder.py) when semantic search actually needs to
        # run -- the default, disabled path behaves exactly like Phase 5
        # left it. Kept as its own section rather than merged into
        # ``results`` above: a similarity score is a distinct signal
        # from lexical rank, never mixed into the same ranked list (see
        # retrieval/semantic.py's docstring).
        semantic_result = None
        if run_semantic:
            started = time.perf_counter()
            semantic_result = semantic.semantic_search(
                ctx,
                query,
                config=search_config,
                limit=limit,
                candidate_k=search_config.semantic_top_k,
            )
            timings.append(
                lexical.StageTiming(
                    name="semantic",
                    hits=len(semantic_result.results),
                    duration_ms=(time.perf_counter() - started) * 1000,
                )
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
            if explain:
                payload["explain"] = {
                    "query_kind": query_classifier.classify_query(query).value,
                    "lexical_confidence": confidence.value,
                    "semantic_skipped": search_config.semantic and not run_semantic,
                    "stages": [t.to_dict() for t in timings],
                    "total_ms": round(sum(t.duration_ms for t in timings), 3),
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
        elif search_config.semantic:
            console.print(
                f"[dim]Semantic search skipped: lexical confidence is {confidence.value}.[/dim]"
            )

        if explain:
            console.print(
                f"[bold]Query kind:[/bold] {query_classifier.classify_query(query).value}  "
                f"[bold]Lexical confidence:[/bold] {confidence.value}"
            )
            explain_table = Table("Stage", "Hits", "Duration (ms)")
            for t in timings:
                explain_table.add_row(t.name, str(t.hits), f"{t.duration_ms:.3f}")
            console.print(explain_table)
            console.print(f"[bold]Total:[/bold] {sum(t.duration_ms for t in timings):.3f} ms")
