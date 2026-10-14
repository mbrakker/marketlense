from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.quality.release_evidence_job_summary import (
    CANONICAL_BUNDLE_REQUIRED_PATHS,
)


def _full_ci_prerequisite_program() -> tuple[str, dict[str, object]]:
    jobs = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))[
        "jobs"
    ]
    steps = jobs["release_evidence"]["steps"]
    gate = next(
        step for step in steps if step.get("name") == "Check full-CI prerequisites"
    )
    prefix = "python3 - <<'PY'\n"
    suffix = "\nPY"
    run = gate["run"].rstrip("\n")
    assert run.startswith(prefix) and run.endswith(suffix)
    return run[len(prefix) : -len(suffix)], gate


@pytest.mark.parametrize(
    ("results", "expected_exit", "expected_summary"),
    [
        (("success", "success", "success"), 0, None),
        (("success", "failure", "success"), 1, "- `tests` job: `failure`"),
        (
            ("success", "success", "failure"),
            1,
            "- `mutation` job: `failure`",
        ),
        (("success", "", "success"), 1, "- `tests` job: `missing`"),
        (("success", "success", ""), 1, "- `mutation` job: `missing`"),
        (
            ("success", "success", "cancelled"),
            1,
            "- `mutation` job: `cancelled`",
        ),
        (
            ("cancelled", "skipped", "skipped"),
            1,
            "- `ci_start` job: `cancelled`",
        ),
    ],
)
def test_release_evidence_prerequisite_gate_handles_all_job_outcomes(
    tmp_path: Path,
    results: tuple[str, str, str],
    expected_exit: int,
    expected_summary: str | None,
) -> None:
    program, gate = _full_ci_prerequisite_program()
    assert gate.get("if") == "always()"
    assert gate.get("id") == "check_full_ci_prerequisites"
    summary = tmp_path / "step-summary.md"
    environment = os.environ.copy()
    environment.update(
        {
            "CI_START_RESULT": results[0],
            "TEST_JOB_RESULT": results[1],
            "MUTATION_JOB_RESULT": results[2],
            "GITHUB_STEP_SUMMARY": str(summary),
        }
    )

    completed = subprocess.run(
        [sys.executable, "-c", program],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert completed.returncode == expected_exit
    if expected_summary is None:
        assert not summary.exists()
    else:
        assert expected_summary in summary.read_text(encoding="utf-8")
        assert "release bundle was not created" in summary.read_text(encoding="utf-8")


def test_ci_workflow_archives_fresh_release_evidence_bundle() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    jobs = yaml.safe_load(workflow)["jobs"]
    release_steps = jobs["release_evidence"]["steps"]
    prerequisite_index = next(
        index
        for index, step in enumerate(release_steps)
        if step.get("name") == "Check full-CI prerequisites"
    )
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
    assert prerequisite_index == 0
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
    assert "steps.check_full_ci_prerequisites.outcome == 'success'" in benchmark_step
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
    assert "steps.check_full_ci_prerequisites.outcome == 'success'" in summary_step
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


def test_failed_prerequisites_skip_release_setup_and_bundle_upload() -> None:
    jobs = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))[
        "jobs"
    ]
    steps = jobs["release_evidence"]["steps"]
    names = [step.get("name", step.get("uses", "")) for step in steps]
    gate_index = names.index("Check full-CI prerequisites")

    assert gate_index == 0
    assert gate_index < names.index("actions/checkout@v4")
    assert gate_index < names.index("actions/setup-python@v5")
    assert gate_index < names.index("Install dependencies")
    for step_name in (
        "Download pytest and coverage inputs",
        "Download mutation partition results",
        "Restore PDF candidate benchmark evidence",
        "Merge mutation partition results",
    ):
        step = next(step for step in steps if step.get("name") == step_name)
        assert step.get("if") is None

    for step in steps[1:]:
        condition = step.get("if", "")
        if "always()" in condition:
            assert "steps.check_full_ci_prerequisites.outcome == 'success'" in condition


def test_pdf_candidate_gate_runs_in_existing_partition_and_is_required_evidence() -> (
    None
):
    jobs = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))[
        "jobs"
    ]
    mutation_steps = jobs["mutation"]["steps"]
    candidate_step = next(
        step
        for step in mutation_steps
        if step.get("name") == "PDF candidate benchmark gate"
    )
    mutation_upload = next(
        step
        for step in mutation_steps
        if step.get("name") == "Upload mutation partition result"
    )
    release_steps = jobs["release_evidence"]["steps"]
    download_step = next(
        step
        for step in release_steps
        if step.get("name") == "Download mutation partition results"
    )
    restore_step = next(
        step
        for step in release_steps
        if step.get("name") == "Restore PDF candidate benchmark evidence"
    )
    merge_step = next(
        step
        for step in release_steps
        if step.get("name") == "Merge mutation partition results"
    )

    assert candidate_step["if"] == "${{ matrix.partition == 0 }}"
    assert "run_command_with_telemetry.py" in candidate_step["run"]
    assert "--stage pdf_candidate_benchmark" in candidate_step["run"]
    assert "out/pdf_candidate_benchmark_ci.json" in mutation_upload["with"]["path"]
    assert "out/quality_command_telemetry_ci.json" in mutation_upload["with"]["path"]
    assert (
        download_step["with"]["pattern"]
        == "mutation-partition-${{ github.run_id }}-${{ github.run_attempt }}-*"
    )
    assert restore_step.get("if") is None
    assert (
        "mutation-partition-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}-0"
        in restore_step["run"]
    )
    assert "test -s" in restore_step["run"]
    assert "--merge-stage-json" in restore_step["run"]
    assert release_steps.index(restore_step) < release_steps.index(merge_step)
    assert release_steps.index(merge_step) < release_steps.index(
        next(
            step
            for step in release_steps
            if step.get("name") == "Build release evidence manifest"
        )
    )
    assert not any(
        step.get("name") == "PDF candidate benchmark gate" for step in release_steps
    )
