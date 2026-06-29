from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestSettings
from src.contracts.files import PipelineStageCheckpoint
from src.contracts.report_artifacts import ArtifactRef, ArtifactRegistry
from src.contracts.run_context import RunContext
from src.orchestrators import report_generation_orchestrator as rgo
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


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
        state_db=str(tmp_path / "state" / "index.sqlite"),
        reports_db=str(tmp_path / "state" / "reports.sqlite"),
        category_mapping_path="./src/config/category-mappings.yaml",
        cover_style_path="./src/config/cover-styles.yaml",
        ingest_lock_path=str(tmp_path / "state" / "ingest.lock"),
        ingest_lock_ttl_seconds=7200.0,
        temperature=1.0,
    )


def _runtime(tmp_path: Path):
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF artifact registry test")
    return rgo._build_runtime_state(
        DriveFile(
            schema_version="1.0",
            file_id="file-artifacts",
            name="artifact.pdf",
            modified_time=None,
            md5_checksum="md5",
        ),
        str(pdf_path),
        _settings(tmp_path),
        "md5",
        _ctx(),
    )


def test_checkpoint_write_records_typed_artifact_registry(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    source_pdf = Path(runtime.local_pdf_path)

    checkpoint_path = rgo._write_stage_checkpoint(
        runtime,
        stage_name="source_prepared",
        artifact_refs={"source_pdf": str(source_pdf)},
        payload={"schema_version": "1.0"},
    )

    payload = json.loads(Path(checkpoint_path).read_text(encoding="utf-8"))
    registry = payload["payload"]["artifact_registry"]
    ref = registry["refs"][0]
    assert registry["schema_version"] == "1.0"
    assert ref["artifact_id"] == "source_pdf"
    assert ref["kind"] == "source_pdf"
    assert ref["path"] == str(source_pdf.resolve())
    assert ref["content_hash"]
    assert ref["producer_step"] == "source_prepared"
    assert ref["required"] is True
    assert ref["created_at_utc"]


def test_artifact_registry_rejects_duplicate_artifact_ids() -> None:
    ref = ArtifactRef(
        schema_version="1.0",
        artifact_id="source_pdf",
        kind="source_pdf",
        path="source.pdf",
        content_hash="hash",
        producer_step="source_prepared",
        required=True,
        created_at_utc="2026-06-29T00:00:00+00:00",
    )
    registry = ArtifactRegistry(schema_version="1.0", refs=[ref, ref])

    with pytest.raises(AppError) as exc_info:
        registry.validate()

    assert exc_info.value.code == "artifact_registry_duplicate_id"
    assert exc_info.value.retryable is False


def test_checkpoint_validation_rejects_missing_required_registry_artifact(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    missing_path = tmp_path / "missing.pdf"
    checkpoint = PipelineStageCheckpoint(
        schema_version="1.0",
        pipeline_name="report_generation",
        file_id=runtime.file.file_id,
        report_slug=runtime.report_name,
        stage_name="source_prepared",
        stage_status="completed",
        artifact_refs={"source_pdf": str(missing_path)},
        payload={
            "schema_version": "1.0",
            "artifact_registry": {
                "schema_version": "1.0",
                "refs": [
                    {
                        "schema_version": "1.0",
                        "artifact_id": "source_pdf",
                        "kind": "source_pdf",
                        "path": str(missing_path),
                        "content_hash": "missing-hash",
                        "producer_step": "source_prepared",
                        "required": True,
                        "created_at_utc": "2026-06-29T00:00:00+00:00",
                    }
                ],
            },
        },
        completed_at_utc="2026-06-29T00:00:00+00:00",
        source_run_id="r",
        source_task_id="t",
    )

    with pytest.raises(AppError) as exc_info:
        rgo._validate_checkpoint_artifacts(runtime, checkpoint, "checkpoint.json")

    assert exc_info.value.code == "report_pipeline_checkpoint_artifact_missing"
    assert exc_info.value.context["artifact_id"] == "source_pdf"


def test_checkpoint_validation_allows_absent_optional_registry_artifact(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    optional_path = tmp_path / "optional.png"
    checkpoint = PipelineStageCheckpoint(
        schema_version="1.0",
        pipeline_name="report_generation",
        file_id=runtime.file.file_id,
        report_slug=runtime.report_name,
        stage_name="source_prepared",
        stage_status="completed",
        artifact_refs={"preview_image": str(optional_path)},
        payload={
            "schema_version": "1.0",
            "artifact_registry": {
                "schema_version": "1.0",
                "refs": [
                    {
                        "schema_version": "1.0",
                        "artifact_id": "preview_image",
                        "kind": "preview_image",
                        "path": str(optional_path),
                        "content_hash": "",
                        "producer_step": "source_prepared",
                        "required": False,
                        "created_at_utc": "2026-06-29T00:00:00+00:00",
                    }
                ],
            },
        },
        completed_at_utc="2026-06-29T00:00:00+00:00",
        source_run_id="r",
        source_task_id="t",
    )

    rgo._validate_checkpoint_artifacts(runtime, checkpoint, "checkpoint.json")
