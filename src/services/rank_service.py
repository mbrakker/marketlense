from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from openai import OpenAI

from src.contracts.report_assets import RankRequest, RankResponse
from src.contracts.report_models import RankedCandidate
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.rank_service")

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
            ranked = RankedCandidate(
                id=item.get("id", ""),
                type=item.get("type", ""),
                score=int(item.get("score", 0)),
            )
            result.append(ranked)
        except (ValueError, TypeError):
            continue

    request_id = getattr(resp, "id", None)
    logger.info(log_event(
        ctx,
        role="service",
        event="rank_candidates_complete",
        module=logger.name,
        fields={"count": len(result), "request_id": request_id or ""},
    ))
    return RankResponse(
        schema_version="1.0",
        results=result,
        raw_content=content,
        request_id=str(request_id) if request_id else None,
    )
