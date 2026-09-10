"""End-to-end Phase 9 semantic retrieval: index a small project with
``search.semantic`` enabled, verify embeddings actually get computed and
stored, verify ``ragpilot search``/``ragpilot explore`` surface a
semantic-tier result distinctly from lexical/graph results, verify
behavior is unchanged with ``search.semantic`` left at its default
``false``, and verify graceful degradation when embeddings are missing/
cleared.

The real embedding model is never loaded here: ``retrieval/embedder.
embed_texts`` is monkeypatched to a small deterministic hash-based
function, keeping this test in the default, fast suite while still
exercising every real code path around it (indexing, storage, cosine
similarity, CLI wiring) -- see ``tests/unit/test_embedder.py`` /
CONTRIBUTING.md's ``embedding_model`` marker for the real-model tests.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragpilot.cli.main import app
from ragpilot.core import paths
from ragpilot.retrieval import embedder
from ragpilot.storage.repositories import embeddings_repo
from ragpilot.storage.sqlite import connect


def _fake_embed_texts(texts: list[str]) -> list[list[float]]:
    """Deterministic, dependency-free stand-in for the real model: each
    text hashes to a small fixed-dimension vector so semantically
    unrelated calls (e.g. a query vs. indexed content) still produce
    *some* non-degenerate cosine similarity structure to assert on,
    without needing torch/transformers or any real embedding math.
    """
    vectors: list[list[float]] = []
    for text in texts:
        digest = hashlib.sha256(text.lower().encode("utf-8")).digest()
        vectors.append([b / 255.0 for b in digest[:8]] or [1.0])
    return vectors


def _write_project(root: Path) -> None:
    services = root / "services"
    services.mkdir(parents=True)
    (services / "animal_service.py").write_text(
        "class AnimalService:\n    def bark_loudly(self):\n        return 'WOOF'\n"
    )
    docs = root / "docs"
    docs.mkdir()
    (docs / "api.md").write_text(
        "# API Reference\n\nThe AnimalService class documents the animal service.\n"
    )


@pytest.fixture(autouse=True)
def _fake_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embedder, "embed_texts", _fake_embed_texts)


def test_semantic_disabled_by_default_leaves_search_and_explore_unaffected(
    ragpilot_home: Path, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    _write_project(root)
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["source", "add", str(root)]).exit_code == 0
    index_result = runner.invoke(app, ["index"])
    assert index_result.exit_code == 0
    # search.semantic defaults to false -- no embeddings computed at all.
    assert "embedded=0" in index_result.output

    project_id = paths.project_id_for_path(root)
    conn = connect(paths.project_db_path(project_id, ragpilot_home))
    try:
        assert embeddings_repo.count_all(conn) == 0
    finally:
        conn.close()

    search_result = runner.invoke(app, ["search", "AnimalService", "--json"])
    assert search_result.exit_code == 0, search_result.output
    payload = json.loads(search_result.output)["data"]
    assert "semantic" not in payload
    assert payload["results"] != []

    explore_result = runner.invoke(
        app, ["explore", "documents about animal service", "--json"]
    )
    assert explore_result.exit_code == 0, explore_result.output
    explore_payload = json.loads(explore_result.output)["data"]
    assert explore_payload["semantic_results"] == []
    assert explore_payload["semantic_available"] is None


def test_semantic_enabled_computes_embeddings_and_surfaces_semantic_results(
    ragpilot_home: Path, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    _write_project(root)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RAGPILOT_SEARCH__SEMANTIC", "true")

    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["source", "add", str(root)]).exit_code == 0
    index_result = runner.invoke(app, ["index"])
    assert index_result.exit_code == 0, index_result.output
    assert "embedded=0" not in index_result.output

    project_id = paths.project_id_for_path(root)
    conn = connect(paths.project_db_path(project_id, ragpilot_home))
    try:
        stored = embeddings_repo.count_all(conn)
        assert stored > 0
        rows = embeddings_repo.list_by_model(conn, embedder.EMBEDDING_MODEL_ID)
        assert len(rows) == stored
    finally:
        conn.close()

    # The exact same query text as an indexed entity's signature scores a
    # perfect (or near-perfect) match under the fake hash-based embedder,
    # so it is guaranteed to surface as a semantic hit distinct from
    # lexical/graph results.
    search_result = runner.invoke(app, ["search", "bark_loudly", "--json"])
    assert search_result.exit_code == 0, search_result.output
    payload = json.loads(search_result.output)["data"]
    assert payload["semantic"]["available"] is True
    assert payload["semantic"]["results"] != []
    assert all(r["tier"] == "semantic" for r in payload["semantic"]["results"])
    # Semantic results are additive, never mixed into the lexical list's
    # own tier values.
    assert all(r["tier"] != "semantic" for r in payload["results"])

    # "bark_loudly" alone is a bare identifier -> Strategy.SEMANTIC is
    # only added for document/general-intent queries (see
    # retrieval/planner.py), so use a phrasing that actually routes
    # through it.
    explore_result = runner.invoke(app, ["explore", "documents about animal service", "--json"])
    assert explore_result.exit_code == 0, explore_result.output
    explore_payload = json.loads(explore_result.output)["data"]
    assert explore_payload["semantic_available"] is True
    # Any semantic evidence is folded in at the lowest confidence tier.
    semantic_evidence = [
        e for e in explore_payload["evidence"] if e["source"].startswith("semantic:")
    ]
    assert all(e["confidence"] == "heuristic" for e in semantic_evidence)


def test_semantic_enabled_degrades_gracefully_when_embeddings_are_cleared(
    ragpilot_home: Path, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    _write_project(root)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RAGPILOT_SEARCH__SEMANTIC", "true")

    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["source", "add", str(root)]).exit_code == 0
    assert runner.invoke(app, ["index"]).exit_code == 0

    project_id = paths.project_id_for_path(root)
    conn = connect(paths.project_db_path(project_id, ragpilot_home))
    try:
        assert embeddings_repo.count_all(conn) > 0
        embeddings_repo.clear_all(conn)
        conn.commit()
    finally:
        conn.close()

    # Clearing embeddings must never touch entities/documents, and
    # search/explore must degrade to "no embeddings yet" rather than
    # erroring out.
    search_result = runner.invoke(app, ["search", "AnimalService", "--json"])
    assert search_result.exit_code == 0, search_result.output
    payload = json.loads(search_result.output)["data"]
    assert payload["results"] != []  # lexical/entities untouched
    assert payload["semantic"]["available"] is True
    assert payload["semantic"]["results"] == []

    explore_result = runner.invoke(app, ["explore", "AnimalService", "--json"])
    assert explore_result.exit_code == 0, explore_result.output


def test_semantic_enabled_degrades_gracefully_when_the_model_is_unavailable(
    ragpilot_home: Path,
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "project"
    _write_project(root)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RAGPILOT_SEARCH__SEMANTIC", "true")

    def _raise(texts: list[str]) -> list[list[float]]:
        raise embedder.EmbeddingModelUnavailableError("simulated: no network")

    monkeypatch.setattr(embedder, "embed_texts", _raise)

    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["source", "add", str(root)]).exit_code == 0
    # Indexing must not fail just because the embedding model can't load.
    index_result = runner.invoke(app, ["index"])
    assert index_result.exit_code == 0, index_result.output
    assert "embedded=0" in index_result.output

    search_result = runner.invoke(app, ["search", "AnimalService", "--json"])
    assert search_result.exit_code == 0, search_result.output
    payload = json.loads(search_result.output)["data"]
    assert payload["results"] != []
    assert payload["semantic"]["available"] is False
    assert "unavailable" in payload["semantic"]["reason"]
