from __future__ import annotations

import hashlib
import json
import logging
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Sequence

from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    ArtifactRegenerationResponse,
    RepairDecision,
    RepairPatchOperation,
    RegenerationIssue,
    RegenerationTarget,
)
from src.contracts.run_context import RunContext
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    align_soft_copy_claim_bindings_to_text,
    soft_copy_claim_provenance_from_payload,
    soft_copy_material_sentences,
    soft_copy_public_text,
    valid_soft_copy_evidence_selection,
)
from src.contracts.validation import ValidationRequest
from src.generators.artifact_generator import (
    apply_artifact_family_policy,
    assemble_artifacts_payload,
    build_toc_artifacts,
    render_artifact_json_model,
    store_artifacts_payload,
)
from src.generators.artifact_normalization import (
    REQUIRED_REPORT_PAYLOAD_INSIGHTS,
    artifact_base_variables,
    artifact_quote_candidates,
    artifact_vector_store_enabled,
    build_expert_synthesis_context,
    discard_location_only_insights,
    discard_location_only_quotes,
    fallback_artifact_insights_from_findings,
    normalize_artifact_editorial_plan,
    normalize_artifact_evidence_ids,
    normalize_artifact_insights,
    normalize_artifact_quotes,
    normalize_artifact_source_status,
    normalize_artifact_summary,
    normalize_artifact_toc_entries,
    normalize_artifact_topics,
    normalize_expert_domain,
    select_artifact_insights,
    stabilize_broad_artifact_editorial_plan,
    strip_linkedin_inline_reference_ids,
)
from src.generators.artifact_prompt_provenance import (
    artifact_family_for_producing_namespace,
    artifact_prompt_identity,
)
from src.generators.evidence_compatibility import (
    CompatibilityQuery,
    rank_compatible_alternatives,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
)
from src.generators.validation.evidence import retrieve_evidence_windows
from src.generators.validation.preparation import prepare_validation_inputs
from src.services import prompt_service, report_analysis_store_service
from src.utils.analysis_family import family_is_abstained
from src.utils.cache_utils import sha256_json
from src.utils.coercion import string_value as _s
from src.utils.editorial_identity import failed_insight_id
from src.utils.errors import AppError
from src.utils.json_utils import dump_json_text as _dump_json
from src.utils.logging import child_context, log_event
from src.utils.model_client_contract import require_injected_model_client

logger = logging.getLogger("market_lense.report_regeneration_generator")


@dataclass
class _RegenerationState:
    toc_entries: List[Dict[str, Any]]
    toc_topics: List[str]
    topic_briefs: List[Dict[str, Any]]
    editorial_plan: Dict[str, Any]
    summary: Dict[str, Any]
    insights_candidates: List[Dict[str, Any]]
    insights_final: List[Dict[str, Any]]
    quotes_final: List[Dict[str, Any]]
    cover_semantics: Dict[str, Any]
    expert_comment: str
    linkedin_post: str
    source_status: Dict[str, Any]
    regenerated_sections: List[str] = field(default_factory=list)
    prompt_namespaces: List[str] = field(default_factory=list)
    prompt_identities: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    producing_prompt_identities: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    regeneration_prompt_requirements: Dict[str, str] = field(default_factory=dict)
    soft_copy_claim_bindings: Dict[str, List[Dict[str, Any]]] = field(
        default_factory=dict
    )
    soft_copy_prompt_identities: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    soft_copy_generation_attempts: Dict[str, int] = field(default_factory=dict)
    existing_soft_copy_claim_provenance: Dict[str, Any] = field(default_factory=dict)
    replaced_soft_copy_families: List[str] = field(default_factory=list)
    replaced_soft_copy_claim_ids: Dict[str, List[str]] = field(default_factory=dict)
    soft_copy_repair_texts: Dict[str, List[str]] = field(default_factory=dict)
    soft_copy_repair_lineage: Dict[str, str] = field(default_factory=dict)
    soft_copy_evidence_selections: Dict[str, Dict[str, Any]] = field(
        default_factory=dict
    )
    payload_overrides: Dict[str, Any] = field(default_factory=dict)
    selected_evidence_ids: List[str] = field(default_factory=list)
    repair_decisions: List[RepairDecision] = field(default_factory=list)
    deterministic_repairs: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class _RegenerationRuntime:
    request: ArtifactRegenerationRequest
    safe_doc_map: Dict[str, Any]
    safe_evidence: Dict[str, Any]
    base_vars: Dict[str, Any]
    quote_candidates: List[Dict[str, Any]]
    expert_domain: str
    artifact_use_vector_store: bool
    openai_client: Any
    prompt_client: Any


@dataclass(frozen=True)
class _RegenerationHandlerExecution:
    handler: "_RegenerationHandler"
    runtime: _RegenerationRuntime
    state: _RegenerationState
    target: RegenerationTarget
    target_ctx: RunContext
    grounding_package: Dict[str, Any]


@dataclass(frozen=True)
class _SoftCopyClaimRepair:
    """One retained sentence that can be safely repaired in place."""

    artifact_family: str
    claim: SoftCopyClaimProvenance
    text: str
    start: int
    end: int
    issue: RegenerationIssue
    issues: tuple[RegenerationIssue, ...] = ()


@dataclass(frozen=True)
class _RegenerationHandler:
    target_section: str
    prompt_namespaces: tuple[str, ...]
    current_section_payload: Callable[[Dict[str, Any]], Any]
    extra_fix_checklist: tuple[str, ...]
    handle: Callable[[_RegenerationHandlerExecution], None]


def regenerate_artifacts(
    request: ArtifactRegenerationRequest,
    *,
    openai_client=None,
    prompt_client=prompt_service,
    analysis_store=report_analysis_store_service,
) -> ArtifactRegenerationResponse:
    ctx = request.ctx
    safe_artifacts = (
        deepcopy(request.current_artifacts)
        if isinstance(request.current_artifacts, dict)
        else {}
    )
    safe_doc_map = request.doc_map if isinstance(request.doc_map, dict) else {}
    safe_evidence = (
        request.evidence_packs if isinstance(request.evidence_packs, dict) else {}
    )
    availability = normalize_artifact_source_status(
        request.source_status,
        request.settings,
        has_density=isinstance(request.source_status, dict)
        and (
            "text_density" in request.source_status
            or "density_threshold" in request.source_status
        ),
        vector_store_id=request.vector_store_id,
    )
    artifact_use_vector_store = artifact_vector_store_enabled(
        settings=request.settings,
        vector_store_id=request.vector_store_id,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_regeneration_start",
            module=logger.name,
            fields={
                "report_id": request.report_id,
                "attempt_index": request.attempt_index,
                "plan_mode": request.plan.mode,
                "targets": [target.target_section for target in request.plan.targets],
            },
        )
    )

    base_vars = artifact_base_variables(safe_doc_map, safe_evidence)
    base_vars.pop("canonical_evidence_ids_json", None)
    quote_candidates = artifact_quote_candidates(safe_evidence)
    expert_domain = normalize_expert_domain(request.categories)
    fallback_toc_bundle = build_toc_artifacts(doc_map=safe_doc_map)
    state = _build_regeneration_state(
        safe_artifacts=safe_artifacts,
        fallback_toc_bundle=fallback_toc_bundle,
        source_status=availability,
    )
    state.editorial_plan = stabilize_broad_artifact_editorial_plan(
        state.editorial_plan,
        doc_map=safe_doc_map,
        evidence_packs=safe_evidence,
    )
    runtime = _RegenerationRuntime(
        request=request,
        safe_doc_map=safe_doc_map,
        safe_evidence=safe_evidence,
        base_vars=base_vars,
        quote_candidates=quote_candidates,
        expert_domain=expert_domain,
        artifact_use_vector_store=artifact_use_vector_store,
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    for target in request.plan.targets:
        target_ctx = child_context(
            ctx, task_id=f"{ctx.task_id}:{target.target_section}"
        )
        logger.info(
            log_event(
                target_ctx,
                role="generator",
                event="artifact_regeneration_target_start",
                module=logger.name,
                fields={
                    "target_section": target.target_section,
                    "regenerate_steps": list(target.regenerate_steps),
                    "issue_count": len(target.issues),
                },
            )
        )
        current_artifact_state = _artifact_state_from_state(state)
        prepared = _prepare_grounding(request, current_artifact_state)
        grounding_package = _build_grounding_package(
            target=target,
            prepared=prepared,
            artifacts=current_artifact_state,
            evidence_packs=safe_evidence,
            doc_map=safe_doc_map,
        )
        handler = _resolve_regeneration_handler(target.target_section)
        repair_decision_count = len(state.repair_decisions)
        handler.handle(
            _RegenerationHandlerExecution(
                handler=handler,
                runtime=runtime,
                state=state,
                target=target,
                target_ctx=target_ctx,
                grounding_package=grounding_package,
            )
        )
        # The attempt fingerprint must describe the evidence actually used,
        # not the planned evidence, so a failed strategy cannot be repeated
        # under another nominal label.
        target_decisions = [
            decision for decision in state.repair_decisions[repair_decision_count:]
        ]
        if target_decisions:
            state.selected_evidence_ids.extend(
                evidence_id
                for decision in target_decisions
                for evidence_id in decision.evidence_ids_used
            )
        else:
            state.selected_evidence_ids.extend(
                grounding_package.get("evidence_ids") or []
            )
        logger.info(
            log_event(
                target_ctx,
                role="generator",
                event="artifact_regeneration_target_complete",
                module=logger.name,
                fields={
                    "target_section": target.target_section,
                    "regenerated_sections": list(state.regenerated_sections),
                },
            )
        )

    (
        summary,
        insights_candidates,
        insights_final,
        quotes_final,
        expert_comment,
        linkedin_post,
        family_status,
    ) = apply_artifact_family_policy(
        summary=state.summary,
        insights_candidates=state.insights_candidates,
        insights_final=state.insights_final,
        quotes_final=state.quotes_final,
        expert_comment=state.expert_comment,
        linkedin_post=state.linkedin_post,
    )
    insights_candidates = discard_location_only_insights(insights_candidates)
    insights_final = discard_location_only_insights(insights_final)
    quotes_final = discard_location_only_quotes(quotes_final)
    cache_meta = deepcopy(safe_artifacts.get("_cache"))
    if not isinstance(cache_meta, dict):
        cache_meta = {}
    cached_prompts = cache_meta.get("prompts")
    prompts = dict(cached_prompts) if isinstance(cached_prompts, dict) else {}
    prompts.update(state.prompt_identities)
    cache_meta["prompts"] = prompts
    cache_meta["producing_prompt_identities"] = state.producing_prompt_identities
    cache_meta["regeneration_prompt_requirements"] = (
        state.regeneration_prompt_requirements
    )
    updated_artifacts = assemble_artifacts_payload(
        report_id=request.report_id,
        report_name=request.report_name,
        doc_map=safe_doc_map,
        evidence_packs=safe_evidence,
        toc_bundle={
            "toc_entries": state.toc_entries,
            "toc_topics": state.toc_topics,
            "toc_topics_expanded": state.topic_briefs,
        },
        editorial_plan=state.editorial_plan,
        summary=summary,
        cover_semantics=state.cover_semantics,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        expert_comment=expert_comment,
        linkedin_post=linkedin_post,
        source_status=availability,
        family_status=family_status,
        category_ids=safe_artifacts.get("categories")
        if isinstance(safe_artifacts.get("categories"), list)
        else [],
        ctx=ctx,
        cache_meta=cache_meta,
        soft_copy_claim_bindings=state.soft_copy_claim_bindings,
        soft_copy_prompt_identities=state.soft_copy_prompt_identities,
        soft_copy_generation_attempts=state.soft_copy_generation_attempts,
        existing_soft_copy_claim_provenance=state.existing_soft_copy_claim_provenance,
        replaced_soft_copy_families=state.replaced_soft_copy_families,
        replaced_soft_copy_claim_ids=state.replaced_soft_copy_claim_ids,
        soft_copy_repair_texts=state.soft_copy_repair_texts,
        soft_copy_repair_lineage=state.soft_copy_repair_lineage,
        regeneration_attempt=request.attempt_index,
        validate_references=False,
    )
    _preserve_atomic_target_families(
        updated_artifacts=updated_artifacts,
        state=state,
        plan=request.plan,
        original_artifacts=request.current_artifacts,
    )
    changed_roots = {
        str(path).split(".", 1)[0]
        for target in request.plan.targets
        for path in target.allowed_paths
    }
    derived_inputs = {
        "topics_covered": {"summary", "insights_final"},
        "claim_ledgers": {"summary", "insights_final", "quotes_final"},
    }
    for artifact_root, input_roots in derived_inputs.items():
        if changed_roots.intersection(input_roots):
            continue
        if artifact_root in safe_artifacts:
            updated_artifacts[artifact_root] = deepcopy(safe_artifacts[artifact_root])
        else:
            # A targeted repair must not introduce an unrelated derived
            # projection that was absent from the last promoted artifact set.
            updated_artifacts.pop(artifact_root, None)
    if state.soft_copy_evidence_selections:
        # This is private candidate-audit provenance, never rendered public copy.
        updated_artifacts["_repair_evidence_selection"] = {
            key: state.soft_copy_evidence_selections[key]
            for key in sorted(state.soft_copy_evidence_selections)
        }
    candidate_artifacts_path = store_artifacts_payload(
        analysis_store=analysis_store,
        output_dir=request.settings.output_dir,
        report_id=request.report_id,
        report_name=request.report_name,
        payload=updated_artifacts,
        ctx=ctx,
        pack_name=f"artifacts_regen_candidate_{request.attempt_index}",
    )
    response = ArtifactRegenerationResponse(
        updated_artifacts=updated_artifacts,
        regenerated_sections=state.regenerated_sections,
        prompt_namespaces=state.prompt_namespaces,
        artifacts_path="",
        artifacts_snapshot_path=candidate_artifacts_path,
        candidate_artifacts_path=candidate_artifacts_path,
        repair_action=_actual_repair_action(state, request),
        repair_strategy=_actual_repair_strategy(state, request),
        selected_evidence_ids=_unique_strings(state.selected_evidence_ids),
        repair_decisions=list(state.repair_decisions),
        payload_overrides=deepcopy(state.payload_overrides),
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_regeneration_complete",
            module=logger.name,
            fields={
                "report_id": request.report_id,
                "attempt_index": request.attempt_index,
                "regenerated_sections": state.regenerated_sections,
                "candidate_artifacts_path": candidate_artifacts_path,
            },
        )
    )
    return response


_DETERMINISTIC_REPAIR_ACTIONS = {
    "canonical_identity": "COPY_CANONICAL_SOURCE_VALUE",
    "canonical_quote_restore": "COPY_CANONICAL_SOURCE_VALUE",
    "canonical_metric_copy": "CORRECT_PROTECTED_FACT",
    "canonical_identity_abstained": "ABSTAIN",
    "safe_abstain": "ABSTAIN",
}


def _actual_repair_action(
    state: _RegenerationState, request: ArtifactRegenerationRequest
) -> str:
    if state.repair_decisions:
        return "+".join(
            dict.fromkeys(item.repair_action for item in state.repair_decisions)
        )
    for label in state.deterministic_repairs:
        action = _DETERMINISTIC_REPAIR_ACTIONS.get(label)
        if action:
            return action
    targets = request.plan.targets
    if (
        state.prompt_namespaces
        and targets
        and targets[0].repair_action
        in {
            "COPY_CANONICAL_SOURCE_VALUE",
            "CORRECT_PROTECTED_FACT",
        }
    ):
        return "REGENERATE_ITEM"
    return targets[0].repair_action if targets else "REGENERATE_ITEM"


def _actual_repair_strategy(
    state: _RegenerationState, request: ArtifactRegenerationRequest
) -> str:
    if state.repair_decisions:
        return "+".join(
            dict.fromkeys(item.repair_strategy for item in state.repair_decisions)
        )
    if state.deterministic_repairs:
        return "+".join(dict.fromkeys(state.deterministic_repairs))
    targets = request.plan.targets
    if (
        state.prompt_namespaces
        and targets
        and targets[0].repair_action
        in {
            "COPY_CANONICAL_SOURCE_VALUE",
            "CORRECT_PROTECTED_FACT",
        }
    ):
        return "current_evidence_escalation"
    return targets[0].repair_strategy if targets else "current_evidence"


def _prepare_grounding(
    request: ArtifactRegenerationRequest,
    artifacts: Dict[str, Any],
):
    validation_request = ValidationRequest(
        schema_version="1.0",
        report_id=request.report_id,
        report=_regeneration_report_stub(artifacts),
        artifacts=artifacts,
        evidence_packs=request.evidence_packs,
        vector_store_id=request.vector_store_id,
        publisher_name=request.publisher_name,
        report_name=request.report_name,
        source_url=request.source_url,
    )
    return prepare_validation_inputs(
        validation_request,
        request.settings,
        request.ctx,
        md5=request.md5,
    )


def _regeneration_report_stub(artifacts: Dict[str, Any]):
    from src.generators.report_generation_shared import base_payload

    payload = base_payload("", 0, "", "")
    summary_abstained = family_is_abstained(artifacts, "summary")
    insights_abstained = family_is_abstained(artifacts, "insights_bundle")
    quotes_abstained = family_is_abstained(artifacts, "quotes")
    summary = _copy_dict(artifacts.get("summary"))
    if not summary_abstained and _s(summary.get("tldr")).strip():
        payload.tldr = _s(summary.get("tldr"))
    if not summary_abstained and _s(summary.get("executive_summary")).strip():
        payload.commentary = _s(summary.get("executive_summary"))
    payload.insights = []
    if not insights_abstained:
        payload.insights = [
            _s(entry.get("text"))
            for entry in _copy_list(artifacts.get("insights_final"))[:5]
            if isinstance(entry, dict)
        ]
    while len(payload.insights) < 5:
        payload.insights.append("")
    quotes = _copy_list(artifacts.get("quotes_final"))
    if not quotes_abstained and quotes and isinstance(quotes[0], dict):
        payload.quote.text = _s(quotes[0].get("text"))
        payload.quote.author = _s(
            quotes[0].get("speaker") or quotes[0].get("author") or "Unknown"
        )
    return payload


def _build_grounding_package(
    *,
    target: RegenerationTarget,
    prepared,
    artifacts: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    doc_map: Dict[str, Any],
) -> Dict[str, Any]:
    current_section = _current_section_payload(target.target_section, artifacts)
    quarantined_ids = _unique_strings(
        evidence_id
        for issue in target.issues
        for evidence_id in issue.excluded_evidence_ids
    )
    failed_ids = {
        _normalized_evidence_id(evidence_id)
        for evidence_id in (
            quarantined_ids
            + [
                evidence_id
                for issue in target.issues
                for evidence_id in issue.evidence_ids
            ]
        )
        if _normalized_evidence_id(evidence_id)
    }
    issue_pages = _unique_ints(page for issue in target.issues for page in issue.pages)
    search_text = " ".join(
        part
        for part in (
            _section_text(current_section),
            " ".join(issue.message for issue in target.issues),
        )
        if part
    )
    rebind_to_alternative = target.repair_strategy == "alternative_evidence"
    if rebind_to_alternative:
        relevant_evidence = _replacement_evidence_entries(
            evidence_packs=evidence_packs,
            excluded_evidence_ids=failed_ids,
            search_text=search_text,
            pages=issue_pages,
            section=target.target_section,
        )
    else:
        relevant_evidence = (
            _replacement_evidence_entries(
                evidence_packs=evidence_packs,
                excluded_evidence_ids=set(quarantined_ids),
                search_text=search_text,
                pages=issue_pages,
                section=target.target_section,
            )
            if quarantined_ids
            else _collect_relevant_evidence_entries(
                target.issues, evidence_packs, doc_map
            )
        )
    if not relevant_evidence and target.target_section in {
        "summary",
        "expert_comment",
        "linkedin_post",
    }:
        relevant_evidence = _replacement_evidence_entries(
            evidence_packs=evidence_packs,
            excluded_evidence_ids=failed_ids
            if rebind_to_alternative
            else set(quarantined_ids),
            search_text=" ".join(
                part
                for part in (
                    search_text,
                    _dump_json(artifacts.get("editorial_plan") or {}),
                    _dump_json(artifacts.get("insights_final") or []),
                )
                if part
            ),
            pages=issue_pages,
            section=target.target_section,
        )
    evidence_ids = _unique_strings(
        _entry_evidence_id(entry) for entry in relevant_evidence
    )
    evidence_windows = (
        []
        if quarantined_ids
        else retrieve_evidence_windows(search_text, prepared.evidence_windows)
    )
    return {
        "current_section": current_section,
        "relevant_evidence": relevant_evidence,
        "evidence_windows": [
            {"idx": window.idx, "text": window.text} for window in evidence_windows[:4]
        ],
        "evidence_ids": evidence_ids,
        "quarantined_evidence_ids": quarantined_ids,
        "pages": issue_pages,
    }


MAX_SOFT_COPY_CLAIM_EVIDENCE_ENTRIES = 4


def _build_soft_copy_claim_evidence_package(
    *,
    claim: SoftCopyClaimProvenance,
    issue: RegenerationIssue,
    artifacts: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    quarantined_evidence_ids: tuple[str, ...],
    doc_map: Dict[str, Any] | None = None,
    claim_text: str = "",
) -> Dict[str, Any]:
    """Build one bounded, deterministic retained-evidence package for a claim."""

    quarantined = {
        _normalized_evidence_id(evidence_id)
        for evidence_id in quarantined_evidence_ids
        if _normalized_evidence_id(evidence_id)
    }
    evidence_by_id = _retained_evidence_entries_by_id(evidence_packs, doc_map)
    direct_ids = _unique_strings(claim.evidence_ids)
    parent_ids = _soft_copy_parent_evidence_ids(
        claim=claim, artifacts=artifacts, claim_text=claim_text
    )

    def resolved(ids: List[str]) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for evidence_id in ids:
            normalized_id = _normalized_evidence_id(evidence_id)
            entry = evidence_by_id.get(normalized_id)
            if not normalized_id or normalized_id in quarantined or entry is None:
                continue
            if normalized_id not in seen:
                seen.add(normalized_id)
                selected.append(entry)
            if len(selected) == MAX_SOFT_COPY_CLAIM_EVIDENCE_ENTRIES:
                break
        return selected

    selected = resolved(direct_ids)
    strategy = "claim_evidence_ids" if selected else ""
    if not selected:
        selected = resolved(parent_ids)
        strategy = "parent_insight_or_theme" if selected else ""
    if not selected:
        selected = _typed_compatible_evidence_entries(
            evidence_by_id=evidence_by_id,
            quarantined_ids=quarantined,
            search_text=" ".join((claim_text, issue.message)),
            require_relevance=True,
        )
        strategy = "typed_compatibility_fallback" if selected else "abstain"

    evidence_ids = [_entry_evidence_id(entry) for entry in selected]
    provenance = {
        "schema_version": "1.0",
        "claim_id": claim.claim_id,
        "strategy": strategy,
        "direct_evidence_ids": direct_ids,
        "parent_evidence_ids": parent_ids,
        "quarantined_evidence_ids": sorted(quarantined),
        "selected_evidence_ids": evidence_ids,
        "selected_evidence_entries": _canonical_evidence_entries(selected),
    }
    provenance["package_sha256"] = _canonical_evidence_hash(provenance)
    return {
        "relevant_evidence": selected,
        "evidence_ids": evidence_ids,
        "evidence_selection": provenance,
    }


def _claim_scoped_grounding_package(
    execution: _RegenerationHandlerExecution,
    repair: _SoftCopyClaimRepair,
) -> Dict[str, Any]:
    """Replace target-wide evidence with the failed claim's retained support."""

    package = dict(execution.grounding_package)
    selected = _build_soft_copy_claim_evidence_package(
        claim=repair.claim,
        issue=repair.issue,
        artifacts=_artifact_state_from_state(execution.state),
        evidence_packs=execution.runtime.safe_evidence,
        quarantined_evidence_ids=tuple(
            dict.fromkeys(
                evidence_id
                for issue in repair.issues or (repair.issue,)
                for evidence_id in issue.excluded_evidence_ids
            )
        ),
        doc_map=execution.runtime.safe_doc_map,
        claim_text=repair.text,
    )
    selection = selected["evidence_selection"]
    package.update(selected)
    package["quarantined_evidence_ids"] = list(selection["quarantined_evidence_ids"])
    package["evidence_windows"] = []
    execution.state.soft_copy_evidence_selections[
        f"{repair.artifact_family}:{repair.claim.claim_id}"
    ] = selection
    return package


def _normalized_evidence_id(value: object) -> str:
    return _s(value).strip().casefold()


_VOLATILE_EVIDENCE_FIELDS = frozenset(
    {
        "_cache",
        "cache_key",
        "created_at",
        "created_at_utc",
        "generated_at",
        "generated_at_utc",
        "path",
        "retrieved_at",
        "retrieved_at_utc",
        "run_id",
        "span_id",
        "task_id",
        "trace_id",
        "updated_at",
        "updated_at_utc",
    }
)


def _canonical_evidence_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the selected package content in stable, non-volatile form."""

    return [_canonical_evidence_value(entry) for entry in entries]


def _canonical_evidence_value(value: Any, *, field_name: str = "") -> Any:
    if isinstance(value, dict):
        return {
            key: _canonical_evidence_value(item, field_name=key)
            for key, item in sorted(value.items())
            if key not in _VOLATILE_EVIDENCE_FIELDS
        }
    if isinstance(value, list):
        items = [_canonical_evidence_value(item) for item in value]
        if field_name in {"evidence_ids", "pages"}:
            return sorted(items, key=_canonical_json)
        return items
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _canonical_evidence_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _retained_evidence_entries_by_id(
    evidence_packs: Dict[str, Any],
    doc_map: Dict[str, Any] | None,
) -> Dict[str, Dict[str, Any]]:
    """Canonicalize retained entries independently of input mapping order."""

    candidates: List[Dict[str, Any]] = []
    for pack_name in sorted(evidence_packs):
        candidates.extend(_all_pack_entries(pack_name, evidence_packs[pack_name]))
    candidates.extend(_doc_map_section_evidence_entries(doc_map or {}))
    ordered = sorted(
        candidates,
        key=lambda entry: (
            _normalized_evidence_id(_entry_evidence_id(entry)),
            _s(entry.get("pack_name")),
            _dump_json(entry),
        ),
    )
    result: Dict[str, Dict[str, Any]] = {}
    for entry in ordered:
        evidence_id = _normalized_evidence_id(_entry_evidence_id(entry))
        if evidence_id and evidence_id not in result:
            result[evidence_id] = entry
    return result


def _doc_map_section_evidence_entries(
    doc_map: Dict[str, Any], target_ids: set[str] | None = None
) -> List[Dict[str, Any]]:
    """Return canonical retained DocMap entries in their existing package shape."""

    entries: List[Dict[str, Any]] = []
    for section in doc_map.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _s(section.get("id")).strip()
        if not section_id or (target_ids is not None and section_id not in target_ids):
            continue
        entries.append(
            {
                "pack_name": "doc_map",
                "id": section_id,
                "title": _s(section.get("title")),
                "summary": _s(section.get("summary")),
                "pages": list(section.get("pages") or []),
            }
        )
    return entries


def _soft_copy_parent_evidence_ids(
    *, claim: SoftCopyClaimProvenance, artifacts: Dict[str, Any], claim_text: str
) -> List[str]:
    """Resolve declared parent insight/theme links before lexical fallback."""

    parent_insight_ids: set[str] = set()
    parent_theme_ids: set[str] = set()
    for span in claim.source_spans:
        for key in ("insight_id", "parent_insight_id"):
            value = _s(span.get(key)).strip()
            if value:
                parent_insight_ids.add(value)
        for key in ("theme_id", "parent_theme_id", "theme"):
            value = _s(span.get(key)).strip()
            if value:
                parent_theme_ids.add(value)

    query_tokens = _evidence_query_tokens(claim_text)
    insight_entries = [
        entry
        for entry in artifacts.get("insights_final") or []
        if isinstance(entry, dict)
    ]
    theme_entries = [
        entry
        for entry in _copy_dict(artifacts.get("editorial_plan")).get("themes") or []
        if isinstance(entry, dict)
    ]
    if query_tokens:
        for insight in insight_entries:
            if _token_overlap(query_tokens, _s(insight.get("text"))) >= 2:
                parent_insight_ids.add(_s(insight.get("id")).strip())
        for theme in theme_entries:
            if _token_overlap(query_tokens, _s(theme.get("theme"))) >= 2:
                parent_theme_ids.add(
                    _s(
                        theme.get("id") or theme.get("theme_id") or theme.get("theme")
                    ).strip()
                )

    evidence_ids: List[str] = []
    for insight in sorted(
        insight_entries, key=lambda entry: _s(entry.get("id")).strip()
    ):
        if _s(insight.get("id")).strip() not in parent_insight_ids:
            continue
        evidence_ids.extend(_entry_declared_evidence_ids(insight))
    for theme in sorted(
        theme_entries,
        key=lambda entry: _s(
            entry.get("id") or entry.get("theme_id") or entry.get("theme")
        ).strip(),
    ):
        theme_id = _s(
            theme.get("id") or theme.get("theme_id") or theme.get("theme")
        ).strip()
        if theme_id not in parent_theme_ids:
            continue
        evidence_ids.extend(_entry_declared_evidence_ids(theme))
    return _unique_strings(evidence_ids)


def _entry_declared_evidence_ids(entry: Dict[str, Any]) -> List[str]:
    values = [entry.get("evidence_id")]
    values.extend(entry.get("evidence_ids") or [])
    return _unique_strings(value for value in values if _s(value).strip())


def _evidence_query_tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]+", value)
        if len(token) >= 4
    }


def _token_overlap(query_tokens: set[str], value: str) -> int:
    return len(query_tokens.intersection(_evidence_query_tokens(value)))


def _typed_compatible_evidence_entries(
    *,
    evidence_by_id: Dict[str, Dict[str, Any]],
    quarantined_ids: set[str],
    search_text: str,
    metric: Dict[str, Any] | None = None,
    pages: List[int] | None = None,
    section: str = "",
    exclude_ids: set[str] | None = None,
    require_relevance: bool = False,
) -> List[Dict[str, Any]]:
    """Rank retained alternatives with the bounded typed compatibility scorer.

    Replaces the former lexical-only fallback: same-number/wrong-geography,
    wrong-period, wrong-cohort, wrong-denominator, and forecast-vs-observed
    near-matches can never outrank compatible evidence, and conflicting or
    quarantined entries are never returned.
    """

    def unwrap(entry: Dict[str, Any]) -> Dict[str, Any]:
        payload = entry.get("entry") if isinstance(entry, dict) else None
        return payload if isinstance(payload, dict) else entry

    query = CompatibilityQuery(
        text=search_text,
        metric=metric or {},
        pages=pages or [],
        section=section,
    )
    blocked = set(quarantined_ids) | set(exclude_ids or set())
    ranked = rank_compatible_alternatives(
        query,
        [
            (evidence_id, unwrap(entry))
            for evidence_id, entry in evidence_by_id.items()
            if evidence_id not in blocked
        ],
        quarantined_ids=sorted(blocked),
        limit=MAX_SOFT_COPY_CLAIM_EVIDENCE_ENTRIES * 4,
    )
    if require_relevance:
        # A claim-scoped fallback is repair support only when it is relevant
        # to the failed material through its metric payload or shared tokens;
        # otherwise the repair abstains instead of inventing support.
        ranked = [
            item
            for item in ranked
            if item.breakdown.get("token_relevance", 0.0) > 0.0
            or item.breakdown.get("metric_match", 0.0) > 0.0
        ]
    return [
        evidence_by_id[item.evidence_id]
        for item in ranked[:MAX_SOFT_COPY_CLAIM_EVIDENCE_ENTRIES]
    ]


def _lexically_relevant_evidence_entries(
    *,
    evidence_by_id: Dict[str, Dict[str, Any]],
    quarantined_ids: set[str],
    search_text: str,
) -> List[Dict[str, Any]]:
    """Compatibility-ranked fallback for claim-scoped soft-copy repairs."""

    return _typed_compatible_evidence_entries(
        evidence_by_id=evidence_by_id,
        quarantined_ids=quarantined_ids,
        search_text=search_text,
        require_relevance=True,
    )


def _replacement_evidence_entries(
    *,
    evidence_packs: Dict[str, Any],
    excluded_evidence_ids: set[str],
    search_text: str,
    pages: List[int] | None = None,
    section: str = "",
) -> List[Dict[str, Any]]:
    """Select bounded, source-retained alternatives after a fidelity failure."""

    evidence_by_id: Dict[str, Dict[str, Any]] = {}
    for pack_name, pack in evidence_packs.items():
        for wrapped in _all_pack_entries(pack_name, pack):
            entry = wrapped.get("entry")
            if not isinstance(entry, dict):
                continue
            evidence_id = _normalized_evidence_id(_entry_evidence_id(wrapped))
            if not evidence_id or evidence_id in excluded_evidence_ids:
                continue
            evidence_by_id.setdefault(evidence_id, entry)
    return _typed_compatible_evidence_entries(
        evidence_by_id=evidence_by_id,
        quarantined_ids=excluded_evidence_ids,
        search_text=search_text,
        pages=pages,
        section=section,
    )


def _all_pack_entries(pack_name: str, value: Any) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            entries.extend(_all_pack_entries(pack_name, item))
        return entries
    if not isinstance(value, dict):
        return entries
    if _s(value.get("id") or value.get("evidence_id")).strip():
        entries.append({"pack_name": pack_name, "entry": value})
    for nested in value.values():
        if isinstance(nested, (dict, list)):
            entries.extend(_all_pack_entries(pack_name, nested))
    return entries


def _entry_evidence_id(entry: Dict[str, Any]) -> str:
    payload = entry.get("entry") if isinstance(entry, dict) else None
    payload = payload if isinstance(payload, dict) else entry
    payload = payload if isinstance(payload, dict) else {}
    return _s(payload.get("id") or payload.get("evidence_id")).strip()


def _collect_relevant_evidence_entries(
    issues: List[RegenerationIssue],
    evidence_packs: Dict[str, Any],
    doc_map: Dict[str, Any],
) -> List[Dict[str, Any]]:
    target_ids = {
        evidence_id
        for issue in issues
        for evidence_id in issue.evidence_ids
        if _s(evidence_id).strip()
    }
    entries: List[Dict[str, Any]] = []
    if target_ids and isinstance(doc_map, dict):
        entries.extend(_doc_map_section_evidence_entries(doc_map, target_ids))
    for pack_name, pack in evidence_packs.items():
        entries.extend(_collect_pack_entries(pack_name, pack, target_ids))
    return entries[:8]


def _collect_pack_entries(
    pack_name: str,
    pack: Any,
    target_ids: set[str],
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if not target_ids:
        return entries
    if isinstance(pack, list):
        for entry in pack:
            if not isinstance(entry, dict):
                continue
            pack_id = _s(entry.get("id") or entry.get("evidence_id"))
            if pack_id in target_ids:
                entries.append(
                    {
                        "pack_name": pack_name,
                        "entry": entry,
                    }
                )
        return entries
    if not isinstance(pack, dict):
        return entries
    for key, value in pack.items():
        if isinstance(value, list):
            entries.extend(_collect_pack_entries(pack_name, value, target_ids))
        elif isinstance(value, dict):
            pack_id = _s(value.get("id") or value.get("evidence_id"))
            if pack_id in target_ids:
                entries.append(
                    {
                        "pack_name": pack_name,
                        "key": key,
                        "entry": value,
                    }
                )
    return entries


def _artifact_state(
    *,
    toc_entries: List[Dict[str, Any]],
    toc_topics: List[str],
    toc_topics_expanded: List[Dict[str, Any]],
    summary: Dict[str, Any],
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    cover_semantics: Dict[str, Any],
    expert_comment: str,
    linkedin_post: str,
    source_status: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "toc_entries": deepcopy(toc_entries),
        "toc_topics": deepcopy(toc_topics),
        "toc_topics_expanded": deepcopy(toc_topics_expanded),
        "summary": deepcopy(summary),
        "insights_candidates": deepcopy(insights_candidates),
        "insights_final": deepcopy(insights_final),
        "quotes_final": deepcopy(quotes_final),
        "cover_semantics": deepcopy(cover_semantics),
        "expert_comment": expert_comment,
        "linkedin_post": linkedin_post,
        "source_status": deepcopy(source_status),
    }


def _artifact_state_from_state(state: _RegenerationState) -> Dict[str, Any]:
    return _artifact_state(
        toc_entries=state.toc_entries,
        toc_topics=state.toc_topics,
        toc_topics_expanded=state.topic_briefs,
        summary=state.summary,
        insights_candidates=state.insights_candidates,
        insights_final=state.insights_final,
        quotes_final=state.quotes_final,
        cover_semantics=state.cover_semantics,
        expert_comment=state.expert_comment,
        linkedin_post=state.linkedin_post,
        source_status=state.source_status,
    )


def _current_section_payload(target_section: str, artifacts: Dict[str, Any]) -> Any:
    return _resolve_regeneration_handler(target_section).current_section_payload(
        artifacts
    )


def _issues_json(issues: Sequence[RegenerationIssue]) -> str:
    return _dump_json([asdict(issue) for issue in issues])


def _fix_checklist_json(target: RegenerationTarget) -> str:
    checklist = [
        "Address every listed validator failure directly.",
        "Remove unsupported claims instead of softening them.",
        "Use only grounded evidence from the supplied package.",
        "Preserve the required JSON schema exactly.",
    ]
    checklist.extend(
        _resolve_regeneration_handler(target.target_section).extra_fix_checklist
    )
    return _dump_json(checklist)


def _section_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return _dump_json(value)


def _copy_dict(value: Any) -> Dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _copy_list(value: Any) -> List[Any]:
    return deepcopy(value) if isinstance(value, list) else []


def _unique_strings(values) -> List[str]:
    unique: List[str] = []
    seen: set[str] = set()
    for value in values:
        token = _s(value).strip()
        if not token or token in seen:
            continue
        seen.add(token)
        unique.append(token)
    return unique


def _unique_ints(values) -> List[int]:
    unique: List[int] = []
    seen: set[int] = set()
    for value in values:
        if not isinstance(value, int) or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _preserve_atomic_target_families(
    *,
    updated_artifacts: Dict[str, Any],
    state: _RegenerationState,
    plan,
    original_artifacts: Dict[str, Any],
) -> None:
    """Apply targeted changes onto the exact current artifact family."""

    family_state = {
        "summary": state.summary,
        "insights_candidates": state.insights_candidates,
        "insights_final": state.insights_final,
        "quotes_final": state.quotes_final,
        "expert_comment": state.expert_comment,
        "linkedin_post": state.linkedin_post,
    }
    allowed_roots = {
        re.split(r"[.\[]", str(path or ""), maxsplit=1)[0]
        for target in plan.targets
        for path in target.allowed_paths
    }
    paths_by_root: Dict[str, List[str]] = {}
    for target in plan.targets:
        for allowed_path in target.allowed_paths:
            root = re.split(r"[.\[]", str(allowed_path or ""), maxsplit=1)[0]
            paths_by_root.setdefault(root, []).append(str(allowed_path or ""))
        if not target.allowed_paths:
            legacy_roots = {
                "summary": ("summary",),
                "insights_bundle": ("insights_candidates", "insights_final"),
                "quotes": ("quotes_final",),
                "expert_comment": ("expert_comment",),
                "linkedin_post": ("linkedin_post",),
            }.get(target.target_section, ())
            for root in legacy_roots:
                paths_by_root[root] = [root]
                allowed_roots.add(root)
    for root, paths in paths_by_root.items():
        if root not in family_state or root not in original_artifacts:
            continue
        if root in paths:
            updated_artifacts[root] = deepcopy(
                updated_artifacts.get(root, family_state[root])
            )
            continue
        merged_family = deepcopy(original_artifacts[root])
        for allowed_path in paths:
            merged_family = _copy_allowed_mutation_path(
                original_family=merged_family,
                target_family=(
                    family_state[root]
                    if root in state.soft_copy_repair_texts
                    else updated_artifacts.get(root, family_state[root])
                ),
                full_path=allowed_path,
                root=root,
            )
        updated_artifacts[root] = merged_family
    for root, value in family_state.items():
        if root not in allowed_roots:
            updated_artifacts[root] = deepcopy(original_artifacts.get(root, value))


def _copy_allowed_mutation_path(
    *,
    original_family: Any,
    target_family: Any,
    full_path: str,
    root: str,
) -> Any:
    """Copy one declared value from assembly onto its last-promoted family."""

    path = full_path[len(root) :].lstrip(".")
    if not path:
        return deepcopy(target_family)
    item_root_match = re.fullmatch(r"\[(?:item=)?([^\]]+)\]", path)
    if (
        item_root_match
        and isinstance(original_family, list)
        and isinstance(target_family, list)
    ):
        selector = item_root_match.group(1)
        original_index = _mutation_list_index(original_family, selector)
        target_index = _mutation_list_index(target_family, selector)
        if original_index is not None and (
            target_index is None or target_family[target_index] is None
        ):
            original_family.pop(original_index)
            return original_family
    claim_index_match = re.search(r"\[claim_index=(\d+)\]$", path)
    if claim_index_match:
        field_path = path[: claim_index_match.start()]
        original_text = _read_mutation_path(original_family, field_path)
        target_text = _read_mutation_path(target_family, field_path)
        index = int(claim_index_match.group(1))
        if not isinstance(original_text, str) or not isinstance(target_text, str):
            return original_family
        original_spans = _soft_copy_sentence_spans(original_text)
        target_sentences = soft_copy_material_sentences(target_text)
        if index >= len(original_spans):
            return original_family
        matcher = SequenceMatcher(
            a=soft_copy_material_sentences(original_text),
            b=target_sentences,
            autojunk=False,
        )
        target_spans = _soft_copy_sentence_spans(target_text)
        repaired_text = original_text
        for operation, old_start, old_end, new_start, new_end in matcher.get_opcodes():
            if operation == "equal":
                continue
            if old_start <= index < old_end:
                start = original_spans[old_start][0]
                end = original_spans[old_end - 1][1]
                replacement = (
                    target_text[
                        target_spans[new_start][0] : target_spans[new_end - 1][1]
                    ]
                    if new_start < new_end and len(target_spans) >= new_end
                    else ""
                )
                if new_start == new_end and end < len(original_text):
                    separator = re.match(r"\s+", original_text[end:])
                    end += len(separator.group(0)) if separator else 0
                elif new_start == new_end:
                    start = len(original_text[:start].rstrip())
                repaired_text = (
                    original_text[:start] + replacement + original_text[end:]
                )
                break
            if operation == "insert" and old_start == index and new_start < new_end:
                insertion = (
                    target_text[
                        target_spans[new_start][0] : target_spans[new_end - 1][1]
                    ]
                    if len(target_spans) >= new_end
                    else ""
                )
                insertion_at = (
                    original_spans[index][0]
                    if index < len(original_spans)
                    else len(original_text)
                )
                repaired_text = (
                    original_text[:insertion_at]
                    + insertion
                    + original_text[insertion_at:]
                )
                break
        if not field_path:
            return repaired_text
        return _write_mutation_path(original_family, field_path, repaired_text)
    return _write_mutation_path(
        original_family,
        path,
        _read_mutation_path(target_family, path),
    )


def _mutation_path_tokens(path: str) -> List[tuple[str, str | None]]:
    tokens: List[tuple[str, str | None]] = []
    for part in path.split("."):
        match = re.fullmatch(r"([^\[\]]+)(?:\[(?:item=)?([^\]]+)\])?", part)
        if match is None:
            return []
        tokens.append((match.group(1), match.group(2)))
    return tokens


def _resolve_mutation_child(value: Any, key: str, selector: str | None) -> Any:
    child = value.get(key) if isinstance(value, dict) else None
    if selector is None:
        return child
    if not isinstance(child, list):
        return None
    if selector.isdigit():
        index = int(selector)
        return child[index] if 0 <= index < len(child) else None
    matches = [
        item
        for item in child
        if isinstance(item, dict)
        and selector
        in {
            _s(item.get(field)).strip()
            for field in (
                "id",
                "insight_id",
                "key_figure_id",
                "claim_id",
                "evidence_id",
            )
        }
    ]
    return matches[0] if len(matches) == 1 else None


def _read_mutation_path(value: Any, path: str) -> Any:
    list_match = re.match(r"^\[(?:item=)?([^\]]+)\](?:\.(.*))?$", path)
    if list_match and isinstance(value, list):
        index = _mutation_list_index(value, list_match.group(1))
        if index is None:
            return None
        child = value[index]
        remainder = list_match.group(2)
        return child if remainder is None else _read_mutation_path(child, remainder)
    tokens = _mutation_path_tokens(path)
    current = value
    for key, selector in tokens:
        current = _resolve_mutation_child(current, key, selector)
    return current


def _write_mutation_path(value: Any, path: str, replacement: Any) -> Any:
    list_match = re.match(r"^\[(?:item=)?([^\]]+)\](?:\.(.*))?$", path)
    if list_match and isinstance(value, list):
        index = _mutation_list_index(value, list_match.group(1))
        if index is None:
            return value
        remainder = list_match.group(2)
        if remainder is None:
            value[index] = deepcopy(replacement)
        else:
            value[index] = _write_mutation_path(value[index], remainder, replacement)
        return value
    tokens = _mutation_path_tokens(path)
    if not tokens:
        return value
    current = value
    for key, selector in tokens[:-1]:
        current = _resolve_mutation_child(current, key, selector)
        if current is None:
            return value
    key, selector = tokens[-1]
    if selector is None:
        if isinstance(current, dict):
            current[key] = deepcopy(replacement)
        return value
    items = current.get(key) if isinstance(current, dict) else None
    if not isinstance(items, list):
        return value
    if selector.isdigit():
        index = int(selector)
        if 0 <= index < len(items):
            items[index] = deepcopy(replacement)
        return value
    matches = [
        index
        for index, item in enumerate(items)
        if isinstance(item, dict)
        and selector
        in {
            _s(item.get(field)).strip()
            for field in (
                "id",
                "insight_id",
                "key_figure_id",
                "claim_id",
                "evidence_id",
            )
        }
    ]
    if len(matches) == 1:
        items[matches[0]] = deepcopy(replacement)
    return value


def _mutation_list_index(values: List[Any], selector: str) -> int | None:
    if selector.isdigit():
        index = int(selector)
        return index if 0 <= index < len(values) else None
    matching = [
        index
        for index, item in enumerate(values)
        if isinstance(item, dict)
        and selector
        in {
            _s(item.get(field)).strip()
            for field in (
                "id",
                "insight_id",
                "key_figure_id",
                "claim_id",
                "evidence_id",
            )
        }
    ]
    return matching[0] if len(matching) == 1 else None


def _restore_final_insight_evidence_bindings(
    *,
    final_insights: List[Dict[str, Any]],
    candidate_insights: List[Dict[str, Any]],
    prior_final_insights: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Restore only a missing final-insight binding from the same stable ID.

    Regeneration intentionally lets the model rewrite final-insight editorial
    wording.  It must not, however, discard a retained evidence binding when
    the regenerated candidate (or the prior final insight) has the same stable
    identity.  Unknown or conflicting model-supplied IDs stay untouched for
    the normal grounding gate to reject.
    """
    binding_fields = ("evidence_id", "evidence", "evidence_spans", "pages")
    bindings: Dict[str, Dict[str, Any]] = {}
    # The just-regenerated candidate is the current source of truth; it
    # intentionally overrides a compatible prior final binding.
    for source in (prior_final_insights, candidate_insights):
        for insight in source:
            if not isinstance(insight, dict):
                continue
            insight_id = _s(insight.get("id")).strip()
            evidence_id = _s(insight.get("evidence_id")).strip()
            if not insight_id or not evidence_id:
                continue
            bindings[insight_id] = {
                field_name: deepcopy(insight[field_name])
                for field_name in binding_fields
                if field_name in insight
            }

    restored: List[Dict[str, Any]] = []
    for insight in final_insights:
        if not isinstance(insight, dict):
            continue
        repaired = dict(insight)
        insight_id = _s(repaired.get("id")).strip()
        if not _s(repaired.get("evidence_id")).strip() and insight_id in bindings:
            repaired.update(deepcopy(bindings[insight_id]))
        restored.append(repaired)
    return restored


def _restore_missing_final_insight_roster(
    *,
    selected_insights: List[Dict[str, Any]],
    prior_final_insights: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Keep a repaired final-insight roster one-to-one with prior stable IDs.

    A model can emit a duplicate ID while selecting a fixed-size final roster.
    If that displaces another prior material insight, the deterministic
    candidate gate correctly rejects the result for losing evidence continuity.
    Replace only duplicate or newly introduced IDs with the displaced prior
    item; explicit repairs for the first occurrence of a stable ID remain
    intact.
    """
    prior_by_id = {
        insight_id: deepcopy(item)
        for item in prior_final_insights
        if isinstance(item, dict)
        and (insight_id := _s(item.get("id")).strip())
        and _s(item.get("text")).strip()
    }
    if not prior_by_id:
        return selected_insights

    selected = [deepcopy(item) for item in selected_insights if isinstance(item, dict)]
    selected_ids = [_s(item.get("id")).strip() for item in selected]
    missing_ids = [
        insight_id for insight_id in prior_by_id if insight_id not in set(selected_ids)
    ]
    if not missing_ids:
        return selected

    replace_indexes = [
        index
        for index, insight_id in enumerate(selected_ids)
        if insight_id in selected_ids[:index] or insight_id not in prior_by_id
    ]
    for index, insight_id in zip(replace_indexes, missing_ids, strict=False):
        selected[index] = deepcopy(prior_by_id[insight_id])
    return selected


def _merge_regenerated_insights_by_stable_id(
    *,
    current_insights: List[Dict[str, Any]],
    regenerated_insights: List[Dict[str, Any]],
    append_new: bool = False,
) -> List[Dict[str, Any]]:
    """Promote only explicit stable-ID replacements during targeted repair."""

    replacements = {
        _s(item.get("id")).strip(): item
        for item in regenerated_insights
        if isinstance(item, dict) and _s(item.get("id")).strip()
    }
    merged: List[Dict[str, Any]] = []
    for current in current_insights:
        if not isinstance(current, dict):
            continue
        stable_id = _s(current.get("id")).strip()
        merged.append(deepcopy(replacements.get(stable_id, current)))
    if append_new:
        current_ids = {
            _s(item.get("id")).strip()
            for item in current_insights
            if isinstance(item, dict)
        }
        merged.extend(
            deepcopy(item)
            for item in regenerated_insights
            if isinstance(item, dict) and _s(item.get("id")).strip() not in current_ids
        )
    return merged


def _build_regeneration_state(
    *,
    safe_artifacts: Dict[str, Any],
    fallback_toc_bundle: Dict[str, Any],
    source_status: Dict[str, Any],
) -> _RegenerationState:
    toc_entries = normalize_artifact_toc_entries(safe_artifacts.get("toc_entries"))
    if not toc_entries:
        toc_entries = normalize_artifact_toc_entries(
            fallback_toc_bundle.get("toc_entries")
        )
    toc_topics = normalize_artifact_topics(safe_artifacts.get("toc_topics"))
    if not toc_topics:
        toc_topics = normalize_artifact_topics(fallback_toc_bundle.get("toc_topics"))
    topic_briefs = _copy_list(safe_artifacts.get("toc_topics_expanded"))
    if not topic_briefs:
        topic_briefs = _copy_list(fallback_toc_bundle.get("toc_topics_expanded"))
    soft_copy_evidence_selections = _retained_soft_copy_evidence_selections(
        safe_artifacts.get("_repair_evidence_selection")
    )
    raw_cache = safe_artifacts.get("_cache")
    raw_producing_identities = (
        raw_cache.get("producing_prompt_identities")
        if isinstance(raw_cache, dict)
        else None
    )
    raw_regeneration_requirements = (
        raw_cache.get("regeneration_prompt_requirements")
        if isinstance(raw_cache, dict)
        else None
    )
    return _RegenerationState(
        toc_entries=toc_entries,
        toc_topics=toc_topics,
        topic_briefs=topic_briefs,
        editorial_plan=normalize_artifact_editorial_plan(
            safe_artifacts.get("editorial_plan")
        ),
        summary=_copy_dict(safe_artifacts.get("summary")),
        insights_candidates=_copy_list(safe_artifacts.get("insights_candidates")),
        insights_final=_copy_list(safe_artifacts.get("insights_final")),
        quotes_final=_copy_list(safe_artifacts.get("quotes_final")),
        cover_semantics=_copy_dict(safe_artifacts.get("cover_semantics")),
        expert_comment=_s(safe_artifacts.get("expert_comment")),
        linkedin_post=_s(safe_artifacts.get("linkedin_post")),
        source_status=deepcopy(source_status),
        existing_soft_copy_claim_provenance=_copy_dict(
            safe_artifacts.get("soft_copy_claim_provenance")
        ),
        producing_prompt_identities={
            str(family): deepcopy(identity)
            for family, identity in raw_producing_identities.items()
            if isinstance(family, str) and isinstance(identity, dict)
        }
        if isinstance(raw_producing_identities, dict)
        else {},
        regeneration_prompt_requirements={
            str(family): str(namespace)
            for family, namespace in raw_regeneration_requirements.items()
            if isinstance(family, str) and isinstance(namespace, str)
        }
        if isinstance(raw_regeneration_requirements, dict)
        else {},
        soft_copy_evidence_selections=soft_copy_evidence_selections,
    )


def _retained_soft_copy_evidence_selections(value: object) -> Dict[str, Dict[str, Any]]:
    """Restore only private selection records with the retained audit shape."""

    if not isinstance(value, dict):
        return {}
    valid: Dict[str, Dict[str, Any]] = {}
    for key, selection in value.items():
        if not isinstance(key, str) or not valid_soft_copy_evidence_selection(
            key, selection
        ):
            continue
        valid[key] = deepcopy(selection)
    return valid


def _render_regeneration_model(
    *,
    execution: _RegenerationHandlerExecution,
    namespace: str,
    variables: Dict[str, Any],
    ctx: RunContext,
    repair_call: bool = True,
) -> Dict[str, Any]:
    request = execution.runtime.request
    openai_client = require_injected_model_client(
        execution.runtime.openai_client,
        scope="artifact_regeneration",
    )
    active_target = _active_repair_target(execution, variables)
    if repair_call:
        variables = {
            **variables,
            "repair_context_json": _dump_json(
                {
                    "allowed_paths": active_target.allowed_paths,
                    "repair_action": execution.target.repair_action,
                    "repair_strategy": execution.target.repair_strategy,
                    "quarantined_evidence_ids": list(
                        execution.target.quarantined_evidence_ids
                    ),
                    "failure_classes": sorted(
                        {
                            issue.rule_id
                            for issue in execution.target.issues
                            if issue.rule_id
                        }
                    ),
                    "required_protected_fields": _required_repair_protected_fields(
                        _current_repair_artifacts(execution.state), active_target
                    ),
                }
            ),
            "prior_repair_memory_json": _dump_json(
                _repair_memory_prompt_payload(request.repair_memory)
            ),
        }
    prepared = prepare_prompt_bundle(
        namespace=namespace,
        settings=request.settings,
        ctx=ctx,
        prompt_client=execution.runtime.prompt_client,
        system_variables=variables,
        user_variables=variables,
        retrieval_mode=(
            "vector_store"
            if execution.runtime.artifact_use_vector_store and request.vector_store_id
            else "chat_json"
        ),
        temperature=request.settings.temperature,
        seed=request.settings.openai_seed,
        timeout_seconds=request.settings.openai_timeout_seconds,
        output_contract_schema_version="artifact_json:1.0",
        validator_version="artifacts_schema:3.0",
    )
    identity = artifact_prompt_identity(
        prepared=prepared,
        relevant_input_hash=sha256_json(
            {
                "namespace": namespace,
                "variables": variables,
                "vector_store_id": request.vector_store_id
                if execution.runtime.artifact_use_vector_store
                else "",
            }
        ),
    )
    execution.state.prompt_identities[namespace] = identity
    artifact_family = artifact_family_for_producing_namespace(namespace)
    execution.state.producing_prompt_identities[artifact_family] = identity
    execution.state.regeneration_prompt_requirements[artifact_family] = namespace
    result = render_artifact_json_model(
        namespace=namespace,
        variables=variables,
        settings=request.settings,
        ctx=ctx,
        openai_client=openai_client,
        prompt_client=execution.runtime.prompt_client,
        allow_vector_store=execution.runtime.artifact_use_vector_store,
        vector_store_id=request.vector_store_id,
        publisher_name=request.publisher_name,
        report_name=request.report_name,
        source_url=request.source_url,
        prepared_prompt_bundle=prepared,
        response_contract_name=("regeneration_repair_decision" if repair_call else ""),
    )
    if not repair_call:
        return result
    call_grounding = variables.get("grounding_package_json")
    try:
        decision_grounding = json.loads(call_grounding) if call_grounding else None
    except (TypeError, ValueError):
        decision_grounding = None
    if not isinstance(decision_grounding, dict):
        decision_grounding = execution.grounding_package
    decision = _validated_repair_decision(
        result.get("repair_decision"),
        execution=execution,
        current_artifacts=_current_repair_artifacts(execution.state),
        grounding_package=decision_grounding,
        target=active_target,
    )
    patched_artifacts = _apply_repair_decision_patch(
        current_artifacts=_current_repair_artifacts(execution.state),
        decision=decision,
    )
    execution.state.repair_decisions.append(decision)
    root_key = {
        "report_vs/artifacts/regenerate/summary": "summary",
        "report_vs/artifacts/regenerate/insights_candidates": "insights_candidates",
        "report_vs/artifacts/regenerate/insights_final": "insights_final",
        "report_vs/artifacts/regenerate/quotes": "quotes_final",
        "report_vs/artifacts/regenerate/expert_comment": "expert_comment",
        "report_vs/artifacts/regenerate/linkedin_post": "linkedin_post",
    }.get(namespace)
    if not root_key or root_key not in patched_artifacts:
        raise _repair_decision_error(execution, "repair_patch_root_unresolved")
    claim_index_operation = next(
        (
            operation
            for operation in decision.minimal_patch
            if re.search(r"\[claim_index=\d+\]$", operation.path)
        ),
        None,
    )
    if claim_index_operation is not None and root_key in {
        "summary",
        "expert_comment",
        "linkedin_post",
    }:
        replacement = claim_index_operation.value
        if root_key == "summary":
            field = claim_index_operation.path.split(".", 1)[1].split("[", 1)[0]
            root_value: Any = {field: replacement}
        else:
            root_value = replacement
    else:
        root_value = patched_artifacts[root_key]
    return {
        root_key: root_value,
        "_soft_copy_claim_bindings": deepcopy(decision.claim_provenance),
        "_repair_decision": decision,
    }


def _active_repair_target(
    execution: _RegenerationHandlerExecution, variables: Dict[str, Any]
) -> RegenerationTarget:
    """Narrow multi-claim planner scope to the one claim in this provider call."""

    raw_scope = variables.get("claim_repair_scope_json")
    try:
        scope = json.loads(raw_scope) if raw_scope else {}
    except (TypeError, ValueError):
        scope = {}
    if not isinstance(scope, dict):
        return execution.target
    mode = scope.get("mode")
    paths = list(execution.target.allowed_paths)
    active_path = ""
    if mode == "claim":
        failed_claim = _s(scope.get("failed_claim")).strip()
        family = execution.target.target_section
        field = _s(scope.get("field")).strip()
        stable_paths = [
            path
            for path in paths
            if "[claim_index=" in path
            or ("[item=" in path and path.rsplit(".", 1)[-1] in {"text", "claim"})
        ]
        matches = []
        for path in stable_paths:
            found, value = _read_repair_path(
                _current_repair_artifacts(execution.state), path
            )
            if found and isinstance(value, str) and value.strip() == failed_claim:
                matches.append(path)
        if len(matches) == 1:
            active_path = matches[0]
        elif not matches and failed_claim:
            if family == "summary" and field in {
                "tldr",
                "card_tldr_compact",
                "executive_summary",
            }:
                base_path = f"summary.{field}"
                found, text = _read_repair_path(
                    _current_repair_artifacts(execution.state), base_path
                )
            elif family in {"expert_comment", "linkedin_post"}:
                base_path = family
                found, text = _read_repair_path(
                    _current_repair_artifacts(execution.state), base_path
                )
            else:
                base_path, found, text = "", False, ""
            sentence_matches = (
                [
                    (index, sentence)
                    for index, (_start, _end, sentence) in enumerate(
                        _soft_copy_sentence_spans(text)
                    )
                    if _normalized_soft_copy_text(sentence)
                    == _normalized_soft_copy_text(failed_claim)
                ]
                if found and isinstance(text, str)
                else []
            )
            candidate_path = (
                f"{base_path}[claim_index={sentence_matches[0][0]}]"
                if len(sentence_matches) == 1
                else ""
            )
            if candidate_path and any(
                candidate_path == allowed
                or candidate_path.startswith(allowed + ".")
                or candidate_path.startswith(allowed + "[")
                for allowed in paths
            ):
                active_path = candidate_path
    elif mode == "claim_map_item":
        claim_id = _s(scope.get("claim_id")).strip()
        matches = [
            path
            for path in paths
            if f"[item={claim_id}]" in path or f"[{claim_id}]" in path
        ]
        if len(matches) == 1:
            active_path = matches[0]
        elif not matches and claim_id:
            claims = execution.state.summary.get("claim_evidence_map")
            claims = claims if isinstance(claims, list) else []
            indexed_matches = [
                (index, claim)
                for index, claim in enumerate(claims)
                if isinstance(claim, dict)
                and claim_id
                in {
                    _s(claim.get("id")).strip(),
                    _s(claim.get("claim_id")).strip(),
                    str(index + 1),
                }
            ]
            fields_to_change = scope.get("fields_to_change")
            field = (
                _s(fields_to_change[0]).strip()
                if isinstance(fields_to_change, list) and fields_to_change
                else "claim"
            )
            if len(indexed_matches) == 1 and field == "claim":
                index, claim = indexed_matches[0]
                identity = _s(claim.get("id") or claim.get("claim_id")).strip()
                item_selector = f"item={identity}" if identity else str(index)
                candidate_path = f"summary.claim_evidence_map[{item_selector}].claim"
                if any(
                    candidate_path == allowed
                    or candidate_path.startswith(allowed + ".")
                    or candidate_path.startswith(allowed + "[")
                    for allowed in paths
                ):
                    active_path = candidate_path
    if not active_path:
        if mode in {"claim", "claim_map_item"}:
            raise _repair_decision_error(
                execution, "atomic_repair_target_unresolved_or_ambiguous"
            )
        return execution.target
    raw_grounding = variables.get("grounding_package_json")
    try:
        grounding = json.loads(raw_grounding) if raw_grounding else {}
    except (TypeError, ValueError):
        grounding = {}
    quarantined = (
        list(grounding.get("quarantined_evidence_ids", []))
        if isinstance(grounding, dict)
        else list(execution.target.quarantined_evidence_ids)
    )
    return replace(
        execution.target,
        allowed_paths=[active_path],
        quarantined_evidence_ids=quarantined,
    )


def _current_repair_artifacts(state: _RegenerationState) -> Dict[str, Any]:
    return {
        "summary": deepcopy(state.summary),
        "insights_candidates": deepcopy(state.insights_candidates),
        "insights_final": deepcopy(state.insights_final),
        "quotes_final": deepcopy(state.quotes_final),
        "expert_comment": state.expert_comment,
        "linkedin_post": state.linkedin_post,
    }


def _repair_memory_prompt_payload(memory) -> List[Dict[str, Any]]:
    """Return bounded, content-free retry memory for the next model call."""

    def identities(values) -> List[Dict[str, Any]]:
        return [
            {
                "fingerprint": item.key,
                "rule_id": item.rule_id,
                "affected_section": item.affected_section,
                "entity_id": item.entity_id,
                "evidence_ids": item.evidence_ids[:8],
            }
            for item in values[:8]
        ]

    return [
        {
            "resolved": identities(delta.resolved),
            "persisting": identities(delta.persisting),
            "introduced": identities(delta.introduced),
            "severity_changes": [
                {
                    "failure_fingerprint": item.failure_fingerprint,
                    "before": item.before,
                    "after": item.after,
                }
                for item in delta.severity_changes[:8]
            ],
            "mutation_scope_result": delta.mutation_scope_result,
            "evidence_lineage_result": delta.evidence_lineage_result,
            "repair_action": delta.repair_action,
            "repair_strategy": delta.repair_strategy,
            "strategy_fingerprint": delta.strategy_fingerprint,
            "evidence_ids_used": delta.evidence_ids_used[:8],
            "candidate_sha256": delta.candidate_sha256,
            "input_sha256": delta.input_sha256,
            "validator_identity": delta.validator_identity,
        }
        for delta in memory[-3:]
    ]


def _repair_decision_error(
    execution: _RegenerationHandlerExecution, reason: str
) -> AppError:
    return AppError(
        code="regeneration_repair_decision_invalid",
        message="Model repair decision or minimal patch failed deterministic validation.",
        retryable=False,
        context={
            "report_id": execution.runtime.request.report_id,
            "target_section": execution.target.target_section,
            "reason": reason,
        },
    )


def _validated_repair_decision(
    payload: object,
    *,
    execution: _RegenerationHandlerExecution,
    current_artifacts: Dict[str, Any],
    grounding_package: Dict[str, Any],
    target: RegenerationTarget | None = None,
) -> RepairDecision:
    if not isinstance(payload, dict):
        raise _repair_decision_error(execution, "decision_missing")
    try:
        raw_patch = payload["minimal_patch"]
        if not isinstance(raw_patch, list):
            raise TypeError("minimal_patch_not_array")
        patch = [
            RepairPatchOperation(
                op=str(item["op"]),
                path=str(item["path"]),
                value=deepcopy(item["value"]),
            )
            for item in raw_patch
            if isinstance(item, dict)
        ]
        if len(patch) != len(raw_patch):
            raise TypeError("minimal_patch_operation_invalid")
        decision = RepairDecision(
            schema_version=str(payload["schema_version"]),
            diagnosed_failure_class=str(payload["diagnosed_failure_class"]).strip(),
            repair_action=str(payload["repair_action"]).strip(),
            repair_strategy=str(payload["repair_strategy"]).strip(),
            evidence_ids_used=[
                str(value).strip() for value in payload["evidence_ids_used"]
            ],
            protected_fields=[
                str(value).strip() for value in payload["protected_fields"]
            ],
            changed_paths=[str(value).strip() for value in payload["changed_paths"]],
            minimal_patch=patch,
            claim_provenance=[
                dict(value)
                for value in payload["claim_provenance"]
                if isinstance(value, dict)
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _repair_decision_error(execution, "decision_contract_invalid") from exc

    target = target or execution.target
    failure_classes = {issue.rule_id for issue in target.issues if issue.rule_id}
    if decision.diagnosed_failure_class not in failure_classes:
        raise _repair_decision_error(execution, "failure_class_not_in_plan")
    if (
        decision.repair_action != target.repair_action
        or decision.repair_strategy != target.repair_strategy
    ):
        raise _repair_decision_error(execution, "strategy_not_in_plan")
    if not target.allowed_paths:
        raise _repair_decision_error(execution, "allowed_paths_missing")
    if not decision.minimal_patch or any(
        item.op != "replace" or not item.path for item in decision.minimal_patch
    ):
        raise _repair_decision_error(execution, "patch_operation_unsupported")
    operation_paths = [item.path for item in decision.minimal_patch]
    if len(operation_paths) != len(set(operation_paths)) or set(
        decision.changed_paths
    ) != set(operation_paths):
        raise _repair_decision_error(execution, "changed_paths_do_not_match_patch")
    if not decision.evidence_ids_used == list(
        dict.fromkeys(decision.evidence_ids_used)
    ):
        raise _repair_decision_error(execution, "duplicate_evidence_identity")
    package_ids = {
        str(value).strip()
        for value in grounding_package.get("evidence_ids", [])
        if str(value).strip()
    }
    quarantined = {
        str(value).strip()
        for value in (
            list(target.quarantined_evidence_ids)
            + list(grounding_package.get("quarantined_evidence_ids", []))
        )
        if str(value).strip()
    }
    if not set(decision.evidence_ids_used) <= package_ids or set(
        decision.evidence_ids_used
    ).intersection(quarantined):
        raise _repair_decision_error(execution, "evidence_not_retained_or_quarantined")
    for claim in decision.claim_provenance:
        if not set(claim.get("evidence_ids") or []) <= set(decision.evidence_ids_used):
            raise _repair_decision_error(execution, "claim_evidence_not_declared_used")

    required_protected = _required_repair_protected_fields(current_artifacts, target)
    if set(decision.protected_fields) != set(required_protected):
        raise _repair_decision_error(execution, "protected_fields_incomplete")
    candidate = deepcopy(current_artifacts)
    for operation in decision.minimal_patch:
        if not any(
            operation.path == allowed
            or operation.path.startswith(allowed + ".")
            or operation.path.startswith(allowed + "[")
            for allowed in target.allowed_paths
        ):
            raise _repair_decision_error(
                execution, "changed_path_outside_allowed_paths"
            )
        found, previous = _read_repair_path(candidate, operation.path)
        if not found:
            raise _repair_decision_error(
                execution, "patch_target_unresolved_or_ambiguous"
            )
        family_root_replacement = operation.path in target.allowed_paths and not any(
            "." in path or "[" in path for path in target.allowed_paths
        )
        if (
            isinstance(previous, (dict, list))
            and not operation.path.endswith(".metric")
            and not family_root_replacement
        ):
            raise _repair_decision_error(execution, "patch_target_not_atomic")
        if (
            isinstance(operation.value, (dict, list))
            and not operation.path.endswith(".metric")
            and not family_root_replacement
        ):
            raise _repair_decision_error(execution, "patch_value_over_broad")
        if not _write_repair_path(candidate, operation.path, operation.value):
            raise _repair_decision_error(execution, "patch_application_failed")
    if not _repair_protected_fields_preserved(
        before=current_artifacts, after=candidate, paths=required_protected
    ):
        raise _repair_decision_error(execution, "protected_field_changed")
    return decision


def _repair_protected_fields_preserved(
    *, before: Dict[str, Any], after: Dict[str, Any], paths: List[str]
) -> bool:
    claim_paths: Dict[str, List[int]] = {}
    exact_paths: List[str] = []
    for path in paths:
        match = re.fullmatch(r"(.+)\[claim_index=(\d+)\]", path)
        if match:
            base_path, raw_index = match.groups()
            claim_paths.setdefault(base_path, []).append(int(raw_index))
        else:
            exact_paths.append(path)
    for path in exact_paths:
        before_found, before_value = _read_repair_path(before, path)
        after_found, after_value = _read_repair_path(after, path)
        if not before_found or not after_found or before_value != after_value:
            return False
    for base_path, indices in claim_paths.items():
        before_found, before_text = _read_repair_path(before, base_path)
        after_found, after_text = _read_repair_path(after, base_path)
        if (
            not before_found
            or not after_found
            or not isinstance(before_text, str)
            or not isinstance(after_text, str)
        ):
            return False
        before_spans = _soft_copy_sentence_spans(before_text)
        after_spans = _soft_copy_sentence_spans(after_text)
        required_values = [
            before_text[start:end].strip()
            for index in indices
            if index < len(before_spans)
            for start, end, *_ in [before_spans[index]]
        ]
        candidate_values = [
            after_text[start:end].strip() for start, end, *_ in after_spans
        ]
        remaining = list(candidate_values)
        for expected in required_values:
            if expected not in remaining:
                return False
            remaining.remove(expected)
    return True


def _apply_repair_decision_patch(
    *, current_artifacts: Dict[str, Any], decision: RepairDecision
) -> Dict[str, Any]:
    """Apply only operations already proven legal against this promoted state."""

    patched = deepcopy(current_artifacts)
    for operation in decision.minimal_patch:
        if not _write_repair_path(patched, operation.path, operation.value):
            raise AppError(
                code="regeneration_repair_decision_invalid",
                message="Validated repair patch could not be applied to its target.",
                retryable=False,
                context={"reason": "patch_application_failed"},
            )
    return patched


def _required_repair_protected_fields(
    artifacts: Dict[str, Any], target: RegenerationTarget
) -> List[str]:
    protected: set[str] = set()
    for allowed in target.allowed_paths:
        claim_match = re.fullmatch(r"(.+)\[claim_index=(\d+)\]", allowed)
        if claim_match:
            base_path, raw_index = claim_match.groups()
            found, text = _read_repair_path(artifacts, base_path)
            if found and isinstance(text, str):
                for index in range(len(_soft_copy_sentence_spans(text))):
                    if index != int(raw_index):
                        protected.add(f"{base_path}[claim_index={index}]")
            summary = artifacts.get("summary")
            if base_path.startswith("summary.") and isinstance(summary, dict):
                field_name = base_path.split(".", 1)[1]
                protected.update(
                    f"summary.{key}" for key in summary if key != field_name
                )
            continue
        item_match = re.match(r"^([^\[]+\[[^\]]+\])(?:\.(.*))?$", allowed)
        if item_match:
            item_path, suffix = item_match.groups()
            found, item = _read_repair_path(artifacts, item_path)
            if not found or not isinstance(item, dict):
                continue
            mutable_fields = set()
            if suffix:
                mutable_fields.add(suffix.split(".", 1)[0])
            elif target.target_section == "quotes":
                mutable_fields.add("text")
            elif target.target_section == "insights_bundle":
                if target.repair_action == "REBIND_EVIDENCE":
                    mutable_fields.update(
                        {"evidence_id", "evidence", "evidence_spans", "pages"}
                    )
                else:
                    mutable_fields.update(
                        _insight_repair_field(issue.entity_id, issue.affected_section)
                        for issue in target.issues
                    )
            elif target.target_section == "summary":
                mutable_fields.update({"claim", "evidence_id", "evidence", "pages"})
            protected.update(
                f"{item_path}.{key}" for key in item if key not in mutable_fields
            )
            continue
        root, separator, suffix = allowed.partition(".")
        if separator and root == "summary":
            summary = artifacts.get("summary")
            mutable = {suffix.split(".", 1)[0]}
            if isinstance(summary, dict):
                protected.update(
                    f"summary.{key}" for key in summary if key not in mutable
                )
    return sorted(protected)


def _read_repair_path(value: Any, path: str) -> tuple[bool, Any]:
    claim_match = re.fullmatch(r"(.+)\[claim_index=(\d+)\]", path)
    if claim_match:
        base_path, raw_index = claim_match.groups()
        found, text = _read_repair_path(value, base_path)
        if not found or not isinstance(text, str):
            return False, None
        spans = _soft_copy_sentence_spans(text)
        index = int(raw_index)
        return (
            (True, text[spans[index][0] : spans[index][1]])
            if index < len(spans)
            else (False, None)
        )
    tokens = _mutation_path_tokens(path)
    if not tokens:
        return False, None
    current = value
    for key, selector in tokens:
        if not isinstance(current, dict) or key not in current:
            return False, None
        current = current[key]
        if selector is None:
            continue
        if not isinstance(current, list):
            return False, None
        if selector.isdigit():
            index = int(selector)
            if index >= len(current):
                return False, None
        else:
            matches = [
                index
                for index, item in enumerate(current)
                if isinstance(item, dict)
                and selector
                in {
                    _s(item.get(field)).strip()
                    for field in (
                        "id",
                        "insight_id",
                        "key_figure_id",
                        "claim_id",
                        "evidence_id",
                    )
                }
            ]
            if len(matches) != 1:
                return False, None
            index = matches[0]
        current = current[index]
    return True, current


def _write_repair_path(value: Dict[str, Any], path: str, replacement: Any) -> bool:
    claim_match = re.fullmatch(r"(.+)\[claim_index=(\d+)\]", path)
    if claim_match:
        base_path, raw_index = claim_match.groups()
        found, text = _read_repair_path(value, base_path)
        if not found or not isinstance(text, str) or not isinstance(replacement, str):
            return False
        spans = _soft_copy_sentence_spans(text)
        index = int(raw_index)
        if index >= len(spans):
            return False
        start, end = spans[index][:2]
        _write_mutation_path(value, base_path, text[:start] + replacement + text[end:])
        return True
    found, _ = _read_repair_path(value, path)
    if not found:
        return False
    _write_mutation_path(value, path, replacement)
    return True


def _normalize_state_evidence_ids(execution: _RegenerationHandlerExecution) -> None:
    normalize_artifact_evidence_ids(
        summary=execution.state.summary,
        insights_candidates=execution.state.insights_candidates,
        insights_final=execution.state.insights_final,
        quotes_final=execution.state.quotes_final,
        doc_map=execution.runtime.safe_doc_map,
        evidence_packs=execution.runtime.safe_evidence,
        editorial_plan=execution.state.editorial_plan,
        soft_copy_claim_provenance=execution.state.existing_soft_copy_claim_provenance,
    )


def _record_soft_copy_claim_bindings(
    execution: _RegenerationHandlerExecution,
    *,
    artifact_family: str,
    namespace: str,
    result: Dict[str, Any],
    repaired_claim: _SoftCopyClaimRepair | None = None,
    repaired_text: str = "",
) -> None:
    bindings = result.get("_soft_copy_claim_bindings")
    declared_bindings = (
        [dict(item) for item in bindings if isinstance(item, dict)]
        if isinstance(bindings, list)
        else []
    )
    if repaired_claim is not None:
        normalized_repaired = _normalized_soft_copy_text(repaired_text)
        repaired_claim_id = (
            f"soft_copy:{artifact_family}:"
            f"{hashlib.sha256(normalized_repaired.encode()).hexdigest()[:16]}"
        )
        if repaired_claim_id == repaired_claim.claim.claim_id:
            return
        declared_bindings = [
            item
            for item in align_soft_copy_claim_bindings_to_text(
                artifact_family=artifact_family,
                text=repaired_text,
                claim_bindings=declared_bindings,
            )
            if _normalized_soft_copy_text(item.get("claim")) == normalized_repaired
        ]
        if repaired_claim_id != repaired_claim.claim.claim_id:
            execution.state.replaced_soft_copy_claim_ids.setdefault(
                artifact_family, []
            ).append(repaired_claim.claim.claim_id)
            execution.state.soft_copy_repair_texts.setdefault(
                artifact_family, []
            ).append(repaired_text)
            execution.state.soft_copy_repair_lineage[
                f"{artifact_family}:{repaired_claim_id}"
            ] = repaired_claim.claim.claim_id
            selection = execution.state.soft_copy_evidence_selections.get(
                f"{artifact_family}:{repaired_claim.claim.claim_id}"
            )
            if isinstance(selection, dict):
                selection["repaired_claim_id"] = repaired_claim_id
    if repaired_claim is not None:
        execution.state.soft_copy_claim_bindings.setdefault(artifact_family, []).extend(
            declared_bindings
        )
    else:
        execution.state.soft_copy_claim_bindings[artifact_family] = declared_bindings
    execution.state.soft_copy_prompt_identities[artifact_family] = dict(
        execution.state.prompt_identities.get(namespace) or {}
    )
    execution.state.soft_copy_generation_attempts[artifact_family] = max(
        1, int(result.get("_soft_copy_generation_attempt") or 1)
    )
    if repaired_claim is None:
        _mark_soft_copy_family_replaced(execution, artifact_family)


def _mark_soft_copy_family_replaced(
    execution: _RegenerationHandlerExecution, artifact_family: str
) -> None:
    """Retire every prior provenance claim when a family is replaced or removed."""
    if artifact_family not in execution.state.replaced_soft_copy_families:
        execution.state.replaced_soft_copy_families.append(artifact_family)


def _normalized_soft_copy_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _valid_claim_replacement(
    *, artifact_family: str, text: str, bindings: object
) -> bool:
    """Accept only one newly bound sentence for a claim-scoped model reply."""

    sentences = soft_copy_material_sentences(text)
    if len(sentences) != 1:
        return False
    aligned = align_soft_copy_claim_bindings_to_text(
        artifact_family=artifact_family, text=text, claim_bindings=bindings
    )
    return any(
        _normalized_soft_copy_text(binding.get("claim")) == sentences[0]
        and binding.get("classification")
        in {"factual", "interpretive", "recommendation"}
        and (
            binding.get("classification") != "factual"
            or bool(binding.get("evidence_ids"))
        )
        for binding in aligned
    )


def _soft_copy_sentence_spans(text: str) -> List[tuple[int, int, str]]:
    """Return byte-preserving spans on the canonical provenance sentence grid."""

    fragments: List[tuple[int, int]] = []
    start = 0
    for separator in re.finditer(r"(?<=[.!?])\s+", text):
        end = separator.start()
        if _normalized_soft_copy_text(text[start:end]):
            fragments.append((start, end))
        start = separator.end()
    if (tail := text[start:]) and _normalized_soft_copy_text(tail):
        fragments.append((start, len(text)))
    sentences = soft_copy_material_sentences(text)
    spans: List[tuple[int, int, str]] = []
    cursor = 0
    for sentence in sentences:
        for end_index in range(cursor, len(fragments)):
            span_start = fragments[cursor][0]
            span_end = fragments[end_index][1]
            candidate = text[span_start:span_end]
            if _normalized_soft_copy_text(candidate) == sentence:
                spans.append((span_start, span_end, candidate))
                cursor = end_index + 1
                break
        else:
            return []
    return spans


# Keep one model decision per claim while supporting the largest retained
# multi-claim failure fixture (six distinct claims) without family rewrites.
MAX_SOFT_COPY_CLAIM_REPAIRS = 6


def _soft_copy_claim_repairs(
    execution: _RegenerationHandlerExecution,
    *,
    artifact_family: str,
    text: str,
    issues: List[RegenerationIssue] | None = None,
) -> List[_SoftCopyClaimRepair] | None:
    """Resolve every distinct, unambiguous failed sentence in one soft family."""

    target_issues = issues if issues is not None else execution.target.issues
    if not target_issues or not text:
        return None
    try:
        claims = soft_copy_claim_provenance_from_payload(
            execution.state.existing_soft_copy_claim_provenance
        )
    except AppError:
        return None
    claims_by_hash: Dict[str, List[SoftCopyClaimProvenance]] = {}
    for claim in claims:
        if claim.artifact_family == artifact_family:
            claims_by_hash.setdefault(claim.text_hash, []).append(claim)
    candidates: List[_SoftCopyClaimRepair] = []
    for start, end, sentence in _soft_copy_sentence_spans(text):
        matched_claims = claims_by_hash.get(
            hashlib.sha256(
                _normalized_soft_copy_text(sentence).encode("utf-8")
            ).hexdigest()
        )
        if matched_claims is None or len(matched_claims) != 1:
            return None
        candidates.append(
            _SoftCopyClaimRepair(
                artifact_family=artifact_family,
                claim=matched_claims[0],
                text=sentence,
                start=start,
                end=end,
                issue=target_issues[0],
            )
        )
    if not candidates:
        return None

    def uniquely_matched(
        values: List[_SoftCopyClaimRepair],
    ) -> _SoftCopyClaimRepair | None:
        return values[0] if len(values) == 1 else None

    resolved: List[_SoftCopyClaimRepair] = []
    for issue in target_issues:
        entity_id = str(issue.entity_id or "").strip()
        matched = (
            uniquely_matched(
                [
                    candidate
                    for candidate in candidates
                    if entity_id == candidate.claim.claim_id
                ]
            )
            if entity_id
            else None
        )
        if matched is None and entity_id:
            matched = uniquely_matched(
                [
                    candidate
                    for candidate in candidates
                    if entity_id == candidate.claim.text_hash
                ]
            )
        if matched is None:
            attributed = str(issue.affected_section or "").split(":", 1)
            attributed_text = (
                _normalized_soft_copy_text(attributed[1])
                if len(attributed) == 2
                else ""
            )
            message = str(issue.message or "")
            matched = uniquely_matched(
                [
                    candidate
                    for candidate in candidates
                    if (
                        attributed_text
                        and attributed_text
                        == _normalized_soft_copy_text(candidate.text)
                    )
                    or candidate.text in message
                ]
            )
        if matched is None:
            issue_evidence_ids = {
                str(evidence_id).strip().casefold()
                for evidence_id in issue.evidence_ids
                if str(evidence_id).strip()
            }
            matched = uniquely_matched(
                [
                    candidate
                    for candidate in candidates
                    if issue_evidence_ids
                    and issue_evidence_ids.intersection(
                        evidence_id.casefold()
                        for evidence_id in candidate.claim.evidence_ids
                    )
                ]
            )
        if matched is None:
            return None
        prior_index = next(
            (
                index
                for index, prior in enumerate(resolved)
                if prior.claim.claim_id == matched.claim.claim_id
            ),
            None,
        )
        if prior_index is not None:
            prior = resolved[prior_index]
            resolved[prior_index] = replace(prior, issues=prior.issues + (issue,))
            continue
        resolved.append(
            _SoftCopyClaimRepair(
                artifact_family=matched.artifact_family,
                claim=matched.claim,
                text=matched.text,
                start=matched.start,
                end=matched.end,
                issue=issue,
                issues=(issue,),
            )
        )
    return resolved if len(resolved) <= MAX_SOFT_COPY_CLAIM_REPAIRS else None


def _claim_has_repair_support(
    grounding_package: Dict[str, Any],
) -> bool:
    """A scoped repair proceeds only with its selected retained support."""

    return bool(grounding_package.get("relevant_evidence"))


def _uses_safe_removal(execution: _RegenerationHandlerExecution) -> bool:
    """A rejected strategy never earns another unsupported paraphrase."""

    return execution.target.repair_action in {"REMOVE_CLAIM", "ABSTAIN"}


def _replace_soft_copy_claim(
    text: str, repair: _SoftCopyClaimRepair, replacement: str
) -> str:
    return f"{text[: repair.start]}{replacement.strip()}{text[repair.end :]}"


def _remove_soft_copy_claim(text: str, repair: _SoftCopyClaimRepair) -> str:
    """Delete only the failed span and one adjacent separator when needed."""

    if repair.end < len(text):
        separator = re.match(r"\s+", text[repair.end :])
        end = repair.end + (len(separator.group(0)) if separator else 0)
        return f"{text[: repair.start]}{text[end:]}"
    prefix = text[: repair.start]
    return prefix.rstrip()


def _mark_soft_copy_claim_removed(
    execution: _RegenerationHandlerExecution, repair: _SoftCopyClaimRepair
) -> None:
    execution.state.replaced_soft_copy_claim_ids.setdefault(
        repair.artifact_family, []
    ).append(repair.claim.claim_id)


def _reconstruct_soft_copy_claims(
    text: str,
    repairs: List[_SoftCopyClaimRepair],
    replacements: Dict[str, str | None],
) -> str:
    """Apply original offsets right-to-left, preserving every untouched byte."""

    reconstructed = text
    for repair in sorted(repairs, key=lambda item: item.start, reverse=True):
        replacement = replacements.get(repair.claim.claim_id)
        reconstructed = (
            _remove_soft_copy_claim(reconstructed, repair)
            if replacement is None
            else _replace_soft_copy_claim(reconstructed, repair, replacement)
        )
    return reconstructed


def _summary_claim_repairs(
    execution: _RegenerationHandlerExecution,
) -> Dict[str, List[_SoftCopyClaimRepair]] | None:
    """Resolve all named summary-field claims, or retain family repair semantics."""

    fields = ("tldr", "card_tldr_compact", "executive_summary")
    grouped: Dict[str, List[RegenerationIssue]] = {}
    for issue in execution.target.issues:
        affected = str(issue.affected_section or "").casefold()
        field = next(
            (
                candidate
                for candidate in fields
                if affected in {candidate, f"summary.{candidate}"}
            ),
            "",
        )
        if not field:
            return None
        grouped.setdefault(field, []).append(issue)
    resolved: Dict[str, List[_SoftCopyClaimRepair]] = {}
    claim_ids: set[str] = set()
    for field, issues in grouped.items():
        repairs = _soft_copy_claim_repairs(
            execution,
            artifact_family="summary",
            text=_s(execution.state.summary.get(field)),
            issues=issues,
        )
        if repairs is None or any(
            repair.claim.claim_id in claim_ids for repair in repairs
        ):
            return None
        claim_ids.update(repair.claim.claim_id for repair in repairs)
        resolved[field] = repairs
    return resolved


def _summary_claim_map_targets(
    execution: _RegenerationHandlerExecution,
) -> List[tuple[int, Dict[str, Any], List[RegenerationIssue]]] | None:
    """Resolve every failed claim-map issue to one stable summary item."""

    claims = execution.state.summary.get("claim_evidence_map")
    if not isinstance(claims, list) or not execution.target.issues:
        return None
    grouped: Dict[int, List[RegenerationIssue]] = {}
    for issue in execution.target.issues:
        identity = ""
        entity_match = re.fullmatch(r"summary_claim:(.+)", _s(issue.entity_id).strip())
        affected_match = re.match(
            r"^summary\.claim_evidence_map:([^.:]+)",
            _s(issue.affected_section).strip(),
        )
        index_match = re.match(
            r"^summary(?:\.)?\.?(?:claim_evidence_map)\[(\d+)\]",
            _s(issue.affected_section).strip(),
        )
        if entity_match:
            identity = entity_match.group(1)
        elif affected_match:
            identity = affected_match.group(1)
        elif index_match:
            identity = str(int(index_match.group(1)) + 1)
        if not identity:
            return None
        matches = [
            index
            for index, claim in enumerate(claims)
            if isinstance(claim, dict)
            and identity
            in {
                _s(claim.get("id")).strip(),
                _s(claim.get("claim_id")).strip(),
                str(index + 1),
            }
        ]
        if len(matches) != 1:
            return None
        grouped.setdefault(matches[0], []).append(issue)
    return [(index, claims[index], issues) for index, issues in sorted(grouped.items())]


def _regenerate_summary_claim_map_items(
    execution: _RegenerationHandlerExecution,
    targets: List[tuple[int, Dict[str, Any], List[RegenerationIssue]]],
    namespace: str,
) -> None:
    claims = execution.state.summary.get("claim_evidence_map") or []
    if _uses_safe_removal(execution):
        removed = {index for index, _claim, _issues in targets}
        execution.state.summary["claim_evidence_map"] = [
            claim for index, claim in enumerate(claims) if index not in removed
        ]
        execution.state.regenerated_sections.append("summary")
        return
    for index, claim, issues in targets:
        grounding_package = execution.grounding_package
        if not grounding_package.get("evidence_ids"):
            raise AppError(
                code="regeneration_target_item_no_retained_evidence",
                message=(
                    "Targeted summary claim repair has no retained evidence "
                    "available for grounding."
                ),
                retryable=False,
                context={"report_id": execution.runtime.request.report_id},
            )
        result = _render_regeneration_model(
            execution=execution,
            namespace=namespace,
            ctx=execution.target_ctx,
            variables={
                **execution.runtime.base_vars,
                "attempt_index": execution.runtime.request.attempt_index,
                "target_section": execution.target.target_section,
                "current_section_json": _dump_json({"claim_evidence_map": [claim]}),
                "claim_repair_scope_json": _dump_json(
                    {
                        "mode": "claim_map_item",
                        "claim_id": _s(
                            claim.get("id") or claim.get("claim_id") or index + 1
                        ),
                        "fields_to_change": ["claim"],
                        "preserve_sibling_claims": True,
                    }
                ),
                "failure_reasons_json": _issues_json(issues),
                "fix_checklist_json": _fix_checklist_json(execution.target),
                "grounding_package_json": _dump_json(grounding_package),
                "editorial_plan_json": _dump_json(execution.state.editorial_plan),
            },
        )
        repaired_summary = result.get("summary")
        repaired_items = (
            repaired_summary.get("claim_evidence_map")
            if isinstance(repaired_summary, dict)
            else None
        )
        if not isinstance(repaired_items, list) or not repaired_items:
            raise AppError(
                code="regeneration_target_item_unresolved",
                message="Targeted summary claim repair returned no claim item.",
                retryable=False,
                context={"report_id": execution.runtime.request.report_id},
            )
        stable_id = _s(claim.get("id") or claim.get("claim_id")).strip()
        matching = [
            item
            for item in repaired_items
            if isinstance(item, dict)
            and (
                not stable_id
                or _s(item.get("id") or item.get("claim_id")).strip() == stable_id
            )
        ]
        if len(matching) != 1:
            raise AppError(
                code="regeneration_target_item_unresolved",
                message="Targeted summary claim repair returned an ambiguous item.",
                retryable=False,
                context={"report_id": execution.runtime.request.report_id},
            )
        repaired_text = _s(matching[0].get("claim")).strip()
        if not repaired_text or repaired_text == _s(claim.get("claim")).strip():
            raise AppError(
                code="regeneration_target_item_unresolved",
                message="Targeted summary claim repair did not change the failed claim.",
                retryable=False,
                context={"report_id": execution.runtime.request.report_id},
            )
        claims[index] = {**claim, "claim": repaired_text}
    execution.state.regenerated_sections.append("summary")
    execution.state.prompt_namespaces.append(namespace)


def _handle_summary_regeneration(execution: _RegenerationHandlerExecution) -> None:
    namespace = execution.handler.prompt_namespaces[0]
    claim_map_targets = _summary_claim_map_targets(execution)
    if claim_map_targets is not None:
        _regenerate_summary_claim_map_items(execution, claim_map_targets, namespace)
        return
    scoped_repairs = _summary_claim_repairs(execution)
    if scoped_repairs is not None:
        for field, repairs in scoped_repairs.items():
            replacements: Dict[str, str | None] = {}
            for repair in repairs:
                if _uses_safe_removal(execution):
                    replacements[repair.claim.claim_id] = None
                    _mark_soft_copy_claim_removed(execution, repair)
                    continue
                claim_grounding = _claim_scoped_grounding_package(execution, repair)
                if not _claim_has_repair_support(claim_grounding):
                    replacements[repair.claim.claim_id] = None
                    _mark_soft_copy_claim_removed(execution, repair)
                    continue
                selected_evidence_ids = set(claim_grounding["evidence_ids"])
                result = _render_regeneration_model(
                    execution=execution,
                    namespace=namespace,
                    ctx=execution.target_ctx,
                    variables={
                        **execution.runtime.base_vars,
                        "attempt_index": execution.runtime.request.attempt_index,
                        "target_section": execution.target.target_section,
                        "current_section_json": _dump_json(execution.state.summary),
                        "claim_repair_scope_json": _dump_json(
                            {
                                "mode": "claim",
                                "field": field,
                                "failed_claim": repair.text,
                                "preserve_sibling_claims": True,
                            }
                        ),
                        "failure_reasons_json": _issues_json(repair.issues),
                        "fix_checklist_json": _fix_checklist_json(execution.target),
                        "grounding_package_json": _dump_json(claim_grounding),
                        "editorial_plan_json": _dump_json(
                            _claim_scoped_editorial_plan(
                                execution.state.editorial_plan, selected_evidence_ids
                            )
                        ),
                    },
                )
                repaired_summary = result.get("summary")
                repaired_text = (
                    _s(repaired_summary.get(field))
                    if isinstance(repaired_summary, dict)
                    else ""
                )
                if not _valid_claim_replacement(
                    artifact_family="summary",
                    text=repaired_text,
                    bindings=result.get("_soft_copy_claim_bindings"),
                ):
                    replacements[repair.claim.claim_id] = None
                    _mark_soft_copy_claim_removed(execution, repair)
                    continue
                _record_soft_copy_claim_bindings(
                    execution,
                    artifact_family="summary",
                    namespace=namespace,
                    result=result,
                    repaired_claim=repair,
                    repaired_text=repaired_text,
                )
                replacements[repair.claim.claim_id] = repaired_text
            execution.state.summary[field] = _reconstruct_soft_copy_claims(
                _s(execution.state.summary.get(field)), repairs, replacements
            )
        execution.state.regenerated_sections.append("summary")
        execution.state.prompt_namespaces.append(namespace)
        return
    if _uses_safe_removal(execution):
        for field in ("tldr", "card_tldr_compact", "executive_summary"):
            if field in execution.state.summary:
                execution.state.summary[field] = ""
        _mark_soft_copy_family_replaced(execution, "summary")
        execution.state.regenerated_sections.append("summary")
        return
    result = _render_regeneration_model(
        execution=execution,
        namespace=namespace,
        ctx=execution.target_ctx,
        variables={
            **execution.runtime.base_vars,
            "attempt_index": execution.runtime.request.attempt_index,
            "target_section": execution.target.target_section,
            "current_section_json": _dump_json(execution.state.summary),
            "claim_repair_scope_json": _dump_json({"mode": "family"}),
            "failure_reasons_json": _issues_json(execution.target.issues),
            "fix_checklist_json": _fix_checklist_json(execution.target),
            "grounding_package_json": _dump_json(execution.grounding_package),
            "editorial_plan_json": _dump_json(execution.state.editorial_plan),
        },
    )
    if not _record_atomic_summary_claim_bindings(
        execution, namespace=namespace, result=result
    ):
        _record_soft_copy_claim_bindings(
            execution,
            artifact_family="summary",
            namespace=namespace,
            result=result,
        )
    execution.state.summary = normalize_artifact_summary(result.get("summary"))
    execution.state.regenerated_sections.append("summary")
    execution.state.prompt_namespaces.append(namespace)


def _record_atomic_summary_claim_bindings(
    execution: _RegenerationHandlerExecution,
    *,
    namespace: str,
    result: Dict[str, Any],
) -> bool:
    """Retain unchanged summary claims around a field-scoped model patch."""

    decision = result.get("_repair_decision")
    repaired_summary = result.get("summary")
    if not isinstance(decision, RepairDecision) or not isinstance(
        repaired_summary, dict
    ):
        return False
    patch_operations = [
        operation
        for operation in decision.minimal_patch
        if operation.path
        in {
            "summary.tldr",
            "summary.card_tldr_compact",
            "summary.executive_summary",
        }
        and isinstance(operation.value, str)
    ]
    if not patch_operations:
        return False
    declared_bindings = result.get("_soft_copy_claim_bindings")
    if not isinstance(declared_bindings, list) or not declared_bindings:
        return False

    public_sentences = set(
        soft_copy_material_sentences(soft_copy_public_text("summary", repaired_summary))
    )
    retained_claims = soft_copy_claim_provenance_from_payload(
        execution.state.existing_soft_copy_claim_provenance
    )
    # Hashes in the retained contract are over normalized sentence text. Derive
    # the live hashes and retire only prior claims no longer present anywhere in
    # the public summary family.
    public_hashes = {
        hashlib.sha256(_normalized_soft_copy_text(sentence).encode("utf-8")).hexdigest()
        for sentence in public_sentences
    }
    stale_claim_ids = [
        claim.claim_id
        for claim in retained_claims
        if claim.artifact_family == "summary" and claim.text_hash not in public_hashes
    ]
    replaced_claim_ids = execution.state.replaced_soft_copy_claim_ids.setdefault(
        "summary", []
    )
    replaced_claim_ids.extend(
        claim_id for claim_id in stale_claim_ids if claim_id not in replaced_claim_ids
    )
    execution.state.soft_copy_claim_bindings.setdefault("summary", []).extend(
        dict(binding) for binding in declared_bindings if isinstance(binding, dict)
    )
    execution.state.soft_copy_prompt_identities["summary"] = dict(
        execution.state.prompt_identities.get(namespace) or {}
    )
    execution.state.soft_copy_generation_attempts["summary"] = max(
        1, int(result.get("_soft_copy_generation_attempt") or 1)
    )
    execution.state.soft_copy_repair_texts.setdefault("summary", []).extend(
        operation.value.strip()
        for operation in patch_operations
        if operation.value.strip()
    )
    return True


def _handle_topics_regeneration(execution: _RegenerationHandlerExecution) -> None:
    toc_bundle = build_toc_artifacts(doc_map=execution.runtime.safe_doc_map)
    execution.state.toc_entries = normalize_artifact_toc_entries(
        toc_bundle.get("toc_entries")
    )
    execution.state.toc_topics = normalize_artifact_topics(toc_bundle.get("toc_topics"))
    execution.state.topic_briefs = _copy_list(toc_bundle.get("toc_topics_expanded"))
    execution.state.regenerated_sections.extend(
        ["toc_entries", "toc_topics", "toc_topics_expanded"]
    )


_INSIGHT_METRIC_PROVENANCE_FIELDS = (
    "label",
    "value",
    "unit",
    "trend",
    "timeframe",
    "geography",
    "segment",
    "sample_size",
    "confidence",
    "subject",
    "cohort",
    "denominator",
    "observation_status",
)
_INSIGHT_EVIDENCE_BINDING_FIELDS = (
    "evidence_id",
    "evidence",
    "evidence_spans",
    "pages",
)


def _restore_failed_insight_metrics_deterministically(
    execution: _RegenerationHandlerExecution,
) -> bool:
    """Copy protected insight metric fields from their retained binding.

    A final insight whose protected metric fields or evidence binding drifted
    from one uniquely retained same-stable-ID candidate is repaired by copying
    those canonical fields. Ambiguous identity or missing source fields keep
    the generative path.
    """

    if execution.target.repair_action != "CORRECT_PROTECTED_FACT":
        return False
    retained_by_id: Dict[str, List[Dict[str, Any]]] = {}
    for insight in execution.state.insights_candidates:
        if not isinstance(insight, dict):
            continue
        insight_id = _s(insight.get("id")).strip()
        metric = insight.get("metric")
        if insight_id and isinstance(metric, dict) and _s(metric.get("value")).strip():
            retained_by_id.setdefault(insight_id, []).append(insight)
    corrected_any = False
    for issue in execution.target.issues:
        insight_id = failed_insight_id(issue.entity_id, issue.affected_section)
        if not insight_id:
            return False
        target_matches = [
            insight
            for insight in execution.state.insights_final
            if isinstance(insight, dict) and _s(insight.get("id")).strip() == insight_id
        ]
        retained_matches = retained_by_id.get(insight_id, [])
        if len(target_matches) != 1 or len(retained_matches) != 1:
            return False
        target_insight = target_matches[0]
        retained = retained_matches[0]
        current_metric = target_insight.get("metric")
        current_metric = current_metric if isinstance(current_metric, dict) else {}
        retained_metric = retained.get("metric")
        retained_metric = retained_metric if isinstance(retained_metric, dict) else {}
        drifted = any(
            _s(current_metric.get(field_name)).strip()
            != _s(retained_metric.get(field_name)).strip()
            for field_name in _INSIGHT_METRIC_PROVENANCE_FIELDS
            if _s(retained_metric.get(field_name)).strip()
        )
        binding_drifted = any(
            retained.get(field_name) != target_insight.get(field_name)
            for field_name in _INSIGHT_EVIDENCE_BINDING_FIELDS
            if field_name in retained
        )
        if not drifted and not binding_drifted:
            continue
        if drifted:
            target_insight["metric"] = {
                **current_metric,
                **{
                    field_name: deepcopy(retained_metric.get(field_name, ""))
                    for field_name in _INSIGHT_METRIC_PROVENANCE_FIELDS
                    if field_name in retained_metric
                },
            }
        for field_name in _INSIGHT_EVIDENCE_BINDING_FIELDS:
            if field_name in retained:
                target_insight[field_name] = deepcopy(retained[field_name])
        evidence_id = _s(retained.get("evidence_id")).strip()
        if evidence_id:
            target_insight["evidence_id"] = evidence_id
            execution.state.selected_evidence_ids.append(evidence_id)
        corrected_any = True
    if not corrected_any:
        return False
    execution.state.deterministic_repairs.append("canonical_metric_copy")
    execution.state.regenerated_sections.append("insights_final")
    logger.info(
        log_event(
            execution.target_ctx,
            role="generator",
            event="artifact_regeneration_insight_metrics_copied",
            module=logger.name,
            fields={
                "report_id": execution.runtime.request.report_id,
                "model_calls": 0,
            },
        )
    )
    return True


def _handle_insights_bundle_regeneration(
    execution: _RegenerationHandlerExecution,
) -> None:
    if _uses_safe_removal(execution):
        _remove_failed_insight_with_retained_replacement(execution)
        return
    if _restore_failed_insight_metrics_deterministically(execution):
        return
    candidates_namespace, final_namespace = execution.handler.prompt_namespaces
    if _regenerate_one_final_insight(execution, final_namespace):
        return
    prior_final_insights = deepcopy(execution.state.insights_final)
    candidates_ctx = child_context(
        execution.target_ctx, task_id=f"{execution.target_ctx.task_id}:candidates"
    )
    candidates_result = _render_regeneration_model(
        execution=execution,
        namespace=candidates_namespace,
        ctx=candidates_ctx,
        variables={
            **execution.runtime.base_vars,
            "attempt_index": execution.runtime.request.attempt_index,
            "target_section": execution.target.target_section,
            "current_section_json": _dump_json(execution.state.insights_candidates),
            "failure_reasons_json": _issues_json(execution.target.issues),
            "fix_checklist_json": _fix_checklist_json(execution.target),
            "grounding_package_json": _dump_json(execution.grounding_package),
            "editorial_plan_json": _dump_json(execution.state.editorial_plan),
        },
    )
    target_count = max(
        REQUIRED_REPORT_PAYLOAD_INSIGHTS,
        len(execution.state.editorial_plan["themes"]),
    )
    regenerated_candidates = normalize_artifact_insights(
        candidates_result.get("insights_candidates"),
        prefix="candidate",
    )
    execution.state.insights_candidates = _merge_regenerated_insights_by_stable_id(
        current_insights=execution.state.insights_candidates,
        regenerated_insights=regenerated_candidates,
        append_new=True,
    )
    execution.state.insights_candidates = select_artifact_insights(
        final_insights=execution.state.insights_candidates,
        candidate_insights=fallback_artifact_insights_from_findings(
            execution.runtime.safe_evidence.get("findings"), limit=target_count
        ),
        editorial_plan=execution.state.editorial_plan,
    )
    final_ctx = child_context(
        execution.target_ctx, task_id=f"{execution.target_ctx.task_id}:final"
    )
    final_result = _render_regeneration_model(
        execution=execution,
        namespace=final_namespace,
        ctx=final_ctx,
        variables={
            **execution.runtime.base_vars,
            "attempt_index": execution.runtime.request.attempt_index,
            "target_section": execution.target.target_section,
            "current_section_json": _dump_json(execution.state.insights_final),
            "insights_candidates_json": _dump_json(execution.state.insights_candidates),
            "failure_reasons_json": _issues_json(execution.target.issues),
            "fix_checklist_json": _fix_checklist_json(execution.target),
            "grounding_package_json": _dump_json(execution.grounding_package),
            "editorial_plan_json": _dump_json(execution.state.editorial_plan),
            "final_insight_target_count": target_count,
        },
    )
    regenerated_final = _restore_final_insight_evidence_bindings(
        final_insights=normalize_artifact_insights(
            final_result.get("insights_final"), prefix="insight"
        ),
        candidate_insights=execution.state.insights_candidates,
        prior_final_insights=execution.state.insights_final,
    )
    execution.state.insights_final = _merge_regenerated_insights_by_stable_id(
        current_insights=execution.state.insights_final,
        regenerated_insights=regenerated_final,
    )
    execution.state.insights_final = _restore_missing_final_insight_roster(
        selected_insights=select_artifact_insights(
            final_insights=execution.state.insights_final,
            candidate_insights=execution.state.insights_candidates,
            editorial_plan=execution.state.editorial_plan,
        ),
        prior_final_insights=prior_final_insights,
    )
    execution.state.regenerated_sections.extend(
        ["insights_candidates", "insights_final"]
    )
    execution.state.prompt_namespaces.extend([candidates_namespace, final_namespace])


def _regenerate_one_final_insight(
    execution: _RegenerationHandlerExecution, namespace: str
) -> bool:
    """Regenerate only a uniquely identified final insight and its failed fields."""

    insight_ids = {
        failed_insight_id(issue.entity_id, issue.affected_section)
        for issue in execution.target.issues
    }
    insight_ids.discard("")
    if len(insight_ids) != 1:
        return False
    insight_id = next(iter(insight_ids))
    matches = [
        (index, item)
        for index, item in enumerate(execution.state.insights_final)
        if isinstance(item, dict) and _s(item.get("id")).strip() == insight_id
    ]
    if len(matches) != 1:
        return False
    index, original = matches[0]
    requested_fields = {
        field
        for issue in execution.target.issues
        if (field := _insight_repair_field(issue.entity_id, issue.affected_section))
    }
    if not requested_fields:
        return False
    candidate = next(
        (
            item
            for item in execution.state.insights_candidates
            if isinstance(item, dict) and _s(item.get("id")).strip() == insight_id
        ),
        None,
    )
    selected_evidence_ids = {
        _s(value).strip()
        for issue in execution.target.issues
        for value in issue.evidence_ids
        if _s(value).strip()
    }
    claim_fields = {
        "text": ["text"],
        "metric": ["metric"],
    }
    mutable_fields = {
        field_name
        for field in requested_fields
        for field_name in claim_fields.get(field, [])
    }
    if execution.target.repair_action == "REBIND_EVIDENCE":
        mutable_fields.update({"evidence_id", "evidence", "evidence_spans", "pages"})
    result = _render_regeneration_model(
        execution=execution,
        namespace=namespace,
        ctx=execution.target_ctx,
        variables={
            **execution.runtime.base_vars,
            "attempt_index": execution.runtime.request.attempt_index,
            "target_section": execution.target.target_section,
            "current_section_json": _dump_json([original]),
            "insights_candidates_json": _dump_json([candidate] if candidate else []),
            "failure_reasons_json": _issues_json(execution.target.issues),
            "fix_checklist_json": _fix_checklist_json(execution.target),
            "grounding_package_json": _dump_json(execution.grounding_package),
            "editorial_plan_json": _dump_json(
                _claim_scoped_editorial_plan(
                    execution.state.editorial_plan, selected_evidence_ids
                )
            ),
            "final_insight_target_count": 1,
        },
    )
    regenerated = normalize_artifact_insights(
        result.get("insights_final"), prefix="insight"
    )
    matching = [
        item for item in regenerated if _s(item.get("id")).strip() == insight_id
    ]
    if not matching and len(regenerated) == 1:
        matching = regenerated
    if len(matching) != 1:
        raise AppError(
            code="regeneration_target_item_unresolved",
            message="Atomic insight regeneration did not return its stable target.",
            retryable=False,
            context={"report_id": execution.runtime.request.report_id},
        )
    repaired = deepcopy(original)
    for field_name in mutable_fields:
        if field_name in matching[0]:
            repaired[field_name] = deepcopy(matching[0][field_name])
    repaired["id"] = insight_id
    if not any(repaired.get(name) != original.get(name) for name in mutable_fields):
        raise AppError(
            code="regeneration_target_item_unchanged",
            message="Atomic insight regeneration did not change its declared field.",
            retryable=False,
            context={"report_id": execution.runtime.request.report_id},
        )
    execution.state.insights_final[index] = repaired
    execution.state.regenerated_sections.append("insights_final")
    execution.state.prompt_namespaces.append(namespace)
    return True


def _insight_repair_field(entity_id: str, affected_section: str) -> str:
    parts = str(entity_id or "").split(":")
    if len(parts) >= 3 and parts[0] == "insight" and parts[2] in {"text", "metric"}:
        return parts[2]
    affected = str(affected_section or "").casefold()
    match = re.search(r"\.(text|metric)(?:\.|$)", affected)
    if match:
        return match.group(1)
    suffix = affected.rsplit(":", 1)[-1]
    return suffix if suffix in {"text", "metric"} else ""


def _remove_failed_insight_with_retained_replacement(
    execution: _RegenerationHandlerExecution,
) -> None:
    """Remove one failed stable ID and fill its slot from retained source copy."""

    failed_ids = {
        failed_insight_id(issue.entity_id, issue.affected_section)
        for issue in execution.target.issues
    }
    failed_ids.discard("")
    final_ids = {
        _s(item.get("id")).strip()
        for item in execution.state.insights_final
        if isinstance(item, dict)
    }
    if len(failed_ids) != 1 or not failed_ids <= final_ids:
        raise AppError(
            code="insight_safe_removal_target_unresolved",
            message="Safe removal requires one existing failed final insight ID.",
            retryable=False,
            context={"report_id": execution.runtime.request.report_id},
        )
    failed_id = next(iter(failed_ids))
    retained_final = [
        deepcopy(item)
        for item in execution.state.insights_final
        if isinstance(item, dict) and _s(item.get("id")).strip() != failed_id
    ]
    retained_candidates = [
        deepcopy(item)
        for item in execution.state.insights_candidates
        if isinstance(item, dict) and _s(item.get("id")).strip() != failed_id
    ]
    target_count = max(
        REQUIRED_REPORT_PAYLOAD_INSIGHTS,
        len(execution.state.editorial_plan["themes"]),
    )
    evidence_by_id = _retained_evidence_entries_by_id(
        execution.runtime.safe_evidence, execution.runtime.safe_doc_map
    )
    pool = [
        *retained_candidates,
        *fallback_artifact_insights_from_findings(
            execution.runtime.safe_evidence.get("findings"), limit=target_count * 2
        ),
    ]
    selected = retained_final
    replacement = None
    if len(selected) < target_count:
        occupied_ids = {_s(item.get("id")).strip() for item in selected}
        for candidate in pool:
            candidate_id = _s(candidate.get("id")).strip()
            evidence_id = _normalized_evidence_id(candidate.get("evidence_id"))
            if (
                not candidate_id
                or candidate_id == failed_id
                or candidate_id in occupied_ids
                or not _s(candidate.get("text")).strip()
                or not _s(candidate.get("evidence")).strip()
                or evidence_id not in evidence_by_id
            ):
                continue
            support = evidence_by_id[evidence_id]
            support_pages = set(support.get("pages") or [])
            candidate_pages = set(candidate.get("pages") or [])
            if support_pages and (
                not candidate_pages or not candidate_pages <= support_pages
            ):
                continue
            candidate_metric = candidate.get("metric")
            metric: Dict[str, Any] = (
                candidate_metric if isinstance(candidate_metric, dict) else {}
            )
            compatible = rank_compatible_alternatives(
                CompatibilityQuery(
                    text=_s(candidate.get("text")),
                    metric=metric,
                    pages=tuple(candidate_pages),
                ),
                [
                    (
                        evidence_id,
                        {"text": candidate["evidence"], "pages": list(candidate_pages)},
                    )
                ],
                limit=1,
            )
            if not compatible:
                continue
            proposed = select_artifact_insights(
                final_insights=[*retained_final, candidate],
                candidate_insights=[],
                editorial_plan=execution.state.editorial_plan,
            )
            if len(proposed) != target_count or candidate_id not in {
                _s(item.get("id")).strip() for item in proposed
            }:
                continue
            quality = evaluate_public_editorial_quality(
                report_id=execution.runtime.request.report_id,
                artifacts={"insights_final": proposed},
            )
            if any(
                issue.affected_artifact == "insights_final" for issue in quality.issues
            ):
                continue
            selected = proposed
            replacement = deepcopy(candidate)
            break
        if replacement is None:
            raise AppError(
                code="insight_safe_removal_no_replacement",
                message=(
                    "No distinct supported retained insight can fill the removed "
                    "final slot."
                ),
                retryable=False,
                context={
                    "report_id": execution.runtime.request.report_id,
                    "insight_id": failed_id,
                },
            )
    execution.state.insights_candidates = retained_candidates
    if replacement is not None and _s(replacement.get("id")).strip() not in {
        _s(item.get("id")).strip() for item in retained_candidates
    }:
        execution.state.insights_candidates.append(replacement)
    execution.state.insights_final = selected
    execution.state.regenerated_sections.extend(
        ["insights_candidates", "insights_final"]
    )
    execution.state.deterministic_repairs.append("safe_removal")
    logger.info(
        log_event(
            execution.target_ctx,
            role="generator",
            event="artifact_regeneration_insight_removed",
            module=logger.name,
            fields={
                "report_id": execution.runtime.request.report_id,
                "removed_insight_id": failed_id,
                "replacement_insight_id": _s(replacement.get("id"))
                if replacement
                else "",
                "model_calls": 0,
            },
        )
    )


def _handle_report_identity_regeneration(
    execution: _RegenerationHandlerExecution,
) -> None:
    """Repair report identity from canonical source identity without a model.

    A metadata.title/metadata.publisher grounding failure is uniquely
    source-provable: the retained doc map already carries the deterministically
    resolved canonical source title and publisher. Copying that value is the
    cheapest safe repair; broad regeneration of unrelated families is never
    justified by an identity mismatch.
    """

    identity = _public_report_identity(execution.runtime.safe_doc_map)
    if execution.target.repair_action != "COPY_CANONICAL_SOURCE_VALUE":
        # The deterministic correction was already rejected for this failure
        # fingerprint: abstain under the planned terminal strategy instead of
        # repeating the same correction under another nominal label.
        execution.state.deterministic_repairs.append(
            execution.target.repair_strategy or "canonical_identity_abstained"
        )
        execution.state.regenerated_sections.append("report_identity")
        return
    wanted_fields = {
        str(issue.affected_section or "").strip().lower().removeprefix("metadata.")
        for issue in execution.target.issues
    }
    resolved: Dict[str, Any] = {}
    for field_name in ("title", "publisher"):
        if wanted_fields and field_name not in wanted_fields:
            continue
        canonical_value = _s(identity.get(field_name)).strip()
        if canonical_value:
            resolved[field_name] = canonical_value
    if resolved:
        execution.state.payload_overrides.update(resolved)
        execution.state.deterministic_repairs.append("canonical_identity")
        execution.state.regenerated_sections.append("report_identity")
        logger.info(
            log_event(
                execution.target_ctx,
                role="generator",
                event="artifact_regeneration_identity_repaired",
                module=logger.name,
                fields={
                    "report_id": execution.runtime.request.report_id,
                    "fields": sorted(resolved),
                    "model_calls": 0,
                },
            )
        )
        return
    # No canonical identity is retained: abstain explicitly rather than let a
    # later retry invent a title.
    execution.state.deterministic_repairs.append(
        "canonical_identity_abstained"
        if execution.target.repair_strategy == "canonical_identity"
        else (execution.target.repair_strategy or "canonical_identity_abstained")
    )
    execution.state.regenerated_sections.append("report_identity")


def _resolve_failed_quote_entry(
    execution: _RegenerationHandlerExecution,
    issue: RegenerationIssue,
) -> Dict[str, Any] | None:
    entity_id = _s(issue.entity_id).strip()
    affected = _s(issue.affected_section).strip().casefold()
    quote_id = affected.split(":", 1)[1].strip() if ":" in affected else ""
    message = _s(issue.message)
    matches: List[Dict[str, Any]] = []
    for quote in execution.state.quotes_final:
        if not isinstance(quote, dict):
            continue
        candidate_ids = {
            _s(quote.get("id")).strip(),
            _s(quote.get("evidence_id")).strip(),
        }
        if entity_id and entity_id in candidate_ids:
            matches.append(quote)
            continue
        if quote_id and quote_id in candidate_ids:
            matches.append(quote)
            continue
        quote_text = _normalized_soft_copy_text(_s(quote.get("text")))
        if quote_text and quote_text in _normalized_soft_copy_text(message):
            matches.append(quote)
    if len(matches) != 1:
        return None
    return matches[0]


def _failed_quote_entries(
    execution: _RegenerationHandlerExecution,
) -> List[tuple[RegenerationIssue, Dict[str, Any]]] | None:
    """Resolve each failed quote issue to exactly one retained quote entry."""

    resolved: List[tuple[RegenerationIssue, Dict[str, Any]]] = []
    for issue in execution.target.issues:
        failed_entry = _resolve_failed_quote_entry(execution, issue)
        if failed_entry is None:
            return None
        resolved.append((issue, failed_entry))
    return resolved


def _retained_quote_candidate_for(
    execution: _RegenerationHandlerExecution, quote_entry: Dict[str, Any]
) -> Dict[str, Any] | None:
    evidence_id = _normalized_evidence_id(quote_entry.get("evidence_id"))
    quarantined = {
        _normalized_evidence_id(value)
        for value in execution.target.quarantined_evidence_ids
        if _normalized_evidence_id(value)
    }
    if evidence_id and evidence_id not in quarantined:
        matching_ids = [
            candidate
            for candidate in execution.runtime.quote_candidates
            if isinstance(candidate, dict)
            and _normalized_evidence_id(
                candidate.get("id") or candidate.get("evidence_id")
            )
            == evidence_id
        ]
        if len(matching_ids) == 1 and _s(matching_ids[0].get("text")).strip():
            return matching_ids[0]
    quote_text = _normalized_soft_copy_text(_s(quote_entry.get("text")))
    if not quote_text:
        return None
    exact_text_matches: List[Dict[str, Any]] = []
    for candidate in execution.runtime.quote_candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_id = _normalized_evidence_id(
            candidate.get("id") or candidate.get("evidence_id")
        )
        candidate_text = _normalized_soft_copy_text(_s(candidate.get("text")))
        if (
            candidate_id
            and candidate_id not in quarantined
            and candidate_text == quote_text
        ):
            exact_text_matches.append(candidate)
    return exact_text_matches[0] if len(exact_text_matches) == 1 else None


def _restore_failed_quotes_deterministically(
    execution: _RegenerationHandlerExecution,
) -> bool:
    """Restore each failed quote verbatim from its retained source candidate.

    Exact source-supported quote failures are uniquely source-provable.  When
    every failed quote resolves to one retained quote candidate bound to the
    same evidence id, copying that candidate repairs the failure with zero
    model calls.  Any ambiguous or unresolvable case returns False so the
    normal evidence-backed rewrite path runs instead.
    """

    if execution.target.repair_action != "COPY_CANONICAL_SOURCE_VALUE":
        return False
    resolved = _failed_quote_entries(execution)
    if resolved is None:
        return False
    restored: List[Dict[str, Any]] = []
    for quote in execution.state.quotes_final:
        match = next(
            ((issue, entry) for issue, entry in resolved if entry is quote),
            None,
        )
        if match is None:
            restored.append(quote)
            continue
        _issue, failed_entry = match
        candidate = _retained_quote_candidate_for(execution, failed_entry)
        if candidate is None:
            return False
        repaired = quote
        repaired["text"] = _s(candidate.get("text")).strip()
        speaker = _s(candidate.get("speaker")).strip()
        if speaker:
            repaired["speaker"] = speaker
        page = candidate.get("page")
        if isinstance(page, int) and page > 0:
            repaired["page"] = page
        candidate_id = _s(candidate.get("id") or candidate.get("evidence_id")).strip()
        if candidate_id:
            repaired["evidence_id"] = candidate_id
        source_pack = _s(candidate.get("source_pack")).strip()
        if source_pack:
            repaired["source_pack"] = source_pack
        restored.append(repaired)
        execution.state.selected_evidence_ids.extend(
            [
                _s(candidate.get("id") or candidate.get("evidence_id")).strip(),
                _s(failed_entry.get("evidence_id")).strip(),
            ]
        )
    execution.state.quotes_final = restored
    execution.state.deterministic_repairs.append("canonical_quote_restore")
    execution.state.regenerated_sections.append("quotes")
    logger.info(
        log_event(
            execution.target_ctx,
            role="generator",
            event="artifact_regeneration_quotes_restored",
            module=logger.name,
            fields={
                "report_id": execution.runtime.request.report_id,
                "restored_quote_count": len(resolved),
                "model_calls": 0,
            },
        )
    )
    return True


def _handle_quotes_regeneration(execution: _RegenerationHandlerExecution) -> None:
    if _restore_failed_quotes_deterministically(execution):
        return
    if _regenerate_one_quote(execution):
        return
    quarantined_ids = set(
        execution.grounding_package.get("quarantined_evidence_ids") or []
    )
    retained_candidates = _without_quarantined_evidence(
        execution.runtime.quote_candidates, quarantined_ids
    )
    if not retained_candidates:
        resolved = _failed_quote_entries(execution)
        if resolved is None:
            execution.state.quotes_final = []
        else:
            failed_entries = {id(entry) for _issue, entry in resolved}
            execution.state.quotes_final = [
                quote
                for quote in execution.state.quotes_final
                if id(quote) not in failed_entries
            ]
        execution.state.deterministic_repairs.append("safe_abstain")
        execution.state.regenerated_sections.append("quotes")
        return
    namespace = execution.handler.prompt_namespaces[0]
    result = _render_regeneration_model(
        execution=execution,
        namespace=namespace,
        ctx=execution.target_ctx,
        variables={
            **execution.runtime.base_vars,
            "attempt_index": execution.runtime.request.attempt_index,
            "target_section": execution.target.target_section,
            "current_section_json": _dump_json(execution.state.quotes_final),
            "quote_candidates_json": _dump_json(
                _without_quarantined_evidence(
                    execution.runtime.quote_candidates, quarantined_ids
                )
            ),
            "failure_reasons_json": _issues_json(execution.target.issues),
            "fix_checklist_json": _fix_checklist_json(execution.target),
            "grounding_package_json": _dump_json(execution.grounding_package),
        },
    )
    execution.state.quotes_final = normalize_artifact_quotes(result.get("quotes_final"))
    execution.state.regenerated_sections.append("quotes")
    execution.state.prompt_namespaces.append(namespace)


def _regenerate_one_quote(execution: _RegenerationHandlerExecution) -> bool:
    """Patch one uniquely resolved quote while retaining all quote siblings."""

    resolved = _failed_quote_entries(execution)
    if resolved is None or len(resolved) != 1:
        return False
    _issue, failed_entry = resolved[0]
    index = next(
        (
            position
            for position, quote in enumerate(execution.state.quotes_final)
            if quote is failed_entry
        ),
        None,
    )
    if index is None:
        return False
    namespace = execution.handler.prompt_namespaces[0]
    quarantined_ids = set(
        execution.grounding_package.get("quarantined_evidence_ids") or []
    )
    candidates = _without_quarantined_evidence(
        execution.runtime.quote_candidates, quarantined_ids
    )
    result = _render_regeneration_model(
        execution=execution,
        namespace=namespace,
        ctx=execution.target_ctx,
        variables={
            **execution.runtime.base_vars,
            "attempt_index": execution.runtime.request.attempt_index,
            "target_section": execution.target.target_section,
            "current_section_json": _dump_json([failed_entry]),
            "quote_candidates_json": _dump_json(candidates),
            "failure_reasons_json": _issues_json(execution.target.issues),
            "fix_checklist_json": _fix_checklist_json(execution.target),
            "grounding_package_json": _dump_json(execution.grounding_package),
        },
    )
    regenerated = normalize_artifact_quotes(result.get("quotes_final"))
    if not regenerated:
        raise AppError(
            code="regeneration_target_item_unresolved",
            message="Atomic quote regeneration did not return its stable target.",
            retryable=False,
            context={"report_id": execution.runtime.request.report_id},
        )
    stable_id = _s(failed_entry.get("id") or failed_entry.get("evidence_id")).strip()
    replacement = next(
        (
            quote
            for quote in regenerated
            if stable_id
            and _s(quote.get("id") or quote.get("evidence_id")).strip() == stable_id
        ),
        regenerated[0] if len(regenerated) == 1 else None,
    )
    if replacement is None:
        raise AppError(
            code="regeneration_target_item_unresolved",
            message="Atomic quote regeneration returned an ambiguous target.",
            retryable=False,
            context={"report_id": execution.runtime.request.report_id},
        )
    # Quote repair changes the text claim. Keep the retained quote's source
    # binding and speaker/citation metadata, which the model cannot safely
    # reconstruct from a text-only answer.
    replacement_text = _s(replacement.get("text")).strip()
    replacement = deepcopy(failed_entry)
    replacement["text"] = replacement_text
    if not replacement["text"]:
        raise AppError(
            code="regeneration_target_item_unresolved",
            message="Atomic quote regeneration returned empty text.",
            retryable=False,
            context={"report_id": execution.runtime.request.report_id},
        )
    execution.state.quotes_final[index] = replacement
    execution.state.regenerated_sections.append("quotes")
    execution.state.prompt_namespaces.append(namespace)
    return True


def _handle_cover_semantics_regeneration(
    execution: _RegenerationHandlerExecution,
) -> None:
    """Refresh the cover fingerprint from retained, already-grounded artifacts."""
    namespace = execution.handler.prompt_namespaces[0]
    result = _render_regeneration_model(
        execution=execution,
        namespace=namespace,
        ctx=execution.target_ctx,
        repair_call=False,
        variables={
            **execution.runtime.base_vars,
            "summary_json": _dump_json(execution.state.summary),
            "insights_final_json": _dump_json(execution.state.insights_final),
            "categories_json": _dump_json(execution.runtime.request.categories),
            "region": _s(
                execution.runtime.safe_doc_map.get("region")
                or execution.runtime.safe_doc_map.get("geography")
            ).strip(),
            "covered_period": _s(
                execution.runtime.safe_doc_map.get("covered_period")
                or execution.runtime.safe_doc_map.get("time_period")
                or execution.runtime.safe_doc_map.get("period")
            ).strip(),
        },
    )
    cover = result.get("cover_semantics")
    execution.state.cover_semantics = dict(cover) if isinstance(cover, dict) else {}
    execution.state.regenerated_sections.append("cover_semantics")
    execution.state.prompt_namespaces.append(namespace)


def _handle_expert_comment_regeneration(
    execution: _RegenerationHandlerExecution,
) -> None:
    _normalize_state_evidence_ids(execution)
    claim_repairs = _soft_copy_claim_repairs(
        execution,
        artifact_family="expert_comment",
        text=execution.state.expert_comment,
    )
    namespace = execution.handler.prompt_namespaces[0]
    if claim_repairs is not None:
        replacements: Dict[str, str | None] = {}
        if _uses_safe_removal(execution):
            for repair in claim_repairs:
                replacements[repair.claim.claim_id] = None
                _mark_soft_copy_claim_removed(execution, repair)
        else:
            expert_synthesis_context = _exclude_quarantined_expert_context(
                build_expert_synthesis_context(
                    editorial_plan=execution.state.editorial_plan,
                    insights_final=execution.state.insights_final,
                    doc_map=execution.runtime.safe_doc_map,
                    evidence_packs=execution.runtime.safe_evidence,
                ),
                set(execution.grounding_package.get("quarantined_evidence_ids") or []),
            )
            for repair in claim_repairs:
                claim_grounding = _claim_scoped_grounding_package(execution, repair)
                if not _claim_has_repair_support(claim_grounding):
                    replacements[repair.claim.claim_id] = None
                    _mark_soft_copy_claim_removed(execution, repair)
                    continue
                selected_evidence_ids = set(claim_grounding["evidence_ids"])
                result = _render_regeneration_model(
                    execution=execution,
                    namespace=namespace,
                    ctx=execution.target_ctx,
                    variables={
                        "attempt_index": execution.runtime.request.attempt_index,
                        "target_section": execution.target.target_section,
                        "editorial_plan_json": _dump_json(
                            _claim_scoped_editorial_plan(
                                execution.state.editorial_plan, selected_evidence_ids
                            )
                        ),
                        "expert_synthesis_context_json": _dump_json(
                            _claim_scoped_expert_context(
                                expert_synthesis_context, selected_evidence_ids
                            )
                        ),
                        "expert_domain": execution.runtime.expert_domain,
                        "current_section_text": repair.text,
                        "claim_repair_scope_json": _dump_json(
                            {
                                "mode": "claim",
                                "failed_claim": repair.text,
                                "preserve_sibling_claims": True,
                            }
                        ),
                        "failure_reasons_json": _issues_json(repair.issues),
                        "fix_checklist_json": _fix_checklist_json(execution.target),
                        "grounding_package_json": _dump_json(claim_grounding),
                    },
                )
                repaired_text = _s(result.get("expert_comment"))
                if not _valid_claim_replacement(
                    artifact_family="expert_comment",
                    text=repaired_text,
                    bindings=result.get("_soft_copy_claim_bindings"),
                ):
                    replacements[repair.claim.claim_id] = None
                    _mark_soft_copy_claim_removed(execution, repair)
                    continue
                _record_soft_copy_claim_bindings(
                    execution,
                    artifact_family="expert_comment",
                    namespace=namespace,
                    result=result,
                    repaired_claim=repair,
                    repaired_text=repaired_text,
                )
                replacements[repair.claim.claim_id] = repaired_text
        execution.state.expert_comment = _reconstruct_soft_copy_claims(
            execution.state.expert_comment, claim_repairs, replacements
        )
        execution.state.regenerated_sections.append("expert_comment")
        execution.state.prompt_namespaces.append(namespace)
        return
    if _uses_safe_removal(execution):
        execution.state.expert_comment = ""
        _mark_soft_copy_family_replaced(execution, "expert_comment")
        execution.state.regenerated_sections.append("expert_comment")
        return
    expert_synthesis_context = build_expert_synthesis_context(
        editorial_plan=execution.state.editorial_plan,
        insights_final=execution.state.insights_final,
        doc_map=execution.runtime.safe_doc_map,
        evidence_packs=execution.runtime.safe_evidence,
    )
    expert_synthesis_context = _exclude_quarantined_expert_context(
        expert_synthesis_context,
        set(execution.grounding_package.get("quarantined_evidence_ids") or []),
    )
    result = _render_regeneration_model(
        execution=execution,
        namespace=namespace,
        ctx=execution.target_ctx,
        variables={
            "attempt_index": execution.runtime.request.attempt_index,
            "target_section": execution.target.target_section,
            "editorial_plan_json": _dump_json(execution.state.editorial_plan),
            "expert_synthesis_context_json": _dump_json(expert_synthesis_context),
            "expert_domain": execution.runtime.expert_domain,
            "current_section_text": execution.state.expert_comment,
            "claim_repair_scope_json": _dump_json({"mode": "family"}),
            "failure_reasons_json": _issues_json(execution.target.issues),
            "fix_checklist_json": _fix_checklist_json(execution.target),
            "grounding_package_json": _dump_json(execution.grounding_package),
        },
    )
    _record_soft_copy_claim_bindings(
        execution,
        artifact_family="expert_comment",
        namespace=namespace,
        result=result,
    )
    regenerated_text = _s(result.get("expert_comment"))
    execution.state.expert_comment = regenerated_text
    execution.state.regenerated_sections.append("expert_comment")
    execution.state.prompt_namespaces.append(namespace)


def _handle_key_figures_regeneration(execution: _RegenerationHandlerExecution) -> None:
    """Rebuild the deterministic Key Figure projection without rewriting editorial."""

    execution.state.regenerated_sections.append("key_figures")


def _exclude_quarantined_expert_context(
    context: Dict[str, Any], excluded_evidence_ids: set[str]
) -> Dict[str, Any]:
    if not excluded_evidence_ids:
        return context
    normalized_excluded = {
        _normalized_evidence_id(value) for value in excluded_evidence_ids
    }
    safe_context = deepcopy(context)
    for theme in safe_context.get("themes") or []:
        if isinstance(theme, dict):
            theme["evidence"] = [
                entry
                for entry in theme.get("evidence") or []
                if _normalized_evidence_id(entry.get("evidence_id"))
                not in normalized_excluded
            ]
    for key in ("insight_implications", "limitations", "counter_signals"):
        safe_context[key] = [
            entry
            for entry in safe_context.get(key) or []
            if not isinstance(entry, dict)
            or _normalized_evidence_id(entry.get("evidence_id"))
            not in normalized_excluded
        ]
    return safe_context


def _claim_scoped_editorial_plan(
    editorial_plan: Dict[str, Any], selected_evidence_ids: set[str]
) -> Dict[str, Any]:
    """Keep only selected retained theme bindings in a scoped repair prompt."""

    plan = deepcopy(editorial_plan)
    normalized_selected = {
        _normalized_evidence_id(value) for value in selected_evidence_ids
    }
    plan["themes"] = [
        {
            **theme,
            "evidence_ids": [
                evidence_id
                for evidence_id in theme.get("evidence_ids") or []
                if _normalized_evidence_id(evidence_id) in normalized_selected
            ],
        }
        for theme in plan.get("themes") or []
        if isinstance(theme, dict)
        and any(
            _normalized_evidence_id(evidence_id) in normalized_selected
            for evidence_id in theme.get("evidence_ids") or []
        )
    ]
    return plan


def _claim_scoped_expert_context(
    context: Dict[str, Any], selected_evidence_ids: set[str]
) -> Dict[str, Any]:
    """Keep an Expert View repair from receiving unrelated report evidence."""

    allowed_ids = {_normalized_evidence_id(value) for value in selected_evidence_ids}
    scoped = deepcopy(context)
    scoped["themes"] = [
        {
            **theme,
            "evidence": [
                entry
                for entry in theme.get("evidence") or []
                if isinstance(entry, dict)
                and _normalized_evidence_id(entry.get("evidence_id")) in allowed_ids
            ],
        }
        for theme in scoped.get("themes") or []
        if isinstance(theme, dict)
        and any(
            isinstance(entry, dict)
            and _normalized_evidence_id(entry.get("evidence_id")) in allowed_ids
            for entry in theme.get("evidence") or []
        )
    ]
    for key in ("insight_implications", "limitations", "counter_signals"):
        scoped[key] = [
            entry
            for entry in scoped.get(key) or []
            if isinstance(entry, dict)
            and _normalized_evidence_id(entry.get("evidence_id")) in allowed_ids
        ]
    return scoped


def _handle_linkedin_post_regeneration(
    execution: _RegenerationHandlerExecution,
) -> None:
    _normalize_state_evidence_ids(execution)
    claim_repairs = _soft_copy_claim_repairs(
        execution,
        artifact_family="linkedin_post",
        text=execution.state.linkedin_post,
    )
    namespace = execution.handler.prompt_namespaces[0]
    if claim_repairs is not None:
        replacements: Dict[str, str | None] = {}
        for repair in claim_repairs:
            if _uses_safe_removal(execution):
                replacements[repair.claim.claim_id] = None
                _mark_soft_copy_claim_removed(execution, repair)
                continue
            claim_grounding = _claim_scoped_grounding_package(execution, repair)
            if not _claim_has_repair_support(claim_grounding):
                replacements[repair.claim.claim_id] = None
                _mark_soft_copy_claim_removed(execution, repair)
                continue
            selected_evidence_ids = set(claim_grounding["evidence_ids"])
            result = _render_regeneration_model(
                execution=execution,
                namespace=namespace,
                ctx=execution.target_ctx,
                variables={
                    "attempt_index": execution.runtime.request.attempt_index,
                    "target_section": execution.target.target_section,
                    "editorial_plan_json": _dump_json(
                        _claim_scoped_editorial_plan(
                            execution.state.editorial_plan, selected_evidence_ids
                        )
                    ),
                    "report_identity_json": _dump_json(
                        _public_report_identity(execution.runtime.safe_doc_map)
                    ),
                    "current_section_text": repair.text,
                    "claim_repair_scope_json": _dump_json(
                        {
                            "mode": "claim",
                            "failed_claim": repair.text,
                            "preserve_sibling_claims": True,
                        }
                    ),
                    "failure_reasons_json": _issues_json(repair.issues),
                    "fix_checklist_json": _fix_checklist_json(execution.target),
                    "grounding_package_json": _dump_json(claim_grounding),
                },
            )
            repaired_text = strip_linkedin_inline_reference_ids(
                _s(result.get("linkedin_post"))
            )
            if not _valid_claim_replacement(
                artifact_family="linkedin_post",
                text=repaired_text,
                bindings=result.get("_soft_copy_claim_bindings"),
            ):
                replacements[repair.claim.claim_id] = None
                _mark_soft_copy_claim_removed(execution, repair)
                continue
            _record_soft_copy_claim_bindings(
                execution,
                artifact_family="linkedin_post",
                namespace=namespace,
                result=result,
                repaired_claim=repair,
                repaired_text=repaired_text,
            )
            replacements[repair.claim.claim_id] = repaired_text
        execution.state.linkedin_post = _reconstruct_soft_copy_claims(
            execution.state.linkedin_post, claim_repairs, replacements
        )
        execution.state.regenerated_sections.append("linkedin_post")
        execution.state.prompt_namespaces.append(namespace)
        return
    if _uses_safe_removal(execution):
        execution.state.linkedin_post = ""
        _mark_soft_copy_family_replaced(execution, "linkedin_post")
        execution.state.regenerated_sections.append("linkedin_post")
        return
    result = _render_regeneration_model(
        execution=execution,
        namespace=namespace,
        ctx=execution.target_ctx,
        variables={
            "attempt_index": execution.runtime.request.attempt_index,
            "target_section": execution.target.target_section,
            "editorial_plan_json": _dump_json(execution.state.editorial_plan),
            "report_identity_json": _dump_json(
                _public_report_identity(execution.runtime.safe_doc_map)
            ),
            "current_section_text": execution.state.linkedin_post,
            "claim_repair_scope_json": _dump_json({"mode": "family"}),
            "failure_reasons_json": _issues_json(execution.target.issues),
            "fix_checklist_json": _fix_checklist_json(execution.target),
            "grounding_package_json": _dump_json(execution.grounding_package),
        },
    )
    _record_soft_copy_claim_bindings(
        execution,
        artifact_family="linkedin_post",
        namespace=namespace,
        result=result,
    )
    regenerated_text = strip_linkedin_inline_reference_ids(
        _s(result.get("linkedin_post"))
    )
    execution.state.linkedin_post = regenerated_text
    execution.state.regenerated_sections.append("linkedin_post")
    execution.state.prompt_namespaces.append(namespace)


def _without_quarantined_evidence(value: Any, excluded_evidence_ids: set[str]) -> Any:
    if not excluded_evidence_ids:
        return value
    if isinstance(value, list):
        return [
            _without_quarantined_evidence(item, excluded_evidence_ids)
            for item in value
            if not (
                isinstance(item, dict)
                and _s(item.get("evidence_id") or item.get("id")).strip()
                in excluded_evidence_ids
            )
        ]
    if isinstance(value, dict):
        return {
            key: _without_quarantined_evidence(item, excluded_evidence_ids)
            for key, item in value.items()
        }
    return value


def _public_report_identity(doc_map: Dict[str, Any]) -> Dict[str, str]:
    return {
        key: _s(doc_map.get(key)).strip()
        for key in (
            "title",
            "report_title",
            "publisher",
            "author",
            "edition",
            "publication_date",
            "covered_period",
            "region",
            "scope",
            "source_url",
        )
        if _s(doc_map.get(key)).strip()
    }


def _topics_section_payload(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "toc_entries": _copy_list(artifacts.get("toc_entries")),
        "toc_topics": _copy_list(artifacts.get("toc_topics")),
        "toc_topics_expanded": _copy_list(artifacts.get("toc_topics_expanded")),
    }


def _summary_section_payload(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    return _copy_dict(artifacts.get("summary"))


def _insights_bundle_section_payload(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "insights_candidates": _copy_list(artifacts.get("insights_candidates")),
        "insights_final": _copy_list(artifacts.get("insights_final")),
    }


def _key_figures_section_payload(artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _copy_list(artifacts.get("key_figures"))


def _quotes_section_payload(artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _copy_list(artifacts.get("quotes_final"))


def _cover_semantics_section_payload(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    return _copy_dict(artifacts.get("cover_semantics"))


def _expert_comment_section_payload(artifacts: Dict[str, Any]) -> str:
    return _s(artifacts.get("expert_comment"))


def _linkedin_post_section_payload(artifacts: Dict[str, Any]) -> str:
    return _s(artifacts.get("linkedin_post"))


_REGENERATION_HANDLER_REGISTRY: Dict[str, _RegenerationHandler] = {
    "summary": _RegenerationHandler(
        target_section="summary",
        prompt_namespaces=("report_vs/artifacts/regenerate/summary",),
        current_section_payload=_summary_section_payload,
        extra_fix_checklist=(),
        handle=_handle_summary_regeneration,
    ),
    "topics": _RegenerationHandler(
        target_section="topics",
        prompt_namespaces=(),
        current_section_payload=_topics_section_payload,
        extra_fix_checklist=(),
        handle=_handle_topics_regeneration,
    ),
    "insights_bundle": _RegenerationHandler(
        target_section="insights_bundle",
        prompt_namespaces=(
            "report_vs/artifacts/regenerate/insights_candidates",
            "report_vs/artifacts/regenerate/insights_final",
        ),
        current_section_payload=_insights_bundle_section_payload,
        extra_fix_checklist=(
            "Each final insight must map cleanly to evidence_id and supporting evidence text.",
        ),
        handle=_handle_insights_bundle_regeneration,
    ),
    "key_figures": _RegenerationHandler(
        target_section="key_figures",
        prompt_namespaces=(),
        current_section_payload=_key_figures_section_payload,
        extra_fix_checklist=(
            "Keep only source-backed, distinct metrics that pass label/value relationship fidelity.",
        ),
        handle=_handle_key_figures_regeneration,
    ),
    "quotes": _RegenerationHandler(
        target_section="quotes",
        prompt_namespaces=("report_vs/artifacts/regenerate/quotes",),
        current_section_payload=_quotes_section_payload,
        extra_fix_checklist=(
            "Quotes must be verbatim or clearly supported by source evidence.",
        ),
        handle=_handle_quotes_regeneration,
    ),
    "cover_semantics": _RegenerationHandler(
        target_section="cover_semantics",
        prompt_namespaces=("report_vs/artifacts/cover_semantics",),
        current_section_payload=_cover_semantics_section_payload,
        extra_fix_checklist=(),
        handle=_handle_cover_semantics_regeneration,
    ),
    "expert_comment": _RegenerationHandler(
        target_section="expert_comment",
        prompt_namespaces=("report_vs/artifacts/regenerate/expert_comment",),
        current_section_payload=_expert_comment_section_payload,
        extra_fix_checklist=(
            "Do not introduce new claims that are absent from the updated summary/insights/quotes.",
        ),
        handle=_handle_expert_comment_regeneration,
    ),
    "linkedin_post": _RegenerationHandler(
        target_section="linkedin_post",
        prompt_namespaces=("report_vs/artifacts/regenerate/linkedin_post",),
        current_section_payload=_linkedin_post_section_payload,
        extra_fix_checklist=(
            "Do not introduce new claims that are absent from the updated summary/insights/quotes.",
        ),
        handle=_handle_linkedin_post_regeneration,
    ),
    "report_identity": _RegenerationHandler(
        target_section="report_identity",
        prompt_namespaces=(),
        current_section_payload=lambda artifacts: {},
        extra_fix_checklist=(),
        handle=_handle_report_identity_regeneration,
    ),
}


def _resolve_regeneration_handler(target_section: str) -> _RegenerationHandler:
    handler = _REGENERATION_HANDLER_REGISTRY.get(target_section)
    if handler is None:
        raise AppError(
            code="artifact_regeneration_target_unsupported",
            message=f"Unsupported artifact regeneration target_section: {target_section}",
            retryable=False,
            context={"target_section": target_section},
        )
    return handler
