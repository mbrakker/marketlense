from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.contracts.artifact_lineage import (
    ARTIFACT_LINEAGE_SCHEMA_VERSION,
    ArtifactLineageRegistrationRequest,
)
from src.contracts.drive import DriveFile
from src.contracts.files import (
    FileStatRequest,
    PipelineCheckpointWriteRequest,
    PipelineStageCheckpoint,
)
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.pdf_text import PdfTextExtractResponse
from src.contracts.pdf_utils import PdfInfoResponse
from src.contracts.prompt_family_materialization import (
    PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
    PromptFamilyMaterializationRequest,
)
from src.contracts.prompts import PromptLoadRequest
from src.contracts.regeneration import (
    RegenerationAttemptResult,
    RegenerationLoopState,
)
from src.contracts.report_artifacts import (
    ArtifactRef,
    ArtifactRegistry,
    artifact_registry_to_payload,
)
from src.contracts.report_assets import PreviewResponse
from src.contracts.report_generation import (
    ReportAnalysisState,
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.report_models import Figure, Quote, ReportFigureAsset, ReportPayload
from src.contracts.report_store import (
    SourceIdentityResolution,
    SourcePublicationMetadata,
)
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationIssue, ValidationReport
from src.generators.report_analysis_generator import VectorStoreIndexingState
from src.generators.report_generation_shared import derive_title, report_slug
from src.services import prompt_service
from src.services.file_service import (
    file_stat,
    write_pipeline_checkpoint,
)
from src.services.prompt_family_materialization_service import materialize_prompt_family
from src.services.report_store_service import record_artifact_lineage
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.report_generation_orchestrator")
REPORT_PIPELINE_NAME = "report_generation"
STAGE_SOURCE_PREPARED = "source_prepared"
STAGE_SELECTION_COMPLETE = "selection_complete"
STAGE_ANALYSIS_COMPLETE = "analysis_complete"
STAGE_RENDER_COMPLETE = "render_complete"


def _build_runtime_state(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
    *,
    publisher_name: str = "",
    source_report_name: str = "",
    source_url: str = "",
    source_publication_metadata: SourcePublicationMetadata | None = None,
    source_identity: SourceIdentityResolution | None = None,
    execution_compatibility: Optional[dict[str, object]] = None,
    execution_plan_hash: str = "",
    execution_plan_intent: str = "",
    planned_stages: Optional[list[str]] = None,
) -> ReportRuntimeState:
    report_worker_limit = getattr(settings, "report_worker_limit", 1)
    try:
        report_worker_limit = int(report_worker_limit)
    except (TypeError, ValueError):
        report_worker_limit = 1
    if report_worker_limit < 1:
        report_worker_limit = 1
    file_name = file.name or file.file_id
    return ReportRuntimeState(
        schema_version="1.0",
        file=file,
        local_pdf_path=local_pdf_path,
        settings=settings,
        md5=md5,
        ctx=ctx,
        file_name=file_name,
        report_name=report_slug(file_name, file.file_id),
        report_title=derive_title(file_name),
        analysis_mode="vector_store",
        analysis_modes=["vector_store"],
        report_worker_limit=report_worker_limit,
        parallel_within_file=report_worker_limit > 1,
        publisher_name=str(publisher_name or "").strip(),
        source_report_name=str(source_report_name or "").strip(),
        source_url=str(source_url or "").strip(),
        source_publication_metadata=source_publication_metadata,
        source_identity=source_identity,
        execution_compatibility=dict(execution_compatibility or {}),
        execution_plan_hash=str(execution_plan_hash or "").strip(),
        execution_plan_intent=str(execution_plan_intent or "").strip(),
        planned_stages=[str(stage) for stage in (planned_stages or [])],
    )


def _report_payload_from_dict(raw_payload: object) -> ReportPayload:
    if not isinstance(raw_payload, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint report payload must be an object",
            retryable=False,
        )
    try:
        quote_payload = raw_payload["quote"]
        figure_payload = raw_payload["figure"]
        if not isinstance(quote_payload, dict) or not isinstance(figure_payload, dict):
            raise TypeError("quote and figure must be objects")
        figure_assets: list[ReportFigureAsset] = []
        for raw_asset in raw_payload.get("_figure_assets", []):
            if not isinstance(raw_asset, dict):
                raise TypeError("figure asset must be an object")
            figure_assets.append(
                ReportFigureAsset(
                    image_path=str(raw_asset["image_path"]),
                    page=int(raw_asset["page"]),
                    candidate_id=str(raw_asset["candidate_id"]),
                    kind=str(raw_asset["kind"]),
                    is_primary=bool(raw_asset["is_primary"]),
                    detected_caption=str(raw_asset.get("detected_caption") or ""),
                    preview_text=str(raw_asset.get("preview_text") or ""),
                    generated_caption=str(raw_asset.get("generated_caption") or ""),
                    display_caption=str(raw_asset.get("display_caption") or ""),
                    caption_source=str(raw_asset.get("caption_source") or ""),
                    schema_version=str(raw_asset.get("schema_version") or "1.0"),
                )
            )
        return ReportPayload(
            tldr=str(raw_payload["tldr"]),
            title=str(raw_payload["title"]),
            insights=[str(item) for item in raw_payload["insights"]],
            quote=Quote(
                text=str(quote_payload["text"]),
                author=str(quote_payload.get("author") or "Unknown"),
                schema_version=str(quote_payload.get("schema_version") or "1.0"),
            ),
            figure=Figure(
                title=str(figure_payload["title"]),
                evidence=str(figure_payload["evidence"]),
                schema_version=str(figure_payload.get("schema_version") or "1.0"),
            ),
            commentary=str(raw_payload["commentary"]),
            source=str(raw_payload["source"]),
            publisher=str(raw_payload.get("publisher") or ""),
            taxonomy=[str(item) for item in raw_payload.get("taxonomy", [])],
            categories=[str(item) for item in raw_payload.get("categories", [])],
            region=str(raw_payload.get("region") or ""),
            time_period=str(raw_payload.get("time_period") or ""),
            contents_page_number=int(raw_payload.get("contents_page_number") or 0),
            contents_heading=str(raw_payload.get("contents_heading") or ""),
            _figure_image=str(raw_payload.get("_figure_image") or ""),
            _figure_gallery=[
                str(item) for item in raw_payload.get("_figure_gallery", [])
            ],
            _figure_top=str(raw_payload.get("_figure_top") or ""),
            _figure_assets=figure_assets,
            _figure_section_enabled=bool(
                raw_payload.get("_figure_section_enabled", True)
            ),
            _contents_image=str(raw_payload.get("_contents_image") or ""),
            _vector_store_id=str(raw_payload.get("_vector_store_id") or ""),
            _evidence_packs=dict(raw_payload.get("_evidence_packs") or {}),
            _text_density=float(raw_payload.get("_text_density") or 0.0),
            _text_pages_sampled=int(raw_payload.get("_text_pages_sampled") or 0),
            _text_char_count=int(raw_payload.get("_text_char_count") or 0),
            _text_not_available=bool(raw_payload.get("_text_not_available", False)),
            schema_version=str(raw_payload.get("schema_version") or "1.1"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint report payload is incomplete",
            cause=exc,
            retryable=False,
        ) from exc


def _validation_report_from_dict(raw_report: object) -> Optional[ValidationReport]:
    if raw_report is None:
        return None
    if not isinstance(raw_report, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint validation report must be an object",
            retryable=False,
        )
    issues: list[ValidationIssue] = []
    for raw_issue in raw_report.get("issues", []):
        if not isinstance(raw_issue, dict):
            raise AppError(
                code="report_pipeline_checkpoint_invalid",
                message="Checkpoint validation issue must be an object",
                retryable=False,
            )
        issues.append(
            ValidationIssue(
                message=str(raw_issue["message"]),
                severity=str(raw_issue["severity"]),
                affected_section=str(raw_issue["affected_section"]),
                rule_id=str(raw_issue.get("rule_id") or ""),
                repair_target=str(raw_issue.get("repair_target") or ""),
                entity_id=str(raw_issue.get("entity_id") or ""),
                schema_version=str(raw_issue.get("schema_version") or "1.0"),
            )
        )
    return ValidationReport(
        schema_version=str(raw_report["schema_version"]),
        status=str(raw_report["status"]),
        issues=issues,
        severity=str(raw_report.get("severity") or "pass"),
        source_path=str(raw_report.get("source_path") or ""),
    )


def _regeneration_loop_from_dict(raw_state: object) -> Optional[RegenerationLoopState]:
    if raw_state is None:
        return None
    if not isinstance(raw_state, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint regeneration loop state must be an object",
            retryable=False,
        )
    return RegenerationLoopState(
        attempt_count=int(raw_state["attempt_count"]),
        max_attempts=int(raw_state["max_attempts"]),
        final_status=str(raw_state["final_status"]),
        max_reached=bool(raw_state["max_reached"]),
        schema_version=str(raw_state.get("schema_version") or "1.0"),
    )


def _regeneration_attempts_from_list(
    raw_attempts: object,
) -> list[RegenerationAttemptResult]:
    if raw_attempts is None:
        return []
    if not isinstance(raw_attempts, list):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint regeneration attempts must be a list",
            retryable=False,
        )
    attempts: list[RegenerationAttemptResult] = []
    for raw_attempt in raw_attempts:
        if not isinstance(raw_attempt, dict):
            raise AppError(
                code="report_pipeline_checkpoint_invalid",
                message="Checkpoint regeneration attempt must be an object",
                retryable=False,
            )
        attempts.append(
            RegenerationAttemptResult(
                attempt_index=int(raw_attempt["attempt_index"]),
                plan_mode=str(raw_attempt["plan_mode"]),
                validation_before_status=str(raw_attempt["validation_before_status"]),
                validation_after_status=str(raw_attempt["validation_after_status"]),
                regenerated_sections=[
                    str(item) for item in raw_attempt.get("regenerated_sections", [])
                ],
                artifacts_path=str(raw_attempt.get("artifacts_path") or ""),
                artifacts_snapshot_path=str(
                    raw_attempt.get("artifacts_snapshot_path") or ""
                ),
                candidate_artifacts_path=str(
                    raw_attempt.get("candidate_artifacts_path") or ""
                ),
                candidate_audit_path=str(raw_attempt.get("candidate_audit_path") or ""),
                validation_path=str(raw_attempt.get("validation_path") or ""),
                validation_snapshot_path=str(
                    raw_attempt.get("validation_snapshot_path") or ""
                ),
                promotion_outcome=str(
                    raw_attempt.get("promotion_outcome") or "not_attempted"
                ),
                schema_version=str(raw_attempt.get("schema_version") or "1.0"),
            )
        )
    return attempts


def _write_stage_checkpoint(
    runtime: ReportRuntimeState,
    *,
    stage_name: str,
    artifact_refs: dict[str, str],
    payload: dict,
) -> str:
    checkpoint_payload = dict(payload)
    checkpoint_payload["artifact_integrity"] = _artifact_integrity_payload(
        runtime, artifact_refs
    )
    checkpoint_payload["artifact_registry"] = _artifact_registry_payload(
        runtime,
        stage_name=stage_name,
        artifact_refs=artifact_refs,
    )
    artifact_lineage, artifact_hashes = _record_checkpoint_artifact_lineage(
        runtime,
        stage_name=stage_name,
        artifact_registry=checkpoint_payload["artifact_registry"],
        payload=checkpoint_payload,
    )
    checkpoint_payload["artifact_lineage"] = artifact_lineage
    prompt_family_materializations = _record_prompt_family_materializations(
        runtime,
        stage_name=stage_name,
        payload=checkpoint_payload,
        artifact_lineage=artifact_lineage,
        artifact_hashes=artifact_hashes,
    )
    checkpoint_payload["prompt_family_materializations"] = (
        prompt_family_materializations
    )
    if stage_name == STAGE_RENDER_COMPLETE:
        _record_rendered_html_prompt_family_lineage(
            runtime,
            artifact_registry=checkpoint_payload["artifact_registry"],
            payload=checkpoint_payload,
            artifact_lineage=artifact_lineage,
            prompt_family_materializations=prompt_family_materializations,
        )
    response = write_pipeline_checkpoint(
        PipelineCheckpointWriteRequest(
            schema_version="1.0",
            checkpoint_root=runtime.settings.output_dir,
            checkpoint=PipelineStageCheckpoint(
                schema_version="1.0",
                pipeline_name=REPORT_PIPELINE_NAME,
                file_id=runtime.file.file_id,
                report_slug=runtime.report_name,
                stage_name=stage_name,
                stage_status="completed",
                artifact_refs=dict(artifact_refs),
                payload=checkpoint_payload,
                completed_at_utc=datetime.now(timezone.utc).isoformat(),
                source_run_id=str(runtime.ctx.run_id),
                source_task_id=str(runtime.ctx.task_id),
            ),
        ),
        runtime.ctx,
    )
    logger.info(
        log_event(
            runtime.ctx,
            role="orchestrator",
            event="report_pipeline_checkpoint_recorded",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "stage_name": stage_name,
                "checkpoint_path": response.checkpoint_path,
                "artifact_ref_count": len(artifact_refs),
                "artifact_registry_count": len(
                    checkpoint_payload["artifact_registry"]["refs"]
                ),
                "artifact_lineage_count": len(checkpoint_payload["artifact_lineage"]),
                "prompt_family_materialization_count": len(
                    checkpoint_payload["prompt_family_materializations"]
                ),
            },
        )
    )
    return response.checkpoint_path


def _record_checkpoint_artifact_lineage(
    runtime: ReportRuntimeState,
    *,
    stage_name: str,
    artifact_registry: dict,
    payload: dict,
) -> tuple[dict[str, str], dict[str, str]]:
    """Persist checkpoint artifacts without changing legacy checkpoint ref IDs."""
    lineage_ids: dict[str, str] = {}
    lineage_hashes: dict[str, str] = {}
    refs = artifact_registry.get("refs")
    if not isinstance(refs, list):
        return lineage_ids, lineage_hashes
    validation_status = _checkpoint_validation_status(payload)
    for raw_ref in _checkpoint_lineage_registration_order(refs):
        artifact_name = str(raw_ref["artifact_id"]).strip()
        storage_ref = _resolve_retained_artifact_path(
            runtime, str(raw_ref.get("path") or "").strip()
        )
        if not artifact_name or not storage_ref:
            continue
        storage_stat = file_stat(
            FileStatRequest(schema_version="1.0", path=storage_ref, compute_md5=False),
            runtime.ctx,
        )
        if not storage_stat.exists or not storage_stat.is_file:
            continue
        dependencies = (
            sorted(
                artifact_id
                for name, artifact_id in lineage_ids.items()
                if name not in {"source_pdf", "analysis_pdf", "preview_image"}
            )
            if artifact_name == "rendered_html"
            else [
                lineage_ids[dependency]
                for dependency in _checkpoint_dependency_names(artifact_name)
                if dependency in lineage_ids
            ]
        )
        prompt_hash, model_name, metadata, compatibility = _checkpoint_model_provenance(
            payload, artifact_name
        )
        compatibility = {
            **dict(runtime.execution_compatibility),
            **compatibility,
        }
        if artifact_name == "rendered_html":
            source_metadata_hash = str(
                getattr(runtime.source_identity, "source_metadata_hash", "") or ""
            ).strip()
            compatibility["source_metadata_hash"] = {
                "rendered_html": source_metadata_hash
                or hashlib.sha256(
                    json.dumps(
                        {
                            "publisher_name": runtime.publisher_name,
                            "source_report_name": runtime.source_report_name,
                            "source_url": runtime.source_url,
                            "source_publication_metadata": (
                                asdict(runtime.source_publication_metadata)
                                if runtime.source_publication_metadata is not None
                                else None
                            ),
                        },
                        ensure_ascii=True,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
            }
        response = record_artifact_lineage(
            ArtifactLineageRegistrationRequest(
                schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
                db_path=runtime.settings.reports_db,
                artifact_kind=artifact_name,
                report_id=runtime.file.file_id,
                source_id=str(runtime.md5 or "").strip().lower(),
                storage_ref=storage_ref,
                producer=stage_name,
                schema_version_used=str(raw_ref.get("schema_version") or "1.0"),
                processing_version="report_generation_checkpoint_v2",
                dependency_artifact_ids=dependencies,
                prompt_hash=prompt_hash,
                model_name=model_name,
                validation_status=(
                    validation_status
                    if artifact_name == "validation"
                    else "not_applicable"
                ),
                metadata=metadata,
                compatibility=compatibility,
                lineage_status=(
                    "complete"
                    if (
                        runtime.file.file_id.strip()
                        and str(runtime.md5 or "").strip()
                        and stage_name.strip()
                        and str(raw_ref.get("schema_version") or "1.0").strip()
                    )
                    else "legacy_incomplete"
                ),
            ),
            runtime.ctx,
        )
        lineage_ids[artifact_name] = response.record.artifact_id
        lineage_hashes[artifact_name] = response.record.content_hash
    return lineage_ids, lineage_hashes


def _checkpoint_lineage_registration_order(refs: list[object]) -> list[dict]:
    """Order persisted checkpoint artifacts so lineage dependencies exist first.

    Checkpoints are JSON resources and their object keys may be serialized in
    a different order than the workflow assembled them.  Dependency-based
    registration keeps the resulting immutable identities stable across that
    representation change.
    """
    refs_by_name: dict[str, dict] = {}
    for raw_ref in refs:
        if not isinstance(raw_ref, dict):
            continue
        artifact_name = str(raw_ref.get("artifact_id") or "").strip()
        if artifact_name:
            refs_by_name[artifact_name] = raw_ref

    ordered_names: list[str] = []
    visiting: set[str] = set()

    def visit(artifact_name: str) -> None:
        if artifact_name in ordered_names or artifact_name in visiting:
            return
        visiting.add(artifact_name)
        for dependency in _checkpoint_dependency_names(artifact_name):
            if dependency in refs_by_name:
                visit(dependency)
        visiting.remove(artifact_name)
        ordered_names.append(artifact_name)

    for artifact_name in refs_by_name:
        visit(artifact_name)
    return [refs_by_name[artifact_name] for artifact_name in ordered_names]


def _resolve_retained_artifact_path(
    runtime: ReportRuntimeState, storage_ref: str
) -> str:
    """Resolve generator-relative output refs before hashing them as lineage."""
    raw_path = Path(storage_ref).expanduser()
    candidates = (raw_path, Path(runtime.settings.output_dir) / raw_path)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return str(raw_path)


def _checkpoint_dependency_names(artifact_name: str) -> tuple[str, ...]:
    if artifact_name == "analysis_pdf":
        return ("source_pdf",)
    if artifact_name in {"contents_image", "preview_image"}:
        return ("analysis_pdf",)
    if artifact_name == "rendered_html":
        return ("artifacts", "validation")
    if artifact_name not in {"source_pdf", "analysis_pdf"}:
        return ("analysis_pdf",)
    return ()


def _checkpoint_validation_status(payload: dict) -> str:
    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        return "not_recorded"
    report = analysis.get("validation_report")
    if not isinstance(report, dict):
        return "not_recorded"
    return str(report.get("status") or "not_recorded")


def _checkpoint_model_provenance(
    payload: dict, artifact_name: str
) -> tuple[str, str, dict[str, object], dict[str, object]]:
    metadata: dict[str, object] = {"checkpoint_artifact_name": artifact_name}
    compatibility: dict[str, object] = {"artifact_family": artifact_name}
    if artifact_name != "artifacts":
        return "", "", metadata, compatibility
    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        return "", "", metadata, compatibility
    generated = analysis.get("artifacts_payload")
    if not isinstance(generated, dict):
        return "", "", metadata, compatibility
    cache = generated.get("_cache")
    prompts = cache.get("prompts") if isinstance(cache, dict) else None
    if not isinstance(prompts, dict) or not prompts:
        return "", "", metadata, compatibility
    prompt_content_hashes = {
        str(namespace): str(value.get("prompt_content_hash") or "").strip()
        for namespace, value in prompts.items()
        if isinstance(value, dict)
        and str(value.get("prompt_content_hash") or "").strip()
    }
    prompt_hash = hashlib.sha256(
        json.dumps(
            prompt_content_hashes or prompts,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    models = sorted(
        {
            str(value.get("model") or "").strip()
            for value in prompts.values()
            if isinstance(value, dict) and str(value.get("model") or "").strip()
        }
    )
    metadata["prompt_hashes"] = prompts
    metadata["prompt_content_hashes"] = prompt_content_hashes
    metadata["prompt_dependency_manifests"] = {
        str(namespace): dict(value.get("dependency_manifest") or {})
        for namespace, value in prompts.items()
        if isinstance(value, dict)
        and isinstance(value.get("dependency_manifest"), dict)
    }
    metadata["execution_identities"] = {
        str(namespace): str(value.get("execution_identity") or "")
        for namespace, value in prompts.items()
        if isinstance(value, dict)
    }
    compatibility["prompt_versions"] = {
        str(namespace): (
            str(value.get("prompt_content_hash") or "")
            or hashlib.sha256(
                json.dumps(
                    {
                        "system": str(value.get("prompt_system_sha256") or ""),
                        "user": str(value.get("prompt_user_sha256") or ""),
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        )
        for namespace, value in prompts.items()
        if isinstance(value, dict)
    }
    execution_identities = metadata["execution_identities"]
    compatibility["execution_identities"] = (
        dict(execution_identities) if isinstance(execution_identities, dict) else {}
    )
    return prompt_hash, ",".join(models), metadata, compatibility


def _record_prompt_family_materializations(
    runtime: ReportRuntimeState,
    *,
    stage_name: str,
    payload: dict,
    artifact_lineage: dict[str, str],
    artifact_hashes: dict[str, str],
) -> dict[str, str]:
    """Persist independently reusable family output at the analysis boundary.

    Composite checkpoints remain for backward-compatible resume.  They are
    deliberately not used as a substitute for family-level provenance.
    """
    if stage_name not in {STAGE_ANALYSIS_COMPLETE, STAGE_RENDER_COMPLETE}:
        return {}
    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        return {}
    artifacts = analysis.get("artifacts_payload")
    evidence_packs = analysis.get("evidence_packs")
    if not isinstance(artifacts, dict) or not isinstance(evidence_packs, dict):
        return {}
    cache = artifacts.get("_cache")
    cached_prompts = cache.get("prompts") if isinstance(cache, dict) else {}
    prompts = cached_prompts if isinstance(cached_prompts, dict) else {}
    cached_family_reuse = cache.get("family_reuse") if isinstance(cache, dict) else {}
    family_reuse = cached_family_reuse if isinstance(cached_family_reuse, dict) else {}
    cached_family_outputs = (
        cache.get("family_outputs") if isinstance(cache, dict) else {}
    )
    family_outputs = (
        cached_family_outputs if isinstance(cached_family_outputs, dict) else {}
    )
    execution_compatibility = dict(runtime.execution_compatibility or {})
    raw_prompt_versions = execution_compatibility.get("prompt_versions")
    raw_model_versions = execution_compatibility.get("model_policy_versions")
    raw_validator_versions = execution_compatibility.get("validator_versions")
    prompt_versions = (
        raw_prompt_versions if isinstance(raw_prompt_versions, dict) else {}
    )
    model_versions = raw_model_versions if isinstance(raw_model_versions, dict) else {}
    validator_versions = (
        raw_validator_versions if isinstance(raw_validator_versions, dict) else {}
    )
    evidence_set_hash = sha256_json(evidence_packs)
    source_identity = (
        str(
            runtime.md5
            or artifact_hashes.get("source_pdf")
            or artifact_hashes.get("analysis_pdf")
            or ""
        )
        .strip()
        .lower()
    )
    validation_report = analysis.get("validation_report")
    validation_status = (
        str(validation_report.get("status") or "fail")
        if isinstance(validation_report, dict)
        else "fail"
    )
    materialized: dict[str, str] = {}
    materialized_hashes: dict[str, str] = {}

    def dependencies(*names: str) -> tuple[list[str], dict[str, str]]:
        ids: list[str] = []
        hashes: dict[str, str] = {}
        for name in names:
            if name in artifact_lineage:
                artifact_id = artifact_lineage[name]
                digest = artifact_hashes.get(name, "")
            elif name in materialized:
                artifact_id = materialized[name]
                digest = materialized_hashes.get(name, "")
            else:
                continue
            if artifact_id not in ids:
                ids.append(artifact_id)
                hashes[artifact_id] = digest
        return ids, hashes

    def persist(
        family_id: str,
        output: object,
        dependency_names: tuple[str, ...],
        *,
        schema_version: str = "1.0",
        family_validation: str = validation_status,
    ) -> None:
        prompt = prompts.get(family_id)
        prompt_data = prompt if isinstance(prompt, dict) else {}
        cached_identity = family_reuse.get(family_id)
        identity = cached_identity if isinstance(cached_identity, dict) else {}
        recovery_attempted = bool(identity.get("recovery_attempted"))
        system_hash = str(prompt_data.get("prompt_system_sha256") or "")
        user_hash = str(prompt_data.get("prompt_user_sha256") or "")
        prompt_content_hash = str(prompt_data.get("prompt_content_hash") or "")
        prompt_dependency_manifest = dict(prompt_data.get("dependency_manifest") or {})
        execution_identity = str(prompt_data.get("execution_identity") or "")
        execution_identity_manifest = dict(
            prompt_data.get("execution_identity_manifest") or {}
        )
        if not system_hash and not user_hash:
            try:
                prompt_set = prompt_service.load_prompt_set(
                    PromptLoadRequest(schema_version="1.0", namespace=family_id),
                    runtime.ctx,
                )
            except AppError:
                # Some deterministic packs (for example report context) do
                # not own a prompt namespace. Their compatibility is governed
                # by direct dependencies and schema/processing versions.
                pass
            else:
                system_hash = prompt_set.system.sha256
                user_hash = prompt_set.user.sha256
                prompt_content_hash = prompt_set.prompt_content_hash
                prompt_dependency_manifest = (
                    asdict(prompt_set.dependency_manifest)
                    if prompt_set.dependency_manifest is not None
                    else {}
                )
        policy_version = str(
            prompt_versions.get(family_id)
            or prompt_content_hash
            or sha256_json({"system": system_hash, "user": user_hash})
        )
        prompt_content_hash = str(
            identity.get("prompt_content_hash") or prompt_content_hash
        )
        prompt_dependency_manifest = dict(
            identity.get("prompt_dependency_manifest")
            or prompt_dependency_manifest
            or {}
        )
        execution_identity = str(
            identity.get("execution_identity") or execution_identity
        )
        execution_identity_manifest = dict(
            identity.get("execution_identity_manifest")
            or execution_identity_manifest
            or {}
        )
        dependency_ids, dependency_hashes = dependencies(*dependency_names)
        result = materialize_prompt_family(
            PromptFamilyMaterializationRequest(
                schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
                db_path=runtime.settings.reports_db,
                output_dir=runtime.settings.output_dir,
                report_id=runtime.file.file_id,
                report_slug=runtime.report_name,
                source_id=source_identity,
                family_id=family_id,
                family_schema_version=schema_version,
                processing_version="report_generation_checkpoint_v2",
                output_payload=output,
                system_prompt_hash=system_hash,
                user_prompt_hash=user_hash,
                prompt_content_hash=prompt_content_hash,
                prompt_dependency_manifest=prompt_dependency_manifest,
                execution_identity=execution_identity,
                execution_identity_manifest=execution_identity_manifest,
                prompt_policy_version=policy_version,
                model_name=str(
                    identity.get("model_name") or prompt_data.get("model") or ""
                ),
                model_provider=str(identity.get("model_provider") or ""),
                model_policy_namespace=str(
                    identity.get("model_policy_namespace") or ""
                ),
                routing_policy_version=str(
                    identity.get("routing_policy_version")
                    or model_versions.get(family_id)
                    or model_versions.get("*")
                    or ""
                ),
                # A recovery prompt has different instructions and may use a
                # different model route.  Its output must not inherit the
                # primary family identity; leave the proof incomplete so a
                # later run fails closed and regenerates through the primary
                # path before it can become reusable.
                relevant_input_hash=(
                    ""
                    if recovery_attempted
                    else str(identity.get("relevant_input_hash") or "")
                ),
                configuration_policy_hash=str(
                    identity.get("configuration_policy_hash") or ""
                ),
                validator_version=str(
                    identity.get("validator_version")
                    or validator_versions.get(family_id)
                    or validator_versions.get("*")
                    or ""
                ),
                direct_dependency_artifact_ids=dependency_ids,
                direct_dependency_hashes=dependency_hashes,
                evidence_set_hash=evidence_set_hash,
                validation_status=family_validation,
            ),
            runtime.ctx,
        )
        materialized[family_id] = result.materialization.artifact_id
        materialized_hashes[family_id] = result.materialization.output_hash

    # Model-backed non-artifact families (document map, evidence packs,
    # taxonomy, and contextual category fit) retain their raw, schema-checked
    # responses immediately at their own generator boundary.  Rewriting them
    # here from a composite checkpoint would replace their exact input and
    # execution proof with checkpoint provenance, making a later pre-call
    # decision unsafe.  The checkpoint remains a resume artifact only.
    evidence_family_ids = tuple(
        f"report_vs/evidence_packs/{name}"
        for name in sorted(evidence_packs)
        if f"report_vs/evidence_packs/{name}" in materialized
    )
    persist(
        "report_vs/artifacts/summary",
        family_outputs.get("report_vs/artifacts/summary", artifacts.get("summary", {})),
        ("report_vs/doc_map", *evidence_family_ids),
    )
    persist(
        "report_vs/artifacts/insights_candidates",
        family_outputs.get(
            "report_vs/artifacts/insights_candidates",
            artifacts.get("insights_candidates", []),
        ),
        ("report_vs/doc_map", *evidence_family_ids),
    )
    persist(
        "report_vs/artifacts/quotes",
        family_outputs.get(
            "report_vs/artifacts/quotes", artifacts.get("quotes_final", [])
        ),
        ("report_vs/doc_map", *evidence_family_ids),
    )
    persist(
        "report_vs/artifacts/insights_final",
        family_outputs.get(
            "report_vs/artifacts/insights_final", artifacts.get("insights_final", [])
        ),
        ("report_vs/artifacts/insights_candidates", *evidence_family_ids),
    )
    persist(
        "report_vs/artifacts/cover_semantics",
        family_outputs.get(
            "report_vs/artifacts/cover_semantics", artifacts.get("cover_semantics", {})
        ),
        ("report_vs/artifacts/summary", "report_vs/artifacts/insights_final"),
    )
    persist(
        "report_vs/artifacts/expert_comment",
        family_outputs.get(
            "report_vs/artifacts/expert_comment",
            {"expert_comment": artifacts.get("expert_comment", "")},
        ),
        (
            "report_vs/artifacts/summary",
            "report_vs/artifacts/insights_final",
            "report_vs/artifacts/quotes",
            "report_vs/validate/grounding",
            "report_vs/validate/semantic",
        ),
    )
    persist(
        "report_vs/artifacts/linkedin_post",
        family_outputs.get(
            "report_vs/artifacts/linkedin_post",
            {"linkedin_post": artifacts.get("linkedin_post", "")},
        ),
        (
            "report_vs/artifacts/summary",
            "report_vs/artifacts/insights_final",
            "report_vs/validate/grounding",
            "report_vs/validate/semantic",
        ),
    )
    return materialized


def _record_rendered_html_prompt_family_lineage(
    runtime: ReportRuntimeState,
    *,
    artifact_registry: dict,
    payload: dict,
    artifact_lineage: dict[str, str],
    prompt_family_materializations: dict[str, str],
) -> None:
    """Make the rendered artifact explicitly consume accepted family outputs."""
    rendered_ref = next(
        (
            ref
            for ref in artifact_registry.get("refs", [])
            if isinstance(ref, dict)
            and str(ref.get("artifact_id") or "") == "rendered_html"
        ),
        None,
    )
    if not isinstance(rendered_ref, dict) or not prompt_family_materializations:
        return
    storage_ref = _resolve_retained_artifact_path(
        runtime, str(rendered_ref.get("path") or "").strip()
    )
    storage_stat = file_stat(
        FileStatRequest(schema_version="1.0", path=storage_ref, compute_md5=False),
        runtime.ctx,
    )
    if not storage_stat.exists or not storage_stat.is_file:
        return
    dependencies = sorted(
        {
            artifact_id
            for name, artifact_id in artifact_lineage.items()
            if name
            not in {"source_pdf", "analysis_pdf", "preview_image", "rendered_html"}
        }
        | set(prompt_family_materializations.values())
    )
    prompt_hash, model_name, metadata, compatibility = _checkpoint_model_provenance(
        payload, "rendered_html"
    )
    source_metadata_hash = str(
        getattr(runtime.source_identity, "source_metadata_hash", "") or ""
    ).strip()
    compatibility = {
        **dict(runtime.execution_compatibility),
        **compatibility,
        "source_metadata_hash": {
            "rendered_html": source_metadata_hash
            or hashlib.sha256(
                json.dumps(
                    {
                        "publisher_name": runtime.publisher_name,
                        "source_report_name": runtime.source_report_name,
                        "source_url": runtime.source_url,
                        "source_publication_metadata": (
                            asdict(runtime.source_publication_metadata)
                            if runtime.source_publication_metadata is not None
                            else None
                        ),
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        },
    }
    response = record_artifact_lineage(
        ArtifactLineageRegistrationRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=runtime.settings.reports_db,
            artifact_kind="rendered_html",
            report_id=runtime.file.file_id,
            source_id=str(runtime.md5 or "").strip().lower(),
            storage_ref=storage_ref,
            producer=STAGE_RENDER_COMPLETE,
            schema_version_used=str(rendered_ref.get("schema_version") or "1.0"),
            processing_version="report_generation_checkpoint_v2",
            dependency_artifact_ids=dependencies,
            prompt_hash=prompt_hash,
            model_name=model_name,
            validation_status="not_applicable",
            metadata=metadata,
            compatibility=compatibility,
            lineage_status=(
                "complete"
                if runtime.file.file_id.strip() and str(runtime.md5 or "").strip()
                else "legacy_incomplete"
            ),
        ),
        runtime.ctx,
    )
    artifact_lineage["rendered_html"] = response.record.artifact_id


def _artifact_required(artifact_id: str) -> bool:
    return artifact_id not in {
        "contents_image",
        "preview_image",
    }


def _artifact_registry_payload(
    runtime: ReportRuntimeState,
    *,
    stage_name: str,
    artifact_refs: dict[str, str],
) -> dict:
    created_at_utc = datetime.now(timezone.utc).isoformat()
    refs: list[ArtifactRef] = []
    for raw_artifact_id, raw_path in artifact_refs.items():
        artifact_id = str(raw_artifact_id or "").strip()
        path = str(raw_path or "").strip()
        if not artifact_id or not path:
            continue
        stat = file_stat(
            FileStatRequest(schema_version="1.0", path=path, compute_md5=True),
            runtime.ctx,
        )
        required = _artifact_required(artifact_id)
        if required and (not stat.exists or not stat.is_file):
            continue
        refs.append(
            ArtifactRef(
                schema_version="1.0",
                artifact_id=artifact_id,
                kind=artifact_id,
                path=stat.path,
                content_hash=stat.md5 or "",
                producer_step=stage_name,
                required=required,
                created_at_utc=created_at_utc,
            )
        )
    return artifact_registry_to_payload(
        ArtifactRegistry(schema_version="1.0", refs=refs)
    )


def _artifact_integrity_payload(
    runtime: ReportRuntimeState, artifact_refs: dict[str, str]
) -> dict:
    files: dict[str, dict] = {}
    for name, raw_path in artifact_refs.items():
        path = str(raw_path or "").strip()
        if not path:
            continue
        stat = file_stat(
            FileStatRequest(schema_version="1.0", path=path, compute_md5=True),
            runtime.ctx,
        )
        if not stat.exists or not stat.is_file or not stat.md5:
            continue
        files[str(name)] = {
            "schema_version": "1.0",
            "path": stat.path,
            "size_bytes": stat.size_bytes,
            "md5": stat.md5,
        }
    return {"schema_version": "1.0", "files": files}


def _source_checkpoint_payload(source: ReportSourceState) -> dict:
    return {
        "schema_version": "1.0",
        "info_response": _source_info_payload(source),
        "contents_page_number": source.contents_page_number,
        "contents_heading": source.contents_heading,
        "contents_image": source.contents_image,
        "text_response": _source_text_payload(source),
        "text_status": dict(source.text_status),
        "text_validation_status": source.text_validation_status,
        "text_validation_reason": source.text_validation_reason,
        "text_validation_pages": list(source.text_validation_pages),
        "payload": source.payload.to_dict(),
        "analysis_pdf_path": source.analysis_pdf_path,
        "ocr_fallback_used": source.ocr_fallback_used,
        "ocr_pdf_path": source.ocr_pdf_path,
    }


def _selection_checkpoint_payload(selection: ReportSelectionState) -> dict:
    return {
        "schema_version": "1.0",
        "payload": selection.payload.to_dict(),
        "rank_usage": dict(selection.rank_usage),
        "candidate_count": selection.candidate_count,
    }


def _vector_indexing_checkpoint_payload(
    vector_state: VectorStoreIndexingState,
) -> dict:
    return {
        "schema_version": "1.0",
        "vector_store_id": vector_state.vector_store_id,
        "openai_file_id": vector_state.openai_file_id,
        "vector_store_status": vector_state.vector_store_status,
        "indexed_at_utc": vector_state.indexed_at_utc,
        "last_error": vector_state.last_error,
    }


def _source_info_payload(source: ReportSourceState) -> dict:
    info = source.info_response
    return {
        "schema_version": str(getattr(info, "schema_version", "1.0")),
        "path": str(getattr(info, "path", source.runtime.local_pdf_path)),
        "page_count": int(getattr(info, "page_count", 0) or 0),
        "metadata": dict(getattr(info, "metadata", {}) or {}),
    }


def _source_text_payload(source: ReportSourceState) -> dict:
    text = source.text_response
    return {
        "schema_version": str(getattr(text, "schema_version", "1.0")),
        "text": str(getattr(text, "text", "") or ""),
        "pages_extracted": int(getattr(text, "pages_extracted", 0) or 0),
        "char_count": int(getattr(text, "char_count", 0) or 0),
        "text_density": float(getattr(text, "text_density", 0.0) or 0.0),
    }


def _preview_checkpoint_payload(preview_resp) -> dict:
    return {
        "schema_version": getattr(preview_resp, "schema_version", "1.1"),
        "image_path": str(getattr(preview_resp, "image_path", "") or ""),
        "page_number": int(getattr(preview_resp, "page_number", 0) or 0),
    }


def _analysis_checkpoint_payload(
    source: ReportSourceState,
    selection: ReportSelectionState,
    analysis: ReportAnalysisState,
    preview_resp,
) -> dict:
    validation_report = (
        analysis.validation_report.to_dict() if analysis.validation_report else None
    )
    return {
        "schema_version": "1.0",
        "source": _source_checkpoint_payload(source),
        "selection": _selection_checkpoint_payload(selection),
        "preview": _preview_checkpoint_payload(preview_resp),
        "analysis": {
            "schema_version": analysis.schema_version,
            "payload": analysis.payload.to_dict(),
            "normalized_payload": analysis.normalized_payload.to_dict(),
            "data_dict": dict(analysis.data_dict),
            "evidence_paths": dict(analysis.evidence_paths),
            "evidence_packs": dict(analysis.evidence_packs),
            "artifacts_payload": analysis.artifacts_payload,
            "validation_report": validation_report,
            "category_labels": list(analysis.category_labels),
            "vector_store_id": analysis.vector_store_id,
            "vector_store_status": analysis.vector_store_status,
            "indexed_at_utc": analysis.indexed_at_utc,
            "openai_file_id": analysis.openai_file_id,
            "last_error": analysis.last_error,
            "regeneration_loop_state": asdict(analysis.regeneration_loop_state)
            if analysis.regeneration_loop_state
            else None,
            "regeneration_attempts": [
                asdict(attempt) for attempt in analysis.regeneration_attempts
            ],
        },
    }


def _render_checkpoint_payload(
    source: ReportSourceState,
    selection: ReportSelectionState,
    analysis: ReportAnalysisState,
    preview_resp,
    outcome: IngestOutcome,
) -> dict:
    """Retain analysis provenance alongside a render outcome.

    Render checkpoints reference the same evidence and validation artifacts as
    analysis checkpoints.  Keeping their provenance prevents a downstream
    checkpoint write from replacing a valid lineage record with an incomplete
    observation of the same materialized file.
    """
    return {
        **_analysis_checkpoint_payload(source, selection, analysis, preview_resp),
        "outcome": asdict(outcome),
    }


def _analysis_checkpoint_refs(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    analysis: ReportAnalysisState,
    preview_resp,
) -> dict[str, str]:
    refs = {
        "source_pdf": runtime.local_pdf_path,
        "analysis_pdf": source.analysis_pdf_path or runtime.local_pdf_path,
        "preview_image": str(getattr(preview_resp, "image_path", "") or ""),
    }
    refs.update(
        {str(key): str(value) for key, value in analysis.evidence_paths.items()}
    )
    return {key: value for key, value in refs.items() if value}


def _render_checkpoint_refs(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    analysis: ReportAnalysisState,
    preview_resp,
    outcome: IngestOutcome,
) -> dict[str, str]:
    refs = {
        **_analysis_checkpoint_refs(runtime, source, analysis, preview_resp),
        "rendered_html": outcome.html_path or "",
    }
    for name, path in dict(outcome.evidence_packs or {}).items():
        if path:
            refs[str(name)] = str(path)
    return refs


def _source_state_from_checkpoint(
    runtime: ReportRuntimeState,
    raw_source: object,
) -> ReportSourceState:
    if not isinstance(raw_source, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint source state must be an object",
            retryable=False,
        )
    info_raw = raw_source.get("info_response")
    text_raw = raw_source.get("text_response")
    if not isinstance(info_raw, dict) or not isinstance(text_raw, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint source info/text state is incomplete",
            retryable=False,
        )
    return ReportSourceState(
        schema_version="1.0",
        runtime=runtime,
        info_response=PdfInfoResponse(
            schema_version=str(info_raw["schema_version"]),
            path=str(info_raw["path"]),
            page_count=int(info_raw["page_count"]),
            metadata={
                str(k): str(v) for k, v in dict(info_raw.get("metadata") or {}).items()
            },
        ),
        contents_page_number=int(raw_source["contents_page_number"]),
        contents_heading=str(raw_source["contents_heading"]),
        contents_image=str(raw_source["contents_image"]),
        text_response=PdfTextExtractResponse(
            schema_version=str(text_raw["schema_version"]),
            text=str(text_raw["text"]),
            pages_extracted=int(text_raw["pages_extracted"]),
            char_count=int(text_raw["char_count"]),
            text_density=float(text_raw.get("text_density") or 0.0),
        ),
        text_status=dict(raw_source["text_status"]),
        text_validation_status=str(raw_source["text_validation_status"]),
        text_validation_reason=str(raw_source["text_validation_reason"]),
        text_validation_pages=[
            int(item) for item in raw_source["text_validation_pages"]
        ],
        payload=_report_payload_from_dict(raw_source["payload"]),
        analysis_pdf_path=str(raw_source.get("analysis_pdf_path") or ""),
        ocr_fallback_used=bool(raw_source.get("ocr_fallback_used", False)),
        ocr_pdf_path=str(raw_source.get("ocr_pdf_path") or ""),
        pdf_context=None,
        pdf_context_for_tasks=None,
    )


def _selection_state_from_checkpoint(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    raw_selection: object,
) -> ReportSelectionState:
    if not isinstance(raw_selection, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint selection state must be an object",
            retryable=False,
        )
    return ReportSelectionState(
        schema_version="1.0",
        runtime=runtime,
        source=source,
        payload=_report_payload_from_dict(raw_selection["payload"]),
        rank_usage=dict(raw_selection["rank_usage"]),
        candidate_count=int(raw_selection["candidate_count"]),
    )


def _analysis_state_from_checkpoint(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    selection: ReportSelectionState,
    raw_analysis: object,
) -> ReportAnalysisState:
    if not isinstance(raw_analysis, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint analysis state must be an object",
            retryable=False,
        )
    return ReportAnalysisState(
        schema_version=str(raw_analysis["schema_version"]),
        runtime=runtime,
        source=source,
        selection=selection,
        payload=_report_payload_from_dict(raw_analysis["payload"]),
        normalized_payload=_report_payload_from_dict(
            raw_analysis["normalized_payload"]
        ),
        data_dict=dict(raw_analysis["data_dict"]),
        evidence_paths={
            str(k): str(v) for k, v in dict(raw_analysis["evidence_paths"]).items()
        },
        evidence_packs=dict(raw_analysis["evidence_packs"]),
        artifacts_payload=raw_analysis.get("artifacts_payload")
        if isinstance(raw_analysis.get("artifacts_payload"), dict)
        else None,
        validation_report=_validation_report_from_dict(
            raw_analysis.get("validation_report")
        ),
        category_labels=[str(item) for item in raw_analysis.get("category_labels", [])],
        vector_store_id=raw_analysis.get("vector_store_id"),
        vector_store_status=raw_analysis.get("vector_store_status"),
        indexed_at_utc=raw_analysis.get("indexed_at_utc"),
        openai_file_id=raw_analysis.get("openai_file_id"),
        last_error=raw_analysis.get("last_error"),
        regeneration_loop_state=_regeneration_loop_from_dict(
            raw_analysis.get("regeneration_loop_state")
        ),
        regeneration_attempts=_regeneration_attempts_from_list(
            raw_analysis.get("regeneration_attempts")
        ),
    )


def _vector_indexing_state_from_checkpoint(
    raw_state: object,
) -> VectorStoreIndexingState:
    # Legacy selection checkpoints predate vector-state persistence.  They
    # retain ``null`` rather than an object and are still safe to resume: no
    # vector resource is represented by the empty state.
    if raw_state is None:
        return VectorStoreIndexingState(
            vector_store_id=None,
            openai_file_id=None,
            vector_store_status=None,
            indexed_at_utc=None,
            last_error=None,
        )
    if not isinstance(raw_state, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint vector indexing state must be an object",
            retryable=False,
        )
    return VectorStoreIndexingState(
        vector_store_id=raw_state.get("vector_store_id"),
        openai_file_id=raw_state.get("openai_file_id"),
        vector_store_status=raw_state.get("vector_store_status"),
        indexed_at_utc=raw_state.get("indexed_at_utc"),
        last_error=raw_state.get("last_error"),
    )


def _preview_from_checkpoint(raw_preview: object) -> PreviewResponse:
    if not isinstance(raw_preview, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint preview state must be an object",
            retryable=False,
        )
    return PreviewResponse(
        schema_version=str(raw_preview.get("schema_version") or "1.1"),
        image_path=str(raw_preview["image_path"]),
        page_number=int(raw_preview["page_number"]),
    )


__all__ = [
    "_build_runtime_state",
    "_report_payload_from_dict",
    "_validation_report_from_dict",
    "_regeneration_loop_from_dict",
    "_regeneration_attempts_from_list",
    "_write_stage_checkpoint",
    "_checkpoint_lineage_registration_order",
    "_artifact_registry_payload",
    "_artifact_integrity_payload",
    "_source_checkpoint_payload",
    "_selection_checkpoint_payload",
    "_vector_indexing_checkpoint_payload",
    "_source_info_payload",
    "_source_text_payload",
    "_preview_checkpoint_payload",
    "_analysis_checkpoint_payload",
    "_render_checkpoint_payload",
    "_analysis_checkpoint_refs",
    "_render_checkpoint_refs",
    "_source_state_from_checkpoint",
    "_selection_state_from_checkpoint",
    "_analysis_state_from_checkpoint",
    "_vector_indexing_state_from_checkpoint",
    "_preview_from_checkpoint",
]
