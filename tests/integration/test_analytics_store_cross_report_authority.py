from __future__ import annotations

import sqlite3

import pytest

from src.contracts.analytics_projection import (
    PROJECTION_SCHEMA_VERSION,
    AnalyticsProjectionUpsertRequest,
)
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportProjectedDataReadRequest,
)
from src.services.analytics_store_service import (
    read_cross_report_projected_data,
    upsert_projection,
)
from tests.integration.test_analytics_store_cross_report_reads import _batch, _ctx


@pytest.mark.integration
def test_cross_report_read_recomputes_normal_eligibility_from_validation_state(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "normal-validation.sqlite")
    ctx = _ctx()
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=db_path,
            batch=_batch(
                "report-normal",
                title="Normal report",
                publisher="Publisher A",
                publisher_id="publisher-a",
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
            "UPDATE reports SET validation_status = '', validation_severity = '', "
            "source_validation_eligible = 1 WHERE report_id = ?",
            ("report-normal",),
        )
        conn.commit()

    response = read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=db_path,
            source_report_ids=["report-normal"],
        ),
        ctx,
    )

    assert response.source_candidates[0].source_validation_eligible is False


@pytest.mark.integration
def test_verified_cross_report_read_rejects_parent_and_row_provenance_conflicts(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "verified-provenance.sqlite")
    ctx = _ctx()
    source_identity = "same-source|pdf-sha256:" + "a" * 64
    fact_digest = "b" * 64
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=db_path,
            batch=_batch(
                "report-provenance",
                title="Verified report",
                publisher="Publisher A",
                publisher_id="publisher-a",
                generated_at_utc="2026-05-01T00:00:00Z",
                tag="AI",
                category_id="retail",
                category_label="Retail",
                authority_mode="verified",
                verified_source_identity=source_identity,
                verified_source_pdf_sha256="a" * 64,
                verified_fact_digest=fact_digest,
                verified_fact_id="fact-1",
            ),
        ),
        ctx,
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE report_findings SET source_identity = ? WHERE report_id = ?",
            ("other-source|pdf-sha256:" + "c" * 64, "report-provenance"),
        )
        conn.commit()

    response = read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=db_path,
            source_report_ids=["report-provenance"],
            expected_verified_sources={
                "report-provenance": {
                    "source_identity": source_identity,
                    "source_pdf_sha256": "a" * 64,
                    "verified_fact_digest": fact_digest,
                }
            },
            content_classes=["finding", "metric"],
        ),
        ctx,
    )

    assert response.evidence == []
    assert response.raw_metrics == []
    assert response.excluded_report_counts["row_source_identity_mismatch"] == 1
    assert response.excluded_report_counts["row_metric_evidence_id_mismatch"] == 1

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE reports SET verified_source_pdf_sha256 = ? WHERE report_id = ?",
            ("c" * 64, "report-provenance"),
        )
        conn.commit()
    stale = read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=db_path,
            source_report_ids=["report-provenance"],
        ),
        ctx,
    )
    assert stale.source_candidates[0].source_validation_eligible is False
    assert stale.excluded_report_counts["verified_source_identity_pdf_mismatch"] == 1


@pytest.mark.integration
def test_verified_read_excludes_unbound_content_and_malformed_metrics(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "verified-integrity.sqlite")
    ctx = _ctx()
    source_identity = "same-source|pdf-sha256:" + "a" * 64
    fact_digest = "b" * 64
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=db_path,
            batch=_batch(
                "report-verified",
                title="Verified report",
                publisher="Publisher A",
                publisher_id="publisher-a",
                generated_at_utc="2026-05-01T00:00:00Z",
                tag="AI",
                category_id="retail",
                category_label="Retail",
                authority_mode="verified",
                verified_source_identity=source_identity,
                verified_source_pdf_sha256="a" * 64,
                verified_fact_digest=fact_digest,
                verified_fact_id="fact-1",
            ),
        ),
        ctx,
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE report_metrics SET metric_context_json = ? WHERE report_id = ?",
            ("{malformed", "report-verified"),
        )
        conn.commit()

    response = read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=db_path,
            source_report_ids=["report-verified"],
            expected_verified_sources={
                "report-verified": {
                    "source_identity": source_identity,
                    "source_pdf_sha256": "a" * 64,
                    "verified_fact_digest": fact_digest,
                }
            },
            content_classes=["claim", "finding", "quote", "metric"],
        ),
        ctx,
    )

    assert [item.content_class for item in response.evidence] == ["finding"]
    assert response.raw_metrics == []
    assert response.source_candidates[0].claim_count == 0
    assert response.source_candidates[0].quote_count == 0
    assert response.excluded_report_counts["row_metric_context_malformed"] == 1


@pytest.mark.integration
def test_verified_cross_report_read_accepts_exactly_bound_claim_and_quote(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "verified-bound-context.sqlite")
    ctx = _ctx()
    source_identity = "same-source|pdf-sha256:" + "a" * 64
    fact_digest = "b" * 64
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=db_path,
            batch=_batch(
                "report-verified",
                title="Verified report",
                publisher="Publisher A",
                publisher_id="publisher-a",
                generated_at_utc="2026-05-01T00:00:00Z",
                tag="AI",
                category_id="retail",
                category_label="Retail",
                authority_mode="verified",
                verified_source_identity=source_identity,
                verified_source_pdf_sha256="a" * 64,
                verified_fact_digest=fact_digest,
                verified_fact_id="fact-1",
            ),
        ),
        ctx,
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE report_claims SET evidence_id = ?, pages_json = ? WHERE report_id = ?",
            ("verified-fact:fact-1", "[2]", "report-verified"),
        )
        conn.execute(
            "UPDATE report_quotes SET evidence_id = ?, page = ? WHERE report_id = ?",
            ("verified-fact:fact-1", 2, "report-verified"),
        )
        conn.commit()

    response = read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=db_path,
            source_report_ids=["report-verified"],
            expected_verified_sources={
                "report-verified": {
                    "source_identity": source_identity,
                    "source_pdf_sha256": "a" * 64,
                    "verified_fact_digest": fact_digest,
                }
            },
            content_classes=["claim", "finding", "quote"],
        ),
        ctx,
    )

    assert {item.content_class for item in response.evidence} == {
        "claim",
        "finding",
        "quote",
    }
    assert {item.verified_fact_id for item in response.evidence} == {"fact-1"}
