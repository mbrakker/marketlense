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
    system_mtime: int
    user_mtime: int


@dataclass(frozen=True)
class _PromptNamespaceCacheEntry:
    root: Path
    namespaces: tuple[str, ...]
    watched_dirs: tuple[Path, ...]
    directory_mtimes: tuple[tuple[str, int], ...]


_PROMPT_CACHE: Dict[str, _PromptCacheEntry] = {}
_PROMPT_NAMESPACE_CACHE: _PromptNamespaceCacheEntry | None = None


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
    logger.info(
        log_event(
            ctx,
            role="service",
            event="prompt_load_start",
            module=logger.name,
            fields={"namespace": request.namespace, "resolved_namespace": namespace},
        )
    )
    cache_entry = _PROMPT_CACHE.get(namespace)
    prompt_set: PromptSet | None = None
    source = "reloaded"
    if cache_entry and not request.force_reload:
        if not request.reload_if_changed:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="prompt_load_cache_hit",
                    module=logger.name,
                    fields={"namespace": namespace, "validated": False},
                )
            )
            prompt_set = cache_entry.prompt_set
            source = "cache"
        elif _is_prompt_cache_valid(cache_entry, system_path, user_path):
            logger.info(
                log_event(
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
                )
            )
            prompt_set = cache_entry.prompt_set
            source = "cache_validated"
        else:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="prompt_load_cache_stale",
                    module=logger.name,
                    fields={"namespace": namespace},
                )
            )
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
    logger.info(
        log_event(
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
        )
    )
    return prompt_set


def list_prompt_namespaces(
    request: PromptNamespaceListRequest, ctx: RunContext
) -> PromptNamespaceListResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="prompt_namespace_list_start",
            module=logger.name,
            fields={
                "reload_if_changed": request.reload_if_changed,
                "force_reload": request.force_reload,
            },
        )
    )
    namespaces: list[PromptNamespaceSummary] = []
    namespace_names = _list_prompt_namespace_names(
        reload_if_changed=request.reload_if_changed,
        force_reload=request.force_reload,
    )
    for rel_namespace in namespace_names:
        prompt_set = load_prompt_set(
            PromptLoadRequest(
                schema_version="1.0",
                namespace=rel_namespace,
                reload_if_changed=request.reload_if_changed,
                force_reload=request.force_reload,
            ),
            ctx,
        )
        namespaces.append(
            PromptNamespaceSummary(
                schema_version="1.0",
                namespace=rel_namespace,
                system_path=prompt_set.system.path,
                user_path=prompt_set.user.path,
                system_sha256=prompt_set.system.sha256,
                user_sha256=prompt_set.user.sha256,
            )
        )
    response = PromptNamespaceListResponse(schema_version="1.0", namespaces=namespaces)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="prompt_namespace_list_complete",
            module=logger.name,
            fields={"count": len(namespaces)},
        )
    )
    return response


def render_prompt(
    request: PromptRenderRequest, ctx: RunContext
) -> PromptRenderResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="prompt_render_start",
            module=logger.name,
            fields={"template_path": request.template.path},
        )
    )
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
    logger.info(
        log_event(
            ctx,
            role="service",
            event="prompt_render_complete",
            module=logger.name,
            fields={"template_path": request.template.path, "length": len(text)},
        )
    )
    return PromptRenderResponse(schema_version="1.0", text=text)


def _get_mtime(path: Path) -> int:
    stat = path.stat()
    return int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))


def _is_prompt_cache_valid(
    entry: _PromptCacheEntry, system_path: Path, user_path: Path
) -> bool:
    try:
        return (
            entry.system_mtime == system_path.stat().st_mtime
            and entry.user_mtime == user_path.stat().st_mtime
        )
    except FileNotFoundError:
        return False


def _list_prompt_namespace_names(
    *, reload_if_changed: bool, force_reload: bool
) -> tuple[str, ...]:
    global _PROMPT_NAMESPACE_CACHE
    root = PROMPTS_ROOT.resolve()
    cache_entry = _PROMPT_NAMESPACE_CACHE
    if (
        cache_entry is not None
        and cache_entry.root == root
        and not force_reload
        and (not reload_if_changed or _is_prompt_namespace_cache_valid(cache_entry))
    ):
        return cache_entry.namespaces

    namespaces, watched_dirs = _discover_prompt_namespaces(root)
    _PROMPT_NAMESPACE_CACHE = _PromptNamespaceCacheEntry(
        root=root,
        namespaces=namespaces,
        watched_dirs=watched_dirs,
        directory_mtimes=_directory_mtimes(watched_dirs),
    )
    return namespaces


def _discover_prompt_namespaces(root: Path) -> tuple[tuple[str, ...], tuple[Path, ...]]:
    namespace_dirs: list[Path] = []
    watched_dirs = {root}
    for system_path in sorted(root.rglob("system.yaml")):
        watched_dirs.add(system_path.parent)
        user_path = system_path.parent / "user.yaml"
        if not user_path.exists():
            continue
        namespace_dirs.append(system_path.parent)
    for namespace_dir in namespace_dirs:
        current = namespace_dir
        while True:
            watched_dirs.add(current)
            if current == root:
                break
            current = current.parent
    namespaces = tuple(
        str(namespace_dir.relative_to(root)).replace("\\", "/")
        for namespace_dir in sorted(namespace_dirs)
    )
    return namespaces, tuple(sorted(watched_dirs))


def _directory_mtimes(paths: tuple[Path, ...]) -> tuple[tuple[str, int], ...]:
    mtimes: list[tuple[str, int]] = []
    for path in paths:
        try:
            mtimes.append((str(path), _get_mtime(path)))
        except FileNotFoundError:
            mtimes.append((str(path), -1))
    return tuple(mtimes)


def _is_prompt_namespace_cache_valid(entry: _PromptNamespaceCacheEntry) -> bool:
    return _directory_mtimes(entry.watched_dirs) == entry.directory_mtimes


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
