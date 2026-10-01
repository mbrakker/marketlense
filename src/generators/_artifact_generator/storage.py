from __future__ import annotations

import hashlib
import logging
import re
from copy import deepcopy
from dataclasses import asdict, replace
from typing import Any, Dict, Iterable, List, Optional

from src.contracts.config import AppSettings
from src.contracts.prompts import PromptLoadRequest
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.report_cards import (
    DIRECTIONS,
    DOMAIN_LAYERS,
    EVIDENCE_DENSITIES,
    EVIDENCE_SHAPES,
    GEOGRAPHY_SCOPES,
)
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.semantic_ids import ReportId
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    align_soft_copy_claim_bindings_to_text,
    soft_copy_claim_provenance_from_payload,
    soft_copy_claim_provenance_to_payload,
    soft_copy_material_sentences,
    soft_copy_public_text,
)
from src.generators._artifact_generator.family_policy import (
    apply_artifact_family_policy,
    build_artifact_family_status,
)
from src.generators._artifact_generator.toc import (
    TOC_STRUCTURE_VERSION,
    TOPIC_BRIEF_MAPPING_VERSION,
    audit_topic_brief_mappings,
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
    artifact_evidence_span_index,
    bind_artifact_evidence_spans,
    carry_soft_copy_binding_semantics_to_final_sentences,
    constrain_summary_to_source_backed_claims,
    normalize_artifact_editorial_plan,
    normalize_artifact_evidence_ids,
    normalize_artifact_insights,
    normalize_artifact_toc_entries,
    preserve_public_source_displays,
    preserve_soft_copy_binding_source_displays,
    retain_bound_optional_soft_copy_sentences,
    source_backed_summary_claim_bindings,
    summary_has_unbound_material_sentences,
)
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
)
from src.generators.soft_copy_claim_provenance import (
    assert_retained_soft_copy_claims_match_public_copy,
    build_soft_copy_claim_provenance,
    retained_soft_copy_claims_cover_text,
)
from src.generators.validation.quantities import quantity_supported
from src.services import file_service
from src.services.prompt_service import build_llm_execution_identity
from src.services.schema_validator_service import (
    validate_evidence_references,
    validate_schema,
)
from src.utils.analysis_family import family_is_abstained
from src.utils.artifact_diff import artifact_diff_paths
from src.utils.cache_utils import sha256_json
from src.utils.coercion import string_value as _s
from src.utils.errors import AppError
from src.utils.json_utils import dump_json_text
from src.utils.logging import log_event
from src.utils.model_resolver import (
    execution_policies_from_config,
    resolve_execution_policy,
    resolve_routing_policy,
    routing_policies_from_config,
)
from src.utils.numeric_display import numeric_metadata_for_complete_display
from src.utils.public_metric_display import normalize_public_metric_display
from src.utils.quantity import extract_quantities

ARTIFACT_ROOT_DEPENDENCIES = {
    "metric_spine": frozenset({"insights_final", "editorial_plan"}),
    "topics_covered": frozenset({"toc_entries", "summary", "insights_final"}),
    "key_figures": frozenset(
        {"insights_final", "summary", "editorial_plan", "metric_spine"}
    ),
    "chart_insight_cards": frozenset({"insights_final", "key_figures", "summary"}),
    "executive_advisory": frozenset(
        {"insights_final", "summary", "quotes_final", "metric_spine"}
    ),
    "claim_ledgers": frozenset(
        {
            "insights_final",
            "summary",
            "quotes_final",
            "metric_spine",
            "executive_advisory",
        }
    ),
    "family_status": frozenset(
        {
            "summary",
            "insights_candidates",
            "insights_final",
            "quotes_final",
            "expert_comment",
            "linkedin_post",
        }
    ),
    "soft_copy_claim_provenance": frozenset(
        {"summary", "expert_comment", "linkedin_post"}
    ),
    "_repair_evidence_selection": frozenset(
        {"summary", "expert_comment", "linkedin_post"}
    ),
    "_cache": frozenset(
        {
            "summary",
            "insights_candidates",
            "insights_final",
            "quotes_final",
            "expert_comment",
            "linkedin_post",
        }
    ),
}
CANONICAL_DERIVED_ARTIFACT_ROOTS = frozenset(
    {
        "metric_spine",
        "topics_covered",
        "key_figures",
        "chart_insight_cards",
        "executive_advisory",
        "claim_ledgers",
        "family_status",
    }
)
REGENERATION_PRIVATE_METADATA_ROOTS = frozenset(
    {"_cache", "_repair_evidence_selection"}
)

logger = logging.getLogger("market_lense.artifact_generator")
EVIDENCE_QUALITY_BY_SUPPORT_TYPE = {
    "direct_evidence_span": "direct_evidence_span",
    "direct_metric": "direct_metric",
    "direct_quote": "direct_quote",
    "chart_readout": "chart_readout",
    "explicit_recommendation": "explicit_recommendation",
    "explicit_risk": "explicit_risk",
    "canonical_evidence_id": "source_backed",
}


def _dump_json(value: Any) -> str:
    return dump_json_text(value)


def _abstain_summary_without_short_direct_claim(
    *,
    summary: Dict[str, Any],
    family_status: Dict[str, Dict[str, Any]],
) -> None:
    """Abstain the summary family when no direct claim can fill compact copy."""

    summary.clear()
    summary.update(
        {
            "tldr": "",
            "card_tldr_compact": "",
            "executive_summary": "",
            "claim_evidence_map": [],
        }
    )
    family_status["summary"].update(
        {
            "status": "abstained",
            "policy_action": "abstain",
            "reason": "summary_no_short_direct_claim",
        }
    )


def assemble_artifacts_payload(
    *,
    report_id: str,
    report_name: Optional[str],
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    toc_bundle: Dict[str, Any],
    editorial_plan: Dict[str, Any],
    summary: Dict[str, Any],
    cover_semantics: Dict[str, str],
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    expert_comment: str,
    linkedin_post: str,
    source_status: Dict[str, Any],
    family_status: Dict[str, Dict[str, Any]],
    ctx: RunContext,
    category_ids: Optional[List[str]] = None,
    cache_meta: Optional[Dict[str, Any]] = None,
    soft_copy_claim_bindings: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    soft_copy_prompt_identities: Optional[Dict[str, Dict[str, Any]]] = None,
    soft_copy_generation_attempts: Optional[Dict[str, int]] = None,
    existing_soft_copy_claim_provenance: Optional[Dict[str, Any]] = None,
    replaced_soft_copy_families: Optional[List[str]] = None,
    replaced_soft_copy_claim_ids: Optional[Dict[str, List[str]]] = None,
    soft_copy_repair_texts: Optional[Dict[str, List[str]]] = None,
    soft_copy_repair_lineage: Optional[Dict[str, str]] = None,
    regeneration_attempt: int = 0,
    validate_references: bool = True,
) -> Dict[str, Any]:
    del report_name
    soft_copy_claim_bindings = deepcopy(soft_copy_claim_bindings or {})
    editorial_plan = normalize_artifact_editorial_plan(editorial_plan)
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
        editorial_plan=editorial_plan,
        soft_copy_claim_provenance={
            "claims": [
                binding
                for bindings in (soft_copy_claim_bindings or {}).values()
                if isinstance(bindings, list)
                for binding in bindings
                if isinstance(binding, dict)
            ]
        },
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
    try:
        summary_fallback_applied = constrain_summary_to_source_backed_claims(summary)
    except AppError as exc:
        if exc.code != "card_tldr_compact_invalid":
            raise
        _abstain_summary_without_short_direct_claim(
            summary=summary,
            family_status=family_status,
        )
        soft_copy_claim_bindings["summary"] = []
        summary_fallback_applied = False
    pre_correction_soft_copy = {
        "summary": deepcopy(summary),
        "expert_comment": expert_comment,
        "linkedin_post": linkedin_post,
    }
    pre_correction_bindings = deepcopy(soft_copy_claim_bindings)
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
    expert_comment, linkedin_post = preserve_public_source_displays(
        summary=summary,
        insights_final=insights_final,
        expert_comment=expert_comment,
        linkedin_post=linkedin_post,
    )
    if summary_fallback_applied:
        soft_copy_claim_bindings["summary"] = source_backed_summary_claim_bindings(
            summary
        )
    preserve_soft_copy_binding_source_displays(
        summary=summary,
        insights_final=insights_final,
        soft_copy_claim_bindings=soft_copy_claim_bindings,
    )
    retained_summary_claims = (
        [
            claim
            for claim in soft_copy_claim_provenance_from_payload(
                existing_soft_copy_claim_provenance
            )
            if claim.artifact_family == "summary"
        ]
        if isinstance(existing_soft_copy_claim_provenance, dict)
        and isinstance(existing_soft_copy_claim_provenance.get("claims"), list)
        else []
    )
    summary_already_bound = not soft_copy_claim_bindings.get(
        "summary"
    ) and retained_soft_copy_claims_cover_text(
        text=soft_copy_public_text("summary", summary),
        claims=retained_summary_claims,
    )
    if (
        not summary_fallback_applied
        and "summary" not in (soft_copy_repair_texts or {})
        and not summary_already_bound
        and summary_has_unbound_material_sentences(
            summary=summary,
            claim_bindings=soft_copy_claim_bindings.get("summary"),
        )
    ):
        try:
            summary_fallback_applied = constrain_summary_to_source_backed_claims(
                summary,
                require_direct_fallback=True,
            )
        except AppError as exc:
            if exc.code != "card_tldr_compact_invalid":
                raise
            _abstain_summary_without_short_direct_claim(
                summary=summary,
                family_status=family_status,
            )
            soft_copy_claim_bindings["summary"] = []
            summary_fallback_applied = False
        if summary_fallback_applied:
            preserve_public_source_displays(
                summary=summary,
                insights_final=insights_final,
                expert_comment="",
                linkedin_post="",
            )
            soft_copy_claim_bindings["summary"] = source_backed_summary_claim_bindings(
                summary
            )
            preserve_soft_copy_binding_source_displays(
                summary=summary,
                insights_final=insights_final,
                soft_copy_claim_bindings=soft_copy_claim_bindings,
            )
        else:
            _abstain_summary_without_short_direct_claim(
                summary=summary,
                family_status=family_status,
            )
            soft_copy_claim_bindings["summary"] = []
    if "expert_comment" not in (soft_copy_repair_texts or {}):
        expert_comment = retain_bound_optional_soft_copy_sentences(
            artifact_family="expert_comment",
            public_text=expert_comment,
            claim_bindings=soft_copy_claim_bindings.get("expert_comment"),
        )
    if "linkedin_post" not in (soft_copy_repair_texts or {}):
        linkedin_post = retain_bound_optional_soft_copy_sentences(
            artifact_family="linkedin_post",
            public_text=linkedin_post,
            claim_bindings=soft_copy_claim_bindings.get("linkedin_post"),
        )
    for family, final_public_output in {
        "summary": summary,
        "expert_comment": expert_comment,
        "linkedin_post": linkedin_post,
    }.items():
        if family == "summary" and summary_fallback_applied:
            continue
        carried = carry_soft_copy_binding_semantics_to_final_sentences(
            artifact_family=family,
            original_public_text=pre_correction_soft_copy[family],
            final_public_text=final_public_output,
            original_claim_bindings=pre_correction_bindings.get(family),
        )
        if carried:
            soft_copy_claim_bindings[family] = carried
    metric_spine = derive_metric_spine_from_insights(
        insights_final, editorial_plan=editorial_plan
    )
    topics_covered = build_topics_covered(
        toc_entries=toc_entries,
        evidence_packs=evidence_packs,
        summary=summary,
        insights_final=insights_final,
    )
    key_figures = build_key_figures(
        metric_spine=metric_spine,
        evidence_packs=evidence_packs,
        summary=summary,
        insights_final=insights_final,
        editorial_plan=editorial_plan,
    )
    chart_insight_cards = build_chart_insight_cards(
        key_figures=key_figures,
        evidence_packs=evidence_packs,
        insights_final=insights_final,
    )
    artifacts_payload: Dict[str, Any] = {
        "schema_version": "3.0",
        "categories": list(
            dict.fromkeys(
                _s(category_id).strip()
                for category_id in (category_ids or [])
                if _s(category_id).strip()
            )
        ),
        "editorial_plan": editorial_plan,
        "toc_entries": toc_entries,
        "toc_topics": toc_topics,
        "toc_topics_expanded": topic_briefs,
        "metric_spine": metric_spine,
        "topics_covered": topics_covered,
        "key_figures": key_figures,
        "chart_insight_cards": chart_insight_cards,
        "summary": summary,
        "cover_semantics": _validate_cover_semantics(cover_semantics, ctx=ctx),
        "insights_candidates": insights_candidates,
        "insights_final": insights_final,
        "quotes_final": quotes_final,
        "expert_comment": expert_comment,
        "linkedin_post": linkedin_post,
        "source_status": source_status,
        "family_status": family_status,
    }
    completed_summary_bindings, recovered_summary_binding_count = (
        _complete_summary_bindings_from_exact_direct_claims(
            summary=summary,
            bindings=soft_copy_claim_bindings.get("summary"),
        )
        if not summary_already_bound
        else (soft_copy_claim_bindings.get("summary") or [], 0)
    )
    if recovered_summary_binding_count:
        soft_copy_claim_bindings["summary"] = completed_summary_bindings
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_summary_provenance_completed_from_direct_claim_map",
                module=logger.name,
                fields={"binding_count": recovered_summary_binding_count},
            )
        )
    artifacts_payload["soft_copy_claim_provenance"] = (
        _soft_copy_claim_provenance_payload(
            summary=summary,
            expert_comment=expert_comment,
            linkedin_post=linkedin_post,
            doc_map=doc_map,
            evidence_packs=evidence_packs,
            bindings=soft_copy_claim_bindings,
            prompt_identities=soft_copy_prompt_identities or {},
            generation_attempts=soft_copy_generation_attempts or {},
            existing_provenance=existing_soft_copy_claim_provenance,
            replaced_families=replaced_soft_copy_families or [],
            replaced_claim_ids=replaced_soft_copy_claim_ids or {},
            repair_texts=soft_copy_repair_texts or {},
            repair_lineage=soft_copy_repair_lineage or {},
            regeneration_attempt=regeneration_attempt,
        )
    )
    normalize_artifact_evidence_ids(
        summary=summary,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        doc_map=doc_map,
        evidence_packs=evidence_packs,
        editorial_plan=editorial_plan,
        soft_copy_claim_provenance=artifacts_payload["soft_copy_claim_provenance"],
    )
    artifacts_payload["executive_advisory"] = build_executive_advisory_artifacts(
        summary=summary,
        insights_final=insights_final,
        quotes_final=quotes_final,
        metric_spine=metric_spine,
        evidence_packs=evidence_packs,
    )
    artifacts_payload["claim_ledgers"] = build_universal_claim_ledger(
        report_id=report_id,
        summary=summary,
        insights_final=insights_final,
        quotes_final=quotes_final,
        metric_spine=metric_spine,
        executive_advisory=artifacts_payload["executive_advisory"],
    )
    if cache_meta:
        artifacts_payload["_cache"] = dict(cache_meta)
    _log_topic_brief_mapping_audit(
        topic_briefs=topic_briefs,
        doc_map=doc_map,
        ctx=ctx,
    )
    try:
        assert_retained_soft_copy_claims_match_public_copy(artifacts_payload)
        _validate_artifact_semantic_fields(artifacts_payload, ctx)
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0",
                payload=artifacts_payload,
                schema_name="artifacts",
            ),
            ctx,
        )
        if validate_references:
            validate_evidence_references(
                artifacts_payload,
                {**evidence_packs, "doc_map": doc_map},
                ctx,
            )
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


def _soft_copy_claim_provenance_payload(
    *,
    summary: Dict[str, Any],
    expert_comment: str,
    linkedin_post: str,
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    bindings: Dict[str, List[Dict[str, Any]]],
    prompt_identities: Dict[str, Dict[str, Any]],
    generation_attempts: Dict[str, int],
    existing_provenance: Optional[Dict[str, Any]],
    replaced_families: List[str],
    replaced_claim_ids: Dict[str, List[str]],
    repair_texts: Dict[str, List[str]],
    repair_lineage: Dict[str, str],
    regeneration_attempt: int,
) -> Dict[str, Any]:
    public_output_by_family = {
        "summary": summary,
        "expert_comment": expert_comment,
        "linkedin_post": linkedin_post,
    }
    span_index = artifact_evidence_span_index(
        doc_map=doc_map,
        evidence_packs=evidence_packs,
    )
    replaced = {str(family).strip() for family in replaced_families}
    replaced_ids = {
        str(family).strip(): {
            str(claim_id).strip() for claim_id in claim_ids if str(claim_id).strip()
        }
        for family, claim_ids in replaced_claim_ids.items()
        if isinstance(claim_ids, list)
    }
    claims: List[SoftCopyClaimProvenance] = []
    for claim in (
        soft_copy_claim_provenance_from_payload(existing_provenance)
        if isinstance(existing_provenance, dict)
        and isinstance(existing_provenance.get("claims"), list)
        else []
    ):
        if (
            claim.artifact_family in replaced
            or claim.claim_id in replaced_ids.get(claim.artifact_family, set())
        ):
            continue
        if any(existing == claim for existing in claims):
            continue
        claims.append(claim)
    public_sentence_hashes = {
        family: {
            hashlib.sha256(sentence.encode("utf-8")).hexdigest()
            for sentence in soft_copy_material_sentences(
                soft_copy_public_text(family, public_output)
            )
        }
        for family, public_output in public_output_by_family.items()
    }
    claims = [
        claim
        for claim in claims
        if claim.artifact_family not in public_sentence_hashes
        or claim.text_hash in public_sentence_hashes[claim.artifact_family]
    ]
    for family, public_output in public_output_by_family.items():
        text = soft_copy_public_text(family, public_output)
        declared = bindings.get(family)
        if family in repair_texts:
            final_sentences = set(soft_copy_material_sentences(text))
            retained_hashes = {
                claim.text_hash for claim in claims if claim.artifact_family == family
            }
            for repaired_text in repair_texts[family]:
                # A repair may later be rolled back by validation. Only carry
                # provenance from the repair for sentences that still occur on
                # the canonical final public sentence grid.
                retained_repair_sentences = [
                    sentence
                    for sentence in soft_copy_material_sentences(
                        str(repaired_text or "")
                    )
                    if sentence in final_sentences
                ]
                if not retained_repair_sentences:
                    continue
                repair_text = " ".join(retained_repair_sentences)
                retained_repair_set = set(retained_repair_sentences)
                repaired_bindings = [
                    binding
                    for binding in declared or []
                    if isinstance(binding, dict)
                    and " ".join(str(binding.get("claim") or "").split())
                    in retained_repair_set
                ]
                repaired_claims = build_soft_copy_claim_provenance(
                    artifact_family=family,
                    text=repair_text,
                    declared_claims=repaired_bindings,
                    evidence_span_index=span_index,
                    producing_prompt_identity=dict(prompt_identities.get(family) or {}),
                    generation_attempt=max(
                        1, int(generation_attempts.get(family) or 1)
                    ),
                    regeneration_attempt=regeneration_attempt,
                )
                for claim in repaired_claims:
                    # A family repair can carry bindings for every public
                    # sentence, including unchanged sentences already
                    # retained above. Keep each canonical sentence identity
                    # once and preserve its existing semantic binding.
                    if claim.text_hash in retained_hashes:
                        continue
                    claims.append(
                        replace(
                            claim,
                            repaired_from_claim_id=repair_lineage.get(
                                f"{family}:{claim.claim_id}", ""
                            ),
                        )
                    )
                    retained_hashes.add(claim.text_hash)
        elif text:
            retained = [claim for claim in claims if claim.artifact_family == family]
            if not isinstance(declared, list) or not declared:
                if not retained_soft_copy_claims_cover_text(text=text, claims=retained):
                    build_soft_copy_claim_provenance(
                        artifact_family=family,
                        text=text,
                        declared_claims=declared,
                        evidence_span_index=span_index,
                        producing_prompt_identity=dict(
                            prompt_identities.get(family) or {}
                        ),
                        generation_attempt=max(
                            1, int(generation_attempts.get(family) or 1)
                        ),
                        regeneration_attempt=regeneration_attempt,
                    )
            else:
                # A complete prompt-family output is re-finalized as one
                # canonical public surface. Its model-declared bindings
                # therefore replace every earlier retained claim for that
                # family; carrying an obsolete claim forward would make the
                # public/provenance invariant fail after a deterministic
                # correction or a fresh materialization.
                claims = [claim for claim in claims if claim.artifact_family != family]
                claims.extend(
                    build_soft_copy_claim_provenance(
                        artifact_family=family,
                        text=text,
                        declared_claims=declared,
                        evidence_span_index=span_index,
                        producing_prompt_identity=dict(
                            prompt_identities.get(family) or {}
                        ),
                        generation_attempt=max(
                            1, int(generation_attempts.get(family) or 1)
                        ),
                        regeneration_attempt=regeneration_attempt,
                    )
                )
        # Repair state can outlive a candidate copy that was later rolled back.
        # Retain provenance only for sentences in the canonical final public
        # text; the exact coverage check below still blocks any unbound sentence.
        claims = [
            claim
            for claim in claims
            if claim.artifact_family != family
            or claim.text_hash in public_sentence_hashes[family]
        ]
        family_claims = [claim for claim in claims if claim.artifact_family == family]
        if not retained_soft_copy_claims_cover_text(text=text, claims=family_claims):
            raise AppError(
                code="soft_copy_claim_provenance_coverage_invalid",
                message="Soft-copy claim provenance must exactly cover public prose",
                retryable=False,
                context={"artifact_family": family},
            )
    return soft_copy_claim_provenance_to_payload(claims)


def _complete_summary_bindings_from_exact_direct_claims(
    *,
    summary: Dict[str, Any],
    bindings: object,
) -> tuple[List[Dict[str, Any]], int]:
    """Recover only uncovered summary sentences with one exact direct source row."""

    public_text = soft_copy_public_text("summary", summary)
    sentences = soft_copy_material_sentences(public_text)
    declared = (
        [dict(binding) for binding in bindings if isinstance(binding, dict)]
        if isinstance(bindings, list)
        else []
    )
    if not sentences:
        return declared, 0

    aligned = align_soft_copy_claim_bindings_to_text(
        artifact_family="summary",
        text=public_text,
        claim_bindings=declared,
    )
    covered_sentences = {
        " ".join(str(binding.get("claim") or "").split())
        for binding in aligned
        if isinstance(binding, dict)
    }
    if all(sentence in covered_sentences for sentence in sentences):
        return declared, 0

    direct_by_sentence: Dict[str, Dict[tuple[str, ...], Dict[str, Any]]] = {}
    for binding in source_backed_summary_claim_bindings(summary):
        claim_sentences = soft_copy_material_sentences(binding.get("claim"))
        if len(claim_sentences) != 1:
            continue
        sentence = claim_sentences[0]
        evidence_ids = tuple(
            dict.fromkeys(
                str(value).strip()
                for value in binding.get("evidence_ids", [])
                if str(value).strip()
            )
        )
        if not evidence_ids:
            continue
        direct_by_sentence.setdefault(sentence, {})[evidence_ids] = {
            **binding,
            "claim": sentence,
        }

    recovered: List[Dict[str, Any]] = []
    for sentence in dict.fromkeys(sentences):
        if sentence in covered_sentences:
            continue
        matches = list(direct_by_sentence.get(sentence, {}).values())
        if len(matches) == 1:
            recovered.append(matches[0])
    return [*declared, *recovered], len(recovered)


def build_universal_claim_ledger(
    *,
    report_id: str,
    summary: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    metric_spine: List[Dict[str, Any]],
    executive_advisory: Dict[str, Any],
) -> List[Dict[str, Any]]:
    ledger: List[Dict[str, Any]] = []

    def _evidence_ids(*values: Any) -> List[str]:
        ids: List[str] = []
        for value in values:
            if isinstance(value, str):
                text = value.strip()
                if text:
                    ids.append(text)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        ids.append(item.strip())
                    elif isinstance(item, dict):
                        evidence_id = _s(item.get("evidence_id")).strip()
                        if evidence_id:
                            ids.append(evidence_id)
        return sorted(dict.fromkeys(ids))

    def _append(
        *,
        artifact_section: str,
        local_id: str,
        claim_text: str,
        evidence_ids: List[str],
        spans: Any = None,
        support_type: str = "",
        confidence: str = "source_backed",
        risk: str = "low",
        evidence_quality_grade: str = "",
    ) -> None:
        text = " ".join(_s(claim_text).split())
        if not text or not evidence_ids:
            return
        span_count = len(spans) if isinstance(spans, list) else 0
        resolved_support = support_type or (
            "direct_evidence_span" if span_count else "canonical_evidence_id"
        )
        ledger.append(
            {
                "schema_version": "1.0",
                "canonical_claim_id": f"{report_id}:{artifact_section}:{local_id}",
                "claim_text": text,
                "artifact_section": artifact_section,
                "evidence_ids": evidence_ids,
                "support_type": resolved_support,
                "evidence_quality_grade": (
                    _s(evidence_quality_grade).strip()
                    or EVIDENCE_QUALITY_BY_SUPPORT_TYPE.get(
                        resolved_support, "source_backed"
                    )
                ),
                "confidence": confidence,
                "risk": risk,
                "evidence_span_count": span_count,
            }
        )

    for index, claim in enumerate(summary.get("claim_evidence_map") or [], start=1):
        if not isinstance(claim, dict):
            continue
        spans = claim.get("evidence_spans")
        _append(
            artifact_section="summary.claim_evidence_map",
            local_id=str(index),
            claim_text=_s(claim.get("claim")),
            evidence_ids=_evidence_ids(claim.get("evidence_id"), spans),
            spans=spans,
        )
    for item in insights_final:
        if not isinstance(item, dict):
            continue
        spans = item.get("evidence_spans")
        _append(
            artifact_section="insights_final",
            local_id=_s(item.get("id")).strip() or str(len(ledger) + 1),
            claim_text=_s(item.get("text")),
            evidence_ids=_evidence_ids(item.get("evidence_id"), spans),
            spans=spans,
        )
    for item in metric_spine:
        if not isinstance(item, dict):
            continue
        label = _s(item.get("label")).strip()
        value = _s(item.get("value")).strip()
        unit = _s(item.get("unit")).strip()
        claim_text = " ".join(part for part in (label, value, unit) if part)
        _append(
            artifact_section="metric_spine",
            local_id=_s(item.get("metric_id")).strip() or str(len(ledger) + 1),
            claim_text=claim_text,
            evidence_ids=_evidence_ids(item.get("evidence_id")),
            support_type="direct_metric",
            confidence=_s(item.get("confidence")).strip() or "source_backed",
            risk="medium" if item.get("missing_context_notes") else "low",
        )
    advisory = executive_advisory if isinstance(executive_advisory, dict) else {}
    recommendations = advisory.get("recommendations")
    if isinstance(recommendations, dict):
        for index, item in enumerate(recommendations.get("items") or [], start=1):
            if not isinstance(item, dict):
                continue
            _append(
                artifact_section="executive_advisory.recommendations",
                local_id=_s(item.get("id")).strip() or str(index),
                claim_text=_s(item.get("recommendation") or item.get("text")),
                evidence_ids=_evidence_ids(item.get("evidence_id")),
                support_type="explicit_recommendation",
                risk="medium",
            )
    risks = advisory.get("risks")
    if isinstance(risks, dict):
        for index, item in enumerate(risks.get("items") or [], start=1):
            if not isinstance(item, dict):
                continue
            _append(
                artifact_section="executive_advisory.risks",
                local_id=_s(item.get("id")).strip() or str(index),
                claim_text=_s(item.get("risk") or item.get("text")),
                evidence_ids=_evidence_ids(item.get("evidence_id")),
                support_type="explicit_risk",
                risk="medium",
            )
    for index, quote in enumerate(quotes_final, start=1):
        if not isinstance(quote, dict):
            continue
        spans = quote.get("evidence_spans")
        _append(
            artifact_section="quotes_final",
            local_id=_s(quote.get("id")).strip() or str(index),
            claim_text=_s(quote.get("text")),
            evidence_ids=_evidence_ids(quote.get("evidence_id"), spans),
            spans=spans,
            support_type="direct_quote",
        )
    return ledger


def derive_metric_spine_from_insights(
    insights_final: List[Dict[str, Any]],
    *,
    editorial_plan: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return _derive_metric_spine_from_insights(
        insights_final,
        editorial_plan=editorial_plan,
        limit=6,
    )


def _derive_metric_spine_from_insights(
    insights_final: List[Dict[str, Any]],
    *,
    editorial_plan: Dict[str, Any] | None,
    limit: int | None,
) -> List[Dict[str, Any]]:
    spine: List[Dict[str, Any]] = []
    for index, insight in enumerate(insights_final, start=1):
        if not isinstance(insight, dict):
            continue
        metric = insight.get("metric")
        if not isinstance(metric, dict):
            continue
        raw_value = _s(metric.get("value") or metric.get("raw_value")).strip()
        raw_unit = _s(metric.get("unit")).strip()
        value, unit = normalize_public_metric_display(value=raw_value, unit=raw_unit)
        if not value and _is_coherent_metric_display(raw_value, raw_unit):
            value, unit = raw_value, raw_unit
        evidence_id = _s(
            insight.get("evidence_id") or metric.get("evidence_id")
        ).strip()
        label = _s(metric.get("label") or metric.get("metric")).strip()
        if not label:
            label = _metric_label_from_insight_text(
                _s(insight.get("text")).strip(), value=value
            )
        if not label and _metric_text_is_unambiguous(
            text=_s(insight.get("text")).strip(), value=value
        ):
            label = _s(insight.get("text")).strip()
        if not value or not evidence_id or not _is_complete_metric_label(label):
            continue
        missing_context_notes = [
            field_name
            for field_name in ("timeframe", "segment", "geography")
            if not _s(metric.get(field_name)).strip()
        ]
        item: Dict[str, Any] = {
            "schema_version": "1.0",
            "metric_id": _s(insight.get("id") or metric.get("metric_id")).strip()
            or f"insight_metric_{index}",
            "label": label,
            "value": value,
            "unit": unit,
            "timeframe": _s(metric.get("timeframe")).strip(),
            "segment": _s(metric.get("segment")).strip(),
            "geography": _s(metric.get("geography")).strip(),
            "comparator": _s(metric.get("comparator")).strip(),
            "baseline": _s(metric.get("baseline")).strip(),
            "delta": _s(metric.get("delta") or metric.get("trend")).strip(),
            "sample_size": _s(metric.get("sample_size")).strip(),
            "subject": _s(metric.get("subject")).strip(),
            "cohort": _s(metric.get("cohort")).strip(),
            "denominator": _s(metric.get("denominator")).strip(),
            "observation_status": _s(
                metric.get("observation_status") or metric.get("forecast_status")
            ).strip(),
            "confidence": _s(metric.get("confidence")).strip() or "source_backed",
            "missing_context_notes": missing_context_notes,
            "evidence_id": evidence_id,
        }
        numeric_metadata = numeric_metadata_for_complete_display(value)
        if numeric_metadata is not None:
            item["source_display_value"] = value
            item["numeric_metadata"] = numeric_metadata
        spine.append(item)
    return _rank_metric_spine(spine, editorial_plan=editorial_plan, limit=limit)


def _rank_metric_spine(
    metrics: List[Dict[str, Any]],
    *,
    editorial_plan: Dict[str, Any] | None,
    limit: int | None = 6,
) -> List[Dict[str, Any]]:
    ranked = sorted(
        metrics,
        key=lambda item: (
            *_metric_editorial_rank(item, editorial_plan=editorial_plan),
            len(item.get("missing_context_notes") or []),
            _s(item.get("metric_id")).strip(),
            _s(item.get("label")).strip(),
        ),
    )
    return ranked[:limit] if limit is not None else ranked


def _metric_editorial_rank(
    metric: Dict[str, Any],
    *,
    editorial_plan: Dict[str, Any] | None,
) -> tuple[int, int]:
    evidence_id = _s(metric.get("evidence_id")).strip().casefold()
    raw_themes = (
        editorial_plan.get("themes") if isinstance(editorial_plan, dict) else []
    )
    themes = raw_themes if isinstance(raw_themes, list) else []
    priorities: List[int] = []
    for theme in themes:
        if not isinstance(theme, dict):
            continue
        priority = theme.get("priority")
        evidence_ids = theme.get("evidence_ids")
        if (
            not isinstance(priority, int)
            or priority <= 0
            or not isinstance(evidence_ids, list)
            or not evidence_id
        ):
            continue
        if evidence_id in {
            _s(theme_evidence_id).strip().casefold()
            for theme_evidence_id in evidence_ids
        }:
            priorities.append(priority)
    if priorities:
        return (0, min(priorities))
    return (1, 0)


def _metric_label_from_insight_text(text: str, *, value: str) -> str:
    """Derive a legacy label only when a sentence can be tied to the metric."""
    token = _s(text).strip()
    if not token:
        return ""
    metric_numbers = _metric_measurement_numbers(value, retain_bare=True)
    if not metric_numbers:
        return ""
    heading, separator, remainder = token.partition(":")
    if (
        separator
        and not _metric_measurement_numbers(heading)
        and _metric_measurement_numbers(remainder) == metric_numbers
    ):
        return heading.strip()
    sentences = _abbreviation_safe_sentences(token)
    matching = [
        sentence
        for sentence in sentences
        if _metric_measurement_numbers(sentence) == metric_numbers
    ]
    if len(matching) == 1:
        return matching[0]
    matching_clauses = [
        clause
        for sentence in sentences
        for clause in re.split(r"[;,]", sentence)
        if _metric_measurement_numbers(clause) == metric_numbers
        and len(re.findall(r"[A-Za-z]+", clause)) >= 3
        and clause.lstrip()[:1].isupper()
    ]
    if len(matching_clauses) == 1:
        return matching_clauses[0].strip()
    return ""


def _is_coherent_metric_display(value: str, unit: str) -> bool:
    """Keep a source-provided range intact when display normalization abstains."""

    return bool(
        re.search(r"\d", value)
        and ";" not in value
        and ";" not in unit
        and "\n" not in value
    )


def _metric_text_is_unambiguous(*, text: str, value: str) -> bool:
    source_numbers = _metric_measurement_numbers(text, retain_bare=True)
    display_numbers = _metric_measurement_numbers(value, retain_bare=True)
    return (
        bool(text)
        and bool(display_numbers)
        and set(source_numbers) == set(display_numbers)
    )


def _abbreviation_safe_sentences(text: str) -> List[str]:
    protected: List[str] = []

    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"\ufff0{len(protected) - 1}\ufff1"

    compact = re.sub(r"\b(?:[A-Za-z]\.){2,}", protect, text)
    sentences = re.split(r"(?<=[.!?])\s+", compact)

    def restore(sentence: str) -> str:
        return re.sub(
            r"\uFFF0(\d+)\uFFF1",
            lambda match: protected[int(match.group(1))],
            sentence,
        ).strip()

    return [restored for item in sentences if (restored := restore(item))]


def _metric_measurement_numbers(text: str, *, retain_bare: bool = False) -> List[str]:
    matches = re.finditer(
        r"(?P<currency>[$€£¥])?\s*(?P<number>\d+(?:,\d{3})*(?:\.\d+)?)"
        r"(?:\s*(?P<unit>%|percent\b|pct\b|pp\b|bps\b|thousand\b|"
        r"million\b|billion\b|trillion\b|mm\b|mn\b|bn\b|tn\b|k\b|m\b|b\b|t\b))?",
        text,
        re.IGNORECASE,
    )
    numbers: List[str] = []
    for match in matches:
        number = match.group("number").replace(",", "")
        if not retain_bare and not (match.group("currency") or match.group("unit")):
            continue
        numbers.append(number)
    return numbers


def _is_complete_metric_label(label: str) -> bool:
    return bool(label) and not label.endswith(("U.S.", "U.K.", "...", "…"))


def build_topics_covered(
    *,
    toc_entries: List[Dict[str, Any]],
    evidence_packs: Dict[str, Any],
    summary: Dict[str, Any] | None = None,
    insights_final: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    evidence_by_page = _evidence_ids_by_page(evidence_packs)
    for page, evidence_ids in _artifact_evidence_ids_by_page(
        summary=summary or {},
        insights_final=insights_final or [],
    ).items():
        current = evidence_by_page.setdefault(page, [])
        for evidence_id in evidence_ids:
            if evidence_id not in current:
                current.append(evidence_id)
    topics: List[Dict[str, Any]] = []
    for index, entry in enumerate(toc_entries, start=1):
        if not isinstance(entry, dict):
            continue
        topic = _s(entry.get("display_title") or entry.get("section_title")).strip()
        if not topic:
            continue
        pages = _int_list(entry.get("pages"))
        evidence_ids = sorted(
            {
                evidence_id
                for page in pages
                for evidence_id in evidence_by_page.get(page, [])
            }
        )
        subtopics = [
            _s(item).strip()
            for item in (entry.get("key_points") or [])
            if _s(item).strip()
        ][:5]
        why_it_matters = _s(entry.get("summary")).strip()
        if not why_it_matters and subtopics:
            why_it_matters = subtopics[0]
        if not why_it_matters:
            why_it_matters = f"{topic} is covered in the source structure."
        topics.append(
            {
                "schema_version": "1.0",
                "topic_id": _s(entry.get("section_id")).strip() or f"topic-{index}",
                "topic": topic,
                "subtopics": subtopics,
                "why_it_matters": why_it_matters,
                "evidence_ids": evidence_ids,
                "pages": pages,
                "status": "source_backed" if evidence_ids else "toc_only",
            }
        )
    return topics


def _artifact_evidence_ids_by_page(
    *,
    summary: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
) -> Dict[int, List[str]]:
    ids_by_page: Dict[int, List[str]] = {}

    def register(evidence_id: str, pages: List[int]) -> None:
        if not evidence_id:
            return
        for page in pages:
            ids_by_page.setdefault(page, [])
            if evidence_id not in ids_by_page[page]:
                ids_by_page[page].append(evidence_id)

    for claim in summary.get("claim_evidence_map") or []:
        if not isinstance(claim, dict):
            continue
        register(_s(claim.get("evidence_id")).strip(), _int_list(claim.get("pages")))
        for span in claim.get("evidence_spans") or []:
            if isinstance(span, dict):
                register(
                    _s(span.get("evidence_id")).strip(), _int_list([span.get("page")])
                )
    for insight in insights_final:
        if not isinstance(insight, dict):
            continue
        register(
            _s(insight.get("evidence_id")).strip(), _int_list(insight.get("pages"))
        )
        for span in insight.get("evidence_spans") or []:
            if isinstance(span, dict):
                register(
                    _s(span.get("evidence_id")).strip(), _int_list([span.get("page")])
                )
    return ids_by_page


def build_key_figures(
    *,
    metric_spine: List[Dict[str, Any]],
    evidence_packs: Dict[str, Any],
    summary: Dict[str, Any] | None = None,
    insights_final: List[Dict[str, Any]] | None = None,
    editorial_plan: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    evidence_pages = _evidence_pages(evidence_packs)
    artifact_pages = _artifact_pages_by_evidence_id(
        summary=summary or {},
        insights_final=insights_final or [],
    )
    insight_text_by_id = {
        _s(insight.get("id")).strip(): _s(insight.get("text")).strip()
        for insight in (insights_final or [])
        if isinstance(insight, dict)
        and _s(insight.get("id")).strip()
        and _s(insight.get("text")).strip()
    }
    selected_metrics = _select_key_figure_metrics(
        metric_spine=metric_spine,
        evidence_packs=evidence_packs,
        summary=summary or {},
        insights_final=insights_final or [],
        editorial_plan=editorial_plan,
    )
    evidence_text_by_id = _key_figure_evidence_text_by_id(
        evidence_packs=evidence_packs,
        insights_final=insights_final or [],
    )
    figures: List[Dict[str, Any]] = []
    for metric in selected_metrics:
        evidence_id = _s(metric.get("evidence_id")).strip()
        label = _s(metric.get("label")).strip()
        value = _s(metric.get("value")).strip()
        unit = _s(metric.get("unit")).strip()
        if not label or not value or not evidence_id:
            continue
        page_values = evidence_pages.get(evidence_id, []) or artifact_pages.get(
            evidence_id, []
        )
        missing = [
            _s(item).strip()
            for item in (metric.get("missing_context_notes") or [])
            if _s(item).strip()
        ]
        figure = _key_figure_display(
            value=value,
            unit=unit,
            evidence_text=evidence_text_by_id.get(evidence_id, ""),
        )
        figures.append(
            {
                "schema_version": "1.0",
                "figure_id": _s(metric.get("metric_id")).strip() or evidence_id,
                "figure": figure,
                "label": label,
                "unit": unit,
                "segment": _s(metric.get("segment")).strip(),
                "geography": _s(metric.get("geography")).strip(),
                "timeframe": _s(metric.get("timeframe")).strip(),
                "subject": _s(metric.get("subject")).strip(),
                "cohort": _s(metric.get("cohort")).strip(),
                "denominator": _s(metric.get("denominator")).strip(),
                "observation_status": _s(metric.get("observation_status")).strip(),
                "source_page": page_values[0] if page_values else None,
                "why_it_matters": _key_figure_why_it_matters(
                    metric,
                    insight_text=insight_text_by_id.get(
                        _s(metric.get("metric_id")).strip(), ""
                    ),
                ),
                "caveat": ("Missing context: " + ", ".join(missing) if missing else ""),
                "evidence_id": evidence_id,
                "related_chart_candidate": _related_chart_candidate_id(
                    evidence_packs=evidence_packs,
                    evidence_id=evidence_id,
                ),
            }
        )
    return figures


def _key_figure_display(*, value: str, unit: str, evidence_text: str) -> str:
    """Keep the exact source display unless its unit is explicitly retained."""

    if not unit:
        return value
    candidate = f"{value} {unit}".strip()
    if re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", evidence_text, re.IGNORECASE):
        return candidate
    return value


_KEY_FIGURE_MAXIMUM = 5
_KEY_FIGURE_MINIMUM_SCORE = 22
_KEY_FIGURE_CONTEXT_FIELDS = (
    "geography",
    "timeframe",
    "segment",
    "subject",
    "cohort",
    "denominator",
    "observation_status",
)
_KEY_FIGURE_DECISION_TERMS = {
    "adoption",
    "budget",
    "buyer",
    "campaign",
    "commerce",
    "conversion",
    "cost",
    "customer",
    "demand",
    "efficiency",
    "market",
    "media",
    "merchant",
    "purchase",
    "revenue",
    "retail",
    "retailer",
    "sales",
    "shopper",
    "workflow",
}
_KEY_FIGURE_GENERIC_MACRO_TERMS = {
    "economy",
    "economic",
    "gdp",
    "global",
    "inflation",
    "macro",
    "unemployment",
}
_KEY_FIGURE_VENDOR_CASE_STUDY_TERMS = {
    "case study",
    "case-study",
    "client",
    "customer story",
    "vendor",
}
_KEY_FIGURE_STOP_WORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "rate",
    "the",
    "to",
    "using",
}


def _select_key_figure_metrics(
    *,
    metric_spine: List[Dict[str, Any]],
    evidence_packs: Dict[str, Any],
    summary: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
    editorial_plan: Dict[str, Any] | None,
) -> List[Dict[str, Any]]:
    """Choose a small, non-redundant set without inventing replacement facts."""

    evidence_text_by_id = _key_figure_evidence_text_by_id(
        evidence_packs=evidence_packs, insights_final=insights_final
    )
    insights_by_evidence_id = {
        _s(insight.get("evidence_id")).strip(): insight
        for insight in insights_final
        if isinstance(insight, dict) and _s(insight.get("evidence_id")).strip()
    }
    ranked = sorted(
        (
            metric
            for metric in metric_spine
            if isinstance(metric, dict)
            and _s(metric.get("label")).strip()
            and _s(metric.get("value")).strip()
            and _s(metric.get("evidence_id")).strip()
        ),
        key=lambda metric: (
            -_key_figure_score(
                metric=metric,
                summary=summary,
                evidence_text=evidence_text_by_id.get(
                    _s(metric.get("evidence_id")).strip(), ""
                ),
                editorial_plan=editorial_plan,
            ),
            _s(metric.get("metric_id")).strip(),
            _s(metric.get("label")).strip(),
        ),
    )
    selected: List[Dict[str, Any]] = []
    for metric in ranked:
        if len(selected) >= _KEY_FIGURE_MAXIMUM:
            break
        evidence_id = _s(metric.get("evidence_id")).strip()
        evidence_text = evidence_text_by_id.get(evidence_id, "")
        display = _key_figure_display(
            value=_s(metric.get("value")).strip(),
            unit=_s(metric.get("unit")).strip(),
            evidence_text=evidence_text,
        )
        display_quantities = extract_quantities(display)
        evidence_quantities = extract_quantities(evidence_text)
        if not display_quantities or not all(
            quantity_supported(quantity, evidence_quantities, numeric_only=True)
            for quantity in display_quantities
        ):
            continue
        if (
            _key_figure_score(
                metric=metric,
                summary=summary,
                evidence_text=evidence_text,
                editorial_plan=editorial_plan,
            )
            < _KEY_FIGURE_MINIMUM_SCORE
        ):
            continue
        if any(_key_figures_are_redundant(metric, prior) for prior in selected):
            continue
        if not _key_figure_relationship_is_valid(
            metric=metric,
            insight=insights_by_evidence_id.get(evidence_id),
            evidence_text=evidence_text,
        ):
            continue
        selected.append(metric)
    return selected


def _key_figure_evidence_text_by_id(
    *, evidence_packs: Dict[str, Any], insights_final: List[Dict[str, Any]]
) -> Dict[str, str]:
    texts: Dict[str, str] = {}
    for item in _evidence_items(evidence_packs):
        evidence_id = _s(
            item.get("evidence_id") or item.get("id") or item.get("metric_id")
        ).strip()
        text = _s(item.get("evidence") or item.get("text") or item.get("quote")).strip()
        if evidence_id and text and evidence_id not in texts:
            texts[evidence_id] = text
    for insight in insights_final:
        if not isinstance(insight, dict):
            continue
        evidence_id = _s(insight.get("evidence_id")).strip()
        text = _s(insight.get("evidence")).strip()
        if evidence_id and text:
            texts[evidence_id] = text
    return texts


def _key_figure_score(
    *,
    metric: Dict[str, Any],
    summary: Dict[str, Any],
    evidence_text: str,
    editorial_plan: Dict[str, Any] | None,
) -> int:
    """Score retained metrics by editorial utility; low-scoring items stay omitted."""

    label = _s(metric.get("label")).strip()
    value = _s(metric.get("value")).strip()
    combined = " ".join(
        _s(metric.get(field_name)).strip()
        for field_name in ("label", "subject", "segment", "cohort", "source_type")
    ).casefold()
    score = 18  # A clean labelled, evidence-linked primary display.
    rank_group, priority = _metric_editorial_rank(metric, editorial_plan=editorial_plan)
    if rank_group == 0:
        score += max(12, 26 - (priority * 2))
    claim_evidence_ids = {
        _s(claim.get("evidence_id")).strip()
        for claim in (summary.get("claim_evidence_map") or [])
        if isinstance(claim, dict)
    }
    if _s(metric.get("evidence_id")).strip() in claim_evidence_ids:
        score += 12
    executive_summary = _s(
        summary.get("executive_summary") or summary.get("tldr")
    ).casefold()
    if value.casefold() in executive_summary:
        score += 7
    if _key_figure_label_tokens(label) & _key_figure_label_tokens(executive_summary):
        score += 4
    score += min(
        10,
        2
        * sum(
            bool(_s(metric.get(field_name)).strip())
            for field_name in _KEY_FIGURE_CONTEXT_FIELDS
        ),
    )
    score += min(
        9,
        3 * len(_KEY_FIGURE_DECISION_TERMS & _key_figure_label_tokens(combined)),
    )
    confidence = _s(metric.get("confidence")).strip().casefold() or "source_backed"
    score += {
        "high": 10,
        "medium": 5,
        "source_backed": 7,
        "low": -5,
        "weak": -8,
    }.get(confidence, 2)
    if evidence_text:
        score += 4
    if _key_figure_is_vendor_case_study(metric, combined):
        score -= 24
    if _key_figure_is_generic_macro(metric, combined):
        score -= 14
    return score


def _key_figure_is_vendor_case_study(metric: Dict[str, Any], combined: str) -> bool:
    source_type = _s(
        metric.get("source_type") or metric.get("evidence_type")
    ).casefold()
    return source_type in {"vendor_case_study", "case_study", "vendor"} or any(
        term in combined for term in _KEY_FIGURE_VENDOR_CASE_STUDY_TERMS
    )


def _key_figure_is_generic_macro(metric: Dict[str, Any], combined: str) -> bool:
    tokens = _key_figure_label_tokens(combined)
    return bool(tokens & _KEY_FIGURE_GENERIC_MACRO_TERMS) and not bool(
        tokens & _KEY_FIGURE_DECISION_TERMS
    )


def _key_figures_are_redundant(
    candidate: Dict[str, Any], selected: Dict[str, Any]
) -> bool:
    candidate_tokens = _key_figure_label_tokens(_s(candidate.get("label")))
    selected_tokens = _key_figure_label_tokens(_s(selected.get("label")))
    if not candidate_tokens or not selected_tokens:
        return False
    overlap = len(candidate_tokens & selected_tokens)
    union = len(candidate_tokens | selected_tokens)
    same_context = all(
        _s(candidate.get(field_name)).strip().casefold()
        == _s(selected.get(field_name)).strip().casefold()
        for field_name in ("timeframe", "geography", "segment", "cohort", "denominator")
    )
    same_value = _s(candidate.get("value")).strip() == _s(selected.get("value")).strip()
    return overlap / union >= 0.6 or (same_context and same_value and overlap >= 2)


def _key_figure_label_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", _s(value).casefold()):
        if token in _KEY_FIGURE_STOP_WORDS or len(token) < 3:
            continue
        if token.endswith("ies"):
            token = f"{token[:-3]}y"
        elif token.startswith("explor"):
            token = "explore"
        elif token.startswith("adopt"):
            token = "adopt"
        elif token.endswith("s"):
            token = token[:-1]
        tokens.add(token)
    return tokens


def _key_figure_relationship_is_valid(
    *, metric: Dict[str, Any], insight: Dict[str, Any] | None, evidence_text: str
) -> bool:
    """Run the public label/value fidelity rule for every selected projection."""

    evidence_id = _s(metric.get("evidence_id")).strip()
    report = evaluate_public_editorial_quality(
        report_id="key-figure-selection",
        artifacts={
            "insights_final": [
                {
                    "id": _s((insight or {}).get("id")).strip() or evidence_id,
                    "evidence_id": evidence_id,
                    "evidence": evidence_text,
                }
            ],
            "key_figures": [
                {
                    "label": _s(metric.get("label")).strip(),
                    "figure": " ".join(
                        part
                        for part in (
                            _s(metric.get("value")).strip(),
                            _s(metric.get("unit")).strip(),
                        )
                        if part
                    ),
                    "why_it_matters": _s((insight or {}).get("text")).strip(),
                    "evidence_id": evidence_id,
                }
            ],
        },
    )
    return not any(
        issue.rule_id == "public_editorial_quality.metric_label_relationship"
        for issue in report.issues
    )


def _artifact_pages_by_evidence_id(
    *,
    summary: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
) -> Dict[str, List[int]]:
    pages_by_id: Dict[str, List[int]] = {}
    for page, evidence_ids in _artifact_evidence_ids_by_page(
        summary=summary,
        insights_final=insights_final,
    ).items():
        for evidence_id in evidence_ids:
            pages_by_id.setdefault(evidence_id, [])
            if page not in pages_by_id[evidence_id]:
                pages_by_id[evidence_id].append(page)
    return pages_by_id


def build_chart_insight_cards(
    *,
    key_figures: List[Dict[str, Any]],
    evidence_packs: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    chart_candidates = _chart_candidates(evidence_packs)
    insights_by_evidence = {
        _s(item.get("evidence_id")).strip(): {
            "insight_id": _s(item.get("id") or item.get("insight_id")).strip(),
            "text": _s(item.get("text")).strip(),
        }
        for item in insights_final
        if isinstance(item, dict) and _s(item.get("evidence_id")).strip()
    }
    cards: List[Dict[str, Any]] = []
    for index, figure in enumerate(key_figures, start=1):
        evidence_id = _s(figure.get("evidence_id")).strip()
        chart = _chart_candidate_for_evidence(chart_candidates, evidence_id)
        confidence = _s((chart or {}).get("confidence")).strip() or "medium"
        candidate_id = _s(
            (chart or {}).get("candidate_id")
            or (chart or {}).get("chart_id")
            or (chart or {}).get("id")
        ).strip()
        insight = insights_by_evidence.get(evidence_id, {})
        caption = _s((chart or {}).get("caption") or figure.get("label")).strip()
        metric_mentions = _metric_mentions_for_figure(figure)
        weak_reason = ""
        if not chart:
            weak_reason = "No chart candidate was linked to the metric evidence."
        elif not candidate_id:
            weak_reason = "The linked chart has no retained accepted candidate ID."
        elif not bool((chart or {}).get("crop_qa_accepted")):
            weak_reason = "The linked candidate is not retained as crop-QA accepted."
        elif not _s(
            (chart or {}).get("source_page") or figure.get("source_page")
        ).strip():
            weak_reason = "The accepted candidate has no retained source-page linkage."
        elif (
            not _s(insight.get("insight_id")).strip()
            or not _s(insight.get("text")).strip()
        ):
            weak_reason = "No retained insight is linked to the chart evidence."
        elif confidence.lower() in {"low", "weak"}:
            weak_reason = "Chart candidate confidence is below source-backed threshold."
        public_takeaway = _chart_takeaway(figure, insights_by_evidence)
        cards.append(
            {
                "schema_version": "1.0",
                "card_id": candidate_id or f"chart-card-{index}",
                "status": "generated" if not weak_reason else "weak_evidence",
                "candidate_id": candidate_id,
                "crop_qa_accepted": bool((chart or {}).get("crop_qa_accepted")),
                "caption": caption,
                "takeaway": public_takeaway,
                "public_takeaway": public_takeaway,
                "business_implication": _business_implication(
                    figure, insights_by_evidence
                ),
                "metric_mentions": metric_mentions,
                "evidence_confidence": confidence,
                "evidence_id": evidence_id,
                "source_page": (chart or {}).get("source_page")
                or figure.get("source_page"),
                "insight_id": _s(insight.get("insight_id")).strip(),
                "avoid_reason_if_weak": weak_reason,
            }
        )
    return cards


def regeneration_dependent_roots(source_roots: Iterable[str]) -> frozenset[str]:
    """Return transitive dependents declared by the canonical artifact graph."""

    affected_roots = {str(root).strip() for root in source_roots if str(root).strip()}
    required_roots: set[str] = set()
    while True:
        newly_required = {
            root
            for root, dependencies in ARTIFACT_ROOT_DEPENDENCIES.items()
            if root not in required_roots and dependencies.intersection(affected_roots)
        }
        if not newly_required:
            return frozenset(required_roots)
        required_roots.update(newly_required)
        affected_roots.update(newly_required)


def rebuild_regeneration_derived_artifacts(
    *,
    artifacts: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    writable_roots: Iterable[str],
    materialize_roots: Iterable[str] = (),
) -> frozenset[str]:
    """Rebuild present affected projections through the canonical builders."""

    required_roots = set(regeneration_dependent_roots(writable_roots))

    present_roots = required_roots.intersection(
        artifacts, CANONICAL_DERIVED_ARTIFACT_ROOTS
    ) | required_roots.intersection(materialize_roots, CANONICAL_DERIVED_ARTIFACT_ROOTS)
    if not present_roots:
        return frozenset()
    try:
        expected = build_canonical_regeneration_derived_artifacts(
            artifacts=artifacts,
            evidence_packs=evidence_packs,
            roots=present_roots,
        )
    except AppError as exc:
        raise AppError(
            code="regeneration_deterministic_projection_failed",
            message="Canonical deterministic projections could not be rebuilt",
            retryable=False,
            context={
                "projection_roots": sorted(present_roots),
                "cause_code": exc.code,
            },
            cause=exc,
        ) from exc
    for root in present_roots:
        artifacts[root] = expected[root]
    return frozenset(present_roots)


def finalize_regeneration_candidate_artifacts(
    *,
    promoted_baseline: Dict[str, Any],
    candidate_artifacts: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    atomic_source_patch: Dict[str, Any],
) -> frozenset[str]:
    """Finalize deterministic dependents and provenance on an atomic patch.

    Candidate assembly can contain incidental changes. The explicit patch is
    the sole source of public source-root mutations; all other candidate roots
    are restored from the last promoted baseline except retained provenance
    and private audit metadata. Projection roots are restored, then only the
    changed patch roots' dependents are rebuilt through the canonical builders.
    Returned paths are the exact changed dependent paths produced by this step.
    """

    projection_roots = set(CANONICAL_DERIVED_ARTIFACT_ROOTS)
    patch_roots = {
        str(root).strip() for root in atomic_source_patch if str(root).strip()
    }
    invalid_patch_roots = patch_roots.intersection(
        projection_roots
        | REGENERATION_PRIVATE_METADATA_ROOTS
        | {"soft_copy_claim_provenance"}
    )
    if invalid_patch_roots:
        raise AppError(
            code="regeneration_deterministic_projection_failed",
            message="Atomic source patch contains a derived or private artifact root",
            retryable=False,
            context={
                "projection": "atomic_source_patch",
                "roots": sorted(invalid_patch_roots),
            },
        )
    candidate_materialized_roots = {
        root for root in projection_roots if root in candidate_artifacts
    }
    for root in projection_roots:
        if root in promoted_baseline:
            candidate_artifacts[root] = deepcopy(promoted_baseline[root])
        else:
            candidate_artifacts.pop(root, None)

    for root in set(promoted_baseline) | set(candidate_artifacts):
        if (
            root in patch_roots
            or root in projection_roots
            or root in REGENERATION_PRIVATE_METADATA_ROOTS
            or root == "soft_copy_claim_provenance"
        ):
            continue
        if root in promoted_baseline:
            candidate_artifacts[root] = deepcopy(promoted_baseline[root])
        else:
            candidate_artifacts.pop(root, None)

    for root, value in atomic_source_patch.items():
        candidate_artifacts[str(root).strip()] = deepcopy(value)

    changed_source_roots = {
        root
        for root in patch_roots
        if promoted_baseline.get(root) != candidate_artifacts.get(root)
    }
    rebuilt_roots = rebuild_regeneration_derived_artifacts(
        artifacts=candidate_artifacts,
        evidence_packs=evidence_packs,
        writable_roots=changed_source_roots,
        materialize_roots=candidate_materialized_roots,
    )
    if "family_status" in rebuilt_roots:
        candidate_artifacts["family_status"] = _preserve_unchanged_summary_status(
            rebuilt=candidate_artifacts.get("family_status"),
            promoted_baseline=promoted_baseline,
            candidate_artifacts=candidate_artifacts,
        )

    candidate_provenance_changed = candidate_artifacts.get(
        "soft_copy_claim_provenance"
    ) != promoted_baseline.get("soft_copy_claim_provenance")
    if changed_source_roots.intersection(
        {"summary", "expert_comment", "linkedin_post"}
    ) or candidate_provenance_changed:
        try:
            _rebuild_final_soft_copy_claim_provenance(
                artifacts=candidate_artifacts,
                promoted_baseline=promoted_baseline,
            )
        except AppError as exc:
            raise AppError(
                code="regeneration_deterministic_projection_failed",
                message="Final soft-copy provenance could not be rebuilt deterministically",
                retryable=False,
                context={
                    "projection": "soft_copy_claim_provenance",
                    "cause_code": exc.code,
                    "artifact_family": exc.context.get("artifact_family", ""),
                    "missing_public_sentence_count": exc.context.get(
                        "missing_public_sentence_count", 0
                    ),
                    "obsolete_provenance_sentence_count": exc.context.get(
                        "obsolete_provenance_sentence_count", 0
                    ),
                },
                cause=exc,
            ) from exc
    elif "soft_copy_claim_provenance" in promoted_baseline:
        candidate_artifacts["soft_copy_claim_provenance"] = deepcopy(
            promoted_baseline["soft_copy_claim_provenance"]
        )
    else:
        candidate_artifacts.pop("soft_copy_claim_provenance", None)

    changed_paths = artifact_diff_paths(promoted_baseline, candidate_artifacts)
    verified_roots = set(rebuilt_roots)
    if promoted_baseline.get("soft_copy_claim_provenance") != candidate_artifacts.get(
        "soft_copy_claim_provenance"
    ):
        verified_roots.add("soft_copy_claim_provenance")
    return frozenset(
        path
        for path in changed_paths
        if path.split(".", 1)[0].split("[", 1)[0] in verified_roots
    )


def _preserve_unchanged_summary_status(
    *,
    rebuilt: Any,
    promoted_baseline: Dict[str, Any],
    candidate_artifacts: Dict[str, Any],
) -> Dict[str, Any]:
    """Reuse the accepted summary outcome when its source root is unchanged."""

    result = deepcopy(rebuilt) if isinstance(rebuilt, dict) else {}
    prior = promoted_baseline.get("family_status")
    if (
        not isinstance(prior, dict)
        or "summary" not in promoted_baseline
        or "summary" not in candidate_artifacts
        or promoted_baseline.get("summary") != candidate_artifacts.get("summary")
    ):
        return result
    status = prior.get("summary")
    if _is_reusable_summary_status(status):
        result["summary"] = deepcopy(status)
    return result


def _is_reusable_summary_status(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if (
        value.get("schema_version") != "1.0"
        or value.get("family") != "summary"
        or value.get("source") != "artifact"
    ):
        return False
    status = str(value.get("status") or "").strip().lower()
    action = str(value.get("policy_action") or "").strip().lower()
    confidence = value.get("confidence_score")
    return (
        (status == "generated" and action == "keep")
        or (status == "abstained" and action == "abstain")
    ) and isinstance(confidence, (int, float)) and not isinstance(
        confidence, bool
    ) and 0.0 <= confidence <= 1.0


def _rebuild_final_soft_copy_claim_provenance(
    *,
    artifacts: Dict[str, Any],
    promoted_baseline: Dict[str, Any],
) -> None:
    """Rebind final public sentences on the shared canonical material grid."""

    raw_provenance = artifacts.get("soft_copy_claim_provenance")
    if raw_provenance is None:
        claims: List[SoftCopyClaimProvenance] = []
    else:
        claims = soft_copy_claim_provenance_from_payload(raw_provenance)
    baseline_claims: List[SoftCopyClaimProvenance] = []
    baseline_provenance = promoted_baseline.get("soft_copy_claim_provenance")
    if isinstance(baseline_provenance, dict):
        try:
            baseline_claims = soft_copy_claim_provenance_from_payload(
                baseline_provenance
            )
        except AppError:
            baseline_claims = []
    rebuilt_claims: List[SoftCopyClaimProvenance] = []
    for family in ("summary", "expert_comment", "linkedin_post"):
        public_text = soft_copy_public_text(family, artifacts.get(family))
        family_claims = [claim for claim in claims if claim.artifact_family == family]
        baseline_family_claims = [
            claim for claim in baseline_claims if claim.artifact_family == family
        ]
        claims_by_hash = {claim.text_hash: claim for claim in family_claims}
        baseline_by_hash = {claim.text_hash: claim for claim in baseline_family_claims}
        rebuilt_hashes: set[str] = set()
        for sentence in soft_copy_material_sentences(public_text):
            text_hash = hashlib.sha256(sentence.encode("utf-8")).hexdigest()
            if text_hash in rebuilt_hashes:
                continue
            candidate_claim = claims_by_hash.get(text_hash)
            baseline_claim = baseline_by_hash.get(text_hash)
            retained = candidate_claim or baseline_claim
            if (
                candidate_claim is not None
                and baseline_claim is not None
                and candidate_claim.classification == baseline_claim.classification
                and candidate_claim.evidence_ids == baseline_claim.evidence_ids
            ):
                retained = baseline_claim
            if retained is None:
                raise AppError(
                    code="soft_copy_claim_provenance_sentence_missing",
                    message="Final sentence is absent from retained provenance",
                    retryable=False,
                    context={"artifact_family": family},
                )
            rebuilt_claims.append(retained)
            rebuilt_hashes.add(text_hash)
    rebuilt_claims.extend(
        claim
        for claim in claims
        if claim.artifact_family not in {"summary", "expert_comment", "linkedin_post"}
    )
    artifacts["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        rebuilt_claims
    )
    assert_retained_soft_copy_claims_match_public_copy(artifacts)


def build_canonical_regeneration_derived_artifacts(
    *,
    artifacts: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    roots: Iterable[str],
) -> Dict[str, Any]:
    """Return requested projections from the canonical artifact builders."""

    requested = set(roots)
    builder_roots = set(requested)
    if "chart_insight_cards" in builder_roots:
        builder_roots.add("key_figures")
    if builder_roots.intersection(
        {"key_figures", "executive_advisory", "claim_ledgers"}
    ):
        builder_roots.add("metric_spine")
    if "claim_ledgers" in builder_roots:
        builder_roots.add("executive_advisory")

    insights = artifacts.get("insights_final") or []
    summary = artifacts.get("summary") or {}
    quotes = artifacts.get("quotes_final") or []
    editorial_plan = artifacts.get("editorial_plan") or {}
    canonical: Dict[str, Any] = {}
    if "metric_spine" in builder_roots:
        canonical["metric_spine"] = derive_metric_spine_from_insights(
            insights,
            editorial_plan=editorial_plan,
        )
    if "topics_covered" in builder_roots:
        canonical["topics_covered"] = build_topics_covered(
            toc_entries=artifacts.get("toc_entries") or [],
            evidence_packs=evidence_packs,
            summary=summary,
            insights_final=insights,
        )
    if "key_figures" in builder_roots:
        canonical["key_figures"] = build_key_figures(
            metric_spine=canonical["metric_spine"],
            evidence_packs=evidence_packs,
            summary=summary,
            insights_final=insights,
            editorial_plan=editorial_plan,
        )
    if "chart_insight_cards" in builder_roots:
        canonical["chart_insight_cards"] = build_chart_insight_cards(
            key_figures=canonical["key_figures"],
            evidence_packs=evidence_packs,
            insights_final=insights,
        )
    if "executive_advisory" in builder_roots:
        canonical["executive_advisory"] = build_executive_advisory_artifacts(
            summary=summary,
            insights_final=insights,
            quotes_final=quotes,
            metric_spine=canonical["metric_spine"],
            evidence_packs=evidence_packs,
        )
    if "claim_ledgers" in builder_roots:
        claim_ledger = artifacts.get("claim_ledgers") or []
        report_id = (
            str(claim_ledger[0].get("canonical_claim_id") or "").split(":", 1)[0]
            if isinstance(claim_ledger, list)
            and claim_ledger
            and isinstance(claim_ledger[0], dict)
            else ""
        )
        canonical["claim_ledgers"] = build_universal_claim_ledger(
            report_id=report_id,
            summary=summary,
            insights_final=insights,
            quotes_final=quotes,
            metric_spine=canonical["metric_spine"],
            executive_advisory=canonical["executive_advisory"],
        )
    if "family_status" in builder_roots:
        canonical["family_status"] = build_artifact_family_status(
            summary=summary,
            insights_candidates=artifacts.get("insights_candidates") or [],
            insights_final=insights,
            quotes_final=quotes,
            expert_comment=_s(artifacts.get("expert_comment")),
            linkedin_post=_s(artifacts.get("linkedin_post")),
        )
    return {root: canonical[root] for root in requested}


def _int_list(value: Any) -> List[int]:
    if not isinstance(value, list):
        return []
    numbers: List[int] = []
    for item in value:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number not in numbers:
            numbers.append(number)
    return numbers


def _evidence_items(evidence_packs: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not isinstance(evidence_packs, dict):
        return items
    for pack_name, pack in evidence_packs.items():
        if not isinstance(pack, dict):
            continue
        for key in ("findings", "quotes", "metrics", "items"):
            raw_items = pack.get(key)
            if not isinstance(raw_items, list):
                continue
            for item in raw_items:
                if isinstance(item, dict):
                    copied = dict(item)
                    copied.setdefault("source_pack", pack_name)
                    items.append(copied)
    return items


def _evidence_pages(evidence_packs: Dict[str, Any]) -> Dict[str, List[int]]:
    pages_by_id: Dict[str, List[int]] = {}
    for item in _evidence_items(evidence_packs):
        evidence_id = _s(
            item.get("evidence_id") or item.get("id") or item.get("metric_id")
        ).strip()
        if not evidence_id:
            continue
        pages = _int_list(item.get("pages"))
        page = item.get("page")
        if page is not None:
            pages = _int_list([*pages, page])
        pages_by_id[evidence_id] = pages
    return pages_by_id


def _evidence_ids_by_page(evidence_packs: Dict[str, Any]) -> Dict[int, List[str]]:
    ids_by_page: Dict[int, List[str]] = {}
    for evidence_id, pages in _evidence_pages(evidence_packs).items():
        for page in pages:
            ids_by_page.setdefault(page, [])
            if evidence_id not in ids_by_page[page]:
                ids_by_page[page].append(evidence_id)
    return ids_by_page


def _key_figure_why_it_matters(
    metric: Dict[str, Any], *, insight_text: str = ""
) -> str:
    if insight_text:
        return insight_text
    label = _s(metric.get("label")).strip()
    segment = _s(metric.get("segment")).strip()
    geography = _s(metric.get("geography")).strip()
    timeframe = _s(metric.get("timeframe")).strip()
    parts = [label]
    context = ", ".join([item for item in (segment, geography, timeframe) if item])
    if context:
        parts.append(context)
    delta = _s(metric.get("delta")).strip()
    if delta:
        parts.append(f"change: {delta}")
    return "; ".join(parts)


def _chart_candidates(evidence_packs: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    if not isinstance(evidence_packs, dict):
        return candidates
    for pack in evidence_packs.values():
        if not isinstance(pack, dict):
            continue
        for key in ("chart_candidates", "charts", "figures", "visual_candidates"):
            raw_items = pack.get(key)
            if not isinstance(raw_items, list):
                continue
            candidates.extend([item for item in raw_items if isinstance(item, dict)])
    return candidates


def _related_chart_candidate_id(
    *, evidence_packs: Dict[str, Any], evidence_id: str
) -> str:
    chart = _chart_candidate_for_evidence(
        _chart_candidates(evidence_packs), evidence_id
    )
    if not chart:
        return ""
    return _s(chart.get("chart_id") or chart.get("id")).strip()


def _chart_candidate_for_evidence(
    chart_candidates: List[Dict[str, Any]], evidence_id: str
) -> Dict[str, Any]:
    for chart in chart_candidates:
        candidate_evidence_id = _s(
            chart.get("evidence_id") or chart.get("source_evidence_id")
        ).strip()
        if candidate_evidence_id == evidence_id:
            return chart
        evidence_ids = [
            _s(item).strip()
            for item in (chart.get("evidence_ids") or [])
            if _s(item).strip()
        ]
        if evidence_id in evidence_ids:
            return chart
    return {}


def _metric_mentions_for_figure(figure: Dict[str, Any]) -> List[str]:
    mentions = [
        _s(figure.get("figure")).strip(),
        _s(figure.get("label")).strip(),
        _s(figure.get("segment")).strip(),
        _s(figure.get("geography")).strip(),
        _s(figure.get("timeframe")).strip(),
    ]
    return [item for item in mentions if item]


def _chart_takeaway(
    figure: Dict[str, Any], insights_by_evidence: Dict[str, Dict[str, str]]
) -> str:
    evidence_id = _s(figure.get("evidence_id")).strip()
    insight = insights_by_evidence.get(evidence_id, {})
    if _s(insight.get("text")).strip():
        return _s(insight.get("text")).strip()
    return f"{_s(figure.get('label')).strip()} is reported at {_s(figure.get('figure')).strip()}."


def _business_implication(
    figure: Dict[str, Any], insights_by_evidence: Dict[str, Dict[str, str]]
) -> str:
    evidence_id = _s(figure.get("evidence_id")).strip()
    insight = insights_by_evidence.get(evidence_id, {})
    if _s(insight.get("text")).strip():
        return _s(insight.get("text")).strip()
    context = _s(figure.get("why_it_matters")).strip()
    return context or _s(figure.get("label")).strip()


def _unique_advisory_texts(values: List[str], *, limit: int = 3) -> List[str]:
    texts: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = _s(value).strip()
        normalized = " ".join(text.split()).casefold()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        texts.append(text)
        if len(texts) >= limit:
            break
    return texts


def _has_advisory_evidence(item: Dict[str, Any]) -> bool:
    return bool(_s(item.get("evidence_id")).strip() or item.get("evidence_spans"))


def _decision_brief_context(summary: Dict[str, Any]) -> str:
    context = _s(summary.get("tldr") or summary.get("card_tldr_compact")).strip()
    executive_summary = _s(summary.get("executive_summary")).strip()
    if (
        " ".join(context.split()).casefold()
        == " ".join(executive_summary.split()).casefold()
    ):
        return ""
    return context


def _limitation_texts(limitations: List[Any]) -> List[str]:
    return [
        _s(item)
        if isinstance(item, str)
        else _s(
            item.get("description")
            or item.get("limitation")
            or item.get("text")
            or item.get("summary")
        )
        for item in limitations
        if isinstance(item, (str, dict))
    ]


def build_executive_advisory_artifacts(
    *,
    summary: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    metric_spine: List[Dict[str, Any]],
    evidence_packs: Dict[str, Any],
) -> Dict[str, Any]:
    limitations_pack = evidence_packs.get("limitations", {})
    limitations = (
        limitations_pack.get("limitations")
        if isinstance(limitations_pack, dict)
        else []
    )
    if not isinstance(limitations, list):
        limitations = []
    supported_insights = [
        item
        for item in insights_final
        if isinstance(item, dict) and _has_advisory_evidence(item)
    ]
    grounded_recommendations = [
        {
            "id": _s(item.get("id")).strip(),
            "recommendation": _s(item.get("now_what")).strip(),
            "rationale": "",
            "evidence_id": _s(item.get("evidence_id")).strip(),
        }
        for item in supported_insights
        if _s(item.get("now_what")).strip()
    ]
    grounded_risks = [
        {
            "id": _s(item.get("id")).strip(),
            "risk": _s(item.get("text")).strip(),
            "impact": "",
            "likelihood": "",
            "mitigation": "",
            "evidence_id": _s(item.get("evidence_id")).strip(),
        }
        for item in supported_insights
        if _s(item.get("coverage_role")).strip().casefold()
        in {"counter_signal", "strategic_risk"}
        and _s(item.get("text")).strip()
    ]
    decision_implications = _unique_advisory_texts(
        [_s(item.get("so_what")) for item in supported_insights]
    )
    priority_moves = _unique_advisory_texts(
        [
            *[_s(item.get("now_what")) for item in supported_insights],
            *[_s(item.get("recommendation")) for item in grounded_recommendations],
        ]
    )
    watchouts = _unique_advisory_texts(
        [
            *[
                _s(item.get("text"))
                for item in supported_insights
                if _s(item.get("coverage_role")).strip().casefold()
                in {"counter_signal", "strategic_risk"}
            ],
            *[_s(item.get("risk")) for item in grounded_risks],
            *_limitation_texts(limitations),
        ]
    )
    return {
        "schema_version": "1.0",
        "decision_brief": {
            "schema_version": "1.0",
            "status": "generated"
            if supported_insights or metric_spine
            else "not_found",
            "strategic_context": _decision_brief_context(summary),
            "decision_implications": decision_implications,
            "priority_moves": priority_moves,
            "watchouts": watchouts,
            "evidence_links": sorted(
                {
                    _s(item.get("evidence_id")).strip()
                    for item in [
                        *supported_insights,
                        *grounded_recommendations,
                        *grounded_risks,
                        *quotes_final,
                    ]
                    if isinstance(item, dict) and _s(item.get("evidence_id")).strip()
                }
            ),
            "confidence_note": (
                "Metric spine available"
                if metric_spine
                else "Evidence-linked insights available"
            ),
        },
        "recommendations": {
            "schema_version": "1.0",
            "status": (
                "generated" if grounded_recommendations else "recommendations_not_found"
            ),
            "items": grounded_recommendations,
        },
        "risks": {
            "schema_version": "1.0",
            "status": "generated" if grounded_risks else "risks_not_found",
            "items": grounded_risks,
        },
        "coverage_diagnostics": {
            "schema_version": "1.0",
            "metric_spine_count": len(metric_spine),
            "evidence_linked_insight_count": len(supported_insights),
            "quote_count": len(quotes_final),
        },
        "audience_variants": {
            "schema_version": "1.0",
            "status": "not_requested",
            "items": [],
        },
        "category_relevance": {
            "schema_version": "1.0",
            "status": "not_found",
            "items": [],
        },
    }


def _log_topic_brief_mapping_audit(
    *,
    topic_briefs: List[Dict[str, Any]],
    doc_map: Dict[str, Any],
    ctx: RunContext,
) -> None:
    diagnostics = audit_topic_brief_mappings(
        topic_briefs=topic_briefs,
        doc_map=doc_map,
    )
    status_counts: Dict[str, int] = {}
    for diagnostic in diagnostics:
        status = _s(diagnostic.get("status")).strip() or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    issue_count = sum(
        count for status, count in status_counts.items() if status != "ok"
    )
    unmapped_count = sum(
        status_counts.get(status, 0)
        for status in ("identity_mismatch", "unknown_section")
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_topic_brief_mapping_audit",
            module=logger.name,
            fields={
                "mapping_version": TOPIC_BRIEF_MAPPING_VERSION,
                "brief_count": len(topic_briefs),
                "diagnostic_count": len(diagnostics),
                "mapped_count": status_counts.get("ok", 0),
                "unmapped_count": unmapped_count,
                "issue_count": issue_count,
                "status_counts": status_counts,
                "diagnostics": diagnostics,
            },
        )
    )


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
    category_ids: List[str],
    retrieval_mode: str,
    settings: AppSettings,
    prompt_client,
    ctx: RunContext,
) -> Dict[str, Any]:
    prompt_meta: Dict[str, Any] = {}
    namespaces = [
        "report_vs/artifacts/editorial_plan",
        "report_vs/artifacts/summary",
        "report_vs/artifacts/cover_semantics",
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
        routing_decision = resolve_routing_policy(
            namespace,
            routing_policies_from_config(
                getattr(settings, "llm_routing", {}),
                model_overrides=getattr(settings, "openai_models", {}),
            ),
            default_model=settings.openai_model,
        )
        execution_policy = resolve_execution_policy(
            namespace,
            execution_policies_from_config(
                getattr(settings, "llm_execution_policies", {}),
                model_overrides=getattr(settings, "openai_models", {}),
                legacy_routing=getattr(settings, "llm_routing", {}),
                default_model=settings.openai_model,
                default_temperature=settings.temperature,
                default_seed=settings.openai_seed,
                default_timeout_seconds=settings.openai_timeout_seconds,
            ),
            default_model=settings.openai_model,
            default_temperature=settings.temperature,
            default_seed=settings.openai_seed,
            default_timeout_seconds=settings.openai_timeout_seconds,
        )
        policy = execution_policy.policy
        seed = (
            None
            if policy.seed_policy == "disabled"
            else policy.seed
            if policy.seed_policy == "fixed"
            else settings.openai_seed
        )
        execution_identity = build_llm_execution_identity(
            prompt_content_hash=prompt_set.prompt_content_hash,
            provider=policy.provider,
            model=policy.model,
            temperature=policy.temperature,
            seed=seed,
            max_output_tokens=policy.max_output_tokens,
            timeout_seconds=policy.timeout_seconds,
            retrieval_mode=retrieval_mode,
            routing_policy={
                "policy_source": routing_decision.policy_source,
                "tier": routing_decision.tier,
                "quality_threshold": routing_decision.quality_threshold,
                "same_provider_fallback": routing_decision.same_provider_fallback,
                "max_input_tokens": routing_decision.max_input_tokens,
                "compaction_enabled": routing_decision.compaction_enabled,
                "execution_policy_hash": execution_policy.policy_hash,
                "execution_policy_source": execution_policy.policy_source,
            },
            compaction_policy={
                "enabled": routing_decision.compaction_enabled,
                "max_input_tokens": routing_decision.max_input_tokens or None,
                "strategy": "anchor_preserving_head_tail",
            },
            output_contract_schema_version="artifact_json:1.0",
            validator_version="artifacts_schema:3.0",
        )
        prompt_meta[namespace] = {
            "prompt_system_sha256": prompt_set.system.sha256,
            "prompt_user_sha256": prompt_set.user.sha256,
            "prompt_content_hash": prompt_set.prompt_content_hash,
            "dependency_manifest": (
                asdict(prompt_set.dependency_manifest)
                if prompt_set.dependency_manifest is not None
                else {}
            ),
            "execution_identity": execution_identity.execution_identity,
            "execution_identity_manifest": asdict(execution_identity),
            "model": policy.model,
            "execution_policy_hash": execution_policy.policy_hash,
            "execution_policy_source": execution_policy.policy_source,
        }
    inputs_hash = sha256_json(
        {
            "doc_map": doc_map,
            "evidence_packs": evidence_packs,
            "availability": availability,
            "expert_domain": expert_domain,
            "category_ids": category_ids,
        }
    )
    return {
        "schema_version": "2.0",
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
    expected_cache_meta: Optional[Dict[str, Any]] = None,
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
        cache_meta_matcher=lambda cached_meta: _artifact_cache_meta_matches(
            cached_meta=cached_meta,
            expected_cache_meta=expected_cache_meta or {},
            cache_key=cache_key,
        ),
        adapt_payload=lambda payload, path: _adapt_cached_artifacts_payload(
            payload=payload,
            path=path,
            report_id=report_id,
            ctx=ctx,
        ),
    )
    return result.value if result.status == "hit" else None


def _artifact_cache_meta_matches(
    *,
    cached_meta: dict[str, Any],
    expected_cache_meta: dict[str, Any],
    cache_key: str,
) -> tuple[bool, str]:
    if cached_meta.get("key") == cache_key:
        return True, ""
    cached_prompts = cached_meta.get("prompts")
    expected_prompts = expected_cache_meta.get("prompts")
    if not isinstance(cached_prompts, dict):
        return False, "legacy_identity_read"
    if not isinstance(expected_prompts, dict):
        return False, "key_mismatch"
    for namespace, expected in expected_prompts.items():
        cached = cached_prompts.get(namespace)
        if not isinstance(expected, dict) or not isinstance(cached, dict):
            return False, "execution_identity_mismatch"
        if cached.get("execution_identity") != expected.get("execution_identity"):
            return False, "execution_identity_mismatch"
        if cached.get("prompt_content_hash") != expected.get("prompt_content_hash"):
            return False, "prompt_content_identity_mismatch"
    return False, "key_mismatch"


def _adapt_cached_artifacts_payload(
    *,
    payload: Dict[str, Any],
    path: str,
    report_id: str,
    ctx: RunContext,
) -> CachedPackAdaptResult[Dict[str, Any]]:
    payload = _attach_cached_artifact_family_status(payload)
    try:
        payload = _adapt_cached_artifact_schema(payload)
        payload["editorial_plan"] = normalize_artifact_editorial_plan(
            payload.get("editorial_plan")
        )
        _validate_cover_semantics(payload.get("cover_semantics"), ctx=ctx)
        raw_summary = payload.get("summary")
        _validate_card_tldrs(
            raw_summary if isinstance(raw_summary, dict) else {},
            summary_abstained=family_is_abstained(payload, "summary"),
            ctx=ctx,
        )
        assert_retained_soft_copy_claims_match_public_copy(payload)
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


def _adapt_cached_artifact_schema(payload: Dict[str, Any]) -> Dict[str, Any]:
    version = _s(payload.get("schema_version")).strip()
    if version == "3.0":
        return _ensure_cached_derived_artifact_fields(dict(payload))
    if version not in {"1.0", "2.0"}:
        raise AppError(
            code="artifact_schema_migration_required",
            message="Cached artifact schema version is unsupported",
            retryable=False,
            context={"schema_version": version},
        )
    adapted = dict(payload)
    if version == "1.0":
        raw_summary = adapted.get("summary")
        summary = dict(raw_summary) if isinstance(raw_summary, dict) else {}
        if family_is_abstained(adapted, "summary"):
            summary.setdefault("card_tldr_compact", "")
        else:
            standard = _validate_complete_tldr(
                summary.get("tldr"),
                limit=18,
                code="card_tldr_compact_invalid",
                field_name="summary.tldr",
            )
            summary["card_tldr_compact"] = standard
        adapted["summary"] = summary
    if not isinstance(adapted.get("cover_semantics"), dict):
        raise AppError(
            code="cover_fingerprint_invalid",
            message="Cached artifacts do not contain grounded cover semantics",
            retryable=False,
            context={"schema_version": version},
        )
    adapted["schema_version"] = "3.0"
    return _ensure_cached_derived_artifact_fields(adapted)


def _ensure_cached_derived_artifact_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload.setdefault("topics_covered", [])
    payload.setdefault("key_figures", [])
    payload.setdefault("chart_insight_cards", [])
    return payload


def _validate_cover_semantics(
    value: Any,
    *,
    ctx: RunContext,
) -> Dict[str, str]:
    if not isinstance(value, dict):
        raise AppError(
            code="cover_fingerprint_invalid",
            message="cover_semantics must be an object",
            retryable=False,
            context={"field": "cover_semantics"},
        )
    allowed_values = {
        "evidence_shape": EVIDENCE_SHAPES,
        "direction": DIRECTIONS,
        "geography_scope": GEOGRAPHY_SCOPES,
        "evidence_density": EVIDENCE_DENSITIES,
        "domain_layer": DOMAIN_LAYERS,
    }
    normalized: Dict[str, str] = {}
    for field_name, allowed in allowed_values.items():
        field_value = _normalize_cover_semantic_enum(value.get(field_name))
        if field_value not in allowed:
            raise AppError(
                code="cover_fingerprint_invalid",
                message=f"cover_semantics.{field_name} is not approved",
                retryable=False,
                context={"field": field_name, "value": field_value},
            )
        normalized[field_name] = field_value
    selection_reason = " ".join(_s(value.get("selection_reason")).split())
    if not selection_reason:
        raise AppError(
            code="cover_fingerprint_invalid",
            message="cover_semantics.selection_reason must be populated",
            retryable=False,
            context={"field": "selection_reason"},
        )
    normalized["selection_reason"] = selection_reason
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_cover_semantics_validated",
            module=logger.name,
            fields={key: normalized[key] for key in allowed_values},
        )
    )
    return normalized


def _normalize_cover_semantic_enum(value: Any) -> str:
    """Normalize provider formatting without broadening the semantic contract."""
    return re.sub(r"[\s-]+", "_", _s(value).strip().casefold())


def _attach_cached_artifact_family_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    raw_summary = payload.get("summary")
    raw_insights_candidates = payload.get("insights_candidates")
    raw_insights_final = payload.get("insights_final")
    raw_quotes_final = payload.get("quotes_final")
    summary: Dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    insights_candidates: List[Dict[str, Any]] = normalize_artifact_insights(
        raw_insights_candidates, prefix="candidate"
    )
    insights_final: List[Dict[str, Any]] = normalize_artifact_insights(
        raw_insights_final, prefix="insight"
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

    _validate_card_tldrs(
        summary,
        summary_abstained=summary_abstained,
        ctx=ctx,
    )
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
    if not insights_abstained and len(insights_final) < 2:
        missing_fields.append("insights_final")
    for index, insight in enumerate(insights_final):
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


def _word_count(value: str) -> int:
    return len(value.split())


def _validate_card_tldrs(
    summary: Dict[str, Any],
    *,
    summary_abstained: bool,
    ctx: RunContext,
) -> None:
    if summary_abstained:
        return
    standard_tldr = _validate_complete_tldr(
        summary.get("tldr"),
        limit=45,
        code="card_tldr_standard_invalid",
        field_name="summary.tldr",
    )
    compact_tldr = _validate_complete_tldr(
        summary.get("card_tldr_compact"),
        limit=18,
        code="card_tldr_compact_invalid",
        field_name="summary.card_tldr_compact",
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_card_tldrs_validated",
            module=logger.name,
            fields={
                "standard_word_count": _word_count(standard_tldr),
                "compact_word_count": _word_count(compact_tldr),
            },
        )
    )


def _validate_complete_tldr(
    value: Any,
    *,
    limit: int,
    code: str,
    field_name: str,
) -> str:
    text = " ".join(_s(value).split())
    count = _word_count(text)
    if (
        count < 1
        or count > limit
        or text.endswith(("...", "\u2026"))
        or text[-1] not in ".?!"
    ):
        raise AppError(
            code=code,
            message=f"{field_name} must be a complete sentence of 1 to {limit} words",
            retryable=False,
            context={"field": field_name, "word_count": count},
        )
    return text
