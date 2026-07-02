"""Payload metadata and completeness checks for report analysis.

This module owns local payload adaptation and contract completeness validation;
it does not decide workflow sequencing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.orchestrators._report_analysis_orchestrator.shared import logger
from src.utils.analysis_family import family_is_abstained
from src.utils.errors import AppError
from src.utils.logging import log_event

__all__ = [
    "REPORT_PAYLOAD_SENTINELS",
    "_attach_payload_analysis_metadata",
    "_ensure_report_payload_complete",
    "_serialize_context_category_fit_payload",
]


def _serialize_context_category_fit_payload(fit_response) -> dict[str, Any]:
    return {
        "schema_version": str(fit_response.schema_version or "1.0"),
        "selected_category_ids": list(fit_response.categories or []),
        "category_fits": [
            {
                "category_id": str(fit.category_id),
                "label": str(fit.label),
                "fit_score": float(fit.fit_score),
                "decision": str(fit.decision),
                "why_fit": str(fit.why_fit),
                "why_not_fit": str(fit.why_not_fit),
                "evidence_sections": list(fit.evidence_sections or []),
                "semantic_rule_status": str(
                    getattr(fit, "semantic_rule_status", "not_evaluated")
                ),
                "supported_topic_rules": list(
                    getattr(fit, "supported_topic_rules", []) or []
                ),
                "rejected_topic_rules": list(
                    getattr(fit, "rejected_topic_rules", []) or []
                ),
                "remediation_signal": str(
                    getattr(fit, "remediation_signal", "") or ""
                ),
            }
            for fit in fit_response.fits
        ],
    }


def _attach_payload_analysis_metadata(
    payload,
    *,
    vector_store_id: Optional[str],
    evidence_paths: Dict[str, str],
):
    payload._vector_store_id = str(vector_store_id or "")
    payload._evidence_packs = dict(evidence_paths)
    return payload


REPORT_PAYLOAD_SENTINELS = {"not available from text"}


def _ensure_report_payload_complete(
    payload,
    *,
    artifacts: Optional[Dict[str, Any]] = None,
    ctx,
    file_id: str,
    stage: str,
) -> None:
    missing_fields: List[str] = []
    artifact_payload = artifacts if isinstance(artifacts, dict) else {}
    summary_abstained = family_is_abstained(artifact_payload, "summary")
    insights_abstained = family_is_abstained(artifact_payload, "insights_bundle")
    quotes_abstained = family_is_abstained(artifact_payload, "quotes")

    def _missing_text(value: Any) -> bool:
        text = str(value or "").strip()
        return not text or text.lower() in REPORT_PAYLOAD_SENTINELS

    if _missing_text(payload.title):
        missing_fields.append("title")
    if not summary_abstained and _missing_text(payload.tldr):
        missing_fields.append("tldr")
    if not summary_abstained and _missing_text(payload.commentary):
        missing_fields.append("commentary")
    insights = list(payload.insights or [])
    if not insights_abstained and len(insights) < 5:
        missing_fields.append("insights")
    if not insights_abstained:
        for index in range(5):
            insight = insights[index] if index < len(insights) else ""
            if _missing_text(insight):
                missing_fields.append(f"insights[{index}]")
    if not quotes_abstained and _missing_text(payload.quote.text):
        missing_fields.append("quote.text")
    if bool(getattr(payload, "_figure_section_enabled", True)):
        if _missing_text(payload.figure.title):
            missing_fields.append("figure.title")
        if _missing_text(payload.figure.evidence):
            missing_fields.append("figure.evidence")

    if not missing_fields:
        return

    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_payload_incomplete",
            module=logger.name,
            fields={
                "file_id": file_id,
                "stage": stage,
                "missing_fields": missing_fields,
            },
        )
    )
    raise AppError(
        code="report_payload_incomplete",
        message="Report payload is missing required semantic fields",
        retryable=False,
        context={
            "file_id": file_id,
            "stage": stage,
            "missing_fields": missing_fields,
        },
    )
