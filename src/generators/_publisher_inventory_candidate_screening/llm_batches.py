"""LLM batch execution for publisher-inventory candidate screening.

This module owns prompt rendering, JSON model calls, and bounded repair calls
for missing per-candidate decisions.
"""

from __future__ import annotations

import json

from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseResult
from src.contracts.publisher_inventory import (
    PublisherInventoryCandidateScreeningItem,
    PublisherInventoryCandidateScreeningRequest,
    PublisherInventoryCandidateScreeningResponse,
)
from src.generators._publisher_inventory_candidate_screening.deterministic import (
    _fallback_screening_decision,
)
from src.generators._publisher_inventory_candidate_screening.response_policy import (
    _build_screening_response,
    _coerce_screening_decision_map,
)
from src.generators._publisher_inventory_candidate_screening.shared import (
    _truncate_prompt_text,
    logger,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.utils.errors import AppError
from src.utils.logging import log_event

_MISSING_DECISION_REPAIR_BATCH_SIZE = 1


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
                "prompt_content_hash": prompt_bundle.prompt_content_hash,
                "execution_identity": prompt_bundle.execution_identity.execution_identity,
                "system_prompt_chars": len(prompt_bundle.system_prompt),
                "user_prompt_chars": len(prompt_bundle.user_prompt),
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


def _chunk_candidates(
    candidates: list[PublisherInventoryCandidateScreeningItem],
    batch_size: int,
) -> list[list[PublisherInventoryCandidateScreeningItem]]:
    return [
        candidates[start : start + batch_size]
        for start in range(0, len(candidates), batch_size)
    ]


__all__ = [
    "_MISSING_DECISION_REPAIR_BATCH_SIZE",
    "_screen_candidate_batch",
    "_chunk_candidates",
]
