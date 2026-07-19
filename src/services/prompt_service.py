from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Dict

import yaml
from jinja2 import (
    Environment,
    StrictUndefined,
    Template,
    TemplateSyntaxError,
    UndefinedError,
)

from src.contracts.prompts import (
    PROMPT_COMPOSITION_VERSION,
    PROMPT_IDENTITY_SCHEMA_VERSION,
    LLMExecutionIdentity,
    PromptDependency,
    PromptDependencyManifest,
    PromptDryRunBenchmark,
    PromptDryRunFixture,
    PromptDryRunRequest,
    PromptDryRunResponse,
    PromptDryRunResult,
    PromptLoadRequest,
    PromptNamespaceListRequest,
    PromptNamespaceListResponse,
    PromptNamespaceSummary,
    PromptRenderRequest,
    PromptRenderResponse,
    PromptSet,
    PromptTemplate,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.model_resolver import (
    execution_policies_from_config,
    resolve_execution_policy,
)

logger = logging.getLogger("market_lense.prompt_service")

PROMPTS_ROOT = Path(__file__).resolve().parents[1] / "prompts"
SCHEMAS_ROOT = Path(__file__).resolve().parents[1] / "schemas"
PROMPT_DRY_RUN_FIXTURE_PATH = PROMPTS_ROOT / "_dry_run_fixtures.yaml"
JINJA_ENV = Environment(
    autoescape=False,
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)


@dataclass(frozen=True)
class _PromptCacheEntry:
    prompt_set: PromptSet


@dataclass(frozen=True)
class _PromptNamespaceCacheEntry:
    root: Path
    namespaces: tuple[str, ...]
    watched_dirs: tuple[Path, ...]
    directory_mtimes: tuple[tuple[str, int, tuple[str, ...]], ...]


_PROMPT_CACHE: Dict[str, _PromptCacheEntry] = {}
_PROMPT_NAMESPACE_CACHE: _PromptNamespaceCacheEntry | None = None
_RENDER_TEMPLATE_CACHE: Dict[tuple[str, str, str], Template] = {}


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
        valid, invalidation_reason = _is_prompt_cache_valid(cache_entry)
        if valid:
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
                        "prompt_content_hash": cache_entry.prompt_set.prompt_content_hash,
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
                    event="prompt_cache_invalidated",
                    module=logger.name,
                    fields={
                        "namespace": namespace,
                        "reason": invalidation_reason,
                    },
                )
            )
    if prompt_set is None:
        system_template = _load_prompt(system_path)
        user_template = _load_prompt(user_path)
        dependency_manifest = _build_dependency_manifest(
            namespace=namespace,
            system_path=system_path,
            user_path=user_path,
            system_template=system_template,
            user_template=user_template,
        )
        prompt_set = PromptSet(
            schema_version="1.0",
            system=system_template,
            user=user_template,
            dependency_manifest=dependency_manifest,
            prompt_content_hash=dependency_manifest.prompt_content_hash,
        )
        _PROMPT_CACHE[namespace] = _PromptCacheEntry(prompt_set=prompt_set)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="prompt_dependency_manifest_built",
                module=logger.name,
                fields={
                    "namespace": namespace,
                    "prompt_content_hash": dependency_manifest.prompt_content_hash,
                    "partial_count": len(dependency_manifest.included_partials),
                    "schema_snippet_count": len(dependency_manifest.schema_snippets),
                    "composition_version": dependency_manifest.composition_version,
                },
            )
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
                "prompt_content_hash": prompt_set.prompt_content_hash,
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
                prompt_content_hash=prompt_set.prompt_content_hash,
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
        variables = dict(request.variables)
        for key, snippet in request.template.schema_snippets.items():
            if key in variables:
                raise AppError(
                    code="prompt_render_schema_snippet_variable_conflict",
                    message="Prompt render variables must not override generated schema snippets",
                    retryable=False,
                    context={"template_path": request.template.path, "variable": key},
                )
            variables[key] = snippet
        cache_key = (
            str(request.template.path),
            str(request.template.sha256),
            str(request.template.text),
        )
        template = _RENDER_TEMPLATE_CACHE.get(cache_key)
        if template is None:
            template = JINJA_ENV.from_string(request.template.text)
            _RENDER_TEMPLATE_CACHE[cache_key] = template
        text = template.render(**variables)
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
    # Fixture content exercises rendering only. Execution settings always come
    # from the same runtime resolver as a provider call unless a fixture opts
    # into a clearly marked test-only override.
    from src.contracts.config import ConfigLoadRequest
    from src.services.config_service import load_settings

    runtime_settings = load_settings(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )
    execution_policies = execution_policies_from_config(
        runtime_settings.llm_execution_policies,
        model_overrides=runtime_settings.openai_models,
        legacy_routing=runtime_settings.llm_routing,
        default_model=runtime_settings.openai_model,
        default_temperature=runtime_settings.temperature,
        default_seed=runtime_settings.openai_seed,
        default_timeout_seconds=runtime_settings.openai_timeout_seconds,
    )
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
        policy_decision = resolve_execution_policy(
            namespace,
            execution_policies,
            default_model=runtime_settings.openai_model,
            default_temperature=runtime_settings.temperature,
            default_seed=runtime_settings.openai_seed,
            default_timeout_seconds=runtime_settings.openai_timeout_seconds,
        )
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
            model=(
                fixture.model
                if fixture.test_only_execution_override
                else policy_decision.policy.model
            ),
            temperature=(
                float(fixture.temperature)
                if fixture.test_only_execution_override
                else policy_decision.policy.temperature
            ),
            execution_policy_hash=policy_decision.policy_hash,
            execution_policy_source=policy_decision.policy_source,
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
                    "rendered_system_sha256": hashlib.sha256(
                        result.rendered_system_prompt.encode("utf-8")
                    ).hexdigest(),
                    "rendered_user_sha256": hashlib.sha256(
                        result.rendered_user_prompt.encode("utf-8")
                    ).hexdigest(),
                    "rendered_system_length": len(result.rendered_system_prompt),
                    "rendered_user_length": len(result.rendered_user_prompt),
                    "render_runtime_ms": result.render_runtime_ms,
                    "execution_policy_hash": result.execution_policy_hash,
                    "execution_policy_source": result.execution_policy_source,
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


def _is_prompt_cache_valid(entry: _PromptCacheEntry) -> tuple[bool, str]:
    manifest = entry.prompt_set.dependency_manifest
    if manifest is None or not manifest.prompt_content_hash:
        return False, "legacy_manifest_missing"
    for dependency in _manifest_dependencies(manifest):
        try:
            actual_hash = _sha256_file(
                _resolve_manifest_dependency_path(dependency.path)
            )
        except (AppError, FileNotFoundError):
            return False, f"{dependency.kind}_missing"
        if actual_hash != dependency.sha256:
            return False, f"{dependency.kind}_content_changed"
    return True, ""


def _manifest_dependencies(
    manifest: PromptDependencyManifest,
) -> tuple[PromptDependency, ...]:
    return (
        manifest.system_root,
        manifest.user_root,
        *manifest.included_partials,
        *manifest.schema_snippets,
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_dependency_path(path: Path, *, root: Path, prefix: str) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise AppError(
            code="prompt_dependency_path_invalid",
            message="Prompt dependency must resolve under its canonical root",
            cause=exc,
            retryable=False,
        ) from exc
    return f"{prefix}/{relative.as_posix()}"


def _resolve_manifest_dependency_path(canonical_path: str) -> Path:
    prefix, separator, relative = canonical_path.partition("/")
    if not separator or not relative:
        raise AppError(
            code="prompt_dependency_path_invalid",
            message="Prompt dependency path is invalid",
            retryable=False,
            context={"path": canonical_path},
        )
    if prefix == "prompts":
        root = PROMPTS_ROOT.resolve()
    elif prefix == "schemas":
        root = SCHEMAS_ROOT.resolve()
    else:
        raise AppError(
            code="prompt_dependency_path_invalid",
            message="Prompt dependency path root is invalid",
            retryable=False,
            context={"path": canonical_path},
        )
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AppError(
            code="prompt_dependency_path_invalid",
            message="Prompt dependency path must remain under its canonical root",
            cause=exc,
            retryable=False,
            context={"path": canonical_path},
        ) from exc
    return candidate


def _build_dependency_manifest(
    *,
    namespace: str,
    system_path: Path,
    user_path: Path,
    system_template: PromptTemplate,
    user_template: PromptTemplate,
) -> PromptDependencyManifest:
    def root_dependency(path: Path, kind: str) -> PromptDependency:
        return PromptDependency(
            schema_version=PROMPT_IDENTITY_SCHEMA_VERSION,
            path=_canonical_dependency_path(path, root=PROMPTS_ROOT, prefix="prompts"),
            sha256=_sha256_file(path),
            kind=kind,
        )

    partials: list[PromptDependency] = []
    schema_snippets: list[PromptDependency] = []
    for root_name, template in (("system", system_template), ("user", user_template)):
        for index, (path, digest) in enumerate(
            zip(template.include_paths, template.include_sha256s, strict=True)
        ):
            partials.append(
                PromptDependency(
                    schema_version=PROMPT_IDENTITY_SCHEMA_VERSION,
                    path=_canonical_dependency_path(
                        Path(path), root=PROMPTS_ROOT, prefix="prompts"
                    ),
                    sha256=digest,
                    kind="partial",
                    source=f"{root_name}:{index}",
                )
            )
        for key in sorted(template.schema_snippet_paths):
            schema_snippets.append(
                PromptDependency(
                    schema_version=PROMPT_IDENTITY_SCHEMA_VERSION,
                    path=template.schema_snippet_paths[key],
                    sha256=template.schema_snippet_sha256s[key],
                    kind="schema_snippet",
                    source=f"{root_name}:{key}:{template.schema_snippet_sources.get(key, '')}",
                )
            )
    without_hash = PromptDependencyManifest(
        schema_version=PROMPT_IDENTITY_SCHEMA_VERSION,
        namespace=namespace,
        system_root=root_dependency(system_path, "system_root"),
        user_root=root_dependency(user_path, "user_root"),
        included_partials=partials,
        schema_snippets=schema_snippets,
        composition_version=PROMPT_COMPOSITION_VERSION,
    )
    payload = asdict(without_hash)
    payload.pop("prompt_content_hash", None)
    return replace(
        without_hash,
        prompt_content_hash=hashlib.sha256(
            json.dumps(
                payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest(),
    )


def build_llm_execution_identity(
    *,
    prompt_content_hash: str,
    provider: str,
    model: str,
    temperature: float | None,
    seed: int | None,
    max_output_tokens: int | None = None,
    timeout_seconds: float | None = None,
    provider_retry_count: int = 0,
    retrieval_mode: str = "chat_json",
    routing_policy: dict[str, Any] | None = None,
    compaction_policy: dict[str, Any] | None = None,
    output_contract_schema_version: str = "",
    validator_version: str = "",
) -> LLMExecutionIdentity:
    """Build the stable, content-free identity for one model execution.

    The payload deliberately contains only resolved configuration and hashes.  It
    excludes checkout paths, timestamps, prompt text, source content, and
    request-local IDs so compatible work can be reused across processes.
    """

    identity = LLMExecutionIdentity(
        schema_version=PROMPT_IDENTITY_SCHEMA_VERSION,
        prompt_content_hash=str(prompt_content_hash or "").strip(),
        provider=str(provider or "").strip(),
        model=str(model or "").strip(),
        temperature=None if temperature is None else float(temperature),
        seed=None if seed is None else int(seed),
        output_controls={
            "max_output_tokens": (
                None if max_output_tokens is None else int(max_output_tokens)
            ),
            "timeout_seconds": (
                None if timeout_seconds is None else float(timeout_seconds)
            ),
            "provider_retry_count": int(provider_retry_count),
        },
        retrieval_mode=str(retrieval_mode or "chat_json").strip() or "chat_json",
        routing_policy=dict(routing_policy or {}),
        compaction_policy=dict(compaction_policy or {}),
        output_contract_schema_version=str(
            output_contract_schema_version or ""
        ).strip(),
        validator_version=str(validator_version or "").strip(),
    )
    payload = asdict(identity)
    payload.pop("execution_identity", None)
    return LLMExecutionIdentity(
        **{
            **payload,
            "execution_identity": hashlib.sha256(
                json.dumps(
                    payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest(),
        }
    )


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
    include_templates = _load_prompt_includes(data.get("includes", []), owner_path=path)
    include_texts = [item.text for item in include_templates]
    composed_text = "\n\n".join([*include_texts, str(text)]).strip() + "\n"
    (
        schema_snippets,
        schema_snippet_sources,
        schema_snippet_paths,
        schema_snippet_sha256s,
    ) = _load_prompt_schema_snippets(
        data.get("schema_snippets", {}),
        owner_path=path,
    )
    digest = hashlib.sha256(composed_text.encode("utf-8")).hexdigest()
    return PromptTemplate(
        schema_version="1.0",
        path=str(path),
        text=composed_text,
        sha256=digest,
        include_paths=[item.path for item in include_templates],
        include_sha256s=[item.sha256 for item in include_templates],
        schema_snippets=schema_snippets,
        schema_snippet_sources=schema_snippet_sources,
        schema_snippet_paths=schema_snippet_paths,
        schema_snippet_sha256s=schema_snippet_sha256s,
    )


def _load_prompt_includes(payload: object, *, owner_path: Path) -> list[PromptTemplate]:
    if payload in (None, ""):
        return []
    if not isinstance(payload, list):
        raise AppError(
            code="prompt_include_invalid",
            message="Prompt includes must be a list of prompt-root relative paths",
            retryable=False,
            context={"path": str(owner_path)},
        )
    includes: list[PromptTemplate] = []
    for raw_include in payload:
        include_path = _resolve_prompt_relative_path(raw_include, owner_path=owner_path)
        includes.append(_load_prompt_include(include_path))
    return includes


def _load_prompt_include(path: Path) -> PromptTemplate:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AppError(
            code="prompt_include_not_found",
            message=f"Prompt include file not found: {path}",
            cause=exc,
            retryable=False,
            context={"path": str(path)},
        ) from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise AppError(
            code="prompt_include_yaml_invalid",
            message=f"Prompt include YAML invalid: {path}",
            cause=exc,
            retryable=False,
        ) from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise AppError(
            code="prompt_include_yaml_invalid",
            message=f"Prompt include YAML root must be a mapping: {path}",
            retryable=False,
            context={"path": str(path)},
        )
    text = str(data.get("text") or "")
    if not text:
        raise AppError(
            code="prompt_include_empty",
            message=f"Prompt include file is empty: {path}",
            retryable=False,
            context={"path": str(path)},
        )
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return PromptTemplate(
        schema_version="1.0",
        path=str(path.resolve()),
        text=text,
        sha256=digest,
    )


def _resolve_prompt_relative_path(raw_path: object, *, owner_path: Path) -> Path:
    rel = str(raw_path or "").strip()
    if not rel:
        raise AppError(
            code="prompt_include_invalid",
            message="Prompt include path is required",
            retryable=False,
            context={"path": str(owner_path)},
        )
    root = PROMPTS_ROOT.resolve()
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AppError(
            code="prompt_include_invalid",
            message="Prompt include path must resolve inside the prompts root",
            cause=exc,
            retryable=False,
            context={"path": str(owner_path), "include": rel},
        ) from exc
    return candidate


def _load_prompt_schema_snippets(
    payload: object, *, owner_path: Path
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    if payload in (None, ""):
        return {}, {}, {}, {}
    if not isinstance(payload, dict):
        raise AppError(
            code="prompt_schema_snippets_invalid",
            message="Prompt schema_snippets must be a mapping",
            retryable=False,
            context={"path": str(owner_path)},
        )
    snippets: dict[str, str] = {}
    sources: dict[str, str] = {}
    paths: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for raw_key, raw_spec in payload.items():
        key = str(raw_key or "").strip()
        if not key:
            raise AppError(
                code="prompt_schema_snippets_invalid",
                message="Prompt schema snippet variable name is required",
                retryable=False,
                context={"path": str(owner_path)},
            )
        snippet, source, schema_path, schema_hash = _build_prompt_schema_snippet(
            raw_spec, owner_path=owner_path
        )
        snippets[key] = snippet
        sources[key] = source
        paths[key] = schema_path
        hashes[key] = schema_hash
    return snippets, sources, paths, hashes


def _build_prompt_schema_snippet(
    spec: object, *, owner_path: Path
) -> tuple[str, str, str, str]:
    if isinstance(spec, str):
        schema_name = spec
        pointer = ""
    elif isinstance(spec, dict):
        schema_name = str(spec.get("schema") or "").strip()
        pointer = str(spec.get("pointer") or "").strip()
    else:
        raise AppError(
            code="prompt_schema_snippets_invalid",
            message="Prompt schema snippet spec must be a schema name or mapping",
            retryable=False,
            context={"path": str(owner_path)},
        )
    schema_path = _resolve_schema_path(schema_name, owner_path=owner_path)
    try:
        raw_schema = schema_path.read_bytes()
        schema_payload = json.loads(raw_schema.decode("utf-8"))
    except FileNotFoundError as exc:
        raise AppError(
            code="prompt_schema_not_found",
            message=f"Prompt schema source not found: {schema_path}",
            cause=exc,
            retryable=False,
            context={"path": str(owner_path), "schema": schema_name},
        ) from exc
    except json.JSONDecodeError as exc:
        raise AppError(
            code="prompt_schema_invalid_json",
            message=f"Prompt schema source is invalid JSON: {schema_path}",
            cause=exc,
            retryable=False,
            context={"path": str(owner_path), "schema": schema_name},
        ) from exc
    target = _json_pointer_get(schema_payload, pointer)
    source = f"{schema_name}#{pointer}" if pointer else schema_name
    lines = [f"Schema source: {source}", *_schema_snippet_lines(target)]
    return (
        "\n".join(lines),
        source,
        _canonical_dependency_path(schema_path, root=SCHEMAS_ROOT, prefix="schemas"),
        hashlib.sha256(raw_schema).hexdigest(),
    )


def _resolve_schema_path(schema_name: str, *, owner_path: Path) -> Path:
    if not schema_name:
        raise AppError(
            code="prompt_schema_snippets_invalid",
            message="Prompt schema snippet source schema is required",
            retryable=False,
            context={"path": str(owner_path)},
        )
    root = SCHEMAS_ROOT.resolve()
    candidate = (root / schema_name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AppError(
            code="prompt_schema_snippets_invalid",
            message="Prompt schema snippet source must resolve inside the schemas root",
            cause=exc,
            retryable=False,
            context={"path": str(owner_path), "schema": schema_name},
        ) from exc
    return candidate


def _json_pointer_get(payload: Any, pointer: str) -> Any:
    if not pointer:
        return payload
    if not pointer.startswith("/"):
        raise AppError(
            code="prompt_schema_pointer_invalid",
            message="Prompt schema snippet pointer must be a JSON pointer",
            retryable=False,
            context={"pointer": pointer},
        )
    current = payload
    for raw_part in pointer.strip("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise AppError(
                    code="prompt_schema_pointer_invalid",
                    message="Prompt schema snippet pointer does not resolve",
                    cause=exc,
                    retryable=False,
                    context={"pointer": pointer},
                ) from exc
        else:
            current = None
        if current is None:
            raise AppError(
                code="prompt_schema_pointer_invalid",
                message="Prompt schema snippet pointer does not resolve",
                retryable=False,
                context={"pointer": pointer},
            )
    return current


def _schema_snippet_lines(schema: Any, *, depth: int = 0, name: str = "") -> list[str]:
    if not isinstance(schema, dict):
        return [f"Type: {type(schema).__name__}"]
    lines: list[str] = []
    schema_type = _schema_type(schema)
    if depth == 0:
        lines.append(f"Type: {schema_type}")
        required = _required_fields(schema)
        if required:
            lines.append(f"Required fields: {', '.join(required)}")
    properties = schema.get("properties")
    if isinstance(properties, dict):
        if depth == 0:
            lines.append("Fields:")
        required_fields = set(_required_fields(schema))
        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                continue
            descriptor = _schema_field_descriptor(
                prop_schema,
                required=prop_name in required_fields,
            )
            indent = "  " * depth
            lines.append(f"{indent}- {prop_name}: {descriptor}")
            if depth < 2 and _schema_type(prop_schema) in {"object", "array"}:
                lines.extend(
                    _schema_snippet_lines(
                        prop_schema,
                        depth=depth + 1,
                        name=str(prop_name),
                    )
                )
    elif schema_type == "array" and isinstance(schema.get("items"), dict):
        descriptor = _schema_field_descriptor(schema["items"], required=False)
        label = f"{name} items" if name else "Items"
        lines.append(f"{'  ' * depth}- {label}: {descriptor}")
        if depth < 2:
            lines.extend(
                _schema_snippet_lines(schema["items"], depth=depth + 1, name=label)
            )
    return lines or [f"Type: {schema_type}"]


def _schema_field_descriptor(schema: dict[str, Any], *, required: bool) -> str:
    parts = [_schema_type(schema)]
    if required:
        parts.append("required")
    for key in (
        "enum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
    ):
        if key not in schema:
            continue
        value = schema[key]
        if key == "enum" and isinstance(value, list):
            parts.append("enum=" + "|".join(str(item) for item in value))
        else:
            parts.append(f"{key}={value}")
    description = str(schema.get("description") or "").strip()
    if description:
        parts.append(f"description={description}")
    return ", ".join(parts)


def _schema_type(schema: dict[str, Any]) -> str:
    raw_type = schema.get("type")
    if isinstance(raw_type, list):
        return "|".join(str(item) for item in raw_type)
    if raw_type:
        return str(raw_type)
    if "enum" in schema:
        return "enum"
    if "properties" in schema:
        return "object"
    if "items" in schema:
        return "array"
    return "value"


def _required_fields(schema: dict[str, Any]) -> list[str]:
    required = schema.get("required")
    if not isinstance(required, list):
        return []
    return [str(item) for item in required]
