from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List

from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    ArtifactRegenerationResponse,
    RegenerationIssue,
    RegenerationTarget,
)
from src.contracts.run_context import RunContext
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
from src.generators.validation.evidence import retrieve_evidence_windows
from src.generators.validation.preparation import prepare_validation_inputs
from src.services import prompt_service, report_analysis_store_service
from src.utils.analysis_family import family_is_abstained
from src.utils.coercion import string_value as _s
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
    openai_client = require_injected_model_client(
        openai_client,
        scope="artifact_regeneration",
    )
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
        validate_references=False,
    )
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
    relevant_evidence = _collect_relevant_evidence_entries(
        target.issues, evidence_packs, doc_map
    )
    search_text = " ".join(
        part
        for part in (
            _section_text(current_section),
            " ".join(issue.message for issue in target.issues),
        )
        if part
    )
    evidence_windows = retrieve_evidence_windows(search_text, prepared.evidence_windows)
    return {
        "current_section": current_section,
        "relevant_evidence": relevant_evidence,
        "evidence_windows": [
            {"idx": window.idx, "text": window.text} for window in evidence_windows[:4]
        ],
        "evidence_ids": _unique_strings(
            evidence_id for issue in target.issues for evidence_id in issue.evidence_ids
        ),
        "pages": _unique_ints(page for issue in target.issues for page in issue.pages),
    }


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
        for section in doc_map.get("sections") or []:
            if not isinstance(section, dict):
                continue
            section_id = _s(section.get("id"))
            if section_id in target_ids:
                entries.append(
                    {
                        "pack_name": "doc_map",
                        "id": section_id,
                        "title": _s(section.get("title")),
                        "summary": _s(section.get("summary")),
                        "pages": list(section.get("pages") or []),
                    }
                )
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


def _issues_json(issues: List[RegenerationIssue]) -> str:
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
    )


def _render_regeneration_model(
    *,
    execution: _RegenerationHandlerExecution,
    namespace: str,
    variables: Dict[str, Any],
    ctx: RunContext,
) -> Dict[str, Any]:
    request = execution.runtime.request
    return render_artifact_json_model(
        namespace=namespace,
        variables=variables,
        settings=request.settings,
        ctx=ctx,
        openai_client=execution.runtime.openai_client,
        prompt_client=execution.runtime.prompt_client,
        allow_vector_store=execution.runtime.artifact_use_vector_store,
        vector_store_id=request.vector_store_id,
        publisher_name=request.publisher_name,
        report_name=request.report_name,
        source_url=request.source_url,
    )


def _normalize_state_evidence_ids(execution: _RegenerationHandlerExecution) -> None:
    normalize_artifact_evidence_ids(
        summary=execution.state.summary,
        insights_candidates=execution.state.insights_candidates,
        insights_final=execution.state.insights_final,
        quotes_final=execution.state.quotes_final,
        doc_map=execution.runtime.safe_doc_map,
        evidence_packs=execution.runtime.safe_evidence,
    )


def _handle_summary_regeneration(execution: _RegenerationHandlerExecution) -> None:
    namespace = execution.handler.prompt_namespaces[0]
    result = _render_regeneration_model(
        execution=execution,
        namespace=namespace,
        ctx=execution.target_ctx,
        variables={
            **execution.runtime.base_vars,
            "attempt_index": execution.runtime.request.attempt_index,
            "target_section": execution.target.target_section,
            "current_section_json": _dump_json(execution.state.summary),
            "failure_reasons_json": _issues_json(execution.target.issues),
            "fix_checklist_json": _fix_checklist_json(execution.target),
            "grounding_package_json": _dump_json(execution.grounding_package),
            "editorial_plan_json": _dump_json(execution.state.editorial_plan),
        },
    )
    execution.state.summary = normalize_artifact_summary(result.get("summary"))
    execution.state.regenerated_sections.append("summary")
    execution.state.prompt_namespaces.append(namespace)


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


def _handle_insights_bundle_regeneration(
    execution: _RegenerationHandlerExecution,
) -> None:
    candidates_namespace, final_namespace = execution.handler.prompt_namespaces
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
    execution.state.insights_candidates = select_artifact_insights(
        final_insights=normalize_artifact_insights(
            candidates_result.get("insights_candidates"),
            prefix="candidate",
        ),
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
    execution.state.insights_final = select_artifact_insights(
        final_insights=_restore_final_insight_evidence_bindings(
            final_insights=normalize_artifact_insights(
                final_result.get("insights_final"), prefix="insight"
            ),
            candidate_insights=execution.state.insights_candidates,
            prior_final_insights=execution.state.insights_final,
        ),
        candidate_insights=execution.state.insights_candidates,
        editorial_plan=execution.state.editorial_plan,
    )
    execution.state.regenerated_sections.extend(
        ["insights_candidates", "insights_final"]
    )
    execution.state.prompt_namespaces.extend([candidates_namespace, final_namespace])


def _handle_quotes_regeneration(execution: _RegenerationHandlerExecution) -> None:
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
            "quote_candidates_json": _dump_json(execution.runtime.quote_candidates),
            "failure_reasons_json": _issues_json(execution.target.issues),
            "fix_checklist_json": _fix_checklist_json(execution.target),
            "grounding_package_json": _dump_json(execution.grounding_package),
        },
    )
    execution.state.quotes_final = normalize_artifact_quotes(result.get("quotes_final"))
    execution.state.regenerated_sections.append("quotes")
    execution.state.prompt_namespaces.append(namespace)


def _handle_cover_semantics_regeneration(
    execution: _RegenerationHandlerExecution,
) -> None:
    """Refresh the cover fingerprint from retained, already-grounded artifacts."""
    namespace = execution.handler.prompt_namespaces[0]
    result = _render_regeneration_model(
        execution=execution,
        namespace=namespace,
        ctx=execution.target_ctx,
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
    namespace = execution.handler.prompt_namespaces[0]
    expert_synthesis_context = build_expert_synthesis_context(
        editorial_plan=execution.state.editorial_plan,
        insights_final=execution.state.insights_final,
        doc_map=execution.runtime.safe_doc_map,
        evidence_packs=execution.runtime.safe_evidence,
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
            "failure_reasons_json": _issues_json(execution.target.issues),
            "fix_checklist_json": _fix_checklist_json(execution.target),
            "grounding_package_json": _dump_json(execution.grounding_package),
        },
    )
    execution.state.expert_comment = _s(result.get("expert_comment"))
    execution.state.regenerated_sections.append("expert_comment")
    execution.state.prompt_namespaces.append(namespace)


def _handle_linkedin_post_regeneration(
    execution: _RegenerationHandlerExecution,
) -> None:
    _normalize_state_evidence_ids(execution)
    namespace = execution.handler.prompt_namespaces[0]
    result = _render_regeneration_model(
        execution=execution,
        namespace=namespace,
        ctx=execution.target_ctx,
        variables={
            "attempt_index": execution.runtime.request.attempt_index,
            "target_section": execution.target.target_section,
            "editorial_plan_json": _dump_json(execution.state.editorial_plan),
            "doc_map_json": execution.runtime.base_vars["doc_map_json"],
            "insights_final_json": _dump_json(execution.state.insights_final),
            "current_section_text": execution.state.linkedin_post,
            "failure_reasons_json": _issues_json(execution.target.issues),
            "fix_checklist_json": _fix_checklist_json(execution.target),
            "grounding_package_json": _dump_json(execution.grounding_package),
        },
    )
    execution.state.linkedin_post = strip_linkedin_inline_reference_ids(
        _s(result.get("linkedin_post"))
    )
    execution.state.regenerated_sections.append("linkedin_post")
    execution.state.prompt_namespaces.append(namespace)


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
