from __future__ import annotations

from pathlib import Path

from src.contracts.artifact_lineage import (
    ARTIFACT_LINEAGE_SCHEMA_VERSION,
    ArtifactInvalidationRequest,
    ArtifactLineageBackfillRequest,
    ArtifactLineageRegistrationRequest,
    ArtifactLineageTraceRequest,
    ArtifactReuseCheckRequest,
)
from src.services.report_store_service import (
    backfill_artifact_lineage,
    check_artifact_reuse,
    invalidate_artifacts,
    record_artifact_lineage,
    trace_artifact_lineage,
)


def _register(
    db_path: Path,
    artifact_path: Path,
    run_context,
    *,
    kind: str,
    report_id: str = "report-1",
    source_id: str = "source-1",
    dependencies: list[str] | None = None,
    prompt_hash: str = "",
    metadata: dict[str, object] | None = None,
) -> object:
    return record_artifact_lineage(
        ArtifactLineageRegistrationRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            artifact_kind=kind,
            report_id=report_id,
            source_id=source_id,
            storage_ref=str(artifact_path),
            producer="test",
            schema_version_used="1.0",
            processing_version="test-v1",
            dependency_artifact_ids=dependencies or [],
            prompt_hash=prompt_hash,
            validation_status="pass",
            metadata=metadata or {},
        ),
        run_context,
    )


def test_lineage_persists_immutable_identity_edges_and_compatible_reuse(
    tmp_path: Path, run_context
) -> None:
    db_path = tmp_path / "reports.sqlite"
    source_path = tmp_path / "source.pdf"
    html_path = tmp_path / "report.html"
    source_path.write_bytes(b"canonical source")
    html_path.write_text("<h1>canonical report</h1>", encoding="utf-8")

    source = _register(db_path, source_path, run_context, kind="source_pdf")
    rendered = _register(
        db_path,
        html_path,
        run_context,
        kind="rendered_html",
        dependencies=[source.record.artifact_id],
        metadata={"template_hash": "template-v1"},
    )
    repeated = _register(
        db_path,
        html_path,
        run_context,
        kind="rendered_html",
        dependencies=[source.record.artifact_id],
        metadata={"template_hash": "template-v1"},
    )

    assert source.created is True
    assert rendered.created is True
    assert repeated.created is False
    assert repeated.record.artifact_id == rendered.record.artifact_id
    trace = trace_artifact_lineage(
        ArtifactLineageTraceRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            artifact_id=rendered.record.artifact_id,
        ),
        run_context,
    )
    assert (rendered.record.artifact_id, source.record.artifact_id) in trace.edges
    assert {record.artifact_kind for record in trace.records} == {
        "source_pdf",
        "rendered_html",
    }
    reuse = check_artifact_reuse(
        ArtifactReuseCheckRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            artifact_id=rendered.record.artifact_id,
            expected_schema_version="1.0",
            expected_processing_version="test-v1",
            expected_validation_status="pass",
        ),
        run_context,
    )
    assert reuse.reusable is True
    html_path.write_text("changed", encoding="utf-8")
    changed = check_artifact_reuse(
        ArtifactReuseCheckRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            artifact_id=rendered.record.artifact_id,
            expected_schema_version="1.0",
            expected_processing_version="test-v1",
            expected_validation_status="pass",
        ),
        run_context,
    )
    assert changed.reusable is False
    assert changed.reason == "content_changed"


def test_selective_invalidation_preserves_analysis_for_render_only_changes(
    tmp_path: Path, run_context
) -> None:
    db_path = tmp_path / "reports.sqlite"
    paths = {}
    for name in ("source", "analysis", "crop", "validation", "render"):
        path = tmp_path / f"{name}.json"
        path.write_text(name, encoding="utf-8")
        paths[name] = path
    source = _register(db_path, paths["source"], run_context, kind="source_pdf")
    analysis = _register(
        db_path,
        paths["analysis"],
        run_context,
        kind="extracted_text",
        dependencies=[source.record.artifact_id],
        prompt_hash="prompt-v1",
    )
    crop = _register(
        db_path,
        paths["crop"],
        run_context,
        kind="crop_image",
        dependencies=[analysis.record.artifact_id],
        metadata={"crop_hash": "crop-v1"},
    )
    validation = _register(
        db_path,
        paths["validation"],
        run_context,
        kind="validation",
        dependencies=[analysis.record.artifact_id],
        metadata={"validator_hash": "validator-v1"},
    )
    rendered = _register(
        db_path,
        paths["render"],
        run_context,
        kind="rendered_html",
        dependencies=[crop.record.artifact_id, validation.record.artifact_id],
        metadata={"template_hash": "template-v1"},
    )

    template = invalidate_artifacts(
        ArtifactInvalidationRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            change_kind="template",
            changed_value="template-v1",
        ),
        run_context,
    )
    assert template.invalidated_artifact_ids == [rendered.record.artifact_id]
    assert analysis.record.artifact_id not in template.invalidated_artifact_ids
    assert crop.record.artifact_id not in template.invalidated_artifact_ids
    assert validation.record.artifact_id not in template.invalidated_artifact_ids

    source_change = invalidate_artifacts(
        ArtifactInvalidationRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            change_kind="source",
            changed_value="source-1",
            dry_run=True,
        ),
        run_context,
    )
    assert set(source_change.invalidated_artifact_ids) == {
        source.record.artifact_id,
        analysis.record.artifact_id,
        crop.record.artifact_id,
        rendered.record.artifact_id,
        validation.record.artifact_id,
    }

    prompt = invalidate_artifacts(
        ArtifactInvalidationRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            change_kind="prompt",
            changed_value="prompt-v1",
            dry_run=True,
        ),
        run_context,
    )
    assert set(prompt.invalidated_artifact_ids) == {
        analysis.record.artifact_id,
        crop.record.artifact_id,
        rendered.record.artifact_id,
        validation.record.artifact_id,
    }
    crop_change = invalidate_artifacts(
        ArtifactInvalidationRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            change_kind="crop",
            changed_value="crop-v1",
            dry_run=True,
        ),
        run_context,
    )
    assert set(crop_change.invalidated_artifact_ids) == {
        crop.record.artifact_id,
        rendered.record.artifact_id,
    }
    validator_change = invalidate_artifacts(
        ArtifactInvalidationRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            change_kind="validator",
            changed_value="validator-v1",
            dry_run=True,
        ),
        run_context,
    )
    assert set(validator_change.invalidated_artifact_ids) == {
        rendered.record.artifact_id,
        validation.record.artifact_id,
    }


def test_backfill_reads_legacy_checkpoint_artifact_refs_from_workspace_root(
    tmp_path: Path, run_context
) -> None:
    workspace = tmp_path / "workspace"
    checkpoint_root = workspace / "out" / ".checkpoints" / "report_generation"
    checkpoint_dir = checkpoint_root / "report-1"
    checkpoint_dir.mkdir(parents=True)
    source_path = workspace / "cache" / "report-1.pdf"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"source")
    artifacts_path = (
        workspace / "out" / "report-1" / "report_analysis" / "artifacts.json"
    )
    artifacts_path.parent.mkdir(parents=True)
    artifacts_path.write_text("{}", encoding="utf-8")
    (checkpoint_dir / "analysis_complete.json").write_text(
        '{"file_id":"report-1","stage_name":"analysis_complete","artifact_refs":'
        '{"source_pdf":"cache/report-1.pdf","analysis_pdf":"cache/report-1.pdf",'
        '"artifacts":"out/report-1/report_analysis/artifacts.json"}}',
        encoding="utf-8",
    )

    result = backfill_artifact_lineage(
        ArtifactLineageBackfillRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(workspace / "state" / "reports.sqlite"),
            checkpoint_root=str(checkpoint_root),
            dry_run=False,
        ),
        run_context,
    )

    assert result.scanned_checkpoints == 1
    assert result.eligible_artifacts == 3
    assert result.created_artifacts == 3
    assert result.skipped_artifacts == 0
