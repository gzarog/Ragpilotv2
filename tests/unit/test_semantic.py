"""``retrieval/semantic.py`` is a seam, not an implementation: proves it
never crashes while disabled (the Phase 5 default) and fails loudly, with
a specific type, if ever invoked while enabled.
"""

from __future__ import annotations

import pytest

from ragpilot.core.config import SearchConfig
from ragpilot.retrieval.semantic import SemanticSearchNotImplementedError, semantic_search


def test_disabled_semantic_search_returns_a_skipped_result() -> None:
    result = semantic_search("anything", config=SearchConfig(semantic=False))
    assert result.available is False
    assert result.results == ()
    assert "disabled" in result.reason


def test_enabled_semantic_search_raises_the_typed_not_implemented_error() -> None:
    with pytest.raises(SemanticSearchNotImplementedError):
        semantic_search("anything", config=SearchConfig(semantic=True))
