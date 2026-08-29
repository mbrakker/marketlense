from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.artifact_lineage import (
    ARTIFACT_LINEAGE_SCHEMA_VERSION,
    ArtifactInvalidationRequest,
    ArtifactLineageRegistrationRequest,
    ArtifactLineageRegistrationResponse,
    ArtifactLineageTraceRequest,
)
from src.contracts.drive import DriveFile
from src.contracts.files import PipelineStageCheckpoint
from src.contracts.report_generation import ReportRuntimeState
from src.generators.report_generation_dependencies import ReportGenerationDependencies
from src.generators.report_render_generator import render_preview_asset
from src.orchestrators._report_generation_orchestrator.checkpoints import (
    _record_rendered_html_prompt_family_lineage,
    _regeneration_attempts_from_list,
    _vector_indexing_state_from_checkpoint,
)
from src.orchestrators._report_generation_orchestrator.resume import (
    _outcome_from_render_checkpoint,
    _read_validated_checkpoint,
    _render_project_and_cleanup,
    _resume_from_checkpoint_stage,
    _select_latest_safe_restart_stage,
    _validate_checkpoint_artifact_lineage,
    _validate_checkpoint_artifacts,
)
from src.orchestrators._report_generation_orchestrator.workflow import (
    _should_fresh_start_after_latest_safe_rejection,
)
from src.services.report_store_service import (
    invalidate_artifacts,
    record_artifact_lineage,
    trace_artifact_lineage,
)
from src.utils.errors import AppError
from tests.test_report_pipeline_orchestrator import _ctx, _settings
from tests.test_report_render_generator import (
    _analysis,
    _selection,
    _source,
)
from tests.test_report_render_generator import (
    _deps as _render_dependencies,
)


def _runtime(tmp_path: Path) -> ReportRuntimeState:
    report_file = tmp_path / "report.pdf"
    report_file.write_bytes(b"retained source")
    return ReportRuntimeState(
        schema_version="1.0",
        file=DriveFile(
            schema_version="1.0",
            file_id="report-1",
            name="report.pdf",
            modified_time=None,
            md5_checksum="md5",
        ),
        local_pdf_path=str(report_file),
        settings=replace(_settings(), reports_db=str(tmp_path / "reports.sqlite")),
        md5="md5",
        ctx=_ctx(),
        file_name="report.pdf",
        report_name="report",
        report_title="Report",
        analysis_mode="default",
        analysis_modes=["default"],
        report_worker_limit=1,
        parallel_within_file=False,
    )


def _checkpoint(*, artifact_id: str) -> PipelineStageCheckpoint:
    return PipelineStageCheckpoint(
        schema_version="1.0",
        pipeline_name="report_generation",
        file_id="report-1",
        report_slug="report",
        stage_name="render_complete",
        stage_status="completed",
        artifact_refs={},
        payload={"artifact_lineage": {"rendered_html": artifact_id}},
        completed_at_utc="2026-07-13T00:00:00+00:00",
        source_run_id="run-1",
        source_task_id="task-1",
    )


def _record_rendered_html(
    runtime: ReportRuntimeState,
    artifact_path: Path,
    *,
    lineage_status: str = "legacy_unverified",
) -> ArtifactLineageRegistrationResponse:
    return record_artifact_lineage(
        ArtifactLineageRegistrationRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=runtime.settings.reports_db,
            artifact_kind="rendered_html",
            report_id=runtime.file.file_id,
            source_id="md5",
            storage_ref=str(artifact_path),
            producer="render_complete",
            schema_version_used="1.0",
            processing_version="report_generation_checkpoint_v1",
            metadata={"template_hash": "template-v1"},
            lineage_status=lineage_status,
        ),
        runtime.ctx,
    )


def test_checkpoint_lineage_validation_accepts_active_content(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    html_path = tmp_path / "report.html"
    html_path.write_text("<h1>Report</h1>", encoding="utf-8")
    record = _record_rendered_html(runtime, html_path, lineage_status="complete")

    _validate_checkpoint_artifact_lineage(
        runtime,
        _checkpoint(artifact_id=record.record.artifact_id),
        "checkpoint.json",
    )


def test_regeneration_attempt_checkpoint_preserves_promotion_lineage() -> None:
    attempts = _regeneration_attempts_from_list(
        [
            {
                "attempt_index": 1,
                "plan_mode": "targeted",
                "validation_before_status": "fail",
                "validation_after_status": "pass",
                "candidate_artifacts_path": "out/candidate-artifacts.json",
                "candidate_audit_path": "out/candidate-audit.json",
                "promotion_outcome": "promoted",
            }
        ]
    )

    assert attempts[0].promotion_outcome == "promoted"
    assert attempts[0].candidate_artifacts_path.endswith("candidate-artifacts.json")
    assert attempts[0].candidate_audit_path.endswith("candidate-audit.json")


def test_rendered_html_lineage_explicitly_depends_on_prompt_materializations(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    artifacts_path = tmp_path / "artifacts.json"
    validation_path = tmp_path / "validation.json"
    family_path = tmp_path / "prompt-family.json"
    html_path = tmp_path / "report.html"
    artifacts_path.write_text("{}", encoding="utf-8")
    validation_path.write_text("{}", encoding="utf-8")
    family_path.write_text("{}", encoding="utf-8")
    html_path.write_text("<h1>Report</h1>", encoding="utf-8")

    def record(kind: str, path: Path):
        return record_artifact_lineage(
            ArtifactLineageRegistrationRequest(
                schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
                db_path=runtime.settings.reports_db,
                artifact_kind=kind,
                report_id=runtime.file.file_id,
                source_id="md5",
                storage_ref=str(path),
                producer="analysis_complete",
                schema_version_used="1.0",
                processing_version="report_generation_checkpoint_v2",
                validation_status="pass",
                lineage_status="complete",
            ),
            runtime.ctx,
        ).record.artifact_id

    artifacts_id = record("artifacts", artifacts_path)
    validation_id = record("validation", validation_path)
    family_id = record("prompt_family:report_vs/artifacts/summary", family_path)
    initial_rendered = _record_rendered_html(
        runtime, html_path, lineage_status="complete"
    ).record.artifact_id
    lineage = {
        "artifacts": artifacts_id,
        "validation": validation_id,
        "rendered_html": initial_rendered,
    }

    _record_rendered_html_prompt_family_lineage(
        runtime,
        artifact_registry={
            "refs": [
                {
                    "artifact_id": "rendered_html",
                    "path": str(html_path),
                    "schema_version": "1.0",
                }
            ]
        },
        payload={},
        artifact_lineage=lineage,
        prompt_family_materializations={"report_vs/artifacts/summary": family_id},
    )

    trace = trace_artifact_lineage(
        ArtifactLineageTraceRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=runtime.settings.reports_db,
            artifact_id=lineage["rendered_html"],
        ),
        runtime.ctx,
    )
    assert (lineage["rendered_html"], family_id) in trace.edges


def test_checkpoint_lineage_validation_rejects_invalidated_artifact(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    html_path = tmp_path / "report.html"
    html_path.write_text("<h1>Report</h1>", encoding="utf-8")
    record = _record_rendered_html(runtime, html_path)
    invalidate_artifacts(
        ArtifactInvalidationRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=runtime.settings.reports_db,
            change_kind="template",
            changed_value="template-v1",
            report_id=runtime.file.file_id,
        ),
        runtime.ctx,
    )

    with pytest.raises(AppError) as exc_info:
        _validate_checkpoint_artifact_lineage(
            runtime,
            _checkpoint(artifact_id=record.record.artifact_id),
            "checkpoint.json",
        )

    assert exc_info.value.code == "report_pipeline_checkpoint_lineage_not_reusable"
    assert exc_info.value.retryable is False


def test_selective_regeneration_rejects_checkpoint_without_lineage(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    checkpoint = _checkpoint(artifact_id="")
    checkpoint = replace(checkpoint, payload={})

    with pytest.raises(AppError) as exc_info:
        _validate_checkpoint_artifact_lineage(
            runtime,
            checkpoint,
            "checkpoint.json",
            require_artifact_lineage=True,
        )

    assert exc_info.value.code == "report_pipeline_checkpoint_lineage_missing"
    assert exc_info.value.retryable is False


def test_selective_regeneration_requires_complete_lineage(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    html_path = tmp_path / "report.html"
    html_path.write_text("<h1>Report</h1>", encoding="utf-8")
    record = _record_rendered_html(runtime, html_path)

    with pytest.raises(AppError) as exc_info:
        _validate_checkpoint_artifact_lineage(
            runtime,
            _checkpoint(artifact_id=record.record.artifact_id),
            "checkpoint.json",
            require_artifact_lineage=True,
        )

    assert exc_info.value.code == "report_pipeline_checkpoint_lineage_not_reusable"
    assert exc_info.value.context["reason"] == "lineage_incomplete"


def test_selection_checkpoint_without_vector_state_remains_resumable() -> None:
    """Retained pre-vector checkpoints represent the optional state as null."""
    state = _vector_indexing_state_from_checkpoint(None)

    assert state.vector_store_id is None
    assert state.openai_file_id is None
    assert state.vector_store_status is None


def _integrity_checkpoint(
    artifact_path: Path,
    *,
    artifact_ref: str | None = None,
    artifact_entry: object | None = None,
) -> PipelineStageCheckpoint:
    payload_entry = artifact_entry
    if payload_entry is None:
        payload_entry = {
            "path": str(artifact_path),
            "md5": hashlib.md5(artifact_path.read_bytes()).hexdigest(),
        }
    return replace(
        _checkpoint(artifact_id=""),
        artifact_refs={"rendered_html": artifact_ref or str(artifact_path)},
        payload={"artifact_integrity": {"files": {"rendered_html": payload_entry}}},
    )


def test_checkpoint_artifact_integrity_accepts_retained_file(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    artifact_path = tmp_path / "report.html"
    artifact_path.write_text("<h1>Report</h1>", encoding="utf-8")

    _validate_checkpoint_artifacts(
        runtime,
        _integrity_checkpoint(artifact_path),
        "checkpoint.json",
    )


def test_checkpoint_rejects_legacy_artifacts_without_editorial_plan(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    artifact_path = tmp_path / "artifacts.json"
    artifact_path.write_text(
        json.dumps(
            {
                "toc_topics": ["Overview"],
                "summary": {},
                "cover_semantics": {},
                "insights_candidates": [],
                "insights_final": [],
                "quotes_final": [],
                "expert_comment": "",
                "linkedin_post": "",
            }
        ),
        encoding="utf-8",
    )
    checkpoint = replace(
        _checkpoint(artifact_id=""),
        artifact_refs={"artifacts": str(artifact_path)},
        payload={},
    )

    with pytest.raises(AppError) as exc_info:
        _validate_checkpoint_artifacts(runtime, checkpoint, "checkpoint.json")

    assert exc_info.value.code == "report_pipeline_checkpoint_artifact_schema_invalid"


def test_checkpoint_rejects_artifacts_with_stale_editorial_prompt_identity(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    artifact_path = tmp_path / "artifacts.json"
    artifact_path.write_text(
        json.dumps(
            {
                "editorial_plan": {
                    "report_thesis": "Evidence supports one clear report thesis.",
                    "themes": [
                        {
                            "theme": "The priority theme is evidence-led.",
                            "priority": 1,
                            "evidence_ids": ["finding-1"],
                        },
                        {
                            "theme": "A second theme preserves the minimal contract.",
                            "priority": 2,
                            "evidence_ids": ["finding-2"],
                        },
                    ],
                },
                "_cache": {
                    "prompts": {
                        "report_vs/artifacts/editorial_plan": {
                            "prompt_content_hash": "stale-prompt-hash"
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    checkpoint = replace(
        _checkpoint(artifact_id=""),
        artifact_refs={"artifacts": str(artifact_path)},
        payload={},
    )

    with pytest.raises(AppError) as exc_info:
        _validate_checkpoint_artifacts(runtime, checkpoint, "checkpoint.json")

    assert exc_info.value.code == "report_pipeline_checkpoint_prompt_identity_invalid"


@pytest.mark.parametrize(
    ("checkpoint_factory", "expected_code"),
    [
        (
            lambda artifact: replace(
                _checkpoint(artifact_id=""),
                payload={"artifact_integrity": {"files": []}},
            ),
            "report_pipeline_checkpoint_invalid",
        ),
        (
            lambda artifact: _integrity_checkpoint(
                artifact,
                artifact_entry="not-an-object",
            ),
            "report_pipeline_checkpoint_invalid",
        ),
        (
            lambda artifact: _integrity_checkpoint(
                artifact,
                artifact_ref=str(artifact.with_name("other.html")),
            ),
            "report_pipeline_checkpoint_artifact_missing",
        ),
        (
            lambda artifact: _integrity_checkpoint(
                artifact,
                artifact_entry={"path": str(artifact), "md5": "not-the-hash"},
            ),
            "report_pipeline_checkpoint_artifact_hash_mismatch",
        ),
        (
            lambda artifact: replace(
                _checkpoint(artifact_id=""),
                artifact_refs={
                    "rendered_html": str(artifact.with_name("missing.html"))
                },
                payload={
                    "artifact_integrity": {
                        "files": {
                            "rendered_html": {
                                "path": str(artifact.with_name("missing.html")),
                                "md5": "",
                            }
                        }
                    }
                },
            ),
            "report_pipeline_checkpoint_artifact_missing",
        ),
    ],
)
def test_checkpoint_artifact_integrity_rejects_invalid_or_changed_artifact(
    tmp_path: Path,
    checkpoint_factory,
    expected_code: str,
) -> None:
    runtime = _runtime(tmp_path)
    artifact_path = tmp_path / "report.html"
    artifact_path.write_text("<h1>Report</h1>", encoding="utf-8")

    with pytest.raises(AppError) as exc_info:
        _validate_checkpoint_artifacts(
            runtime,
            checkpoint_factory(artifact_path),
            "checkpoint.json",
        )

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize("raw_outcome", [None, {"schema_version": "1.0"}])
def test_render_checkpoint_outcome_rejects_invalid_or_incomplete_payload(
    raw_outcome: object,
) -> None:
    with pytest.raises(AppError) as exc_info:
        _outcome_from_render_checkpoint(raw_outcome)

    assert exc_info.value.code == "report_pipeline_checkpoint_invalid"


def test_render_checkpoint_outcome_requires_passing_readiness() -> None:
    with pytest.raises(AppError) as exc_info:
        _outcome_from_render_checkpoint(
            {
                "schema_version": "1.1",
                "file_id": "report-1",
                "name": "report.pdf",
                "md5": "md5",
                "html_path": "out/report.html",
                "status": "processed",
                "publish_readiness_status": "fail",
            }
        )

    assert exc_info.value.code == "report_pipeline_checkpoint_readiness_unverified"


def test_checkpoint_resume_rejects_unknown_stage_without_side_effects(
    tmp_path: Path,
) -> None:
    with pytest.raises(AppError) as exc_info:
        _resume_from_checkpoint_stage(
            _runtime(tmp_path),
            ReportGenerationDependencies.default(),
            None,
            requested_resume_stage="not-a-stage",
        )

    assert exc_info.value.code == "report_pipeline_restart_stage_invalid"


def test_read_validated_checkpoint_and_latest_safe_restart_fail_closed_when_missing(
    tmp_path: Path,
) -> None:
    base_runtime = _runtime(tmp_path)
    runtime = replace(
        base_runtime,
        settings=replace(
            base_runtime.settings,
            output_dir=str(tmp_path / "no-checkpoints"),
        ),
    )

    with pytest.raises(AppError) as read_error:
        _read_validated_checkpoint(runtime, stage_name="render_complete")
    with pytest.raises(AppError) as restart_error:
        _select_latest_safe_restart_stage(runtime)

    assert read_error.value.code == "report_pipeline_checkpoint_missing"
    assert restart_error.value.code == "report_pipeline_checkpoint_missing"


def test_nonreusable_latest_safe_checkpoint_selects_fresh_pipeline_start() -> None:
    error = AppError(
        code="report_pipeline_checkpoint_lineage_not_reusable",
        message="Checkpoint artifact lineage cannot be reused",
        retryable=False,
    )

    assert _should_fresh_start_after_latest_safe_rejection(error) is True


def test_render_only_resume_avoids_post_render_side_effects(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    html_path = tmp_path / "out" / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    render_dependencies = _render_dependencies(render_report=_render_report)
    dependencies = replace(
        ReportGenerationDependencies.default(), render=render_dependencies
    )
    outcome = _render_project_and_cleanup(
        runtime,
        source,
        selection,
        analysis,
        render_preview_asset(runtime, source, render_dependencies),
        dependencies,
        None,
        existing_artifact_refs={},
        skip_post_render_projection=True,
    )

    assert outcome.html_path == str(html_path)
