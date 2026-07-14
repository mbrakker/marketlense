from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.artifact_lineage import (
    ARTIFACT_LINEAGE_SCHEMA_VERSION,
    ArtifactInvalidationRequest,
    ArtifactLineageRegistrationRequest,
    ArtifactLineageRegistrationResponse,
)
from src.contracts.drive import DriveFile
from src.contracts.files import PipelineStageCheckpoint
from src.contracts.report_generation import ReportRuntimeState
from src.orchestrators._report_generation_orchestrator.resume import (
    _validate_checkpoint_artifact_lineage,
)
from src.services.report_store_service import (
    invalidate_artifacts,
    record_artifact_lineage,
)
from src.utils.errors import AppError
from tests.test_report_pipeline_orchestrator import _ctx, _settings


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
    runtime: ReportRuntimeState, artifact_path: Path
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
        ),
        runtime.ctx,
    )


def test_checkpoint_lineage_validation_accepts_active_content(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    html_path = tmp_path / "report.html"
    html_path.write_text("<h1>Report</h1>", encoding="utf-8")
    record = _record_rendered_html(runtime, html_path)

    _validate_checkpoint_artifact_lineage(
        runtime,
        _checkpoint(artifact_id=record.record.artifact_id),
        "checkpoint.json",
    )


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


def test_selective_regeneration_rejects_checkpoint_without_lineage(tmp_path: Path) -> None:
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
