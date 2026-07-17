from __future__ import annotations

from pathlib import Path

import pytest

from src.contracts.files import (
    JsonObjectCacheWriteRequest,
    PipelineCheckpointReadRequest,
    PipelineCheckpointWriteRequest,
    PipelineStageCheckpoint,
)
from src.contracts.report_card_remediation import ReportCardCheckpointRemediationRequest
from src.contracts.remediation import RemediationListRequest
from src.contracts.run_context import RunContext
from src.orchestrators.report_card_date_remediation_orchestrator import (
    remediate_report_card_date_checkpoint,
)
from src.services.file_service import (
    read_pipeline_checkpoint,
    write_json_object_cache,
    write_pipeline_checkpoint,
)
from src.services.report_store_service import check_artifact_reuse
from src.services.state_service import list_remediation_records
from src.utils.errors import AppError
from src.contracts.artifact_lineage import ArtifactReuseCheckRequest


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_checkpoint_remediation_projects_source_date_and_refreshes_lineage(
    tmp_path: Path,
) -> None:
    artifacts_path = tmp_path / "artifacts.json"
    doc_map_path = tmp_path / "doc_map.json"
    validation_path = tmp_path / "validation.json"
    write_json_object_cache(
        JsonObjectCacheWriteRequest(
            schema_version="1.0", path=str(artifacts_path), payload={"summary": {}}
        ),
        _ctx(),
    )
    write_json_object_cache(
        JsonObjectCacheWriteRequest(
            schema_version="1.0",
            path=str(doc_map_path),
            payload={"publication_date": "2026-01-15"},
        ),
        _ctx(),
    )
    write_json_object_cache(
        JsonObjectCacheWriteRequest(
            schema_version="1.0", path=str(validation_path), payload={"status": "pass"}
        ),
        _ctx(),
    )
    refs = [
        {
            "schema_version": "1.0",
            "artifact_id": name,
            "kind": name,
            "path": str(path),
            "content_hash": "",
            "producer_step": "analysis_complete",
            "required": True,
            "created_at_utc": "2026-01-01T00:00:00+00:00",
        }
        for name, path in (
            ("artifacts", artifacts_path),
            ("doc_map", doc_map_path),
            ("validation", validation_path),
        )
    ]
    checkpoint = PipelineStageCheckpoint(
        schema_version="1.0",
        pipeline_name="report_generation",
        file_id="file-1",
        report_slug="report",
        stage_name="analysis_complete",
        stage_status="completed",
        artifact_refs={
            "artifacts": str(artifacts_path),
            "doc_map": str(doc_map_path),
            "validation": str(validation_path),
        },
        payload={
            "artifact_registry": {"schema_version": "1.0", "refs": refs},
            "artifact_lineage": {},
            "analysis": {"artifacts_payload": {"summary": {}}},
        },
        completed_at_utc="2026-01-01T00:00:00+00:00",
        source_run_id="r",
        source_task_id="t",
    )
    write_pipeline_checkpoint(
        PipelineCheckpointWriteRequest(
            schema_version="1.0", checkpoint_root=str(tmp_path), checkpoint=checkpoint
        ),
        _ctx(),
    )

    response = remediate_report_card_date_checkpoint(
        ReportCardCheckpointRemediationRequest(
            schema_version="1.0",
            checkpoint_root=str(tmp_path),
            file_id="file-1",
            reports_db_path=str(tmp_path / "reports.sqlite"),
        ),
        _ctx(),
    )

    assert response.result.publication_date == "2026-01-15"
    assert response.result.date_source == "doc_map.publication_date"
    restored = read_pipeline_checkpoint(
        PipelineCheckpointReadRequest(
            schema_version="1.0",
            checkpoint_root=str(tmp_path),
            pipeline_name="report_generation",
            file_id="file-1",
            stage_name="analysis_complete",
        ),
        _ctx(),
    ).checkpoint
    assert restored is not None
    assert (
        restored.payload["analysis"]["artifacts_payload"]["publication_date"]
        == "2026-01-15"
    )
    assert (
        restored.payload["artifact_lineage"]["artifacts"]
        == response.artifact_lineage_id
    )
    reuse = check_artifact_reuse(
        ArtifactReuseCheckRequest(
            schema_version="1.0",
            db_path=str(tmp_path / "reports.sqlite"),
            artifact_id=response.artifact_lineage_id,
            expected_schema_version="1.0",
            expected_processing_version="report_generation_checkpoint_v1",
        ),
        _ctx(),
    )
    assert reuse.reusable is True


def test_missing_checkpoint_creates_operator_held_remediation(tmp_path: Path) -> None:
    request = ReportCardCheckpointRemediationRequest(
        schema_version="1.0",
        checkpoint_root=str(tmp_path),
        file_id="missing-file",
        reports_db_path=str(tmp_path / "reports.sqlite"),
        state_db=str(tmp_path / "state.sqlite"),
    )

    with pytest.raises(AppError):
        remediate_report_card_date_checkpoint(request, _ctx())

    records = list_remediation_records(
        RemediationListRequest(
            schema_version="1.0",
            state_db=request.state_db,
            workflow="report_card_date_remediation",
        ),
        _ctx(),
    ).records
    assert len(records) == 1
    assert records[0].status == "operator_action_required"
