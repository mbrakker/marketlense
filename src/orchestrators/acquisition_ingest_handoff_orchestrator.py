"""Canonical handoff from a verified retained acquisition into source ingest."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlsplit

from src.contracts.acquisition_handoff import VerifiedAcquisitionIngestHandoffRequest
from src.contracts.files import FileStatRequest
from src.contracts.report_store import (
    ReportMetadataGetRequest,
    ReportMetadataUpsertRequest,
    ReportSourceRecordRequest,
    SourceIdentityObservation,
    SourceIdentityObservationRecordRequest,
    SourceIdentityResolution,
)
from src.contracts.run_context import RunContext
from src.contracts.workflow_queue import (
    SourceIngestPayload,
    WorkflowJob,
    WorkflowJobSubmission,
)
from src.services.file_service import file_stat
from src.services.report_store_service import (
    get_metadata,
    record_report_source,
    record_source_identity_observation,
    upsert_metadata,
)
from src.utils.clock import utc_now_iso
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.acquisition_ingest_handoff_orchestrator")


def build_source_ingest_submission_from_verified_acquisition(
    request: VerifiedAcquisitionIngestHandoffRequest,
    *,
    parent_job: WorkflowJob,
    ctx: RunContext,
) -> WorkflowJobSubmission:
    """Create one source-ingest submission after all retained identity checks pass."""
    artifact_reference = request.source_artifact_reference.strip()
    expected_hash = request.expected_content_hash.strip().lower()
    processing_version = request.processing_version.strip()
    report_title = request.report_title.strip()
    source_url = request.source_url.strip()
    if not artifact_reference:
        raise AppError(
            code="acquisition_ingest_artifact_incomplete",
            message="Verified acquisition handoff requires a retained artifact",
            retryable=False,
        )
    if not processing_version:
        raise AppError(
            code="acquisition_ingest_processing_version_missing",
            message="Verified acquisition handoff requires a processing version",
            retryable=False,
        )
    if not request.reports_db.strip() or not source_url or not report_title:
        raise AppError(
            code="acquisition_ingest_provenance_incomplete",
            message="Verified acquisition handoff requires report-store provenance",
            retryable=False,
        )
    if Path(artifact_reference).suffix.casefold() != ".pdf":
        raise AppError(
            code="acquisition_ingest_unsupported_type",
            message="Source ingest currently accepts retained PDF acquisitions only",
            retryable=False,
        )
    parsed_url = urlsplit(source_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise AppError(
            code="acquisition_ingest_source_url_invalid",
            message="Verified acquisition handoff requires a safe source URL",
            retryable=False,
        )
    stat = file_stat(
        FileStatRequest(
            schema_version="1.0", path=artifact_reference, compute_md5=True
        ),
        ctx,
    )
    if not stat.exists or not stat.is_file or not stat.md5:
        raise AppError(
            code="acquisition_ingest_artifact_missing",
            message="Verified acquisition artifact is no longer retained locally",
            retryable=False,
        )
    content_hash = stat.md5.lower()
    if expected_hash and content_hash != expected_hash:
        raise AppError(
            code="acquisition_ingest_hash_mismatch",
            message=(
                "Verified acquisition artifact no longer matches its retained "
                "content hash"
            ),
            retryable=False,
        )

    source_identity = _resolve_or_record_source_identity(
        request=request,
        content_hash=content_hash,
        ctx=ctx,
    )
    # Report IDs are later used as checkpoint path tokens, so content-derived
    # identities must be filesystem-safe as well as deterministic.
    report_id = request.report_id.strip() or f"acquired-{content_hash}"
    _validate_report_content_compatibility(
        reports_db=request.reports_db,
        report_id=report_id,
        content_hash=content_hash,
        ctx=ctx,
    )
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            file_id=report_id,
            title=report_title,
            file_name=Path(artifact_reference).name,
            publisher=request.publisher_name.strip() or None,
            source_url=source_url,
            md5=content_hash,
            source_identity_id=source_identity.source_identity_id,
            source_metadata_hash=source_identity.source_metadata_hash,
            source_identity_status=source_identity.identity_status,
            source_publication_date_status=source_identity.publication_date_status,
        ),
        ctx,
    )
    submission = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="source_ingest",
        job_type="source_ingest.v1",
        payload=SourceIngestPayload(
            source_identity_id=source_identity.source_identity_id,
            source_artifact_reference=artifact_reference,
            source_content_hash=content_hash,
            report_id=report_id,
            parser_ocr_compatibility_version=processing_version,
            input_reference=artifact_reference,
            input_content_hash=content_hash,
            processing_version=processing_version,
            attributes={"acquisition_route": request.acquisition_route.strip()},
        ),
        idempotency_key=f"{content_hash}:source_ingest:{processing_version}",
        deduplication_scope="source-ingest-content",
        root_workflow_id=parent_job.root_workflow_id or parent_job.job_id,
        parent_job_id=parent_job.job_id,
        trigger_event_id=parent_job.trigger_event_id or parent_job.job_id,
        correlation_id=(
            parent_job.correlation_id
            or parent_job.root_workflow_id
            or parent_job.job_id
        ),
        entity_type="report",
        entity_id=report_id,
        publisher_id=request.publisher_id.strip() or parent_job.publisher_id,
        source_identity_id=source_identity.source_identity_id,
        report_id=report_id,
        budget_profile="report_ingest",
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="verified_acquisition_source_ingest_submitted",
            module=logger.name,
            fields={
                "source_identity_id": source_identity.source_identity_id,
                "report_id": report_id,
                "content_hash": content_hash,
                "acquisition_route": request.acquisition_route.strip(),
                "ingest_idempotency_key": submission.idempotency_key,
            },
        )
    )
    return submission


def _resolve_or_record_source_identity(
    *,
    request: VerifiedAcquisitionIngestHandoffRequest,
    content_hash: str,
    ctx: RunContext,
) -> SourceIdentityResolution:
    source_record = record_report_source(
        ReportSourceRecordRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            source_domain=urlsplit(request.source_url).netloc.casefold(),
            report_name=request.report_title,
            landing_page_url=request.source_url,
            downloaded_at_utc=utc_now_iso(),
            md5=content_hash,
            publisher_name=request.publisher_name,
            source_page_url=request.source_url,
        ),
        ctx,
    )
    recorded = record_source_identity_observation(
        SourceIdentityObservationRecordRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            observation=SourceIdentityObservation(
                schema_version="1.0",
                source_record_id=source_record.record_id,
                canonical_title=request.report_title,
                title_evidence_locator="verified_acquisition.report_title",
                publisher_id=request.publisher_id,
                publisher_name=request.publisher_name,
                canonical_landing_page_url=request.source_url,
                acquired_artifact_url=request.source_url,
                source_page_url=request.source_url,
                retrieved_at_utc=utc_now_iso(),
                acquisition_route=request.acquisition_route,
                content_hash=f"md5:{content_hash}",
                resolution_method="verified_acquisition_handoff",
                identity_confidence="medium",
            ),
        ),
        ctx,
    ).resolution
    if not _identity_is_compatible(recorded, content_hash):
        raise AppError(
            code="acquisition_ingest_source_identity_unresolved",
            message=(
                "Verified acquisition could not resolve a compatible canonical "
                "source identity"
            ),
            retryable=False,
        )
    return recorded


def _validate_report_content_compatibility(
    *,
    reports_db: str,
    report_id: str,
    content_hash: str,
    ctx: RunContext,
) -> None:
    """Fail closed instead of silently rebinding a persisted Drive ID to new bytes."""
    existing = get_metadata(
        ReportMetadataGetRequest(
            schema_version="1.0", db_path=reports_db, file_id=report_id
        ),
        ctx,
    )
    if (
        existing is not None
        and existing.md5
        and existing.md5.casefold() != content_hash
    ):
        raise AppError(
            code="acquisition_ingest_report_content_conflict",
            message=(
                "Verified acquisition content conflicts with the persisted report ID"
            ),
            retryable=False,
        )


def _identity_is_compatible(
    identity: SourceIdentityResolution, content_hash: str
) -> bool:
    return (
        identity.identity_status == "resolved"
        and identity.source_identity_id != ""
        and identity.content_hash == f"md5:{content_hash}"
    )
