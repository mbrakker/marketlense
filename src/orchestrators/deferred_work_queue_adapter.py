"""Lossless compatibility handoff from legacy budget-deferred work.

The original ledger remains the audit record for historic budget decisions.  New
execution is represented by a normal typed workflow job, so it receives the
canonical controls, leases, retry decisions, outbox and reconciliation path.
"""

from __future__ import annotations

import hashlib

from src.contracts.deferred_work import (
    DeferredWorkItem,
    DeferredWorkListRequest,
    DeferredWorkQueueMigrationRecord,
    DeferredWorkQueueMigrationRequest,
    DeferredWorkQueueMigrationResponse,
)
from src.contracts.files import FileStatRequest
from src.contracts.run_context import RunContext
from src.contracts.workflow_queue import (
    SourceIngestPayload,
    WorkflowArtifactReference,
    WorkflowJobSubmission,
)
from src.services.file_service import file_stat
from src.services.llm_usage_ledger_service import list_deferred_work
from src.services.workflow_queue_service import enqueue_workflow_job


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _local_pdf_reference(item: DeferredWorkItem) -> str:
    for artifact in item.reusable_artifacts:
        if artifact.kind == "local_pdf" and artifact.reference:
            return artifact.reference
    return ""


def _report_submission(
    item: DeferredWorkItem,
    *,
    artifact_reference: str,
    source_hash: str,
) -> WorkflowJobSubmission:
    processing_version = "legacy-deferred-report-v1"
    report_id = item.report_id or _digest("legacy-report", item.work_key)[:32]
    source_identity_id = item.source_id or source_hash
    remaining_attempts = item.max_attempts - item.attempt_count
    return WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="source_ingest",
        job_type="source_ingest.v1",
        payload=SourceIngestPayload(
            source_identity_id=source_identity_id,
            source_artifact_reference=artifact_reference,
            source_content_hash=source_hash,
            report_id=report_id,
            parser_ocr_compatibility_version=processing_version,
            input_reference=artifact_reference,
            input_content_hash=source_hash,
            required_artifact_references=[
                WorkflowArtifactReference(
                    kind="local_pdf",
                    reference=artifact_reference,
                    content_hash=source_hash,
                )
            ],
            processing_version=processing_version,
            attributes={"legacy_deferred_work_key": item.work_key},
        ),
        idempotency_key=_digest("legacy-deferred-work", item.work_key, source_hash),
        deduplication_scope="legacy-deferred-work",
        root_workflow_id=f"legacy-deferred:{item.run_id or item.work_key}",
        trigger_event_id=f"legacy-deferred:{item.work_key}",
        correlation_id=item.run_id or item.work_key,
        entity_type="report",
        entity_id=report_id,
        publisher_id=item.publisher_id,
        source_identity_id=source_identity_id,
        report_id=report_id,
        available_at_utc=item.earliest_run_at_utc,
        max_attempts=max(1, remaining_attempts),
        budget_profile="report_ingest",
        execution_plan_hash=item.plan_hash,
    )


def migrate_deferred_work_to_workflow_queue(
    request: DeferredWorkQueueMigrationRequest,
    ctx: RunContext,
) -> DeferredWorkQueueMigrationResponse:
    """Materialise supported pending legacy work as idempotent queue jobs.

    Only ``report_generation`` is currently a safe mapping because it has a
    retained PDF and checkpoint-aware pipeline adapter.  Other rows are left
    untouched and returned explicitly for operator remediation; this prevents
    silent loss while avoiding a second generic execution engine.
    """

    records = list_deferred_work(
        DeferredWorkListRequest(
            schema_version="1.0",
            usage_db_path=request.usage_db_path,
            statuses=["pending"],
            limit=max(1, min(500, request.limit)),
        ),
        ctx,
    ).records
    outcomes: list[DeferredWorkQueueMigrationRecord] = []
    for item in records:
        if item.workflow != "report_generation":
            outcomes.append(
                DeferredWorkQueueMigrationRecord(
                    work_key=item.work_key,
                    outcome="unresolved",
                    reason="unsupported_legacy_workflow",
                )
            )
            continue
        if item.attempt_count >= item.max_attempts:
            outcomes.append(
                DeferredWorkQueueMigrationRecord(
                    work_key=item.work_key,
                    outcome="unresolved",
                    reason="legacy_attempts_exhausted",
                )
            )
            continue
        artifact_reference = _local_pdf_reference(item)
        if not artifact_reference:
            outcomes.append(
                DeferredWorkQueueMigrationRecord(
                    work_key=item.work_key,
                    outcome="unresolved",
                    reason="legacy_required_artifact_missing",
                )
            )
            continue
        stat = file_stat(
            FileStatRequest(
                schema_version="1.0", path=artifact_reference, compute_md5=True
            ),
            ctx,
        )
        if not stat.exists or not stat.is_file or not stat.md5:
            outcomes.append(
                DeferredWorkQueueMigrationRecord(
                    work_key=item.work_key,
                    outcome="unresolved",
                    reason="legacy_required_artifact_unverified",
                )
            )
            continue
        job, created = enqueue_workflow_job(
            request.state_db,
            _report_submission(
                item,
                artifact_reference=artifact_reference,
                source_hash=stat.md5,
            ),
            ctx,
        )
        outcomes.append(
            DeferredWorkQueueMigrationRecord(
                work_key=item.work_key,
                workflow_job_id=job.job_id,
                outcome="submitted" if created else "deduplicated",
            )
        )
    return DeferredWorkQueueMigrationResponse(
        inspected_count=len(records), records=outcomes
    )
