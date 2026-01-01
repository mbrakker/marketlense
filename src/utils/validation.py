from __future__ import annotations

from src.contracts.candidates import Candidate
from src.contracts.report_models import ReportPayload


def validate_report_payload(payload: ReportPayload) -> None:
    if not payload.schema_version:
        raise ValueError("ReportPayload.schema_version is required")
    if not (payload.title or "").strip():
        raise ValueError("ReportPayload.title is required")
    if not isinstance(payload.insights, list) or len(payload.insights) != 5:
        raise ValueError("ReportPayload.insights must contain exactly 5 items")
    if not isinstance(payload.taxonomy, list):
        raise ValueError("ReportPayload.taxonomy must be a list")
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
