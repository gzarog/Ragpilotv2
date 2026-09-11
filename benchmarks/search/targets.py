"""Performance targets from the blueprint (section 36), grouped by the
same four buckets the blueprint itself groups them into. Each benchmark
query category (``queries.py``) maps to exactly one bucket.

These are meant to be measured "on normal developer hardware" (the
blueprint's own words) -- a shared/virtualized CI runner is neither
normal nor consistent hardware, so ``runner.py``'s automated pytest
coverage reports measured-vs-target as diagnostic output rather than a
hard pass/fail gate; ``python -m benchmarks.search --strict`` is the
form meant to actually enforce these on a real developer machine.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LatencyTarget:
    p50_ms: float
    p95_ms: float


TARGETS: dict[str, LatencyTarget] = {
    "exact_symbol": LatencyTarget(p50_ms=5, p95_ms=15),
    "lexical_fts": LatencyTarget(p50_ms=15, p95_ms=40),
    "semantic_ann": LatencyTarget(p50_ms=20, p95_ms=50),
    "hybrid": LatencyTarget(p50_ms=40, p95_ms=100),
}

# Maps each benchmark query category (``queries.build_queries``) to the
# target bucket it is judged against.
CATEGORY_TARGET_BUCKET: dict[str, str] = {
    "exact_symbol": "exact_symbol",
    "qualified_symbol": "exact_symbol",
    "alias": "exact_symbol",
    "file_path": "lexical_fts",
    "single_keyword": "lexical_fts",
    "multi_keyword": "lexical_fts",
    "conceptual": "semantic_ann",
    "hybrid": "hybrid",
}


def target_for(category: str) -> LatencyTarget:
    return TARGETS[CATEGORY_TARGET_BUCKET[category]]
