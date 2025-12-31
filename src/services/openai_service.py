from __future__ import annotations

import json
import logging

from openai import OpenAI

from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.openai import OpenAIAnalyzeRequest, OpenAIAnalyzeResponse
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.openai_service")

REQUIRED_KEYS = ("tldr", "insights", "quote", "figure", "commentary", "source")


def _validate_payload(data: dict) -> None:
    for k in REQUIRED_KEYS:
        if k not in data:
            raise ValueError(f"Missing key in JSON: {k}")
    if not isinstance(data.get("insights"), list) or len(data["insights"]) != 5:
        raise ValueError("`insights` must be a list of exactly 5 items")


def analyze_report(request: OpenAIAnalyzeRequest, ctx: RunContext) -> OpenAIAnalyzeResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="openai_analyze_start",
        module=logger.name,
        fields={
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
    try:
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
        resp = client.chat.completions.create(**payload_args)
        payload = resp.choices[0].message.content
        data = json.loads(payload)
        _validate_payload(data)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="openai_response_invalid_json",
            message="OpenAI response JSON parsing failed",
            cause=exc,
            retryable=False,
            context={"model": request.model},
        ) from exc
    except ValueError as exc:
        raise AppError(
            code="openai_response_validation_failed",
            message=str(exc),
            cause=exc,
            retryable=False,
            context={"model": request.model},
        ) from exc
    except Exception as exc:
        raise AppError(
            code="openai_request_failed",
            message="OpenAI request failed",
            cause=exc,
            retryable=True,
            context={"model": request.model},
        ) from exc

    request_id = getattr(resp, "id", None)
    logger.info(log_event(
        ctx,
        role="service",
        event="openai_analyze_complete",
        module=logger.name,
        fields={
            "request_id": request_id or "",
            "prompt_system_sha256": request.prompt_system_sha256,
            "prompt_user_sha256": request.prompt_user_sha256,
        },
    ))

    quote = Quote(
        text=data.get("quote", {}).get("text", ""),
        author=data.get("quote", {}).get("author", "Unknown"),
    )
    figure = Figure(
        title=data.get("figure", {}).get("title", ""),
        evidence=data.get("figure", {}).get("evidence", ""),
    )
    insights = data.get("insights", [])
    if len(insights) < 5:
        insights = insights + [""] * (5 - len(insights))
    insights = insights[:5]

    result = ReportPayload(
        tldr=data.get("tldr", ""),
        insights=insights,
        quote=quote,
        figure=figure,
        commentary=data.get("commentary", ""),
        source=data.get("source", ""),
        _openai_file_id="",
    )

    return OpenAIAnalyzeResponse(
        schema_version="1.0",
        payload=result,
        prompt_system_sha256=request.prompt_system_sha256,
        prompt_user_sha256=request.prompt_user_sha256,
        model=request.model,
        temperature=request.temperature,
        raw_content=payload,
        request_id=str(request_id) if request_id else None,
    )
