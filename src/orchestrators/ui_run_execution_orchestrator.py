from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, TypeAlias

from src.contracts.acquisition_audit import AcquisitionAuditBatchRequest
from src.contracts.browser_download import ReportDownloadOrchestratorRequest
from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.cover_images import CoverImageOrchestratorRequest
from src.contracts.publisher_inventory import PublisherInventoryDiscoveryRequest
from src.contracts.run_context import RunContext
from src.contracts.ui_run_control import UiRunWorkerRequest
from src.contracts.ui_run_payloads import (
    PAYLOAD_SCHEMA_VERSION,
    AcquisitionAuditUiRunPayload,
    CandidateExtractionUiRunPayload,
    CoverImagesUiRunPayload,
    IngestUiRunPayload,
    PublishUiRunPayload,
    PublisherDiscoveryUiRunPayload,
    ReportDownloadUiRunPayload,
)
from src.contracts.ui_run_replay import UiRunExecutionResponse
from src.orchestrators.acquisition_audit_orchestrator import run_acquisition_audit
from src.orchestrators.candidate_extraction_orchestrator import run_candidate_extraction
from src.orchestrators.cover_image_orchestrator import run_cover_image_generation
from src.orchestrators.ingest_orchestrator import run_ingest
from src.orchestrators.publish_orchestrator import run_publish
from src.orchestrators.publisher_inventory_orchestrator import (
    run_publisher_inventory_discovery,
)
from src.orchestrators.report_download_orchestrator import run_report_download
from src.services.config_service import (
    build_ingest_settings,
    load_browser_download_settings,
    load_publisher_inventory_settings,
    load_publish_settings,
    load_settings,
)
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.ui_run_execution_orchestrator")

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_TREE_ROOT = REPO_ROOT / "src"
PROMPT_TREE_ROOT = REPO_ROOT / "src" / "prompts"
SENSITIVE_KEY_TOKENS = ("api_key", "token", "password", "secret", "email")
UiRunPayload: TypeAlias = (
    IngestUiRunPayload
    | CandidateExtractionUiRunPayload
    | CoverImagesUiRunPayload
    | PublishUiRunPayload
    | PublisherDiscoveryUiRunPayload
    | ReportDownloadUiRunPayload
    | AcquisitionAuditUiRunPayload
)


def _sensitive_key(token: str) -> bool:
    lowered = str(token or "").strip().lower()
    return any(marker in lowered for marker in SENSITIVE_KEY_TOKENS)


def _stable_scalar_hash(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _sanitize_snapshot(value: Any, *, parent_hint: str = "") -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, dict):
        entity_key = str(value.get("key") or "").strip().lower()
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_name = str(key)
            should_hash = _sensitive_key(key_name) or (
                key_name == "value" and _sensitive_key(entity_key or parent_hint)
            )
            if should_hash:
                if item in (None, "", [], {}, ()):
                    sanitized[key_name] = item
                else:
                    sanitized[key_name] = f"redacted_sha256:{_stable_scalar_hash(item)}"
                continue
            sanitized[key_name] = _sanitize_snapshot(
                item,
                parent_hint=entity_key or key_name,
            )
        return sanitized
    if isinstance(value, list):
        return [_sanitize_snapshot(item, parent_hint=parent_hint) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_snapshot(item, parent_hint=parent_hint) for item in value]
    return value


def _optional_text(payload: dict[str, Any], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    token = str(value).strip()
    return token or None


def _required_text(
    payload: dict[str, Any],
    field_name: str,
    *,
    run_type: str,
    missing_code: str = "ui_run_payload_missing_field",
) -> str:
    token = _optional_text(payload, field_name)
    if token:
        return token
    raise AppError(
        code=missing_code,
        message=f"UI run payload field is required: {field_name}",
        retryable=False,
        severity="error",
        context={
            "run_type": run_type,
            "field": field_name,
            "payload_keys": sorted(payload.keys()),
        },
    )


def _optional_positive_int(
    payload: dict[str, Any],
    field_name: str,
    *,
    run_type: str,
) -> int | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, bool):
        raise AppError(
            code="ui_run_payload_invalid_int",
            message=f"UI run payload field must be a positive integer: {field_name}",
            retryable=False,
            severity="error",
            context={"run_type": run_type, "field": field_name, "value_type": "bool"},
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AppError(
            code="ui_run_payload_invalid_int",
            message=f"UI run payload field must be a positive integer: {field_name}",
            cause=exc if isinstance(exc, Exception) else None,
            retryable=False,
            severity="error",
            context={
                "run_type": run_type,
                "field": field_name,
                "value_type": type(value).__name__,
            },
        ) from exc
    if parsed <= 0:
        raise AppError(
            code="ui_run_payload_invalid_int",
            message=f"UI run payload field must be greater than zero: {field_name}",
            retryable=False,
            severity="error",
            context={"run_type": run_type, "field": field_name, "value": parsed},
        )
    return parsed


def _validate_ui_run_payload(*, run_type: str, payload: dict[str, Any]) -> UiRunPayload:
    if run_type == "ingest":
        return IngestUiRunPayload(
            schema_version=PAYLOAD_SCHEMA_VERSION,
            folder_id=_optional_text(payload, "folder_id"),
            limit=_optional_positive_int(payload, "limit", run_type=run_type),
        )
    if run_type == "candidate_extraction":
        return CandidateExtractionUiRunPayload(
            schema_version=PAYLOAD_SCHEMA_VERSION,
            folder_id=_optional_text(payload, "folder_id"),
            limit=_optional_positive_int(payload, "limit", run_type=run_type),
            file_id=_optional_text(payload, "file_id"),
            pdf_path=_optional_text(payload, "pdf_path"),
            report_id=_optional_text(payload, "report_id"),
        )
    if run_type == "cover_images":
        return CoverImagesUiRunPayload(
            schema_version=PAYLOAD_SCHEMA_VERSION,
            style_config_path=_optional_text(payload, "style_config_path") or "",
            limit=_optional_positive_int(payload, "limit", run_type=run_type),
            file_id=_optional_text(payload, "file_id"),
        )
    if run_type == "publish":
        return PublishUiRunPayload(
            schema_version=PAYLOAD_SCHEMA_VERSION,
            limit=_optional_positive_int(payload, "limit", run_type=run_type),
        )
    if run_type == "publisher_discovery":
        return PublisherDiscoveryUiRunPayload(
            schema_version=PAYLOAD_SCHEMA_VERSION,
            insights_url=_required_text(
                payload,
                "insights_url",
                run_type=run_type,
                missing_code="ui_run_payload_insights_url_missing",
            ),
        )
    if run_type == "report_download":
        return ReportDownloadUiRunPayload(
            schema_version=PAYLOAD_SCHEMA_VERSION,
            url=_required_text(
                payload,
                "url",
                run_type=run_type,
                missing_code="ui_run_payload_url_missing",
            ),
            delivery_email=_optional_text(payload, "delivery_email"),
            publisher_insights_url=_optional_text(payload, "publisher_insights_url"),
            publisher_google_folder=_optional_text(payload, "publisher_google_folder"),
        )
    if run_type == "acquisition_audit":
        return AcquisitionAuditUiRunPayload(
            schema_version=PAYLOAD_SCHEMA_VERSION,
            publisher_limit=_optional_positive_int(
                payload, "publisher_limit", run_type=run_type
            ),
            candidate_limit_per_publisher=_optional_positive_int(
                payload, "candidate_limit_per_publisher", run_type=run_type
            ),
            delivery_email=_optional_text(payload, "delivery_email"),
        )
    raise AppError(
        code="ui_run_type_unknown",
        message=f"Unknown UI run type: {run_type}",
        retryable=False,
        context={"run_type": run_type, "payload_keys": sorted(payload.keys())},
    )


def _invalid_payload_config_snapshot(
    *,
    worker_request: UiRunWorkerRequest,
    error: AppError,
) -> dict[str, Any]:
    return {
        "run_type": worker_request.run_type,
        "request_payload_keys": sorted(worker_request.request_payload.keys()),
        "source_tree_root": str(SOURCE_TREE_ROOT),
        "prompt_tree_root": str(PROMPT_TREE_ROOT),
        "payload_error": {
            "code": error.code,
            "field": error.context.get("field", ""),
        },
    }


def _execution_response(
    *,
    worker_request: UiRunWorkerRequest,
    status: str,
    result_summary: dict[str, Any],
    artifact_paths: list[str],
    config_snapshot: dict[str, Any],
    error_code: str = "",
    error_message: str = "",
    error_retryable: bool = False,
    error_severity: str = "error",
) -> UiRunExecutionResponse:
    return UiRunExecutionResponse(
        schema_version="1.0",
        run_id=worker_request.run_id,
        run_type=worker_request.run_type,
        status=status,
        result_summary=result_summary,
        artifact_paths=artifact_paths,
        config_snapshot=config_snapshot,
        config_fingerprint=sha256_json(config_snapshot),
        error_code=error_code,
        error_message=error_message,
        error_retryable=error_retryable,
        error_severity=error_severity,
    )


def resolve_ui_run_config_snapshot(
    worker_request: UiRunWorkerRequest, ctx: RunContext
) -> dict[str, Any]:
    payload = worker_request.request_payload
    run_type = worker_request.run_type
    try:
        _validate_ui_run_payload(run_type=run_type, payload=payload)
    except AppError as exc:
        if exc.code.startswith("ui_run_payload_"):
            return _invalid_payload_config_snapshot(
                worker_request=worker_request,
                error=exc,
            )
        raise
    if run_type in {"ingest", "candidate_extraction"}:
        app_settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), ctx
        )
        ingest_settings = build_ingest_settings(
            IngestSettingsBuildRequest(schema_version="1.0", app_settings=app_settings),
            ctx,
        )
        return {"run_type": run_type, "settings": _sanitize_snapshot(ingest_settings)}
    if run_type == "cover_images":
        app_settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), ctx
        )
        return {"run_type": run_type, "settings": _sanitize_snapshot(app_settings)}
    if run_type == "publish":
        publish_settings = load_publish_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), ctx
        )
        return {"run_type": run_type, "settings": _sanitize_snapshot(publish_settings)}
    if run_type == "publisher_discovery":
        inventory_settings = load_publisher_inventory_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            ctx,
        )
        return {
            "run_type": run_type,
            "settings": _sanitize_snapshot(inventory_settings),
        }
    if run_type == "report_download":
        browser_settings = load_browser_download_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            ctx,
        )
        return {"run_type": run_type, "settings": _sanitize_snapshot(browser_settings)}
    if run_type == "acquisition_audit":
        app_settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), ctx
        )
        inventory_settings = load_publisher_inventory_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            ctx,
        )
        browser_settings = load_browser_download_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            ctx,
        )
        return {
            "run_type": run_type,
            "app_settings": _sanitize_snapshot(app_settings),
            "inventory_settings": _sanitize_snapshot(inventory_settings),
            "browser_settings": _sanitize_snapshot(browser_settings),
        }
    raise AppError(
        code="ui_run_type_unknown",
        message=f"Unknown UI run type: {run_type}",
        retryable=False,
        context={"run_type": run_type, "payload_keys": sorted(payload.keys())},
    )


def execute_ui_run(
    worker_request: UiRunWorkerRequest, ctx: RunContext
) -> UiRunExecutionResponse:
    payload = worker_request.request_payload
    run_type = worker_request.run_type
    config_snapshot: dict[str, Any] = {
        "run_type": run_type,
        "request_payload_keys": sorted(payload.keys()),
        "source_tree_root": str(SOURCE_TREE_ROOT),
        "prompt_tree_root": str(PROMPT_TREE_ROOT),
    }
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="ui_run_execute_start",
            module=logger.name,
            fields={
                "run_id": worker_request.run_id,
                "run_type": run_type,
                "payload_keys": sorted(payload.keys()),
            },
        )
    )
    try:
        validated_payload = _validate_ui_run_payload(run_type=run_type, payload=payload)
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="ui_run_payload_validated",
                module=logger.name,
                fields={
                    "run_id": worker_request.run_id,
                    "run_type": run_type,
                    "payload": _sanitize_snapshot(validated_payload),
                },
            )
        )
        if run_type == "ingest":
            assert isinstance(validated_payload, IngestUiRunPayload)
            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            ingest_settings = build_ingest_settings(
                IngestSettingsBuildRequest(
                    schema_version="1.0", app_settings=app_settings
                ),
                ctx,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(ingest_settings),
            }
            ingest_outcomes = run_ingest(
                ingest_settings,
                folder_id=validated_payload.folder_id,
                limit=validated_payload.limit,
                ctx=ctx,
            )
            processed_count = len(
                [item for item in ingest_outcomes if item.status == "processed"]
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "processed_count": processed_count,
                    "total_count": len(ingest_outcomes),
                },
                artifact_paths=[
                    item.html_path for item in ingest_outcomes if item.html_path
                ],
                config_snapshot=config_snapshot,
            )
        elif run_type == "candidate_extraction":
            assert isinstance(validated_payload, CandidateExtractionUiRunPayload)
            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            candidate_settings = build_ingest_settings(
                IngestSettingsBuildRequest(
                    schema_version="1.0", app_settings=app_settings
                ),
                ctx,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(candidate_settings),
            }
            candidate_outcomes = run_candidate_extraction(
                candidate_settings,
                folder_id=validated_payload.folder_id,
                limit=validated_payload.limit,
                file_id=validated_payload.file_id,
                pdf_path=validated_payload.pdf_path,
                report_id=validated_payload.report_id,
                ctx=ctx,
            )
            artifact_paths: list[str] = []
            for outcome in candidate_outcomes:
                if outcome.candidates_path:
                    artifact_paths.append(outcome.candidates_path)
                artifact_paths.extend(outcome.crop_paths[:5])
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "total_count": len(candidate_outcomes),
                    "candidate_count": sum(
                        item.candidate_count for item in candidate_outcomes
                    ),
                    "chart_count": sum(item.chart_count for item in candidate_outcomes),
                    "table_count": sum(item.table_count for item in candidate_outcomes),
                },
                artifact_paths=artifact_paths,
                config_snapshot=config_snapshot,
            )
        elif run_type == "cover_images":
            assert isinstance(validated_payload, CoverImagesUiRunPayload)
            cover_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(cover_settings),
            }
            cover_outcomes = run_cover_image_generation(
                CoverImageOrchestratorRequest(
                    schema_version="1.0",
                    reports_db=cover_settings.reports_db,
                    output_dir=cover_settings.output_dir,
                    style_config_path=validated_payload.style_config_path,
                    limit=validated_payload.limit,
                    file_id=validated_payload.file_id,
                ),
                ctx=ctx,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "total_count": len(cover_outcomes),
                    "generated_count": len(
                        [item for item in cover_outcomes if item.status == "generated"]
                    ),
                },
                artifact_paths=[
                    item.output_path for item in cover_outcomes if item.output_path
                ],
                config_snapshot=config_snapshot,
            )
        elif run_type == "publish":
            assert isinstance(validated_payload, PublishUiRunPayload)
            publish_settings = load_publish_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(publish_settings),
            }
            publish_outcomes = run_publish(
                publish_settings,
                limit=validated_payload.limit,
                ctx=ctx,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "total_count": len(publish_outcomes),
                    "published_count": len(
                        [
                            item
                            for item in publish_outcomes
                            if item.status == "published"
                        ]
                    ),
                },
                artifact_paths=[
                    item.html_path for item in publish_outcomes if item.html_path
                ],
                config_snapshot=config_snapshot,
            )
        elif run_type == "publisher_discovery":
            assert isinstance(validated_payload, PublisherDiscoveryUiRunPayload)
            inventory_settings = load_publisher_inventory_settings(
                ConfigLoadRequest(schema_version="1.0", path=""),
                ctx,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(inventory_settings),
            }
            discovery_result = run_publisher_inventory_discovery(
                PublisherInventoryDiscoveryRequest(
                    schema_version="1.0",
                    insights_url=validated_payload.insights_url,
                    reports_db=inventory_settings.reports_db,
                    settings=inventory_settings,
                ),
                ctx=ctx,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "publisher_name": discovery_result.publisher_name,
                    "current_report_count": discovery_result.current_report_count,
                    "previous_report_count": discovery_result.previous_report_count,
                    "new_report_count": len(discovery_result.new_report_urls),
                    "quality_band": discovery_result.run_quality_summary.quality_band,
                    "recommended_route_kind": discovery_result.run_quality_summary.recommended_route_kind,
                },
                artifact_paths=[],
                config_snapshot=config_snapshot,
            )
        elif run_type == "report_download":
            assert isinstance(validated_payload, ReportDownloadUiRunPayload)
            browser_settings = load_browser_download_settings(
                ConfigLoadRequest(schema_version="1.0", path=""),
                ctx,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(browser_settings),
            }
            download_result = run_report_download(
                ReportDownloadOrchestratorRequest(
                    schema_version="1.0",
                    url=validated_payload.url,
                    settings=browser_settings,
                    state_db=browser_settings.state_db,
                    reports_db=browser_settings.reports_db,
                    delivery_email=validated_payload.delivery_email,
                    publisher_insights_url=validated_payload.publisher_insights_url,
                    publisher_google_folder=validated_payload.publisher_google_folder,
                ),
                ctx=ctx,
            )
            artifact_paths = [
                path
                for path in [
                    download_result.downloaded_file_path,
                    download_result.onsite_capture_path,
                ]
                if path
            ]
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "route_kind": download_result.route_kind,
                    "route_family": download_result.route_family,
                    "outcome": download_result.outcome,
                    "final_page_url": download_result.final_page_url,
                    "downloaded_file_name": download_result.downloaded_file_name or "",
                },
                artifact_paths=artifact_paths,
                config_snapshot=config_snapshot,
            )
        elif run_type == "acquisition_audit":
            assert isinstance(validated_payload, AcquisitionAuditUiRunPayload)
            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            inventory_settings = load_publisher_inventory_settings(
                ConfigLoadRequest(schema_version="1.0", path=""),
                ctx,
            )
            browser_settings = load_browser_download_settings(
                ConfigLoadRequest(schema_version="1.0", path=""),
                ctx,
            )
            config_snapshot = {
                "run_type": run_type,
                "app_settings": _sanitize_snapshot(app_settings),
                "inventory_settings": _sanitize_snapshot(inventory_settings),
                "browser_settings": _sanitize_snapshot(browser_settings),
            }
            audit_result = run_acquisition_audit(
                AcquisitionAuditBatchRequest(
                    schema_version="1.0",
                    reports_db=app_settings.reports_db,
                    publisher_inventory_settings=inventory_settings,
                    browser_download_settings=browser_settings,
                    output_dir=app_settings.output_dir,
                    delivery_email=validated_payload.delivery_email,
                    publisher_limit=validated_payload.publisher_limit,
                    candidate_limit_per_publisher=validated_payload.candidate_limit_per_publisher,
                ),
                ctx=ctx,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "publisher_count": audit_result.publisher_count,
                    "candidate_count": audit_result.candidate_count,
                    "output_path": audit_result.output_path,
                },
                artifact_paths=[audit_result.output_path],
                config_snapshot=config_snapshot,
            )
        else:
            raise AppError(
                code="ui_run_type_unknown",
                message=f"Unknown UI run type: {run_type}",
                retryable=False,
                context={"run_type": run_type},
            )
    except AppError as exc:
        if exc.code.startswith("ui_run_payload_"):
            config_snapshot = _invalid_payload_config_snapshot(
                worker_request=worker_request,
                error=exc,
            )
        response = _execution_response(
            worker_request=worker_request,
            status="failed",
            result_summary={},
            artifact_paths=[],
            config_snapshot=config_snapshot,
            error_code=exc.code,
            error_message=exc.message,
            error_retryable=exc.retryable,
            error_severity=exc.severity,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="ui_run_execute_failed",
                module=logger.name,
                fields={
                    "run_id": worker_request.run_id,
                    "run_type": run_type,
                    "error_code": exc.code,
                    "error_message": exc.message,
                },
            )
        )
        return response
    except Exception as exc:
        response = _execution_response(
            worker_request=worker_request,
            status="failed",
            result_summary={},
            artifact_paths=[],
            config_snapshot=config_snapshot,
            error_code="ui_run_worker_failed",
            error_message=str(exc),
            error_retryable=False,
            error_severity="error",
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="ui_run_execute_failed",
                module=logger.name,
                fields={
                    "run_id": worker_request.run_id,
                    "run_type": run_type,
                    "error_code": "ui_run_worker_failed",
                    "error_message": str(exc),
                },
            )
        )
        return response
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="ui_run_execute_complete",
            module=logger.name,
            fields={
                "run_id": worker_request.run_id,
                "run_type": run_type,
                "status": response.status,
                "artifact_count": len(response.artifact_paths),
                "result_summary": response.result_summary,
            },
        )
    )
    return response
