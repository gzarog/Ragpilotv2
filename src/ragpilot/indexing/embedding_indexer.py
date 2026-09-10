"""Computes and stores Phase 9 embeddings for touched files, mirroring
``knowledge/linker.py``'s ``link_touched_files`` shape and scoping:

Run once per source pass, after the per-file processor queue has fully
drained (``indexing/runner.py``), scoped to files touched *this run*
only -- embedding every entity/document section in the whole project on
every single ``ragpilot index`` would be O(all content) regardless of how
little changed, the exact cost problem ``link_touched_files`` already
rejected for the same reason. One accepted consequence, mirroring
``link_touched_files``'s own documented tradeoff: freshly turning on
``search.semantic`` for an *already-indexed, otherwise-unchanged* project
computes no embeddings until something actually touches those files
again -- ``ragpilot rebuild`` (every file becomes "new", hence touched)
is the documented way to force a full backfill, rather than this module
growing a second, whole-project code path.

Gated entirely behind ``search.semantic`` by its one caller
(``indexing/runner.py``): enabling that config is the single switch that
turns on both computing embeddings here and using them in
``retrieval/semantic.py``, never one without the other.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Sequence

from ragpilot.core.models import EmbeddingSubjectType, Entity
from ragpilot.retrieval import embedder
from ragpilot.storage.repositories import documents_repo, embeddings_repo, entities_repo
from ragpilot.telemetry.logging import get_logger, log_event

_logger = get_logger("embeddings")


def _entity_text(entity: Entity) -> str:
    return entity.signature or entity.qualified_name


def embed_touched_files(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    touched_code_file_ids: Sequence[str],
    touched_document_file_ids: Sequence[str],
) -> int:
    """Embeds every non-empty-text entity/document-section belonging to a
    touched file, replacing that file's previous embeddings generation
    (any model) in the same caller-held transaction -- run inside the
    same ``with transaction(conn):`` block as the rest of one source
    pass's writes, matching ``link_touched_files``.

    Returns the number of vectors stored. Never raises for a missing or
    unloadable embedding model: it logs and returns ``0`` instead, so
    ``search.semantic`` being on can never turn an ordinary ``ragpilot
    index`` run into a hard failure -- semantic search just stays
    unavailable until the model loads (see ``retrieval/semantic.py``).
    """
    if not touched_code_file_ids and not touched_document_file_ids:
        return 0

    subjects: list[tuple[EmbeddingSubjectType, str, str, str]] = []
    for file_id in touched_code_file_ids:
        for entity in entities_repo.list_by_file(conn, file_id):
            text = _entity_text(entity)
            if text.strip():
                subjects.append((EmbeddingSubjectType.ENTITY, entity.id, file_id, text))
    for file_id in touched_document_file_ids:
        for unit in documents_repo.list_units_by_file(conn, file_id):
            if unit.text.strip():
                subjects.append(
                    (EmbeddingSubjectType.DOCUMENT_SECTION, unit.id, file_id, unit.text)
                )

    if not subjects:
        return 0

    try:
        vectors = embedder.embed_texts([s[3] for s in subjects])
    except embedder.EmbeddingModelUnavailableError as exc:
        log_event(
            _logger,
            "embedding_model_unavailable",
            level=logging.WARNING,
            source_id=source_id,
            error=str(exc),
        )
        return 0

    touched_files = set(touched_code_file_ids) | set(touched_document_file_ids)
    for file_id in touched_files:
        embeddings_repo.delete_by_file(conn, file_id)

    for (subject_type, subject_id, file_id, _text), vector in zip(subjects, vectors, strict=True):
        embeddings_repo.insert(
            conn,
            subject_type=subject_type,
            subject_id=subject_id,
            file_id=file_id,
            source_id=source_id,
            model_id=embedder.EMBEDDING_MODEL_ID,
            vector=vector,
        )

    log_event(
        _logger,
        "embeddings_computed",
        source_id=source_id,
        count=len(subjects),
    )
    return len(subjects)
