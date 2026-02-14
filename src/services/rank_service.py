from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from datetime import datetime, timezone
from openai import OpenAI

from src.contracts.costs import CostLedgerAppendRequest, CostLedgerEntry, CostRollupRequest
from src.contracts.openai import OpenAIJSONImagePromptRequest
from src.contracts.report_assets import CropRefineRequest, CropRefineResponse, CropRefineResult, RankRequest, RankResponse
from src.contracts.report_models import RankedCandidate
from src.contracts.run_context import RunContext
from src.services.cost_ledger_service import append_entry as append_cost_entry, rollup_daily
from src.services.openai_service import openai_chat_json_with_images
from src.utils.costing import estimate_cost_usd
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.rank_service")


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _to_bbox(value: Any, fallback: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
        except (TypeError, ValueError):
            return fallback
    return fallback

def rank_candidates(request: RankRequest, ctx: RunContext) -> RankResponse:
    logger.info(log_event(
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
    ))
    client_kwargs: dict = {"api_key": request.api_key}
    if request.timeout_seconds is not None:
        client_kwargs["timeout"] = request.timeout_seconds
    client = OpenAI(**client_kwargs)
    payload_args = {
        "model": request.model,
        "messages": [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": request.temperature,
    }
    if request.seed is not None:
        payload_args["seed"] = request.seed
    try:
        resp = client.chat.completions.create(**payload_args)
        content = resp.choices[0].message.content
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="rank_response_invalid_json",
            message="Ranking response JSON parsing failed",
            cause=exc,
            retryable=False,
            context={"model": request.model},
        ) from exc
    except Exception as exc:
        raise AppError(
            code="rank_request_failed",
            message="Ranking request failed",
            cause=exc,
            retryable=True,
            context={"model": request.model},
        ) from exc

    try:
        items: List[Dict[str, Any]]
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            if "results" in parsed and isinstance(parsed["results"], list):
                items = parsed["results"]
            else:
                found = False
                for candidate_key in ("data", "items", "results"):
                    if candidate_key in parsed and isinstance(parsed[candidate_key], list):
                        items = parsed[candidate_key]
                        found = True
                        break
                if not found:
                    raise ValueError("Ranking response did not return a JSON list of objects")
        else:
            raise ValueError("Ranking response did not return a JSON list of objects")
    except ValueError as exc:
        raise AppError(
            code="rank_response_invalid_format",
            message=str(exc),
            cause=exc,
            retryable=False,
            context={"model": request.model},
        ) from exc

    result: List[RankedCandidate] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            score_value = _to_int(item.get("score"), 0)
            ranked = RankedCandidate(
                id=item.get("id", ""),
                type=item.get("type", ""),
                score=score_value,
                quality_score=_to_int(item.get("quality_score"), score_value),
                insight_score=_to_int(item.get("insight_score"), score_value),
                data_score=_to_int(item.get("data_score"), score_value),
                keep=_to_bool(item.get("keep"), True),
                reject_reason=str(item.get("reject_reason") or ""),
            )
            result.append(ranked)
        except (ValueError, TypeError):
            continue

    request_id = getattr(resp, "id", None)
    usage = getattr(resp, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None) if usage is not None else None
    completion_tokens = getattr(usage, "completion_tokens", None) if usage is not None else None
    total_tokens = getattr(usage, "total_tokens", None) if usage is not None else None
    estimated_cost = estimate_cost_usd(
        request.model,
        int(prompt_tokens or 0),
        int(completion_tokens or 0),
        int(request.tool_calls or 0),
        pricing=request.model_pricing or {},
    )
    try:
        entry = CostLedgerEntry(
            schema_version="1.0",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            run_id=ctx.run_id,
            task_id=ctx.task_id,
            span_id=ctx.span_id,
            step_name="rank_candidates",
            model=request.model,
            input_tokens=int(prompt_tokens or 0),
            output_tokens=int(completion_tokens or 0),
            cached_input_tokens=None,
            tool_calls=int(request.tool_calls or 0),
            estimated_cost_usd=estimated_cost,
            extra={"request_id": str(request_id) if request_id else None},
        )
        append_cost_entry(
            CostLedgerAppendRequest(schema_version="1.0", path=request.cost_ledger_path, entry=entry),
            ctx,
        )
        rollup_daily(
            CostRollupRequest(schema_version="1.0", ledger_path=request.cost_ledger_path, out_path=request.cost_daily_path),
            ctx,
        )
    except Exception as exc:  # pragma: no cover - ledger failures must not break main flow
        logger.info(log_event(
            ctx,
            role="service",
            event="cost_ledger_write_failed",
            module=logger.name,
            fields={"error": str(exc)},
        ))
    logger.info(log_event(
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
    ))
    return RankResponse(
        schema_version="1.0",
        results=result,
        raw_content=content,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        request_id=str(request_id) if request_id else None,
    )


def refine_candidate_crops(request: CropRefineRequest, ctx: RunContext) -> CropRefineResponse:
    logger.info(log_event(
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
    ))
    response = openai_chat_json_with_images(
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
        ),
        ctx,
    )
    parsed = response.parsed_json if isinstance(response.parsed_json, dict) else {}
    raw_items = parsed.get("results") if isinstance(parsed.get("results"), list) else []
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
            results.append(CropRefineResult(
                schema_version="1.0",
                id=cid,
                is_valid_candidate=_to_bool(item.get("is_valid_candidate"), False),
                refined_bbox=refined_bbox,
                include_title=_to_bool(item.get("include_title"), True),
                include_note_if_present=_to_bool(item.get("include_note_if_present"), True),
                confidence=float(item.get("confidence", 0.0) or 0.0),
                reason=str(item.get("reason") or ""),
            ))
        except (TypeError, ValueError):
            continue
    if not results:
        for candidate in request.candidates:
            results.append(CropRefineResult(
                schema_version="1.0",
                id=candidate.id,
                is_valid_candidate=False,
                refined_bbox=candidate.bbox,
                include_title=True,
                include_note_if_present=True,
                confidence=0.0,
                reason="no_valid_response",
            ))
    logger.info(log_event(
        ctx,
        role="service",
        event="crop_refine_complete",
        module=logger.name,
        fields={
            "page": request.page,
            "candidate_count": len(request.candidates or []),
            "accepted_count": sum(1 for result in results if result.is_valid_candidate),
            "response_has_json": bool(response.parsed_json),
        },
    ))
    return CropRefineResponse(
        schema_version="1.0",
        results=results,
        raw_content=response.text or "",
        prompt_tokens=response.input_tokens,
        completion_tokens=response.output_tokens,
        total_tokens=(response.input_tokens or 0) + (response.output_tokens or 0),
        request_id=None,
    )
