"""Assembles a budgeted, deduplicated evidence package (blueprint section
27) for a retrieval caller -- ``explore`` now, Phase 6's MCP tools later.

A pure function over already-fetched ``Evidence``/``GraphPath`` values,
with no database access of its own: every caller already has to look up
entities/relationships/documents to build an ``Evidence`` object in the
first place (``knowledge/evidence.py``), so this module's only job is
dedup + priority + budget, not another round of storage reads. That also
makes it trivially unit-testable without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ragpilot.core.config import ContextConfig
from ragpilot.knowledge import confidence as confidence_rank
from ragpilot.knowledge.evidence import Evidence

_LocationKey = tuple[str, Any, Any, Any, Any]


@dataclass(frozen=True)
class EvidenceItem:
    """An ``Evidence`` fact plus the source snippet that lets a reader
    actually interpret it (blueprint step 7: "preserve enough source for
    interpretation") -- ``Evidence`` itself carries only location/
    provenance, never text, so the snippet travels alongside it rather
    than inside it.
    """

    evidence: Evidence
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = self.evidence.to_dict()
        payload["snippet"] = self.snippet
        return payload


@dataclass(frozen=True)
class GraphPath:
    """One relationship hop rendered as ``A -[REL]-> B``, not just the
    two bare endpoints -- blueprint step 5, "include graph paths (how A
    relates to B), not just the endpoints".
    """

    source: str
    relationship: str
    target: str
    confidence: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "relationship": self.relationship,
            "target": self.target,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ContextResult:
    evidence: list[dict[str, Any]]
    graph_paths: list[dict[str, str]]
    truncated: bool
    truncation_reasons: list[str]
    total_chars: int
    file_count: int
    graph_node_count: int


def _location_key(item: EvidenceItem) -> _LocationKey:
    loc = item.evidence.location
    return (item.evidence.path, loc.line_start, loc.line_end, loc.page, loc.section)


def _dedupe(items: list[EvidenceItem]) -> list[EvidenceItem]:
    """Blueprint step 1: the same file/location shouldn't appear twice.
    When two items share a location, the higher-confidence one wins;
    ties keep whichever came first, so the result is deterministic for a
    given, already-deterministic input order.
    """
    best: dict[_LocationKey, EvidenceItem] = {}
    order: list[_LocationKey] = []
    for item in items:
        key = _location_key(item)
        current = best.get(key)
        if current is None:
            order.append(key)
            best[key] = item
        elif confidence_rank.rank(item.evidence.confidence) > confidence_rank.rank(
            current.evidence.confidence
        ):
            best[key] = item
    return [best[key] for key in order]


def _none_last(value: Any) -> tuple[int, Any]:
    return (1, 0) if value is None else (0, value)


def _priority_key(item: EvidenceItem) -> tuple[Any, ...]:
    """Blueprint step 3: exact evidence before heuristic. Sorted by
    confidence rank descending, then deterministically by location/entity
    so equally-confident items always truncate in the same order across
    runs.
    """
    loc = item.evidence.location
    return (
        -confidence_rank.rank(item.evidence.confidence),
        item.evidence.path,
        _none_last(loc.line_start),
        _none_last(loc.page),
        item.evidence.entity,
    )


def build_context(
    items: list[EvidenceItem],
    graph_paths: list[GraphPath],
    *,
    budget: ContextConfig,
) -> ContextResult:
    """Dedupes, priority-sorts, then caps ``items`` to ``budget.max_files``
    distinct files and ``budget.max_chars`` total snippet characters, and
    caps ``graph_paths`` to ``budget.max_graph_nodes`` distinct endpoints
    -- truncation is explicit (``ContextResult.truncated``/
    ``truncation_reasons``), never a silent drop.

    Only snippet text counts toward ``max_chars``: it is the actual bulk
    of an evidence item's payload and the one thing that varies widely in
    size, whereas the small fixed fields (path/entity/confidence) are
    kept regardless so a truncated-to-zero-snippet item is still
    traceable to its source.
    """
    ordered = sorted(_dedupe(items), key=_priority_key)

    included: list[EvidenceItem] = []
    included_files: set[str] = set()
    total_chars = 0
    files_exceeded = False
    chars_exceeded = False

    for item in ordered:
        is_new_file = item.evidence.path not in included_files
        if is_new_file and len(included_files) >= budget.max_files:
            files_exceeded = True
            continue
        item_chars = len(item.snippet)
        if total_chars + item_chars > budget.max_chars:
            chars_exceeded = True
            continue
        included.append(item)
        included_files.add(item.evidence.path)
        total_chars += item_chars

    included_graph: list[GraphPath] = []
    nodes: set[str] = set()
    graph_exceeded = False
    for path in graph_paths:
        candidate_nodes = nodes | {path.source, path.target}
        if len(candidate_nodes) > budget.max_graph_nodes:
            graph_exceeded = True
            continue
        nodes = candidate_nodes
        included_graph.append(path)

    reasons: list[str] = []
    if files_exceeded:
        reasons.append(f"evidence truncated: max_files={budget.max_files} reached")
    if chars_exceeded:
        reasons.append(f"evidence truncated: max_chars={budget.max_chars} reached")
    if graph_exceeded:
        reasons.append(f"graph paths truncated: max_graph_nodes={budget.max_graph_nodes} reached")

    return ContextResult(
        evidence=[item.to_dict() for item in included],
        graph_paths=[path.to_dict() for path in included_graph],
        truncated=bool(reasons),
        truncation_reasons=reasons,
        total_chars=total_chars,
        file_count=len(included_files),
        graph_node_count=len(nodes),
    )
