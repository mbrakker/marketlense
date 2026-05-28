"""Response adaptation and post-model policy for publisher screening.

This module owns model JSON decision coercion, response assembly, prefilter
merge behavior, duplicate collapse, and publisher-success hard rejections.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from src.contracts.publisher_inventory import (
    PublisherInventoryCandidateScreeningDecision,
    PublisherInventoryCandidateScreeningItem,
    PublisherInventoryCandidateScreeningResponse,
)
from src.generators._publisher_inventory_candidate_screening.shared import (
    _FALLBACK_REPORT_TITLE_MARKERS,
    _GENERIC_DUPLICATE_TITLE_FINGERPRINTS,
    _PUBLISHER_SUCCESS_ANALYST_MARKERS,
    _PUBLISHER_SUCCESS_HARD_PATTERNS,
    _contains_any_title_marker,
    _normalize_title_fingerprint,
    _publisher_reference_tokens,
    logger,
)
from src.utils.errors import AppError
from src.utils.logging import log_event


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
        item for item in response.approved_items if item.canonical_url in duplicate_map
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
    if title_key and not _is_generic_duplicate_title(title_key):
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


def _is_generic_duplicate_title(title_key: str) -> bool:
    normalized_title = _normalize_title_fingerprint(title_key)
    if not normalized_title:
        return True
    if normalized_title in _GENERIC_DUPLICATE_TITLE_FINGERPRINTS:
        return True
    tokens = [token for token in normalized_title.split() if token]
    if not tokens or any(char.isdigit() for char in normalized_title):
        return False
    if tokens[0] not in {"download", "get", "learn", "read", "view"}:
        return False
    if len(tokens) > 4:
        return False
    return _contains_any_title_marker(normalized_title, _FALLBACK_REPORT_TITLE_MARKERS)


def _is_publisher_success_marketing_title(*, title: str, publisher_name: str) -> bool:
    normalized_title = _normalize_title_fingerprint(title)
    if not normalized_title:
        return False
    normalized_title = re.sub(r"^(read|download|view)\s+now\s+", "", normalized_title)
    publisher_tokens = _publisher_reference_tokens(publisher_name)
    if publisher_tokens and not any(
        token in normalized_title for token in publisher_tokens
    ):
        return False
    if any(
        pattern.search(normalized_title) for pattern in _PUBLISHER_SUCCESS_HARD_PATTERNS
    ):
        return True
    return "leader" in normalized_title and any(
        marker in normalized_title for marker in _PUBLISHER_SUCCESS_ANALYST_MARKERS
    )


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


__all__ = [
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
]
