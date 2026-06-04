from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any, TypeAlias, cast

from src.contracts.acquisition_audit import AcquisitionAuditBatchRequest
from src.contracts.browser_download import ReportDownloadOrchestratorRequest
from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisOrchestratorRequest,
    CrossReportAnalysisRequest,
    CrossReportProjectedDataReadRequest,
    PublicationMode,
)
from src.contracts.cover_images import CoverImageOrchestratorRequest
from src.contracts.publisher_inventory import PublisherInventoryDiscoveryRequest
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidateExtractionRequest,
)
from src.contracts.ui_run_control import UiRunWorkerRequest
from src.contracts.ui_run_payloads import (
    PAYLOAD_SCHEMA_VERSION,
    AcquisitionAuditUiRunPayload,
    CandidateExtractionUiRunPayload,
    CoverImagesUiRunPayload,
    CrossReportAnalysisUiRunPayload,
    IngestUiRunPayload,
    PublishUiRunPayload,
    PublisherDiscoveryUiRunPayload,
    ReportDownloadUiRunPayload,
    SignalCandidateExtractionUiRunPayload,
    SignalPostUiRunPayload,
    UiRunReplayUiRunPayload,
)
from src.contracts.ui_run_replay import UiRunExecutionResponse, UiRunReplayRequest
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPostGenerationRequest,
    SignalPostWorkflowRequest,
)
from src.orchestrators.acquisition_audit_orchestrator import run_acquisition_audit
from src.orchestrators.candidate_extraction_orchestrator import run_candidate_extraction
from src.orchestrators.cover_image_orchestrator import run_cover_image_generation
from src.orchestrators.cross_report_analysis_orchestrator import (
    run_cross_report_analysis,
)
from src.orchestrators.ingest_orchestrator import run_ingest
from src.orchestrators.publish_orchestrator import run_publish
from src.orchestrators.publisher_inventory_orchestrator import (
    run_publisher_inventory_discovery,
)
from src.orchestrators.report_download_orchestrator import run_report_download
from src.orchestrators.signal_candidate_orchestrator import (
    run_signal_candidate_extraction,
)
from src.orchestrators.signal_post_orchestrator import run_signal_post_workflow
from src.services.config_service import (
    build_ingest_settings,
    load_browser_download_settings,
    load_publisher_inventory_settings,
    load_publish_settings,
    load_settings,
)
from src.services.run_registry_service import default_ui_run_registry_path
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.ui_run_execution_orchestrator")

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_TREE_ROOT = REPO_ROOT / "src"
PROMPT_TREE_ROOT = REPO_ROOT / "src" / "prompts"
SENSITIVE_KEY_TOKENS = ("api_key", "token", "password", "secret", "email")
PUBLICATION_MODES = {"generate_only", "validate_only", "publish_dry_run", "publish_live"}
UiRunPayload: TypeAlias = (
    IngestUiRunPayload
    | CandidateExtractionUiRunPayload
    | CoverImagesUiRunPayload
    | PublishUiRunPayload
    | PublisherDiscoveryUiRunPayload
    | ReportDownloadUiRunPayload
    | AcquisitionAuditUiRunPayload
    | CrossReportAnalysisUiRunPayload
    | SignalCandidateExtractionUiRunPayload
    | SignalPostUiRunPayload
    | UiRunReplayUiRunPayload
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


def _optional_date_text(
    payload: dict[str, Any],
    field_name: str,
    *,
    run_type: str,
) -> str | None:
    token = _optional_text(payload, field_name)
    if token is None:
        return None
    try:
        return date.fromisoformat(token).isoformat()
    except ValueError as exc:
        raise AppError(
            code="ui_run_payload_invalid_date",
            message=f"UI run payload field must be a YYYY-MM-DD date: {field_name}",
            cause=exc,
            retryable=False,
            severity="error",
            context={"run_type": run_type, "field": field_name, "value": token},
        ) from exc


def _optional_string_list(payload: dict[str, Any], field_name: str) -> list[str]:
    value = payload.get(field_name)
    if value is None:
        return []
    if isinstance(value, str):
        parts = [piece.strip() for piece in value.split(",")]
    elif isinstance(value, list):
        parts = [str(piece).strip() for piece in value]
    else:
        parts = [str(value).strip()]
    return [piece for piece in parts if piece]


def _publication_mode(payload: dict[str, Any], *, run_type: str) -> PublicationMode:
    mode = str(payload.get("publication_mode") or "generate_only").strip()
    if mode not in PUBLICATION_MODES:
        raise AppError(
            code="ui_run_payload_invalid_publication_mode",
            message="UI run payload publication mode is invalid.",
            retryable=False,
            severity="error",
            context={"run_type": run_type, "publication_mode": mode},
        )
    return cast(PublicationMode, mode)


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
    if run_type == "cross_report_analysis":
        auto_theme = bool(payload.get("auto_theme", True))
        topic = _optional_text(payload, "topic") or ""
        if not auto_theme and not topic:
            raise AppError(
                code="ui_run_payload_topic_missing",
                message="Cross-report analysis requires a topic when auto-theme is off.",
                retryable=False,
                severity="error",
                context={"run_type": run_type, "field": "topic"},
            )
        return CrossReportAnalysisUiRunPayload(
            schema_version=PAYLOAD_SCHEMA_VERSION,
            topic=topic,
            auto_theme=auto_theme,
            category_filters=_optional_string_list(payload, "category_filters"),
            tag_filters=_optional_string_list(payload, "tag_filters"),
            publisher_filters=_optional_string_list(payload, "publisher_filters"),
            date_range_start=_optional_date_text(
                payload, "date_range_start", run_type=run_type
            ),
            date_range_end=_optional_date_text(
                payload, "date_range_end", run_type=run_type
            ),
            max_source_reports=_optional_positive_int(
                payload, "max_source_reports", run_type=run_type
            ),
            max_evidence_items=_optional_positive_int(
                payload, "max_evidence_items", run_type=run_type
            ),
            max_prompt_chars=_optional_positive_int(
                payload, "max_prompt_chars", run_type=run_type
            ),
            publication_mode=_publication_mode(payload, run_type=run_type),
            output_root=_optional_text(payload, "output_root") or "",
            idempotency_db=_optional_text(payload, "idempotency_db") or "",
            request_id=_optional_text(payload, "request_id") or "",
            diagnostic=bool(payload.get("diagnostic", False)),
            override_publishability=bool(payload.get("override_publishability", False)),
        )
    if run_type == "signal_candidate_extraction":
        topic = _required_text(payload, "topic", run_type=run_type)
        return SignalCandidateExtractionUiRunPayload(
            schema_version=PAYLOAD_SCHEMA_VERSION,
            topic=topic,
            category_filters=_optional_string_list(payload, "category_filters"),
            tag_filters=_optional_string_list(payload, "tag_filters"),
            publisher_filters=_optional_string_list(payload, "publisher_filters"),
            date_range_start=_optional_date_text(
                payload, "date_range_start", run_type=run_type
            ),
            date_range_end=_optional_date_text(
                payload, "date_range_end", run_type=run_type
            ),
            max_source_reports=_optional_positive_int(
                payload, "max_source_reports", run_type=run_type
            ),
            max_evidence_items=_optional_positive_int(
                payload, "max_evidence_items", run_type=run_type
            ),
            max_signals=_optional_positive_int(
                payload, "max_signals", run_type=run_type
            ),
            extraction_request_id=_optional_text(payload, "extraction_request_id") or "",
            signal_store_db=_optional_text(payload, "signal_store_db") or "",
        )
    if run_type == "signal_post":
        topic = _required_text(payload, "topic", run_type=run_type)
        return SignalPostUiRunPayload(
            schema_version=PAYLOAD_SCHEMA_VERSION,
            topic=topic,
            category_filters=_optional_string_list(payload, "category_filters"),
            tag_filters=_optional_string_list(payload, "tag_filters"),
            publisher_filters=_optional_string_list(payload, "publisher_filters"),
            date_range_start=_optional_date_text(
                payload, "date_range_start", run_type=run_type
            ),
            date_range_end=_optional_date_text(
                payload, "date_range_end", run_type=run_type
            ),
            max_source_reports=_optional_positive_int(
                payload, "max_source_reports", run_type=run_type
            ),
            max_evidence_items=_optional_positive_int(
                payload, "max_evidence_items", run_type=run_type
            ),
            minimum_source_reports=_optional_positive_int(
                payload, "minimum_source_reports", run_type=run_type
            ),
            minimum_evidence_items=_optional_positive_int(
                payload, "minimum_evidence_items", run_type=run_type
            ),
            publication_mode=_publication_mode(payload, run_type=run_type),
            request_id=_optional_text(payload, "request_id") or "",
            output_root=_optional_text(payload, "output_root") or "",
            signal_store_db=_optional_text(payload, "signal_store_db") or "",
        )
    if run_type == "ui_run_replay":
        return UiRunReplayUiRunPayload(
            schema_version=PAYLOAD_SCHEMA_VERSION,
            run_id=_required_text(payload, "run_id", run_type=run_type),
            registry_path=_optional_text(payload, "registry_path") or "",
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


def _stable_request_id(prefix: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()[:16]}"


def _cross_report_analysis_request(
    payload: CrossReportAnalysisUiRunPayload,
    settings: Any,
) -> CrossReportAnalysisOrchestratorRequest:
    material = {
        "topic": payload.topic,
        "auto_theme": payload.auto_theme,
        "category_filters": payload.category_filters,
        "tag_filters": payload.tag_filters,
        "publisher_filters": payload.publisher_filters,
        "date_range_start": payload.date_range_start,
        "date_range_end": payload.date_range_end,
        "max_source_reports": payload.max_source_reports,
        "max_evidence_items": payload.max_evidence_items,
        "max_prompt_chars": payload.max_prompt_chars,
        "publication_mode": payload.publication_mode,
    }
    max_source_reports = payload.max_source_reports or int(
        getattr(settings, "cross_report_analysis_max_source_reports", 6)
    )
    max_evidence_items = payload.max_evidence_items or int(
        getattr(settings, "cross_report_analysis_max_evidence_items", 48)
    )
    max_prompt_chars = payload.max_prompt_chars or int(
        getattr(settings, "cross_report_analysis_max_prompt_chars", 60000)
    )
    request_id = payload.request_id or _stable_request_id(
        "ui-cross-report", material
    )
    analysis_request = CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id=request_id,
        topic=payload.topic,
        auto_theme=payload.auto_theme,
        category_filters=list(payload.category_filters),
        tag_filters=list(payload.tag_filters),
        publisher_filters=list(payload.publisher_filters),
        date_range_start=payload.date_range_start,
        date_range_end=payload.date_range_end,
        max_source_reports=max_source_reports,
        diagnostic=payload.diagnostic,
        override_publishability=payload.override_publishability,
        publication_mode=cast(PublicationMode, payload.publication_mode),
    )
    return CrossReportAnalysisOrchestratorRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        analysis_request=analysis_request,
        projected_data_request=CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=settings.reports_db,
            publisher_filters=list(payload.publisher_filters),
            date_range_start=payload.date_range_start,
            date_range_end=payload.date_range_end,
            category_filters=list(payload.category_filters),
            tag_filters=list(payload.tag_filters),
            content_classes=["claim", "finding", "quote", "metric"],
            minimum_projection_status="projected",
        ),
        idempotency_db_path=payload.idempotency_db or settings.state_db,
        output_root=payload.output_root or settings.output_dir,
        max_evidence_items=max_evidence_items,
        max_signals=8,
        max_prompt_chars=max_prompt_chars,
        retry_retries=2,
        retry_base_delay_seconds=1.0,
        retry_backoff_step_seconds=1.0,
        retry_jitter_seconds=0.25,
        publish_target_route="wordpress:ml_briefing",
    )


def _signal_analysis_request(
    *,
    request_id: str,
    topic: str,
    category_filters: list[str],
    tag_filters: list[str],
    publisher_filters: list[str],
    date_range_start: str | None,
    date_range_end: str | None,
    max_source_reports: int,
    publication_mode: PublicationMode,
) -> CrossReportAnalysisRequest:
    return CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id=request_id,
        topic=topic,
        auto_theme=False,
        category_filters=category_filters,
        tag_filters=tag_filters,
        publisher_filters=publisher_filters,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        max_source_reports=max_source_reports,
        diagnostic=False,
        override_publishability=True,
        publication_mode=publication_mode,
    )


def _signal_candidate_request(
    payload: SignalCandidateExtractionUiRunPayload,
    settings: Any,
) -> SignalCandidateExtractionRequest:
    max_source_reports = payload.max_source_reports or int(
        getattr(settings, "cross_report_analysis_max_source_reports", 6)
    )
    max_evidence_items = payload.max_evidence_items or int(
        getattr(settings, "cross_report_analysis_max_evidence_items", 48)
    )
    max_signals = payload.max_signals or 8
    material = {
        "topic": payload.topic,
        "category_filters": payload.category_filters,
        "tag_filters": payload.tag_filters,
        "publisher_filters": payload.publisher_filters,
        "date_range_start": payload.date_range_start,
        "date_range_end": payload.date_range_end,
        "max_source_reports": max_source_reports,
        "max_evidence_items": max_evidence_items,
        "max_signals": max_signals,
    }
    extraction_id = payload.extraction_request_id or _stable_request_id(
        "ui-signal-candidates", material
    )
    analysis_request = _signal_analysis_request(
        request_id=extraction_id,
        topic=payload.topic,
        category_filters=list(payload.category_filters),
        tag_filters=list(payload.tag_filters),
        publisher_filters=list(payload.publisher_filters),
        date_range_start=payload.date_range_start,
        date_range_end=payload.date_range_end,
        max_source_reports=max_source_reports,
        publication_mode="generate_only",
    )
    return SignalCandidateExtractionRequest(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        extraction_request_id=extraction_id,
        analysis_request=analysis_request,
        projected_data_request=CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=settings.reports_db,
            publisher_filters=list(payload.publisher_filters),
            date_range_start=payload.date_range_start,
            date_range_end=payload.date_range_end,
            category_filters=list(payload.category_filters),
            tag_filters=list(payload.tag_filters),
            content_classes=["claim", "finding", "quote", "metric"],
            minimum_projection_status="projected",
        ),
        db_path=payload.signal_store_db or settings.signal_store_db or settings.reports_db,
        max_evidence_items=max_evidence_items,
        max_signals=max_signals,
        generated_at_utc="",
    )


def _signal_post_request(
    payload: SignalPostUiRunPayload,
    settings: Any,
) -> SignalPostWorkflowRequest:
    max_source_reports = payload.max_source_reports or 3
    max_evidence_items = payload.max_evidence_items or 6
    material = {
        "topic": payload.topic,
        "category_filters": payload.category_filters,
        "tag_filters": payload.tag_filters,
        "publisher_filters": payload.publisher_filters,
        "date_range_start": payload.date_range_start,
        "date_range_end": payload.date_range_end,
        "max_source_reports": max_source_reports,
        "max_evidence_items": max_evidence_items,
        "publication_mode": payload.publication_mode,
    }
    request_id = payload.request_id or _stable_request_id("ui-signal-post", material)
    return SignalPostWorkflowRequest(
        schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
        request_id=request_id,
        generation_request=SignalPostGenerationRequest(
            schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
            request_id=request_id,
            topic=payload.topic,
            category_filters=list(payload.category_filters),
            tag_filters=list(payload.tag_filters),
            publisher_filters=list(payload.publisher_filters),
            date_range_start=payload.date_range_start,
            date_range_end=payload.date_range_end,
            max_source_reports=max_source_reports,
            max_evidence_items=max_evidence_items,
            minimum_source_reports=payload.minimum_source_reports or 2,
            minimum_evidence_items=payload.minimum_evidence_items or 2,
            target_route="wordpress:ml_signal",
        ),
        db_path=settings.reports_db,
        output_root=payload.output_root or settings.output_dir,
        publication_mode=cast(PublicationMode, payload.publication_mode),
        signal_store_db=payload.signal_store_db
        or settings.signal_store_db
        or settings.reports_db,
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
    if run_type in {
        "cross_report_analysis",
        "signal_candidate_extraction",
        "signal_post",
    }:
        app_settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), ctx
        )
        return {"run_type": run_type, "settings": _sanitize_snapshot(app_settings)}
    if run_type == "ui_run_replay":
        app_settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=""), ctx
        )
        replay_payload = _validate_ui_run_payload(run_type=run_type, payload=payload)
        assert isinstance(replay_payload, UiRunReplayUiRunPayload)
        return {
            "run_type": run_type,
            "registry_path": replay_payload.registry_path
            or default_ui_run_registry_path(app_settings.state_db),
            "run_id": replay_payload.run_id,
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
        elif run_type == "cross_report_analysis":
            assert isinstance(validated_payload, CrossReportAnalysisUiRunPayload)
            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            cross_report_request = _cross_report_analysis_request(
                validated_payload,
                app_settings,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(app_settings),
                "request": _sanitize_snapshot(cross_report_request),
            }
            publish_settings = None
            if validated_payload.publication_mode == "publish_live":
                publish_settings = load_publish_settings(
                    ConfigLoadRequest(schema_version="1.0", path=""),
                    ctx,
                )
            outcome = run_cross_report_analysis(
                cross_report_request,
                app_settings,
                ctx,
                publish_settings=publish_settings,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "status": outcome.status,
                    "request_id": outcome.request.request_id,
                    "selected_theme": outcome.generated_result.selected_theme.label,
                    "selected_report_count": len(
                        outcome.generated_result.selected_sources
                    ),
                    "validation_status": outcome.validation_result.status,
                    "publication_mode": outcome.publish_result.publication_mode,
                    "publish_status": outcome.publish_result.status,
                    "post_url": outcome.publish_result.post_url or "",
                    "idempotency_reused": outcome.idempotency_reused,
                },
                artifact_paths=[
                    path
                    for path in [
                        outcome.artifact_path,
                        getattr(outcome.publish_package, "html_path", ""),
                    ]
                    if path
                ],
                config_snapshot=config_snapshot,
            )
        elif run_type == "signal_candidate_extraction":
            assert isinstance(
                validated_payload,
                SignalCandidateExtractionUiRunPayload,
            )
            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            candidate_request = _signal_candidate_request(
                validated_payload,
                app_settings,
            )
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(app_settings),
                "request": _sanitize_snapshot(candidate_request),
            }
            outcome = run_signal_candidate_extraction(candidate_request, ctx)
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "status": outcome.status,
                    "extraction_request_id": outcome.extraction_request_id,
                    "candidate_count": outcome.candidate_count,
                    "group_count": outcome.group_count,
                    "stored_candidate_count": outcome.stored_response.candidate_count,
                    "stored_group_count": outcome.stored_response.group_count,
                },
                artifact_paths=[],
                config_snapshot=config_snapshot,
            )
        elif run_type == "signal_post":
            assert isinstance(validated_payload, SignalPostUiRunPayload)
            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            signal_request = _signal_post_request(validated_payload, app_settings)
            config_snapshot = {
                "run_type": run_type,
                "settings": _sanitize_snapshot(app_settings),
                "request": _sanitize_snapshot(signal_request),
            }
            publish_settings = None
            if validated_payload.publication_mode == "publish_live":
                publish_settings = load_publish_settings(
                    ConfigLoadRequest(schema_version="1.0", path=""),
                    ctx,
                )
            result = run_signal_post_workflow(
                signal_request,
                ctx,
                publish_settings=publish_settings,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded",
                result_summary={
                    "request_id": result.request_id,
                    "title": result.projection.title,
                    "slug": result.projection.slug,
                    "confidence": result.projection.confidence,
                    "validation_status": result.projection.validation_status,
                    "publish_status": result.publish_result.status,
                    "target_route": result.publish_result.target_route,
                    "post_url": result.publish_result.post_url or "",
                },
                artifact_paths=[],
                config_snapshot=config_snapshot,
            )
        elif run_type == "ui_run_replay":
            assert isinstance(validated_payload, UiRunReplayUiRunPayload)
            from src.orchestrators.ui_run_replay_orchestrator import replay_ui_run

            app_settings = load_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            )
            registry_path = (
                validated_payload.registry_path
                or default_ui_run_registry_path(app_settings.state_db)
            )
            config_snapshot = {
                "run_type": run_type,
                "registry_path": registry_path,
                "run_id": validated_payload.run_id,
            }
            result = replay_ui_run(
                request=UiRunReplayRequest(
                    schema_version="1.0",
                    registry_path=registry_path,
                    run_id=RunId(validated_payload.run_id),
                ),
                ctx=ctx,
            )
            response = _execution_response(
                worker_request=worker_request,
                status="succeeded" if result.report.matched else "failed",
                result_summary={
                    "original_run_id": str(result.original_record.run_id),
                    "original_run_type": result.original_record.run_type,
                    "replay_status": result.report.replay_status,
                    "matched": result.report.matched,
                    "delta_count": len(result.report.deltas),
                    "manifest_path": result.manifest_path,
                    "report_path": result.report_path,
                },
                artifact_paths=[result.manifest_path, result.report_path],
                config_snapshot=config_snapshot,
                error_code="" if result.report.matched else "ui_run_replay_mismatch",
                error_message=""
                if result.report.matched
                else "UI run replay completed with deltas.",
                error_retryable=False,
                error_severity="error",
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
