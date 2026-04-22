from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from typing import Any, Iterable

from src.contracts.candidates import Candidate
from src.contracts.report_models import ReportPayload
from src.contracts.validation import ValidationIssue, ValidationReport
from src.utils.errors import AppError


def assert_required_dataclass_fields_populated(
    obj: Any,
    *,
    contract_name: str | None = None,
    sentinel_values: Iterable[str] = (),
) -> None:
    if not is_dataclass(obj):
        raise AppError(
            code="contract_validation_type_error",
            message="Expected a dataclass contract instance.",
            retryable=False,
            context={"contract": contract_name or type(obj).__name__},
        )

    sentinels = {
        str(value).strip().lower() for value in sentinel_values if str(value).strip()
    }
    missing: list[str] = []
    for field_def in fields(obj):
        is_required = (
            field_def.default is MISSING and field_def.default_factory is MISSING
        )
        if not is_required:
            continue
        value = getattr(obj, field_def.name)
        if _is_defaulted_required_value(value, sentinels):
            missing.append(field_def.name)

    if missing:
        name = contract_name or type(obj).__name__
        raise AppError(
            code="contract_required_field_missing",
            message=f"{name} required fields are empty/defaulted: {', '.join(missing)}",
            retryable=False,
            severity="error",
            context={"contract": name, "fields": missing},
        )


def _is_defaulted_required_value(value: Any, sentinel_values: set[str]) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        normalized = value.strip().lower()
        return not normalized or normalized in sentinel_values
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def validate_report_payload(payload: ReportPayload) -> None:
    if not payload.schema_version:
        raise ValueError("ReportPayload.schema_version is required")
    if not (payload.title or "").strip():
        raise ValueError("ReportPayload.title is required")
    if not isinstance(payload.insights, list) or len(payload.insights) != 5:
        raise ValueError("ReportPayload.insights must contain exactly 5 items")
    if not isinstance(payload.taxonomy, list):
        raise ValueError("ReportPayload.taxonomy must be a list")
    if not isinstance(payload.categories, list):
        raise ValueError("ReportPayload.categories must be a list")
    if len(payload.categories) > 3:
        raise ValueError("ReportPayload.categories must contain at most 3 items")
    if payload.region is None:
        raise ValueError(
            "ReportPayload.region is required (use empty string if unknown)"
        )
    if payload.time_period is None:
        raise ValueError(
            "ReportPayload.time_period is required (use empty string if unknown)"
        )
    if not payload.quote.text:
        raise ValueError("ReportPayload.quote.text is required")
    if not payload.figure.title and not payload.figure.evidence:
        raise ValueError("ReportPayload.figure requires title or evidence")


def validate_candidate(candidate: Candidate) -> None:
    if not candidate.schema_version:
        raise ValueError("Candidate.schema_version is required")
    if not candidate.id:
        raise ValueError("Candidate.id is required")
    if candidate.kind not in ("chart", "table"):
        raise ValueError("Candidate.kind must be 'chart' or 'table'")


def parse_validation_report_payload(
    payload: object, *, source_path: str = ""
) -> ValidationReport:
    data = payload if isinstance(payload, dict) else {}
    issues_payload = data.get("issues") if isinstance(data, dict) else []
    issues: list[ValidationIssue] = []
    if isinstance(issues_payload, list):
        for item in issues_payload:
            if not isinstance(item, dict):
                continue
            issues.append(
                ValidationIssue(
                    schema_version=str(item.get("schema_version", "1.0")),
                    message=str(item.get("message", "")),
                    severity=str(item.get("severity", "warning")),
                    affected_section=str(item.get("affected_section", "")),
                    rule_id=str(item.get("rule_id", "")),
                    repair_target=str(item.get("repair_target", "")),
                    entity_id=str(item.get("entity_id", "")),
                )
            )
    status = str(data.get("status") or "fail")
    severity = str(data.get("severity") or ("error" if status != "pass" else "pass"))
    severity_norm = severity if severity in {"pass", "warning", "error"} else "error"
    return ValidationReport(
        schema_version=str(data.get("schema_version", "1.1")),
        status=status,
        severity=severity_norm,
        issues=issues,
        source_path=source_path,
    )
