"""The blueprint's eight benchmark query categories (section 35), built
against a ``corpus.GeneratedCorpus``'s ``KnownFixtures`` so every query
has a guaranteed correct hit regardless of corpus size.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from benchmarks.search.corpus import GeneratedCorpus


class SearchMode(StrEnum):
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class BenchmarkQuery:
    category: str
    text: str
    mode: SearchMode


def build_queries(corpus: GeneratedCorpus) -> list[BenchmarkQuery]:
    known = corpus.known
    return [
        BenchmarkQuery("exact_symbol", known.entity_name, SearchMode.LEXICAL),
        BenchmarkQuery("qualified_symbol", known.entity_qualified_name, SearchMode.LEXICAL),
        BenchmarkQuery("alias", known.entity_alias, SearchMode.LEXICAL),
        BenchmarkQuery("file_path", known.path_fragment, SearchMode.LEXICAL),
        BenchmarkQuery("single_keyword", "settlement", SearchMode.LEXICAL),
        BenchmarkQuery("multi_keyword", "settlement retry timeout", SearchMode.LEXICAL),
        BenchmarkQuery(
            "conceptual",
            "how are provider settlements retried when a payment times out",
            SearchMode.SEMANTIC,
        ),
        BenchmarkQuery("hybrid", "settlement retry behavior", SearchMode.HYBRID),
    ]
