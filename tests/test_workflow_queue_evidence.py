from __future__ import annotations

import json
from pathlib import Path

from scripts.quality.generate_workflow_queue_evidence import (
    MAX_EVIDENCE_BYTES,
    finalize_exact_head,
    generate_workflow_queue_evidence,
    validate_workflow_queue_evidence,
)
from scripts.quality.release_evidence_job_summary import (
    MAX_ISSUE_LINES,
    render_release_evidence_job_summary,
)
from scripts.quality.release_evidence_manifest import (
    ReleaseEvidenceArtifactInput,
    build_release_evidence_manifest,
)

_SHA = "a" * 40


def test_queue_evidence_exercises_bounded_lifecycle_and_reconciles_counts() -> None:
    evidence = generate_workflow_queue_evidence(
        expected_commit_sha=_SHA,
        initial_commit_sha=_SHA,
        final_commit_sha=_SHA,
        generated_at="2026-07-19T12:00:00+00:00",
    )

    assert evidence["passed"] is True
    assert evidence["exact_head_verified"] is True
    assert evidence["queue_schema_version"] == 14
    assert evidence["transition_counts"] == {
        "budget_deferred": 1,
        "leased": 4,
        "pending": 7,
        "retry_wait": 1,
        "running": 3,
        "succeeded": 1,
    }
    assert evidence["outbox_status_counts"] == {"materialised": 2}
    assert evidence["publication_readiness_counts"] == {"approved": 1}
    assert evidence["approval_count"] == 1
    assert evidence["external_effects"] == {
        "provider_call_count": 0,
        "recorded_effect_count": 0,
        "wordpress_write_count": 0,
    }
    assert set(evidence["record_ids"]) == {
        "approval_id",
        "budget_deferred_job_id",
        "dry_run_handoff_job_id",
        "expired_lease_job_id",
        "materialized_child_job_id",
        "retryable_failure_job_id",
        "submitted_job_id",
    }
    rendered = json.dumps(evidence, ensure_ascii=True)
    assert "source_content" not in rendered
    assert "prompt" not in rendered
    assert len(rendered.encode("utf-8")) <= MAX_EVIDENCE_BYTES


def test_queue_evidence_fails_closed_on_exact_head_mismatch() -> None:
    evidence = generate_workflow_queue_evidence(
        expected_commit_sha=_SHA,
        initial_commit_sha="b" * 40,
        final_commit_sha="b" * 40,
    )

    assert evidence["passed"] is False
    assert evidence["exact_head_verified"] is False
    assert evidence["repository_commit_sha"] == "b" * 40
    assert evidence["failures"] == [
        "exact_head_not_verified",
        "final_commit_sha_mismatch",
        "initial_commit_sha_mismatch",
    ]


def test_queue_evidence_finalization_detects_a_moving_head() -> None:
    evidence = generate_workflow_queue_evidence(
        expected_commit_sha=_SHA,
        initial_commit_sha=_SHA,
        final_commit_sha=_SHA,
    )

    finalized = finalize_exact_head(evidence, final_commit_sha="b" * 40)

    assert finalized["passed"] is False
    assert finalized["exact_head_verified"] is False
    assert finalized["repository"]["final_commit_sha"] == "b" * 40
    assert finalized["failures"] == [
        "exact_head_not_verified",
        "final_commit_sha_mismatch",
    ]


def test_malformed_or_missing_queue_evidence_cannot_pass_release_manifest(
    tmp_path: Path,
) -> None:
    malformed = {"schema_version": "1.0", "passed": True}
    malformed_path = tmp_path / "malformed-queue-evidence.json"
    malformed_path.write_text(json.dumps(malformed), encoding="utf-8")

    assert "evidence_field_invalid:repository" in validate_workflow_queue_evidence(
        malformed
    )
    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="workflow_queue_evidence",
                path=tmp_path / "missing-queue-evidence.json",
                expected_schema_version="1.0",
            ),
            ReleaseEvidenceArtifactInput(
                name="workflow_queue_evidence",
                path=malformed_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="queue-evidence-test",
        commit_sha=_SHA,
        command_args=("manifest",),
    )

    assert manifest.passed is False
    assert {issue.reason for issue in manifest.issues} == {
        "artifact_missing",
        "artifact_invalid_queue_evidence",
    }


def test_job_summary_is_bounded_when_issues_are_present() -> None:
    issues = [
        {"artifact_name": f"artifact-{index}", "reason": "failed"}
        for index in range(MAX_ISSUE_LINES + 3)
    ]
    summary = render_release_evidence_job_summary(
        review={
            "passed": False,
            "unwaived_issue_count": len(issues),
            "issues": issues,
        },
        queue_evidence={"passed": True},
        tested_sha=_SHA,
    )

    assert "Exact tested SHA" in summary
    assert "Queue-evidence status: `passed`" in summary
    assert "not live production throughput proof" in summary
    assert "artifact-9" in summary
    assert "artifact-10" not in summary
    assert "3 additional issue(s) omitted" in summary
