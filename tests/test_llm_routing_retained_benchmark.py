from __future__ import annotations

from pathlib import Path

from scripts.quality.llm_routing_retained_benchmark import (
    build_retained_routing_benchmark,
)


def test_retained_routing_benchmark_preserves_evidence_with_real_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    report = build_retained_routing_benchmark(
        artifact_root=str(root / "tests" / "fixtures" / "docpacks" / "golden"),
        config_path=str(root / "src" / "config" / "app.yaml"),
    )

    assert report.report_count >= 15
    assert report.routed_prompt_count == report.report_count * 2
    assert report.missing_evidence_ids == ()
    assert all(row.policy_source != "default" for row in report.rows)
    assert all(row.same_provider_fallback for row in report.rows)
