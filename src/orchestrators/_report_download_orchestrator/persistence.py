from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from src.contracts.browser_download import (
    BrowserDownloadIdentityFieldUpsertRequest,
    BrowserDownloadIdentityFieldUpsertResponse,
    BrowserReportDownloadResult,
    DownloadTerminalEvidence,
    ReportDownloadDriveUpload,
    ReportDownloadOrchestratorRequest,
)
from src.contracts.drive import DriveFile
from src.contracts.files import FileHashRequest
from src.contracts.idempotency import (
    OrchestratorIdempotencyGetRequest,
    OrchestratorIdempotencyRecordRequest,
)
from src.contracts.report_store import (
    PublisherDownloadRouteRecordRequest,
    ReportSourceRecordRequest,
    ReportSourceRecordResponse,
    ReportValueScoreRecordRequest,
    ReportValueScoreRequest,
)
from src.contracts.run_context import RunContext
from src.orchestrators._report_download_orchestrator.dependencies import (
    ReportDownloadDependencies,
)
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.services import idempotency_service
from src.utils.cache_utils import sha256_json
from src.utils.coercion import coerce_int
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.report_download_orchestrator")
_REPORT_DOWNLOAD_ROUTE_RECORD_SCOPE = "report_download_orchestrator.route_record"
_REPORT_DOWNLOAD_SOURCE_RECORD_SCOPE = "report_download_orchestrator.source_record"
_REPORT_DOWNLOAD_IDENTITY_UPDATE_SCOPE = "report_download_orchestrator.identity_update"


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


def _serialize_terminal_evidence_for_idempotency(
    terminal_evidence: DownloadTerminalEvidence | None,
) -> dict[str, object] | None:
    if terminal_evidence is None:
        return None
    return {
        "schema_version": terminal_evidence.schema_version,
        "final_page_url": terminal_evidence.final_page_url,
        "final_page_title": terminal_evidence.final_page_title,
        "terminal_text_excerpt": terminal_evidence.terminal_text_excerpt,
        "artifact_url": terminal_evidence.artifact_url,
        "artifact_kind": terminal_evidence.artifact_kind,
        "artifact_validation_status": terminal_evidence.artifact_validation_status,
        "artifact_validation_detail": terminal_evidence.artifact_validation_detail,
        "confirmation_signal_count": terminal_evidence.confirmation_signal_count,
        "traversed_page_urls": list(terminal_evidence.traversed_page_urls or []),
        "network_events": [
            asdict(event) for event in (terminal_evidence.network_events or [])
        ],
    }


def _route_record_checksum(
    request: PublisherDownloadRouteRecordRequest,
) -> str:
    payload = {
        "schema_version": "1.0",
        "normalized_url": request.normalized_url,
        "source_url": request.source_url,
        "route_kind": request.route_kind,
        "route_summary": request.route_summary,
        "outcome": request.outcome,
        "route_family": request.route_family,
        "route_status": request.route_status,
        "resolved_target_url": request.resolved_target_url,
        "route_steps": [asdict(step) for step in request.route_steps],
        "confirmation_evidence": (
            asdict(request.confirmation_evidence)
            if request.confirmation_evidence is not None
            else None
        ),
        "terminal_evidence": _serialize_terminal_evidence_for_idempotency(
            request.terminal_evidence
        ),
        "browser_had_structured_result": bool(request.browser_had_structured_result),
        "used_candidate_pdf_url": bool(request.used_candidate_pdf_url),
        "used_candidate_source_page": bool(request.used_candidate_source_page),
        "candidate_pdf_url": request.candidate_pdf_url,
        "candidate_source_page_urls": list(request.candidate_source_page_urls or []),
        "candidate_discovery_provenances": list(
            request.candidate_discovery_provenances or []
        ),
        "publisher_discovery_route_kind": request.publisher_discovery_route_kind,
        "publisher_recommended_discovery_route_kind": (
            request.publisher_recommended_discovery_route_kind
        ),
        "blocked_reason": request.blocked_reason,
        "blocked_reason_detail": request.blocked_reason_detail,
        "last_final_page_url": request.last_final_page_url,
        "onsite_capture_format": request.onsite_capture_format,
        "onsite_page_count": request.onsite_page_count,
        "onsite_completeness_status": request.onsite_completeness_status,
    }
    return sha256_json(payload)


def _identity_update_checksum(
    request: BrowserDownloadIdentityFieldUpsertRequest,
) -> str:
    encountered_fields = sorted(
        {
            str(field or "").strip()
            for field in (request.encountered_form_fields or [])
            if str(field or "").strip()
        }
    )
    return sha256_json(
        {
            "schema_version": "1.0",
            "path": request.path,
            "encountered_form_fields": encountered_fields,
        }
    )


def _restore_identity_update_response(
    payload: dict[str, object],
) -> BrowserDownloadIdentityFieldUpsertResponse:
    raw_added_field_keys = payload.get("added_field_keys")
    added_field_keys = (
        raw_added_field_keys if isinstance(raw_added_field_keys, list) else []
    )
    return BrowserDownloadIdentityFieldUpsertResponse(
        schema_version=str(payload.get("schema_version") or "1.0"),
        path=str(payload.get("path") or ""),
        added_field_keys=[
            str(item) for item in added_field_keys if str(item or "").strip()
        ],
        total_fields=coerce_int(payload.get("total_fields"), 0),
    )


def _identity_update_response_payload(
    response: object,
) -> dict[str, object]:
    added_field_keys = getattr(response, "added_field_keys", [])
    return {
        "schema_version": str(getattr(response, "schema_version", "1.0") or "1.0"),
        "path": str(getattr(response, "path", "") or ""),
        "added_field_keys": [
            str(item)
            for item in list(added_field_keys or [])
            if str(item or "").strip()
        ],
        "total_fields": coerce_int(getattr(response, "total_fields", 0), 0),
    }


def _restore_report_source_record(
    payload: dict[str, object],
) -> ReportSourceRecordResponse:
    return ReportSourceRecordResponse(
        schema_version=str(payload.get("schema_version") or "1.0"),
        record_id=coerce_int(payload.get("record_id"), 0),
        source_domain=str(payload.get("source_domain") or ""),
        report_name=str(payload.get("report_name") or ""),
        landing_page_url=str(payload.get("landing_page_url") or ""),
        downloaded_at_utc=str(payload.get("downloaded_at_utc") or ""),
        md5=str(payload.get("md5") or ""),
    )


def _payload_optional_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    token = str(value).strip()
    return token or None


def _restore_drive_file(payload: dict[str, object]) -> DriveFile:
    return DriveFile(
        schema_version=str(payload.get("schema_version") or "1.0"),
        file_id=str(payload.get("file_id") or ""),
        name=str(payload.get("name") or ""),
        modified_time=_payload_optional_str(payload, "modified_time"),
        md5_checksum=_payload_optional_str(payload, "md5_checksum"),
        mime_type=_payload_optional_str(payload, "mime_type"),
    )


def _restore_drive_upload(payload: dict[str, object]) -> ReportDownloadDriveUpload:
    drive_file_payload = payload.get("drive_file")
    drive_file = (
        _restore_drive_file(drive_file_payload)
        if isinstance(drive_file_payload, dict)
        else DriveFile(
            schema_version="1.0",
            file_id="",
            name="",
            modified_time=None,
            md5_checksum=None,
            mime_type=None,
        )
    )
    return ReportDownloadDriveUpload(
        schema_version=str(payload.get("schema_version") or "1.0"),
        local_path=str(payload.get("local_path") or ""),
        file_name=str(payload.get("file_name") or ""),
        mime_type=str(payload.get("mime_type") or ""),
        folder_id=str(payload.get("folder_id") or ""),
        status=str(payload.get("status") or ""),
        size=coerce_int(payload.get("size"), 0),
        md5=(str(payload.get("md5")) if payload.get("md5") is not None else None),
        drive_file=drive_file,
    )


def record_route_outcome(
    *,
    request: ReportDownloadOrchestratorRequest,
    result: BrowserReportDownloadResult,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
) -> bool:
    route_record_request = PublisherDownloadRouteRecordRequest(
        schema_version="1.0",
        db_path=request.reports_db,
        normalized_url=result.normalized_url,
        source_url=result.source_url,
        route_kind=result.route_kind,
        route_summary=result.route_summary,
        outcome=result.outcome,
        route_family=result.route_family,
        route_status=result.route_status,
        resolved_target_url=result.resolved_target_url,
        route_steps=result.route_steps,
        confirmation_evidence=result.confirmation_evidence,
        terminal_evidence=result.terminal_evidence,
        browser_had_structured_result=result.browser_had_structured_result,
        used_candidate_pdf_url=result.used_candidate_pdf_url,
        used_candidate_source_page=result.used_candidate_source_page,
        candidate_pdf_url=(
            request.candidate_trace.pdf_url if request.candidate_trace else None
        ),
        candidate_source_page_urls=(
            list(request.candidate_trace.source_page_urls)
            if request.candidate_trace is not None
            else []
        ),
        candidate_discovery_provenances=(
            list(request.candidate_trace.discovery_provenances)
            if request.candidate_trace is not None
            else []
        ),
        publisher_discovery_route_kind=request.publisher_discovery_route_kind,
        publisher_recommended_discovery_route_kind=request.publisher_recommended_discovery_route_kind,
        blocked_reason=result.blocked_reason,
        blocked_reason_detail=result.blocked_reason_detail,
        last_downloaded_file_path=result.downloaded_file_path,
        last_final_page_url=result.final_page_url,
        onsite_capture_path=result.onsite_capture_path,
        onsite_capture_format=result.onsite_capture_format,
        onsite_page_count=result.onsite_page_count,
        onsite_completeness_status=result.onsite_completeness_status,
    )
    route_record_checksum = _route_record_checksum(route_record_request)
    route_record_key = _idempotency_key_with_checksum(
        normalize_url(result.normalized_url),
        result.route_kind,
        result.outcome,
        checksum=route_record_checksum,
    )
    existing_route_record = _lookup_idempotency_record(
        db_path=request.reports_db,
        scope=_REPORT_DOWNLOAD_ROUTE_RECORD_SCOPE,
        idempotency_key=route_record_key,
        input_checksum=route_record_checksum,
        ctx=ctx,
    )
    if existing_route_record is not None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_route_record_idempotency_reused",
                module=logger.name,
                fields={
                    "normalized_url": result.normalized_url,
                    "route_kind": result.route_kind,
                    "outcome": result.outcome,
                },
            )
        )
    else:
        dependencies.record_publisher_download_route(
            route_record_request,
            ctx,
        )
        _record_idempotency_outcome(
            db_path=request.reports_db,
            scope=_REPORT_DOWNLOAD_ROUTE_RECORD_SCOPE,
            idempotency_key=route_record_key,
            input_checksum=route_record_checksum,
            outcome_payload={
                "schema_version": "1.0",
                "normalized_url": result.normalized_url,
                "route_kind": result.route_kind,
                "route_family": result.route_family,
                "route_status": result.route_status,
                "outcome": result.outcome,
            },
            artifact_references={
                "resolved_target_url": result.resolved_target_url,
                "last_final_page_url": result.final_page_url,
                "last_downloaded_file_path": result.downloaded_file_path or "",
                "onsite_capture_path": result.onsite_capture_path or "",
            },
            ctx=ctx,
        )
    return existing_route_record is not None


def record_downloaded_source(
    *,
    request: ReportDownloadOrchestratorRequest,
    result: BrowserReportDownloadResult,
    policy: RetryPolicy,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
) -> None:
    if result.outcome == "downloaded" and result.downloaded_file_path:
        file_hash = dependencies.file_md5(
            FileHashRequest(
                schema_version="1.0",
                path=result.downloaded_file_path,
            ),
            ctx,
        )
        source_record_request = ReportSourceRecordRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            source_domain=_source_domain_for_url(result.source_url),
            report_name=_report_name_for_result(result),
            landing_page_url=result.source_url,
            downloaded_at_utc=_utc_now_iso(),
            md5=file_hash.md5,
        )
        source_record_checksum = sha256_json(
            {
                "schema_version": "1.0",
                "source_domain": source_record_request.source_domain,
                "report_name": source_record_request.report_name,
                "landing_page_url": source_record_request.landing_page_url,
                "md5": source_record_request.md5,
            }
        )
        source_record_key = _idempotency_key_with_checksum(
            normalize_url(source_record_request.landing_page_url),
            checksum=source_record_checksum,
        )
        existing_source_record = _lookup_idempotency_record(
            db_path=request.reports_db,
            scope=_REPORT_DOWNLOAD_SOURCE_RECORD_SCOPE,
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
                    event="report_download_source_record_idempotency_reused",
                    module=logger.name,
                    fields={
                        "landing_page_url": source_record.landing_page_url,
                        "record_id": source_record.record_id,
                        "md5": source_record.md5,
                    },
                )
            )
        else:
            source_record = run_with_retry(
                step_name="report_download_source_record",
                operation=lambda: dependencies.record_report_source(
                    source_record_request,
                    ctx,
                ),
                ctx=ctx,
                logger=logger,
                module_name=logger.name,
                policy=policy,
                retry_event="report_download_source_record_retry",
                failure_event="report_download_source_record_failed",
                sleep_fn=dependencies.sleep_fn,
            )
            _record_idempotency_outcome(
                db_path=request.reports_db,
                scope=_REPORT_DOWNLOAD_SOURCE_RECORD_SCOPE,
                idempotency_key=source_record_key,
                input_checksum=source_record_checksum,
                outcome_payload=asdict(source_record),
                artifact_references={
                    "record_id": source_record.record_id,
                    "landing_page_url": source_record.landing_page_url,
                    "md5": source_record.md5,
                },
                ctx=ctx,
            )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_source_recorded",
                module=logger.name,
                fields={
                    "record_id": source_record.record_id,
                    "reports_db": request.reports_db,
                    "source_domain": source_record.source_domain,
                    "report_name": source_record.report_name,
                    "landing_page_url": source_record.landing_page_url,
                    "downloaded_at_utc": source_record.downloaded_at_utc,
                    "md5": source_record.md5,
                },
            )
        )
        report_value_score = dependencies.score_report_value(
            ReportValueScoreRequest(
                schema_version="1.0",
                publisher_name="",
                source_domain=source_record.source_domain,
                report_name=source_record.report_name,
                landing_page_url=source_record.landing_page_url,
                source_page_url=source_record.landing_page_url,
                source_status="downloaded",
                discovered_at_utc="",
                downloaded_at_utc=source_record.downloaded_at_utc,
                md5=source_record.md5,
                evaluation_year=_utc_now_year(),
            ),
            ctx,
        )
        run_with_retry(
            step_name="report_download_source_value_score_record",
            operation=lambda: dependencies.record_report_value_score(
                ReportValueScoreRecordRequest(
                    schema_version="1.0",
                    db_path=request.reports_db,
                    record_id=source_record.record_id,
                    score=report_value_score,
                    scored_at_utc=_utc_now_iso(),
                ),
                ctx,
            ),
            ctx=ctx,
            logger=logger,
            module_name=logger.name,
            policy=policy,
            retry_event="report_download_source_value_score_record_retry",
            failure_event="report_download_source_value_score_record_failed",
            sleep_fn=dependencies.sleep_fn,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_source_value_scored",
                module=logger.name,
                fields={
                    "record_id": source_record.record_id,
                    "landing_page_url": source_record.landing_page_url,
                    "overall_score": report_value_score.overall_score,
                    "value_band": report_value_score.value_band,
                    "component_scores": {
                        component.dimension: component.score
                        for component in report_value_score.components
                    },
                    "rationale": report_value_score.rationale,
                },
            )
        )


def record_identity_update(
    *,
    request: ReportDownloadOrchestratorRequest,
    result: BrowserReportDownloadResult,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
) -> BrowserDownloadIdentityFieldUpsertResponse:
    identity_upsert_request = BrowserDownloadIdentityFieldUpsertRequest(
        schema_version="1.0",
        path=request.settings.identity_config_path,
        encountered_form_fields=result.encountered_form_fields,
    )
    identity_update_checksum = _identity_update_checksum(identity_upsert_request)
    identity_update_key = _idempotency_key_with_checksum(
        request.settings.identity_config_path,
        checksum=identity_update_checksum,
    )
    existing_identity_update = _lookup_idempotency_record(
        db_path=request.reports_db,
        scope=_REPORT_DOWNLOAD_IDENTITY_UPDATE_SCOPE,
        idempotency_key=identity_update_key,
        input_checksum=identity_update_checksum,
        ctx=ctx,
    )
    if existing_identity_update is not None:
        identity_update = _restore_identity_update_response(
            dict(existing_identity_update.outcome_payload or {})
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_identity_update_idempotency_reused",
                module=logger.name,
                fields={
                    "path": identity_update.path,
                    "added_field_keys": identity_update.added_field_keys,
                    "total_fields": identity_update.total_fields,
                },
            )
        )
    else:
        identity_update = dependencies.upsert_browser_download_identity_fields(
            identity_upsert_request,
            ctx,
        )
        _record_idempotency_outcome(
            db_path=request.reports_db,
            scope=_REPORT_DOWNLOAD_IDENTITY_UPDATE_SCOPE,
            idempotency_key=identity_update_key,
            input_checksum=identity_update_checksum,
            outcome_payload=_identity_update_response_payload(identity_update),
            artifact_references={
                "path": identity_update.path,
                "added_field_keys": list(identity_update.added_field_keys or []),
            },
            ctx=ctx,
        )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_identity_updated",
            module=logger.name,
            fields={
                "path": identity_update.path,
                "added_field_keys": identity_update.added_field_keys,
                "total_fields": identity_update.total_fields,
            },
        )
    )

    return identity_update


def _source_domain_for_url(url: str) -> str:
    return str(urlsplit(str(url).strip()).hostname or "").strip().lower()


def _report_name_for_result(result: BrowserReportDownloadResult) -> str:
    file_name = str(result.downloaded_file_name or "").strip()
    path_value = str(result.downloaded_file_path or "").strip()
    if file_name:
        base_name = Path(file_name).stem
    elif path_value:
        base_name = Path(path_value).stem
    else:
        base_name = "downloaded_report"
    return " ".join(base_name.replace("_", " ").replace("-", " ").split()).strip()


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _utc_now_year() -> int:
    return datetime.now(timezone.utc).year
