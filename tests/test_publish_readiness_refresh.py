from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.contracts.validation import ValidationReport
from src.generators.publish_readiness_generator import (
    complete_publish_readiness_refresh_plan,
    evaluate_publish_readiness,
    plan_publish_readiness_refresh,
)

_HTML = (
    "<!doctype html><html><head><title>Report 2026 | MarketLense</title>"
    '<link rel="canonical" href="https://marketlense.example/reports/report">'
    "</head><body><h1>Report 2026</h1>"
    "<p>Revenue grew in the measured market.</p>"
    '<section id="source"><a href="https://publisher.example/report">'
    "Open original source</a></section></body></html>"
)
_CREATED_AT = datetime(2026, 8, 26, 12, tzinfo=UTC)


def _readiness(
    *,
    created_at: datetime = _CREATED_AT,
    html: str = _HTML,
    artifact_hashes: dict[str, str] | None = None,
):
    return evaluate_publish_readiness(
        report_id="report-1",
        artifacts={
            "categories": ["markets"],
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": "Revenue grew in the measured market.",
                        "evidence_id": "F1",
                        "evidence": "Revenue grew in the measured market.",
                    }
                ]
            },
            "insights_final": [],
            "quotes_final": [],
            "chart_insight_cards": [],
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "F1",
                        "snippet": "Revenue grew in the measured market.",
                        "page": 1,
                    }
                ]
            }
        },
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="out/report-1.html",
        category_ids=["markets"],
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_revision="producer-1",
        artifact_hashes=artifact_hashes,
        provenance={
            "publisher_landing_page_url": "https://publisher.example/report",
            "original_report_url": "",
            "marketlense_article_url": "https://marketlense.example/reports/report",
        },
        created_at=created_at,
    )


def test_ready_current_package_has_no_refresh_work() -> None:
    plan = plan_publish_readiness_refresh(
        report_id="report-1",
        readiness=_readiness(),
        final_html=_HTML,
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_revision="producer-1",
        evaluated_at_utc=_CREATED_AT + timedelta(hours=1),
    )

    assert plan.previous_readiness_state == "ready"
    assert plan.selected_resume_stage is None
    assert plan.regenerated_stages == []
    assert plan.execution_result == "not_required"


def test_expired_passing_readiness_is_stale_and_requests_render_only() -> None:
    plan = plan_publish_readiness_refresh(
        report_id="report-1",
        readiness=_readiness(),
        final_html=_HTML,
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_revision="producer-1",
        evaluated_at_utc=_CREATED_AT + timedelta(days=2),
    )

    assert plan.previous_readiness_state == "stale"
    assert plan.invalidated_artifact_or_check == "publish_readiness.expired"
    assert plan.selected_resume_stage == "analysis_complete"
    assert plan.regenerated_stages == ["render_complete"]
    assert "report_analysis_model" in plan.avoided_external_calls


def test_expiring_readiness_is_planned_before_expiry() -> None:
    plan = plan_publish_readiness_refresh(
        report_id="report-1",
        readiness=_readiness(),
        final_html=_HTML,
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_revision="producer-1",
        evaluated_at_utc=_CREATED_AT + timedelta(hours=23, minutes=45),
        expiry_warning_window=timedelta(minutes=30),
    )

    assert plan.previous_readiness_state == "expiring"
    assert plan.selected_resume_stage == "analysis_complete"


def test_identity_mismatch_is_incompatible_and_remains_render_scoped() -> None:
    plan = plan_publish_readiness_refresh(
        report_id="report-1",
        readiness=_readiness(),
        final_html=_HTML,
        configuration_hash="configuration-hash-v2",
        policy_hash="policy-hash",
        producer_revision="producer-1",
        evaluated_at_utc=_CREATED_AT + timedelta(hours=1),
    )

    assert plan.previous_readiness_state == "incompatible"
    assert plan.invalidated_artifact_or_check == (
        "publish_readiness.configuration_changed"
    )
    assert plan.selected_resume_stage == "analysis_complete"


def test_retained_artifact_hash_mismatch_is_incompatible() -> None:
    readiness = _readiness(artifact_hashes={"artifacts": "retained-hash"})
    plan = plan_publish_readiness_refresh(
        report_id="report-1",
        readiness=readiness,
        final_html=_HTML,
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_revision="producer-1",
        current_artifact_hashes={"artifacts": "changed-hash"},
        evaluated_at_utc=_CREATED_AT + timedelta(hours=1),
    )

    assert plan.previous_readiness_state == "incompatible"
    assert plan.invalidated_artifact_or_check == (
        "publish_readiness.artifact_hash_changed"
    )


def test_failed_semantic_readiness_requires_reanalysis_from_selection_checkpoint(
) -> None:
    readiness = _readiness(html=_HTML.replace("measured market", "private C:/out/file"))
    assert readiness.status == "fail"

    plan = plan_publish_readiness_refresh(
        report_id="report-1",
        readiness=readiness,
        final_html=_HTML,
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_revision="producer-1",
        evaluated_at_utc=_CREATED_AT + timedelta(hours=1),
    )

    assert plan.previous_readiness_state == "failed"
    assert plan.selected_resume_stage == "selection_complete"
    assert plan.regenerated_stages == ["analysis_complete", "render_complete"]


def test_missing_readiness_fails_closed_without_a_resume_stage() -> None:
    plan = plan_publish_readiness_refresh(
        report_id="report-1",
        readiness=None,
        final_html=_HTML,
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_revision="producer-1",
        evaluated_at_utc=_CREATED_AT,
    )

    assert plan.previous_readiness_state == "missing_unverifiable"
    assert plan.selected_resume_stage is None
    assert plan.execution_result == "blocked"


def test_identical_inputs_produce_the_same_refresh_plan_hash() -> None:
    kwargs = {
        "report_id": "report-1",
        "readiness": _readiness(),
        "final_html": _HTML,
        "configuration_hash": "configuration-hash",
        "policy_hash": "policy-hash",
        "producer_revision": "producer-1",
        "evaluated_at_utc": _CREATED_AT + timedelta(days=2),
    }

    assert plan_publish_readiness_refresh(**kwargs) == plan_publish_readiness_refresh(
        **kwargs
    )


def test_completed_refresh_telemetry_records_actual_reuse_and_regeneration() -> None:
    planned = plan_publish_readiness_refresh(
        report_id="report-1",
        readiness=_readiness(),
        final_html=_HTML,
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_revision="producer-1",
        evaluated_at_utc=_CREATED_AT + timedelta(days=2),
    )

    completed = complete_publish_readiness_refresh_plan(
        planned,
        execution_result="succeeded",
        execution_plan_hash="execution-plan-hash",
        reused_stages=["analysis_complete", "selection_complete", "source_prepared"],
        reused_artifacts=["analysis", "crop", "source_pdf"],
        regenerated_stages=["render_complete"],
        avoided_external_calls=["report_analysis_model", "ocr", "pdf_parse"],
    )

    assert completed.execution_result == "succeeded"
    assert completed.execution_plan_hash == "execution-plan-hash"
    assert completed.reused_stages == [
        "analysis_complete",
        "selection_complete",
        "source_prepared",
    ]
    assert completed.regenerated_stages == ["render_complete"]
    assert completed.refresh_plan_hash != planned.refresh_plan_hash
