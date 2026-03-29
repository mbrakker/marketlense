from __future__ import annotations

import json
import logging
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


def screen_publisher_inventory_candidates(
    request: PublisherInventoryCandidateScreeningRequest,
    ctx,
    *,
    openai_client=None,
    prompt_client=prompt_service,
) -> PublisherInventoryCandidateScreeningResponse:
    candidates = list(request.candidates)
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
        return response

    openai_client = openai_client or llm_service.build_openai_client(
        base_client=openai_service,
        policy=llm_service.openai_client_policy_from_settings(
            request.settings,
            scope="publisher_inventory_candidate_screening",
        ),
    )
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
                        "title": item.title,
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
            context={"publisher_name": request.publisher_name},
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
                "response_preview": (response.text or "")[:400],
            },
        )
    screening_response = _coerce_screening_response(
        payload=payload,
        candidates=candidates,
        model=str(response.model or prompt_bundle.resolved_model or ""),
        request_id=str(response.request_id or "") or None,
        raw_response=str(response.text or ""),
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


def _coerce_screening_response(
    *,
    payload: dict[str, Any],
    candidates: list[PublisherInventoryCandidateScreeningItem],
    model: str,
    request_id: str | None,
    raw_response: str,
) -> PublisherInventoryCandidateScreeningResponse:
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
    missing_urls = [
        candidate.canonical_url
        for candidate in candidates
        if candidate.canonical_url not in decision_map
    ]
    if missing_urls:
        raise AppError(
            code="publisher_inventory_candidate_screen_incomplete",
            message="Candidate screening did not return a decision for every candidate",
            retryable=False,
            severity="error",
            context={"missing_urls": missing_urls},
        )
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
