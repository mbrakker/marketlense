from __future__ import annotations

import json
import logging
import re
import unicodedata
from urllib.parse import urlsplit
from typing import Any

from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseResult
from src.contracts.publisher_inventory import (
    PublisherInventoryCandidateScreeningDecision,
    PublisherInventoryCandidateScreeningItem,
    PublisherInventoryCandidateScreeningRequest,
    PublisherInventoryCandidateScreeningResponse,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.services import llm_service, openai_service, prompt_service
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger(
    "market_lense.publisher_inventory_candidate_screening_generator"
)

_MISSING_DECISION_REPAIR_BATCH_SIZE = 1
_TARGET_MAX_SCREENING_BATCHES = 8
_MAX_DYNAMIC_SCREENING_BATCH_SIZE = 35
_MAX_PROMPT_TITLE_LENGTH = 280
_FALLBACK_REPORT_TITLE_MARKERS = (
    "report",
    "rapport",
    "white paper",
    "whitepaper",
    "study",
    "survey",
    "benchmark",
    "outlook",
    "ebook",
    "guide",
    "playbook",
    "forecast",
    "outlook",
    "barometer",
    "barometre",
    "observatory",
    "observatoire",
    "index",
    "pulse",
    "scorecard",
    "trends",
    "trend",
    "research",
    "analysis",
    "infographic",
    "note de conjoncture",
)
_FALLBACK_SPECIFIC_REPORT_TITLE_MARKERS = (
    "annual report",
    "benchmark",
    "ebook",
    "forecast",
    "index",
    "outlook",
    "playbook",
    "scorecard",
    "study",
    "survey",
    "transparency report",
    "white paper",
    "whitepaper",
)
_FALLBACK_NON_REPORT_TITLE_MARKERS = (
    "cookie notice",
    "cookie policy",
    "privacy notice",
    "privacy policy",
    "code of conduct",
    "modern slavery",
    "gender pay",
    "tax strategy",
    "case study",
    "contact us",
    "join the panel",
    "publication archive",
    "all products",
    "award-winning experts",
    "accurate data",
    "real people",
    "pioneering tech",
    "binding corporate rules",
    "bcr summary",
    "gender equality index",
    "equality index",
    "index de l egalite",
    "index de l égalité",
    "egalite femmes hommes",
    "égalité femmes-hommes",
    "masterclass",
    "template",
    "templates",
    "training",
    "video",
    "webinar",
)
_FALLBACK_NON_REPORT_URL_MARKERS = (
    "/article/",
    "/articles/",
    "/academy/",
    "/blog/",
    "/case-studies/",
    "/careers",
    "/contact",
    "/login",
    "/news/",
    "/newsroom/",
    "/panel",
    "/press-release",
    "/press-releases/",
    "/products",
    "/privacy",
    "/cookie",
    "/modern-slavery",
    "/tax-strategy",
    "/code-of-conduct",
    "/training/",
    "/video",
    "/webinar",
    "academy.",
    "support.",
    "/hc/en-us/articles/",
)
_FALLBACK_REPORT_URL_MARKERS = (
    "/benchmark",
    "/ebook",
    "/ebooks/",
    "/forecast",
    "/outlook",
    "/playbook",
    "/report",
    "/reports/",
    "/reports_posts/",
    "/research/",
    "/study",
    "/studies/",
    "/survey",
    "/whitepaper",
    "/whitepapers/",
)
_FALLBACK_REPORT_COLLECTION_SEGMENTS = {
    "all",
    "asset",
    "assets",
    "benchmark",
    "benchmarks",
    "ebook",
    "ebooks",
    "guide",
    "guides",
    "insights",
    "library",
    "playbook",
    "playbooks",
    "report",
    "reports",
    "research",
    "resource",
    "resources",
    "studies",
    "study",
    "survey",
    "surveys",
    "whitepaper",
    "whitepapers",
}
_FALLBACK_LISTING_QUERY_KEYS = (
    "category=",
    "page=",
    "pagenum=",
    "resource_type=",
    "tag=",
    "topic=",
    "type=",
)

_PUBLISHER_SUCCESS_ANALYST_MARKERS = (
    "gartner",
    "forrester",
    "omdia",
    "idc",
    "peak matrix",
    "marketscape",
    "magic quadrant",
    "quadrant",
    "wave",
)
_PUBLISHER_SUCCESS_HARD_PATTERNS = (
    re.compile(r"\bnamed\s+(?:a|an|the\s+)?leader\b"),
    re.compile(r"\bnames?\b.*\ba\s+leader\b"),
    re.compile(r"\brated\s+(?:a|an|the\s+)?leader\b"),
    re.compile(r"\brecogni[sz]ed\s+as\s+(?:a|an|the\s+)?leader\b"),
    re.compile(r"\btop[- ]rated\b"),
    re.compile(r"\btop ratings?\b"),
    re.compile(r"\bcustomer favorite\b"),
    re.compile(r"\bhighest[- ]designated leader\b"),
    re.compile(r"\bbrings home the gold\b"),
    re.compile(r"\b(?:earns?|receiv(?:e|es|ing)|wins?)\s+\d+\s+(?:exceptional[- ]rated\s+)?(?:gold\s+)?medals?\b"),
    re.compile(r"\bgoes big\b"),
    re.compile(r"\bjust ask\b"),
    re.compile(r"\bearns?\s+top ratings?\b"),
    re.compile(r"\bleader in\b"),
    re.compile(r"\bleader for\b"),
)


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

    openai_client = openai_client or llm_service.build_openai_client(
        base_client=openai_service,
        policy=llm_service.openai_client_policy_from_settings(
            request.settings,
            scope="publisher_inventory_candidate_screening",
        ),
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
                "configured_batch_size": int(request.settings.candidate_screening_batch_size),
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


def _screen_candidate_batch(
    *,
    candidates: list[PublisherInventoryCandidateScreeningItem],
    request: PublisherInventoryCandidateScreeningRequest,
    ctx,
    openai_client,
    prompt_client,
    batch_index: int,
    batch_count: int,
    repair_depth: int = 0,
) -> PublisherInventoryCandidateScreeningResponse:
    prompt_bundle = prepare_prompt_bundle(
        namespace=request.settings.candidate_screening_prompt_namespace,
        settings=request.settings,
        ctx=ctx,
        prompt_client=prompt_client,
        system_variables={},
        user_variables={
            "publisher_name": request.publisher_name,
            "insights_url": request.insights_url,
            "candidate_items_json": json.dumps(
                [
                    {
                            "canonical_url": item.canonical_url,
                            "title": _truncate_prompt_text(item.title),
                            "discovered_on_page_number": item.discovered_on_page_number,
                            "source_page_url": item.source_page_url,
                        }
                    for item in candidates
                ],
                ensure_ascii=True,
                indent=2,
            ),
        },
        reload_if_changed=True,
        default_model=request.settings.candidate_screening_model,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_candidate_screen_prompt_rendered",
            module=logger.name,
            fields={
                "namespace": request.settings.candidate_screening_prompt_namespace,
                "batch_index": batch_index,
                "batch_count": batch_count,
                "batch_candidate_count": len(candidates),
                "system_path": prompt_bundle.prompt_set.system.path,
                "system_sha256": prompt_bundle.prompt_set.system.sha256,
                "user_path": prompt_bundle.prompt_set.user.path,
                "user_sha256": prompt_bundle.prompt_set.user.sha256,
                "resolved_model": prompt_bundle.resolved_model,
                "system_prompt": prompt_bundle.system_prompt,
                "user_prompt": prompt_bundle.user_prompt,
            },
        )
    )
    try:
        response: OpenAIResponseResult = openai_client.openai_chat_json(
            OpenAIJSONPromptRequest(
                schema_version="1.0",
                system_prompt=prompt_bundle.system_prompt,
                user_prompt=prompt_bundle.user_prompt,
                model=prompt_bundle.resolved_model,
                temperature=request.settings.candidate_screening_temperature,
                api_key=request.settings.openai_api_key,
                seed=request.settings.openai_seed,
                timeout_seconds=request.settings.candidate_screening_timeout_seconds,
                cost_ledger_path=request.settings.cost_ledger_path,
                cost_daily_path=request.settings.cost_daily_path,
                model_pricing=request.settings.model_pricing,
            ),
            ctx,
        )
    except AppError:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise AppError(
            code="publisher_inventory_candidate_screen_failed",
            message="Publisher inventory candidate screening failed",
            cause=exc,
            retryable=True,
            context={
                "publisher_name": request.publisher_name,
                "batch_index": batch_index,
                "batch_count": batch_count,
            },
        ) from exc

    payload = response.parsed_json if isinstance(response.parsed_json, dict) else None
    if payload is None:
        raise AppError(
            code="publisher_inventory_candidate_screen_invalid_json",
            message="Candidate screening returned no JSON object",
            retryable=False,
            severity="error",
            context={
                "publisher_name": request.publisher_name,
                "batch_index": batch_index,
                "batch_count": batch_count,
                "response_preview": (response.text or "")[:400],
            },
        )
    primary_model = str(response.model or prompt_bundle.resolved_model or "")
    raw_request_id = str(response.request_id or "") or None
    raw_response = str(response.text or "")
    decision_map = _coerce_screening_decision_map(
        payload=payload,
        candidates=candidates,
    )
    models: list[str] = [primary_model] if primary_model else []
    request_ids: list[str] = [raw_request_id] if raw_request_id else []
    raw_responses: list[str] = [raw_response] if raw_response else []
    missing_candidates = [
        candidate
        for candidate in candidates
        if candidate.canonical_url not in decision_map
    ]
    if missing_candidates and repair_depth == 0 and len(candidates) > 1:
        repair_batches = _chunk_candidates(
            missing_candidates,
            _MISSING_DECISION_REPAIR_BATCH_SIZE,
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="publisher_inventory_candidate_screen_batch_repair_start",
                module=logger.name,
                fields={
                    "publisher_name": request.publisher_name,
                    "batch_index": batch_index,
                    "batch_count": batch_count,
                    "original_batch_candidate_count": len(candidates),
                    "missing_candidate_count": len(missing_candidates),
                    "repair_batch_count": len(repair_batches),
                    "missing_urls": [
                        candidate.canonical_url for candidate in missing_candidates
                    ],
                },
            )
        )
        for repair_index, repair_candidates in enumerate(repair_batches, start=1):
            repair_response = _screen_candidate_batch(
                candidates=repair_candidates,
                request=request,
                ctx=ctx,
                openai_client=openai_client,
                prompt_client=prompt_client,
                batch_index=repair_index,
                batch_count=len(repair_batches),
                repair_depth=repair_depth + 1,
            )
            for decision in repair_response.decisions:
                decision_map[decision.canonical_url] = decision
            if repair_response.model:
                models.append(repair_response.model)
            if repair_response.request_id:
                request_ids.append(repair_response.request_id)
            if repair_response.raw_response:
                raw_responses.append(repair_response.raw_response)
        missing_candidates = [
            candidate
            for candidate in candidates
            if candidate.canonical_url not in decision_map
        ]
    if missing_candidates:
        fallback_decisions = {
            candidate.canonical_url: _fallback_screening_decision(candidate)
            for candidate in missing_candidates
        }
        decision_map.update(fallback_decisions)
        logger.warning(
            log_event(
                ctx,
                role="generator",
                event="publisher_inventory_candidate_screen_missing_decisions_fallback",
                module=logger.name,
                fields={
                    "publisher_name": request.publisher_name,
                    "batch_index": batch_index,
                    "batch_count": batch_count,
                    "fallback_count": len(fallback_decisions),
                    "fallback_urls": sorted(fallback_decisions),
                },
            )
        )
    return _build_screening_response(
        candidates=candidates,
        decision_map=decision_map,
        model=",".join(dict.fromkeys(models)),
        request_id=",".join(dict.fromkeys(request_ids)) or None,
        raw_response="\n\n".join(raw_responses),
    )


def _merge_screening_batches(
    *,
    responses: list[PublisherInventoryCandidateScreeningResponse],
    candidate_count: int,
) -> PublisherInventoryCandidateScreeningResponse:
    if not responses:
        raise AppError(
            code="publisher_inventory_candidate_screen_empty",
            message="Candidate screening produced no batch responses",
            retryable=False,
            severity="error",
            context={"candidate_count": candidate_count},
        )
    if len(responses) == 1:
        return responses[0]
    approved_items: list[PublisherInventoryCandidateScreeningItem] = []
    rejected_items: list[PublisherInventoryCandidateScreeningItem] = []
    decisions: list[PublisherInventoryCandidateScreeningDecision] = []
    models: list[str] = []
    request_ids: list[str] = []
    raw_responses: list[str] = []
    for response in responses:
        approved_items.extend(response.approved_items)
        rejected_items.extend(response.rejected_items)
        decisions.extend(response.decisions)
        if response.model:
            models.append(response.model)
        if response.request_id:
            request_ids.append(response.request_id)
        if response.raw_response:
            raw_responses.append(response.raw_response)
    return PublisherInventoryCandidateScreeningResponse(
        schema_version="1.0",
        approved_items=approved_items,
        rejected_items=rejected_items,
        decisions=decisions,
        model=",".join(dict.fromkeys(models)),
        request_id=",".join(dict.fromkeys(request_ids)) or None,
        raw_response="\n\n".join(raw_responses),
    )


def _coerce_screening_decision_map(
    *,
    payload: dict[str, Any],
    candidates: list[PublisherInventoryCandidateScreeningItem],
) -> dict[str, PublisherInventoryCandidateScreeningDecision]:
    raw_decisions = payload.get("decisions")
    if not isinstance(raw_decisions, list):
        raise AppError(
            code="publisher_inventory_candidate_screen_invalid_payload",
            message="Candidate screening payload must contain a decisions list",
            retryable=False,
            severity="error",
        )
    candidate_by_url = {candidate.canonical_url: candidate for candidate in candidates}
    decision_map: dict[str, PublisherInventoryCandidateScreeningDecision] = {}
    for item in raw_decisions:
        if not isinstance(item, dict):
            continue
        canonical_url = str(item.get("canonical_url") or "").strip()
        if canonical_url not in candidate_by_url or canonical_url in decision_map:
            continue
        accepted = item.get("accepted")
        if not isinstance(accepted, bool):
            raise AppError(
                code="publisher_inventory_candidate_screen_invalid_payload",
                message="Candidate screening decisions must include boolean accepted values",
                retryable=False,
                severity="error",
                context={"canonical_url": canonical_url},
            )
        reason = " ".join(str(item.get("reason") or "").split()).strip()
        if not reason:
            raise AppError(
                code="publisher_inventory_candidate_screen_invalid_payload",
                message="Candidate screening decisions must include a non-empty reason",
                retryable=False,
                severity="error",
                context={"canonical_url": canonical_url},
            )
        decision_map[canonical_url] = PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=canonical_url,
            accepted=accepted,
            reason=reason,
        )
    return decision_map


def _build_screening_response(
    *,
    candidates: list[PublisherInventoryCandidateScreeningItem],
    decision_map: dict[str, PublisherInventoryCandidateScreeningDecision],
    model: str,
    request_id: str | None,
    raw_response: str,
) -> PublisherInventoryCandidateScreeningResponse:
    approved_items: list[PublisherInventoryCandidateScreeningItem] = []
    rejected_items: list[PublisherInventoryCandidateScreeningItem] = []
    decisions: list[PublisherInventoryCandidateScreeningDecision] = []
    for candidate in candidates:
        decision = decision_map[candidate.canonical_url]
        decisions.append(decision)
        if decision.accepted:
            approved_items.append(candidate)
            continue
        rejected_items.append(candidate)
    return PublisherInventoryCandidateScreeningResponse(
        schema_version="1.0",
        approved_items=approved_items,
        rejected_items=rejected_items,
        decisions=decisions,
        model=model,
        request_id=request_id,
        raw_response=raw_response,
    )


def _deduplicate_screening_response(
    *,
    response: PublisherInventoryCandidateScreeningResponse,
    publisher_name: str,
    ctx,
) -> PublisherInventoryCandidateScreeningResponse:
    if len(response.approved_items) <= 1:
        return response
    groups: dict[str, list[PublisherInventoryCandidateScreeningItem]] = {}
    for item in response.approved_items:
        groups.setdefault(_candidate_duplicate_key(item), []).append(item)
    duplicate_map: dict[str, str] = {}
    keep_urls: set[str] = set()
    for items in groups.values():
        winner = min(items, key=_candidate_selection_key)
        keep_urls.add(winner.canonical_url)
        for item in items:
            if item.canonical_url == winner.canonical_url:
                continue
            duplicate_map[item.canonical_url] = winner.canonical_url
    if not duplicate_map:
        return response
    approved_items = [
        item for item in response.approved_items if item.canonical_url in keep_urls
    ]
    rejected_items = list(response.rejected_items) + [
        item
        for item in response.approved_items
        if item.canonical_url in duplicate_map
    ]
    decisions: list[PublisherInventoryCandidateScreeningDecision] = []
    for decision in response.decisions:
        kept_url = duplicate_map.get(decision.canonical_url)
        if not kept_url:
            decisions.append(decision)
            continue
        decisions.append(
            PublisherInventoryCandidateScreeningDecision(
                schema_version="1.0",
                canonical_url=decision.canonical_url,
                accepted=False,
                reason=f"duplicate_in_run keep {kept_url}",
            )
        )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_candidate_screen_duplicates_collapsed",
            module=logger.name,
            fields={
                "publisher_name": publisher_name,
                "duplicate_count": len(duplicate_map),
                "kept_urls": sorted(keep_urls),
                "duplicate_urls": duplicate_map,
            },
        )
    )
    return PublisherInventoryCandidateScreeningResponse(
        schema_version=response.schema_version,
        approved_items=approved_items,
        rejected_items=rejected_items,
        decisions=decisions,
        model=response.model,
        request_id=response.request_id,
        raw_response=response.raw_response,
    )


def _apply_publisher_success_hard_rejections(
    *,
    response: PublisherInventoryCandidateScreeningResponse,
    publisher_name: str,
    ctx,
) -> PublisherInventoryCandidateScreeningResponse:
    if not response.approved_items:
        return response
    forced_rejections: dict[str, str] = {}
    for item in response.approved_items:
        if _is_publisher_success_marketing_title(
            title=item.title,
            publisher_name=publisher_name,
        ):
            forced_rejections[item.canonical_url] = "publisher_success_marketing"
    if not forced_rejections:
        return response
    approved_items = [
        item
        for item in response.approved_items
        if item.canonical_url not in forced_rejections
    ]
    rejected_items = list(response.rejected_items) + [
        item
        for item in response.approved_items
        if item.canonical_url in forced_rejections
    ]
    decisions: list[PublisherInventoryCandidateScreeningDecision] = []
    for decision in response.decisions:
        reason = forced_rejections.get(decision.canonical_url)
        if not reason:
            decisions.append(decision)
            continue
        decisions.append(
            PublisherInventoryCandidateScreeningDecision(
                schema_version="1.0",
                canonical_url=decision.canonical_url,
                accepted=False,
                reason=reason,
            )
        )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_candidate_screen_hard_rejections_applied",
            module=logger.name,
            fields={
                "publisher_name": publisher_name,
                "forced_rejection_count": len(forced_rejections),
                "forced_rejection_urls": sorted(forced_rejections),
            },
        )
    )
    return PublisherInventoryCandidateScreeningResponse(
        schema_version=response.schema_version,
        approved_items=approved_items,
        rejected_items=rejected_items,
        decisions=decisions,
        model=response.model,
        request_id=response.request_id,
        raw_response=response.raw_response,
    )


def _candidate_duplicate_key(
    candidate: PublisherInventoryCandidateScreeningItem,
) -> str:
    title_key = _normalize_title_fingerprint(candidate.title)
    if title_key:
        return title_key
    return candidate.canonical_url


def _candidate_selection_key(
    candidate: PublisherInventoryCandidateScreeningItem,
) -> tuple[int, int, int, int, str]:
    parsed = urlsplit(candidate.canonical_url)
    has_query = 1 if parsed.query else 0
    return (
        has_query,
        candidate.discovered_on_page_number,
        len(parsed.path or ""),
        len(candidate.canonical_url),
        candidate.canonical_url,
    )


def _normalize_title_fingerprint(title: str) -> str:
    token = unicodedata.normalize("NFKD", str(title or ""))
    normalized = "".join(
        char.casefold() if char.isalnum() or char.isspace() else " "
        for char in token
    )
    return " ".join(normalized.split()).strip()


def _contains_any_title_marker(title: str, markers: tuple[str, ...]) -> bool:
    normalized_title = f" {str(title or '').strip()} "
    return any(f" {marker} " in normalized_title for marker in markers)


def _is_publisher_success_marketing_title(*, title: str, publisher_name: str) -> bool:
    normalized_title = _normalize_title_fingerprint(title)
    if not normalized_title:
        return False
    normalized_title = re.sub(r"^(read|download|view)\s+now\s+", "", normalized_title)
    publisher_tokens = _publisher_reference_tokens(publisher_name)
    if publisher_tokens and not any(token in normalized_title for token in publisher_tokens):
        return False
    if any(pattern.search(normalized_title) for pattern in _PUBLISHER_SUCCESS_HARD_PATTERNS):
        return True
    return (
        "leader" in normalized_title
        and any(marker in normalized_title for marker in _PUBLISHER_SUCCESS_ANALYST_MARKERS)
    )


def _chunk_candidates(
    candidates: list[PublisherInventoryCandidateScreeningItem],
    batch_size: int,
) -> list[list[PublisherInventoryCandidateScreeningItem]]:
    return [
        candidates[start : start + batch_size]
        for start in range(0, len(candidates), batch_size)
    ]


def _partition_candidates_for_llm_screening(
    candidates: list[PublisherInventoryCandidateScreeningItem],
) -> tuple[
    list[PublisherInventoryCandidateScreeningItem],
    list[PublisherInventoryCandidateScreeningDecision],
]:
    llm_candidates: list[PublisherInventoryCandidateScreeningItem] = []
    prefilter_decisions: list[PublisherInventoryCandidateScreeningDecision] = []
    for candidate in candidates:
        prefilter_decision = _prefilter_screening_decision(candidate)
        if prefilter_decision is None:
            llm_candidates.append(candidate)
            continue
        prefilter_decisions.append(prefilter_decision)
    return llm_candidates, prefilter_decisions


def _resolve_candidate_screening_batch_size(
    *,
    candidate_count: int,
    configured_batch_size: int,
) -> int:
    batch_size = max(configured_batch_size, 1)
    if candidate_count <= batch_size * _TARGET_MAX_SCREENING_BATCHES:
        return batch_size
    dynamic_batch_size = (candidate_count + _TARGET_MAX_SCREENING_BATCHES - 1) // _TARGET_MAX_SCREENING_BATCHES
    return max(batch_size, min(dynamic_batch_size, _MAX_DYNAMIC_SCREENING_BATCH_SIZE))


def _merge_screening_responses_with_prefilter(
    *,
    candidates: list[PublisherInventoryCandidateScreeningItem],
    llm_response: PublisherInventoryCandidateScreeningResponse,
    prefilter_decisions: list[PublisherInventoryCandidateScreeningDecision],
) -> PublisherInventoryCandidateScreeningResponse:
    if not prefilter_decisions:
        return llm_response
    decision_map = {
        decision.canonical_url: decision for decision in llm_response.decisions
    }
    decision_map.update(
        {decision.canonical_url: decision for decision in prefilter_decisions}
    )
    return _build_screening_response(
        candidates=candidates,
        decision_map=decision_map,
        model=llm_response.model,
        request_id=llm_response.request_id,
        raw_response=llm_response.raw_response,
    )


def _fallback_screening_decision(
    candidate: PublisherInventoryCandidateScreeningItem,
) -> PublisherInventoryCandidateScreeningDecision:
    normalized_title = _normalize_title_fingerprint(candidate.title)
    normalized_url = candidate.canonical_url.casefold()
    if _contains_any_title_marker(normalized_title, _FALLBACK_NON_REPORT_TITLE_MARKERS):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=False,
            reason="fallback_non_report_title",
        )
    if any(marker in normalized_url for marker in _FALLBACK_NON_REPORT_URL_MARKERS):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=False,
            reason="fallback_non_report_url",
        )
    if _has_strong_report_detail_url(candidate.canonical_url):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=True,
            reason="fallback_report_detail_url",
        )
    if _contains_any_title_marker(
        normalized_title, _FALLBACK_SPECIFIC_REPORT_TITLE_MARKERS
    ):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=True,
            reason="fallback_specific_report_title",
        )
    if _contains_any_title_marker(normalized_title, _FALLBACK_REPORT_TITLE_MARKERS):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=True,
            reason="fallback_report_signal",
        )
    return PublisherInventoryCandidateScreeningDecision(
        schema_version="1.0",
        canonical_url=candidate.canonical_url,
        accepted=False,
        reason="fallback_unknown_candidate",
    )


def _is_probable_report_asset(
    candidate: PublisherInventoryCandidateScreeningItem,
) -> bool:
    normalized_title = _normalize_title_fingerprint(candidate.title)
    normalized_url = candidate.canonical_url.casefold()
    if normalized_url.endswith(".pdf"):
        return True
    if _has_strong_report_detail_url(candidate.canonical_url):
        return True
    if any(marker in normalized_url for marker in _FALLBACK_NON_REPORT_URL_MARKERS):
        return False
    if _contains_any_title_marker(normalized_title, _FALLBACK_NON_REPORT_TITLE_MARKERS):
        return False
    return _contains_any_title_marker(normalized_title, _FALLBACK_REPORT_TITLE_MARKERS)


def _prefilter_screening_decision(
    candidate: PublisherInventoryCandidateScreeningItem,
) -> PublisherInventoryCandidateScreeningDecision | None:
    normalized_title = _normalize_title_fingerprint(candidate.title)
    normalized_url = candidate.canonical_url.casefold()
    if any(marker in normalized_url for marker in _FALLBACK_NON_REPORT_URL_MARKERS):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=False,
            reason="low_report_probability_prefilter",
        )
    if _contains_any_title_marker(normalized_title, _FALLBACK_NON_REPORT_TITLE_MARKERS):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=False,
            reason="low_report_probability_prefilter",
        )
    if _has_strong_report_detail_url(candidate.canonical_url):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=True,
            reason="strong_report_detail_url_prefilter",
        )
    if _contains_any_title_marker(
        normalized_title, _FALLBACK_SPECIFIC_REPORT_TITLE_MARKERS
    ):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=True,
            reason="specific_report_title_prefilter",
        )
    if _is_probable_report_asset(candidate):
        return None
    return PublisherInventoryCandidateScreeningDecision(
        schema_version="1.0",
        canonical_url=candidate.canonical_url,
        accepted=False,
        reason="low_report_probability_prefilter",
    )


def _has_strong_report_detail_url(url: str) -> bool:
    normalized_url = str(url or "").strip().casefold()
    if not normalized_url:
        return False
    if normalized_url.endswith(".pdf"):
        return True
    if any(marker in normalized_url for marker in _FALLBACK_NON_REPORT_URL_MARKERS):
        return False
    parsed = urlsplit(normalized_url)
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if len(path_segments) < 2:
        return False
    if any(token in parsed.query for token in _FALLBACK_LISTING_QUERY_KEYS):
        return False
    if "/page/" in parsed.path or "/type/" in parsed.path:
        return False
    if not any(marker in normalized_url for marker in _FALLBACK_REPORT_URL_MARKERS):
        return False
    leaf_segment = path_segments[-1]
    if leaf_segment.isdigit() or leaf_segment in _FALLBACK_REPORT_COLLECTION_SEGMENTS:
        return False
    return True


def _publisher_reference_tokens(publisher_name: str) -> tuple[str, ...]:
    normalized_name = _normalize_title_fingerprint(publisher_name)
    if not normalized_name:
        return ()
    tokens = [token for token in normalized_name.split() if len(token) >= 4]
    unique_tokens: list[str] = []
    for token in [normalized_name, *tokens]:
        if token and token not in unique_tokens:
            unique_tokens.append(token)
    return tuple(unique_tokens)


def _truncate_prompt_text(value: str) -> str:
    normalized_value = " ".join(str(value or "").split()).strip()
    if len(normalized_value) <= _MAX_PROMPT_TITLE_LENGTH:
        return normalized_value
    return normalized_value[: _MAX_PROMPT_TITLE_LENGTH - 1].rstrip() + "…"
