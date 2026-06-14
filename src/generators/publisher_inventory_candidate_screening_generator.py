"""Compatibility facade for publisher-inventory candidate screening.

Focused implementation lives under `_publisher_inventory_candidate_screening`.
Existing callers continue importing the generator entrypoint and helper symbols
from this module.
"""

from __future__ import annotations

from src.contracts.publisher_inventory import (
    PublisherInventoryCandidateScreeningDecision,
    PublisherInventoryCandidateScreeningRequest,
    PublisherInventoryCandidateScreeningResponse,
)
from src.generators._publisher_inventory_candidate_screening.deterministic import (
    _TARGET_MAX_SCREENING_BATCHES,
    _MAX_DYNAMIC_SCREENING_BATCH_SIZE,
    _partition_candidates_for_llm_screening,
    _resolve_candidate_screening_batch_size,
    _fallback_screening_decision,
    _is_probable_report_asset,
    _prefilter_screening_decision,
    _has_strong_report_detail_url,
    _has_report_archive_context,
    _looks_like_human_archive_title,
    _has_pdf_report_signal,
    _has_editorial_report_detail_candidate,
    _looks_like_collection_root_candidate_url,
    _has_contextual_report_term,
    _looks_like_confident_direct_detail_source,
    _is_generic_cta_title,
    _looks_like_insights_detail_url,
    _has_specific_editorial_report_slug,
)
from src.generators._publisher_inventory_candidate_screening.llm_batches import (
    _MISSING_DECISION_REPAIR_BATCH_SIZE,
    _screen_candidate_batch,
    _chunk_candidates,
)
from src.generators._publisher_inventory_candidate_screening.response_policy import (
    _merge_screening_batches,
    _coerce_screening_decision_map,
    _build_screening_response,
    _deduplicate_screening_response,
    _apply_publisher_success_hard_rejections,
    _candidate_duplicate_key,
    _candidate_selection_key,
    _is_generic_duplicate_title,
    _is_publisher_success_marketing_title,
    _merge_screening_responses_with_prefilter,
)
from src.generators._publisher_inventory_candidate_screening.shared import (
    logger,
    _MAX_PROMPT_TITLE_LENGTH,
    _FALLBACK_REPORT_TITLE_MARKERS,
    _FALLBACK_SPECIFIC_REPORT_TITLE_MARKERS,
    _FALLBACK_NON_REPORT_TITLE_MARKERS,
    _FALLBACK_NON_REPORT_URL_MARKERS,
    _FALLBACK_REPORT_URL_MARKERS,
    _FALLBACK_REPORT_COLLECTION_SEGMENTS,
    _FALLBACK_LISTING_QUERY_KEYS,
    _EDITORIAL_REPORT_URL_MARKERS,
    _COLLECTION_ROOT_URL_TOKENS,
    _REPORT_CONTEXT_STOP_WORDS,
    _DIRECT_DETAIL_SOURCE_URL_MARKERS,
    _EDITORIAL_NON_REPORT_URL_MARKERS,
    _INFORMATIONAL_TITLE_PREFIXES,
    _GENERIC_CTA_TITLES,
    _EDITORIAL_SPECIFIC_REPORT_TITLE_MARKERS,
    _GENERIC_DUPLICATE_TITLE_FINGERPRINTS,
    _PUBLISHER_SUCCESS_ANALYST_MARKERS,
    _PUBLISHER_SUCCESS_HARD_PATTERNS,
    _normalize_title_fingerprint,
    _contains_any_title_marker,
    _normalize_marker_word,
    _publisher_reference_tokens,
    _truncate_prompt_text,
)
from src.services import llm_service, prompt_service
from src.utils.logging import log_event


def screen_publisher_inventory_candidates(
    request: PublisherInventoryCandidateScreeningRequest,
    ctx,
    *,
    openai_client=None,
    prompt_client=prompt_service,
) -> PublisherInventoryCandidateScreeningResponse:
    candidates = list(request.candidates)
    candidates_for_llm, prefilter_decisions = _partition_candidates_for_llm_screening(
        candidates
    )
    pre_accepted_count = sum(1 for decision in prefilter_decisions if decision.accepted)
    pre_rejected_count = len(prefilter_decisions) - pre_accepted_count
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_candidate_screen_start",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "insights_url": request.insights_url,
                "candidate_count": len(candidates),
                "llm_candidate_count": len(candidates_for_llm),
                "pre_accepted_count": pre_accepted_count,
                "pre_rejected_count": pre_rejected_count,
                "candidate_screening_enabled": request.settings.candidate_screening_enabled,
                "prompt_namespace": request.settings.candidate_screening_prompt_namespace,
            },
        )
    )
    if not request.settings.candidate_screening_enabled or not candidates:
        decisions = [
            PublisherInventoryCandidateScreeningDecision(
                schema_version="1.0",
                canonical_url=item.canonical_url,
                accepted=True,
                reason="candidate_screening_disabled",
            )
            for item in candidates
        ]
        response = PublisherInventoryCandidateScreeningResponse(
            schema_version="1.0",
            approved_items=candidates,
            rejected_items=[],
            decisions=decisions,
            model="screening_disabled",
            request_id=None,
            raw_response="",
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="publisher_inventory_candidate_screen_complete",
                module=logger.name,
                fields={
                    "publisher_name": request.publisher_name,
                    "candidate_count": len(candidates),
                    "approved_count": len(response.approved_items),
                    "rejected_count": len(response.rejected_items),
                    "model": response.model,
                    "screening_skipped": True,
                },
            )
        )
        deduped_response = _deduplicate_screening_response(
            response=response,
            publisher_name=request.publisher_name,
            ctx=ctx,
        )
        return deduped_response
    if not candidates_for_llm:
        response = _build_screening_response(
            candidates=candidates,
            decision_map={
                decision.canonical_url: decision for decision in prefilter_decisions
            },
            model="screening_prefilter_only",
            request_id=None,
            raw_response="",
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="publisher_inventory_candidate_screen_complete",
                module=logger.name,
                fields={
                    "publisher_name": request.publisher_name,
                    "candidate_count": len(candidates),
                    "approved_count": len(response.approved_items),
                    "rejected_count": len(response.rejected_items),
                    "model": response.model,
                    "screening_prefilter_only": True,
                },
            )
        )
        response = _apply_publisher_success_hard_rejections(
            response=response,
            publisher_name=request.publisher_name,
            ctx=ctx,
        )
        return _deduplicate_screening_response(
            response=response,
            publisher_name=request.publisher_name,
            ctx=ctx,
        )

    openai_client = openai_client or llm_service.build_client_for_settings(
        request.settings,
        scope="publisher_inventory_candidate_screening",
    )
    batch_size = _resolve_candidate_screening_batch_size(
        candidate_count=len(candidates_for_llm),
        configured_batch_size=int(request.settings.candidate_screening_batch_size),
    )
    batch_responses: list[PublisherInventoryCandidateScreeningResponse] = []
    candidate_batches = list(_chunk_candidates(candidates_for_llm, batch_size))
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_candidate_screen_batches_start",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "candidate_count": len(candidates),
                "llm_candidate_count": len(candidates_for_llm),
                "configured_batch_size": int(
                    request.settings.candidate_screening_batch_size
                ),
                "effective_batch_size": batch_size,
                "batch_count": len(candidate_batches),
            },
        )
    )
    for batch_index, batch_candidates in enumerate(candidate_batches, start=1):
        batch_response = _screen_candidate_batch(
            candidates=batch_candidates,
            request=request,
            ctx=ctx,
            openai_client=openai_client,
            prompt_client=prompt_client,
            batch_index=batch_index,
            batch_count=len(candidate_batches),
        )
        batch_responses.append(batch_response)
    screening_response = _merge_screening_batches(
        responses=batch_responses,
        candidate_count=len(candidates_for_llm),
    )
    screening_response = _merge_screening_responses_with_prefilter(
        candidates=candidates,
        llm_response=screening_response,
        prefilter_decisions=prefilter_decisions,
    )
    screening_response = _apply_publisher_success_hard_rejections(
        response=screening_response,
        publisher_name=request.publisher_name,
        ctx=ctx,
    )
    screening_response = _deduplicate_screening_response(
        response=screening_response,
        publisher_name=request.publisher_name,
        ctx=ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_candidate_screen_complete",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "candidate_count": len(candidates),
                "approved_count": len(screening_response.approved_items),
                "rejected_count": len(screening_response.rejected_items),
                "model": screening_response.model,
                "request_id": screening_response.request_id or "",
                "raw_response": screening_response.raw_response,
                "decisions": [
                    {
                        "canonical_url": decision.canonical_url,
                        "accepted": decision.accepted,
                        "reason": decision.reason,
                    }
                    for decision in screening_response.decisions
                ],
            },
        )
    )
    return screening_response


__all__ = [
    "logger",
    "_MAX_PROMPT_TITLE_LENGTH",
    "_FALLBACK_REPORT_TITLE_MARKERS",
    "_FALLBACK_SPECIFIC_REPORT_TITLE_MARKERS",
    "_FALLBACK_NON_REPORT_TITLE_MARKERS",
    "_FALLBACK_NON_REPORT_URL_MARKERS",
    "_FALLBACK_REPORT_URL_MARKERS",
    "_FALLBACK_REPORT_COLLECTION_SEGMENTS",
    "_FALLBACK_LISTING_QUERY_KEYS",
    "_EDITORIAL_REPORT_URL_MARKERS",
    "_COLLECTION_ROOT_URL_TOKENS",
    "_REPORT_CONTEXT_STOP_WORDS",
    "_DIRECT_DETAIL_SOURCE_URL_MARKERS",
    "_EDITORIAL_NON_REPORT_URL_MARKERS",
    "_INFORMATIONAL_TITLE_PREFIXES",
    "_GENERIC_CTA_TITLES",
    "_EDITORIAL_SPECIFIC_REPORT_TITLE_MARKERS",
    "_GENERIC_DUPLICATE_TITLE_FINGERPRINTS",
    "_PUBLISHER_SUCCESS_ANALYST_MARKERS",
    "_PUBLISHER_SUCCESS_HARD_PATTERNS",
    "_normalize_title_fingerprint",
    "_contains_any_title_marker",
    "_normalize_marker_word",
    "_publisher_reference_tokens",
    "_truncate_prompt_text",
    "_TARGET_MAX_SCREENING_BATCHES",
    "_MAX_DYNAMIC_SCREENING_BATCH_SIZE",
    "_partition_candidates_for_llm_screening",
    "_resolve_candidate_screening_batch_size",
    "_fallback_screening_decision",
    "_is_probable_report_asset",
    "_prefilter_screening_decision",
    "_has_strong_report_detail_url",
    "_has_report_archive_context",
    "_looks_like_human_archive_title",
    "_has_pdf_report_signal",
    "_has_editorial_report_detail_candidate",
    "_looks_like_collection_root_candidate_url",
    "_has_contextual_report_term",
    "_looks_like_confident_direct_detail_source",
    "_is_generic_cta_title",
    "_looks_like_insights_detail_url",
    "_has_specific_editorial_report_slug",
    "_merge_screening_batches",
    "_coerce_screening_decision_map",
    "_build_screening_response",
    "_deduplicate_screening_response",
    "_apply_publisher_success_hard_rejections",
    "_candidate_duplicate_key",
    "_candidate_selection_key",
    "_is_generic_duplicate_title",
    "_is_publisher_success_marketing_title",
    "_merge_screening_responses_with_prefilter",
    "_MISSING_DECISION_REPAIR_BATCH_SIZE",
    "_screen_candidate_batch",
    "_chunk_candidates",
    "screen_publisher_inventory_candidates",
]
