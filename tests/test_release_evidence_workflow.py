from __future__ import annotations

from pathlib import Path


def test_ci_workflow_archives_fresh_release_evidence_bundle() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    freshness_index = workflow.index("RELEASE_EVIDENCE_STARTED_AT")
    coverage_index = workflow.index("Run default pytest suite with coverage")
    trend_index = workflow.index("PDF benchmark trend gate")
    health_index = workflow.index("Build CI health scorecard")
    manifest_index = workflow.index("Build release evidence manifest")
    review_index = workflow.index("Build release evidence review")
    upload_index = workflow.index("actions/upload-artifact@v4")

    assert freshness_index < coverage_index
    assert trend_index < health_index < manifest_index < review_index < upload_index
    assert "--fresh-after" in workflow
    assert "--require-head-commit" in workflow
    assert "--allow-issues" in workflow
    assert "--waivers-yaml docs/quality/release_evidence_waivers.yaml" in workflow
    assert "out/release_evidence_manifest_ci.json" in workflow
    assert "out/release_evidence_review_ci.json" in workflow
    assert "out/release_evidence_review_ci.md" in workflow
    assert "docs/quality/release_evidence_waivers.yaml" in workflow
    assert "out/run_health_scorecard_ci.json" in workflow
    assert "out/pdf_candidate_benchmark_ci.json" in workflow
    assert "out/pdf_crop_refine_benchmark_ci.json" in workflow
    assert "out/pdf_benchmark_trends_ci.json" in workflow
    assert "mutation_results.json" in workflow
    assert "coverage.xml" in workflow
