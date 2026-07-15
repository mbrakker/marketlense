from __future__ import annotations

from pathlib import Path

from scripts.quality.semantic_evidence_preselection_benchmark import (
    build_semantic_preselection_benchmark,
)


def test_retained_benchmark_records_safe_embedding_fallback() -> None:
    artifact_path = next(
        (Path(__file__).resolve().parent / "fixtures" / "docpacks" / "golden").glob(
            "*/report_analysis/artifacts.json"
        )
    )

    benchmark = build_semantic_preselection_benchmark(
        artifact_paths=[str(artifact_path)]
    )

    assert benchmark.failures == ()
    assert {row.lane for row in benchmark.lanes} == {"Briefing", "Signal"}
    assert all(
        row.mode == "deterministic_fallback_no_retained_embeddings"
        for row in benchmark.lanes
    )
    assert all(
        row.prompt_chars_after <= row.prompt_chars_before for row in benchmark.lanes
    )
