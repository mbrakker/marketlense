from __future__ import annotations

import pytest

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportEvidenceReference,
    CrossReportProjectedDataReadResponse,
    CrossReportSourceReportCandidate,
)
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPostGenerationRequest,
    SignalPublishProjection,
)
from src.generators.signal_post_generator import build_signal_publish_projection
from src.utils.errors import AppError


def _candidate(
    report_id: str,
    *,
    publisher: str,
    evidence_count: int = 2,
    category_ids: list[str] | None = None,
    category_labels: list[str] | None = None,
    tags: list[str] | None = None,
) -> CrossReportSourceReportCandidate:
    return CrossReportSourceReportCandidate(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id=report_id,
        title=f"{publisher} AI Commerce Report",
        publisher=publisher,
        publisher_id=publisher.lower().replace(" ", "-"),
        report_date="2026-05-20",
        projection_status="projected",
        content_hash=f"{report_id}-hash",
        category_labels=category_labels or ["Retail Strategy"],
        tags=tags or ["AI Commerce"],
        evidence_count=evidence_count,
        claim_count=evidence_count,
        finding_count=0,
        quote_count=0,
        metric_count=0,
        recency_score=0.0,
        relevance_score=0.0,
        diversity_score=0.0,
        density_score=float(evidence_count),
        total_score=0.0,
        selection_reasons=["projection_status:projected"],
        rejection_reasons=[],
        category_ids=category_ids or ["retail-strategy"],
    )


def _evidence(evidence_id: str, *, report_id: str, publisher: str) -> CrossReportEvidenceReference:
    return CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id=evidence_id,
        report_id=report_id,
        publisher=publisher,
        title=f"{publisher} AI Commerce Report",
        source_table="report_claims",
        entity_uid=f"{report_id}:claim:{evidence_id}",
        content_class="claim",
        text=f"{publisher} reports that AI commerce adoption is changing checkout behavior.",
        source_metadata={"pages": [2], "evidence": "projected claim"},
    )


def _projected_data() -> CrossReportProjectedDataReadResponse:
    return CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[
            _candidate("report-a", publisher="Publisher A"),
            _candidate("report-b", publisher="Publisher B"),
        ],
        evidence=[
            _evidence("report-a:claim:1", report_id="report-a", publisher="Publisher A"),
            _evidence("report-b:claim:1", report_id="report-b", publisher="Publisher B"),
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )


def _request() -> SignalPostGenerationRequest:
    return SignalPostGenerationRequest(
        schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
        request_id="signal-ai-commerce",
        topic="AI commerce checkout behavior",
        category_filters=["Retail Strategy"],
        tag_filters=["AI Commerce"],
        publisher_filters=[],
        date_range_start=None,
        date_range_end=None,
        max_source_reports=3,
        max_evidence_items=6,
        minimum_source_reports=2,
        minimum_evidence_items=2,
    )


def test_signal_generator_builds_grounded_publish_projection(
    run_context,
    assert_no_defaulted_required_fields,
) -> None:
    projection = build_signal_publish_projection(
        _request(),
        _projected_data(),
        run_context,
    )

    assert isinstance(projection, SignalPublishProjection)
    assert_no_defaulted_required_fields(projection)
    assert projection.schema_version == WORDPRESS_ENTITY_SCHEMA_VERSION
    assert projection.target_route == "wordpress:ml_signal"
    assert projection.title == "AI commerce checkout behavior signal"
    assert projection.slug == "ai-commerce-checkout-behavior-signal"
    assert projection.evidence_ids == ["report-a:claim:1", "report-b:claim:1"]
    assert projection.source_report_ids == ["report-a", "report-b"]
    assert projection.topic_ids == ["retail-strategy"]
    assert projection.topic_labels == ["Retail Strategy"]
    assert projection.tag_labels == ["AI Commerce"]
    assert projection.publisher_labels == ["Publisher A", "Publisher B"]
    assert projection.validation_status == "approved"
    assert projection.confidence >= 0.7
    assert "projected evidence" in projection.uncertainty
    assert "report-a:claim:1" in projection.body_html
    assert "Publisher A" in projection.body_html


def test_signal_generator_rejects_insufficient_grounding(run_context) -> None:
    projected_data = CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[_candidate("report-a", publisher="Publisher A")],
        evidence=[
            _evidence("report-a:claim:1", report_id="report-a", publisher="Publisher A")
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )

    with pytest.raises(AppError) as exc_info:
        build_signal_publish_projection(_request(), projected_data, run_context)

    assert exc_info.value.code == "signal_grounding_insufficient"
    assert exc_info.value.retryable is False
    assert exc_info.value.severity == "error"
