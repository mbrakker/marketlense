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
def test_unknown_authority_mode_is_not_downgraded_to_normal(tmp_path) -> None:
    db_path = str(tmp_path / "unknown-authority.sqlite")
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=db_path,
            batch=_batch(
                "report-unknown",
                title="Unknown authority report",
                publisher="Publisher A",
                publisher_id="publisher-a",
                generated_at_utc="2026-06-01T00:00:00Z",
                tag="AI",
                category_id="retail",
                category_label="Retail",
                authority_mode="verfied",
            ),
        ),
        _ctx(),
    )

    response = read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=db_path,
            source_report_ids=["report-unknown"],
        ),
        _ctx(),
    )

    assert response.source_candidates[0].source_validation_eligible is False
    assert response.evidence == []
    assert response.raw_metrics == []
    assert response.excluded_report_counts["source_authority_mode_invalid"] == 1


@pytest.mark.integration
def test_verified_source_identity_requires_exact_qualified_identity(tmp_path) -> None:
    db_path = str(tmp_path / "malformed-qualified-identity.sqlite")
    identity = "source|pdf-sha256:" + "a" * 64 + "|stale"
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=db_path,
            batch=_batch(
                "report-malformed",
                title="Malformed identity report",
                publisher="Publisher A",
                publisher_id="publisher-a",
                generated_at_utc="2026-06-01T00:00:00Z",
                tag="AI",
                category_id="retail",
                category_label="Retail",
                authority_mode="verified",
                verified_source_identity=identity,
                verified_source_pdf_sha256="a" * 64,
                verified_fact_digest="b" * 64,
                verified_fact_id="fact-1",
            ),
        ),
        _ctx(),
    )

    response = read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=db_path,
            source_report_ids=["report-malformed"],
        ),
        _ctx(),
    )

    assert response.source_candidates[0].source_validation_eligible is False
    assert response.evidence == []
    assert response.excluded_report_counts["verified_source_identity_invalid"] == 1


@pytest.mark.integration
def test_verified_claim_and_quote_pages_must_belong_to_finding_binding(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "page-binding.sqlite")
    identity = "source|pdf-sha256:" + "a" * 64
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=db_path,
            batch=_batch(
                "report-pages",
                title="Page binding report",
                publisher="Publisher A",
                publisher_id="publisher-a",
                generated_at_utc="2026-06-01T00:00:00Z",
                tag="AI",
                category_id="retail",
                category_label="Retail",
                authority_mode="verified",
                verified_source_identity=identity,
                verified_source_pdf_sha256="a" * 64,
                verified_fact_digest="b" * 64,
                verified_fact_id="fact-1",
            ),
        ),
        _ctx(),
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            (
                "UPDATE report_claims SET evidence_id = ?, pages_json = ? "
                "WHERE report_id = ?"
            ),
            ("verified-fact:fact-1", "[3]", "report-pages"),
        )
        conn.execute(
            "UPDATE report_quotes SET evidence_id = ?, page = ? WHERE report_id = ?",
            ("verified-fact:fact-1", 4, "report-pages"),
        )
        conn.commit()

    response = read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=db_path,
            source_report_ids=["report-pages"],
            expected_verified_sources={
                "report-pages": {
                    "source_identity": identity,
                    "source_pdf_sha256": "a" * 64,
                    "verified_fact_digest": "b" * 64,
                }
            },
            content_classes=["claim", "finding", "quote"],
        ),
        _ctx(),
    )

    assert [item.content_class for item in response.evidence] == ["finding"]
    assert response.excluded_report_counts["row_claim_pages_not_supported"] == 1
    assert response.excluded_report_counts["row_quote_page_not_supported"] == 1
