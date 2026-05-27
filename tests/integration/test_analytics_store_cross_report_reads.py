from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import is_dataclass

import pytest

from src.contracts.analytics_projection import (
    AnalyticsProjectionBatch,
    AnalyticsProjectionFailureRequest,
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
    record_projection_failure,
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
    time_period: str = "2026",
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
        time_period=time_period,
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
            time_period="2026-05-01",
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
            time_period="2026-05-02",
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
    assert candidate.category_ids == ["retail"]
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
    assert response.raw_metrics[0].metric_id == "report-a:metric:1"
    assert response.content_hashes["report-a"]["report-a:claim:1"] == (
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


@pytest.mark.integration
def test_cross_report_projected_data_date_filter_uses_report_period_not_projection_date(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    ctx = _ctx()
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=db_path,
            batch=_batch(
                "old-report-reprojected-now",
                title="Historical Outlook",
                publisher="Publisher A",
                publisher_id="publisher-a",
                time_period="2024-01-01",
                generated_at_utc="2026-05-04T00:00:00Z",
                tag="AI",
                category_id="retail",
                category_label="Retail",
            ),
        ),
        ctx,
    )

    response = read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=db_path,
            date_range_start="2026-05-01",
            date_range_end="2026-05-31",
        ),
        ctx,
    )

    assert response.source_candidates == []


@pytest.mark.integration
def test_cross_report_projected_data_read_adapts_blank_projected_publisher(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    ctx = _ctx()
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=db_path,
            batch=_batch(
                "report-blank-publisher",
                title="Blank Publisher Outlook",
                publisher="Temporary Publisher",
                publisher_id="temporary-publisher",
                generated_at_utc="2026-05-01T00:00:00Z",
                tag="AI",
                category_id="retail",
                category_label="Retail",
            ),
        ),
        ctx,
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE reports SET publisher = '', publisher_id = '' WHERE report_id = ?",
            ("report-blank-publisher",),
        )
        conn.execute(
            "UPDATE report_quotes SET evidence_id = '' WHERE report_id = ?",
            ("report-blank-publisher",),
        )
        conn.execute(
            "UPDATE report_findings SET finding_uid = 'F1' WHERE report_id = ?",
            ("report-blank-publisher",),
        )
        conn.commit()

    response = read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=db_path,
            content_classes=["claim", "finding", "quote", "metric"],
            minimum_projection_status="projected",
        ),
        ctx,
    )

    assert response.source_candidates[0].publisher == "Unknown publisher"
    assert response.source_candidates[0].publisher_id == "Unknown publisher"
    assert {item.publisher for item in response.evidence} == {"Unknown publisher"}
    finding = next(
        item for item in response.evidence if item.content_class == "finding"
    )
    assert finding.evidence_id == "report-blank-publisher:finding:F1"
    quote = next(item for item in response.evidence if item.content_class == "quote")
    assert quote.evidence_id == "report-blank-publisher:quote:1"
    assert response.raw_metrics[0].publisher == "Unknown publisher"


@pytest.mark.integration
def test_cross_report_projected_data_read_can_return_failed_projection_inventory(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    ctx = _ctx()
    record_projection_failure(
        AnalyticsProjectionFailureRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=db_path,
            report_id="failed-report",
            projection_schema_version=PROJECTION_SCHEMA_VERSION,
            projection_version=PROJECTION_VERSION,
            error_code="projection_failed_fixture",
            error_message="Fixture failure row",
            error_retryable=False,
            generated_at_utc="2026-05-01T00:00:00Z",
        ),
        ctx,
    )

    response = read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=db_path,
            minimum_projection_status="failed",
        ),
        ctx,
    )

    assert [candidate.report_id for candidate in response.source_candidates] == [
        "failed-report"
    ]
    candidate = response.source_candidates[0]
    assert candidate.projection_status == "failed"
    assert candidate.selection_reasons == ["projection_status:failed"]
    assert candidate.publisher == "failed-report"
    assert candidate.category_labels == []
    assert candidate.tags == []
