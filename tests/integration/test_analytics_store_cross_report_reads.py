from __future__ import annotations

import json
import logging
from dataclasses import is_dataclass

import pytest

from src.contracts.analytics_projection import (
    AnalyticsProjectionBatch,
    AnalyticsProjectionUpsertRequest,
    AnalyticsReportRow,
    PROJECTION_SCHEMA_VERSION,
    PROJECTION_VERSION,
    ProjectionLineage,
    ReportCategoryProjection,
    ReportClaimProjection,
    ReportFindingProjection,
    ReportMetricProjection,
    ReportQuoteProjection,
    ReportTagProjection,
    VectorProjectionQueueRow,
)
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportProjectedDataReadRequest,
)
from src.contracts.run_context import RunContext
from src.services.analytics_store_service import (
    read_cross_report_projected_data,
    upsert_projection,
)


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="cross-read-run",
        task_id="cross-read-task",
        span_id="cross-read-span",
    )


def _lineage(report_id: str) -> ProjectionLineage:
    return ProjectionLineage(
        schema_version=PROJECTION_SCHEMA_VERSION,
        projection_version=PROJECTION_VERSION,
        source_pack="fixture",
        source_ref=f"{report_id}:fixture",
        generated_at_utc="2026-05-01T00:00:00Z",
        analysis_run_id=f"{report_id}-analysis-run",
        model="gpt-5-mini",
    )


def _batch(
    report_id: str,
    *,
    title: str,
    publisher: str,
    publisher_id: str,
    generated_at_utc: str,
    tag: str,
    category_id: str,
    category_label: str,
) -> AnalyticsProjectionBatch:
    lineage = _lineage(report_id)
    report = AnalyticsReportRow(
        schema_version=PROJECTION_SCHEMA_VERSION,
        projection_version=PROJECTION_VERSION,
        report_id=report_id,
        title=title,
        publisher=publisher,
        publisher_id=publisher_id,
        source_md5=f"{report_id}-md5",
        ingest_run_id=f"{report_id}-ingest-run",
        analysis_run_id=f"{report_id}-analysis-run",
        region="US",
        time_period="2026",
        validation_status="pass",
        validation_severity="pass",
        text_density=1200.0,
        text_not_available=False,
        projection_generated_at_utc=generated_at_utc,
    )
    return AnalyticsProjectionBatch(
        schema_version=PROJECTION_SCHEMA_VERSION,
        projection_version=PROJECTION_VERSION,
        report=report,
        sections=[],
        findings=[
            ReportFindingProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                finding_uid=f"{report_id}:finding:1",
                report_id=report_id,
                finding_id="finding-1",
                text=f"{publisher} sees {tag} growth.",
                evidence=f"{title} evidence for {tag}.",
                confidence="high",
                pages=[2],
                lineage=lineage,
            )
        ],
        metrics=[
            ReportMetricProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                metric_uid=f"{report_id}:metric:1",
                report_id=report_id,
                metric_id="metric-1",
                metric="Adoption",
                value="42",
                unit="percent",
                evidence_id=f"{report_id}:finding:1",
                pages=[3],
                lineage=lineage,
            )
        ],
        quotes=[
            ReportQuoteProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                quote_uid=f"{report_id}:quote:1",
                report_id=report_id,
                quote_id="quote-1",
                text=f"{tag} is changing buying behavior.",
                speaker="Analyst",
                citation="p. 4",
                page=4,
                evidence_id=f"{report_id}:quote:1",
                lineage=lineage,
            )
        ],
        claims=[
            ReportClaimProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                claim_uid=f"{report_id}:claim:1",
                report_id=report_id,
                claim=f"{tag} adoption is accelerating.",
                evidence_id=f"{report_id}:claim:1",
                evidence=f"{publisher} claim evidence.",
                pages=[5],
                lineage=lineage,
            )
        ],
        tags=[
            ReportTagProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                tag_uid=f"{report_id}:tag:1",
                report_id=report_id,
                tag=tag,
                tag_type="primary",
                lineage=lineage,
            )
        ],
        categories=[
            ReportCategoryProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                category_uid=f"{report_id}:category:1",
                report_id=report_id,
                category_id=category_id,
                label=category_label,
                fit_score=0.91,
                decision="primary",
                selected=True,
                evidence_sections=["Market overview"],
                lineage=lineage,
            )
        ],
        figures=[],
        vector_queue=[
            VectorProjectionQueueRow(
                schema_version=PROJECTION_SCHEMA_VERSION,
                entity_uid=f"{report_id}:claim:1",
                entity_type="claim",
                report_id=report_id,
                text_payload=f"{tag} adoption is accelerating.",
                content_hash=f"{report_id}-claim-hash",
                metadata={"source_table": "report_claims"},
                content_class="evidence",
                embedding_status="pending",
                embedding_version="",
                created_at_utc=generated_at_utc,
                updated_at_utc=generated_at_utc,
            )
        ],
    )


@pytest.mark.integration
def test_cross_report_projected_data_read_filters_and_contracts(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    ctx = _ctx()
    for batch in (
        _batch(
            "report-a",
            title="AI Commerce Outlook",
            publisher="Publisher A",
            publisher_id="publisher-a",
            generated_at_utc="2026-05-01T00:00:00Z",
            tag="AI",
            category_id="retail",
            category_label="Retail",
        ),
        _batch(
            "report-b",
            title="Payments Trust Monitor",
            publisher="Publisher B",
            publisher_id="publisher-b",
            generated_at_utc="2026-05-02T00:00:00Z",
            tag="Payments",
            category_id="payments",
            category_label="Payments",
        ),
    ):
        upsert_projection(
            AnalyticsProjectionUpsertRequest(
                schema_version=PROJECTION_SCHEMA_VERSION,
                db_path=db_path,
                batch=batch,
            ),
            ctx,
        )

    caplog.set_level(logging.INFO, logger="market_lense.analytics_store_service")
    response = read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=db_path,
            publisher_filters=["Publisher A"],
            date_range_start="2026-05-01",
            date_range_end="2026-05-01",
            category_filters=["retail"],
            tag_filters=["AI"],
            content_classes=["claim", "finding", "quote", "metric"],
            minimum_projection_status="projected",
        ),
        ctx,
    )

    assert is_dataclass(response)
    assert [candidate.report_id for candidate in response.source_candidates] == [
        "report-a"
    ]
    candidate = response.source_candidates[0]
    assert candidate.projection_status == "projected"
    assert candidate.publisher == "Publisher A"
    assert candidate.category_labels == ["Retail"]
    assert candidate.tags == ["AI"]
    assert candidate.claim_count == 1
    assert candidate.finding_count == 1
    assert candidate.quote_count == 1
    assert candidate.metric_count == 1
    assert candidate.evidence_count == 3
    assert candidate.content_hash

    evidence_by_class = {item.content_class: item for item in response.evidence}
    assert set(evidence_by_class) == {"claim", "finding", "quote"}
    assert evidence_by_class["claim"].source_table == "report_claims"
    assert evidence_by_class["finding"].source_metadata["pages"] == [2]
    assert response.raw_metrics[0].raw_value == "42"
    assert response.raw_metrics[0].unit == "percent"
    assert response.content_hashes["report-a"][f"report-a:claim:1"] == (
        "report-a-claim-hash"
    )
    assert response.excluded_report_counts == {"filtered": 1}

    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.analytics_store_service"
    ]
    assert_logs_have_required_fields(events)
    assert {event["event"] for event in events} >= {
        "cross_report_projected_data_read_start",
        "cross_report_projected_data_read_complete",
    }
