from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, fields
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Sequence

import yaml
from dotenv import find_dotenv, load_dotenv

from src.contracts.browser_download import (
    BrowserDownloadCaptchaHandoffPolicy,
    BrowserDownloadIdentityFieldUpsertRequest,
    BrowserDownloadIdentityFieldUpsertResponse,
    BrowserDownloadRequiredSelectOverrideProposal,
    BrowserDownloadRequiredSelectOverrideRequest,
    BrowserDownloadRequiredSelectOverrideResponse,
    BrowserDownloadRouteBudget,
    BrowserDownloadRouteSuppressionPolicy,
    BrowserDownloadSessionReusePolicy,
    BrowserDownloadSettings,
    BrowserDownloadWarmWorkerPoolPolicy,
)
from src.contracts.config import (
    AppConfigReadRequest,
    AppConfigReadResponse,
    AppConfigWriteRequest,
    AppConfigWriteResponse,
    AppSettings,
    ConfigLoadRequest,
    IngestSettingsBuildRequest,
    OpenAICredentialResolveRequest,
    OpenAICredentialResolveResponse,
)
from src.contracts.ingest import IngestSettings
from src.contracts.publish import PublishSettings
from src.contracts.publisher_inventory import PublisherInventorySettings
from src.contracts.run_context import RunContext
from src.contracts.wordpress import WordPressAuthSettings
from src.services._config_service.app_document import (
    read_app_config_document as _read_app_config_document,
)
from src.services._config_service.app_document import (
    write_app_config_document as _write_app_config_document,
)
from src.services._config_service.identity import (
    load_browser_download_identity as _load_browser_download_identity,
)
from src.services._config_service.identity import (
    plan_browser_download_identity_field_upserts as _plan_browser_download_identity_field_upserts,
)
from src.services._config_service.identity import (
    serialize_browser_download_identity as _serialize_browser_download_identity,
)
from src.services._config_service.yaml_mapping import (
    YamlMappingError,
    deep_merge_mappings,
)
from src.services._config_service.yaml_mapping import (
    load_yaml_mapping as _read_yaml_mapping,
)
from src.services._config_service.yaml_mapping import (
    parse_yaml_mapping as _parse_yaml_mapping,
)
from src.utils.coercion import (
    coerce_bool as _to_bool,
)
from src.utils.coercion import (
    coerce_extended_bool as _to_config_bool,
)
from src.utils.coercion import (
    coerce_float as _to_float,
)
from src.utils.coercion import (
    coerce_int as _to_int,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.config_service")

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "app.yaml"
DEFAULT_LLM_COSTS_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "llm-costs.yaml"
)
CONFIG_PATH_ENV_KEY = "MARKET_LENSE_CONFIG_PATH"
CONFIG_PROFILE_ENV_KEY = "MARKET_LENSE_CONFIG_PROFILE"
DEFAULT_HTML_TAG_ACRONYMS_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "html-tag-acronyms.yaml"
)
DEFAULT_BROWSER_DOWNLOAD_IDENTITY_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "browser_download_identity.yaml"
)
DEFAULT_PUBLISHER_INVENTORY_PROMPT_NAMESPACE = "publisher_inventory/discovery"
DEFAULT_PUBLISHER_INVENTORY_CANDIDATE_SCREENING_PROMPT_NAMESPACE = (
    "publisher_inventory/meaningful_candidate_screen"
)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _env_value(key: str) -> str:
    return os.getenv(key, "").strip()


def resolve_openai_credential(
    request: OpenAICredentialResolveRequest,
    ctx: RunContext,
) -> OpenAICredentialResolveResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_credential_resolve_start",
            module=logger.name,
            fields={"source": "env:OPENAI_API_KEY"},
        )
    )
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path)
    api_key = _env_value("OPENAI_API_KEY")
    if not api_key:
        raise AppError(
            code="openai_missing_api_key",
            message="OpenAI credential is not configured",
            retryable=False,
            context={"source": "env:OPENAI_API_KEY"},
        )
    response = OpenAICredentialResolveResponse(
        schema_version="1.0",
        api_key=api_key,
        source="env:OPENAI_API_KEY",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_credential_resolve_complete",
            module=logger.name,
            fields={"source": response.source, "configured": True},
        )
    )
    return response


def _to_str(value: Any, default: str) -> str:
    if _is_missing(value):
        return default
    token = str(value).strip()
    return token or default


def _opt_int(value: object) -> int | None:
    if _is_missing(value):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class _SettingSpec:
    field_name: str
    config_key: str
    default: Any
    coerce: Callable[[Any, Any], Any]
    env_key: str | None = None
    env_first: bool = False
    minimum: int | float | None = None
    minimum_mode: str = "clamp"


def _resolve_setting_raw(section: dict[str, Any], spec: _SettingSpec) -> Any:
    config_value = section.get(spec.config_key)
    env_value = _env_value(spec.env_key) if spec.env_key else ""
    if spec.env_first and not _is_missing(env_value):
        return env_value
    if not spec.env_first and _is_missing(config_value) and spec.env_key:
        return env_value
    return config_value


def _apply_setting_minimum(value: Any, spec: _SettingSpec) -> Any:
    if spec.minimum is None or not isinstance(value, (int, float)):
        return value
    if value >= spec.minimum:
        return value
    if spec.minimum_mode == "default":
        return spec.default
    return spec.minimum


def _resolve_scalar_settings(
    section: dict[str, Any],
    specs: Sequence[_SettingSpec],
) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for spec in specs:
        value = spec.coerce(_resolve_setting_raw(section, spec), spec.default)
        resolved[spec.field_name] = _apply_setting_minimum(value, spec)
    return resolved


def _resolve_optional_path(raw_value: Any, *, base_path: Path) -> str:
    if _is_missing(raw_value):
        return ""
    candidate = Path(str(raw_value).strip()).expanduser()
    if not candidate.is_absolute():
        candidate = (base_path / candidate).resolve()
    return str(candidate)


def _resolve_runtime_base_path(config_path: Path) -> Path:
    # Runtime-owned paths have one meaning regardless of whether an operator
    # selects the base config or a nested in-workspace profile.  A deliberately
    # external config remains its own portable workspace for local/test use.
    for candidate in (config_path.resolve().parent, *config_path.resolve().parents):
        if (
            candidate.joinpath("pyproject.toml").is_file()
            and candidate.joinpath("src").is_dir()
        ):
            return candidate
    return config_path.resolve().parent


def _resolve_bootstrap_config_path(path: str) -> Path:
    requested = path.strip()
    if requested:
        return Path(requested).resolve()
    env_path = _env_value(CONFIG_PATH_ENV_KEY)
    if env_path:
        return Path(env_path).expanduser().resolve()
    return CONFIG_PATH.resolve()


def _iter_config_overlay_paths(config_path: Path) -> list[Path]:
    if config_path.name != "app.yaml":
        return []
    overlays: list[Path] = []
    profile = _env_value(CONFIG_PROFILE_ENV_KEY)
    if profile:
        overlays.append(config_path.with_name(f"app.{profile}.yaml"))
    local_overlay = config_path.with_name("app.local.yaml")
    if local_overlay not in overlays:
        overlays.append(local_overlay)
    return [candidate for candidate in overlays if candidate.exists()]


def _load_yaml_mapping_or_runtime_error(
    path: str | Path, *, label: str
) -> dict[str, Any]:
    try:
        return _read_yaml_mapping(path, label=label)
    except YamlMappingError as exc:
        raise RuntimeError(str(exc)) from exc.cause or exc


@lru_cache(maxsize=1)
def _default_config_data() -> dict[str, Any]:
    return _read_yaml_mapping(CONFIG_PATH, label="Config")


def _default_config_value(*keys: str, fallback: Any) -> Any:
    current: Any = _default_config_data()
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return fallback
        current = current[key]
    return current


def _load_yaml_mapping(path: str, *, label: str) -> dict[str, Any]:
    return _load_yaml_mapping_or_runtime_error(path, label=label)


def _normalize_html_tag_acronyms(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value).strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(token)
    return normalized


def _load_html_tag_acronyms(path: str) -> list[str]:
    payload = _load_yaml_mapping_or_runtime_error(path, label="HTML acronym")
    acronyms = _normalize_html_tag_acronyms(payload.get("html_tag_acronyms"))
    if not acronyms:
        raise RuntimeError(
            f"HTML acronym YAML must contain a non-empty 'html_tag_acronyms' list: {path}"
        )
    return acronyms


def _load_config(path: str, *, include_overlays: bool = True) -> dict[str, Any]:
    config_path = Path(path).resolve()
    try:
        payload = _read_yaml_mapping(config_path, label="Config")
        if include_overlays:
            for overlay_path in _iter_config_overlay_paths(config_path):
                overlay_payload = _read_yaml_mapping(
                    overlay_path, label="Config overlay"
                )
                payload = deep_merge_mappings(payload, overlay_payload)
        return payload
    except YamlMappingError as exc:
        if exc.kind == "not_found":
            raise RuntimeError(f"Config file not found: {exc.path}") from exc
        if exc.kind == "invalid":
            raise RuntimeError(f"Config YAML invalid: {exc.path}") from exc
        if exc.kind == "root_invalid":
            raise RuntimeError(f"Config YAML must be a mapping: {exc.path}") from exc
        raise RuntimeError(str(exc)) from exc


def _resolve_pricing_path(
    cost_cfg: dict[str, Any], *, config_path: Path, runtime_base_path: Path
) -> Path:
    raw_path = str(cost_cfg.get("pricing_path") or "").strip()
    if raw_path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            # In-workspace app profiles use the canonical workspace resolver;
            # an external portable profile keeps a sibling rate card.
            base_path = (
                runtime_base_path
                if runtime_base_path != config_path.parent
                else config_path.parent
            )
            candidate = base_path / candidate
        return candidate.resolve()
    sibling = config_path.with_name("llm-costs.yaml")
    if sibling.exists():
        return sibling.resolve()
    return DEFAULT_LLM_COSTS_PATH.resolve()


def _load_model_pricing_from_cost_config(
    cost_cfg: dict[str, Any], *, config_path: Path, runtime_base_path: Path
) -> dict[str, Any]:
    inline_pricing = cost_cfg.get("pricing")
    if isinstance(inline_pricing, dict) and inline_pricing:
        return inline_pricing
    pricing_path = _resolve_pricing_path(
        cost_cfg, config_path=config_path, runtime_base_path=runtime_base_path
    )
    payload = _load_yaml_mapping_or_runtime_error(pricing_path, label="LLM costs")
    pricing = payload.get("pricing")
    if not isinstance(pricing, dict):
        raise RuntimeError(
            f"LLM costs YAML must contain a non-empty 'pricing' mapping: {pricing_path}"
        )
    return pricing


def _resolve_cost_config(
    data: dict[str, Any], *, config_path: Path, runtime_base_path: Path
) -> dict[str, Any]:
    cost_cfg = dict(data.get("cost", {}) or {})
    cost_cfg["pricing"] = _load_model_pricing_from_cost_config(
        cost_cfg, config_path=config_path, runtime_base_path=runtime_base_path
    )
    return cost_cfg


def _resolve_config_path(path: str) -> Path:
    return _resolve_bootstrap_config_path(path)


def read_app_config(
    request: AppConfigReadRequest, ctx: RunContext
) -> AppConfigReadResponse:
    return _read_app_config_document(
        request,
        ctx,
        resolve_config_path=_resolve_config_path,
        parse_yaml_mapping=_parse_yaml_mapping,
    )


def write_app_config(
    request: AppConfigWriteRequest, ctx: RunContext
) -> AppConfigWriteResponse:
    return _write_app_config_document(
        request,
        ctx,
        resolve_config_path=_resolve_config_path,
        parse_yaml_mapping=_parse_yaml_mapping,
    )


def load_model_pricing(request: ConfigLoadRequest, ctx: RunContext) -> dict[str, Any]:
    config_path = _resolve_bootstrap_config_path(request.path)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="model_pricing_load_start",
            module=logger.name,
            fields={"path": str(config_path)},
        )
    )
    data = _load_config(str(config_path))
    cost_cfg = _resolve_cost_config(
        data,
        config_path=config_path,
        runtime_base_path=_resolve_runtime_base_path(config_path),
    )
    pricing = cost_cfg["pricing"]
    logger.info(
        log_event(
            ctx,
            role="service",
            event="model_pricing_load_complete",
            module=logger.name,
            fields={
                "path": str(config_path),
                "model_count": len(pricing),
                "models": sorted(str(key) for key in pricing.keys()),
            },
        )
    )
    return dict(pricing)


class _ConfigResolver:
    def __init__(self) -> None:
        self.missing: list[str] = []

    def need_env(self, key: str) -> str:
        value = _env_value(key)
        if _is_missing(value):
            self.missing.append(f"env:{key}")
        return value

    def need(
        self, section: dict, key: str, label: str, env_key: str | None = None
    ) -> str:
        value = section.get(key)
        if _is_missing(value) and env_key:
            env_value = _env_value(env_key)
            if not _is_missing(env_value):
                return env_value
        if _is_missing(value):
            self.missing.append(label if not env_key else f"{label}|env:{env_key}")
            return ""
        return str(value)

    def need_path(
        self,
        section: dict,
        key: str,
        label: str,
        *,
        base_path: Path,
        env_key: str | None = None,
    ) -> str:
        value = self.need(section, key, label, env_key)
        return _resolve_optional_path(value, base_path=base_path)


@dataclass(frozen=True)
class _ConfigLoadSections:
    config_path: Path
    runtime_base_path: Path
    data: dict[str, Any]
    resolver: _ConfigResolver
    paths: dict[str, Any]
    ingest: dict[str, Any]
    llm_cfg: dict[str, Any]
    drive_cfg: dict[str, Any]
    pdf_text: dict[str, Any]
    candidate_page_gate_cfg: dict[str, Any]
    figure_captions_cfg: dict[str, Any]
    rank: dict[str, Any]
    validation_cfg: dict[str, Any]
    contents_page: dict[str, Any]
    evidence_packs_cfg: dict[str, Any]
    artifacts_cfg: dict[str, Any]
    analysis_cfg: dict[str, Any]
    cost_cfg: dict[str, Any]
    cross_report_analysis_cfg: dict[str, Any]


@dataclass(frozen=True)
class _ResolvedAppSettingsLoad:
    settings: AppSettings
    paths_settings: dict[str, str]


def _load_config_sections(request: ConfigLoadRequest) -> _ConfigLoadSections:
    config_path = _resolve_bootstrap_config_path(request.path)
    data = _load_config(str(config_path))
    runtime_base_path = _resolve_runtime_base_path(config_path)
    ingest = data.get("ingest", {}) or {}
    return _ConfigLoadSections(
        config_path=config_path,
        runtime_base_path=runtime_base_path,
        data=data,
        resolver=_ConfigResolver(),
        paths=data.get("paths", {}) or {},
        ingest=ingest,
        llm_cfg=ingest.get("llm", {}) or {},
        drive_cfg=ingest.get("drive", {}) or {},
        pdf_text=ingest.get("pdf_text", {}) or {},
        candidate_page_gate_cfg=ingest.get("candidate_page_gate", {}) or {},
        figure_captions_cfg=ingest.get("figure_captions", {}) or {},
        rank=data.get("rank", {}) or {},
        validation_cfg=ingest.get("validation", {}) or {},
        contents_page=ingest.get("contents_page", {}) or {},
        evidence_packs_cfg=ingest.get("evidence_packs", {}) or {},
        artifacts_cfg=ingest.get("artifacts", {}) or {},
        analysis_cfg=data.get("analysis", {}) or {},
        cost_cfg=_resolve_cost_config(
            data, config_path=config_path, runtime_base_path=runtime_base_path
        ),
        cross_report_analysis_cfg=data.get("cross_report_analysis", {}) or {},
    )


def _normalize_openai_models(raw_value: Any) -> dict[str, str]:
    openai_models: dict[str, str] = {}
    if not isinstance(raw_value, dict):
        return openai_models
    for key, value in raw_value.items():
        key_str = str(key).strip()
        val_str = str(value).strip()
        if key_str and val_str:
            openai_models[key_str] = val_str
    return openai_models


def _normalize_keyword_list(raw_value: Any, *, default_values: list[str]) -> list[str]:
    values = raw_value or default_values
    normalized = [str(value).strip() for value in values if str(value).strip()]
    return normalized or default_values[:]


def _normalize_evidence_pack_registry(raw_value: Any) -> list[str]:
    default_pack_registry = _normalize_keyword_list(
        _default_config_value(
            "ingest",
            "evidence_packs",
            "registry",
            fallback=[
                "doc_map",
                "scope",
                "methods",
                "findings",
                "limitations",
                "quote_candidates",
            ],
        ),
        default_values=[
            "doc_map",
            "scope",
            "methods",
            "findings",
            "limitations",
            "quote_candidates",
        ],
    )
    evidence_pack_registry: list[str] = []
    if isinstance(raw_value, list):
        for value in raw_value:
            token = str(value).strip()
            if token and token not in evidence_pack_registry:
                evidence_pack_registry.append(token)
    if not evidence_pack_registry:
        evidence_pack_registry = default_pack_registry[:]
    if "doc_map" not in evidence_pack_registry:
        evidence_pack_registry = ["doc_map", *evidence_pack_registry]
    elif evidence_pack_registry[0] != "doc_map":
        evidence_pack_registry = ["doc_map"] + [
            item for item in evidence_pack_registry if item != "doc_map"
        ]
    return evidence_pack_registry


def _resolve_allowed_string(value: Any, *, default: str, allowed: set[str]) -> str:
    token = _to_str(value, default).lower()
    return token if token in allowed else default


__all__ = [
    "Any",
    "AppConfigReadRequest",
    "AppConfigReadResponse",
    "AppConfigWriteRequest",
    "AppConfigWriteResponse",
    "AppError",
    "AppSettings",
    "BrowserDownloadCaptchaHandoffPolicy",
    "BrowserDownloadIdentityFieldUpsertRequest",
    "BrowserDownloadIdentityFieldUpsertResponse",
    "BrowserDownloadRequiredSelectOverrideProposal",
    "BrowserDownloadRequiredSelectOverrideRequest",
    "BrowserDownloadRequiredSelectOverrideResponse",
    "BrowserDownloadRouteBudget",
    "BrowserDownloadRouteSuppressionPolicy",
    "BrowserDownloadSessionReusePolicy",
    "BrowserDownloadSettings",
    "BrowserDownloadWarmWorkerPoolPolicy",
    "CONFIG_PATH",
    "DEFAULT_LLM_COSTS_PATH",
    "CONFIG_PATH_ENV_KEY",
    "CONFIG_PROFILE_ENV_KEY",
    "DEFAULT_BROWSER_DOWNLOAD_IDENTITY_PATH",
    "DEFAULT_HTML_TAG_ACRONYMS_PATH",
    "DEFAULT_PUBLISHER_INVENTORY_CANDIDATE_SCREENING_PROMPT_NAMESPACE",
    "DEFAULT_PUBLISHER_INVENTORY_PROMPT_NAMESPACE",
    "ConfigLoadRequest",
    "IngestSettings",
    "IngestSettingsBuildRequest",
    "Path",
    "PublishSettings",
    "PublisherInventorySettings",
    "RunContext",
    "WordPressAuthSettings",
    "_ConfigLoadSections",
    "_ConfigResolver",
    "_ResolvedAppSettingsLoad",
    "_SettingSpec",
    "_apply_setting_minimum",
    "_default_config_value",
    "_env_value",
    "_is_missing",
    "_load_browser_download_identity",
    "_load_config",
    "_load_config_sections",
    "_load_html_tag_acronyms",
    "_load_model_pricing_from_cost_config",
    "_load_yaml_mapping",
    "_load_yaml_mapping_or_runtime_error",
    "_normalize_evidence_pack_registry",
    "_normalize_html_tag_acronyms",
    "_normalize_keyword_list",
    "_normalize_openai_models",
    "_opt_int",
    "_plan_browser_download_identity_field_upserts",
    "_read_yaml_mapping",
    "_resolve_allowed_string",
    "_resolve_bootstrap_config_path",
    "_resolve_cost_config",
    "_resolve_pricing_path",
    "_resolve_optional_path",
    "_resolve_runtime_base_path",
    "_resolve_scalar_settings",
    "_resolve_setting_raw",
    "_serialize_browser_download_identity",
    "_to_bool",
    "_to_config_bool",
    "_to_float",
    "_to_int",
    "_to_str",
    "asdict",
    "fields",
    "find_dotenv",
    "load_model_pricing",
    "load_dotenv",
    "log_event",
    "logger",
    "os",
    "read_app_config",
    "write_app_config",
    "yaml",
]
