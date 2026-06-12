from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

import hashlib
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any, cast

from src.contracts.cross_report_analysis import PublicationMode
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
from src.utils.errors import AppError

from .shared import *  # noqa: F401,F403
from .shared import PUBLICATION_MODES, SENSITIVE_KEY_TOKENS, UiRunPayload


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
            extraction_request_id=_optional_text(payload, "extraction_request_id")
            or "",
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


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
