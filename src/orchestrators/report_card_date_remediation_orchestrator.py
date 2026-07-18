"""Checkpoint-safe report-card date remediation orchestration."""

from __future__ import annotations

from copy import deepcopy

from src.contracts.artifact_lineage import (
    ARTIFACT_LINEAGE_SCHEMA_VERSION,
    ArtifactLineageRegistrationRequest,
)
from src.contracts.files import (
    FileStatRequest,
    JsonObjectCacheWriteRequest,
    PipelineCheckpointReadRequest,
    PipelineCheckpointWriteRequest,
    PipelineStageCheckpoint,
    ReadJsonRequest,
)
from src.contracts.report_artifacts import artifact_registry_from_payload
from src.contracts.report_card_remediation import (
    ReportCardCheckpointRemediationRequest,
    ReportCardCheckpointRemediationResponse,
    ReportCardPublicationDateRemediationRequest,
)
from src.contracts.remediation import RemediationArtifactReference
from src.contracts.run_context import RunContext
from src.generators.report_card_date_remediation_generator import (
    apply_report_card_publication_date_remediation,
    remediate_report_card_publication_date,
)
from src.services.file_service import (
    file_stat,
    read_json,
    read_pipeline_checkpoint,
    write_json_object_cache,
    write_pipeline_checkpoint,
)
from src.services.report_store_service import record_artifact_lineage
from src.utils.errors import AppError
from src.orchestrators.remediation_orchestrator import (
    record_workflow_failure,
    remediation_input_checksum,
)

_PIPELINE_NAME = "report_generation"
_STAGE_NAME = "analysis_complete"


def _remediate_report_card_date_checkpoint(
    request: ReportCardCheckpointRemediationRequest,
    ctx: RunContext,
) -> ReportCardCheckpointRemediationResponse:
    """Repair only artifacts.json, refresh lineage, and preserve upstream checkpoint work."""
    checkpoint_response = read_pipeline_checkpoint(
        PipelineCheckpointReadRequest(
            schema_version="1.0",
            checkpoint_root=request.checkpoint_root,
            pipeline_name=_PIPELINE_NAME,
            file_id=request.file_id,
            stage_name=_STAGE_NAME,
        ),
        ctx,
    )
    checkpoint = checkpoint_response.checkpoint
    if (
        not checkpoint_response.found
        or checkpoint is None
        or checkpoint.stage_status != "completed"
    ):
        raise AppError(
            code="report_card_publication_date_checkpoint_missing",
            message="Publication-date remediation requires a completed analysis checkpoint",
            retryable=False,
            context={
                "file_id": request.file_id,
                "checkpoint_path": checkpoint_response.checkpoint_path,
            },
        )
    registry = artifact_registry_from_payload(
        checkpoint.payload.get("artifact_registry")
    )
    if registry is None:
        raise AppError(
            code="report_card_publication_date_registry_missing",
            message="Publication-date remediation requires a typed artifact registry",
            retryable=False,
            context={"file_id": request.file_id},
        )
    ref_paths = {ref.artifact_id: ref.path for ref in registry.refs}
    required = {"artifacts", "doc_map", "validation"}
    missing = sorted(required - set(ref_paths))
    if missing:
        raise AppError(
            code="report_card_publication_date_registry_missing",
            message="Publication-date remediation is missing required registry refs",
            retryable=False,
            context={"file_id": request.file_id, "missing_refs": missing},
        )
    artifacts_payload = _read_object(ref_paths["artifacts"], ctx)
    doc_map_payload = _read_object(ref_paths["doc_map"], ctx)
    validation_payload = _read_object(ref_paths["validation"], ctx)
    result = remediate_report_card_publication_date(
        ReportCardPublicationDateRemediationRequest(
            schema_version="1.0",
            file_id=request.file_id,
            artifact_registry=registry,
            artifacts_payload=artifacts_payload,
            doc_map_payload=doc_map_payload,
            validation_payload=validation_payload,
            rendered_html_path=ref_paths.get("rendered_html", ""),
            operator_date=request.operator_date,
            operator_id=request.operator_id,
            operator_reason=request.operator_reason,
            resume_stage=_STAGE_NAME,
        )
    )
    repaired_artifacts = apply_report_card_publication_date_remediation(
        artifacts_payload, result
    )
    write_json_object_cache(
        JsonObjectCacheWriteRequest(
            schema_version="1.0",
            path=ref_paths["artifacts"],
            payload=repaired_artifacts,
        ),
        ctx,
    )
    artifacts_stat = file_stat(
        FileStatRequest(
            schema_version="1.0", path=ref_paths["artifacts"], compute_md5=True
        ),
        ctx,
    )
    if (
        not artifacts_stat.exists
        or not artifacts_stat.is_file
        or not artifacts_stat.md5
    ):
        raise AppError(
            code="report_card_publication_date_artifacts_write_unverified",
            message="Repaired artifacts JSON could not be verified",
            retryable=False,
            context={"path": ref_paths["artifacts"]},
        )
    lineage = dict(checkpoint.payload.get("artifact_lineage") or {})
    dependency_ids = [
        lineage[name]
        for name in ("analysis_pdf", "doc_map")
        if isinstance(lineage.get(name), str) and lineage[name]
    ]
    lineage_response = record_artifact_lineage(
        ArtifactLineageRegistrationRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=request.reports_db_path,
            artifact_kind="artifacts",
            report_id=request.file_id,
            source_id=request.source_id,
            storage_ref=artifacts_stat.path,
            producer="report_card_date_remediation",
            schema_version_used="1.0",
            processing_version="report_generation_checkpoint_v1",
            dependency_artifact_ids=dependency_ids,
            validation_status="not_applicable",
            metadata={
                "remediation_code": "repair_report_card_publication_date",
                "idempotency_key": result.idempotency_key,
                "date_source": result.date_source,
            },
            compatibility={
                "schema_versions": {"artifacts": "1.0"},
                "processing_versions": {"artifacts": "report_generation_checkpoint_v1"},
            },
            lineage_status=(
                "complete" if request.source_id.strip() else "legacy_incomplete"
            ),
        ),
        ctx,
    )
    updated_registry = []
    for ref in registry.refs:
        raw = {
            "schema_version": ref.schema_version,
            "artifact_id": ref.artifact_id,
            "kind": ref.kind,
            "path": ref.path,
            "content_hash": ref.content_hash,
            "producer_step": ref.producer_step,
            "required": ref.required,
            "created_at_utc": ref.created_at_utc,
        }
        if ref.artifact_id == "artifacts":
            raw["content_hash"] = artifacts_stat.md5
            raw["producer_step"] = "report_card_date_remediation"
        updated_registry.append(raw)
    payload = deepcopy(checkpoint.payload)
    payload["artifact_registry"] = {
        "schema_version": registry.schema_version,
        "refs": updated_registry,
    }
    payload["artifact_lineage"] = {
        **lineage,
        "artifacts": lineage_response.record.artifact_id,
    }
    analysis = payload.get("analysis")
    if isinstance(analysis, dict):
        analysis["artifacts_payload"] = repaired_artifacts
    updated_checkpoint = PipelineStageCheckpoint(
        schema_version=checkpoint.schema_version,
        pipeline_name=checkpoint.pipeline_name,
        file_id=checkpoint.file_id,
        report_slug=checkpoint.report_slug,
        stage_name=checkpoint.stage_name,
        stage_status=checkpoint.stage_status,
        artifact_refs=dict(checkpoint.artifact_refs),
        payload=payload,
        completed_at_utc=checkpoint.completed_at_utc,
        source_run_id=checkpoint.source_run_id,
        source_task_id=checkpoint.source_task_id,
    )
    checkpoint_write = write_pipeline_checkpoint(
        PipelineCheckpointWriteRequest(
            schema_version="1.0",
            checkpoint_root=request.checkpoint_root,
            checkpoint=updated_checkpoint,
        ),
        ctx,
    )
    return ReportCardCheckpointRemediationResponse(
        schema_version="1.0",
        result=result,
        checkpoint_path=checkpoint_write.checkpoint_path,
        artifacts_path=artifacts_stat.path,
        artifact_lineage_id=lineage_response.record.artifact_id,
    )


def remediate_report_card_date_checkpoint(
    request: ReportCardCheckpointRemediationRequest,
    ctx: RunContext,
) -> ReportCardCheckpointRemediationResponse:
    """Apply the constrained repair and record any terminal workflow failure."""

    try:
        return _remediate_report_card_date_checkpoint(request, ctx)
    except Exception as exc:
        record_workflow_failure(
            state_db=request.state_db,
            workflow="report_card_date_remediation",
            stage="checkpoint_repair",
            operation="remediate_report_card_date_checkpoint",
            error=exc,
            ctx=ctx,
            input_checksum=remediation_input_checksum(
                {
                    "file_id": request.file_id,
                    "source_id": request.source_id,
                    "checkpoint_root": request.checkpoint_root,
                    "operator_date": request.operator_date,
                }
            ),
            report_id=request.file_id,
            source_id=request.source_id,
            reusable_artifacts=[
                RemediationArtifactReference(
                    schema_version="1.0",
                    name="report_generation_checkpoint_root",
                    reference=request.checkpoint_root,
                ),
                RemediationArtifactReference(
                    schema_version="1.0",
                    name="report_artifact_lineage_db",
                    reference=request.reports_db_path,
                ),
            ],
        )
        raise


def _read_object(path: str, ctx: RunContext) -> dict:
    payload = read_json(ReadJsonRequest(schema_version="1.0", path=path), ctx).payload
    if not isinstance(payload, dict):
        raise AppError(
            code="report_card_publication_date_artifact_invalid",
            message="Publication-date remediation requires JSON-object artifacts",
            retryable=False,
            context={"path": path},
        )
    return payload


__all__ = ["remediate_report_card_date_checkpoint"]
