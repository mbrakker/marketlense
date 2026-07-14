from __future__ import annotations

from datetime import date
from typing import Any

from src.contracts.report_card_remediation import (
    ReportCardPublicationDateRemediationRequest,
    ReportCardPublicationDateRemediationResult,
)
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError

_REQUIRED_REGISTRY_IDS = {"doc_map", "artifacts", "validation"}


def _normalize_iso_date(value: object) -> str:
    text = str(value or "").strip()
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        candidate = text[:10]
        try:
            date.fromisoformat(candidate)
        except ValueError:
            return ""
        return candidate
    return ""


def _first_dict(*values: object) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _source_date_candidates(
    *,
    artifacts_payload: dict[str, Any],
    doc_map_payload: dict[str, Any],
) -> list[tuple[str, object]]:
    summary = _first_dict(artifacts_payload.get("summary"))
    doc_metadata = _first_dict(
        doc_map_payload.get("metadata"),
        doc_map_payload.get("source_metadata"),
        doc_map_payload.get("doc_metadata"),
    )
    return [
        ("artifacts.publication_date", artifacts_payload.get("publication_date")),
        ("artifacts.published_date", artifacts_payload.get("published_date")),
        ("artifacts.report_date", artifacts_payload.get("report_date")),
        ("artifacts.summary.publication_date", summary.get("publication_date")),
        ("artifacts.summary.published_date", summary.get("published_date")),
        ("artifacts.summary.report_date", summary.get("report_date")),
        ("doc_map.publication_date", doc_map_payload.get("publication_date")),
        ("doc_map.published_date", doc_map_payload.get("published_date")),
        ("doc_map.report_date", doc_map_payload.get("report_date")),
        ("doc_map.publicationDate", doc_map_payload.get("publicationDate")),
        ("doc_map.publishedDate", doc_map_payload.get("publishedDate")),
        ("doc_map.metadata.publication_date", doc_metadata.get("publication_date")),
        ("doc_map.metadata.published_date", doc_metadata.get("published_date")),
        ("doc_map.metadata.report_date", doc_metadata.get("report_date")),
    ]


def normalize_source_supported_publication_date(
    *,
    artifacts_payload: dict[str, Any],
    doc_map_payload: dict[str, Any] | None = None,
) -> tuple[str, str]:
    doc_map = doc_map_payload if isinstance(doc_map_payload, dict) else {}
    for source, raw_value in _source_date_candidates(
        artifacts_payload=artifacts_payload,
        doc_map_payload=doc_map,
    ):
        normalized = _normalize_iso_date(raw_value)
        if normalized:
            return normalized, source
    return "", ""


def _registry_ref_paths(request: ReportCardPublicationDateRemediationRequest) -> dict[str, str]:
    registry = request.artifact_registry.validate()
    return {ref.artifact_id: ref.path for ref in registry.refs}


def remediate_report_card_publication_date(
    request: ReportCardPublicationDateRemediationRequest,
) -> ReportCardPublicationDateRemediationResult:
    ref_paths = _registry_ref_paths(request)
    missing_refs = sorted(_REQUIRED_REGISTRY_IDS - set(ref_paths))
    if missing_refs:
        raise AppError(
            code="report_card_publication_date_registry_missing",
            message="Publication-date remediation requires typed registry artifact refs",
            retryable=False,
            severity="error",
            context={"file_id": request.file_id, "missing_refs": missing_refs},
        )
    if request.rendered_html_path and ref_paths.get("rendered_html") != request.rendered_html_path:
        raise AppError(
            code="report_card_publication_date_registry_mismatch",
            message="Rendered HTML path must come from the typed artifact registry",
            retryable=False,
            severity="error",
            context={
                "file_id": request.file_id,
                "registry_rendered_html": ref_paths["rendered_html"],
                "rendered_html_path": request.rendered_html_path,
            },
        )

    publication_date, date_source = normalize_source_supported_publication_date(
        artifacts_payload=request.artifacts_payload,
        doc_map_payload=request.doc_map_payload,
    )
    audit_fields: dict[str, str] = {
        "repair_source": date_source,
        "operator_id": "",
        "operator_reason": "",
    }
    if not publication_date:
        operator_date = _normalize_iso_date(request.operator_date)
        if not operator_date:
            raise AppError(
                code="report_card_publication_date_absent",
                message=(
                    "Publication-date remediation requires a source-supported date "
                    "or an explicit audited operator date"
                ),
                retryable=False,
                severity="error",
                context={"file_id": request.file_id},
            )
        operator_id = str(request.operator_id or "").strip()
        operator_reason = str(request.operator_reason or "").strip()
        if not operator_id or not operator_reason:
            raise AppError(
                code="report_card_publication_date_operator_audit_missing",
                message="Operator date overrides require operator_id and operator_reason",
                retryable=False,
                severity="error",
                context={"file_id": request.file_id},
            )
        publication_date = operator_date
        date_source = "operator_override"
        audit_fields = {
            "repair_source": date_source,
            "operator_id": operator_id,
            "operator_reason": operator_reason,
        }

    idempotency_key = sha256_json(
        {
            "schema_version": "1.0",
            "file_id": request.file_id,
            "publication_date": publication_date,
            "date_source": date_source,
            "rendered_html_path": request.rendered_html_path,
            "resume_stage": request.resume_stage,
        }
    )
    return ReportCardPublicationDateRemediationResult(
        schema_version="1.0",
        file_id=request.file_id,
        publication_date=publication_date,
        date_source=date_source,
        audit_fields=audit_fields,
        resume_stage=request.resume_stage,
        idempotency_key=idempotency_key,
    )
