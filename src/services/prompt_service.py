from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import yaml
from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, UndefinedError

from src.contracts.prompts import (
    PromptDryRunBenchmark,
    PromptDryRunFixture,
    PromptDryRunRequest,
    PromptDryRunResponse,
    PromptDryRunResult,
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
PROMPT_DRY_RUN_FIXTURE_PATH = PROMPTS_ROOT / "_dry_run_fixtures.yaml"
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
    system_size: int
    user_size: int


@dataclass(frozen=True)
class _PromptNamespaceCacheEntry:
    root: Path
    namespaces: tuple[str, ...]
    watched_dirs: tuple[Path, ...]
    directory_mtimes: tuple[tuple[str, int, tuple[str, ...]], ...]


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
            system_size=_get_size(system_path),
            user_size=_get_size(user_path),
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


def validate_prompt_dry_run(
    request: PromptDryRunRequest, ctx: RunContext
) -> PromptDryRunResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="prompt_dry_run_start",
            module=logger.name,
            fields={
                "requested_namespaces": list(request.namespaces),
                "reload_if_changed": request.reload_if_changed,
                "force_reload": request.force_reload,
                "fixture_path": str(PROMPT_DRY_RUN_FIXTURE_PATH),
            },
        )
    )
    fixtures = _load_prompt_dry_run_fixtures()
    fixtures_by_namespace = {fixture.namespace: fixture for fixture in fixtures}
    namespace_response = list_prompt_namespaces(
        PromptNamespaceListRequest(
            schema_version="1.0",
            reload_if_changed=request.reload_if_changed,
            force_reload=request.force_reload,
        ),
        ctx,
    )
    discovered_namespaces = [item.namespace for item in namespace_response.namespaces]
    if request.namespaces:
        target_namespaces = []
        seen: set[str] = set()
        for raw_namespace in request.namespaces:
            namespace = _resolve_prompt_namespace(raw_namespace)
            if namespace in seen:
                continue
            if namespace not in discovered_namespaces:
                raise AppError(
                    code="prompt_dry_run_namespace_unknown",
                    message=f"Prompt dry-run namespace is not an active prompt namespace: {namespace}",
                    retryable=False,
                    context={"namespace": namespace},
                )
            seen.add(namespace)
            target_namespaces.append(namespace)
    else:
        target_namespaces = list(discovered_namespaces)

    missing_fixtures = [
        namespace
        for namespace in target_namespaces
        if namespace not in fixtures_by_namespace
    ]
    if missing_fixtures:
        raise AppError(
            code="prompt_dry_run_fixture_missing",
            message="Prompt dry-run fixtures are missing for one or more active namespaces",
            retryable=False,
            context={"namespaces": missing_fixtures},
        )

    stale_fixture_namespaces = sorted(
        namespace
        for namespace in fixtures_by_namespace
        if namespace not in discovered_namespaces
    )
    if stale_fixture_namespaces:
        raise AppError(
            code="prompt_dry_run_fixture_stale",
            message="Prompt dry-run fixtures reference namespaces that do not exist",
            retryable=False,
            context={"namespaces": stale_fixture_namespaces},
        )

    results: list[PromptDryRunResult] = []
    for namespace in target_namespaces:
        fixture = fixtures_by_namespace[namespace]
        started_at = time.perf_counter()
        prompt_set = load_prompt_set(
            PromptLoadRequest(
                schema_version="1.0",
                namespace=namespace,
                reload_if_changed=request.reload_if_changed,
                force_reload=request.force_reload,
            ),
            ctx,
        )
        rendered_system = render_prompt(
            PromptRenderRequest(
                schema_version="1.0",
                template=prompt_set.system,
                variables=dict(fixture.system_variables),
            ),
            ctx,
        )
        rendered_user = render_prompt(
            PromptRenderRequest(
                schema_version="1.0",
                template=prompt_set.user,
                variables=dict(fixture.user_variables),
            ),
            ctx,
        )
        render_runtime_ms = round((time.perf_counter() - started_at) * 1000.0, 6)
        result = PromptDryRunResult(
            schema_version="1.0",
            namespace=namespace,
            family=fixture.family,
            benchmark=fixture.benchmark,
            fixture_path=str(PROMPT_DRY_RUN_FIXTURE_PATH),
            system_path=prompt_set.system.path,
            user_path=prompt_set.user.path,
            system_sha256=prompt_set.system.sha256,
            user_sha256=prompt_set.user.sha256,
            rendered_system_prompt=rendered_system.text,
            rendered_user_prompt=rendered_user.text,
            render_runtime_ms=render_runtime_ms,
            model=fixture.model,
            temperature=float(fixture.temperature),
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="prompt_dry_run_namespace_validated",
                module=logger.name,
                fields={
                    "namespace": result.namespace,
                    "family": result.family,
                    "fixture_path": result.fixture_path,
                    "system_path": result.system_path,
                    "user_path": result.user_path,
                    "system_sha256": result.system_sha256,
                    "user_sha256": result.user_sha256,
                    "rendered_system_prompt": result.rendered_system_prompt,
                    "rendered_user_prompt": result.rendered_user_prompt,
                    "render_runtime_ms": result.render_runtime_ms,
                    "model": result.model,
                    "temperature": result.temperature,
                    "benchmark": {
                        "expected_output_tokens": result.benchmark.expected_output_tokens,
                        "expected_tool_calls": result.benchmark.expected_tool_calls,
                        "expected_browser_attempts": result.benchmark.expected_browser_attempts,
                        "expected_ocr_calls": result.benchmark.expected_ocr_calls,
                    },
                    "system_variable_keys": sorted(fixture.system_variables.keys()),
                    "user_variable_keys": sorted(fixture.user_variables.keys()),
                },
            )
        )
        results.append(result)

    response = PromptDryRunResponse(schema_version="1.0", results=results)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="prompt_dry_run_complete",
            module=logger.name,
            fields={
                "validated_namespace_count": len(results),
                "families": sorted({item.family for item in results}),
            },
        )
    )
    return response


def _get_mtime(path: Path) -> int:
    stat = path.stat()
    return int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))


def _get_size(path: Path) -> int:
    return int(path.stat().st_size)


def _is_prompt_cache_valid(
    entry: _PromptCacheEntry, system_path: Path, user_path: Path
) -> bool:
    try:
        return (
            entry.system_mtime == _get_mtime(system_path)
            and entry.user_mtime == _get_mtime(user_path)
            and entry.system_size == _get_size(system_path)
            and entry.user_size == _get_size(user_path)
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


def _directory_mtimes(
    paths: tuple[Path, ...],
) -> tuple[tuple[str, int, tuple[str, ...]], ...]:
    mtimes: list[tuple[str, int, tuple[str, ...]]] = []
    for path in paths:
        try:
            child_names = tuple(
                sorted(
                    f"{'d' if child.is_dir() else 'f'}:{child.name}"
                    for child in path.iterdir()
                )
            )
            mtimes.append((str(path), _get_mtime(path), child_names))
        except FileNotFoundError:
            mtimes.append((str(path), -1, ()))
    return tuple(mtimes)


def _is_prompt_namespace_cache_valid(entry: _PromptNamespaceCacheEntry) -> bool:
    return _directory_mtimes(entry.watched_dirs) == entry.directory_mtimes


def _load_prompt_dry_run_fixtures() -> list[PromptDryRunFixture]:
    try:
        raw = PROMPT_DRY_RUN_FIXTURE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AppError(
            code="prompt_dry_run_fixture_not_found",
            message=f"Prompt dry-run fixture registry not found: {PROMPT_DRY_RUN_FIXTURE_PATH}",
            cause=exc,
            retryable=False,
        ) from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise AppError(
            code="prompt_dry_run_fixture_yaml_invalid",
            message=f"Prompt dry-run fixture YAML invalid: {PROMPT_DRY_RUN_FIXTURE_PATH}",
            cause=exc,
            retryable=False,
        ) from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise AppError(
            code="prompt_dry_run_fixture_yaml_invalid",
            message="Prompt dry-run fixture registry root must be a mapping",
            retryable=False,
            context={"path": str(PROMPT_DRY_RUN_FIXTURE_PATH)},
        )
    raw_fixtures = data.get("fixtures", [])
    if not isinstance(raw_fixtures, list) or not raw_fixtures:
        raise AppError(
            code="prompt_dry_run_fixture_registry_invalid",
            message="Prompt dry-run fixture registry must declare a non-empty fixtures list",
            retryable=False,
            context={"path": str(PROMPT_DRY_RUN_FIXTURE_PATH)},
        )
    fixtures: list[PromptDryRunFixture] = []
    seen_namespaces: set[str] = set()
    for index, raw_fixture in enumerate(raw_fixtures):
        fixture = _build_prompt_dry_run_fixture(raw_fixture, index=index)
        if fixture.namespace in seen_namespaces:
            raise AppError(
                code="prompt_dry_run_fixture_duplicate_namespace",
                message=f"Duplicate prompt dry-run fixture namespace: {fixture.namespace}",
                retryable=False,
                context={"namespace": fixture.namespace},
            )
        seen_namespaces.add(fixture.namespace)
        fixtures.append(fixture)
    return fixtures


def _build_prompt_dry_run_fixture(
    payload: object, *, index: int
) -> PromptDryRunFixture:
    if not isinstance(payload, dict):
        raise AppError(
            code="prompt_dry_run_fixture_registry_invalid",
            message="Prompt dry-run fixture entries must be mappings",
            retryable=False,
            context={"index": index},
        )
    namespace = _resolve_prompt_namespace(str(payload.get("namespace") or "").strip())
    family = str(payload.get("family") or "").strip()
    if not family:
        raise AppError(
            code="prompt_dry_run_fixture_registry_invalid",
            message="Prompt dry-run fixture family is required",
            retryable=False,
            context={"namespace": namespace, "index": index},
        )
    system_variables = _coerce_prompt_variable_mapping(
        payload.get("system_variables", {}),
        namespace=namespace,
        field_name="system_variables",
    )
    user_variables = _coerce_prompt_variable_mapping(
        payload.get("user_variables", {}),
        namespace=namespace,
        field_name="user_variables",
    )
    return PromptDryRunFixture(
        schema_version=str(payload.get("schema_version", "1.0")),
        namespace=namespace,
        family=family,
        benchmark=_coerce_prompt_benchmark(
            payload.get("benchmark", {}),
            namespace=namespace,
        ),
        system_variables=system_variables,
        user_variables=user_variables,
        model=str(payload.get("model") or "").strip(),
        temperature=float(payload.get("temperature", 0.0)),
    )


def _coerce_prompt_variable_mapping(
    payload: object, *, namespace: str, field_name: str
) -> dict[str, object]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise AppError(
            code="prompt_dry_run_fixture_registry_invalid",
            message=f"Prompt dry-run fixture {field_name} must be a mapping",
            retryable=False,
            context={"namespace": namespace, "field_name": field_name},
        )
    return {str(key): value for key, value in payload.items()}


def _coerce_prompt_benchmark(
    payload: object, *, namespace: str
) -> PromptDryRunBenchmark:
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise AppError(
            code="prompt_dry_run_fixture_registry_invalid",
            message="Prompt dry-run fixture benchmark must be a mapping",
            retryable=False,
            context={"namespace": namespace, "field_name": "benchmark"},
        )
    return PromptDryRunBenchmark(
        schema_version=str(payload.get("schema_version", "1.0")),
        expected_output_tokens=_coerce_prompt_benchmark_int(
            payload.get("expected_output_tokens", 0),
            namespace=namespace,
            field_name="expected_output_tokens",
        ),
        expected_tool_calls=_coerce_prompt_benchmark_int(
            payload.get("expected_tool_calls", 0),
            namespace=namespace,
            field_name="expected_tool_calls",
        ),
        expected_browser_attempts=_coerce_prompt_benchmark_int(
            payload.get("expected_browser_attempts", 0),
            namespace=namespace,
            field_name="expected_browser_attempts",
        ),
        expected_ocr_calls=_coerce_prompt_benchmark_int(
            payload.get("expected_ocr_calls", 0),
            namespace=namespace,
            field_name="expected_ocr_calls",
        ),
    )


def _coerce_prompt_benchmark_int(
    value: object, *, namespace: str, field_name: str
) -> int:
    try:
        parsed = int(str(value or 0))
    except (TypeError, ValueError) as exc:
        raise AppError(
            code="prompt_dry_run_fixture_registry_invalid",
            message=f"Prompt dry-run fixture benchmark {field_name} must be an integer",
            retryable=False,
            cause=exc,
            context={"namespace": namespace, "field_name": field_name},
        ) from exc
    if parsed < 0:
        raise AppError(
            code="prompt_dry_run_fixture_registry_invalid",
            message=f"Prompt dry-run fixture benchmark {field_name} must be >= 0",
            retryable=False,
            context={
                "namespace": namespace,
                "field_name": field_name,
                "value": parsed,
            },
        )
    return parsed


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
