"""Seam for Phase 9's real semantic/vector search.

Nothing here does embeddings or vector math -- this module exists solely
so ``planner.py`` (and later Phase 6's MCP tools) have one stable place to
ask "is semantic search available" and get a well-typed, never-crashing
answer, per the blueprint's AI-optional principle: no part of Phase 5 may
depend on this actually returning results. ``search.semantic`` already
defaults to ``False`` (``core/config.py``), so the only path exercised
today is the disabled one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ragpilot.core.config import SearchConfig


class SemanticSearchNotImplementedError(NotImplementedError):
    """Raised only if something calls ``semantic_search`` while
    ``search.semantic`` is enabled. A specific, catchable type rather
    than a bare ``NotImplementedError`` so a future caller can tell "not
    implemented yet" apart from an ordinary programming bug.
    """


@dataclass(frozen=True)
class SemanticSearchResult:
    available: bool
    reason: str
    results: tuple[object, ...] = field(default_factory=tuple)


def semantic_search(
    query: str, *, config: SearchConfig, limit: int = 20
) -> SemanticSearchResult:
    """Returns a skipped result while semantic search is disabled (the
    Phase 5 default); raises ``SemanticSearchNotImplementedError`` if
    ever called with it enabled, since implementing it is Phase 9's job,
    not something Phase 5 should silently fake.
    """
    del query, limit
    if not config.semantic:
        return SemanticSearchResult(available=False, reason="search.semantic is disabled")
    raise SemanticSearchNotImplementedError(
        "search.semantic is enabled but semantic search is not implemented until Phase 9"
    )
