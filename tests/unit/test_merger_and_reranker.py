"""Unit tests for ``retrieval/merger.py`` and ``retrieval/reranker.py``
(blueprint sections 21/22): dedup-by-``(kind, id)`` across lexical and
semantic evidence, and a final ranking that never lets a semantic score
outrank even the weakest lexical tier.
"""

from __future__ import annotations

from ragpilot.retrieval.lexical import RankTier, SearchResult
from ragpilot.retrieval.merger import merge
from ragpilot.retrieval.reranker import rerank
from ragpilot.retrieval.semantic import SemanticHit


def _lexical(kind: str, id_: str, tier: RankTier, **kwargs: object) -> SearchResult:
    return SearchResult(
        kind=kind, tier=tier, id=id_, title=id_, path=f"/{id_}", source_id="s1", **kwargs
    )


def _semantic(kind: str, id_: str, score: float) -> SemanticHit:
    return SemanticHit(kind=kind, id=id_, title=id_, path=f"/{id_}", source_id="s1", score=score)


def test_merge_combines_a_hit_found_by_both_signals() -> None:
    lexical_results = [_lexical("entity", "e1", RankTier.FTS)]
    semantic_hits = [_semantic("entity", "e1", 0.9)]
    candidates = merge(lexical_results, semantic_hits)
    assert len(candidates) == 1
    assert candidates[0].lexical_tier == RankTier.FTS
    assert candidates[0].semantic_score == 0.9


def test_merge_keeps_semantic_only_hits_separate() -> None:
    lexical_results = [_lexical("entity", "e1", RankTier.EXACT_SYMBOL)]
    semantic_hits = [_semantic("entity", "e2", 0.5)]
    candidates = merge(lexical_results, semantic_hits)
    by_id = {c.id: c for c in candidates}
    assert by_id["e1"].semantic_score is None
    assert by_id["e2"].lexical_tier is None


def test_rerank_never_lets_semantic_outrank_a_lexical_tier() -> None:
    lexical_results = [_lexical("entity", "e_weak", RankTier.PATH)]
    semantic_hits = [_semantic("entity", "e_strong_semantic", 0.99)]
    candidates = merge(lexical_results, semantic_hits)
    ranked = rerank(candidates, limit=10)
    assert [h.candidate.id for h in ranked] == ["e_weak", "e_strong_semantic"]
    assert ranked[0].tier_label == "path"
    assert ranked[1].tier_label == "semantic_only"


def test_rerank_orders_semantic_only_hits_by_score_descending() -> None:
    semantic_hits = [
        _semantic("entity", "low", 0.1),
        _semantic("entity", "high", 0.9),
        _semantic("entity", "mid", 0.5),
    ]
    candidates = merge([], semantic_hits)
    ranked = rerank(candidates, limit=10)
    assert [h.candidate.id for h in ranked] == ["high", "mid", "low"]


def test_rerank_preserves_lexical_tier_ordering_among_lexical_hits() -> None:
    lexical_results = [
        _lexical("entity", "e_fts", RankTier.FTS),
        _lexical("entity", "e_exact", RankTier.EXACT_SYMBOL),
    ]
    candidates = merge(lexical_results, [])
    ranked = rerank(candidates, limit=10)
    assert [h.candidate.id for h in ranked] == ["e_exact", "e_fts"]


def test_rerank_respects_limit() -> None:
    semantic_hits = [_semantic("entity", f"e{i}", float(i)) for i in range(5)]
    candidates = merge([], semantic_hits)
    ranked = rerank(candidates, limit=2)
    assert len(ranked) == 2
    assert ranked[0].candidate.id == "e4"


def test_ranked_hit_to_dict_shape() -> None:
    candidates = merge([_lexical("entity", "e1", RankTier.EXACT_SYMBOL)], [])
    ranked = rerank(candidates, limit=10)
    payload = ranked[0].to_dict()
    assert payload["kind"] == "entity"
    assert payload["id"] == "e1"
    assert payload["tier"] == "exact_symbol"
    assert payload["semantic_score"] is None
