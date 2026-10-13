from __future__ import annotations

from pathlib import Path

import yaml

from scripts.quality.release_evidence_job_summary import (
    CANONICAL_BUNDLE_REQUIRED_PATHS,
)


def test_ci_workflow_archives_fresh_release_evidence_bundle() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    jobs = yaml.safe_load(workflow)["jobs"]
    trend_index = workflow.index("PDF benchmark trend gate")
    health_index = workflow.index("Build CI health scorecard")
    accounting_index = workflow.index(
        "Reconcile retained canonical LLM accounting corpus"
    )
    queue_evidence_index = workflow.index(
        "Generate deterministic workflow queue evidence"
    )
    manifest_index = workflow.index("Build release evidence manifest")
    executive_summary_index = workflow.index("Build release evidence executive summary")
    review_index = workflow.index("Build release evidence review")
    summary_index = workflow.index("Write release evidence job summary")
    upload_step_start = workflow.index("- name: Upload release evidence bundle")
    upload_index = workflow.index("actions/upload-artifact@v4", review_index)

    assert jobs["ci_start"]["outputs"]["release_evidence_started_at"] == (
        "${{ steps.mark.outputs.release_evidence_started_at }}"
    )
    assert "date -u" in jobs["ci_start"]["steps"][0]["run"]
    assert jobs["tests"]["needs"] == ["ci_start"]
    assert jobs["release_evidence"]["needs"] == ["ci_start", "tests", "mutation"]
    expected_freshness = "${{ needs.ci_start.outputs.release_evidence_started_at }}"
    assert jobs["tests"]["env"]["RELEASE_EVIDENCE_STARTED_AT"] == expected_freshness
    assert (
        jobs["release_evidence"]["env"]["RELEASE_EVIDENCE_STARTED_AT"]
        == expected_freshness
    )
    assert (
        trend_index
        < queue_evidence_index
        < health_index
        < accounting_index
        < manifest_index
        < executive_summary_index
        < review_index
        < upload_index
        < summary_index
    )
    assert "--fresh-after" in workflow
    assert "--require-head-commit" in workflow
    assert "--allow-issues" in workflow
    assert "--waivers-yaml docs/quality/release_evidence_waivers.yaml" in workflow
    assert "out/release_evidence_manifest_ci.json" in workflow
    assert "out/release_evidence_review_ci.json" in workflow
    assert "out/release_evidence_review_ci.md" in workflow
    assert "docs/quality/release_evidence_waivers.yaml" in workflow
    assert "out/run_health_scorecard_ci.json" in workflow
    assert "out/llm_accounting_reconciliation_ci.json" in workflow
    assert "out/workflow_queue_evidence_ci.json" in workflow
    assert '--expected-commit-sha "${GITHUB_SHA}"' in workflow
    assert '--repository-commit-sha "${GITHUB_SHA}"' in workflow
    assert '--evidence-run-id "${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"' in workflow
    assert "out/test_telemetry_ci.json" in workflow
    assert "out/ci_performance_benchmark.json" in workflow
    benchmark_step = workflow[
        workflow.index("- name: Build CI performance benchmark") : manifest_index
    ]
    assert "if: ${{ always() }}" in benchmark_step
    assert "hashFiles('out/test_telemetry_ci.json')" not in benchmark_step
    assert "out/release_evidence_executive_summary_ci.json" in workflow
    assert "--test-telemetry-json out/test_telemetry_ci.json" in workflow
    assert (
        "--ci-performance-benchmark-json out/ci_performance_benchmark.json" in workflow
    )
    assert (
        "--executive-summary-json out/release_evidence_executive_summary_ci.json"
        in workflow
    )
    assert "release_evidence_job_summary.py" in workflow
    upload_step = workflow[upload_step_start:summary_index]
    summary_step = workflow[summary_index:]
    assert "id: release_evidence_bundle" in upload_step
    for required_path in CANONICAL_BUNDLE_REQUIRED_PATHS:
        assert required_path in upload_step
    assert "out/wordpress_entity_rest_verification_staging.json" in upload_step
    assert (
        "out/wordpress_entity_rest_verification_staging.json"
        not in CANONICAL_BUNDLE_REQUIRED_PATHS
    )
    assert "if: ${{ always() }}" in summary_step
    assert "hashFiles(" not in summary_step
    assert "RELEASE_EVIDENCE_UPLOAD_OUTCOME" in summary_step
    assert "steps.release_evidence_bundle.outcome" in summary_step
    assert "RELEASE_EVIDENCE_ARTIFACT_URL" in summary_step
    assert "steps.release_evidence_bundle.outputs.artifact-url" in summary_step
    assert (
        "--runtime-evidence-json docs/CTO_evidence/log_content_leakage.json"
        in summary_step
    )
    assert "out/pdf_candidate_benchmark_ci.json" in workflow
    assert "out/pdf_crop_refine_benchmark_ci.json" in workflow
    assert "out/pdf_benchmark_trends_ci.json" in workflow
    assert "mutation_results.json" in workflow
    assert "coverage.xml" in workflow
