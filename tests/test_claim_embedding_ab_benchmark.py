import subprocess
import sys
from pathlib import Path

from scripts.quality.claim_embedding_ab_benchmark import build_claim_embedding_benchmark


def test_claim_embedding_benchmark_compares_retrieval_and_batched_provider_calls() -> (
    None
):
    claims = [
        ("claim-a", "retail media ad spending is growing"),
        ("claim-b", "spatial computing needs low latency networks"),
        ("claim-c", "online shoppers try new retailers"),
        ("claim-d", "mobile social media use is increasing"),
    ]

    def embed(
        model: str, inputs: list[str], dimensions: int
    ) -> tuple[list[list[float]], int, float]:
        vectors = [[1.0, 0.0] if "retail" in text else [0.0, 1.0] for text in inputs]
        return vectors, len(inputs) * 5, 10.0

    benchmark = build_claim_embedding_benchmark(
        claims=claims,
        query_claim_uids=["claim-a", "claim-b"],
        embed=embed,
        small_dimensions=2,
        large_dimensions=2,
        large_batch_size=4,
    )

    old, new = benchmark.lanes
    assert old.provider_call_count == 6
    assert new.provider_call_count == 2
    assert new.recall_at_5 == 1.0
    assert new.dimensions == 2


def test_claim_embedding_benchmark_runs_as_a_direct_script() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(Path("scripts/quality/claim_embedding_ab_benchmark.py").resolve()),
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Bounded live A/B benchmark" in result.stdout
