"""Real semantic/vector search (Phase 9), completing the seam
``planner.py`` has called into since Phase 5.

Embeds the query with the same model used to embed indexed content
(``retrieval/embedder.py``), scores it against every current-model
embedding in the project via brute-force cosine similarity
(``retrieval/vectorstore.py``), and returns ranked hits in a shape
deliberately close to ``retrieval/lexical.py``'s ``SearchResult`` --
``kind``/``id``/``title``/``path``/``source_id``/``snippet``/``location``
line up field-for-field so a caller can render or evidence-ify a
``SemanticHit`` the same way it already does a lexical hit, plus one
extra ``score`` field lexical results have no equivalent of. It stays a
distinct type rather than literally reusing ``SearchResult``: a
similarity score is not a ``RankTier``, and blueprint section 57/19 is
explicit that semantic similarity must never be folded into or upgrade a
lexical/graph confidence tier -- keeping it a separate type is what makes
"never silently mixed in" structurally true rather than a convention
callers have to remember.

Never crashes ``explore``/``search`` if semantic search is unavailable
for any reason (disabled, embedding model can't load, no embeddings
computed yet) -- every failure path returns
``SemanticSearchResult(available=False, reason=...)`` instead of raising,
per the blueprint's AI-optional principle Phase 5 already established for
this exact seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ragpilot.code.graph import all_project_connections
from ragpilot.core.config import SearchConfig
from ragpilot.core.lifecycle import AppContext
from ragpilot.core.models import EmbeddingSubjectType
from ragpilot.retrieval import embedder, vectorstore
from ragpilot.storage.repositories import documents_repo, embeddings_repo, entities_repo, files_repo
from ragpilot.storage.repositories.embeddings_repo import EmbeddingRow

DEFAULT_LIMIT = 15


@dataclass(frozen=True)
class SemanticHit:
    kind: str  # "entity" | "document"
    id: str
    title: str
    path: str
    source_id: str
    score: float
    snippet: str = ""
    location: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "tier": "semantic",
            "id": self.id,
            "title": self.title,
            "path": self.path,
            "source_id": self.source_id,
            "snippet": self.snippet,
            "location": self.location,
            "score": round(self.score, 4),
        }


@dataclass(frozen=True)
class SemanticSearchResult:
    available: bool
    reason: str
    results: tuple[SemanticHit, ...] = field(default_factory=tuple)


def _hit_from_row(conn: Any, source_id: str, row: EmbeddingRow, score: float) -> SemanticHit | None:
    if row.subject_type is EmbeddingSubjectType.ENTITY:
        entity = entities_repo.get(conn, row.subject_id)
        if entity is None:
            return None
        file = files_repo.get(conn, entity.file_id)
        return SemanticHit(
            kind="entity",
            id=entity.id,
            title=entity.qualified_name,
            path=file.path if file is not None else entity.file_id,
            source_id=source_id,
            score=score,
            snippet=entity.signature or entity.qualified_name,
            location={"line_start": entity.start_line, "line_end": entity.end_line},
        )

    unit = documents_repo.get_unit(conn, row.subject_id)
    if unit is None:
        return None
    file = files_repo.get(conn, unit.file_id)
    document = documents_repo.get_document(conn, unit.document_id)
    title = (document.title if document is not None and document.title else None) or (
        file.path if file is not None else unit.file_id
    )
    return SemanticHit(
        kind="document",
        id=unit.id,
        title=title,
        path=file.path if file is not None else unit.file_id,
        source_id=source_id,
        score=score,
        snippet=unit.text[:280],
        location={"section": " > ".join(unit.heading_path) if unit.heading_path else None},
    )


def semantic_search(
    ctx: AppContext,
    query: str,
    *,
    config: SearchConfig,
    limit: int = DEFAULT_LIMIT,
    candidate_k: int | None = None,
) -> SemanticSearchResult:
    """Returns a skipped/unavailable result rather than raising whenever
    semantic search cannot actually run right now -- see the module
    docstring. Only ever called with ``config.semantic`` true by
    ``explore``/``search`` (both check first so the default, disabled
    path never even imports ``torch``/``transformers`` -- see
    ``retrieval/embedder.py``), but re-checked here too since this is the
    one function that could otherwise silently do real ML work.

    ``candidate_k`` (blueprint section 20's candidate budget) sizes the
    internal nearest-neighbor search independently of ``limit``, the
    final number of results returned -- defaults to ``limit`` itself when
    omitted, i.e. today's behavior of "fetch and return the same count".
    """
    query = query.strip()
    if not config.semantic:
        return SemanticSearchResult(available=False, reason="search.semantic is disabled")
    if not query:
        return SemanticSearchResult(available=True, reason="empty query", results=())

    try:
        query_vector = embedder.embed_texts([query])[0]
    except embedder.EmbeddingModelUnavailableError as exc:
        return SemanticSearchResult(
            available=False, reason=f"embedding model unavailable: {exc}", results=()
        )

    connections = {source_id: conn for source_id, _path, conn in all_project_connections(ctx)}
    k = candidate_k if candidate_k is not None else limit

    scored: list[tuple[str, EmbeddingRow, float]] = []
    for source_id, conn in connections.items():
        rows = embeddings_repo.list_by_model(conn, embedder.EMBEDDING_MODEL_ID)
        if not rows:
            continue
        candidates = [(row.id, row.vector) for row in rows]
        by_id = {row.id: row for row in rows}
        for candidate in vectorstore.top_k(query_vector, candidates, k=k):
            scored.append((source_id, by_id[candidate.key], candidate.score))

    if not scored:
        return SemanticSearchResult(
            available=True, reason="no embeddings computed for this project yet", results=()
        )

    hits: list[SemanticHit] = []
    for source_id, row, score in scored:
        hit = _hit_from_row(connections[source_id], source_id, row, score)
        if hit is not None:
            hits.append(hit)

    hits.sort(key=lambda h: (-h.score, h.path, h.id))
    return SemanticSearchResult(available=True, reason="ok", results=tuple(hits[:limit]))
