from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationReport
from src.generators.publish_readiness_generator import (
    complete_publish_readiness_refresh_plan,
    evaluate_publish_readiness,
    plan_publish_readiness_refresh,
)
from src.orchestrators import report_pipeline_orchestrator as orch
from src.utils.errors import AppError

_HTML = (
    "<!doctype html><html><head><title>Report 2026 | MarketLense</title>"
    '<link rel="canonical" href="https://marketlense.example/reports/report">'
    "</head><body><h1>Report 2026</h1>"
    "<p>Revenue grew in the measured market.</p>"
    '<section id="source"><a href="https://publisher.example/report">'
    "Open original source</a></section></body></html>"
)
_CREATED_AT = datetime(2026, 8, 26, 12, tzinfo=UTC)


def _pipeline_settings() -> IngestSettings:
    return IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-5",
        batch_limit=1,
        output_dir="./out",
        cache_dir="./cache",
        state_db="./state/index.sqlite",
        reports_db="./state/reports.sqlite",
        category_mapping_path="./src/config/category-mappings.yaml",
        cover_style_path="./src/config/cover-styles.yaml",
        ingest_lock_path="./state/ingest.lock",
        ingest_lock_ttl_seconds=7200.0,
        temperature=1.0,
    )


def _pipeline_context() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="r",
        task_id="t",
        span_id="s",
        admission_decision_hash="test-admission-decision",
    )


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


def test_failed_semantic_readiness_requires_reanalysis_from_selection_checkpoint() -> (
    None
):
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


def test_readiness_refresh_persists_completed_typed_telemetry(tmp_path) -> None:
    settings = replace(
        _pipeline_settings(),
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        usage_db_path=str(tmp_path / "usage.sqlite"),
        ingest_lock_path=str(tmp_path / "ingest.lock"),
    )
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    refresh_plan = replace(
        plan_publish_readiness_refresh(
            report_id=file.file_id,
            readiness=None,
            final_html="",
            configuration_hash="",
            policy_hash="",
            producer_revision="",
            evaluated_at_utc=_CREATED_AT,
        ),
        execution_result="planned",
    )
    telemetry_path = tmp_path / "out" / "f1" / "report_analysis" / "refresh.json"

    def _generate(current, _path, _settings, md5, _ctx, **_kwargs):
        return IngestOutcome(
            schema_version="1.0",
            file_id=current.file_id,
            name=current.name or current.file_id,
            md5=md5,
            html_path=str(tmp_path / "out" / "f1.html"),
            status="processed",
        )

    response = orch.run_report_pipeline(
        file,
        local_pdf_path=str(tmp_path / "cache" / "a.pdf"),
        settings=settings,
        md5="md5",
        ctx=_pipeline_context(),
        retries=0,
        generate_report_fn=_generate,
        execution_plan_mode="disabled",
        readiness_refresh_plan=refresh_plan,
        refresh_telemetry_path=str(telemetry_path),
    )

    assert response.status == "processed"
    payload = json.loads(telemetry_path.read_text(encoding="utf-8"))
    assert payload["execution_result"] == "succeeded"
    assert payload["report_id"] == "f1"
    assert "report_analysis_model" in payload["avoided_external_calls"]


def test_readiness_refresh_without_telemetry_path_skips_artifact_write(
    tmp_path,
) -> None:
    settings = replace(
        _pipeline_settings(),
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        usage_db_path=str(tmp_path / "usage.sqlite"),
        ingest_lock_path=str(tmp_path / "ingest.lock"),
    )
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    refresh_plan = replace(
        plan_publish_readiness_refresh(
            report_id=file.file_id,
            readiness=None,
            final_html="",
            configuration_hash="",
            policy_hash="",
            producer_revision="",
            evaluated_at_utc=_CREATED_AT,
        ),
        execution_result="planned",
    )

    def _generate(current, _path, _settings, md5, _ctx, **_kwargs):
        return IngestOutcome(
            schema_version="1.0",
            file_id=current.file_id,
            name=current.name or current.file_id,
            md5=md5,
            html_path=str(tmp_path / "out" / "f1.html"),
            status="processed",
        )

    response = orch.run_report_pipeline(
        file,
        local_pdf_path=str(tmp_path / "cache" / "a.pdf"),
        settings=settings,
        md5="md5",
        ctx=_pipeline_context(),
        retries=0,
        generate_report_fn=_generate,
        execution_plan_mode="disabled",
        readiness_refresh_plan=refresh_plan,
    )

    assert response.status == "processed"


def test_unverifiable_readiness_persists_blocked_telemetry_before_any_work(
    tmp_path, assert_app_error
) -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    refresh_plan = plan_publish_readiness_refresh(
        report_id=file.file_id,
        readiness=None,
        final_html="",
        evaluated_at_utc=_CREATED_AT,
    )
    telemetry_path = tmp_path / "refresh.json"

    with pytest.raises(AppError) as exc_info:
        orch.run_report_pipeline(
            file,
            local_pdf_path=str(tmp_path / "cache" / "a.pdf"),
            settings=_pipeline_settings(),
            md5="md5",
            ctx=_pipeline_context(),
            readiness_refresh_plan=refresh_plan,
            refresh_telemetry_path=str(telemetry_path),
        )

    assert_app_error(
        exc_info.value,
        code="publish_readiness_refresh_unverifiable",
        retryable=False,
    )
    payload = json.loads(telemetry_path.read_text(encoding="utf-8"))
    assert payload["execution_result"] == "blocked"
