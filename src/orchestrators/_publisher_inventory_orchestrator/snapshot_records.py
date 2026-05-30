from __future__ import annotations

"""Snapshot upload and report-source recording for publisher inventory.

This module owns side-effecting persistence after candidate qualification. It
does not discover inventory, rank candidates, or decide route fallback.
"""

import logging
from dataclasses import asdict

from src.contracts.drive import DriveUploadBytesRequest
from src.contracts.publisher_inventory import (
    PublisherInventoryBuildResponse,
    PublisherInventoryQualifiedCandidateItem,
    PublisherInventorySettings,
)
from src.contracts.report_store import ReportSourceDiscoveryRecordRequest
from src.contracts.run_context import RunContext
from src.orchestrators._publisher_inventory_orchestrator.candidate_flow import (
    _source_domain_for_url,
)
from src.orchestrators._publisher_inventory_orchestrator.dependencies import (
    PublisherInventoryDependencies,
)
from src.orchestrators._publisher_inventory_orchestrator.idempotency import (
    _REPORT_SOURCE_RECORD_IDEMPOTENCY_SCOPE,
    _SNAPSHOT_UPLOAD_IDEMPOTENCY_SCOPE,
    _lookup_idempotency_record,
    _record_idempotency_outcome,
    _restore_report_source_record,
    _restore_upload_bytes_response,
)
from src.orchestrators._publisher_inventory_orchestrator.runtime import (
    _assert_time_budget_remaining,
)
from src.orchestrators._publisher_inventory_orchestrator.snapshot_io import (
    _snapshot_file_name,
)
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.utils.cache_utils import sha256_json
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_inventory_orchestrator")


def _upload_snapshot_if_changed(
    *,
    snapshot_changed: bool,
    previous_snapshot_file_id: str | None,
    previous_snapshot_file_name: str | None,
    previous_snapshot_sha256: str | None,
    build_response: PublisherInventoryBuildResponse,
    folder_id: str,
    normalized_url: str,
    reports_db: str,
    settings: PublisherInventorySettings,
    deadline_monotonic: float,
    policy: RetryPolicy,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> tuple[str | None, str | None, str | None]:
    snapshot_drive_file_id = previous_snapshot_file_id
    snapshot_drive_file_name = previous_snapshot_file_name
    snapshot_sha256 = previous_snapshot_sha256
    if not snapshot_changed:
        return snapshot_drive_file_id, snapshot_drive_file_name, snapshot_sha256

    _assert_time_budget_remaining(
        deadline_monotonic=deadline_monotonic,
        normalized_url=normalized_url,
        step_name="publisher_inventory_snapshot_upload",
        ctx=ctx,
    )
    snapshot_upload_request = DriveUploadBytesRequest(
        schema_version="1.0",
        folder_id=folder_id,
        service_account_path=settings.google_sa_path,
        auth_mode=settings.drive_auth_mode,
        oauth_client_path=settings.google_oauth_client_path,
        oauth_token_path=settings.google_oauth_token_path,
        file_name=_snapshot_file_name(),
        content=build_response.snapshot_json.encode("utf-8"),
        mime_type="application/json",
        supports_all_drives=True,
    )
    snapshot_upload_key = f"{normalized_url}:{build_response.snapshot_sha256}"
    snapshot_upload_checksum = sha256_json(
        {
            "schema_version": "1.0",
            "folder_id": snapshot_upload_request.folder_id,
            "mime_type": snapshot_upload_request.mime_type,
            "snapshot_sha256": build_response.snapshot_sha256,
        }
    )
    existing_snapshot_upload = _lookup_idempotency_record(
        db_path=reports_db,
        scope=_SNAPSHOT_UPLOAD_IDEMPOTENCY_SCOPE,
        idempotency_key=snapshot_upload_key,
        input_checksum=snapshot_upload_checksum,
        ctx=ctx,
    )
    if existing_snapshot_upload is not None:
        upload_response = _restore_upload_bytes_response(
            dict(existing_snapshot_upload.outcome_payload or {})
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_snapshot_upload_idempotency_reused",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "snapshot_drive_file_id": upload_response.file.file_id,
                    "snapshot_drive_file_name": upload_response.file.name or "",
                    "snapshot_sha256": build_response.snapshot_sha256,
                },
            )
        )
    else:
        upload_response = run_with_retry(
            step_name="publisher_inventory_snapshot_upload",
            operation=lambda: dependencies.upload_bytes(
                snapshot_upload_request,
                ctx,
            ),
            ctx=ctx,
            logger=logger,
            module_name=logger.name,
            policy=policy,
            retry_event="publisher_inventory_snapshot_upload_retry",
            failure_event="publisher_inventory_snapshot_upload_failed",
        )
        _record_idempotency_outcome(
            db_path=reports_db,
            scope=_SNAPSHOT_UPLOAD_IDEMPOTENCY_SCOPE,
            idempotency_key=snapshot_upload_key,
            input_checksum=snapshot_upload_checksum,
            outcome_payload=asdict(upload_response),
            artifact_references={
                "folder_id": snapshot_upload_request.folder_id,
                "snapshot_drive_file_id": upload_response.file.file_id,
                "snapshot_drive_file_name": upload_response.file.name or "",
                "snapshot_sha256": build_response.snapshot_sha256,
            },
            ctx=ctx,
        )
    snapshot_drive_file_id = upload_response.file.file_id
    snapshot_drive_file_name = upload_response.file.name
    snapshot_sha256 = build_response.snapshot_sha256
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_snapshot_uploaded",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "snapshot_drive_file_id": snapshot_drive_file_id,
                "snapshot_drive_file_name": snapshot_drive_file_name or "",
                "snapshot_sha256": snapshot_sha256,
            },
        )
    )
    return snapshot_drive_file_id, snapshot_drive_file_name, snapshot_sha256


def _record_qualified_report_sources(
    *,
    qualified_items: list[PublisherInventoryQualifiedCandidateItem],
    page_url_by_number: dict[int, str],
    publisher_name: str,
    publisher_insights_url: str,
    normalized_url: str,
    reports_db: str,
    discovered_at_utc: str,
    deadline_monotonic: float,
    policy: RetryPolicy,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> None:
    for item in qualified_items:
        _assert_time_budget_remaining(
            deadline_monotonic=deadline_monotonic,
            normalized_url=normalized_url,
            step_name="publisher_inventory_report_source_record",
            ctx=ctx,
        )
        source_record_request = ReportSourceDiscoveryRecordRequest(
            schema_version="1.0",
            db_path=reports_db,
            publisher_name=publisher_name,
            source_domain=_source_domain_for_url(item.canonical_url),
            report_name=item.title,
            landing_page_url=item.canonical_url,
            source_page_url=page_url_by_number.get(
                item.discovered_on_page_number,
                publisher_insights_url,
            ),
            discovered_at_utc=discovered_at_utc,
            discovered_on_page_number=item.discovered_on_page_number,
        )
        source_record_key = f"{normalized_url}:{item.canonical_url}"
        source_record_checksum = sha256_json(
            {
                "schema_version": "1.0",
                "publisher_name": source_record_request.publisher_name,
                "source_domain": source_record_request.source_domain,
                "report_name": source_record_request.report_name,
                "landing_page_url": source_record_request.landing_page_url,
                "source_page_url": source_record_request.source_page_url,
                "discovered_on_page_number": source_record_request.discovered_on_page_number,
            }
        )
        existing_source_record = _lookup_idempotency_record(
            db_path=reports_db,
            scope=_REPORT_SOURCE_RECORD_IDEMPOTENCY_SCOPE,
            idempotency_key=source_record_key,
            input_checksum=source_record_checksum,
            ctx=ctx,
        )
        if existing_source_record is not None:
            source_record = _restore_report_source_record(
                dict(existing_source_record.outcome_payload or {})
            )
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_report_source_record_idempotency_reused",
                    module=logger.name,
                    fields={
                        "publisher_name": source_record.publisher_name,
                        "landing_page_url": source_record.landing_page_url,
                        "record_id": source_record.record_id,
                    },
                )
            )
        else:
            source_record = run_with_retry(
                step_name="publisher_inventory_report_source_record",
                operation=lambda: dependencies.record_discovered_report_source(
                    source_record_request,
                    ctx,
                ),
                ctx=ctx,
                logger=logger,
                module_name=logger.name,
                policy=policy,
                retry_event="publisher_inventory_report_source_record_retry",
                failure_event="publisher_inventory_report_source_record_failed",
            )
            _record_idempotency_outcome(
                db_path=reports_db,
                scope=_REPORT_SOURCE_RECORD_IDEMPOTENCY_SCOPE,
                idempotency_key=source_record_key,
                input_checksum=source_record_checksum,
                outcome_payload=asdict(source_record),
                artifact_references={
                    "record_id": source_record.record_id,
                    "landing_page_url": source_record.landing_page_url,
                    "source_page_url": source_record.source_page_url,
                },
                ctx=ctx,
            )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_report_source_recorded",
                module=logger.name,
                fields={
                    "record_id": source_record.record_id,
                    "publisher_name": source_record.publisher_name,
                    "report_name": source_record.report_name,
                    "landing_page_url": source_record.landing_page_url,
                    "source_page_url": source_record.source_page_url,
                    "discovered_on_page_number": source_record.discovered_on_page_number,
                    "created_new": source_record.created_new,
                },
            )
        )


__all__ = [name for name in globals() if not name.startswith("__")]
