from __future__ import annotations

import json
import logging
from dataclasses import asdict

from src.contracts.acquisition_audit import (
    AcquisitionAuditBatchResult,
    AcquisitionAuditCandidateResult,
    AcquisitionAuditPublisherSummary,
)
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.acquisition_audit_generator")


def build_acquisition_audit_candidate(
    *,
    publisher_name: str,
    publisher_insights_url: str,
    publisher_discovery_route_kind: str,
    publisher_recommended_discovery_route_kind: str,
    candidate_trace: PublisherInventoryCandidateTrace,
    acquisition_route_kind: str,
    acquisition_outcome: str,
    acquisition_route_summary: str | None,
    acquisition_final_page_url: str | None,
    encountered_form_fields: list[str],
    downloaded_file_path: str | None,
    error_code: str | None,
    error_message: str | None,
    ctx: RunContext,
) -> AcquisitionAuditCandidateResult:
    recommended_report_flow, recommendation_reason = _recommend_report_flow(
        acquisition_outcome=acquisition_outcome,
        acquisition_route_kind=acquisition_route_kind,
        error_code=error_code,
    )
    result = AcquisitionAuditCandidateResult(
        schema_version="1.0",
        publisher_name=publisher_name,
        publisher_insights_url=publisher_insights_url,
        publisher_discovery_route_kind=publisher_discovery_route_kind,
        publisher_recommended_discovery_route_kind=publisher_recommended_discovery_route_kind,
        report_url=candidate_trace.canonical_url,
        report_title=candidate_trace.title,
        discovered_on_page_number=candidate_trace.discovered_on_page_number,
        source_page_urls=list(candidate_trace.source_page_urls),
        discovery_provenances=list(candidate_trace.discovery_provenances),
        acquisition_route_kind=acquisition_route_kind,
        acquisition_outcome=acquisition_outcome,
        recommended_report_flow=recommended_report_flow,
        recommendation_reason=recommendation_reason,
        acquisition_route_summary=acquisition_route_summary,
        acquisition_final_page_url=acquisition_final_page_url,
        encountered_form_fields=list(encountered_form_fields),
        downloaded_file_path=downloaded_file_path,
        error_code=error_code,
        error_message=error_message,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="acquisition_audit_candidate_built",
            module=logger.name,
            fields={
                "publisher_name": result.publisher_name,
                "report_url": result.report_url,
                "acquisition_route_kind": result.acquisition_route_kind,
                "acquisition_outcome": result.acquisition_outcome,
                "recommended_report_flow": result.recommended_report_flow,
            },
        )
    )
    return result


def build_acquisition_audit_publisher_summary(
    *,
    publisher_name: str,
    insights_url: str,
    discovery_route_kind: str,
    discovery_quality_band: str,
    recommended_discovery_route_kind: str,
    candidates: list[AcquisitionAuditCandidateResult],
    ctx: RunContext,
) -> AcquisitionAuditPublisherSummary:
    discovery_provenance_counts = _count_strings(
        provenance
        for candidate in candidates
        for provenance in candidate.discovery_provenances
    )
    acquisition_route_counts = _count_strings(
        candidate.acquisition_route_kind for candidate in candidates
    )
    acquisition_outcome_counts = _count_strings(
        candidate.acquisition_outcome for candidate in candidates
    )
    downloaded_count = acquisition_outcome_counts.get("downloaded", 0)
    email_requested_count = acquisition_outcome_counts.get("email_requested", 0)
    email_required_count = acquisition_outcome_counts.get("email_required", 0)
    failed_count = sum(
        count
        for outcome, count in acquisition_outcome_counts.items()
        if outcome.startswith("failed")
    )
    recommended_publisher_flow, recommendation_reason = _recommend_publisher_flow(
        candidate_count=len(candidates),
        downloaded_count=downloaded_count,
        email_requested_count=email_requested_count,
        email_required_count=email_required_count,
        failed_count=failed_count,
    )
    result = AcquisitionAuditPublisherSummary(
        schema_version="1.0",
        publisher_name=publisher_name,
        insights_url=insights_url,
        discovery_route_kind=discovery_route_kind,
        discovery_quality_band=discovery_quality_band,
        recommended_discovery_route_kind=recommended_discovery_route_kind,
        recommended_publisher_flow=recommended_publisher_flow,
        recommendation_reason=recommendation_reason,
        current_candidate_count=len(candidates),
        downloaded_count=downloaded_count,
        email_requested_count=email_requested_count,
        email_required_count=email_required_count,
        failed_count=failed_count,
        discovery_provenance_counts=discovery_provenance_counts,
        acquisition_route_counts=acquisition_route_counts,
        acquisition_outcome_counts=acquisition_outcome_counts,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="acquisition_audit_publisher_summary_built",
            module=logger.name,
            fields={
                "publisher_name": result.publisher_name,
                "candidate_count": result.current_candidate_count,
                "recommended_publisher_flow": result.recommended_publisher_flow,
            },
        )
    )
    return result


def serialize_acquisition_audit_result(
    result: AcquisitionAuditBatchResult,
    *,
    ctx: RunContext,
) -> str:
    payload = json.dumps(asdict(result), ensure_ascii=False, indent=2)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="acquisition_audit_serialized",
            module=logger.name,
            fields={
                "publisher_count": result.publisher_count,
                "candidate_count": result.candidate_count,
                "output_path": result.output_path,
            },
        )
    )
    return payload


def _recommend_report_flow(
    *,
    acquisition_outcome: str,
    acquisition_route_kind: str,
    error_code: str | None,
) -> tuple[str, str]:
    if acquisition_outcome == "downloaded":
        return (
            "automate_pdf_download",
            "The acquisition flow produced a verified local PDF download.",
        )
    if acquisition_outcome == "email_requested":
        return (
            "automate_email_delivery",
            "The acquisition flow completed a gated email-delivery request successfully.",
        )
    if acquisition_outcome == "email_required":
        return (
            "complete_identity_profile",
            "The report is email-gated and needs a delivery email or additional identity values before automation can finish.",
        )
    if acquisition_route_kind == "failed_retryable":
        return (
            "retry_with_browser_review",
            f"The acquisition flow failed with a retryable error ({error_code or 'unknown'}).",
        )
    return (
        "manual_review",
        f"The acquisition flow did not reach a reusable terminal state ({error_code or 'no_typed_error'}).",
    )


def _recommend_publisher_flow(
    *,
    candidate_count: int,
    downloaded_count: int,
    email_requested_count: int,
    email_required_count: int,
    failed_count: int,
) -> tuple[str, str]:
    if candidate_count <= 0:
        return ("no_candidates", "Discovery produced no current candidates for this publisher.")
    if downloaded_count == candidate_count:
        return (
            "publisher_prefers_pdf_download",
            "Every audited candidate completed as a verified local PDF download.",
        )
    if email_requested_count + email_required_count == candidate_count:
        return (
            "publisher_prefers_email_delivery",
            "Every audited candidate used an email-delivery route, so future flows should prioritize gated-form handling.",
        )
    if failed_count == candidate_count:
        return (
            "manual_review_required",
            "Every audited candidate failed acquisition, so this publisher needs manual review before automation is expanded.",
        )
    if downloaded_count + email_requested_count >= max(1, candidate_count // 2):
        return (
            "mixed_automation",
            "The publisher supports multiple automatable acquisition paths, so future flows should branch by report-level outcome.",
        )
    if email_required_count > 0 and failed_count == 0:
        return (
            "identity_completion_needed",
            "The publisher looks automatable, but some reports still need delivery-email or form-identity completion.",
        )
    return (
        "manual_review_required",
        "Observed outcomes are too mixed or failure-heavy to recommend one fully automated publisher flow yet.",
    )


def _count_strings(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        token = str(value or "").strip()
        if not token:
            continue
        counts[token] = counts.get(token, 0) + 1
    return counts

