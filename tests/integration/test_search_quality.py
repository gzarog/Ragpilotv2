"""Golden-query quality regression test (blueprint section 37): indexes
a small, fixed fixture project through the real CLI pipeline (Tree-
sitter parsing, FTS indexing -- no synthetic corpus shortcuts, unlike
``benchmarks/search``'s latency suite), runs every query in
``benchmarks/search/golden_queries.yaml`` through the real
``retrieval/lexical.search``, and asserts Recall@5/@10, MRR, and
NDCG@10 stay at the levels this fixture is known to support.

Deliberately lexical-only: every golden query below is answerable by
lexical search alone (the fixture's document text literally shares
vocabulary with each "conceptual"-style query), so this stays in the
default, network/model-free test suite -- semantic/hybrid search has
its own separate, already-covered contract (see
``tests/integration/test_semantic_retrieval.py``).
"""

from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import Any

import pytest
import yaml
from benchmarks.search.quality import ndcg_at_k, recall_at_k, reciprocal_rank, result_key
from typer.testing import CliRunner

from ragpilot.cli.main import app
from ragpilot.core.lifecycle import AppContext
from ragpilot.retrieval import lexical

GOLDEN_QUERIES_PATH = (
    Path(__file__).resolve().parents[2] / "benchmarks" / "search" / "golden_queries.yaml"
)

# The blueprint's quality targets are stated qualitatively ("speed must
# not reduce retrieval quality"), not as fixed numbers -- these
# thresholds are this fixture's own known-achievable baseline, pinned so
# a future change to lexical ranking that quietly regresses it fails
# here rather than only being noticed by a human eyeballing search
# output.
_MIN_RECALL_AT_5 = 1.0
_MIN_RECALL_AT_10 = 1.0
_MIN_MRR = 0.9
_MIN_NDCG_AT_10 = 0.9


def _write_project(root: Path) -> None:
    services = root / "services"
    services.mkdir(parents=True)
    (services / "settlement_service.py").write_text(
        "class SettlementService:\n"
        "    def process(self):\n"
        "        return self.retry_settlement()\n"
        "\n"
        "    def retry_settlement(self):\n"
        "        return 'retried'\n"
    )

    consumers = root / "consumers"
    consumers.mkdir()
    (consumers / "payment_consumer.py").write_text(
        "from services.settlement_service import SettlementService\n\n\n"
        "class PaymentConsumer:\n"
        "    def handle(self):\n"
        "        service = SettlementService()\n"
        "        return service.process()\n"
    )

    workers = root / "workers"
    workers.mkdir()
    (workers / "retry_worker.py").write_text(
        "from services.settlement_service import SettlementService\n\n\n"
        "class RetryWorker:\n"
        "    def run(self):\n"
        "        service = SettlementService()\n"
        "        return service.retry_settlement()\n"
    )

    docs = root / "docs"
    docs.mkdir()
    (docs / "settlement_guide.md").write_text(
        "# Settlement Guide\n\n"
        "Provider settlements are retried automatically by the retry worker "
        "whenever a payment attempt times out. The SettlementService "
        "coordinates the retry logic.\n"
    )
    (docs / "health_notes.md").write_text(
        "# Health Notes\n\n"
        "Cholesterol measurements should be taken annually. LDL cholesterol "
        "levels above 160 mg/dL indicate elevated cardiovascular risk.\n"
    )


def _load_golden_queries() -> list[dict[str, Any]]:
    data = yaml.safe_load(GOLDEN_QUERIES_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data, f"no golden queries loaded from {GOLDEN_QUERIES_PATH}"
    return data


def test_golden_query_set_meets_quality_thresholds(
    ragpilot_home: Path, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    _write_project(root)
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["source", "add", str(root)]).exit_code == 0
    index_result = runner.invoke(app, ["index"])
    assert index_result.exit_code == 0, index_result.output

    golden = _load_golden_queries()
    ctx = AppContext.bootstrap(home=ragpilot_home, cwd=tmp_path)
    try:
        recalls_at_5: list[float] = []
        recalls_at_10: list[float] = []
        reciprocal_ranks: list[float] = []
        ndcgs_at_10: list[float] = []

        for item in golden:
            results = lexical.search(ctx, item["query"], limit=10)
            # Golden paths are relative to the fixture root; real search
            # results carry the absolute indexed path, so normalize
            # before building comparison keys.
            retrieved = [
                result_key(r.kind, Path(r.path).relative_to(root).as_posix()) for r in results
            ]
            relevant = {result_key(e["kind"], e["path"]) for e in item["expected"]}

            recall5 = recall_at_k(retrieved, relevant, k=5)
            recall10 = recall_at_k(retrieved, relevant, k=10)
            rr = reciprocal_rank(retrieved, relevant)
            ndcg = ndcg_at_k(retrieved, relevant, k=10)

            assert recall5 > 0, (
                f"query {item['query']!r} found none of its expected relevant "
                f"results within the top 5 (retrieved: {retrieved[:5]})"
            )
            recalls_at_5.append(recall5)
            recalls_at_10.append(recall10)
            reciprocal_ranks.append(rr)
            ndcgs_at_10.append(ndcg)

        recall_at_5 = mean(recalls_at_5)
        recall_at_10 = mean(recalls_at_10)
        mrr = mean(reciprocal_ranks)
        ndcg_at_10 = mean(ndcgs_at_10)
        print(
            f"\nGolden query set ({len(golden)} queries): "
            f"Recall@5={recall_at_5:.3f} Recall@10={recall_at_10:.3f} "
            f"MRR={mrr:.3f} NDCG@10={ndcg_at_10:.3f}"
        )

        assert recall_at_5 >= _MIN_RECALL_AT_5
        assert recall_at_10 >= _MIN_RECALL_AT_10
        assert mrr >= _MIN_MRR
        assert ndcg_at_10 >= _MIN_NDCG_AT_10
    finally:
        ctx.close()
