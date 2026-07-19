from __future__ import annotations

from pathlib import Path

from src.contracts.artifact_lineage import (
    ARTIFACT_LINEAGE_SCHEMA_VERSION,
    ArtifactInvalidationRequest,
    ArtifactLineageAuditRequest,
    ArtifactLineageBackfillRequest,
    ArtifactLineageRegistrationRequest,
    ArtifactLineageTraceRequest,
    ArtifactReuseCheckRequest,
)
from src.services.report_store_service import (
    audit_artifact_lineage,
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
            lineage_status="complete",
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


def test_reuse_rejects_execution_identity_mismatch_and_reads_legacy_records(
    tmp_path: Path, run_context
) -> None:
    db_path = tmp_path / "reports.sqlite"
    artifact_path = tmp_path / "summary.json"
    artifact_path.write_text('{"summary":"retained"}', encoding="utf-8")
    current = _register(
        db_path,
        artifact_path,
        run_context,
        kind="artifacts",
        metadata={"execution_identity": "current-execution-identity"},
    )
    mismatch = check_artifact_reuse(
        ArtifactReuseCheckRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            artifact_id=current.record.artifact_id,
            expected_schema_version="1.0",
            expected_processing_version="test-v1",
            expected_execution_identity="changed-execution-identity",
            expected_validation_status="pass",
        ),
        run_context,
    )
    assert mismatch.reusable is False
    assert mismatch.reason == "execution_identity_mismatch"

    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text('{"summary":"legacy"}', encoding="utf-8")
    legacy = _register(db_path, legacy_path, run_context, kind="legacy_artifacts")
    readable = check_artifact_reuse(
        ArtifactReuseCheckRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            artifact_id=legacy.record.artifact_id,
            expected_schema_version="1.0",
            expected_processing_version="test-v1",
            expected_validation_status="pass",
        ),
        run_context,
    )
    compatibility_checked = check_artifact_reuse(
        ArtifactReuseCheckRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            artifact_id=legacy.record.artifact_id,
            expected_schema_version="1.0",
            expected_processing_version="test-v1",
            expected_execution_identity="current-execution-identity",
            expected_validation_status="pass",
        ),
        run_context,
    )
    assert readable.reusable is True
    assert compatibility_checked.reusable is False
    assert compatibility_checked.reason == "legacy_identity"


def test_new_materialization_supersedes_active_record_at_the_same_path(
    tmp_path: Path, run_context
) -> None:
    db_path = tmp_path / "reports.sqlite"
    html_path = tmp_path / "report.html"
    html_path.write_text("<h1>canonical report</h1>", encoding="utf-8")

    original = _register(
        db_path,
        html_path,
        run_context,
        kind="rendered_html",
        metadata={"template_hash": "template-v1"},
    )
    replacement = _register(
        db_path,
        html_path,
        run_context,
        kind="rendered_html",
        metadata={"template_hash": "template-v2"},
    )

    old_reuse = check_artifact_reuse(
        ArtifactReuseCheckRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            artifact_id=original.record.artifact_id,
            expected_schema_version="1.0",
            expected_processing_version="test-v1",
            expected_validation_status="pass",
        ),
        run_context,
    )
    new_reuse = check_artifact_reuse(
        ArtifactReuseCheckRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            artifact_id=replacement.record.artifact_id,
            expected_schema_version="1.0",
            expected_processing_version="test-v1",
            expected_validation_status="pass",
        ),
        run_context,
    )

    assert original.record.artifact_id != replacement.record.artifact_id
    assert old_reuse.reusable is False
    assert old_reuse.reason == "not_active"
    assert old_reuse.record is not None
    assert old_reuse.record.state == "superseded"
    assert old_reuse.record.superseded_by == replacement.record.artifact_id
    assert new_reuse.reusable is True

    restored = _register(
        db_path,
        html_path,
        run_context,
        kind="rendered_html",
        metadata={"template_hash": "template-v1"},
    )
    restored_reuse = check_artifact_reuse(
        ArtifactReuseCheckRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            artifact_id=restored.record.artifact_id,
            expected_schema_version="1.0",
            expected_processing_version="test-v1",
            expected_validation_status="pass",
        ),
        run_context,
    )
    replaced_reuse = check_artifact_reuse(
        ArtifactReuseCheckRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=str(db_path),
            artifact_id=replacement.record.artifact_id,
            expected_schema_version="1.0",
            expected_processing_version="test-v1",
            expected_validation_status="pass",
        ),
        run_context,
    )

    assert restored.created is False
    assert restored_reuse.reusable is True
    assert replaced_reuse.reusable is False
    assert replaced_reuse.record is not None
    assert replaced_reuse.record.state == "superseded"
    assert replaced_reuse.record.superseded_by == original.record.artifact_id


def test_superseding_materialization_supersedes_active_descendants(
    tmp_path: Path, run_context
) -> None:
    db_path = tmp_path / "reports.sqlite"
    source_path = tmp_path / "source.pdf"
    html_path = tmp_path / "report.html"
    source_path.write_bytes(b"canonical source")
    html_path.write_text("<h1>canonical report</h1>", encoding="utf-8")

    source = _register(
        db_path,
        source_path,
        run_context,
        kind="source_pdf",
        metadata={"parser_hash": "parser-v1"},
    )
    rendered = _register(
        db_path,
        html_path,
        run_context,
        kind="rendered_html",
        dependencies=[source.record.artifact_id],
    )
    replacement = _register(
        db_path,
        source_path,
        run_context,
        kind="source_pdf",
        metadata={"parser_hash": "parser-v2"},
    )

    rendered_reuse = check_artifact_reuse(
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

    assert replacement.created is True
    assert rendered_reuse.reusable is False
    assert rendered_reuse.record is not None
    assert rendered_reuse.record.state == "superseded"
    assert rendered_reuse.record.superseded_by == replacement.record.artifact_id


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
    assert result.incomplete_artifacts == 3


def test_lineage_audit_and_backfill_promote_only_explicit_checkpoint_proof(
    tmp_path: Path, run_context
) -> None:
    workspace = tmp_path / "workspace"
    checkpoint_root = workspace / "out" / ".checkpoints" / "report_generation"
    checkpoint_dir = checkpoint_root / "report-1"
    checkpoint_dir.mkdir(parents=True)
    source_path = workspace / "cache" / "report-1.pdf"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"source")
    analysis_path = workspace / "out" / "report-1" / "analysis.pdf"
    analysis_path.parent.mkdir(parents=True)
    analysis_path.write_bytes(b"analysis")
    (checkpoint_dir / "analysis_complete.json").write_text(
        """{
          "file_id":"report-1",
          "source_id":"source-sha256-1",
          "stage_name":"analysis_complete",
          "payload":{
            "processing_version":"checkpoint-v2",
            "artifact_registry":{"refs":[
              {"artifact_id":"source_pdf","path":"%s","producer_step":"source_prepared","schema_version":"1.0","processing_version":"checkpoint-v2"},
              {"artifact_id":"analysis_pdf","path":"%s","producer_step":"analysis_complete","schema_version":"1.0","processing_version":"checkpoint-v2"}
            ]}
          }
        }"""
        % (source_path.as_posix(), analysis_path.as_posix()),
        encoding="utf-8",
    )
    request = ArtifactLineageBackfillRequest(
        schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
        db_path=str(workspace / "state" / "reports.sqlite"),
        checkpoint_root=str(checkpoint_root),
        dry_run=False,
    )

    first = backfill_artifact_lineage(request, run_context)
    second = backfill_artifact_lineage(request, run_context)
    audit = audit_artifact_lineage(
        ArtifactLineageAuditRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=request.db_path,
            report_id="report-1",
        ),
        run_context,
    )

    assert first.created_artifacts == 2
    assert first.incomplete_artifacts == 0
    assert second.created_artifacts == 0
    assert audit.status_counts == {"complete": 2}
    assert all(item.hash_state == "verified" for item in audit.items)
    assert all(item.missing_field_codes == () for item in audit.items)
