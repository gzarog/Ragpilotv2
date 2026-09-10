"""Lexical search: exact identifiers, ``code_fts``/``document_fts``, file
paths, document titles/headings, and qualified-name aliases, merged into
one ranked list for ``ragpilot search``.

Ranking and merging both live in this one module rather than a separate
``reranker.py``: there is exactly one signal-to-tier mapping and one
merge step in this phase, so splitting them would only add an import hop
with nothing left to decouple.

Ranking order, best first (blueprint order): exact symbol > qualified
symbol > title/heading match > FTS rank > path relevance > entity type >
recency > source priority. The first five are distinct ``RankTier``
values; "entity type"/"recency"/"source priority" have no dedicated
signal stored anywhere in Phases 1-4 to rank *across* tiers on, so they
are folded in as deterministic tie-breakers *within* a tier instead (see
``_sort_key``) -- entity kind via a fixed structural-to-narrow ordering,
recency via each result's file mtime, and source priority via the
registered source id (the closest thing to a priority Phase 1's registry
stores), rather than inventing configuration that doesn't exist yet.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ragpilot.code.graph import all_project_connections
from ragpilot.core.lifecycle import AppContext
from ragpilot.core.models import EntityType
from ragpilot.storage.repositories import documents_repo, entities_repo, files_repo

DEFAULT_LIMIT = 20

_ENTITY_KIND_RANK: dict[EntityType, int] = {
    kind: index
    for index, kind in enumerate(
        [
            EntityType.NAMESPACE,
            EntityType.CLASS,
            EntityType.INTERFACE,
            EntityType.STRUCT,
            EntityType.ENUM,
            EntityType.FUNCTION,
            EntityType.METHOD,
            EntityType.PROPERTY,
            EntityType.FIELD,
        ]
    )
}

# Mirrors knowledge/linker.py's ``match_alias``/``_MIN_ALIAS_SEGMENTS``:
# the qualified name's final two dotted segments, skipped below this many
# segments so the alias never just duplicates the qualified name itself.
_MIN_ALIAS_SEGMENTS = 3


class RankTier(IntEnum):
    EXACT_SYMBOL = 0
    QUALIFIED_SYMBOL = 1
    ALIAS_SYMBOL = 2
    TITLE_OR_HEADING = 3
    FTS = 4
    PATH = 5


@dataclass(frozen=True)
class SearchResult:
    kind: str  # "entity" | "document" | "path"
    tier: RankTier
    id: str
    title: str
    path: str
    source_id: str
    snippet: str | None = None
    location: dict[str, Any] | None = None
    fts_rank: int = 0
    entity_kind_rank: int = 99
    mtime: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "tier": self.tier.name.lower(),
            "id": self.id,
            "title": self.title,
            "path": self.path,
            "source_id": self.source_id,
            "snippet": self.snippet,
            "location": self.location,
        }


def _fts_query(text: str) -> str | None:
    """Builds a permissive FTS5 MATCH expression: each word token quoted
    (so punctuation in the query, e.g. "settlement.BetSettled", can never
    be parsed as FTS syntax) and OR'd together, favoring recall -- the
    ranking below is what narrows a broad FTS hit set back down, not the
    query itself.
    """
    tokens = re.findall(r"\w+", text)
    if not tokens:
        return None
    return " OR ".join(f'"{t}"' for t in tokens)


def _contains_ci(haystack: str | None, needle: str) -> bool:
    return haystack is not None and needle.lower() in haystack.lower()


def _alias(qualified_name: str) -> str | None:
    segments = qualified_name.split(".")
    if len(segments) < _MIN_ALIAS_SEGMENTS:
        return None
    return ".".join(segments[-2:])


def _sort_key(result: SearchResult) -> tuple[Any, ...]:
    return (
        result.tier,
        result.fts_rank,
        result.entity_kind_rank,
        -result.mtime,
        result.source_id,
        result.path,
        result.id,
    )


def _search_entities(
    conn: sqlite3.Connection, source_id: str, query: str, limit: int
) -> list[SearchResult]:
    results: list[SearchResult] = []
    exact_ids: set[str] = set()
    for entity in entities_repo.search(conn, query):
        exact_ids.add(entity.id)
        tier = RankTier.EXACT_SYMBOL if entity.name == query else RankTier.QUALIFIED_SYMBOL
        file = files_repo.get(conn, entity.file_id)
        results.append(
            SearchResult(
                kind="entity",
                tier=tier,
                id=entity.id,
                title=entity.qualified_name,
                path=file.path if file is not None else entity.file_id,
                source_id=source_id,
                snippet=entity.signature,
                location={"line_start": entity.start_line, "line_end": entity.end_line},
                entity_kind_rank=_ENTITY_KIND_RANK.get(entity.kind, 99),
                mtime=file.mtime if file is not None else 0.0,
            )
        )

    # Aliases are always the dotted "Class.member" shape (see
    # ``_alias``), so this extra full-corpus scan is only worth doing
    # when the query itself contains a dot -- bounding its cost to
    # queries that could plausibly benefit from it.
    if "." in query:
        for entity in entities_repo.list_all(conn):
            if entity.id in exact_ids:
                continue
            if _alias(entity.qualified_name) != query:
                continue
            file = files_repo.get(conn, entity.file_id)
            results.append(
                SearchResult(
                    kind="entity",
                    tier=RankTier.ALIAS_SYMBOL,
                    id=entity.id,
                    title=entity.qualified_name,
                    path=file.path if file is not None else entity.file_id,
                    source_id=source_id,
                    snippet=entity.signature,
                    location={"line_start": entity.start_line, "line_end": entity.end_line},
                    entity_kind_rank=_ENTITY_KIND_RANK.get(entity.kind, 99),
                    mtime=file.mtime if file is not None else 0.0,
                )
            )

    fts_query = _fts_query(query)
    if fts_query is not None:
        for rank, entity in enumerate(entities_repo.search_fts(conn, fts_query, limit=limit)):
            file = files_repo.get(conn, entity.file_id)
            results.append(
                SearchResult(
                    kind="entity",
                    tier=RankTier.FTS,
                    id=entity.id,
                    title=entity.qualified_name,
                    path=file.path if file is not None else entity.file_id,
                    source_id=source_id,
                    snippet=entity.signature,
                    location={"line_start": entity.start_line, "line_end": entity.end_line},
                    fts_rank=rank,
                    entity_kind_rank=_ENTITY_KIND_RANK.get(entity.kind, 99),
                    mtime=file.mtime if file is not None else 0.0,
                )
            )
    return results


def _search_documents(
    conn: sqlite3.Connection, source_id: str, query: str, limit: int
) -> list[SearchResult]:
    results: list[SearchResult] = []
    for document in documents_repo.list_all(conn):
        if document.title is not None and document.title.lower() == query.lower():
            file = files_repo.get(conn, document.file_id)
            results.append(
                SearchResult(
                    kind="document",
                    tier=RankTier.TITLE_OR_HEADING,
                    id=document.id,
                    title=document.title,
                    path=file.path if file is not None else document.file_id,
                    source_id=source_id,
                    snippet=document.title,
                    mtime=file.mtime if file is not None else 0.0,
                )
            )

    fts_query = _fts_query(query)
    if fts_query is None:
        return results
    for rank, row in enumerate(documents_repo.search_fts(conn, fts_query, limit=limit)):
        fts_document = documents_repo.get_document(conn, row["document_id"])
        if fts_document is None:
            continue
        document = fts_document
        file = files_repo.get(conn, document.file_id)
        heading = row["heading_text"] or ""
        body = row["body"] or ""
        doc_title = row["doc_title"] or document.title or ""
        tier = RankTier.TITLE_OR_HEADING if _contains_ci(heading, query) else RankTier.FTS
        results.append(
            SearchResult(
                kind="document",
                tier=tier,
                id=row["section_id"] or document.id,
                title=doc_title or (file.path if file is not None else document.id),
                path=file.path if file is not None else document.file_id,
                source_id=source_id,
                snippet=(body or heading)[:280] or None,
                location={"section": heading or None},
                fts_rank=rank,
                mtime=file.mtime if file is not None else 0.0,
            )
        )
    return results


def _search_paths(
    conn: sqlite3.Connection, source_id: str, query: str, limit: int
) -> list[SearchResult]:
    results: list[SearchResult] = []
    for file in files_repo.search_by_substring(conn, query, limit=limit):
        results.append(
            SearchResult(
                kind="path",
                tier=RankTier.PATH,
                id=file.id,
                title=file.path,
                path=file.path,
                source_id=source_id,
                mtime=file.mtime,
            )
        )
    return results


def _merge(results: list[SearchResult]) -> list[SearchResult]:
    """Same (kind, id) found through more than one signal (e.g. an exact
    name match that also showed up in FTS) keeps only its best-tiered
    hit -- this is both the dedup and the final ranking step.
    """
    best: dict[tuple[str, str], SearchResult] = {}
    for result in results:
        key = (result.kind, result.id)
        current = best.get(key)
        if current is None or _sort_key(result) < _sort_key(current):
            best[key] = result
    return sorted(best.values(), key=_sort_key)


def search(ctx: AppContext, query: str, *, limit: int = DEFAULT_LIMIT) -> list[SearchResult]:
    query = query.strip()
    if not query:
        return []
    collected: list[SearchResult] = []
    for source_id, _source_path, conn in all_project_connections(ctx):
        collected.extend(_search_entities(conn, source_id, query, limit))
        collected.extend(_search_documents(conn, source_id, query, limit))
        collected.extend(_search_paths(conn, source_id, query, limit))
    return _merge(collected)[:limit]
