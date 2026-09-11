"""Retrieval quality metrics (blueprint section 37): binary-relevance
Recall@K, Mean Reciprocal Rank, and Normalized Discounted Cumulative
Gain, computed over a ranked list of result keys against a set of
relevant keys. Used by the golden-query regression tests
(``tests/unit/test_search_quality.py``) rather than the latency
benchmark (``runner.py``), which measures speed, not correctness.
"""

from __future__ import annotations

import math


def result_key(kind: str, identifier: str) -> str:
    """A stable key for one search hit, used to compare a ranked result
    list against a golden query's expected relevant set. Deliberately
    ``(kind, path-or-title)`` rather than a result's own ``id``: entity/
    document ids are freshly generated (often UUIDs) each time a fixture
    project is indexed, but a fixture's file paths and titles are fixed
    by the test itself.
    """
    return f"{kind}:{identifier}"


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Fraction of ``relevant`` found within the top ``k`` of
    ``retrieved``. ``1.0`` when there is nothing to find (an empty
    ``relevant`` set is vacuously fully recalled), matching this
    project's existing "don't invent a signal that isn't there"
    convention rather than raising or returning 0.
    """
    if not relevant:
        return 1.0
    top_k = set(retrieved[:k])
    return len(top_k & relevant) / len(relevant)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    """``1 / rank`` of the first relevant item found, ``0.0`` if none of
    ``retrieved`` is relevant. The building block of Mean Reciprocal
    Rank across a golden query set -- MRR itself is just the mean of
    this value over every query, computed by the caller.
    """
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def _discounted_gain_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Only a relevant item's *first* occurrence contributes gain: two
    search hits that key to the same relevant item (e.g. two distinct
    entities retrieved from the same relevant file) represent one piece
    of found information, not two -- counting every occurrence would let
    a single relevant target inflate NDCG past its ``[0, 1]`` bound.
    """
    seen: set[str] = set()
    gain = 0.0
    for rank, item in enumerate(retrieved[:k], start=1):
        if item in relevant and item not in seen:
            gain += 1.0 / math.log2(rank + 1)
            seen.add(item)
    return gain


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Normalized Discounted Cumulative Gain at ``k``, binary relevance
    (every relevant item contributes gain ``1``, not a graded score --
    this project's golden queries only ever mark something relevant or
    not). ``1.0`` when there is nothing to find, matching ``recall_at_k``.
    """
    if not relevant:
        return 1.0
    dcg = _discounted_gain_at_k(retrieved, relevant, k)
    ideal_hits = min(len(relevant), k)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / ideal_dcg if ideal_dcg > 0 else 1.0
