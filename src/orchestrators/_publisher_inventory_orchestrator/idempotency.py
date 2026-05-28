from __future__ import annotations

"""Idempotent persistence helpers for publisher-inventory orchestration.

This module owns checksum construction, idempotency lookup/recording, and
restoration of persisted side-effect payloads. It does not choose workflow
routes or perform discovery.
"""

import logging
from dataclasses import asdict, is_dataclass

from src.contracts.drive import DriveFile, DriveUploadBytesResponse
from src.contracts.idempotency import (
    OrchestratorIdempotencyGetRequest,
    OrchestratorIdempotencyRecordRequest,
)
from src.contracts.report_store import (
    PublisherInventoryRecoveryCacheRecordRequest,
    PublisherInventoryRunQualityRecordRequest,
    PublisherInventoryStateRecordRequest,
    PublisherInventoryTestStatusRecordRequest,
    ReportSourceDiscoveryRecordResponse,
)
from src.contracts.run_context import RunContext
from src.orchestrators._publisher_inventory_orchestrator.dependencies import (
    PublisherInventoryDependencies,
)
from src.services import idempotency_service
from src.utils.cache_utils import sha256_json
from src.utils.coercion import coerce_int
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_inventory_orchestrator")


_RUN_QUALITY_IDEMPOTENCY_SCOPE = "publisher_inventory_orchestrator.run_quality_record"

_RECOVERY_CACHE_IDEMPOTENCY_SCOPE = (
    "publisher_inventory_orchestrator.recovery_cache_record"
)

_SNAPSHOT_UPLOAD_IDEMPOTENCY_SCOPE = "publisher_inventory_orchestrator.snapshot_upload"

_REPORT_SOURCE_RECORD_IDEMPOTENCY_SCOPE = (
    "publisher_inventory_orchestrator.report_source_record"
)

_STATE_RECORD_IDEMPOTENCY_SCOPE = "publisher_inventory_orchestrator.state_record"

_TEST_STATUS_IDEMPOTENCY_SCOPE = "publisher_inventory_orchestrator.test_status_record"


def _lookup_idempotency_record(
    *,
    db_path: str,
    scope: str,
    idempotency_key: str,
    input_checksum: str,
    ctx: RunContext,
):
    lookup = idempotency_service.get_outcome(
        OrchestratorIdempotencyGetRequest(
            schema_version="1.0",
            db_path=db_path,
            scope=scope,
            idempotency_key=idempotency_key,
            input_checksum=input_checksum,
        ),
        ctx,
    )
    return lookup.record if lookup.found else None


def _record_idempotency_outcome(
    *,
    db_path: str,
    scope: str,
    idempotency_key: str,
    input_checksum: str,
    outcome_payload: dict[str, object],
    artifact_references: dict[str, object],
    ctx: RunContext,
) -> None:
    idempotency_service.record_outcome(
        OrchestratorIdempotencyRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            scope=scope,
            idempotency_key=idempotency_key,
            input_checksum=input_checksum,
            outcome_payload=outcome_payload,
            artifact_references=artifact_references,
        ),
        ctx,
    )


def _idempotency_key_with_checksum(*parts: str, checksum: str) -> str:
    tokens = [str(part or "").strip() for part in parts if str(part or "").strip()]
    tokens.append(checksum)
    return ":".join(tokens)


def _optional_dataclass_payload(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not is_dataclass(value) or isinstance(value, type):
        return None
    return asdict(value)


def _run_quality_record_checksum(
    request: PublisherInventoryRunQualityRecordRequest,
) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "normalized_url": request.normalized_url,
            "summary": asdict(request.summary),
        }
    )


def _state_record_checksum(
    request: PublisherInventoryStateRecordRequest,
) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "normalized_url": request.normalized_url,
            "source_url": request.source_url,
            "route_kind": request.route_kind,
            "route_summary": request.route_summary,
            "route_trace": _optional_dataclass_payload(request.route_trace),
            "scenario_summary": _optional_dataclass_payload(request.scenario_summary),
            "last_final_page_url": request.last_final_page_url,
            "snapshot_drive_file_id": request.snapshot_drive_file_id,
            "snapshot_drive_file_name": request.snapshot_drive_file_name,
            "snapshot_sha256": request.snapshot_sha256,
        }
    )


def _test_status_record_checksum(
    request: PublisherInventoryTestStatusRecordRequest,
) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "normalized_url": request.normalized_url,
            "status": request.status,
        }
    )


def _recovery_cache_record_checksum(
    request: PublisherInventoryRecoveryCacheRecordRequest,
) -> str:
    record = request.record
    return sha256_json(
        {
            "schema_version": "1.0",
            "normalized_url": record.normalized_url,
            "canonical_url": record.canonical_url,
            "source_surface_class": record.source_surface_class,
            "verification_class": record.verification_class,
            "recovery_action": record.recovery_action,
            "last_outcome": record.last_outcome,
            "last_http_status": record.last_http_status,
            "last_error_marker": record.last_error_marker,
        }
    )


def _record_run_quality_if_needed(
    *,
    request: PublisherInventoryRunQualityRecordRequest,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> None:
    checksum = _run_quality_record_checksum(request)
    idempotency_key = _idempotency_key_with_checksum(
        request.normalized_url,
        request.summary.route_kind,
        request.summary.outcome,
        checksum=checksum,
    )
    existing = _lookup_idempotency_record(
        db_path=request.db_path,
        scope=_RUN_QUALITY_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        ctx=ctx,
    )
    if existing is not None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_run_quality_record_idempotency_reused",
                module=logger.name,
                fields={
                    "normalized_url": request.normalized_url,
                    "outcome": request.summary.outcome,
                    "status": request.summary.status,
                },
            )
        )
        return
    dependencies.record_publisher_inventory_run_quality(request, ctx)
    _record_idempotency_outcome(
        db_path=request.db_path,
        scope=_RUN_QUALITY_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        outcome_payload={
            "schema_version": "1.0",
            "normalized_url": request.normalized_url,
            "summary": asdict(request.summary),
        },
        artifact_references={
            "recommended_route_kind": request.summary.recommended_route_kind,
            "route_kind": request.summary.route_kind,
            "quality_band": request.summary.quality_band,
        },
        ctx=ctx,
    )


def _record_state_if_needed(
    *,
    request: PublisherInventoryStateRecordRequest,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> None:
    checksum = _state_record_checksum(request)
    idempotency_key = _idempotency_key_with_checksum(
        request.normalized_url,
        request.route_kind,
        checksum=checksum,
    )
    existing = _lookup_idempotency_record(
        db_path=request.db_path,
        scope=_STATE_RECORD_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        ctx=ctx,
    )
    if existing is not None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_state_record_idempotency_reused",
                module=logger.name,
                fields={
                    "normalized_url": request.normalized_url,
                    "route_kind": request.route_kind,
                    "snapshot_sha256": request.snapshot_sha256 or "",
                },
            )
        )
        return
    dependencies.record_publisher_inventory_state(request, ctx)
    _record_idempotency_outcome(
        db_path=request.db_path,
        scope=_STATE_RECORD_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        outcome_payload={
            "schema_version": "1.0",
            "normalized_url": request.normalized_url,
            "route_kind": request.route_kind,
            "route_summary": request.route_summary,
            "snapshot_sha256": request.snapshot_sha256,
        },
        artifact_references={
            "snapshot_drive_file_id": request.snapshot_drive_file_id or "",
            "snapshot_drive_file_name": request.snapshot_drive_file_name or "",
            "last_final_page_url": request.last_final_page_url or "",
        },
        ctx=ctx,
    )


def _record_test_status_if_needed(
    *,
    request: PublisherInventoryTestStatusRecordRequest,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> None:
    checksum = _test_status_record_checksum(request)
    idempotency_key = _idempotency_key_with_checksum(
        request.normalized_url,
        checksum=checksum,
    )
    existing = _lookup_idempotency_record(
        db_path=request.db_path,
        scope=_TEST_STATUS_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        ctx=ctx,
    )
    if existing is not None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_test_status_record_idempotency_reused",
                module=logger.name,
                fields={
                    "normalized_url": request.normalized_url,
                    "status": request.status,
                },
            )
        )
        return
    dependencies.record_publisher_inventory_test_status(request, ctx)
    _record_idempotency_outcome(
        db_path=request.db_path,
        scope=_TEST_STATUS_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        outcome_payload={
            "schema_version": "1.0",
            "normalized_url": request.normalized_url,
            "status": request.status,
        },
        artifact_references={"status": request.status},
        ctx=ctx,
    )


def _record_recovery_cache_if_needed(
    *,
    request: PublisherInventoryRecoveryCacheRecordRequest,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> None:
    checksum = _recovery_cache_record_checksum(request)
    record = request.record
    idempotency_key = _idempotency_key_with_checksum(
        record.normalized_url,
        record.canonical_url,
        checksum=checksum,
    )
    existing = _lookup_idempotency_record(
        db_path=request.db_path,
        scope=_RECOVERY_CACHE_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        ctx=ctx,
    )
    if existing is not None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_recovery_cache_record_idempotency_reused",
                module=logger.name,
                fields={
                    "normalized_url": record.normalized_url,
                    "canonical_url": record.canonical_url,
                    "verification_class": record.verification_class,
                    "last_outcome": record.last_outcome,
                },
            )
        )
        return
    dependencies.record_publisher_inventory_recovery_cache_record(request, ctx)
    _record_idempotency_outcome(
        db_path=request.db_path,
        scope=_RECOVERY_CACHE_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        outcome_payload={
            "schema_version": "1.0",
            "normalized_url": record.normalized_url,
            "canonical_url": record.canonical_url,
            "verification_class": record.verification_class,
            "recovery_action": record.recovery_action,
            "last_outcome": record.last_outcome,
        },
        artifact_references={
            "canonical_url": record.canonical_url,
            "verification_class": record.verification_class,
            "recovery_action": record.recovery_action,
        },
        ctx=ctx,
    )


def _restore_drive_file(payload: dict[str, object]) -> DriveFile:
    return DriveFile(
        schema_version=str(payload.get("schema_version") or "1.0"),
        file_id=str(payload.get("file_id") or ""),
        name=str(payload.get("name") or ""),
        modified_time=_payload_optional_str(payload, "modified_time"),
        md5_checksum=_payload_optional_str(payload, "md5_checksum"),
        mime_type=_payload_optional_str(payload, "mime_type"),
    )


def _payload_optional_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    token = str(value).strip()
    return token or None


def _restore_upload_bytes_response(
    payload: dict[str, object],
) -> DriveUploadBytesResponse:
    file_payload = payload.get("file")
    return DriveUploadBytesResponse(
        schema_version=str(payload.get("schema_version") or "1.0"),
        file=(
            _restore_drive_file(file_payload)
            if isinstance(file_payload, dict)
            else DriveFile(
                schema_version="1.0",
                file_id="",
                name="",
                modified_time=None,
                md5_checksum=None,
                mime_type=None,
            )
        ),
        size=coerce_int(payload.get("size"), 0),
        md5=(str(payload.get("md5")) if payload.get("md5") is not None else None),
    )


def _restore_report_source_record(
    payload: dict[str, object],
) -> ReportSourceDiscoveryRecordResponse:
    return ReportSourceDiscoveryRecordResponse(
        schema_version=str(payload.get("schema_version") or "1.0"),
        record_id=coerce_int(payload.get("record_id"), 0),
        publisher_name=str(payload.get("publisher_name") or ""),
        source_domain=str(payload.get("source_domain") or ""),
        report_name=str(payload.get("report_name") or ""),
        landing_page_url=str(payload.get("landing_page_url") or ""),
        source_page_url=str(payload.get("source_page_url") or ""),
        discovered_at_utc=str(payload.get("discovered_at_utc") or ""),
        discovered_on_page_number=coerce_int(
            payload.get("discovered_on_page_number"), 0
        ),
        created_new=bool(payload.get("created_new")),
    )


__all__ = [name for name in globals() if not name.startswith("__")]
