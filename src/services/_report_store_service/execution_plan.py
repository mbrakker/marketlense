"""Durable observation, audit, and cross-report reads for execution planning."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from src.contracts.minimal_execution_plan import (
    MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
    ExecutionCompatibilityVersions,
    ExecutionPlanRecordRequest,
    ExecutionPlanResultRequest,
    MinimalExecutionPlanBuildRequest,
    MinimalExecutionPlanBuildResponse,
    MinimalExecutionPlanInput,
    RetainedArtifact,
    RetainedArtifactGraph,
    ValidatedReportArtifactReadRequest,
    ValidatedReportArtifactReadResponse,
)
from src.contracts.prompts import PromptLoadRequest
from src.contracts.public_editorial_quality import PUBLIC_EDITORIAL_VALIDATOR_VERSION
from src.contracts.run_context import RunContext
from src.services import prompt_service
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.minimal_execution_planner import plan_minimal_execution

from .artifact_lineage import _row_to_record, _sha256_file
from .common import logger
from .connection import _metadata_conn

_REPORT_TEMPLATE_NAMES = (
    "report.html.j2",
    "report.css.j2",
    "_report_macros.j2",
)
_CROSS_REPORT_FAMILY_ALIASES = {
    "claim": {"claim", "claims", "report_claims"},
    "evidence": {
        "evidence",
        "doc_map",
        "findings",
        "methods",
        "limitations",
        "quote_candidates",
        "scope",
    },
    "summary": {"summary", "artifacts"},
    "chart": {"chart", "crop_image", "preview_image"},
    "metadata": {"metadata", "report_context", "source_pdf"},
}


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _current_source_metadata_hash(conn, report_id: str) -> str:
    row = conn.execute(
        "SELECT publisher, title, source_url, md5 FROM reports WHERE file_id=?",
        (report_id,),
    ).fetchone()
    if row is None:
        return ""
    identity_row = conn.execute(
        """
        SELECT resolution.source_metadata_hash
        FROM source_identity_resolutions AS resolution
        JOIN report_sources AS source ON source.id = resolution.source_record_id
        WHERE COALESCE(source.md5, '') <> ''
          AND source.md5 = COALESCE(?, '')
        ORDER BY source.downloaded_at_utc DESC, source.updated_at DESC, source.id DESC
        LIMIT 1
        """,
        (str(row[3] or "").strip(),),
    ).fetchone()
    if identity_row and str(identity_row[0] or "").strip():
        return str(identity_row[0]).strip()
    publication_row = conn.execute(
        """
        SELECT
          metadata.source_record_id,
          metadata.publication_date,
          metadata.publication_date_precision,
          metadata.source_url,
          metadata.retrieved_at_utc,
          metadata.evidence_kind,
          metadata.evidence_locator,
          metadata.evidence_value_hash,
          metadata.evidence_status,
          metadata.contradiction_status,
          metadata.observed_values_json
        FROM source_publication_metadata AS metadata
        JOIN report_sources AS source ON source.id = metadata.source_record_id
        WHERE COALESCE(source.md5, '') <> ''
          AND source.md5 = COALESCE(?, '')
        ORDER BY metadata.updated_at_utc DESC, metadata.source_record_id DESC
        LIMIT 1
        """,
        (str(row[3] or "").strip(),),
    ).fetchone()
    values = {
        "publisher_name": str(row[0] or "").strip(),
        "source_report_name": str(row[1] or "").strip(),
        "source_url": str(row[2] or "").strip(),
        "source_publication_metadata": (
            {
                "source_record_id": int(publication_row[0] or 0),
                "publication_date": str(publication_row[1] or "").strip(),
                "publication_date_precision": str(publication_row[2] or "").strip(),
                "source_url": str(publication_row[3] or "").strip(),
                "retrieved_at_utc": str(publication_row[4] or "").strip(),
                "evidence_kind": str(publication_row[5] or "").strip(),
                "evidence_locator": str(publication_row[6] or "").strip(),
                "evidence_value_hash": str(publication_row[7] or "").strip(),
                "evidence_status": str(publication_row[8] or "").strip(),
                "contradiction_status": str(publication_row[9] or "").strip(),
                "observed_values_json": str(publication_row[10] or "[]"),
            }
            if publication_row is not None
            else None
        ),
    }
    return _sha256_text(values) if any(values.values()) else ""


def build_current_report_execution_compatibility(
    settings,
    ctx: RunContext,
) -> ExecutionCompatibilityVersions:
    """Observe prompt/template policy before any model client is constructed."""
    prompt_versions: dict[str, str] = {}
    for namespace in (
        "pdf_text/ocr_fallback",
        "rank_candidates",
        "rank_candidates/crop_refine",
        "report_vs/context_category_fit",
        "report_vs/doc_map",
        "report_vs/taxonomy",
        "report_vs/validate/grounding",
        "report_vs/validate/semantic",
        "report_vs/figure_caption",
        "report_vs/artifacts/summary",
        "report_vs/artifacts/linkedin_post",
        "report_vs/artifacts/quotes",
        "report_vs/artifacts/expert_comment",
        "report_vs/artifacts/insights_candidates",
        "report_vs/artifacts/insights_final",
        "report_vs/artifacts/cover_semantics",
    ):
        prompt_set = prompt_service.load_prompt_set(
            PromptLoadRequest(
                schema_version="1.0",
                namespace=namespace,
                reload_if_changed=True,
            ),
            ctx,
        )
        prompt_versions[namespace] = _sha256_text(
            {
                "system": prompt_set.system.sha256,
                "user": prompt_set.user.sha256,
            }
        )
    template_dir = Path(__file__).resolve().parents[3] / "templates"
    template_hashes: list[tuple[str, str]] = []
    for name in _REPORT_TEMPLATE_NAMES:
        _, digest = _sha256_file(str(template_dir / name))
        template_hashes.append((name, digest))
    model_policy = _sha256_text(
        {
            "default_model": str(getattr(settings, "openai_model", "") or ""),
            "models": dict(getattr(settings, "openai_models", {}) or {}),
            "temperature": getattr(settings, "temperature", None),
            "seed": getattr(settings, "openai_seed", None),
        }
    )
    parser_version = "pdf_parser:v1"
    ocr_policy_version = _sha256_text(
        {
            "enabled": bool(getattr(settings, "pdf_text_ocr_enabled", False)),
            "policy": str(getattr(settings, "pdf_text_ocr_policy", "") or ""),
            "model": str(getattr(settings, "pdf_text_ocr_model", "") or ""),
            "prompt_namespace": str(
                getattr(settings, "pdf_text_ocr_prompt_namespace", "") or ""
            ),
        }
    )
    crop_profile = _sha256_text(
        {
            "refine_enabled": bool(getattr(settings, "crop_refine_enabled", False)),
            "refine_mode": str(getattr(settings, "crop_refine_mode", "") or ""),
            "refine_dpi": getattr(settings, "crop_refine_page_dpi", None),
            "final_dpi": getattr(settings, "final_crop_dpi", None),
            "qa_enabled": bool(getattr(settings, "crop_qa_escalation_enabled", False)),
        }
    )
    return ExecutionCompatibilityVersions(
        schema_versions={"*": "1.0"},
        processing_versions={"*": "report_generation_checkpoint_v2"},
        prompt_versions=prompt_versions,
        model_policy_versions={"*": model_policy},
        validator_versions={
            "validation": ("validation:v1|" + PUBLIC_EDITORIAL_VALIDATOR_VERSION),
            "public_editorial_quality": PUBLIC_EDITORIAL_VALIDATOR_VERSION,
        },
        crop_profiles={"*": crop_profile},
        template_render_versions={
            "rendered_html": _sha256_text(template_hashes),
        },
        parser_version=parser_version,
        ocr_policy_version=ocr_policy_version,
    )


def _observed_graph(conn, report_id: str) -> RetainedArtifactGraph:
    rows = conn.execute(
        """SELECT r.*, s.state, s.invalidation_reason, s.superseded_by
        FROM artifact_lineage_records r JOIN artifact_lineage_states s
        ON s.artifact_id=r.artifact_id WHERE r.report_id=? ORDER BY r.artifact_id""",
        (report_id,),
    ).fetchall()
    edge_rows = conn.execute(
        """SELECT d.artifact_id, d.dependency_artifact_id
        FROM artifact_lineage_dependencies d JOIN artifact_lineage_records r
        ON r.artifact_id=d.artifact_id WHERE r.report_id=?
        ORDER BY d.artifact_id, d.dependency_artifact_id""",
        (report_id,),
    ).fetchall()
    dependencies: dict[str, list[str]] = {}
    for child, dependency in edge_rows:
        dependencies.setdefault(str(child), []).append(str(dependency))
    artifacts: list[RetainedArtifact] = []
    for row in rows:
        record = _row_to_record(row)
        try:
            _, observed_hash = _sha256_file(record.storage_ref)
            available = True
        except Exception:
            observed_hash = ""
            available = False
        artifacts.append(
            RetainedArtifact(
                artifact_id=record.artifact_id,
                artifact_kind=record.artifact_kind,
                report_id=record.report_id,
                source_id=record.source_id,
                content_hash=record.content_hash,
                storage_ref=record.storage_ref,
                state=record.state,
                schema_version_used=record.schema_version_used,
                processing_version=record.processing_version,
                validation_status=record.validation_status,
                dependency_artifact_ids=dependencies.get(record.artifact_id, []),
                compatibility=record.compatibility,
                lineage_status=record.lineage_status,
                storage_available=available,
                observed_content_hash=observed_hash,
            )
        )
    claim_rows = conn.execute(
        """SELECT claim_uid,claim,evidence_id,evidence,pages_json,schema_version,
        projection_version,source_pack,source_ref,model,generated_at_utc,analysis_run_id
        FROM report_claims WHERE report_id=? ORDER BY claim_uid""",
        (report_id,),
    ).fetchall()
    claim_dependencies = sorted(
        artifact.artifact_id
        for artifact in artifacts
        if artifact.artifact_kind in {"artifacts", "validation"}
        and artifact.lineage_status == "complete"
        and artifact.storage_available
        and artifact.observed_content_hash == artifact.content_hash
    )
    if claim_rows and claim_dependencies:
        claims_payload = [list(row) for row in claim_rows]
        claim_hash = _sha256_text(claims_payload)
        schema_versions = {str(row[5] or "").strip() for row in claim_rows}
        projection_versions = {str(row[6] or "").strip() for row in claim_rows}
        if len(schema_versions) == 1 and "" not in schema_versions:
            claims_schema_version = next(iter(schema_versions))
            claims_compatibility: dict[str, object] = {
                "artifact_family": "claims",
                "schema_versions": {"*": claims_schema_version},
                "processing_versions": {"*": "report_generation_checkpoint_v2"},
                "claim_projection_version": next(iter(projection_versions)),
            }
            source_id = next(
                (
                    artifact.source_id
                    for artifact in artifacts
                    if artifact.artifact_kind == "source_pdf"
                ),
                "",
            )
            claims_identity = hashlib.sha256(
                (report_id + claim_hash).encode("utf-8")
            ).hexdigest()
            artifact_id = f"claims:{claims_identity}"
            artifacts.append(
                RetainedArtifact(
                    artifact_id=artifact_id,
                    artifact_kind="claims",
                    report_id=report_id,
                    source_id=source_id,
                    content_hash=claim_hash,
                    storage_ref=f"sqlite:report_claims:{report_id}",
                    state="active",
                    schema_version_used=claims_schema_version,
                    processing_version=(
                        "report_projection:"
                        + next(iter(projection_versions), "unknown")
                    ),
                    validation_status="pass",
                    dependency_artifact_ids=claim_dependencies,
                    compatibility=claims_compatibility,
                    lineage_status="complete",
                    storage_available=True,
                    observed_content_hash=claim_hash,
                )
            )
            edge_rows.extend(
                (artifact_id, dependency) for dependency in claim_dependencies
            )
    return RetainedArtifactGraph(
        artifacts=artifacts,
        edges=[(str(row[0]), str(row[1])) for row in edge_rows],
    )


def _log_plan(plan, graph: RetainedArtifactGraph, ctx: RunContext) -> None:
    artifact_by_id = {artifact.artifact_id: artifact for artifact in graph.artifacts}
    logger.info(
        log_event(
            ctx,
            role="service",
            event="minimal_execution_plan_created",
            module=logger.name,
            fields={
                "plan_hash": plan.plan_hash,
                "report_id": plan.report_id,
                "intent": plan.execution_intent,
                "required_stages": plan.required_stages,
                "blocker_count": len(plan.missing_lineage_blockers),
            },
        )
    )
    for artifact in graph.artifacts:
        if (
            artifact.storage_available
            and artifact.observed_content_hash != artifact.content_hash
        ):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="artifact_hash_mismatch",
                    module=logger.name,
                    fields={
                        "artifact_id": artifact.artifact_id,
                        "artifact_kind": artifact.artifact_kind,
                        "artifact_hash": artifact.content_hash,
                        "observed_hash": artifact.observed_content_hash,
                    },
                )
            )
    for artifact_id in plan.reusable_artifacts:
        artifact = artifact_by_id[artifact_id]
        logger.info(
            log_event(
                ctx,
                role="service",
                event="artifact_reused",
                module=logger.name,
                fields={
                    "artifact_id": artifact_id,
                    "artifact_hash": artifact.content_hash,
                    "dependency_proof": artifact.dependency_artifact_ids,
                    "compatibility_versions": artifact.compatibility,
                    "consumer_stage": plan.required_stages[0]
                    if plan.required_stages
                    else "cross_report_read",
                },
            )
        )
    for invalid in plan.invalid_artifacts:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="artifact_invalidated",
                module=logger.name,
                fields={
                    "artifact_id": invalid.artifact_id,
                    "artifact_kind": invalid.artifact_kind,
                    "reason": invalid.reason,
                },
            )
        )
        if invalid.reason == "artifact_hash_mismatch":
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="artifact_hash_mismatch",
                    module=logger.name,
                    fields={"artifact_id": invalid.artifact_id},
                )
            )
        elif "changed" in invalid.reason:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="artifact_compatibility_mismatch",
                    module=logger.name,
                    fields={
                        "artifact_id": invalid.artifact_id,
                        "reason": invalid.reason,
                    },
                )
            )
    for blocker in plan.missing_lineage_blockers:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="artifact_missing_lineage",
                module=logger.name,
                fields={
                    "artifact_id": blocker.artifact_id,
                    "artifact_kind": blocker.artifact_kind,
                    "reason": blocker.reason,
                },
            )
        )
    for stage in plan.skipped_stages:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="minimal_execution_stage_skipped",
                module=logger.name,
                fields={"plan_hash": plan.plan_hash, "stage": stage},
            )
        )
    avoided = sorted(
        set(
            {
                "pdf_parse",
                "ocr",
                "crop_render",
                "crop_qa",
                "vector_store",
                "report_analysis_model",
                "validator_model",
                "html_render",
                "wordpress_write",
            }
        )
        - set(plan.required_external_calls)
    )
    for call in avoided:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="minimal_execution_external_call_avoided",
                module=logger.name,
                fields={"plan_hash": plan.plan_hash, "call_category": call},
            )
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="minimal_execution_estimated_cost_avoided",
            module=logger.name,
            fields={
                "plan_hash": plan.plan_hash,
                "avoided_call_categories": avoided,
                "estimated_cost_usd": None,
            },
        )
    )


def build_minimal_execution_plan(
    request: MinimalExecutionPlanBuildRequest, ctx: RunContext
) -> MinimalExecutionPlanBuildResponse:
    with _metadata_conn(request.db_path, ctx) as conn:
        graph = _observed_graph(conn, request.execution_input.report_id)
        observed_source_metadata_hash = _current_source_metadata_hash(
            conn, request.execution_input.report_id
        )
    source_hashes = dict(request.execution_input.current_source_content_hashes)
    if request.source_path:
        try:
            _, source_hash = _sha256_file(request.source_path)
            source_hashes[request.execution_input.source_id or "*"] = source_hash
        except Exception:
            source_hashes[request.execution_input.source_id or "*"] = "__missing__"
    execution_input = replace(
        request.execution_input,
        retained_graph=graph,
        current_source_content_hashes=source_hashes,
        source_metadata_hash=(
            request.execution_input.source_metadata_hash
            or observed_source_metadata_hash
        ),
    )
    plan = plan_minimal_execution(execution_input)
    _log_plan(plan, graph, ctx)
    return MinimalExecutionPlanBuildResponse(
        schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
        plan=plan,
    )


def record_minimal_execution_plan(
    request: ExecutionPlanRecordRequest, ctx: RunContext
) -> None:
    plan = request.plan
    with _metadata_conn(request.db_path, ctx) as conn:
        conn.execute(
            """INSERT INTO artifact_execution_plan_runs(
            plan_hash,report_id,execution_intent,execution_mode,planned_stages_json,
            planned_external_calls_json,planned_side_effects_json,
            reusable_artifact_ids_json,created_at_utc)
            VALUES(?,?,?,?,?,?,?, ?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            ON CONFLICT(plan_hash) DO NOTHING""",
            (
                plan.plan_hash,
                plan.report_id,
                plan.execution_intent,
                request.execution_mode,
                _canonical_json(plan.required_stages),
                _canonical_json(plan.required_external_calls),
                _canonical_json(plan.expected_side_effects),
                _canonical_json(plan.reusable_artifacts),
            ),
        )


def record_minimal_execution_plan_result(
    request: ExecutionPlanResultRequest, ctx: RunContext
) -> bool:
    with _metadata_conn(request.db_path, ctx) as conn:
        row = conn.execute(
            """SELECT planned_stages_json, planned_external_calls_json,
            planned_side_effects_json
            FROM artifact_execution_plan_runs WHERE plan_hash=?""",
            (request.plan_hash,),
        ).fetchone()
        planned_stages = json.loads(str(row[0])) if row else []
        planned_calls = json.loads(str(row[1])) if row else []
        planned_side_effects = json.loads(str(row[2])) if row else []
        divergence = {
            "unplanned_stages": sorted(
                set(request.actual_stages) - set(planned_stages)
            ),
            "skipped_planned_stages": sorted(
                set(planned_stages) - set(request.actual_stages)
            ),
            "unplanned_external_calls": sorted(
                set(request.actual_external_calls) - set(planned_calls)
            ),
            "avoided_planned_external_calls": sorted(
                set(planned_calls) - set(request.actual_external_calls)
            ),
            "unplanned_side_effects": sorted(
                set(request.actual_side_effects) - set(planned_side_effects)
            ),
            "avoided_planned_side_effects": sorted(
                set(planned_side_effects) - set(request.actual_side_effects)
            ),
            "duration_ms": max(0, int(request.duration_ms)),
            "actual_cost_usd": request.actual_cost_usd,
            "estimated_avoided_cost_usd": request.estimated_avoided_cost_usd,
            "reusable_artifact_ids": sorted(set(request.reusable_artifact_ids)),
        }
        diverged = any(
            divergence[key]
            for key in (
                "unplanned_stages",
                "unplanned_external_calls",
                "unplanned_side_effects",
            )
        )
        divergence["reconciliation_status"] = "diverged" if diverged else "matched"
        conn.execute(
            """UPDATE artifact_execution_plan_runs SET actual_stages_json=?,
            actual_external_calls_json=?,actual_side_effects_json=?,duration_ms=?,
            actual_cost_usd=?,estimated_avoided_cost_usd=?,execution_status=?,divergence_json=?,
            completed_at_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE plan_hash=?""",
            (
                _canonical_json(sorted(set(request.actual_stages))),
                _canonical_json(sorted(set(request.actual_external_calls))),
                _canonical_json(sorted(set(request.actual_side_effects))),
                max(0, int(request.duration_ms)),
                request.actual_cost_usd,
                request.estimated_avoided_cost_usd,
                "diverged" if diverged else request.execution_status,
                _canonical_json(divergence),
                request.plan_hash,
            ),
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="minimal_execution_actual_plan_divergence",
            module=logger.name,
            fields={
                "plan_hash": request.plan_hash,
                "report_id": request.report_id,
                "execution_status": request.execution_status,
                "divergence": divergence,
            },
        )
    )
    return diverged


def read_validated_report_artifacts(
    request: ValidatedReportArtifactReadRequest, ctx: RunContext
) -> ValidatedReportArtifactReadResponse:
    requested = {str(value).strip().lower() for value in request.artifact_families}
    with _metadata_conn(request.db_path, ctx) as conn:
        observed_graph = _observed_graph(conn, request.report_id)
    available = {artifact.artifact_kind for artifact in observed_graph.artifacts}
    expanded: list[str] = []
    for family in sorted(requested):
        aliases = _CROSS_REPORT_FAMILY_ALIASES.get(family, {family})
        matched = sorted(aliases & available)
        expanded.extend(matched or [family])
    expanded = sorted(set(expanded))
    response = build_minimal_execution_plan(
        MinimalExecutionPlanBuildRequest(
            schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
            db_path=request.db_path,
            execution_input=MinimalExecutionPlanInput(
                schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
                execution_intent="cross_report_read",
                report_id=request.report_id,
                source_id="",
                current_source_content_hashes=request.current_source_content_hashes,
                retained_graph=RetainedArtifactGraph(),
                requested_output_families=expanded,
                current_compatibility=request.current_compatibility,
            ),
        ),
        ctx,
    )
    record_minimal_execution_plan(
        ExecutionPlanRecordRequest(
            schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
            db_path=request.db_path,
            plan=response.plan,
            execution_mode="enforce",
        ),
        ctx,
    )
    if response.plan.invalid_artifacts or response.plan.missing_lineage_blockers:
        record_minimal_execution_plan_result(
            ExecutionPlanResultRequest(
                schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
                db_path=request.db_path,
                plan_hash=response.plan.plan_hash,
                report_id=request.report_id,
                execution_intent=response.plan.execution_intent,
                actual_stages=[],
                actual_external_calls=[],
                actual_side_effects=[],
                reusable_artifact_ids=[],
                execution_status="blocked",
            ),
            ctx,
        )
        return ValidatedReportArtifactReadResponse(
            schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
            artifacts=[],
            plan=response.plan,
        )
    reusable_ids = set(response.plan.reusable_artifacts)
    selected: dict[tuple[str, str], RetainedArtifact] = {}
    for artifact in observed_graph.artifacts:
        if (
            artifact.artifact_id not in reusable_ids
            or artifact.artifact_kind not in set(expanded)
        ):
            continue
        selected.setdefault((artifact.artifact_kind, artifact.storage_ref), artifact)
    artifacts = [
        selected[key] for key in sorted(selected, key=lambda item: (item[0], item[1]))
    ]
    divergence = record_minimal_execution_plan_result(
        ExecutionPlanResultRequest(
            schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
            db_path=request.db_path,
            plan_hash=response.plan.plan_hash,
            report_id=request.report_id,
            execution_intent=response.plan.execution_intent,
            actual_stages=[],
            actual_external_calls=[],
            actual_side_effects=[],
            reusable_artifact_ids=[item.artifact_id for item in artifacts],
            execution_status="completed",
        ),
        ctx,
    )
    if divergence:
        raise AppError(
            code="minimal_execution_plan_diverged",
            message="Cross-report retained-artifact read diverged from its plan",
            retryable=False,
            context={"plan_hash": response.plan.plan_hash},
        )
    return ValidatedReportArtifactReadResponse(
        schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
        artifacts=artifacts,
        plan=response.plan,
    )


__all__ = [
    "build_current_report_execution_compatibility",
    "build_minimal_execution_plan",
    "read_validated_report_artifacts",
    "record_minimal_execution_plan",
    "record_minimal_execution_plan_result",
]
