"""Pure compatibility and minimum-regeneration policy for retained artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace

from src.contracts.minimal_execution_plan import (
    MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
    ArtifactInvalidation,
    EstimatedWorkCategory,
    ExecutionCompatibilityVersions,
    MinimalExecutionPlan,
    MinimalExecutionPlanInput,
    MissingLineageBlocker,
    RetainedArtifact,
    RetainedArtifactGraph,
)
from src.utils.errors import AppError

EXECUTION_INTENTS = {
    "report_generation",
    "targeted_repair",
    "render_repair",
    "crop_repair",
    "publication_repair",
    "cross_report_read",
}

INVALIDATION_SOURCE_CONTENT_CHANGED = "source_content_changed"
INVALIDATION_SOURCE_METADATA_CHANGED = "source_metadata_changed"
INVALIDATION_PARSER_VERSION_CHANGED = "parser_version_changed"
INVALIDATION_OCR_POLICY_VERSION_CHANGED = "ocr_policy_version_changed"
INVALIDATION_PROMPT_CHANGED = "prompt_changed"
INVALIDATION_OUTPUT_SCHEMA_CHANGED = "output_schema_changed"
INVALIDATION_MODEL_POLICY_CHANGED = "model_policy_changed"
INVALIDATION_VALIDATOR_CHANGED = "validator_changed"
INVALIDATION_CROP_PROFILE_CHANGED = "crop_profile_changed"
INVALIDATION_TEMPLATE_CHANGED = "template_changed"
INVALIDATION_PUBLICATION_TARGET_CHANGED = "publication_target_changed"
INVALIDATION_RETAINED_ARTIFACT_MISSING = "retained_artifact_missing"
INVALIDATION_ARTIFACT_HASH_MISMATCH = "artifact_hash_mismatch"
INVALIDATION_DEPENDENCY_EDGE_MISSING = "dependency_edge_missing"

_STAGE_ORDER = [
    "source_prepared",
    "selection_complete",
    "analysis_complete",
    "render_complete",
    "publication_complete",
]
_EXTERNAL_BY_STAGE = {
    "source_prepared": ["pdf_parse", "ocr"],
    "selection_complete": ["crop_render", "crop_qa"],
    "analysis_complete": ["vector_store", "report_analysis_model", "validator_model"],
    "render_complete": ["html_render"],
    "publication_complete": ["wordpress_write"],
}
_SIDE_EFFECTS_BY_STAGE = {
    "source_prepared": ["checkpoint_write"],
    "selection_complete": ["crop_write", "checkpoint_write"],
    "analysis_complete": ["analysis_artifact_write", "checkpoint_write"],
    "render_complete": ["rendered_html_write", "checkpoint_write"],
    "publication_complete": ["wordpress_update", "publish_state_write"],
}
_FAMILY_STAGE = {
    "source_pdf": "source_prepared",
    "analysis_pdf": "source_prepared",
    "contents_image": "source_prepared",
    "preview_image": "selection_complete",
    "crop_image": "selection_complete",
    "crop": "selection_complete",
    "rendered_html": "render_complete",
    "publication": "publication_complete",
}


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _family_for(artifact: RetainedArtifact) -> str:
    raw = artifact.compatibility.get("artifact_family")
    return str(raw or artifact.artifact_kind).strip()


def _is_prompt_family_materialization(artifact: RetainedArtifact) -> bool:
    return artifact.artifact_kind.startswith("prompt_family:")


def _compatibility_value(
    compatibility: dict[str, object], key: str, family: str
) -> str:
    raw = compatibility.get(key)
    if isinstance(raw, dict):
        return str(raw.get(family) or raw.get("*") or "").strip()
    return str(raw or "").strip()


def _current_value(values: dict[str, str], family: str) -> str:
    return str(values.get(family) or values.get("*") or "").strip()


def _requires_complete_lineage(artifact: RetainedArtifact) -> bool:
    return artifact.artifact_kind not in {"source_pdf", "publication"}


def _artifact_reason(
    artifact: RetainedArtifact,
    current: ExecutionCompatibilityVersions,
    source_hashes: dict[str, str],
    source_metadata_hash: str,
    publication_state: dict[str, str],
) -> tuple[str, str] | None:
    """Return a stable invalidation class and an optional family detail."""
    family = _family_for(artifact)
    if artifact.state != "active":
        return "artifact_not_active", ""
    if not artifact.storage_available:
        return INVALIDATION_RETAINED_ARTIFACT_MISSING, ""
    if artifact.observed_content_hash != artifact.content_hash:
        return INVALIDATION_ARTIFACT_HASH_MISMATCH, ""
    if artifact.artifact_kind == "source_pdf":
        expected = str(
            source_hashes.get(artifact.source_id) or source_hashes.get("*") or ""
        )
        if expected and expected != artifact.content_hash:
            return INVALIDATION_SOURCE_CONTENT_CHANGED, ""
    if artifact.artifact_kind == "rendered_html" and source_metadata_hash:
        stored_metadata = _compatibility_value(
            artifact.compatibility, "source_metadata_hash", family
        )
        if not stored_metadata:
            return "missing_lineage", "source_metadata_hash"
        if stored_metadata != source_metadata_hash:
            return INVALIDATION_SOURCE_METADATA_CHANGED, ""
    if artifact.lineage_status != "complete" and _requires_complete_lineage(artifact):
        return "missing_lineage", "compatibility_incomplete"

    checks = (
        (
            "schema_versions",
            current.schema_versions,
            INVALIDATION_OUTPUT_SCHEMA_CHANGED,
        ),
        (
            "processing_versions",
            current.processing_versions,
            INVALIDATION_PARSER_VERSION_CHANGED,
        ),
        ("prompt_versions", current.prompt_versions, INVALIDATION_PROMPT_CHANGED),
        (
            "model_policy_versions",
            current.model_policy_versions,
            INVALIDATION_MODEL_POLICY_CHANGED,
        ),
        (
            "validator_versions",
            current.validator_versions,
            INVALIDATION_VALIDATOR_CHANGED,
        ),
        ("crop_profiles", current.crop_profiles, INVALIDATION_CROP_PROFILE_CHANGED),
        (
            "template_render_versions",
            current.template_render_versions,
            INVALIDATION_TEMPLATE_CHANGED,
        ),
    )
    analysis_kinds = {
        "artifacts",
        "doc_map",
        "findings",
        "methods",
        "limitations",
        "scope",
        "quote_candidates",
        "report_context",
        "context_category_fit",
        "analysis_vector_store",
    }
    for key, values, reason in checks:
        if (
            key in {"prompt_versions", "model_policy_versions"}
            and artifact.artifact_kind not in analysis_kinds
            and not _is_prompt_family_materialization(artifact)
        ):
            continue
        if (
            key == "validator_versions"
            and artifact.artifact_kind != "validation"
            and not _is_prompt_family_materialization(artifact)
        ):
            continue
        if key == "crop_profiles" and artifact.artifact_kind not in {
            "crop",
            "crop_image",
            "preview_image",
        }:
            continue
        if (
            key == "template_render_versions"
            and artifact.artifact_kind != "rendered_html"
        ):
            continue
        if key == "prompt_versions" and artifact.artifact_kind == "artifacts":
            observed_versions = artifact.compatibility.get(key)
            if not isinstance(observed_versions, dict):
                return "missing_lineage", key
            changed = sorted(
                namespace
                for namespace, observed_value in observed_versions.items()
                if namespace in values and str(observed_value) != str(values[namespace])
            )
            if changed:
                return reason, changed[0].rsplit("/", 1)[-1]
            continue
        expected = _current_value(values, family)
        if not expected:
            continue
        observed = _compatibility_value(artifact.compatibility, key, family)
        if not observed:
            return "missing_lineage", key
        if observed != expected:
            return reason, family
    if current.parser_version:
        observed = _compatibility_value(
            artifact.compatibility, "parser_version", family
        )
        if artifact.artifact_kind in {"source_pdf", "analysis_pdf"}:
            if not observed:
                return "missing_lineage", "parser_version"
            if observed != current.parser_version:
                return INVALIDATION_PARSER_VERSION_CHANGED, ""
    if current.ocr_policy_version:
        observed = _compatibility_value(
            artifact.compatibility, "ocr_policy_version", family
        )
        if artifact.artifact_kind in {"source_pdf", "analysis_pdf"}:
            if not observed:
                return "missing_lineage", "ocr_policy_version"
            if observed != current.ocr_policy_version:
                return INVALIDATION_OCR_POLICY_VERSION_CHANGED, ""
    if (
        _is_prompt_family_materialization(artifact)
        and artifact.validation_status.strip().lower() != "pass"
    ):
        return "family_validation_not_accepted", ""
    target = str(publication_state.get("target") or "").strip()
    if target and artifact.artifact_kind == "publication":
        observed = _compatibility_value(
            artifact.compatibility, "publication_target", family
        )
        if not observed:
            return "missing_lineage", "publication_target"
        if observed != target:
            return INVALIDATION_PUBLICATION_TARGET_CHANGED, ""
    return None


def _family_stage(artifact_kind: str) -> str:
    if artifact_kind in _FAMILY_STAGE:
        return _FAMILY_STAGE[artifact_kind]
    if artifact_kind in {
        "artifacts",
        "validation",
        "doc_map",
        "findings",
        "methods",
        "limitations",
        "scope",
        "quote_candidates",
        "report_context",
        "context_category_fit",
        "analysis_vector_store",
    }:
        return "analysis_complete"
    return "analysis_complete"


def _stage_index(stage: str) -> int:
    try:
        return _STAGE_ORDER.index(stage)
    except ValueError:
        return len(_STAGE_ORDER) - 1


def _required_stages(
    *,
    intent: str,
    invalid: list[ArtifactInvalidation],
    blockers: list[MissingLineageBlocker],
) -> list[str]:
    if intent == "cross_report_read":
        return []
    if blockers:
        # An unprovable graph can only resume after a fresh source pass.
        earliest = "source_prepared"
    elif not invalid:
        earliest = (
            "publication_complete"
            if intent == "publication_repair"
            else "render_complete"
        )
    else:
        reasons = {
            item.reason.split(":", 1)[0]
            for item in invalid
            if item.reason != "dependency_invalidated"
        }
        if reasons & {
            INVALIDATION_SOURCE_CONTENT_CHANGED,
            INVALIDATION_PARSER_VERSION_CHANGED,
            INVALIDATION_OCR_POLICY_VERSION_CHANGED,
            INVALIDATION_RETAINED_ARTIFACT_MISSING,
            INVALIDATION_ARTIFACT_HASH_MISMATCH,
            INVALIDATION_DEPENDENCY_EDGE_MISSING,
        }:
            earliest = min(
                (_family_stage(item.artifact_kind) for item in invalid),
                key=_stage_index,
            )
        elif reasons <= {INVALIDATION_CROP_PROFILE_CHANGED} or intent == "crop_repair":
            # Crop repair is visual-only; analysis artifacts stay reusable.
            return ["selection_complete", "render_complete"]
        elif (
            reasons
            <= {INVALIDATION_TEMPLATE_CHANGED, INVALIDATION_SOURCE_METADATA_CHANGED}
            or intent == "render_repair"
        ):
            return ["render_complete"]
        elif (
            reasons <= {INVALIDATION_PUBLICATION_TARGET_CHANGED}
            or intent == "publication_repair"
        ):
            return ["publication_complete"]
        else:
            # Prompt/model/schema/validator repair uses targeted artifacts.
            return ["analysis_complete", "render_complete"]
    stages = _STAGE_ORDER[_stage_index(earliest) :]
    if intent != "publication_repair":
        stages.remove("publication_complete")
    return stages


def _plan_hash(plan: MinimalExecutionPlan) -> str:
    payload = asdict(plan)
    payload["plan_hash"] = ""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _current_replacement_key(artifact: RetainedArtifact) -> tuple[str, ...]:
    return (
        artifact.report_id,
        artifact.artifact_kind,
        artifact.storage_ref,
    )


def _canonical_graph(
    graph: RetainedArtifactGraph,
) -> tuple[list[RetainedArtifact], list[tuple[str, str]]]:
    """Ignore stale rows only when a complete current proof replaces them.

    A historic row remains fail-closed on its own.  A fresh complete record for
    the same report, source, family, and retained file proves the current
    content and graph, so keeping the old row would make a safe fresh run look
    permanently invalid merely because it retains an older immutable audit
    entry.
    """
    replacements = {
        _current_replacement_key(artifact)
        for artifact in graph.artifacts
        if artifact.state == "active"
        and artifact.lineage_status == "complete"
        and artifact.storage_available
        and artifact.observed_content_hash == artifact.content_hash
    }
    artifacts = sorted(
        [
            artifact
            for artifact in graph.artifacts
            if _current_replacement_key(artifact) not in replacements
            or (
                artifact.lineage_status == "complete"
                and artifact.state == "active"
                and artifact.storage_available
                and artifact.observed_content_hash == artifact.content_hash
            )
        ],
        key=lambda item: item.artifact_id,
    )
    artifact_ids = {artifact.artifact_id for artifact in artifacts}
    edges = sorted(
        {
            (str(child), str(dependency))
            for child, dependency in graph.edges
            if str(child) in artifact_ids and str(dependency) in artifact_ids
        }
    )
    return artifacts, edges


def _requested_artifact_ids(
    artifacts: list[RetainedArtifact],
    edges: list[tuple[str, str]],
    requested_families: set[str],
) -> set[str]:
    """Return requested outputs and every retained artifact they consume."""
    if not requested_families:
        return {artifact.artifact_id for artifact in artifacts}
    dependencies_by_child: dict[str, list[str]] = {}
    for child, dependency in edges:
        dependencies_by_child.setdefault(child, []).append(dependency)
    required = {
        artifact.artifact_id
        for artifact in artifacts
        if artifact.artifact_kind in requested_families
        or _family_for(artifact) in requested_families
    }
    pending = list(required)
    while pending:
        artifact_id = pending.pop()
        for dependency in dependencies_by_child.get(artifact_id, []):
            if dependency not in required:
                required.add(dependency)
                pending.append(dependency)
    return required


def plan_minimal_execution(
    input_value: MinimalExecutionPlanInput,
) -> MinimalExecutionPlan:
    """Build a stable, fail-closed execution plan from an observed graph."""
    intent = str(input_value.execution_intent).strip().lower()
    if intent not in EXECUTION_INTENTS:
        raise AppError(
            code="minimal_execution_plan_intent_invalid",
            message="Minimal execution planning requires a supported execution intent",
            retryable=False,
            context={"execution_intent": intent},
        )
    artifacts, edges = _canonical_graph(input_value.retained_graph)
    by_id = {artifact.artifact_id: artifact for artifact in artifacts}
    invalid_by_id: dict[str, ArtifactInvalidation] = {}
    blockers_by_id: dict[tuple[str, str], MissingLineageBlocker] = {}
    child_ids: dict[str, list[str]] = {}
    for child, dependency in edges:
        child_ids.setdefault(dependency, []).append(child)
    for children in child_ids.values():
        children.sort()

    requested = {
        str(value).strip()
        for value in input_value.requested_output_families
        if str(value).strip()
    }
    relevant_artifact_ids = _requested_artifact_ids(artifacts, edges, requested)
    if intent == "targeted_repair" and "rendered_html" in requested:
        # Prompt materializations are consumed by the rendered report even
        # though the legacy composite renderer predates their explicit lineage
        # edges.  Include them only when a retained report has actually
        # materialized them; legacy reports continue through the established
        # checkpoint safety path rather than gaining synthetic blockers.
        relevant_artifact_ids.update(
            item.artifact_id
            for item in artifacts
            if _is_prompt_family_materialization(item)
        )

    for artifact in artifacts:
        if artifact.artifact_id not in relevant_artifact_ids:
            continue
        if artifact.report_id != input_value.report_id:
            blockers_by_id[(artifact.artifact_id, "report_scope_mismatch")] = (
                MissingLineageBlocker(
                    artifact_id=artifact.artifact_id,
                    artifact_kind=artifact.artifact_kind,
                    reason="report_scope_mismatch",
                )
            )
            continue
        expected_edges = sorted(set(artifact.dependency_artifact_ids))
        observed_edges = sorted(
            dependency for child, dependency in edges if child == artifact.artifact_id
        )
        if expected_edges != observed_edges or any(
            dep not in by_id for dep in expected_edges
        ):
            invalid_by_id[artifact.artifact_id] = ArtifactInvalidation(
                artifact_id=artifact.artifact_id,
                artifact_kind=artifact.artifact_kind,
                artifact_family=_family_for(artifact),
                reason=INVALIDATION_DEPENDENCY_EDGE_MISSING,
            )
            blockers_by_id[
                (artifact.artifact_id, INVALIDATION_DEPENDENCY_EDGE_MISSING)
            ] = MissingLineageBlocker(
                artifact_id=artifact.artifact_id,
                artifact_kind=artifact.artifact_kind,
                reason=INVALIDATION_DEPENDENCY_EDGE_MISSING,
            )
            continue
        reason = _artifact_reason(
            artifact,
            input_value.current_compatibility,
            input_value.current_source_content_hashes,
            input_value.source_metadata_hash,
            input_value.current_publication_state,
        )
        if reason is not None:
            kind, detail = reason
            if kind == "missing_lineage":
                blockers_by_id[(artifact.artifact_id, detail)] = MissingLineageBlocker(
                    artifact_id=artifact.artifact_id,
                    artifact_kind=artifact.artifact_kind,
                    reason=f"missing_lineage:{detail}",
                )
            else:
                invalid_by_id[artifact.artifact_id] = ArtifactInvalidation(
                    artifact_id=artifact.artifact_id,
                    artifact_kind=artifact.artifact_kind,
                    artifact_family=_family_for(artifact),
                    reason=f"{kind}:{detail}" if detail else kind,
                )

    queue = sorted(invalid_by_id)
    while queue:
        dependency = queue.pop(0)
        for child in child_ids.get(dependency, []):
            if (
                child in relevant_artifact_ids
                and child not in invalid_by_id
                and child in by_id
            ):
                item = by_id[child]
                invalid_by_id[child] = ArtifactInvalidation(
                    artifact_id=child,
                    artifact_kind=item.artifact_kind,
                    artifact_family=_family_for(item),
                    reason="dependency_invalidated",
                )
                queue.append(child)

    blockers = sorted(
        blockers_by_id.values(), key=lambda item: (item.artifact_id, item.reason)
    )
    invalid = sorted(invalid_by_id.values(), key=lambda item: item.artifact_id)
    available_families = {
        value for item in artifacts for value in (item.artifact_kind, _family_for(item))
    }
    for family in sorted(requested - available_families):
        blockers.append(
            MissingLineageBlocker(
                artifact_id=f"requested:{family}",
                artifact_kind=family,
                reason="missing_requested_artifact",
            )
        )
    blockers.sort(key=lambda item: (item.artifact_id, item.reason))
    reusable = [
        item.artifact_id
        for item in artifacts
        if item.artifact_id not in invalid_by_id
        and not any(blocker.artifact_id == item.artifact_id for blocker in blockers)
        and (
            not requested
            or item.artifact_kind in requested
            or _family_for(item) in requested
        )
    ]
    stages = _required_stages(intent=intent, invalid=invalid, blockers=blockers)
    skipped = [stage for stage in _STAGE_ORDER if stage not in stages]
    external = sorted({call for stage in stages for call in _EXTERNAL_BY_STAGE[stage]})
    side_effects = sorted(
        {effect for stage in stages for effect in _SIDE_EFFECTS_BY_STAGE[stage]}
    )
    categories = [
        EstimatedWorkCategory(category=call, estimated_calls=1) for call in external
    ]
    publication_prerequisites: list[str] = []
    if intent == "publication_repair":
        if not any(item.artifact_kind == "rendered_html" for item in artifacts):
            publication_prerequisites.append("validated_rendered_html_missing")
        elif any(item.artifact_kind == "rendered_html" for item in invalid):
            publication_prerequisites.append("validated_rendered_html_invalid")
        if blockers:
            publication_prerequisites.append("lineage_complete_required")
    required_prompt_family_set = {
        item.artifact_family
        for item in invalid
        if item.artifact_kind.startswith("prompt_family:")
    }
    artifact_prompt_family_prefix = "report_vs/artifacts/"
    validation_prompt_families = {
        "report_vs/validate/grounding",
        "report_vs/validate/semantic",
    }
    if any(
        family.startswith(artifact_prompt_family_prefix)
        for family in required_prompt_family_set
    ):
        required_prompt_family_set.update(
            _family_for(item)
            for item in artifacts
            if _is_prompt_family_materialization(item)
            and _family_for(item) in validation_prompt_families
            and item.artifact_id in relevant_artifact_ids
        )
    required_prompt_families = sorted(required_prompt_family_set)
    reused_prompt_families = sorted(
        {
            _family_for(item)
            for item in artifacts
            if _is_prompt_family_materialization(item)
            and item.artifact_id in relevant_artifact_ids
            and item.artifact_id not in invalid_by_id
            and not any(blocker.artifact_id == item.artifact_id for blocker in blockers)
        }
    )
    if required_prompt_families:
        regenerated_artifact_prompt_count = sum(
            family.startswith(artifact_prompt_family_prefix)
            for family in required_prompt_families
        )
        required_validation_prompt_count = sum(
            family in validation_prompt_families for family in required_prompt_families
        )
        external = ["html_render"]
        categories = [EstimatedWorkCategory(category="html_render", estimated_calls=1)]
        if regenerated_artifact_prompt_count:
            external.append("report_analysis_model")
            categories.append(
                EstimatedWorkCategory(
                    category="report_analysis_model",
                    estimated_calls=regenerated_artifact_prompt_count,
                )
            )
        if required_validation_prompt_count:
            external.append("validator_model")
            categories.append(
                EstimatedWorkCategory(
                    category="validator_model",
                    estimated_calls=required_validation_prompt_count,
                )
            )
        side_effects = [
            "analysis_artifact_write",
            "checkpoint_write",
            "rendered_html_write",
        ]
    provisional = MinimalExecutionPlan(
        schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
        execution_intent=intent,
        report_id=input_value.report_id,
        reusable_artifacts=sorted(reusable),
        invalid_artifacts=invalid,
        required_stages=stages,
        skipped_stages=skipped,
        required_external_calls=external,
        expected_side_effects=side_effects,
        estimated_cost_call_categories=categories,
        missing_lineage_blockers=blockers,
        publication_prerequisites=publication_prerequisites,
        plan_hash="",
        required_prompt_families=required_prompt_families,
        reused_prompt_families=reused_prompt_families,
    )
    return replace(provisional, plan_hash=_plan_hash(provisional))


__all__ = [
    "EXECUTION_INTENTS",
    "INVALIDATION_ARTIFACT_HASH_MISMATCH",
    "INVALIDATION_CROP_PROFILE_CHANGED",
    "INVALIDATION_DEPENDENCY_EDGE_MISSING",
    "INVALIDATION_MODEL_POLICY_CHANGED",
    "INVALIDATION_OCR_POLICY_VERSION_CHANGED",
    "INVALIDATION_OUTPUT_SCHEMA_CHANGED",
    "INVALIDATION_PARSER_VERSION_CHANGED",
    "INVALIDATION_PROMPT_CHANGED",
    "INVALIDATION_PUBLICATION_TARGET_CHANGED",
    "INVALIDATION_RETAINED_ARTIFACT_MISSING",
    "INVALIDATION_SOURCE_CONTENT_CHANGED",
    "INVALIDATION_SOURCE_METADATA_CHANGED",
    "INVALIDATION_TEMPLATE_CHANGED",
    "INVALIDATION_VALIDATOR_CHANGED",
    "plan_minimal_execution",
]
