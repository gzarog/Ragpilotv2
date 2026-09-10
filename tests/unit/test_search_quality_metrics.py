"""Unit tests for ``benchmarks/search/quality.py``'s Recall@K/MRR/NDCG
formulas (blueprint section 37), independent of any real search call.
"""

from __future__ import annotations

import pytest
from benchmarks.search.quality import ndcg_at_k, recall_at_k, reciprocal_rank, result_key


def test_result_key_combines_kind_and_identifier() -> None:
    assert result_key("entity", "pkg.Dog") == "entity:pkg.Dog"


def test_recall_at_k_full_recall_when_all_relevant_are_in_top_k() -> None:
    retrieved = ["a", "b", "c", "d"]
    assert recall_at_k(retrieved, {"a", "c"}, k=4) == 1.0


def test_recall_at_k_partial_recall_when_relevant_falls_outside_k() -> None:
    retrieved = ["a", "b", "c", "d"]
    assert recall_at_k(retrieved, {"a", "z"}, k=2) == pytest.approx(0.5)


def test_recall_at_k_zero_when_nothing_relevant_is_retrieved() -> None:
    assert recall_at_k(["a", "b"], {"z"}, k=2) == 0.0


def test_recall_at_k_is_one_when_nothing_is_relevant() -> None:
    assert recall_at_k(["a", "b"], set(), k=2) == 1.0


def test_reciprocal_rank_of_first_position() -> None:
    assert reciprocal_rank(["a", "b"], {"a"}) == pytest.approx(1.0)


def test_reciprocal_rank_of_third_position() -> None:
    assert reciprocal_rank(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)


def test_reciprocal_rank_is_zero_when_never_found() -> None:
    assert reciprocal_rank(["x", "y"], {"a"}) == 0.0


def test_ndcg_is_one_for_a_perfectly_ranked_list() -> None:
    assert ndcg_at_k(["a", "b"], {"a", "b"}, k=2) == pytest.approx(1.0)


def test_ndcg_penalizes_relevant_items_ranked_lower() -> None:
    ideal = ndcg_at_k(["a", "b", "x"], {"a", "b"}, k=3)
    worse = ndcg_at_k(["x", "a", "b"], {"a", "b"}, k=3)
    assert worse < ideal
    assert ideal == pytest.approx(1.0)


def test_ndcg_is_zero_when_nothing_relevant_is_retrieved() -> None:
    assert ndcg_at_k(["x", "y"], {"a"}, k=2) == 0.0


def test_ndcg_is_one_when_nothing_is_relevant() -> None:
    assert ndcg_at_k(["x", "y"], set(), k=2) == 1.0


def test_ndcg_never_exceeds_one_when_a_relevant_key_repeats() -> None:
    """A repeated key (e.g. two distinct entities retrieved from the same
    relevant file, both mapped to that file's key) must count as finding
    that one relevant item once, not once per occurrence -- otherwise
    NDCG could exceed its [0, 1] bound.
    """
    retrieved = ["a", "a", "a", "a"]
    assert ndcg_at_k(retrieved, {"a"}, k=4) == pytest.approx(1.0)
