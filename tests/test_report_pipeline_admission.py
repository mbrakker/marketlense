from __future__ import annotations

from dataclasses import replace
from hashlib import md5
from pathlib import Path

import pytest

from src.contracts.deferred_work import (
    DeferredWorkArtifactReference,
    DeferredWorkItem,
    DeferredWorkResumePlan,
)
from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.pipeline_preflight import PipelinePreflightReport
from src.contracts.report_store import ReportSourceRecordRequest
from src.contracts.run_context import RunContext
from src.orchestrators import report_pipeline_orchestrator as orch
from src.services.report_store_service import record_report_source
from src.utils.errors import AppError


def _settings() -> IngestSettings:
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


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="r",
        task_id="t",
        span_id="s",
        admission_decision_hash="test-admission-decision",
    )


def _passed_preflight_report() -> PipelinePreflightReport:
    return PipelinePreflightReport(
        schema_version="1.0",
        workflow="report_pipeline",
        planned_side_effects=["pdf", "model"],
        passed=True,
        expensive_side_effects_allowed=True,
        blocker_count=0,
        warning_count=0,
        auto_fixed_count=0,
        checks=[],
        blockers=[],
        warnings=[],
        auto_fixable_issues=[],
        next_actions=["continue_pipeline"],
    )


def test_report_pipeline_requires_admission_before_runtime_or_model_work() -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="unadmitted",
        name="unadmitted.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    called = {"preflight": False, "generation": False}

    def _preflight(*_args, **_kwargs):
        called["preflight"] = True
        raise AssertionError("runtime preflight must not run without admission")

    def _generate(*_args, **_kwargs):
        called["generation"] = True
        raise AssertionError("generation must not run without admission")

    with pytest.raises(AppError) as exc_info:
        orch.run_report_pipeline(
            file,
            local_pdf_path="./cache/unadmitted.pdf",
            settings=_settings(),
            md5="md5",
            ctx=RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
            preflight_fn=_preflight,
            generate_report_fn=_generate,
        )

    assert exc_info.value.code == "report_pipeline_admission_required"
    assert called == {"preflight": False, "generation": False}


def test_deferred_report_pipeline_admits_source_before_generation(tmp_path) -> None:
    source_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "pdf_benchmark"
        / "golden"
        / "IAS - Industry_Pulse_Report_2026_ACIG.pdf"
    )
    settings = replace(
        _settings(),
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        usage_db_path=str(tmp_path / "usage.sqlite"),
        run_budget_max_spend_usd=None,
        run_budget_max_pdfs=None,
        run_budget_max_retries=None,
        run_budget_max_runtime_seconds=None,
    )
    item = DeferredWorkItem(
        schema_version="1.0",
        work_key="deferred:report",
        workflow="report_generation",
        stage="source_prepared",
        run_id="deferred-run",
        resource_type="pdf_process",
        operation="report_pipeline",
        reason_code="budget_deferred",
        affected_limit="spend_usd",
        earliest_run_at_utc="2026-01-01T00:00:00Z",
        deadline_at_utc="2027-01-01T00:00:00Z",
        attempt_count=0,
        max_attempts=2,
        deferred_at_utc="2026-01-01T00:00:00Z",
        updated_at_utc="2026-01-01T00:00:00Z",
        report_id="ias-2026",
        source_id="not-the-source-md5",
        reusable_artifacts=[
            DeferredWorkArtifactReference(
                schema_version="1.0",
                kind="local_pdf",
                reference=str(source_path),
            )
        ],
    )
    plan = DeferredWorkResumePlan(
        schema_version="1.0", plan_hash="plan", resume_stage="latest_safe"
    )
    generation_calls = {"count": 0}

    def _generate(*_args, **_kwargs):
        generation_calls["count"] += 1
        raise AssertionError("an unadmitted deferred source must not generate")

    with pytest.raises(AppError) as exc_info:
        orch.resume_deferred_report_pipeline(
            item,
            plan,
            settings,
            _ctx(),
            generate_report_fn=_generate,
            preflight_fn=lambda *_args, **_kwargs: _passed_preflight_report(),
        )

    assert exc_info.value.code == "source_admission_corrupt_source"
    assert generation_calls["count"] == 0


def test_deferred_report_recovery_never_falls_back_to_fresh_generation(
    tmp_path,
) -> None:
    source_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "pdf_benchmark"
        / "golden"
        / "IAS - Industry_Pulse_Report_2026_ACIG.pdf"
    )
    source_md5 = md5(source_path.read_bytes()).hexdigest()
    settings = replace(
        _settings(),
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
    )
    record_report_source(
        ReportSourceRecordRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            source_domain="publisher.example",
            report_name="Industry Pulse Report 2026",
            landing_page_url="https://publisher.example/reports/industry-pulse-2026",
            downloaded_at_utc="2026-08-10T12:00:00Z",
            md5=source_md5,
            publisher_name="Industry Analytics Summit",
        ),
        _ctx(),
    )
    item = DeferredWorkItem(
        schema_version="1.0",
        work_key="deferred:validated-report",
        workflow="report_generation",
        stage="analysis_complete",
        run_id="deferred-run",
        resource_type="pdf_process",
        operation="report_pipeline",
        reason_code="budget_deferred",
        affected_limit="spend_usd",
        earliest_run_at_utc="2026-01-01T00:00:00Z",
        deadline_at_utc="2027-01-01T00:00:00Z",
        attempt_count=0,
        max_attempts=2,
        deferred_at_utc="2026-01-01T00:00:00Z",
        updated_at_utc="2026-01-01T00:00:00Z",
        report_id="ias-2026",
        source_id=source_md5,
        reusable_artifacts=[
            DeferredWorkArtifactReference(
                schema_version="1.0",
                kind="local_pdf",
                reference=str(source_path),
            )
        ],
    )
    observed: dict[str, object] = {}

    def _pipeline(*_args, **kwargs) -> IngestOutcome:
        observed.update(kwargs)
        return IngestOutcome(
            schema_version="1.0",
            file_id="ias-2026",
            name=source_path.name,
            md5=source_md5,
            html_path=None,
            status="processed",
        )

    assert (
        orch.resume_deferred_report_pipeline(
            item,
            DeferredWorkResumePlan(
                schema_version="1.0",
                plan_hash="validated-plan",
                resume_stage="latest_safe",
            ),
            settings,
            _ctx(),
            preflight_fn=lambda *_args, **_kwargs: _passed_preflight_report(),
            run_report_pipeline_fn=_pipeline,
        )
        == "completed"
    )
    assert observed["resume_from_stage"] == "latest_safe"
    assert observed["auto_resume_from_latest_safe"] is False
    assert observed["execution_plan_mode"] == "enforce"
