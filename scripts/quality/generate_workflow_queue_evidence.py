"""Generate bounded deterministic durable-queue release evidence.

The scenario uses a temporary SQLite state database through the canonical queue
service.  It does not invoke a queue handler, a provider, or WordPress.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.workflow_queue import (
    MaintenancePayload,
    WordPressPublishPayload,
    WorkflowJobSubmission,
    WorkflowStageResult,
)
from src.services.workflow_queue_service import (
    approve_publication_package,
    claim_next_workflow_job,
    complete_workflow_job,
    enqueue_workflow_job,
    fail_workflow_job,
    materialize_workflow_outbox,
    read_workflow_queue_evidence_summary,
    record_publication_readiness,
    release_expired_workflow_leases,
    start_workflow_job,
)
from src.utils.errors import AppError
from src.utils.logging import new_run_context

EVIDENCE_SCHEMA_VERSION = "1.0"
EVIDENCE_POLICY_VERSION = "workflow_queue_evidence.v1"
QUEUE_POLICY_VERSION = "workflow_queue.v1"
MAX_EVIDENCE_BYTES = 16 * 1024
_NOW = "2026-07-19T12:00:00+00:00"
_LEASE_RECOVERY_NOW = "2026-07-19T12:30:01+00:00"


def verify_exact_head(
    *, expected_commit_sha: str, initial_commit_sha: str, final_commit_sha: str
) -> tuple[bool, tuple[str, ...]]:
    """Fail closed unless the expected and both observed full SHAs agree."""
    failures: list[str] = []
    expected = expected_commit_sha.strip()
    if len(expected) != 40:
        failures.append("expected_commit_sha_invalid")
    if initial_commit_sha != expected:
        failures.append("initial_commit_sha_mismatch")
    if final_commit_sha != expected:
        failures.append("final_commit_sha_mismatch")
    return not failures, tuple(failures)


def generate_workflow_queue_evidence(
    *,
    expected_commit_sha: str,
    initial_commit_sha: str,
    final_commit_sha: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Exercise the queue lifecycle and return redacted scalar-only evidence."""
    exact_head_verified, failures = verify_exact_head(
        expected_commit_sha=expected_commit_sha,
        initial_commit_sha=initial_commit_sha,
        final_commit_sha=final_commit_sha,
    )
    scenario_failures = list(failures)
    record_ids: dict[str, str] = {}
    summary: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="market-lense-queue-evidence-") as temp_dir:
        state_db = str(Path(temp_dir) / "queue-evidence.sqlite")
        ctx = new_run_context(task_id="workflow-queue-release-evidence")
        try:
            successful_parent, _ = enqueue_workflow_job(
                state_db,
                _maintenance_submission("success-parent"),
                ctx,
                now_utc=_NOW,
            )
            record_ids["submitted_job_id"] = successful_parent.job_id
            successful_claim = _claim_and_start(
                state_db, successful_parent, "evidence-success-worker", ctx
            )
            child_submission = _maintenance_submission(
                "success-child",
                parent_job_id=successful_claim.job_id,
                root_workflow_id=successful_claim.root_workflow_id,
                queue_name="cost_reconciliation",
            )
            complete_workflow_job(
                state_db,
                successful_claim.job_id,
                "evidence-success-worker",
                WorkflowStageResult(
                    output_reference="evidence:verified-output",
                    output_content_hash="queue-evidence-output-hash",
                    execution_plan_hash="queue-evidence-plan",
                    output_verified=True,
                    summary={"scenario": "successful_completion"},
                ),
                [child_submission],
                ctx,
                now_utc=_NOW,
            )
            materialized = materialize_workflow_outbox(
                state_db,
                "evidence-outbox-worker",
                ctx,
                now_utc=_NOW,
            )
            if len(materialized) != 1:
                raise RuntimeError(
                    "successful completion did not materialize one outbox child"
                )
            record_ids["materialized_child_job_id"] = materialized[0]

            expired_parent, _ = enqueue_workflow_job(
                state_db,
                _maintenance_submission("expired-lease"),
                ctx,
                now_utc=_NOW,
            )
            expired_claim = claim_next_workflow_job(
                state_db,
                "vector_retention",
                "evidence-expired-lease-worker",
                ctx,
                now_utc=_NOW,
            )
            if expired_claim is None or expired_claim.job_id != expired_parent.job_id:
                raise RuntimeError("expired-lease scenario could not claim its job")
            released = release_expired_workflow_leases(
                state_db, ctx, now_utc=_LEASE_RECOVERY_NOW
            )
            if released != [expired_parent.job_id]:
                raise RuntimeError("expired-lease recovery did not release its one job")
            record_ids["expired_lease_job_id"] = expired_parent.job_id

            retry_parent, _ = enqueue_workflow_job(
                state_db,
                _maintenance_submission("retryable-failure"),
                ctx,
                now_utc=_NOW,
            )
            retry_running = _claim_and_start(
                state_db, retry_parent, "evidence-retry-worker", ctx
            )
            retry_result = fail_workflow_job(
                state_db,
                retry_running.job_id,
                "evidence-retry-worker",
                AppError(
                    code="queue_evidence_retryable_failure",
                    message="Bounded retry scenario",
                    retryable=True,
                ),
                ctx,
                now_utc=_NOW,
            )
            if retry_result.status != "retry_wait":
                raise RuntimeError("retryable failure did not become retry_wait")
            record_ids["retryable_failure_job_id"] = retry_parent.job_id

            deferred_parent, _ = enqueue_workflow_job(
                state_db,
                _maintenance_submission("budget-deferral"),
                ctx,
                now_utc=_NOW,
            )
            deferred_running = _claim_and_start(
                state_db, deferred_parent, "evidence-budget-worker", ctx
            )
            deferred_result = fail_workflow_job(
                state_db,
                deferred_running.job_id,
                "evidence-budget-worker",
                AppError(
                    code="budget_limit_reached",
                    message="Bounded budget-deferral scenario",
                    retryable=True,
                ),
                ctx,
                now_utc=_NOW,
                budget_deferred=True,
            )
            if deferred_result.status != "budget_deferred":
                raise RuntimeError("budget deferral did not remain actionable")
            record_ids["budget_deferred_job_id"] = deferred_parent.job_id

            package_checksum = "queue-evidence-package-checksum"
            record_publication_readiness(
                state_db,
                package_checksum=package_checksum,
                entity_type="briefing",
                package_reference="evidence:publication-package",
                validation_reference="evidence:validation",
                lineage_reference="evidence:lineage",
                required_asset_status="complete",
                readiness_status="awaiting_review",
                reason="bounded queue evidence",
                ctx=ctx,
                now_utc=_NOW,
            )
            approval = approve_publication_package(
                state_db,
                package_checksum=package_checksum,
                actor_id="evidence-operator",
                note="dry-run approval handoff only",
                publish_submission=WorkflowJobSubmission(
                    schema_version="1.0",
                    queue_name="wordpress_publish",
                    job_type="wordpress_publish.v1",
                    payload=WordPressPublishPayload(
                        entity_type="briefing",
                        entity_package_reference="evidence:publication-package",
                        package_checksum=package_checksum,
                        target_site="evidence-only",
                        dry_run=True,
                    ),
                    idempotency_key="queue-evidence-dry-run-publication",
                    deduplication_scope="queue-evidence",
                    root_workflow_id=package_checksum,
                    entity_type="briefing",
                    entity_id="evidence-publication",
                ),
                ctx=ctx,
                now_utc=_NOW,
            )
            approval_handoff = materialize_workflow_outbox(
                state_db,
                "evidence-approval-outbox-worker",
                ctx,
                now_utc=_NOW,
            )
            if len(approval_handoff) != 1:
                raise RuntimeError("dry-run approval did not materialize one handoff")
            record_ids["approval_id"] = approval.approval_id
            record_ids["dry_run_handoff_job_id"] = approval_handoff[0]
            summary = asdict(read_workflow_queue_evidence_summary(state_db, ctx))
        except (AppError, RuntimeError) as exc:
            scenario_failures.append(f"scenario_failed:{type(exc).__name__}")

    expected_counts = {
        "budget_deferred": 1,
        "leased": 4,
        "retry_wait": 1,
        "running": 3,
        "succeeded": 1,
    }
    transition_counts = summary.get("transition_counts", {})
    for status, expected_count in expected_counts.items():
        if transition_counts.get(status) != expected_count:
            scenario_failures.append(f"transition_count_mismatch:{status}")
    if transition_counts.get("pending", 0) != 7:
        scenario_failures.append("transition_count_mismatch:pending")
    if summary.get("outbox_status_counts") != {"materialised": 2}:
        scenario_failures.append("outbox_materialization_mismatch")
    if summary.get("publication_readiness_counts") != {"approved": 1}:
        scenario_failures.append("publication_readiness_mismatch")
    if summary.get("approval_count") != 1:
        scenario_failures.append("approval_count_mismatch")
    if summary.get("external_effect_count") != 0:
        scenario_failures.append("external_effects_detected")

    payload: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "generated_at": generated_at
        or datetime.now(UTC).replace(microsecond=0).isoformat(),
        "repository_commit_sha": final_commit_sha,
        "policy_versions": {
            "workflow_queue": QUEUE_POLICY_VERSION,
            "workflow_queue_evidence": EVIDENCE_POLICY_VERSION,
        },
        "queue_schema_version": summary.get("state_schema_version", 0),
        "exact_head_verified": exact_head_verified,
        "repository": {
            "expected_commit_sha": expected_commit_sha,
            "initial_commit_sha": initial_commit_sha,
            "final_commit_sha": final_commit_sha,
        },
        "record_ids": record_ids,
        "transition_counts": transition_counts,
        "job_status_counts": summary.get("status_counts", {}),
        "outbox_status_counts": summary.get("outbox_status_counts", {}),
        "publication_readiness_counts": summary.get("publication_readiness_counts", {}),
        "approval_count": summary.get("approval_count", 0),
        "external_effects": {
            "provider_call_count": 0,
            "wordpress_write_count": 0,
            "recorded_effect_count": summary.get("external_effect_count", 0),
        },
        "production_proof": "not_provided_deterministic_temporary_sqlite_only",
        "failures": sorted(set(scenario_failures)),
    }
    payload["passed"] = not payload["failures"]
    malformed = validate_workflow_queue_evidence(payload)
    if malformed:
        payload["failures"] = sorted(set([*payload["failures"], *malformed]))
        payload["passed"] = False
    if len(_encode(payload)) > MAX_EVIDENCE_BYTES:
        payload["failures"] = sorted(
            set([*payload["failures"], "evidence_exceeds_bound"])
        )
        payload["passed"] = False
    return payload


def validate_workflow_queue_evidence(payload: object) -> tuple[str, ...]:
    """Validate the bounded artifact shape before CI admits it to a manifest."""
    if not isinstance(payload, dict):
        return ("evidence_not_object",)
    failures: list[str] = []
    required_scalars = {
        "schema_version": str,
        "generated_at": str,
        "repository_commit_sha": str,
        "queue_schema_version": int,
        "exact_head_verified": bool,
        "approval_count": int,
        "passed": bool,
    }
    for field, expected_type in required_scalars.items():
        if not isinstance(payload.get(field), expected_type):
            failures.append(f"evidence_field_invalid:{field}")
    for field in (
        "policy_versions",
        "repository",
        "record_ids",
        "transition_counts",
        "job_status_counts",
        "outbox_status_counts",
        "publication_readiness_counts",
        "external_effects",
    ):
        if not isinstance(payload.get(field), dict):
            failures.append(f"evidence_field_invalid:{field}")
    if not isinstance(payload.get("failures"), list) or not all(
        isinstance(value, str) for value in payload.get("failures", [])
    ):
        failures.append("evidence_field_invalid:failures")
    if payload.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        failures.append("evidence_schema_version_invalid")
    if payload.get("exact_head_verified") is not True:
        failures.append("exact_head_not_verified")
    external_effects = payload.get("external_effects")
    if (
        isinstance(external_effects, dict)
        and external_effects.get("provider_call_count") != 0
    ):
        failures.append("provider_calls_not_zero")
    if (
        isinstance(external_effects, dict)
        and external_effects.get("wordpress_write_count") != 0
    ):
        failures.append("wordpress_writes_not_zero")
    return tuple(sorted(set(failures)))


def write_workflow_queue_evidence(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(_encode(payload) + b"\n")


def finalize_exact_head(
    payload: dict[str, Any], *, final_commit_sha: str
) -> dict[str, Any]:
    """Bind completed temporary-DB evidence to the HEAD observed at finalization."""
    repository = payload.get("repository")
    if not isinstance(repository, dict):
        raise ValueError("Queue evidence repository metadata must be an object")
    expected_commit_sha = str(repository.get("expected_commit_sha") or "")
    initial_commit_sha = str(repository.get("initial_commit_sha") or "")
    exact_head_verified, head_failures = verify_exact_head(
        expected_commit_sha=expected_commit_sha,
        initial_commit_sha=initial_commit_sha,
        final_commit_sha=final_commit_sha,
    )
    known_head_failures = {
        "expected_commit_sha_invalid",
        "initial_commit_sha_mismatch",
        "final_commit_sha_mismatch",
    }
    failures = [
        failure
        for failure in payload.get("failures", [])
        if failure not in known_head_failures
    ]
    payload["repository_commit_sha"] = final_commit_sha
    repository["final_commit_sha"] = final_commit_sha
    payload["exact_head_verified"] = exact_head_verified
    payload["failures"] = sorted(set([*failures, *head_failures]))
    payload["passed"] = not payload["failures"]
    malformed = validate_workflow_queue_evidence(payload)
    if malformed:
        payload["failures"] = sorted(set([*payload["failures"], *malformed]))
        payload["passed"] = False
    if len(_encode(payload)) > MAX_EVIDENCE_BYTES:
        payload["failures"] = sorted(
            set([*payload["failures"], "evidence_exceeds_bound"])
        )
        payload["passed"] = False
    return payload


def _maintenance_submission(
    scenario: str,
    *,
    parent_job_id: str = "",
    root_workflow_id: str = "",
    queue_name: str = "vector_retention",
) -> WorkflowJobSubmission:
    return WorkflowJobSubmission(
        schema_version="1.0",
        queue_name=queue_name,
        job_type=f"{queue_name}.v1",
        payload=MaintenancePayload(
            subject_id=f"queue-evidence:{scenario}",
            input_reference=f"evidence:{scenario}",
            input_content_hash=f"queue-evidence-{scenario}-hash",
            processing_version="queue-evidence.v1",
        ),
        idempotency_key=f"queue-evidence:{scenario}",
        deduplication_scope="queue-evidence",
        root_workflow_id=root_workflow_id,
        parent_job_id=parent_job_id,
        entity_type="queue_evidence",
        entity_id=scenario,
        max_attempts=3,
        execution_plan_hash="queue-evidence-plan",
    )


def _claim_and_start(
    state_db: str,
    expected_job: Any,
    worker_id: str,
    ctx: Any,
) -> Any:
    claimed = claim_next_workflow_job(
        state_db, "vector_retention", worker_id, ctx, now_utc=_NOW
    )
    if claimed is None or claimed.job_id != expected_job.job_id:
        raise RuntimeError("queue evidence claimed an unexpected job")
    return start_workflow_job(state_db, claimed.job_id, worker_id, ctx, now_utc=_NOW)


def _encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "unable to resolve repository HEAD")
    return result.stdout.strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic temporary-SQLite workflow queue release evidence."
    )
    parser.add_argument("--expected-commit-sha", required=True)
    parser.add_argument("--output-json", default="out/workflow_queue_evidence.json")
    args = parser.parse_args(argv)
    initial_commit_sha = _git_head()
    payload = generate_workflow_queue_evidence(
        expected_commit_sha=args.expected_commit_sha,
        initial_commit_sha=initial_commit_sha,
        final_commit_sha=initial_commit_sha,
    )
    payload = finalize_exact_head(payload, final_commit_sha=_git_head())
    output_path = (ROOT / args.output_json).resolve()
    write_workflow_queue_evidence(payload, output_path)
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
