from __future__ import annotations

import json
import logging
from pathlib import Path

from openai import OpenAI
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.openai import OpenAIAnalyzeRequest, OpenAIAnalyzeResponse
from src.contracts.run_context import RunContext
from src.services.prompt_service import load_prompt, render_prompt
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.openai_service")

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts" / "report_generation"

REQUIRED_KEYS = ("tldr", "insights", "quote", "figure", "commentary", "source")


def _validate_payload(data: dict) -> None:
    for k in REQUIRED_KEYS:
        if k not in data:
            raise ValueError(f"Missing key in JSON: {k}")
    if not isinstance(data.get("insights"), list) or len(data["insights"]) != 5:
        raise ValueError("`insights` must be a list of exactly 5 items")


def _extract_text_first_pages(pdf_path: str, max_pages: int = 5, max_chars: int = 80_000) -> str:
    try:
        reader = PdfReader(pdf_path, strict=False)
    except (PdfReadError, PdfStreamError) as exc:
        logger.warning("Failed to read PDF %s (%s); continuing with empty text", pdf_path, exc)
        return ""
    pages = min(len(reader.pages), max_pages)
    chunks = []
    for i in range(pages):
        t = reader.pages[i].extract_text() or ""
        chunks.append(t)
    text = "\n\n".join(chunks)
    return text[:max_chars]


def analyze_pdf(request: OpenAIAnalyzeRequest, ctx: RunContext) -> OpenAIAnalyzeResponse:
    log_event(
        logger,
        ctx,
        role="service",
        event="openai_analyze_start",
        fields={
            "pdf_path": request.pdf_path,
            "model": request.model,
            "temperature": request.temperature,
        },
    )

    extracted = _extract_text_first_pages(request.pdf_path)
    system_template = load_prompt(PROMPT_DIR / "system.yaml")
    user_template = load_prompt(PROMPT_DIR / "user.yaml")
    system_text = render_prompt(system_template)
    user_text = render_prompt(user_template, extracted=extracted)
    log_event(
        logger,
        ctx,
        role="service",
        event="openai_prompts_loaded",
        fields={
            "system_sha256": system_template.sha256,
            "user_sha256": user_template.sha256,
        },
    )

    client = OpenAI(api_key=request.api_key)
    try:
        resp = client.chat.completions.create(
            model=request.model,
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            response_format={"type": "json_object"},
            temperature=request.temperature,
        )
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

    log_event(
        logger,
        ctx,
        role="service",
        event="openai_analyze_complete",
        fields={
            "prompt_system_sha256": system_template.sha256,
            "prompt_user_sha256": user_template.sha256,
        },
    )

    return OpenAIAnalyzeResponse(
        schema_version="1.0",
        payload=result,
        prompt_system_sha256=system_template.sha256,
        prompt_user_sha256=user_template.sha256,
        model=request.model,
        temperature=request.temperature,
    )
