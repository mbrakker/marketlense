from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from threading import Event

import pytest

from src.contracts.artifact_lineage import (
    ARTIFACT_LINEAGE_SCHEMA_VERSION,
    ArtifactLineageRegistrationRequest,
)
from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.minimal_execution_plan import (
    MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
    ExecutionPlanRecordRequest,
    ExecutionPlanResultRequest,
    MinimalExecutionPlan,
)
from src.contracts.pipeline_preflight import PipelinePreflightReport
from src.contracts.run_context import RunContext
from src.orchestrators.report_pipeline_orchestrator import (
    _enforced_resume_stage,
    run_report_pipeline,
)
from src.services.report_store_service import (
    build_current_report_execution_compatibility,
    record_artifact_lineage,
    record_minimal_execution_plan,
    record_minimal_execution_plan_result,
)
from src.utils.errors import AppError

ROOT = Path(__file__).resolve().parents[1]
RETAINED_ARTIFACT = (
    ROOT
    / "tests"
    / "fixtures"
    / "docpacks"
    / "golden"
    / "morningstar-2026-outlook-acig-pdf"
    / "report_analysis"
    / "artifacts.json"
)


def _ctx(task_id: str = "minimal-enforcement") -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id=f"run-{task_id}",
        task_id=task_id,
        span_id="span",
    )


def _settings(tmp_path: Path) -> IngestSettings:
    return IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-5",
        batch_limit=1,
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        usage_db_path=str(tmp_path / "usage.sqlite"),
        category_mapping_path=str(ROOT / "src" / "config" / "category-mappings.yaml"),
        cover_style_path=str(ROOT / "src" / "config" / "cover-styles.yaml"),
        ingest_lock_path=str(tmp_path / "ingest.lock"),
        temperature=0.0,
    )


def _passed_preflight(*_args, **_kwargs) -> PipelinePreflightReport:
    return PipelinePreflightReport(
        schema_version="1.0",
        workflow="report_pipeline",
        planned_side_effects=[],
        passed=True,
        expensive_side_effects_allowed=True,
        blocker_count=0,
        warning_count=0,
        auto_fixed_count=0,
        checks=[],
        blockers=[],
        warnings=[],
        auto_fixable_issues=[],
        next_actions=[],
    )


def _record(
    settings: IngestSettings,
    ctx: RunContext,
    *,
    artifact_kind: str,
    compatibility: dict[str, object],
    dependencies: list[str] | None = None,
) -> str:
    response = record_artifact_lineage(
        ArtifactLineageRegistrationRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=settings.reports_db,
            artifact_kind=artifact_kind,
            report_id="f1",
            source_id="md5",
            storage_ref=str(RETAINED_ARTIFACT),
            producer="retained_fixture",
            schema_version_used="1.0",
            processing_version="report_generation_checkpoint_v2",
            dependency_artifact_ids=dependencies or [],
            compatibility=compatibility,
            lineage_status="complete",
        ),
        ctx,
    )
    return response.record.artifact_id


def _compatibility(settings: IngestSettings, ctx: RunContext) -> dict[str, object]:
    return asdict(build_current_report_execution_compatibility(settings, ctx))


@pytest.mark.parametrize(
    (
        "change_kind",
        "artifact_kind",
        "compatibility_key",
        "expected_resume_stage",
        "expects_client_bundle",
    ),
    [
        (
            "template",
            "rendered_html",
            "template_render_versions",
            "analysis_complete",
            False,
        ),
        ("crop", "crop", "crop_profiles", "source_prepared", False),
        ("prompt", "artifacts", "prompt_versions", "selection_complete", True),
        ("validator", "validation", "validator_versions", "selection_complete", True),
    ],
)
def test_enforce_mode_uses_only_the_planned_checkpoint_entrypoint(
    tmp_path: Path,
    change_kind: str,
    artifact_kind: str,
    compatibility_key: str,
    expected_resume_stage: str,
    expects_client_bundle: bool,
) -> None:
    """Existing retained artifact data proves each enabled enforce family."""
    settings = _settings(tmp_path)
    ctx = _ctx(change_kind)
    current = _compatibility(settings, ctx)
    source = _record(
        settings,
        ctx,
        artifact_kind="source_pdf",
        compatibility={**current, "artifact_family": "source_pdf"},
    )
    analysis = _record(
        settings,
        ctx,
        artifact_kind="analysis_pdf",
        compatibility={**current, "artifact_family": "analysis_pdf"},
        dependencies=[source],
    )
    changed = dict(current)
    changed["artifact_family"] = artifact_kind
    old_values = dict(changed[compatibility_key])
    if compatibility_key == "prompt_versions":
        old_values["report_vs/artifacts/summary"] = "retained-prompt-version"
    elif compatibility_key == "validator_versions":
        old_values["validation"] = "retained-validator-version"
    elif compatibility_key == "crop_profiles":
        old_values["*"] = "retained-crop-profile"
    else:
        old_values["rendered_html"] = "retained-template-version"
    changed[compatibility_key] = old_values
    changed_artifact = _record(
        settings,
        ctx,
        artifact_kind=artifact_kind,
        compatibility=changed,
        dependencies=[analysis],
    )
    if artifact_kind != "rendered_html":
        _record(
            settings,
            ctx,
            artifact_kind="rendered_html",
            compatibility={**current, "artifact_family": "rendered_html"},
            dependencies=[changed_artifact],
        )
    invocations: list[dict[str, object]] = []

    def generate_retained_report(*args, **kwargs) -> IngestOutcome:
        invocations.append(dict(kwargs))
        report_file = args[0]
        return IngestOutcome(
            schema_version="1.0",
            file_id=report_file.file_id,
            name=report_file.name or report_file.file_id,
            md5="md5",
            html_path=str(RETAINED_ARTIFACT),
            status="processed",
        )

    outcome = run_report_pipeline(
        DriveFile("1.0", "f1", "retained.pdf", None, "md5"),
        str(RETAINED_ARTIFACT),
        settings,
        "md5",
        ctx,
        retries=0,
        generate_report_fn=generate_retained_report,
        preflight_fn=_passed_preflight,
        lineage_change_kind=change_kind,
        lineage_available=True,
        execution_plan_mode="enforce",
    )

    assert outcome.status == "processed"
    assert len(invocations) == 1
    assert invocations[0]["resume_from_stage"] == expected_resume_stage
    assert invocations[0]["enforce_minimal_execution"] is True
    assert ("client_bundle" in invocations[0]) is expects_client_bundle


def test_execution_audit_marks_unplanned_side_effect_as_divergence(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    ctx = _ctx("audit")
    current = _compatibility(settings, ctx)
    artifact_id = _record(
        settings,
        ctx,
        artifact_kind="rendered_html",
        compatibility={**current, "artifact_family": "rendered_html"},
    )
    plan = MinimalExecutionPlan(
        schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
        execution_intent="render_repair",
        report_id="f1",
        reusable_artifacts=[artifact_id],
        invalid_artifacts=[],
        required_stages=["render_complete"],
        skipped_stages=["source_prepared", "selection_complete", "analysis_complete"],
        required_external_calls=["html_render"],
        expected_side_effects=["rendered_html_write"],
        estimated_cost_call_categories=[],
        missing_lineage_blockers=[],
        publication_prerequisites=[],
        plan_hash="audit-plan",
    )
    record_minimal_execution_plan(
        ExecutionPlanRecordRequest(
            schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
            db_path=settings.reports_db,
            plan=plan,
            execution_mode="enforce",
        ),
        ctx,
    )

    diverged = record_minimal_execution_plan_result(
        ExecutionPlanResultRequest(
            schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
            db_path=settings.reports_db,
            plan_hash=plan.plan_hash,
            report_id="f1",
            execution_intent=plan.execution_intent,
            actual_stages=plan.required_stages,
            actual_external_calls=plan.required_external_calls,
            actual_side_effects=["rendered_html_write", "wordpress_update"],
            reusable_artifact_ids=[artifact_id],
            execution_status="processed",
        ),
        ctx,
    )

    assert diverged is True


def test_enforce_mode_combines_crop_and_analysis_at_source_checkpoint() -> None:
    plan = MinimalExecutionPlan(
        schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
        execution_intent="targeted_repair",
        report_id="f1",
        reusable_artifacts=["source:retained"],
        invalid_artifacts=[],
        required_stages=[
            "selection_complete",
            "analysis_complete",
            "render_complete",
        ],
        skipped_stages=["source_prepared"],
        required_external_calls=[
            "crop_render",
            "crop_qa",
            "vector_store",
            "report_analysis_model",
            "validator_model",
            "html_render",
        ],
        expected_side_effects=[],
        estimated_cost_call_categories=[],
        missing_lineage_blockers=[],
        publication_prerequisites=[],
        plan_hash="combined-plan",
    )

    assert _enforced_resume_stage(plan) == "source_prepared"


def test_enforce_mode_releases_the_lease_after_a_failed_retained_replay(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    ctx = _ctx("failed")
    current = _compatibility(settings, ctx)
    _record(
        settings,
        ctx,
        artifact_kind="rendered_html",
        compatibility={**current, "artifact_family": "rendered_html"},
    )

    def fail_after_plan(*_args, **_kwargs) -> IngestOutcome:
        raise AppError(code="retained_replay_failed", message="failed", retryable=False)

    with pytest.raises(AppError, match="failed"):
        run_report_pipeline(
            DriveFile("1.0", "f1", "retained.pdf", None, "md5"),
            str(RETAINED_ARTIFACT),
            settings,
            "md5",
            ctx,
            retries=0,
            generate_report_fn=fail_after_plan,
            preflight_fn=_passed_preflight,
            lineage_change_kind="template",
            lineage_available=True,
            execution_plan_mode="enforce",
        )

    assert not list((tmp_path / "out" / ".minimal_execution_leases").glob("*.lock"))


def test_enforce_mode_rejects_a_concurrent_retained_artifact_run(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    seed_ctx = _ctx("concurrent-seed")
    current = _compatibility(settings, seed_ctx)
    _record(
        settings,
        seed_ctx,
        artifact_kind="rendered_html",
        compatibility={**current, "artifact_family": "rendered_html"},
    )
    entered = Event()
    release = Event()

    def slow_retained_render(*args, **_kwargs) -> IngestOutcome:
        entered.set()
        assert release.wait(timeout=10)
        report_file = args[0]
        return IngestOutcome(
            schema_version="1.0",
            file_id=report_file.file_id,
            name=report_file.name or report_file.file_id,
            md5="md5",
            html_path=str(RETAINED_ARTIFACT),
            status="processed",
        )

    def run(ctx: RunContext) -> IngestOutcome:
        return run_report_pipeline(
            DriveFile("1.0", "f1", "retained.pdf", None, "md5"),
            str(RETAINED_ARTIFACT),
            settings,
            "md5",
            ctx,
            retries=0,
            generate_report_fn=slow_retained_render,
            preflight_fn=_passed_preflight,
            lineage_change_kind="template",
            lineage_available=True,
            execution_plan_mode="enforce",
        )

    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(run, _ctx("concurrent-first"))
        assert entered.wait(timeout=10)
        with pytest.raises(AppError) as exc_info:
            run(_ctx("concurrent-second"))
        release.set()
        assert first.result(timeout=10).status == "processed"

    assert exc_info.value.code == "minimal_execution_plan_lease_conflict"
    assert not list((tmp_path / "out" / ".minimal_execution_leases").glob("*.lock"))
