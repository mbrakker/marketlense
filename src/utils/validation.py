from __future__ import annotations

from src.contracts.candidates import Candidate
from src.contracts.report_models import ReportPayload
from src.contracts.validation import ValidationIssue, ValidationReport


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
        raise ValueError("ReportPayload.region is required (use empty string if unknown)")
    if payload.time_period is None:
        raise ValueError("ReportPayload.time_period is required (use empty string if unknown)")
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
