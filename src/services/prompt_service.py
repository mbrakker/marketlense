from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import yaml
from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, UndefinedError

from src.contracts.prompts import (
    PromptNamespaceListRequest,
    PromptNamespaceListResponse,
    PromptNamespaceSummary,
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

@dataclass(frozen=True)
class _PromptCacheEntry:
    prompt_set: PromptSet
    system_mtime: float
    user_mtime: float


_PROMPT_CACHE: Dict[str, _PromptCacheEntry] = {}


def _resolve_prompt_namespace(namespace: str) -> str:
    normalized = str(namespace or "").strip()
    if not normalized:
        raise AppError(
            code="prompt_namespace_invalid",
            message="Prompt namespace is required",
            retryable=False,
        )
    root = PROMPTS_ROOT.resolve()
    candidate = (root / normalized).resolve()
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise AppError(
            code="prompt_namespace_invalid",
            message="Prompt namespace must resolve inside the prompts root",
            cause=exc,
            retryable=False,
            context={"namespace": namespace},
        ) from exc
    rel_namespace = str(relative).replace("\\", "/")
    if not rel_namespace or rel_namespace == ".":
        raise AppError(
            code="prompt_namespace_invalid",
            message="Prompt namespace must resolve to a prompt directory",
            retryable=False,
            context={"namespace": namespace},
        )
    return rel_namespace


def load_prompt_set(request: PromptLoadRequest, ctx: RunContext) -> PromptSet:
    namespace = _resolve_prompt_namespace(request.namespace)
    base = PROMPTS_ROOT / namespace
    system_path = base / "system.yaml"
    user_path = base / "user.yaml"
    logger.info(log_event(
        ctx,
        role="service",
        event="prompt_load_start",
        module=logger.name,
        fields={"namespace": request.namespace, "resolved_namespace": namespace},
    ))
    cache_entry = _PROMPT_CACHE.get(namespace)
    prompt_set: PromptSet | None = None
    source = "reloaded"
    if cache_entry and not request.force_reload:
        if not request.reload_if_changed:
            logger.info(log_event(
                ctx,
                role="service",
                event="prompt_load_cache_hit",
                module=logger.name,
                fields={"namespace": namespace, "validated": False},
            ))
            prompt_set = cache_entry.prompt_set
            source = "cache"
        elif _is_prompt_cache_valid(cache_entry, system_path, user_path):
            logger.info(log_event(
                ctx,
                role="service",
                event="prompt_load_cache_hit",
                module=logger.name,
                fields={
                    "namespace": namespace,
                    "validated": True,
                    "system_path": cache_entry.prompt_set.system.path,
                    "user_path": cache_entry.prompt_set.user.path,
                },
            ))
            prompt_set = cache_entry.prompt_set
            source = "cache_validated"
        else:
            logger.info(log_event(
                ctx,
                role="service",
                event="prompt_load_cache_stale",
                module=logger.name,
                fields={"namespace": namespace},
            ))
    if prompt_set is None:
        system_template = _load_prompt(system_path)
        user_template = _load_prompt(user_path)
        prompt_set = PromptSet(
            schema_version="1.0",
            system=system_template,
            user=user_template,
        )
        _PROMPT_CACHE[namespace] = _PromptCacheEntry(
            prompt_set=prompt_set,
            system_mtime=_get_mtime(system_path),
            user_mtime=_get_mtime(user_path),
        )
    else:
        system_template = prompt_set.system
        user_template = prompt_set.user
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
            "cached": source != "reloaded",
            "source": source,
        },
    ))
    return prompt_set


def list_prompt_namespaces(request: PromptNamespaceListRequest, ctx: RunContext) -> PromptNamespaceListResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="prompt_namespace_list_start",
        module=logger.name,
        fields={
            "reload_if_changed": request.reload_if_changed,
            "force_reload": request.force_reload,
        },
    ))
    namespaces: list[PromptNamespaceSummary] = []
    for system_path in sorted(PROMPTS_ROOT.rglob("system.yaml")):
        user_path = system_path.parent / "user.yaml"
        if not user_path.exists():
            continue
        rel_namespace = str(system_path.parent.relative_to(PROMPTS_ROOT)).replace("\\", "/")
        prompt_set = load_prompt_set(
            PromptLoadRequest(
                schema_version="1.0",
                namespace=rel_namespace,
                reload_if_changed=request.reload_if_changed,
                force_reload=request.force_reload,
            ),
            ctx,
        )
        namespaces.append(PromptNamespaceSummary(
            schema_version="1.0",
            namespace=rel_namespace,
            system_path=prompt_set.system.path,
            user_path=prompt_set.user.path,
            system_sha256=prompt_set.system.sha256,
            user_sha256=prompt_set.user.sha256,
        ))
    response = PromptNamespaceListResponse(schema_version="1.0", namespaces=namespaces)
    logger.info(log_event(
        ctx,
        role="service",
        event="prompt_namespace_list_complete",
        module=logger.name,
        fields={"count": len(namespaces)},
    ))
    return response


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


def _get_mtime(path: Path) -> float:
    return path.stat().st_mtime


def _is_prompt_cache_valid(entry: _PromptCacheEntry, system_path: Path, user_path: Path) -> bool:
    try:
        return entry.system_mtime == system_path.stat().st_mtime and entry.user_mtime == user_path.stat().st_mtime
    except FileNotFoundError:
        return False


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
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise AppError(
            code="prompt_yaml_invalid",
            message=f"Prompt YAML invalid: {path}",
            cause=exc,
            retryable=False,
        ) from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise AppError(
            code="prompt_yaml_invalid",
            message=f"Prompt YAML root must be a mapping: {path}",
            retryable=False,
            context={"path": str(path)},
        )
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
