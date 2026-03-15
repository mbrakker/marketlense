from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import asdict
from typing import Any, Dict, List

from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    ArtifactRegenerationResponse,
    RegenerationIssue,
    RegenerationTarget,
)
from src.contracts.validation import ValidationRequest
from src.generators.artifact_normalization import (
    artifact_base_variables,
    artifact_quote_candidates,
    artifact_vector_store_enabled,
    normalize_artifact_evidence_ids,
    normalize_artifact_insights,
    normalize_artifact_quotes,
    normalize_artifact_source_status,
    normalize_artifact_summary,
    normalize_artifact_topics,
    normalize_expert_domain,
    pad_artifact_insights,
    strip_artifact_inline_reference_ids,
)
from src.generators.artifact_generator import (
    assemble_artifacts_payload,
    render_artifact_json_model,
    store_artifacts_payload,
)
from src.generators.validation.evidence import retrieve_evidence_windows
from src.generators.validation.preparation import prepare_validation_inputs
from src.services import openai_service, prompt_service, report_analysis_store_service
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.report_regeneration_generator")


def regenerate_artifacts(
    request: ArtifactRegenerationRequest,
    *,
    openai_client=openai_service,
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
    quote_candidates = artifact_quote_candidates(safe_evidence)
    expert_domain = normalize_expert_domain(request.categories)

    toc_topics = normalize_artifact_topics(safe_artifacts.get("toc_topics"))
    summary = _copy_dict(safe_artifacts.get("summary"))
    insights_candidates = _copy_list(safe_artifacts.get("insights_candidates"))
    insights_final = _copy_list(safe_artifacts.get("insights_final"))
    quotes_final = _copy_list(safe_artifacts.get("quotes_final"))
    expert_comment = _s(safe_artifacts.get("expert_comment"))
    linkedin_post = _s(safe_artifacts.get("linkedin_post"))
    regenerated_sections: List[str] = []
    prompt_namespaces: List[str] = []

    for target in request.plan.targets:
        target_ctx = child_context(ctx, task_id=f"{ctx.task_id}:{target.target_section}")
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
        current_artifact_state = _artifact_state(
            toc_topics=toc_topics,
            summary=summary,
            insights_candidates=insights_candidates,
            insights_final=insights_final,
            quotes_final=quotes_final,
            expert_comment=expert_comment,
            linkedin_post=linkedin_post,
            source_status=availability,
        )
        prepared = _prepare_grounding(request, current_artifact_state)
        grounding_package = _build_grounding_package(
            target=target,
            prepared=prepared,
            artifacts=current_artifact_state,
            evidence_packs=safe_evidence,
            doc_map=safe_doc_map,
        )
        if target.target_section == "summary":
            namespace = "report_vs/artifacts/regenerate/summary"
            result = render_artifact_json_model(
                namespace=namespace,
                variables={
                    **base_vars,
                    "attempt_index": request.attempt_index,
                    "target_section": target.target_section,
                    "current_section_json": _dump_json(summary),
                    "failure_reasons_json": _issues_json(target.issues),
                    "fix_checklist_json": _fix_checklist_json(target),
                    "grounding_package_json": _dump_json(grounding_package),
                },
                settings=request.settings,
                ctx=target_ctx,
                openai_client=openai_client,
                prompt_client=prompt_client,
                allow_vector_store=artifact_use_vector_store,
                vector_store_id=request.vector_store_id,
            )
            summary = normalize_artifact_summary(result.get("summary"))
            regenerated_sections.append("summary")
            prompt_namespaces.append(namespace)
        elif target.target_section == "insights_bundle":
            candidates_namespace = "report_vs/artifacts/regenerate/insights_candidates"
            candidates_result = render_artifact_json_model(
                namespace=candidates_namespace,
                variables={
                    **base_vars,
                    "attempt_index": request.attempt_index,
                    "target_section": target.target_section,
                    "current_section_json": _dump_json(insights_candidates),
                    "failure_reasons_json": _issues_json(target.issues),
                    "fix_checklist_json": _fix_checklist_json(target),
                    "grounding_package_json": _dump_json(grounding_package),
                },
                settings=request.settings,
                ctx=child_context(target_ctx, task_id=f"{target_ctx.task_id}:candidates"),
                openai_client=openai_client,
                prompt_client=prompt_client,
                allow_vector_store=artifact_use_vector_store,
                vector_store_id=request.vector_store_id,
            )
            insights_candidates = normalize_artifact_insights(
                candidates_result.get("insights_candidates"),
                prefix="candidate",
            )
            final_namespace = "report_vs/artifacts/regenerate/insights_final"
            final_result = render_artifact_json_model(
                namespace=final_namespace,
                variables={
                    **base_vars,
                    "attempt_index": request.attempt_index,
                    "target_section": target.target_section,
                    "current_section_json": _dump_json(insights_final),
                    "insights_candidates_json": _dump_json(insights_candidates),
                    "failure_reasons_json": _issues_json(target.issues),
                    "fix_checklist_json": _fix_checklist_json(target),
                    "grounding_package_json": _dump_json(grounding_package),
                },
                settings=request.settings,
                ctx=child_context(target_ctx, task_id=f"{target_ctx.task_id}:final"),
                openai_client=openai_client,
                prompt_client=prompt_client,
                allow_vector_store=artifact_use_vector_store,
                vector_store_id=request.vector_store_id,
            )
            insights_final = pad_artifact_insights(
                normalize_artifact_insights(
                    final_result.get("insights_final"), prefix="insight"
                ),
                insights_candidates,
            )
            regenerated_sections.extend(["insights_candidates", "insights_final"])
            prompt_namespaces.extend([candidates_namespace, final_namespace])
        elif target.target_section == "quotes":
            namespace = "report_vs/artifacts/regenerate/quotes"
            result = render_artifact_json_model(
                namespace=namespace,
                variables={
                    **base_vars,
                    "attempt_index": request.attempt_index,
                    "target_section": target.target_section,
                    "current_section_json": _dump_json(quotes_final),
                    "quote_candidates_json": _dump_json(quote_candidates),
                    "failure_reasons_json": _issues_json(target.issues),
                    "fix_checklist_json": _fix_checklist_json(target),
                    "grounding_package_json": _dump_json(grounding_package),
                },
                settings=request.settings,
                ctx=target_ctx,
                openai_client=openai_client,
                prompt_client=prompt_client,
                allow_vector_store=artifact_use_vector_store,
                vector_store_id=request.vector_store_id,
            )
            quotes_final = normalize_artifact_quotes(result.get("quotes_final"))
            regenerated_sections.append("quotes")
            prompt_namespaces.append(namespace)
        elif target.target_section == "expert_comment":
            normalize_artifact_evidence_ids(
                summary=summary,
                insights_candidates=insights_candidates,
                insights_final=insights_final,
                quotes_final=quotes_final,
                doc_map=safe_doc_map,
                evidence_packs=safe_evidence,
            )
            namespace = "report_vs/artifacts/regenerate/expert_comment"
            result = render_artifact_json_model(
                namespace=namespace,
                variables={
                    "attempt_index": request.attempt_index,
                    "target_section": target.target_section,
                    "summary_json": _dump_json(summary),
                    "insights_final_json": _dump_json(insights_final),
                    "quotes_json": _dump_json(quotes_final),
                    "expert_domain": expert_domain,
                    "current_section_text": expert_comment,
                    "failure_reasons_json": _issues_json(target.issues),
                    "fix_checklist_json": _fix_checklist_json(target),
                    "grounding_package_json": _dump_json(grounding_package),
                },
                settings=request.settings,
                ctx=target_ctx,
                openai_client=openai_client,
                prompt_client=prompt_client,
                allow_vector_store=artifact_use_vector_store,
                vector_store_id=request.vector_store_id,
            )
            expert_comment = _s(result.get("expert_comment"))
            regenerated_sections.append("expert_comment")
            prompt_namespaces.append(namespace)
        elif target.target_section == "linkedin_post":
            normalize_artifact_evidence_ids(
                summary=summary,
                insights_candidates=insights_candidates,
                insights_final=insights_final,
                quotes_final=quotes_final,
                doc_map=safe_doc_map,
                evidence_packs=safe_evidence,
            )
            namespace = "report_vs/artifacts/regenerate/linkedin_post"
            result = render_artifact_json_model(
                namespace=namespace,
                variables={
                    "attempt_index": request.attempt_index,
                    "target_section": target.target_section,
                    "summary_json": _dump_json(summary),
                    "insights_final_json": _dump_json(insights_final),
                    "current_section_text": linkedin_post,
                    "failure_reasons_json": _issues_json(target.issues),
                    "fix_checklist_json": _fix_checklist_json(target),
                    "grounding_package_json": _dump_json(grounding_package),
                },
                settings=request.settings,
                ctx=target_ctx,
                openai_client=openai_client,
                prompt_client=prompt_client,
                allow_vector_store=artifact_use_vector_store,
                vector_store_id=request.vector_store_id,
            )
            linkedin_post = strip_artifact_inline_reference_ids(
                _s(result.get("linkedin_post"))
            )
            regenerated_sections.append("linkedin_post")
            prompt_namespaces.append(namespace)
        logger.info(
            log_event(
                target_ctx,
                role="generator",
                event="artifact_regeneration_target_complete",
                module=logger.name,
                fields={
                    "target_section": target.target_section,
                    "regenerated_sections": list(regenerated_sections),
                },
            )
        )

    updated_artifacts = assemble_artifacts_payload(
        report_id=request.report_id,
        report_name=request.report_name,
        doc_map=safe_doc_map,
        evidence_packs=safe_evidence,
        toc_topics=toc_topics,
        summary=summary,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        expert_comment=expert_comment,
        linkedin_post=linkedin_post,
        source_status=availability,
        ctx=ctx,
    )
    artifacts_path = store_artifacts_payload(
        analysis_store=analysis_store,
        output_dir=request.settings.output_dir,
        report_id=request.report_id,
        report_name=request.report_name,
        payload=updated_artifacts,
        ctx=ctx,
        pack_name="artifacts",
    )
    artifacts_snapshot_path = store_artifacts_payload(
        analysis_store=analysis_store,
        output_dir=request.settings.output_dir,
        report_id=request.report_id,
        report_name=request.report_name,
        payload=updated_artifacts,
        ctx=ctx,
        pack_name=f"artifacts_regen_attempt_{request.attempt_index}",
    )
    response = ArtifactRegenerationResponse(
        updated_artifacts=updated_artifacts,
        regenerated_sections=regenerated_sections,
        prompt_namespaces=prompt_namespaces,
        artifacts_path=artifacts_path,
        artifacts_snapshot_path=artifacts_snapshot_path,
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
                "regenerated_sections": regenerated_sections,
                "artifacts_path": artifacts_path,
                "artifacts_snapshot_path": artifacts_snapshot_path,
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
    summary = _copy_dict(artifacts.get("summary"))
    if _s(summary.get("tldr")).strip():
        payload.tldr = _s(summary.get("tldr"))
    if _s(summary.get("executive_summary")).strip():
        payload.commentary = _s(summary.get("executive_summary"))
    payload.insights = [
        _s(entry.get("text"))
        for entry in _copy_list(artifacts.get("insights_final"))[:5]
        if isinstance(entry, dict)
    ]
    while len(payload.insights) < 5:
        payload.insights.append("")
    quotes = _copy_list(artifacts.get("quotes_final"))
    if quotes and isinstance(quotes[0], dict):
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
            {"idx": window.idx, "text": window.text}
            for window in evidence_windows[:4]
        ],
        "evidence_ids": _unique_strings(
            evidence_id
            for issue in target.issues
            for evidence_id in issue.evidence_ids
        ),
        "pages": _unique_ints(
            page for issue in target.issues for page in issue.pages
        ),
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
    toc_topics: List[str],
    summary: Dict[str, Any],
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    expert_comment: str,
    linkedin_post: str,
    source_status: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "toc_topics": deepcopy(toc_topics),
        "summary": deepcopy(summary),
        "insights_candidates": deepcopy(insights_candidates),
        "insights_final": deepcopy(insights_final),
        "quotes_final": deepcopy(quotes_final),
        "expert_comment": expert_comment,
        "linkedin_post": linkedin_post,
        "source_status": deepcopy(source_status),
    }


def _current_section_payload(target_section: str, artifacts: Dict[str, Any]) -> Any:
    if target_section == "summary":
        return _copy_dict(artifacts.get("summary"))
    if target_section == "insights_bundle":
        return {
            "insights_candidates": _copy_list(artifacts.get("insights_candidates")),
            "insights_final": _copy_list(artifacts.get("insights_final")),
        }
    if target_section == "quotes":
        return _copy_list(artifacts.get("quotes_final"))
    if target_section == "expert_comment":
        return _s(artifacts.get("expert_comment"))
    if target_section == "linkedin_post":
        return _s(artifacts.get("linkedin_post"))
    return {}


def _issues_json(issues: List[RegenerationIssue]) -> str:
    return _dump_json([asdict(issue) for issue in issues])


def _fix_checklist_json(target: RegenerationTarget) -> str:
    checklist = [
        "Address every listed validator failure directly.",
        "Remove unsupported claims instead of softening them.",
        "Use only grounded evidence from the supplied package.",
        "Preserve the required JSON schema exactly.",
    ]
    if target.target_section == "insights_bundle":
        checklist.append(
            "Each final insight must map cleanly to evidence_id and supporting evidence text."
        )
    if target.target_section == "quotes":
        checklist.append("Quotes must be verbatim or clearly supported by source evidence.")
    if target.target_section in {"expert_comment", "linkedin_post"}:
        checklist.append(
            "Do not introduce new claims that are absent from the updated summary/insights/quotes."
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


def _dump_json(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return ""


def _s(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)
