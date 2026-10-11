from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.quality.generate_workflow_queue_evidence import (
    MAX_EVIDENCE_BYTES,
    finalize_exact_head,
    generate_workflow_queue_evidence,
    validate_workflow_queue_evidence,
)
from scripts.quality.release_evidence_job_summary import (
    main as write_release_evidence_job_summary,
)
from scripts.quality.release_evidence_job_summary import (
    render_release_evidence_job_summary,
)
from scripts.quality.release_evidence_manifest import (
    ReleaseEvidenceArtifactInput,
    build_release_evidence_manifest,
)

_SHA = "a" * 40
_RUN_ID = "12345-2"


def _review_fixture(
    *,
    tested_sha: str = _SHA,
    passed: bool = True,
    issues: list[dict[str, object]] | None = None,
    artifacts: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    issue_rows = issues or []
    artifact_rows = artifacts or [
        {
            "name": "test_telemetry",
            "required": True,
            "status": "passed",
            "passed": True,
            "unwaived_issue_count": 0,
        }
    ]
    return {
        "schema_version": "1.0",
        "generated_at": "2026-10-11T10:00:00+00:00",
        "release_ids": [_RUN_ID],
        "commit_shas": [tested_sha],
        "manifest_passed": passed,
        "passed": passed,
        "artifact_count": len(artifact_rows),
        "issue_count": len(issue_rows),
        "waived_issue_count": sum(1 for issue in issue_rows if issue["waived"]),
        "unwaived_issue_count": sum(1 for issue in issue_rows if not issue["waived"]),
        "waiver_error_count": 0,
        "artifacts": artifact_rows,
        "issues": issue_rows,
        "waiver_errors": [],
    }


def _queue_fixture(*, tested_sha: str = _SHA, passed: bool = True) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "generated_at": "2026-10-11T10:00:00+00:00",
        "repository_commit_sha": tested_sha,
        "queue_schema_version": 16,
        "exact_head_verified": passed,
        "repository": {
            "expected_commit_sha": tested_sha,
            "initial_commit_sha": tested_sha,
            "final_commit_sha": tested_sha,
        },
        "policy_versions": {
            "workflow_queue": "workflow_queue.v1",
            "workflow_queue_evidence": "workflow_queue_evidence.v1",
        },
        "record_ids": {"submitted_job_id": "safe-fixture-id"},
        "transition_counts": {"succeeded": 1},
        "job_status_counts": {"succeeded": 1},
        "outbox_status_counts": {"materialised": 1},
        "publication_readiness_counts": {"approved": 1},
        "approval_count": 1,
        "external_effects": {
            "provider_call_count": 0,
            "wordpress_write_count": 0,
            "recorded_effect_count": 0,
        },
        "production_proof": "not_provided_deterministic_temporary_sqlite_only",
        "failures": [] if passed else ["queue_scenario_failed"],
        "passed": passed,
    }


def _runtime_fixture(
    scope: str, *, tested_sha: str = _SHA, status: str = "passed"
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "generated_at": "2026-10-11T10:00:00+00:00",
        "evidence_run_id": "cto-fixture-run",
        "repository_commit_sha": tested_sha,
        "passed": status == "passed",
        "status": status,
        "freshness_state": "not_required"
        if scope != "representative_report_processing"
        else "passed",
        "log_corpus": {
            "operator_declared_scope": scope,
            "repository_provenance": "collector SHA is distinct from producer SHA",
            "scope_attestation": (
                "scope is declared; workflow execution is not verified"
            ),
        },
        "matches": [
            {"private_diagnostic": "PRIVATE_RUNTIME_DIAGNOSTIC_MUST_NOT_RENDER"}
        ],
    }


def test_queue_evidence_exercises_bounded_lifecycle_and_reconciles_counts() -> None:
    evidence = generate_workflow_queue_evidence(
        expected_commit_sha=_SHA,
        initial_commit_sha=_SHA,
        final_commit_sha=_SHA,
        generated_at="2026-07-19T12:00:00+00:00",
    )

    assert evidence["passed"] is True
    assert evidence["exact_head_verified"] is True
    assert evidence["queue_schema_version"] == 16
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


def test_job_summary_reports_exact_release_and_runtime_evidence_without_details() -> (
    None
):
    review = _review_fixture()
    summary = render_release_evidence_job_summary(
        review=review,
        queue_evidence=_queue_fixture(),
        tested_sha=_SHA,
        expected_run_id=_RUN_ID,
        runtime_evidence=_runtime_fixture("representative_report_processing"),
        artifact_url="https://github.com/acme/marketlense/actions/runs/12345",
    )

    assert f"Tested SHA: `{_SHA}`" in summary
    assert "Final reviewer disposition: `non-green`" in summary
    assert "Release-review disposition: `passed`" in summary
    assert "Queue-evidence disposition: `passed`" in summary
    assert "Runtime-corpus evidence: `declared_unverified`" in summary
    assert "Runtime-corpus scope: `representative`" in summary
    assert (
        "scope declaration does not verify that representative processing ran"
        in summary
    )
    assert "Artifact availability: `unverified`" in summary
    assert "Unwaived issue count: `0`" in summary
    assert "release-evidence-bundle" in summary
    assert "https://github.com/acme/marketlense/actions/runs/12345" in summary
    assert "not live production throughput proof" in summary
    assert "PRIVATE_RUNTIME_DIAGNOSTIC_MUST_NOT_RENDER" not in summary


def test_job_summary_marks_sha_and_run_mismatches_non_green() -> None:
    review = _review_fixture(tested_sha="b" * 40)
    summary = render_release_evidence_job_summary(
        review=review,
        queue_evidence=_queue_fixture(tested_sha="b" * 40),
        tested_sha=_SHA,
        expected_run_id="different-run",
        runtime_evidence=_runtime_fixture(
            "representative_report_processing", tested_sha="b" * 40
        ),
    )

    assert f"Tested SHA: `{_SHA}`" in summary
    assert "Final reviewer disposition: `non-green`" in summary
    assert "Release-review disposition: `mismatched`" in summary
    assert "Runtime-corpus scope: `unavailable`" in summary


def test_job_summary_rejects_same_sha_evidence_from_a_different_build() -> None:
    summary = render_release_evidence_job_summary(
        review=_review_fixture(),
        queue_evidence=_queue_fixture(),
        tested_sha=_SHA,
        expected_run_id="98765-1",
        runtime_evidence=_runtime_fixture("representative_report_processing"),
        artifact_url="https://github.com/acme/marketlense/actions/runs/98765",
    )

    assert "Final reviewer disposition: `non-green`" in summary
    assert "Release-review disposition: `mismatched`" in summary
    assert "Unwaived issue count: `unavailable`" in summary


def test_job_summary_marks_missing_and_stale_evidence_non_green() -> None:
    summary_missing = render_release_evidence_job_summary(
        review=None,
        queue_evidence=_queue_fixture(),
        tested_sha=_SHA,
        expected_run_id=_RUN_ID,
        runtime_evidence=None,
    )
    expired_marker = "PRIVATE_EXPIRED_ARTIFACT_DIAGNOSTIC"
    summary_stale = render_release_evidence_job_summary(
        review=_review_fixture(
            passed=False,
            issues=[
                {
                    "waived": False,
                    "artifact_name": "test_telemetry",
                    "reason": "artifact_stale",
                    "detail": expired_marker,
                }
            ],
            artifacts=[
                {
                    "name": "test_telemetry",
                    "required": True,
                    "status": "stale",
                    "passed": False,
                    "unwaived_issue_count": 1,
                }
            ],
        ),
        queue_evidence=_queue_fixture(),
        tested_sha=_SHA,
        expected_run_id=_RUN_ID,
        runtime_evidence=_runtime_fixture("representative_report_processing"),
    )

    assert "Final reviewer disposition: `non-green`" in summary_missing
    assert "Release-review disposition: `unavailable`" in summary_missing
    assert "Runtime-corpus scope: `unavailable`" in summary_missing
    assert "Final reviewer disposition: `non-green`" in summary_stale
    assert "Release-review disposition: `failed`" in summary_stale
    assert "PRIVATE_EXPIRED_ARTIFACT_DIAGNOSTIC" not in summary_stale
    assert "artifact_stale" not in summary_stale


def test_job_summary_labels_smoke_and_undeclared_corpus_as_non_representative() -> None:
    smoke = render_release_evidence_job_summary(
        review=_review_fixture(),
        queue_evidence=_queue_fixture(),
        tested_sha=_SHA,
        expected_run_id=_RUN_ID,
        runtime_evidence=_runtime_fixture("post_remediation_smoke_only"),
    )
    undeclared = render_release_evidence_job_summary(
        review=_review_fixture(),
        queue_evidence=_queue_fixture(),
        tested_sha=_SHA,
        expected_run_id=_RUN_ID,
        runtime_evidence=_runtime_fixture("not_declared"),
    )

    assert "Runtime-corpus scope: `smoke-only`" in smoke
    assert "representative" in smoke.lower()
    assert "Final reviewer disposition: `non-green`" in smoke
    assert "Runtime-corpus scope: `unavailable`" in undeclared
    assert "Final reviewer disposition: `non-green`" in undeclared


def test_job_summary_is_bounded_and_omits_private_issue_fields() -> None:
    private_marker = "PRIVATE_PROMPT_RESPONSE_CREDENTIAL_BROWSER_PAYLOAD"
    issues = [
        {
            "waived": False,
            "artifact_name": "artifact",
            "reason": private_marker,
            "detail": private_marker,
        }
        for _ in range(200)
    ]
    summary = render_release_evidence_job_summary(
        review=_review_fixture(passed=False, issues=issues),
        queue_evidence=_queue_fixture(),
        tested_sha=_SHA,
        expected_run_id=_RUN_ID,
        runtime_evidence=_runtime_fixture(
            "representative_report_processing", status="failed"
        ),
        artifact_url="https://github.com/acme/marketlense/actions/runs/12345",
    )

    assert "Unwaived issue count: `200`" in summary
    assert "Runtime-corpus evidence: `failed`" in summary
    assert private_marker not in summary
    assert len(summary.encode("utf-8")) <= 2048


def test_job_summary_rejects_incompatible_runtime_metadata_and_bad_queue_sha() -> None:
    incompatible_runtime = _runtime_fixture("representative_report_processing")
    incompatible_runtime["schema_version"] = "9.9"
    summary = render_release_evidence_job_summary(
        review=_review_fixture(),
        queue_evidence=_queue_fixture(tested_sha="b" * 40),
        tested_sha=_SHA,
        expected_run_id=_RUN_ID,
        runtime_evidence=incompatible_runtime,
    )

    assert "Final reviewer disposition: `non-green`" in summary
    assert "Queue-evidence disposition: `mismatched`" in summary
    assert "Runtime-corpus scope: `unavailable`" in summary
    assert "PRIVATE_RUNTIME_DIAGNOSTIC_MUST_NOT_RENDER" not in summary


def test_job_summary_keeps_expired_required_artifacts_non_green_even_if_waived() -> (
    None
):
    review = _review_fixture(
        issues=[{"waived": True, "artifact_name": "test_telemetry"}],
        artifacts=[
            {
                "name": "test_telemetry",
                "required": True,
                "status": "expired",
                "passed": False,
                "unwaived_issue_count": 0,
            }
        ],
    )
    summary = render_release_evidence_job_summary(
        review=review,
        queue_evidence=_queue_fixture(),
        tested_sha=_SHA,
        expected_run_id=_RUN_ID,
        runtime_evidence=_runtime_fixture("representative_report_processing"),
        artifact_url="https://github.com/acme/marketlense/actions/runs/12345",
    )

    assert "Final reviewer disposition: `non-green`" in summary
    assert "Release-review disposition: `failed`" in summary
    assert "Unwaived issue count: `0`" in summary


def test_job_summary_rejects_unknown_required_artifact_status() -> None:
    review = _review_fixture(
        artifacts=[
            {
                "name": "test_telemetry",
                "required": True,
                "status": "unrecognized_status",
                "passed": True,
                "unwaived_issue_count": 0,
            }
        ]
    )
    summary = render_release_evidence_job_summary(
        review=review,
        queue_evidence=_queue_fixture(),
        tested_sha=_SHA,
        expected_run_id=_RUN_ID,
        runtime_evidence=_runtime_fixture("representative_report_processing"),
    )

    assert "Release-review disposition: `incompatible`" in summary
    assert "unrecognized_status" not in summary


def test_job_summary_cli_emits_unavailable_states_when_artifact_files_are_absent(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "github-step-summary.md"

    result = write_release_evidence_job_summary(
        [
            "--review-json",
            str(tmp_path / "missing-review.json"),
            "--queue-evidence-json",
            str(tmp_path / "missing-queue.json"),
            "--output-path",
            str(summary_path),
        ]
    )

    summary = summary_path.read_text(encoding="utf-8")
    assert result == 0
    assert "Final reviewer disposition: `non-green`" in summary
    assert "Release-review disposition: `unavailable`" in summary
    assert "Queue-evidence disposition: `unavailable`" in summary
    assert "Runtime-corpus scope: `unavailable`" in summary


def test_job_summary_script_runs_from_the_repository_root_with_safe_output(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    summary_path = tmp_path / "github-step-summary.md"
    result = subprocess.run(
        [
            sys.executable,
            str(repository_root / "scripts/quality/release_evidence_job_summary.py"),
            "--review-json",
            str(tmp_path / "missing-review.json"),
            "--queue-evidence-json",
            str(tmp_path / "missing-queue.json"),
            "--output-path",
            str(summary_path),
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "ModuleNotFoundError" not in result.stderr
    summary = summary_path.read_text(encoding="utf-8")
    assert "Release-review disposition: `unavailable`" in summary
    assert "Queue-evidence disposition: `unavailable`" in summary
