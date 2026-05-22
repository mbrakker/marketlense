from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.contracts.config import AppSettings
from src.contracts.prompts import PromptLoadRequest
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.semantic_ids import ReportId
from src.generators._artifact_generator.family_policy import (
    apply_artifact_family_policy,
)
from src.generators._artifact_generator.toc import (
    TOC_STRUCTURE_VERSION,
    TOPIC_BRIEF_MAPPING_VERSION,
    build_legacy_topic_briefs,
)
from src.generators.analysis_pack_cache import (
    CachedPackAdaptResult,
    load_cached_pack,
)
from src.generators.analysis_store_adapter import (
    resolve_pack_path as resolve_analysis_pack_path,
)
from src.generators.analysis_store_adapter import (
    store_pack as store_analysis_pack,
)
from src.generators.artifact_normalization import (
    bind_artifact_evidence_spans,
    normalize_artifact_evidence_ids,
    normalize_artifact_toc_entries,
)
from src.services import file_service
from src.services.schema_validator_service import (
    validate_evidence_references,
    validate_schema,
)
from src.utils.analysis_family import family_is_abstained
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.json_utils import safe_json_dumps
from src.utils.logging import log_event
from src.utils.model_resolver import resolve_model

logger = logging.getLogger("market_lense.artifact_generator")


def assemble_artifacts_payload(
    *,
    report_id: str,
    report_name: Optional[str],
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    toc_bundle: Dict[str, Any],
    summary: Dict[str, Any],
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    expert_comment: str,
    linkedin_post: str,
    source_status: Dict[str, Any],
    family_status: Dict[str, Dict[str, Any]],
    ctx: RunContext,
    cache_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    del report_id, report_name
    toc_entries = normalize_artifact_toc_entries(toc_bundle.get("toc_entries"))
    toc_topics = [
        _s(entry.get("display_title")).strip()
        for entry in toc_entries
        if _s(entry.get("display_title")).strip()
    ]
    topic_briefs = build_legacy_topic_briefs(toc_entries=toc_entries)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_topic_briefs_built",
            module=logger.name,
            fields={
                "topic_count": len(toc_topics),
                "toc_entry_count": len(toc_entries),
                "brief_count": len(topic_briefs),
                "briefs_with_summary": len(
                    [item for item in topic_briefs if _s(item.get("summary")).strip()]
                ),
                "briefs_with_key_points": len(
                    [
                        item
                        for item in topic_briefs
                        if isinstance(item.get("key_points"), list)
                        and len(item.get("key_points") or []) > 0
                    ]
                ),
            },
        )
    )
    evidence_id_stats = normalize_artifact_evidence_ids(
        summary=summary,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        doc_map=doc_map,
        evidence_packs=evidence_packs,
    )
    if evidence_id_stats.get("normalized_count", 0) > 0:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_evidence_ids_normalized",
                module=logger.name,
                fields=evidence_id_stats,
            )
        )
    evidence_span_stats = bind_artifact_evidence_spans(
        summary=summary,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        doc_map=doc_map,
        evidence_packs=evidence_packs,
    )
    if (
        evidence_span_stats.get("bound_count", 0) > 0
        or evidence_span_stats.get("unbound_count", 0) > 0
    ):
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_evidence_spans_bound",
                module=logger.name,
                fields=evidence_span_stats,
            )
        )
    artifacts_payload: Dict[str, Any] = {
        "schema_version": "1.0",
        "toc_entries": toc_entries,
        "toc_topics": toc_topics,
        "toc_topics_expanded": topic_briefs,
        "summary": summary,
        "insights_candidates": insights_candidates,
        "insights_final": insights_final,
        "quotes_final": quotes_final,
        "expert_comment": expert_comment,
        "linkedin_post": linkedin_post,
        "source_status": source_status,
        "family_status": family_status,
    }
    if cache_meta:
        artifacts_payload["_cache"] = dict(cache_meta)
    try:
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0",
                payload=artifacts_payload,
                schema_name="artifacts",
            ),
            ctx,
        )
        validate_evidence_references(artifacts_payload, evidence_packs, ctx)
        _validate_artifact_semantic_fields(artifacts_payload, ctx)
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_schema_validation_failed",
                module=logger.name,
                fields={"code": exc.code, "message": exc.message},
            )
        )
        raise
    return artifacts_payload


def store_artifacts_payload(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    report_name: Optional[str],
    payload: Dict[str, Any],
    ctx: RunContext,
    pack_name: str = "artifacts",
) -> str:
    output_path = _store_pack(
        analysis_store=analysis_store,
        output_dir=output_dir,
        report_id=report_id,
        pack_name=pack_name,
        payload=payload,
        ctx=ctx,
        report_slug=report_name,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_payload_stored",
            module=logger.name,
            fields={
                "report_id": report_id,
                "pack_name": pack_name,
                "path": output_path,
            },
        )
    )
    return output_path


def _has_evidence_content(
    doc_map: Dict[str, Any], evidence_packs: Dict[str, Any]
) -> bool:
    if isinstance(doc_map, dict):
        sections = doc_map.get("sections")
        if isinstance(sections, list) and len(sections) > 0:
            return True
    if not isinstance(evidence_packs, dict):
        return False
    for pack in evidence_packs.values():
        if not isinstance(pack, dict):
            continue
        if (
            pack.get("findings")
            or pack.get("quote_candidates")
            or pack.get("methods")
            or pack.get("scope")
            or pack.get("limitations")
            or pack.get("key_metrics")
            or pack.get("risk_register")
            or pack.get("recommendations")
            or pack.get("contradictions")
        ):
            return True
    return False


def _artifact_cache_meta(
    *,
    md5: str,
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    availability: Dict[str, Any],
    expert_domain: str,
    retrieval_mode: str,
    settings: AppSettings,
    prompt_client,
    ctx: RunContext,
) -> Dict[str, Any]:
    prompt_meta: Dict[str, Any] = {}
    namespaces = [
        "report_vs/artifacts/summary",
        "report_vs/artifacts/insights_candidates",
        "report_vs/artifacts/insights_final",
        "report_vs/artifacts/quotes",
        "report_vs/artifacts/expert_comment",
        "report_vs/artifacts/linkedin_post",
    ]
    for namespace in namespaces:
        prompt_set = prompt_client.load_prompt_set(
            PromptLoadRequest(schema_version="1.0", namespace=namespace), ctx
        )
        prompt_meta[namespace] = {
            "prompt_system_sha256": prompt_set.system.sha256,
            "prompt_user_sha256": prompt_set.user.sha256,
            "model": resolve_model(
                namespace, getattr(settings, "openai_models", {}), settings.openai_model
            ),
        }
    inputs_hash = sha256_json(
        {
            "doc_map": doc_map,
            "evidence_packs": evidence_packs,
            "availability": availability,
            "expert_domain": expert_domain,
        }
    )
    return {
        "schema_version": "1.0",
        "topic_brief_mapping_version": TOPIC_BRIEF_MAPPING_VERSION,
        "toc_structure_version": TOC_STRUCTURE_VERSION,
        "md5": md5,
        "inputs_sha256": inputs_hash,
        "prompts": prompt_meta,
        "temperature": settings.temperature,
        "seed": settings.openai_seed,
        "retrieval_mode": retrieval_mode,
    }


def _load_cached_artifacts(
    *,
    output_dir: str,
    report_id: str,
    report_name: Optional[str],
    cache_key: str,
    ctx: RunContext,
    analysis_store,
) -> Optional[Dict[str, Any]]:
    def _log_read_failed(exc: AppError, path: str) -> None:
        del path
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_cache_read_failed",
                module=logger.name,
                fields={"report_id": report_id, "error": exc.message},
            )
        )

    result = load_cached_pack(
        cache_key=cache_key,
        ctx=ctx,
        resolve_path=lambda: _resolve_pack_path(
            analysis_store=analysis_store,
            output_dir=output_dir,
            report_id=report_id,
            pack_name="artifacts",
            ctx=ctx,
            report_slug=report_name,
        ),
        read_text=file_service.read_text,
        on_read_failed=_log_read_failed,
        adapt_payload=lambda payload, path: _adapt_cached_artifacts_payload(
            payload=payload,
            path=path,
            report_id=report_id,
            ctx=ctx,
        ),
    )
    return result.value if result.status == "hit" else None


def _adapt_cached_artifacts_payload(
    *,
    payload: Dict[str, Any],
    path: str,
    report_id: str,
    ctx: RunContext,
) -> CachedPackAdaptResult[Dict[str, Any]]:
    payload = _attach_cached_artifact_family_status(payload)
    try:
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0",
                payload=payload,
                schema_name="artifacts",
            ),
            ctx,
        )
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_cache_invalid",
                module=logger.name,
                fields={
                    "report_id": report_id,
                    "path": path,
                    "code": exc.code,
                    "message": exc.message,
                },
            )
        )
        return CachedPackAdaptResult(
            schema_version="1.0",
            status="schema_invalid",
            value=None,
        )
    return CachedPackAdaptResult(
        schema_version="1.0",
        status="hit",
        value=payload,
    )


def _attach_cached_artifact_family_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    raw_summary = payload.get("summary")
    raw_insights_candidates = payload.get("insights_candidates")
    raw_insights_final = payload.get("insights_final")
    raw_quotes_final = payload.get("quotes_final")
    summary: Dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    insights_candidates: List[Dict[str, Any]] = (
        [item for item in raw_insights_candidates if isinstance(item, dict)]
        if isinstance(raw_insights_candidates, list)
        else []
    )
    insights_final: List[Dict[str, Any]] = (
        [item for item in raw_insights_final if isinstance(item, dict)]
        if isinstance(raw_insights_final, list)
        else []
    )
    quotes_final: List[Dict[str, Any]] = (
        [item for item in raw_quotes_final if isinstance(item, dict)]
        if isinstance(raw_quotes_final, list)
        else []
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
        summary=summary,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        expert_comment=_s(payload.get("expert_comment")),
        linkedin_post=_s(payload.get("linkedin_post")),
    )
    enriched = dict(payload)
    enriched["summary"] = summary
    enriched["insights_candidates"] = insights_candidates
    enriched["insights_final"] = insights_final
    enriched["quotes_final"] = quotes_final
    enriched["expert_comment"] = expert_comment
    enriched["linkedin_post"] = linkedin_post
    enriched["family_status"] = family_status
    return enriched


def _resolve_pack_path(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    pack_name: str,
    ctx: RunContext,
    report_slug: Optional[str],
) -> str:
    return resolve_analysis_pack_path(
        analysis_store=analysis_store,
        request=AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=ReportId(report_id),
            pack_name=pack_name,
            report_slug=report_slug,
        ),
        ctx=ctx,
    )


def _store_pack(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    pack_name: str,
    payload: Dict[str, Any],
    ctx: RunContext,
    report_slug: Optional[str],
) -> str:
    return store_analysis_pack(
        analysis_store=analysis_store,
        request=AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=ReportId(report_id),
            pack_name=pack_name,
            payload=payload,
            report_slug=report_slug,
        ),
        ctx=ctx,
    )


def _validate_artifact_semantic_fields(
    artifacts_payload: Dict[str, Any],
    ctx: RunContext,
) -> None:
    missing_fields: List[str] = []
    sentinel_values = {"not available from text"}
    raw_summary = artifacts_payload.get("summary")
    raw_insights_final = artifacts_payload.get("insights_final")
    raw_quotes_final = artifacts_payload.get("quotes_final")
    summary: Dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    insights_final: List[Dict[str, Any]] = (
        [item for item in raw_insights_final if isinstance(item, dict)]
        if isinstance(raw_insights_final, list)
        else []
    )
    quotes_final: List[Dict[str, Any]] = (
        [item for item in raw_quotes_final if isinstance(item, dict)]
        if isinstance(raw_quotes_final, list)
        else []
    )

    def _missing_text(value: Any) -> bool:
        text = _s(value).strip()
        return not text or text.lower() in sentinel_values

    summary_abstained = family_is_abstained(artifacts_payload, "summary")
    insights_abstained = family_is_abstained(artifacts_payload, "insights_bundle")
    quotes_abstained = family_is_abstained(artifacts_payload, "quotes")
    expert_abstained = family_is_abstained(artifacts_payload, "expert_comment")
    linkedin_abstained = family_is_abstained(artifacts_payload, "linkedin_post")

    if not summary_abstained and _missing_text(summary.get("tldr")):
        missing_fields.append("summary.tldr")
    if not summary_abstained and _missing_text(summary.get("executive_summary")):
        missing_fields.append("summary.executive_summary")
    if not summary_abstained:
        for index, claim in enumerate(summary.get("claim_evidence_map") or []):
            if not isinstance(claim, dict) or _missing_text(claim.get("claim")):
                continue
            if not (
                isinstance(claim.get("evidence_spans"), list)
                and (claim.get("evidence_spans") or [])
            ):
                missing_fields.append(
                    f"summary.claim_evidence_map[{index}].evidence_spans"
                )
    if not insights_abstained and len(insights_final) < 5:
        missing_fields.append("insights_final")
    for index, insight in enumerate(insights_final[:5]):
        if insights_abstained:
            break
        if not isinstance(insight, dict) or _missing_text(insight.get("text")):
            missing_fields.append(f"insights_final[{index}].text")
    if not quotes_abstained and not quotes_final:
        missing_fields.append("quotes_final")
    elif not quotes_abstained and (
        not isinstance(quotes_final[0], dict)
        or _missing_text(quotes_final[0].get("text"))
    ):
        missing_fields.append("quotes_final[0].text")
    if not expert_abstained and _missing_text(artifacts_payload.get("expert_comment")):
        missing_fields.append("expert_comment")
    if not linkedin_abstained and _missing_text(artifacts_payload.get("linkedin_post")):
        missing_fields.append("linkedin_post")

    if not missing_fields:
        return

    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_contract_incomplete",
            module=logger.name,
            fields={
                "missing_fields": missing_fields,
                "summary_abstained": summary_abstained,
                "insights_abstained": insights_abstained,
                "quotes_abstained": quotes_abstained,
                "expert_comment_abstained": expert_abstained,
                "linkedin_post_abstained": linkedin_abstained,
            },
        )
    )
    raise AppError(
        code="artifact_contract_incomplete",
        message="Artifact payload is missing required semantic fields",
        retryable=False,
        context={"missing_fields": missing_fields},
    )


def _dump_json(data: Any) -> str:
    return safe_json_dumps(data, ensure_ascii=False, fallback="")


def _s(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)
