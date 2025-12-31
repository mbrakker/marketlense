from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict

import yaml
from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, UndefinedError

from src.contracts.prompts import (
    PromptLoadRequest,
    PromptRenderRequest,
    PromptRenderResponse,
    PromptSet,
    PromptTemplate,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.prompt_service")

PROMPTS_ROOT = Path(__file__).resolve().parents[1] / "prompts"
JINJA_ENV = Environment(
    autoescape=False,
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)


def load_prompt_set(request: PromptLoadRequest, ctx: RunContext) -> PromptSet:
    logger.info(log_event(
        ctx,
        role="service",
        event="prompt_load_start",
        module=logger.name,
        fields={"namespace": request.namespace},
    ))
    base = PROMPTS_ROOT / request.namespace
    system_path = base / "system.yaml"
    user_path = base / "user.yaml"
    system_template = _load_prompt(system_path)
    user_template = _load_prompt(user_path)
    logger.info(log_event(
        ctx,
        role="service",
        event="prompt_load_complete",
        module=logger.name,
        fields={
            "system_path": system_template.path,
            "system_sha256": system_template.sha256,
            "user_path": user_template.path,
            "user_sha256": user_template.sha256,
        },
    ))
    return PromptSet(
        schema_version="1.0",
        system=system_template,
        user=user_template,
    )


def render_prompt(request: PromptRenderRequest, ctx: RunContext) -> PromptRenderResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="prompt_render_start",
        module=logger.name,
        fields={"template_path": request.template.path},
    ))
    try:
        template = JINJA_ENV.from_string(request.template.text)
        text = template.render(**request.variables)
    except UndefinedError as exc:
        raise AppError(
            code="prompt_render_missing_variable",
            message=f"Missing prompt variable: {exc}",
            cause=exc,
            retryable=False,
        ) from exc
    except TemplateSyntaxError as exc:
        raise AppError(
            code="prompt_render_invalid_template",
            message=f"Prompt template invalid: {exc}",
            cause=exc,
            retryable=False,
        ) from exc
    except Exception as exc:
        raise AppError(
            code="prompt_render_failed",
            message="Prompt rendering failed",
            cause=exc,
            retryable=False,
        ) from exc
    logger.info(log_event(
        ctx,
        role="service",
        event="prompt_render_complete",
        module=logger.name,
        fields={"template_path": request.template.path, "length": len(text)},
    ))
    return PromptRenderResponse(schema_version="1.0", text=text)


def _load_prompt(path: Path) -> PromptTemplate:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AppError(
            code="prompt_not_found",
            message=f"Prompt file not found: {path}",
            cause=exc,
            retryable=False,
        ) from exc
    try:
        data: Dict[str, Any] = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise AppError(
            code="prompt_yaml_invalid",
            message=f"Prompt YAML invalid: {path}",
            cause=exc,
            retryable=False,
        ) from exc
    text = data.get("text", "")
    if not text:
        raise AppError(
            code="prompt_empty",
            message=f"Prompt file is empty: {path}",
            retryable=False,
        )
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return PromptTemplate(
        schema_version="1.0",
        path=str(path),
        text=text,
        sha256=digest,
    )
