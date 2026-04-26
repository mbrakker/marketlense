from __future__ import annotations

import json
import logging
from typing import Any

from src.contracts.llm import LLMClientPolicy
from src.contracts.openai import OpenAIJSONImagePromptRequest, OpenAIJSONPromptRequest
from src.contracts.report_assets import (
    CropRefineCandidate,
    CropRefineRequest,
    CropRefineResponse,
    CropRefineResult,
    RankRequest,
    RankResponse,
)
from src.contracts.report_models import RankedCandidate
from src.contracts.run_context import RunContext
from src.services import llm_service
from src.utils.coercion import coerce_bool, coerce_int
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.rank_service")
openai_chat_json = llm_service.openai_chat_json
openai_chat_json_with_images = llm_service.openai_chat_json_with_images


def _rank_llm_policy(scope: str) -> LLMClientPolicy:
    return llm_service.default_openai_client_policy(scope=scope)


def _to_bbox(
    value: Any, fallback: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
        except (TypeError, ValueError):
            return fallback
    return fallback


def _parse_rank_items(
    *, content: str, parsed_json: Any, model: str
) -> list[dict[str, Any]]:
    parsed = parsed_json
    if parsed is None:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AppError(
                code="rank_response_invalid_json",
                message="Ranking response JSON parsing failed",
                cause=exc,
                retryable=False,
                context={"model": model},
            ) from exc

    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        for candidate_key in ("results", "data", "items"):
            raw_items = parsed.get(candidate_key)
            if isinstance(raw_items, list):
                return [item for item in raw_items if isinstance(item, dict)]

    raise AppError(
        code="rank_response_invalid_format",
        message="Ranking response did not return a JSON list of objects",
        retryable=False,
        context={"model": model},
    )


def _to_ranked_candidate(item: dict[str, Any]) -> RankedCandidate | None:
    try:
        score_value = coerce_int(item.get("score"), 0)
        return RankedCandidate(
            id=item.get("id", ""),
            type=item.get("type", ""),
            score=score_value,
            quality_score=coerce_int(item.get("quality_score"), score_value),
            insight_score=coerce_int(item.get("insight_score"), score_value),
            data_score=coerce_int(item.get("data_score"), score_value),
            keep=coerce_bool(
                item.get("keep"),
                True,
                true_tokens={"1", "true", "yes", "y", "on"},
                false_tokens={"0", "false", "no", "n", "off"},
            ),
            reject_reason=str(item.get("reject_reason") or ""),
        )
    except (ValueError, TypeError):
        return None


def _total_tokens(
    input_tokens: int | None, output_tokens: int | None, total_tokens: int | None
) -> int | None:
    if total_tokens is not None:
        return total_tokens
    if input_tokens is None and output_tokens is None:
        return None
    return int(input_tokens or 0) + int(output_tokens or 0)


def _fallback_crop_refine_results(
    candidates: list[CropRefineCandidate],
) -> list[CropRefineResult]:
    return [
        CropRefineResult(
            schema_version="1.0",
            id=candidate.id,
            is_valid_candidate=False,
            refined_bbox=candidate.bbox,
            include_title=True,
            include_note_if_present=True,
            confidence=0.0,
            reason="no_valid_response",
        )
        for candidate in candidates
    ]


def rank_candidates(request: RankRequest, ctx: RunContext) -> RankResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="rank_candidates_start",
            module=logger.name,
            fields={
                "count": request.candidate_count,
                "model": request.model,
                "temperature": request.temperature,
                "seed": request.seed,
                "timeout_seconds": request.timeout_seconds,
                "prompt_system_sha256": request.prompt_system_sha256,
                "prompt_user_sha256": request.prompt_user_sha256,
            },
        )
    )
    try:
        llm_client = llm_service.build_openai_client_from_callables(
            policy=_rank_llm_policy("rank_candidates"),
            openai_chat_json=openai_chat_json,
        )
        response = llm_client.openai_chat_json(
            OpenAIJSONPromptRequest(
                schema_version="1.0",
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                model=request.model,
                temperature=request.temperature,
                api_key=request.api_key,
                seed=request.seed,
                timeout_seconds=request.timeout_seconds,
                cost_ledger_path=request.cost_ledger_path,
                cost_daily_path=request.cost_daily_path,
                model_pricing=request.model_pricing,
                response_cache_enabled=request.response_cache_enabled,
                response_cache_dir=request.response_cache_dir,
                response_cache_ttl_seconds=request.response_cache_ttl_seconds,
            ),
            ctx,
        )
    except AppError as exc:
        raise AppError(
            code="rank_request_failed",
            message="Ranking request failed",
            cause=exc,
            retryable=exc.retryable,
            severity=exc.severity,
            context={"model": request.model},
        ) from exc

    content = response.text or ""
    items = _parse_rank_items(
        content=content, parsed_json=response.parsed_json, model=request.model
    )
    result: list[RankedCandidate] = []
    for item in items:
        ranked = _to_ranked_candidate(item)
        if ranked is not None:
            result.append(ranked)

    request_id = response.request_id
    prompt_tokens = response.input_tokens
    completion_tokens = response.output_tokens
    total_tokens = _total_tokens(
        prompt_tokens, completion_tokens, response.total_tokens
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="rank_candidates_complete",
            module=logger.name,
            fields={
                "count": len(result),
                "request_id": request_id or "",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        )
    )
    return RankResponse(
        schema_version="1.0",
        results=result,
        raw_content=content,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        request_id=request_id,
    )


def refine_candidate_crops(
    request: CropRefineRequest, ctx: RunContext
) -> CropRefineResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="crop_refine_start",
            module=logger.name,
            fields={
                "page": request.page,
                "candidate_count": len(request.candidates or []),
                "model": request.model,
                "temperature": request.temperature,
                "seed": request.seed,
                "timeout_seconds": request.timeout_seconds,
                "prompt_system_sha256": request.prompt_system_sha256,
                "prompt_user_sha256": request.prompt_user_sha256,
            },
        )
    )
    llm_client = llm_service.build_openai_client_from_callables(
        policy=_rank_llm_policy("crop_refine"),
        openai_chat_json_with_images=openai_chat_json_with_images,
    )
    response = llm_client.openai_chat_json_with_images(
        OpenAIJSONImagePromptRequest(
            schema_version="1.0",
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            model=request.model,
            temperature=request.temperature,
            api_key=request.api_key,
            image_paths=[request.page_image_path],
            seed=request.seed,
            timeout_seconds=request.timeout_seconds,
            cost_ledger_path=request.cost_ledger_path,
            cost_daily_path=request.cost_daily_path,
            model_pricing=request.model_pricing,
            response_cache_enabled=request.response_cache_enabled,
            response_cache_dir=request.response_cache_dir,
            response_cache_ttl_seconds=request.response_cache_ttl_seconds,
        ),
        ctx,
    )
    parsed = response.parsed_json if isinstance(response.parsed_json, dict) else {}
    raw_items_value = parsed.get("results")
    raw_items: list[object] = (
        raw_items_value if isinstance(raw_items_value, list) else []
    )
    by_id = {candidate.id: candidate for candidate in request.candidates}
    results: list[CropRefineResult] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or "").strip()
        candidate = by_id.get(cid)
        if not candidate:
            continue
        refined_bbox = _to_bbox(item.get("refined_bbox"), candidate.bbox)
        try:
            results.append(
                CropRefineResult(
                    schema_version="1.0",
                    id=cid,
                    is_valid_candidate=coerce_bool(
                        item.get("is_valid_candidate"),
                        False,
                        true_tokens={"1", "true", "yes", "y", "on"},
                        false_tokens={"0", "false", "no", "n", "off"},
                    ),
                    refined_bbox=refined_bbox,
                    include_title=coerce_bool(
                        item.get("include_title"),
                        True,
                        true_tokens={"1", "true", "yes", "y", "on"},
                        false_tokens={"0", "false", "no", "n", "off"},
                    ),
                    include_note_if_present=coerce_bool(
                        item.get("include_note_if_present"),
                        True,
                        true_tokens={"1", "true", "yes", "y", "on"},
                        false_tokens={"0", "false", "no", "n", "off"},
                    ),
                    confidence=float(item.get("confidence", 0.0) or 0.0),
                    reason=str(item.get("reason") or ""),
                )
            )
        except (TypeError, ValueError):
            continue
    if not results:
        results = _fallback_crop_refine_results(request.candidates)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="crop_refine_complete",
            module=logger.name,
            fields={
                "page": request.page,
                "candidate_count": len(request.candidates or []),
                "accepted_count": sum(
                    1 for result in results if result.is_valid_candidate
                ),
                "response_has_json": bool(response.parsed_json),
            },
        )
    )
    return CropRefineResponse(
        schema_version="1.0",
        results=results,
        raw_content=response.text or "",
        prompt_tokens=response.input_tokens,
        completion_tokens=response.output_tokens,
        total_tokens=(response.input_tokens or 0) + (response.output_tokens or 0),
        request_id=None,
    )
