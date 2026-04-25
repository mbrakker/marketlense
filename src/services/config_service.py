from __future__ import annotations

import os
import logging
from functools import lru_cache
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from dotenv import load_dotenv, find_dotenv
import yaml

from src.contracts.config import (
    AppConfigReadRequest,
    AppConfigReadResponse,
    AppConfigWriteRequest,
    AppConfigWriteResponse,
    AppSettings,
    ConfigLoadRequest,
    IngestSettingsBuildRequest,
)
from src.contracts.browser_download import (
    BrowserDownloadIdentityField,
    BrowserDownloadIdentityFieldUpsertRequest,
    BrowserDownloadIdentityFieldUpsertResponse,
    BrowserDownloadSettings,
)
from src.contracts.publisher_inventory import PublisherInventorySettings
from src.contracts.ingest import IngestSettings
from src.contracts.publish import PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.wordpress import WordPressAuthSettings
from src.services._config_identity import (
    identity_field_match_tokens as _identity_field_match_tokens,
    load_browser_download_identity as _load_browser_download_identity,
    normalize_browser_download_identity_key as _normalize_browser_download_identity_key,
    should_upsert_browser_download_identity_field as _should_upsert_browser_download_identity_field,
)
from src.services._yaml_config import (
    YamlMappingError,
    deep_merge_mappings,
    load_yaml_mapping as _read_yaml_mapping,
    parse_yaml_mapping as _parse_yaml_mapping,
)
from src.utils.coercion import (
    coerce_bool as _to_bool,
    coerce_extended_bool as _to_config_bool,
    coerce_float as _to_float,
    coerce_int as _to_int,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.config_service")

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "app.yaml"
CONFIG_PATH_ENV_KEY = "MARKET_LENSE_CONFIG_PATH"
CONFIG_PROFILE_ENV_KEY = "MARKET_LENSE_CONFIG_PROFILE"
DEFAULT_HTML_TAG_ACRONYMS_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "html-tag-acronyms.yaml"
)
DEFAULT_BROWSER_DOWNLOAD_IDENTITY_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "browser_download_identity.yaml"
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
    normalized = config_path.resolve()
    if normalized.parent.name == "config" and normalized.parent.parent.name == "src":
        return normalized.parent.parent.parent
    return normalized.parent


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


def _resolve_config_path(path: str) -> Path:
    return _resolve_bootstrap_config_path(path)


def read_app_config(
    request: AppConfigReadRequest, ctx: RunContext
) -> AppConfigReadResponse:
    cfg_path = _resolve_config_path(request.path)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="app_config_read_start",
            module=logger.name,
            fields={"path": str(cfg_path)},
        )
    )
    if not cfg_path.exists():
        raise AppError(
            code="config_file_not_found",
            message=f"Config file not found: {cfg_path}",
            retryable=False,
            context={"path": str(cfg_path)},
        )
    try:
        content = cfg_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise AppError(
            code="config_read_failed",
            message=f"Failed to read config file: {cfg_path}",
            cause=exc,
            retryable=False,
            context={"path": str(cfg_path)},
        ) from exc
    try:
        payload = _parse_yaml_mapping(content, label="Config", path=cfg_path)
    except YamlMappingError as exc:
        if exc.kind == "invalid":
            raise AppError(
                code="config_yaml_invalid",
                message=f"Config YAML invalid: {cfg_path}",
                cause=exc.cause,
                retryable=False,
                context={"path": str(cfg_path)},
            ) from exc
        raise AppError(
            code="config_yaml_root_invalid",
            message=f"Config YAML root must be a mapping: {cfg_path}",
            retryable=False,
            context={"path": str(cfg_path), "root_type": exc.root_type or ""},
        ) from exc
    stat = cfg_path.stat()
    response = AppConfigReadResponse(
        schema_version="1.0",
        path=str(cfg_path),
        content=content,
        payload=payload,
        size_bytes=int(stat.st_size),
        modified_utc=float(stat.st_mtime),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="app_config_read_complete",
            module=logger.name,
            fields={
                "path": response.path,
                "size_bytes": response.size_bytes,
                "modified_utc": response.modified_utc,
                "top_level_keys": list(payload.keys()),
            },
        )
    )
    return response


def write_app_config(
    request: AppConfigWriteRequest, ctx: RunContext
) -> AppConfigWriteResponse:
    cfg_path = _resolve_config_path(request.path)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="app_config_write_start",
            module=logger.name,
            fields={
                "path": str(cfg_path),
                "make_backup": request.make_backup,
                "content_length": len(request.content),
            },
        )
    )
    normalized_content = request.content.replace("\r\n", "\n")
    if normalized_content and not normalized_content.endswith("\n"):
        normalized_content = f"{normalized_content}\n"
    try:
        payload = _parse_yaml_mapping(normalized_content, label="Config", path=cfg_path)
    except YamlMappingError as exc:
        if exc.kind == "invalid":
            raise AppError(
                code="config_yaml_invalid",
                message=f"Config YAML invalid: {cfg_path}",
                cause=exc.cause,
                retryable=False,
                context={"path": str(cfg_path)},
            ) from exc
        raise AppError(
            code="config_yaml_root_invalid",
            message=f"Config YAML root must be a mapping: {cfg_path}",
            retryable=False,
            context={"path": str(cfg_path), "root_type": exc.root_type or ""},
        ) from exc

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: str | None = None
    if request.make_backup and cfg_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = cfg_path.with_name(f"{cfg_path.name}.{stamp}.bak")
        backup.write_text(cfg_path.read_text(encoding="utf-8"), encoding="utf-8")
        backup_path = str(backup)

    try:
        cfg_path.write_text(normalized_content, encoding="utf-8")
    except Exception as exc:
        raise AppError(
            code="config_write_failed",
            message=f"Failed to write config file: {cfg_path}",
            cause=exc,
            retryable=False,
            context={"path": str(cfg_path)},
        ) from exc

    stat = cfg_path.stat()
    top_level_keys = [str(key) for key in payload.keys()]
    response = AppConfigWriteResponse(
        schema_version="1.0",
        path=str(cfg_path),
        bytes_written=len(normalized_content.encode("utf-8")),
        modified_utc=float(stat.st_mtime),
        top_level_keys=top_level_keys,
        backup_path=backup_path,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="app_config_write_complete",
            module=logger.name,
            fields={
                "path": response.path,
                "bytes_written": response.bytes_written,
                "modified_utc": response.modified_utc,
                "backup_path": response.backup_path or "",
                "top_level_keys": response.top_level_keys,
            },
        )
    )
    return response


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
    figure_captions_cfg: dict[str, Any]
    rank: dict[str, Any]
    validation_cfg: dict[str, Any]
    contents_page: dict[str, Any]
    evidence_packs_cfg: dict[str, Any]
    artifacts_cfg: dict[str, Any]
    analysis_cfg: dict[str, Any]
    cost_cfg: dict[str, Any]


@dataclass(frozen=True)
class _ResolvedAppSettingsLoad:
    settings: AppSettings
    paths_settings: dict[str, str]


def _load_config_sections(request: ConfigLoadRequest) -> _ConfigLoadSections:
    config_path = _resolve_bootstrap_config_path(request.path)
    data = _load_config(str(config_path))
    ingest = data.get("ingest", {}) or {}
    return _ConfigLoadSections(
        config_path=config_path,
        runtime_base_path=_resolve_runtime_base_path(config_path),
        data=data,
        resolver=_ConfigResolver(),
        paths=data.get("paths", {}) or {},
        ingest=ingest,
        llm_cfg=ingest.get("llm", {}) or {},
        drive_cfg=ingest.get("drive", {}) or {},
        pdf_text=ingest.get("pdf_text", {}) or {},
        figure_captions_cfg=ingest.get("figure_captions", {}) or {},
        rank=data.get("rank", {}) or {},
        validation_cfg=ingest.get("validation", {}) or {},
        contents_page=ingest.get("contents_page", {}) or {},
        evidence_packs_cfg=ingest.get("evidence_packs", {}) or {},
        artifacts_cfg=ingest.get("artifacts", {}) or {},
        analysis_cfg=data.get("analysis", {}) or {},
        cost_cfg=data.get("cost", {}) or {},
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


def _resolve_paths_settings(
    paths: dict[str, Any],
    resolver: _ConfigResolver,
) -> dict[str, str]:
    output_dir = resolver.need(paths, "output_dir", "paths.output_dir", "OUTPUT_DIR")
    cache_dir = resolver.need(paths, "cache_dir", "paths.cache_dir", "CACHE_DIR")
    state_db = resolver.need(paths, "state_db", "paths.state_db", "STATE_DB")
    reports_db = resolver.need(paths, "reports_db", "paths.reports_db", "REPORTS_DB")
    lock_path_raw = paths.get("ingest_lock")
    if _is_missing(lock_path_raw):
        lock_path_raw = _env_value("INGEST_LOCK_PATH")
    if _is_missing(lock_path_raw):
        lock_path_raw = str(Path(state_db).parent / "ingest.lock")
    return {
        "output_dir": output_dir,
        "cache_dir": cache_dir,
        "state_db": state_db,
        "reports_db": reports_db,
        "publisher_profiles_path": paths.get("publisher_profiles")
        or str(
            Path(__file__).resolve().parents[2]
            / "Wordpress"
            / "config"
            / "publisher-profiles.json"
        ),
        "category_mapping_path": paths.get("category_mappings")
        or str(
            Path(__file__).resolve().parents[1] / "config" / "category-mappings.yaml"
        ),
        "html_tag_acronyms_path": paths.get("html_tag_acronyms")
        or str(DEFAULT_HTML_TAG_ACRONYMS_PATH),
        "cover_style_path": paths.get("cover_styles")
        or str(Path(__file__).resolve().parents[1] / "config" / "cover-styles.yaml"),
        "ingest_lock_path": str(lock_path_raw),
    }


def _resolve_ingest_runtime_settings(
    ingest: dict[str, Any],
) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        ingest,
        [
            _SettingSpec(
                field_name="temperature",
                config_key="temperature",
                default=_to_float(
                    _default_config_value("ingest", "temperature", fallback=1.0), 1.0
                ),
                coerce=_to_float,
                env_key="TEMPERATURE",
            ),
            _SettingSpec(
                field_name="batch_limit",
                config_key="batch_limit",
                default=_to_int(
                    _default_config_value("ingest", "batch_limit", fallback=20), 20
                ),
                coerce=_to_int,
                env_key="BATCH_LIMIT",
            ),
            _SettingSpec(
                field_name="ingest_worker_limit",
                config_key="worker_limit",
                default=_to_int(
                    _default_config_value("ingest", "worker_limit", fallback=2), 2
                ),
                coerce=_to_int,
                env_key="INGEST_WORKER_LIMIT",
                minimum=1,
            ),
            _SettingSpec(
                field_name="report_worker_limit",
                config_key="report_worker_limit",
                default=_to_int(
                    _default_config_value("ingest", "report_worker_limit", fallback=2),
                    2,
                ),
                coerce=_to_int,
                env_key="INGEST_REPORT_WORKER_LIMIT",
                minimum=1,
            ),
            _SettingSpec(
                field_name="openai_timeout_seconds",
                config_key="timeout_seconds",
                default=_to_float(
                    _default_config_value("ingest", "timeout_seconds", fallback=600.0),
                    600.0,
                ),
                coerce=_to_float,
                env_key="OPENAI_TIMEOUT_SECONDS",
            ),
            _SettingSpec(
                field_name="ingest_lock_ttl_seconds",
                config_key="lock_ttl_seconds",
                default=_to_float(
                    _default_config_value(
                        "ingest", "lock_ttl_seconds", fallback=7200.0
                    ),
                    7200.0,
                ),
                coerce=_to_float,
                env_key="INGEST_LOCK_TTL_SECONDS",
            ),
            _SettingSpec(
                field_name="taxonomy_temperature",
                config_key="taxonomy_temperature",
                default=_to_float(
                    _default_config_value(
                        "ingest", "taxonomy_temperature", fallback=0.0
                    ),
                    0.0,
                ),
                coerce=_to_float,
                env_key="TAXONOMY_TEMPERATURE",
                env_first=True,
            ),
            _SettingSpec(
                field_name="cover_cache_enabled",
                config_key="cover_cache_enabled",
                default=_to_config_bool(
                    _default_config_value(
                        "ingest", "cover_cache_enabled", fallback=True
                    ),
                    True,
                ),
                coerce=_to_config_bool,
            ),
        ],
    )
    resolved["taxonomy_temperature"] = _to_float(
        _resolve_setting_raw(
            ingest,
            _SettingSpec(
                field_name="taxonomy_temperature",
                config_key="taxonomy_temperature",
                default=resolved["temperature"],
                coerce=_to_float,
                env_key="TAXONOMY_TEMPERATURE",
                env_first=True,
            ),
        ),
        resolved["temperature"],
    )
    resolved["openai_seed"] = _opt_int(ingest.get("seed"))
    return resolved


def _resolve_llm_runtime_settings(llm_cfg: dict[str, Any]) -> dict[str, Any]:
    return _resolve_scalar_settings(
        llm_cfg,
        [
            _SettingSpec(
                field_name="llm_retry_retries",
                config_key="retries",
                default=_to_int(
                    _default_config_value("ingest", "llm", "retries", fallback=1), 1
                ),
                coerce=_to_int,
                minimum=0,
            ),
            _SettingSpec(
                field_name="llm_retry_base_delay_seconds",
                config_key="base_delay_seconds",
                default=_to_float(
                    _default_config_value(
                        "ingest", "llm", "base_delay_seconds", fallback=1.0
                    ),
                    1.0,
                ),
                coerce=_to_float,
                minimum=0.0,
            ),
            _SettingSpec(
                field_name="llm_retry_backoff_step_seconds",
                config_key="backoff_step_seconds",
                default=_to_float(
                    _default_config_value(
                        "ingest", "llm", "backoff_step_seconds", fallback=1.0
                    ),
                    1.0,
                ),
                coerce=_to_float,
                minimum=0.0,
            ),
            _SettingSpec(
                field_name="llm_retry_jitter_seconds",
                config_key="jitter_seconds",
                default=_to_float(
                    _default_config_value(
                        "ingest", "llm", "jitter_seconds", fallback=0.25
                    ),
                    0.25,
                ),
                coerce=_to_float,
                minimum=0.0,
            ),
            _SettingSpec(
                field_name="llm_circuit_breaker_failure_threshold",
                config_key="circuit_breaker_failure_threshold",
                default=_to_int(
                    _default_config_value(
                        "ingest",
                        "llm",
                        "circuit_breaker_failure_threshold",
                        fallback=3,
                    ),
                    3,
                ),
                coerce=_to_int,
                minimum=0,
            ),
            _SettingSpec(
                field_name="llm_circuit_breaker_recovery_seconds",
                config_key="circuit_breaker_recovery_seconds",
                default=_to_float(
                    _default_config_value(
                        "ingest",
                        "llm",
                        "circuit_breaker_recovery_seconds",
                        fallback=30.0,
                    ),
                    30.0,
                ),
                coerce=_to_float,
                minimum=0.0,
            ),
        ],
    )


def _resolve_rank_settings(
    rank: dict[str, Any],
    *,
    openai_model: str,
    temperature: float,
    openai_timeout_seconds: float,
) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        rank,
        [
            _SettingSpec(
                field_name="rank_temperature",
                config_key="temperature",
                default=temperature,
                coerce=_to_float,
            ),
            _SettingSpec(
                field_name="rank_max_candidates",
                config_key="max_candidates",
                default=_to_int(
                    _default_config_value("rank", "max_candidates", fallback=40), 40
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_selected_max",
                config_key="selected_max",
                default=_to_int(
                    _default_config_value("rank", "selected_max", fallback=5), 5
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_min_overall_score",
                config_key="min_overall_score",
                default=_to_int(
                    _default_config_value("rank", "min_overall_score", fallback=78),
                    78,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_min_quality_score",
                config_key="min_quality_score",
                default=_to_int(
                    _default_config_value("rank", "min_quality_score", fallback=75),
                    75,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_min_insight_score",
                config_key="min_insight_score",
                default=_to_int(
                    _default_config_value("rank", "min_insight_score", fallback=75),
                    75,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_min_data_score",
                config_key="min_data_score",
                default=_to_int(
                    _default_config_value("rank", "min_data_score", fallback=70), 70
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="crop_refine_enabled",
                config_key="crop_refine_enabled",
                default=_to_config_bool(
                    _default_config_value("rank", "crop_refine_enabled", fallback=True),
                    True,
                ),
                coerce=_to_config_bool,
            ),
            _SettingSpec(
                field_name="crop_refine_page_dpi",
                config_key="crop_refine_page_dpi",
                default=_to_int(
                    _default_config_value("rank", "crop_refine_page_dpi", fallback=110),
                    110,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="crop_refine_temperature",
                config_key="crop_refine_temperature",
                default=_to_float(
                    _default_config_value(
                        "rank", "crop_refine_temperature", fallback=0.0
                    ),
                    0.0,
                ),
                coerce=_to_float,
            ),
            _SettingSpec(
                field_name="rank_timeout_seconds",
                config_key="timeout_seconds",
                default=openai_timeout_seconds,
                coerce=_to_float,
            ),
        ],
    )
    resolved["rank_model"] = (
        str(rank.get("model") or "").strip()
        or str(_default_config_value("rank", "model", fallback="")).strip()
        or openai_model
    )
    resolved["rank_seed"] = _opt_int(rank.get("seed"))
    resolved["crop_refine_mode"] = _resolve_allowed_string(
        rank.get(
            "crop_refine_mode",
            _default_config_value("rank", "crop_refine_mode", fallback="adaptive"),
        ),
        default=str(
            _default_config_value("rank", "crop_refine_mode", fallback="adaptive")
        ),
        allowed={"adaptive", "always", "off"},
    )
    resolved["crop_refine_timeout_seconds"] = _to_float(
        rank.get("crop_refine_timeout_seconds"),
        resolved["rank_timeout_seconds"],
    )
    return resolved


def _resolve_figure_caption_settings(
    figure_captions_cfg: dict[str, Any],
    *,
    openai_timeout_seconds: float,
) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        figure_captions_cfg,
        [
            _SettingSpec(
                field_name="figure_caption_enabled",
                config_key="enabled",
                default=_to_config_bool(
                    _default_config_value(
                        "ingest", "figure_captions", "enabled", fallback=False
                    ),
                    False,
                ),
                coerce=_to_config_bool,
                env_key="FIGURE_CAPTION_ENABLED",
            ),
            _SettingSpec(
                field_name="figure_caption_temperature",
                config_key="temperature",
                default=_to_float(
                    _default_config_value(
                        "ingest", "figure_captions", "temperature", fallback=0.2
                    ),
                    0.2,
                ),
                coerce=_to_float,
                env_key="FIGURE_CAPTION_TEMPERATURE",
            ),
            _SettingSpec(
                field_name="figure_caption_timeout_seconds",
                config_key="timeout_seconds",
                default=openai_timeout_seconds,
                coerce=_to_float,
                env_key="FIGURE_CAPTION_TIMEOUT_SECONDS",
            ),
            _SettingSpec(
                field_name="figure_caption_max_chars",
                config_key="max_chars",
                default=_to_int(
                    _default_config_value(
                        "ingest", "figure_captions", "max_chars", fallback=500
                    ),
                    500,
                ),
                coerce=_to_int,
                env_key="FIGURE_CAPTION_MAX_CHARS",
                minimum=1,
                minimum_mode="default",
            ),
        ],
    )
    resolved["figure_caption_prompt_namespace"] = _to_str(
        _resolve_setting_raw(
            figure_captions_cfg,
            _SettingSpec(
                field_name="figure_caption_prompt_namespace",
                config_key="prompt_namespace",
                default=str(
                    _default_config_value(
                        "ingest",
                        "figure_captions",
                        "prompt_namespace",
                        fallback="report_vs/figure_caption",
                    )
                ),
                coerce=_to_str,
                env_key="FIGURE_CAPTION_PROMPT_NAMESPACE",
            ),
        ),
        str(
            _default_config_value(
                "ingest",
                "figure_captions",
                "prompt_namespace",
                fallback="report_vs/figure_caption",
            )
        ),
    )
    return resolved


def _resolve_contents_settings(contents_page: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        contents_page,
        [
            _SettingSpec(
                field_name="contents_max_pages",
                config_key="max_pages",
                default=_to_int(
                    _default_config_value(
                        "ingest", "contents_page", "max_pages", fallback=8
                    ),
                    8,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="contents_min_headings",
                config_key="min_headings",
                default=_to_int(
                    _default_config_value(
                        "ingest", "contents_page", "min_headings", fallback=3
                    ),
                    3,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="contents_preview_enabled",
                config_key="preview_enabled",
                default=_to_config_bool(
                    _default_config_value(
                        "ingest", "contents_page", "preview_enabled", fallback=True
                    ),
                    True,
                ),
                coerce=_to_config_bool,
            ),
            _SettingSpec(
                field_name="contents_preview_dpi",
                config_key="render_dpi",
                default=_to_int(
                    _default_config_value(
                        "ingest", "contents_page", "render_dpi", fallback=144
                    ),
                    144,
                ),
                coerce=_to_int,
            ),
        ],
    )
    resolved["contents_keywords"] = _normalize_keyword_list(
        contents_page.get("keywords"),
        default_values=_normalize_keyword_list(
            _default_config_value(
                "ingest",
                "contents_page",
                "keywords",
                fallback=["table of contents", "contents", "index"],
            ),
            default_values=["table of contents", "contents", "index"],
        ),
    )
    return resolved


def _resolve_evidence_pack_settings(
    evidence_packs_cfg: dict[str, Any],
) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        evidence_packs_cfg,
        [
            _SettingSpec(
                field_name="evidence_pack_parallel_workers",
                config_key="parallel_workers",
                default=_to_int(
                    _default_config_value(
                        "ingest",
                        "evidence_packs",
                        "parallel_workers",
                        fallback=3,
                    ),
                    3,
                ),
                coerce=_to_int,
                env_key="EVIDENCE_PACK_PARALLEL_WORKERS",
                minimum=1,
            ),
            _SettingSpec(
                field_name="evidence_pack_global_max_in_flight",
                config_key="global_max_in_flight",
                default=_to_int(
                    _default_config_value(
                        "ingest",
                        "evidence_packs",
                        "global_max_in_flight",
                        fallback=2,
                    ),
                    2,
                ),
                coerce=_to_int,
                env_key="EVIDENCE_PACK_GLOBAL_MAX_IN_FLIGHT",
                minimum=1,
            ),
            _SettingSpec(
                field_name="evidence_pack_global_min_interval_ms",
                config_key="global_min_interval_ms",
                default=_to_int(
                    _default_config_value(
                        "ingest",
                        "evidence_packs",
                        "global_min_interval_ms",
                        fallback=250,
                    ),
                    250,
                ),
                coerce=_to_int,
                env_key="EVIDENCE_PACK_GLOBAL_MIN_INTERVAL_MS",
                minimum=0,
            ),
            _SettingSpec(
                field_name="evidence_pack_doc_map_max_attempts",
                config_key="doc_map_max_attempts",
                default=_to_int(
                    _default_config_value(
                        "ingest",
                        "evidence_packs",
                        "doc_map_max_attempts",
                        fallback=3,
                    ),
                    3,
                ),
                coerce=_to_int,
                env_key="EVIDENCE_PACK_DOC_MAP_MAX_ATTEMPTS",
                minimum=1,
            ),
            _SettingSpec(
                field_name="evidence_pack_doc_map_retry_delay_ms",
                config_key="doc_map_retry_delay_ms",
                default=_to_int(
                    _default_config_value(
                        "ingest",
                        "evidence_packs",
                        "doc_map_retry_delay_ms",
                        fallback=500,
                    ),
                    500,
                ),
                coerce=_to_int,
                env_key="EVIDENCE_PACK_DOC_MAP_RETRY_DELAY_MS",
                minimum=0,
            ),
            _SettingSpec(
                field_name="evidence_pack_enable_new_variety_packs",
                config_key="enable_new_variety_packs",
                default=_to_config_bool(
                    _default_config_value(
                        "ingest",
                        "evidence_packs",
                        "enable_new_variety_packs",
                        fallback=False,
                    ),
                    False,
                ),
                coerce=_to_config_bool,
                env_key="EVIDENCE_PACK_ENABLE_NEW_VARIETY_PACKS",
            ),
        ],
    )
    evidence_pack_registry_raw = evidence_packs_cfg.get("registry")
    env_evidence_pack_registry = _env_value("EVIDENCE_PACK_REGISTRY")
    if env_evidence_pack_registry:
        evidence_pack_registry_raw = [
            token.strip()
            for token in env_evidence_pack_registry.split(",")
            if token.strip()
        ]
    resolved["evidence_pack_registry"] = _normalize_evidence_pack_registry(
        evidence_pack_registry_raw
    )
    return resolved


def _resolve_artifact_settings(artifacts_cfg: dict[str, Any]) -> dict[str, Any]:
    return _resolve_scalar_settings(
        artifacts_cfg,
        [
            _SettingSpec(
                field_name="artifact_parallel_workers",
                config_key="parallel_workers",
                default=_to_int(
                    _default_config_value(
                        "ingest", "artifacts", "parallel_workers", fallback=4
                    ),
                    4,
                ),
                coerce=_to_int,
                env_key="ARTIFACT_PARALLEL_WORKERS",
                minimum=1,
            ),
            _SettingSpec(
                field_name="artifact_global_max_in_flight",
                config_key="global_max_in_flight",
                default=_to_int(
                    _default_config_value(
                        "ingest", "artifacts", "global_max_in_flight", fallback=2
                    ),
                    2,
                ),
                coerce=_to_int,
                env_key="ARTIFACT_GLOBAL_MAX_IN_FLIGHT",
                minimum=1,
            ),
            _SettingSpec(
                field_name="artifact_global_min_interval_ms",
                config_key="global_min_interval_ms",
                default=_to_int(
                    _default_config_value(
                        "ingest", "artifacts", "global_min_interval_ms", fallback=250
                    ),
                    250,
                ),
                coerce=_to_int,
                env_key="ARTIFACT_GLOBAL_MIN_INTERVAL_MS",
                minimum=0,
            ),
        ],
    )


def _resolve_pdf_text_settings(
    pdf_text: dict[str, Any],
    ingest: dict[str, Any],
) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        pdf_text,
        [
            _SettingSpec(
                field_name="pdf_text_max_pages",
                config_key="max_pages",
                default=_to_int(
                    _default_config_value(
                        "ingest", "pdf_text", "max_pages", fallback=5
                    ),
                    5,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="pdf_text_max_chars",
                config_key="max_chars",
                default=_to_int(
                    _default_config_value(
                        "ingest", "pdf_text", "max_chars", fallback=80_000
                    ),
                    80_000,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="pdf_text_min_density",
                config_key="min_density",
                default=_to_float(
                    _default_config_value(
                        "ingest", "pdf_text", "min_density", fallback=250.0
                    ),
                    250.0,
                ),
                coerce=_to_float,
            ),
            _SettingSpec(
                field_name="pdf_text_sample_pages",
                config_key="sample_pages",
                default=_to_int(
                    _default_config_value(
                        "ingest", "pdf_text", "sample_pages", fallback=3
                    ),
                    3,
                ),
                coerce=_to_int,
            ),
        ],
    )
    ocr_fallback_cfg = pdf_text.get("ocr_fallback") or {}
    resolved.update(
        _resolve_scalar_settings(
            ocr_fallback_cfg,
            [
                _SettingSpec(
                    field_name="pdf_text_ocr_enabled",
                    config_key="enabled",
                    default=_to_bool(
                        _default_config_value(
                            "ingest",
                            "pdf_text",
                            "ocr_fallback",
                            "enabled",
                            fallback=False,
                        ),
                        False,
                    ),
                    coerce=_to_bool,
                ),
                _SettingSpec(
                    field_name="pdf_text_ocr_timeout_seconds",
                    config_key="timeout_seconds",
                    default=_to_float(ingest.get("timeout_seconds"), 600.0),
                    coerce=_to_float,
                ),
                _SettingSpec(
                    field_name="pdf_text_ocr_cache_enabled",
                    config_key="cache_enabled",
                    default=_to_bool(
                        _default_config_value(
                            "ingest",
                            "pdf_text",
                            "ocr_fallback",
                            "cache_enabled",
                            fallback=True,
                        ),
                        True,
                    ),
                    coerce=_to_bool,
                ),
                _SettingSpec(
                    field_name="pdf_text_ocr_chunk_page_count",
                    config_key="chunk_page_count",
                    default=_to_int(
                        _default_config_value(
                            "ingest",
                            "pdf_text",
                            "ocr_fallback",
                            "chunk_page_count",
                            fallback=8,
                        ),
                        8,
                    ),
                    coerce=_to_int,
                    minimum=1,
                ),
            ],
        )
    )
    resolved["pdf_text_ocr_model"] = _to_str(
        ocr_fallback_cfg.get("model"),
        str(
            _default_config_value(
                "ingest", "pdf_text", "ocr_fallback", "model", fallback="gpt-5-mini"
            )
        ),
    )
    resolved["pdf_text_ocr_prompt_namespace"] = _to_str(
        ocr_fallback_cfg.get("prompt_namespace"),
        str(
            _default_config_value(
                "ingest",
                "pdf_text",
                "ocr_fallback",
                "prompt_namespace",
                fallback="pdf_text/ocr_fallback",
            )
        ),
    )
    return resolved


def _resolve_validation_settings(validation_cfg: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        validation_cfg,
        [
            _SettingSpec(
                field_name="validation_regeneration_max_attempts",
                config_key="regeneration_max_attempts",
                default=_to_int(
                    _default_config_value(
                        "ingest",
                        "validation",
                        "regeneration_max_attempts",
                        fallback=3,
                    ),
                    3,
                ),
                coerce=_to_int,
                env_key="VALIDATION_REGENERATION_MAX_ATTEMPTS",
                minimum=1,
            ),
        ],
    )
    resolved["validation_data_gap_policy"] = _resolve_allowed_string(
        validation_cfg.get(
            "data_gap_policy",
            _default_config_value(
                "ingest", "validation", "data_gap_policy", fallback="warn"
            ),
        ),
        default=str(
            _default_config_value(
                "ingest", "validation", "data_gap_policy", fallback="warn"
            )
        ),
        allowed={"warn", "fail"},
    )
    return resolved


def _resolve_analysis_settings(
    analysis_cfg: dict[str, Any],
    cost_cfg: dict[str, Any],
    *,
    html_tag_acronyms_path: str,
) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        analysis_cfg,
        [
            _SettingSpec(
                field_name="vector_store_keep",
                config_key="vector_store_keep",
                default=_to_config_bool(
                    _default_config_value(
                        "analysis", "vector_store_keep", fallback=True
                    ),
                    True,
                ),
                coerce=_to_config_bool,
                env_key="VECTOR_STORE_KEEP",
                env_first=True,
            ),
            _SettingSpec(
                field_name="artifacts_use_vector_store",
                config_key="artifacts_use_vector_store",
                default=_to_config_bool(
                    _default_config_value(
                        "analysis", "artifacts_use_vector_store", fallback=False
                    ),
                    False,
                ),
                coerce=_to_config_bool,
                env_key="ARTIFACTS_USE_VECTOR_STORE",
                env_first=True,
            ),
            _SettingSpec(
                field_name="validation_grounding_use_vector_store",
                config_key="validation_grounding_use_vector_store",
                default=_to_config_bool(
                    _default_config_value(
                        "analysis",
                        "validation_grounding_use_vector_store",
                        fallback=False,
                    ),
                    False,
                ),
                coerce=_to_config_bool,
                env_key="VALIDATION_GROUNDING_USE_VECTOR_STORE",
                env_first=True,
            ),
            _SettingSpec(
                field_name="strict_schema_validation",
                config_key="strict_schema_validation",
                default=_to_config_bool(
                    _default_config_value(
                        "analysis", "strict_schema_validation", fallback=True
                    ),
                    True,
                ),
                coerce=_to_config_bool,
                env_key="STRICT_SCHEMA_VALIDATION",
                env_first=True,
            ),
        ],
    )
    resolved["cost_ledger_path"] = str(
        _resolve_setting_raw(
            analysis_cfg,
            _SettingSpec(
                field_name="cost_ledger_path",
                config_key="cost_ledger_path",
                default=str(
                    _default_config_value(
                        "analysis",
                        "cost_ledger_path",
                        fallback="./out/cost-ledger.jsonl",
                    )
                ),
                coerce=_to_str,
                env_key="COST_LEDGER_PATH",
                env_first=True,
            ),
        )
        or str(
            _default_config_value(
                "analysis", "cost_ledger_path", fallback="./out/cost-ledger.jsonl"
            )
        )
    )
    resolved["cost_daily_path"] = str(
        cost_cfg.get("daily_path")
        or _default_config_value("cost", "daily_path", fallback="./out/cost-daily.json")
    )
    resolved["model_pricing"] = cost_cfg.get("pricing") or _default_config_value(
        "cost", "pricing", fallback={}
    )
    resolved["html_tag_acronyms"] = _load_html_tag_acronyms(html_tag_acronyms_path)
    return resolved


def _resolve_drive_settings(drive_cfg: dict[str, Any]) -> dict[str, Any]:
    drive_id_raw = drive_cfg.get("drive_id")
    return {
        "drive_supports_all_drives": _to_config_bool(
            drive_cfg.get("supports_all_drives"),
            _to_config_bool(
                _default_config_value(
                    "ingest", "drive", "supports_all_drives", fallback=True
                ),
                True,
            ),
        ),
        "drive_include_items_from_all_drives": _to_config_bool(
            drive_cfg.get("include_items_from_all_drives"),
            _to_config_bool(
                _default_config_value(
                    "ingest",
                    "drive",
                    "include_items_from_all_drives",
                    fallback=True,
                ),
                True,
            ),
        ),
        "drive_id": str(drive_id_raw).strip()
        if not _is_missing(drive_id_raw)
        else None,
        "drive_list_mode": _resolve_allowed_string(
            drive_cfg.get(
                "list_mode",
                _default_config_value(
                    "ingest", "drive", "list_mode", fallback="metadata"
                ),
            ),
            default=str(
                _default_config_value(
                    "ingest", "drive", "list_mode", fallback="metadata"
                )
            ),
            allowed={"full", "metadata"},
        ),
    }


def _resolve_drive_auth_settings(
    ingest: dict[str, Any],
    drive_cfg: dict[str, Any],
    *,
    runtime_base_path: Path,
    resolver: _ConfigResolver,
) -> dict[str, Any]:
    auth_mode = _resolve_allowed_string(
        drive_cfg.get("auth_mode")
        or _env_value("GOOGLE_DRIVE_AUTH_MODE")
        or _default_config_value(
            "ingest", "drive", "auth_mode", fallback="service_account"
        ),
        default=str(
            _default_config_value(
                "ingest", "drive", "auth_mode", fallback="service_account"
            )
        ),
        allowed={"service_account", "oauth_user"},
    )
    google_sa_path = _resolve_optional_path(
        ingest.get("google_sa_path") or _env_value("GOOGLE_SERVICE_ACCOUNT_JSON"),
        base_path=runtime_base_path,
    )
    oauth_client_path = _resolve_optional_path(
        drive_cfg.get("oauth_client_path") or _env_value("GOOGLE_OAUTH_CLIENT_JSON"),
        base_path=runtime_base_path,
    )
    oauth_token_path = _resolve_optional_path(
        drive_cfg.get("oauth_token_path") or _env_value("GOOGLE_OAUTH_TOKEN_JSON"),
        base_path=runtime_base_path,
    )
    if auth_mode == "service_account":
        if _is_missing(google_sa_path):
            resolver.missing.append(
                "ingest.google_sa_path|env:GOOGLE_SERVICE_ACCOUNT_JSON"
            )
        oauth_client_path = ""
        oauth_token_path = ""
    else:
        if _is_missing(oauth_client_path):
            resolver.missing.append(
                "ingest.drive.oauth_client_path|env:GOOGLE_OAUTH_CLIENT_JSON"
            )
        if _is_missing(oauth_token_path):
            resolver.missing.append(
                "ingest.drive.oauth_token_path|env:GOOGLE_OAUTH_TOKEN_JSON"
            )
        google_sa_path = ""
    return {
        "drive_auth_mode": auth_mode,
        "google_sa_path": google_sa_path,
        "google_oauth_client_path": oauth_client_path or None,
        "google_oauth_token_path": oauth_token_path or None,
    }


def _to_ingest_settings(app_settings: AppSettings) -> IngestSettings:
    payload = asdict(app_settings)
    allowed = {field.name for field in fields(IngestSettings)}
    filtered_payload = {key: value for key, value in payload.items() if key in allowed}
    return IngestSettings(**filtered_payload)


def build_ingest_settings(
    request: IngestSettingsBuildRequest, ctx: RunContext
) -> IngestSettings:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ingest_settings_build_start",
            module=logger.name,
            fields={
                "output_dir": request.app_settings.output_dir,
                "cache_dir": request.app_settings.cache_dir,
                "state_db": request.app_settings.state_db,
                "reports_db": request.app_settings.reports_db,
            },
        )
    )
    settings = _to_ingest_settings(request.app_settings)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ingest_settings_build_complete",
            module=logger.name,
            fields={
                "gdrive_folder_id": settings.gdrive_folder_id,
                "openai_model": settings.openai_model,
                "batch_limit": settings.batch_limit,
                "ingest_worker_limit": settings.ingest_worker_limit,
                "report_worker_limit": settings.report_worker_limit,
            },
        )
    )
    return settings


def _ensure_app_settings_directories(settings: AppSettings) -> None:
    _ensure_app_settings_directories(settings)


def _config_load_complete_fields(
    settings: AppSettings,
    *,
    paths_settings: dict[str, str],
) -> dict[str, Any]:
    return {
        "output_dir": settings.output_dir,
        "cache_dir": settings.cache_dir,
        "state_db": settings.state_db,
        "reports_db": settings.reports_db,
        "publisher_profiles_path": settings.publisher_profiles_path,
        "category_mapping_path": settings.category_mapping_path,
        "html_tag_acronyms_path": paths_settings["html_tag_acronyms_path"],
        "ingest_lock_path": settings.ingest_lock_path,
        "ingest_lock_ttl_seconds": settings.ingest_lock_ttl_seconds,
        "drive_supports_all_drives": settings.drive_supports_all_drives,
        "drive_include_items_from_all_drives": settings.drive_include_items_from_all_drives,
        "drive_id": settings.drive_id or "",
        "drive_list_mode": settings.drive_list_mode,
        "openai_model": settings.openai_model,
        "openai_models": settings.openai_models,
        "temperature": settings.temperature,
        "taxonomy_temperature": settings.taxonomy_temperature,
        "ingest_worker_limit": settings.ingest_worker_limit,
        "report_worker_limit": settings.report_worker_limit,
        "openai_seed": settings.openai_seed,
        "rank_model": settings.rank_model,
        "rank_temperature": settings.rank_temperature,
        "rank_seed": settings.rank_seed,
        "rank_max_candidates": settings.rank_max_candidates,
        "rank_selected_max": settings.rank_selected_max,
        "rank_min_overall_score": settings.rank_min_overall_score,
        "rank_min_quality_score": settings.rank_min_quality_score,
        "rank_min_insight_score": settings.rank_min_insight_score,
        "rank_min_data_score": settings.rank_min_data_score,
        "crop_refine_enabled": settings.crop_refine_enabled,
        "crop_refine_mode": settings.crop_refine_mode,
        "crop_refine_page_dpi": settings.crop_refine_page_dpi,
        "crop_refine_temperature": settings.crop_refine_temperature,
        "crop_refine_timeout_seconds": settings.crop_refine_timeout_seconds,
        "figure_caption_enabled": settings.figure_caption_enabled,
        "figure_caption_temperature": settings.figure_caption_temperature,
        "figure_caption_timeout_seconds": settings.figure_caption_timeout_seconds,
        "figure_caption_prompt_namespace": settings.figure_caption_prompt_namespace,
        "figure_caption_max_chars": settings.figure_caption_max_chars,
        "pdf_text_max_pages": settings.pdf_text_max_pages,
        "pdf_text_max_chars": settings.pdf_text_max_chars,
        "pdf_text_min_density": settings.pdf_text_min_density,
        "pdf_text_sample_pages": settings.pdf_text_sample_pages,
        "pdf_text_ocr_enabled": settings.pdf_text_ocr_enabled,
        "pdf_text_ocr_model": settings.pdf_text_ocr_model,
        "pdf_text_ocr_timeout_seconds": settings.pdf_text_ocr_timeout_seconds,
        "pdf_text_ocr_prompt_namespace": settings.pdf_text_ocr_prompt_namespace,
        "pdf_text_ocr_cache_enabled": settings.pdf_text_ocr_cache_enabled,
        "pdf_text_ocr_chunk_page_count": settings.pdf_text_ocr_chunk_page_count,
        "openai_timeout_seconds": settings.openai_timeout_seconds,
        "llm_retry_retries": settings.llm_retry_retries,
        "llm_retry_base_delay_seconds": settings.llm_retry_base_delay_seconds,
        "llm_retry_backoff_step_seconds": settings.llm_retry_backoff_step_seconds,
        "llm_retry_jitter_seconds": settings.llm_retry_jitter_seconds,
        "llm_circuit_breaker_failure_threshold": settings.llm_circuit_breaker_failure_threshold,
        "llm_circuit_breaker_recovery_seconds": settings.llm_circuit_breaker_recovery_seconds,
        "rank_timeout_seconds": settings.rank_timeout_seconds,
        "contents_max_pages": settings.contents_max_pages,
        "contents_min_headings": settings.contents_min_headings,
        "contents_keywords": settings.contents_keywords,
        "contents_preview_enabled": settings.contents_preview_enabled,
        "contents_preview_dpi": settings.contents_preview_dpi,
        "evidence_pack_parallel_workers": settings.evidence_pack_parallel_workers,
        "evidence_pack_global_max_in_flight": settings.evidence_pack_global_max_in_flight,
        "evidence_pack_global_min_interval_ms": settings.evidence_pack_global_min_interval_ms,
        "evidence_pack_doc_map_max_attempts": settings.evidence_pack_doc_map_max_attempts,
        "evidence_pack_doc_map_retry_delay_ms": settings.evidence_pack_doc_map_retry_delay_ms,
        "evidence_pack_registry": settings.evidence_pack_registry,
        "evidence_pack_enable_new_variety_packs": settings.evidence_pack_enable_new_variety_packs,
        "artifact_parallel_workers": settings.artifact_parallel_workers,
        "artifact_global_max_in_flight": settings.artifact_global_max_in_flight,
        "artifact_global_min_interval_ms": settings.artifact_global_min_interval_ms,
        "vector_store_keep": settings.vector_store_keep,
        "artifacts_use_vector_store": settings.artifacts_use_vector_store,
        "validation_grounding_use_vector_store": settings.validation_grounding_use_vector_store,
        "strict_schema_validation": settings.strict_schema_validation,
        "cover_cache_enabled": settings.cover_cache_enabled,
        "cost_ledger_path": settings.cost_ledger_path,
        "cost_daily_path": settings.cost_daily_path,
        "html_tag_acronyms": settings.html_tag_acronyms,
        "html_tag_acronyms_count": len(settings.html_tag_acronyms),
        "validation_data_gap_policy": settings.validation_data_gap_policy,
        "validation_regeneration_max_attempts": settings.validation_regeneration_max_attempts,
    }


def load_settings(request: ConfigLoadRequest, ctx: RunContext) -> AppSettings:
    load_dotenv(find_dotenv(filename=".env", usecwd=True))

    logger.info(
        log_event(
            ctx,
            role="service",
            event="config_load_start",
            module=logger.name,
            fields={"path": request.path or str(CONFIG_PATH)},
        )
    )
    sections = _load_config_sections(request)
    resolver = sections.resolver
    need = resolver.need
    need_env = resolver.need_env

    paths_settings = _resolve_paths_settings(sections.paths, resolver)
    openai_model = str(
        sections.ingest.get("openai_model")
        or _env_value("OPENAI_MODEL")
        or _default_config_value("ingest", "openai_model", fallback="")
    ).strip()
    if not openai_model:
        resolver.missing.append("ingest.openai_model|env:OPENAI_MODEL")
    ingest_runtime = _resolve_ingest_runtime_settings(sections.ingest)
    llm_runtime = _resolve_llm_runtime_settings(sections.llm_cfg)
    rank_settings = _resolve_rank_settings(
        sections.rank,
        openai_model=openai_model,
        temperature=ingest_runtime["temperature"],
        openai_timeout_seconds=ingest_runtime["openai_timeout_seconds"],
    )
    figure_caption_settings = _resolve_figure_caption_settings(
        sections.figure_captions_cfg,
        openai_timeout_seconds=ingest_runtime["openai_timeout_seconds"],
    )
    contents_settings = _resolve_contents_settings(sections.contents_page)
    evidence_pack_settings = _resolve_evidence_pack_settings(
        sections.evidence_packs_cfg
    )
    artifact_settings = _resolve_artifact_settings(sections.artifacts_cfg)
    pdf_text_settings = _resolve_pdf_text_settings(
        sections.pdf_text,
        sections.ingest,
    )
    validation_settings = _resolve_validation_settings(sections.validation_cfg)
    analysis_settings = _resolve_analysis_settings(
        sections.analysis_cfg,
        sections.cost_cfg,
        html_tag_acronyms_path=paths_settings["html_tag_acronyms_path"],
    )
    drive_settings = _resolve_drive_settings(sections.drive_cfg)
    drive_auth_settings = _resolve_drive_auth_settings(
        sections.ingest,
        sections.drive_cfg,
        runtime_base_path=sections.runtime_base_path,
        resolver=resolver,
    )

    settings = AppSettings(
        schema_version=str(sections.data.get("schema_version", "1.0")),
        google_sa_path=drive_auth_settings["google_sa_path"],
        gdrive_folder_id=need(
            sections.ingest,
            "gdrive_folder_id",
            "ingest.gdrive_folder_id",
            "GDRIVE_FOLDER_ID",
        ),
        drive_auth_mode=drive_auth_settings["drive_auth_mode"],
        google_oauth_client_path=drive_auth_settings["google_oauth_client_path"],
        google_oauth_token_path=drive_auth_settings["google_oauth_token_path"],
        drive_supports_all_drives=drive_settings["drive_supports_all_drives"],
        drive_include_items_from_all_drives=drive_settings[
            "drive_include_items_from_all_drives"
        ],
        drive_id=drive_settings["drive_id"],
        drive_list_mode=drive_settings["drive_list_mode"],
        openai_api_key=need_env("OPENAI_API_KEY"),
        openai_model=openai_model,
        openai_models=_normalize_openai_models(
            sections.data.get("openai_models")
            or _default_config_value("openai_models", fallback={})
        ),
        batch_limit=ingest_runtime["batch_limit"],
        ingest_worker_limit=ingest_runtime["ingest_worker_limit"],
        report_worker_limit=ingest_runtime["report_worker_limit"],
        output_dir=paths_settings["output_dir"],
        cache_dir=paths_settings["cache_dir"],
        state_db=paths_settings["state_db"],
        reports_db=paths_settings["reports_db"],
        publisher_profiles_path=paths_settings["publisher_profiles_path"],
        category_mapping_path=paths_settings["category_mapping_path"],
        cover_style_path=paths_settings["cover_style_path"],
        ingest_lock_path=paths_settings["ingest_lock_path"],
        ingest_lock_ttl_seconds=ingest_runtime["ingest_lock_ttl_seconds"],
        temperature=ingest_runtime["temperature"],
        taxonomy_temperature=ingest_runtime["taxonomy_temperature"],
        openai_seed=ingest_runtime["openai_seed"],
        pdf_text_max_pages=pdf_text_settings["pdf_text_max_pages"],
        pdf_text_max_chars=pdf_text_settings["pdf_text_max_chars"],
        pdf_text_min_density=pdf_text_settings["pdf_text_min_density"],
        pdf_text_sample_pages=pdf_text_settings["pdf_text_sample_pages"],
        pdf_text_ocr_enabled=pdf_text_settings["pdf_text_ocr_enabled"],
        pdf_text_ocr_model=pdf_text_settings["pdf_text_ocr_model"],
        pdf_text_ocr_timeout_seconds=pdf_text_settings["pdf_text_ocr_timeout_seconds"],
        pdf_text_ocr_prompt_namespace=pdf_text_settings[
            "pdf_text_ocr_prompt_namespace"
        ],
        pdf_text_ocr_cache_enabled=pdf_text_settings["pdf_text_ocr_cache_enabled"],
        pdf_text_ocr_chunk_page_count=pdf_text_settings[
            "pdf_text_ocr_chunk_page_count"
        ],
        rank_model=rank_settings["rank_model"],
        rank_temperature=rank_settings["rank_temperature"],
        rank_seed=rank_settings["rank_seed"],
        rank_max_candidates=rank_settings["rank_max_candidates"],
        rank_selected_max=rank_settings["rank_selected_max"],
        rank_min_overall_score=rank_settings["rank_min_overall_score"],
        rank_min_quality_score=rank_settings["rank_min_quality_score"],
        rank_min_insight_score=rank_settings["rank_min_insight_score"],
        rank_min_data_score=rank_settings["rank_min_data_score"],
        crop_refine_enabled=rank_settings["crop_refine_enabled"],
        crop_refine_mode=rank_settings["crop_refine_mode"],
        crop_refine_page_dpi=rank_settings["crop_refine_page_dpi"],
        crop_refine_temperature=rank_settings["crop_refine_temperature"],
        crop_refine_timeout_seconds=rank_settings["crop_refine_timeout_seconds"],
        figure_caption_enabled=figure_caption_settings["figure_caption_enabled"],
        figure_caption_temperature=figure_caption_settings[
            "figure_caption_temperature"
        ],
        figure_caption_timeout_seconds=figure_caption_settings[
            "figure_caption_timeout_seconds"
        ],
        figure_caption_prompt_namespace=figure_caption_settings[
            "figure_caption_prompt_namespace"
        ],
        figure_caption_max_chars=figure_caption_settings["figure_caption_max_chars"],
        openai_timeout_seconds=ingest_runtime["openai_timeout_seconds"],
        llm_retry_retries=llm_runtime["llm_retry_retries"],
        llm_retry_base_delay_seconds=llm_runtime["llm_retry_base_delay_seconds"],
        llm_retry_backoff_step_seconds=llm_runtime["llm_retry_backoff_step_seconds"],
        llm_retry_jitter_seconds=llm_runtime["llm_retry_jitter_seconds"],
        llm_circuit_breaker_failure_threshold=llm_runtime[
            "llm_circuit_breaker_failure_threshold"
        ],
        llm_circuit_breaker_recovery_seconds=llm_runtime[
            "llm_circuit_breaker_recovery_seconds"
        ],
        rank_timeout_seconds=rank_settings["rank_timeout_seconds"],
        contents_max_pages=contents_settings["contents_max_pages"],
        contents_min_headings=contents_settings["contents_min_headings"],
        contents_keywords=contents_settings["contents_keywords"],
        contents_preview_enabled=contents_settings["contents_preview_enabled"],
        contents_preview_dpi=contents_settings["contents_preview_dpi"],
        evidence_pack_parallel_workers=evidence_pack_settings[
            "evidence_pack_parallel_workers"
        ],
        evidence_pack_global_max_in_flight=evidence_pack_settings[
            "evidence_pack_global_max_in_flight"
        ],
        evidence_pack_global_min_interval_ms=evidence_pack_settings[
            "evidence_pack_global_min_interval_ms"
        ],
        evidence_pack_doc_map_max_attempts=evidence_pack_settings[
            "evidence_pack_doc_map_max_attempts"
        ],
        evidence_pack_doc_map_retry_delay_ms=evidence_pack_settings[
            "evidence_pack_doc_map_retry_delay_ms"
        ],
        evidence_pack_registry=evidence_pack_settings["evidence_pack_registry"],
        evidence_pack_enable_new_variety_packs=evidence_pack_settings[
            "evidence_pack_enable_new_variety_packs"
        ],
        artifact_parallel_workers=artifact_settings["artifact_parallel_workers"],
        artifact_global_max_in_flight=artifact_settings[
            "artifact_global_max_in_flight"
        ],
        artifact_global_min_interval_ms=artifact_settings[
            "artifact_global_min_interval_ms"
        ],
        vector_store_keep=analysis_settings["vector_store_keep"],
        artifacts_use_vector_store=analysis_settings["artifacts_use_vector_store"],
        validation_grounding_use_vector_store=analysis_settings[
            "validation_grounding_use_vector_store"
        ],
        strict_schema_validation=analysis_settings["strict_schema_validation"],
        cover_cache_enabled=ingest_runtime["cover_cache_enabled"],
        cost_ledger_path=analysis_settings["cost_ledger_path"],
        cost_daily_path=analysis_settings["cost_daily_path"],
        model_pricing=analysis_settings["model_pricing"],
        html_tag_acronyms=analysis_settings["html_tag_acronyms"],
        validation_data_gap_policy=validation_settings["validation_data_gap_policy"],
        validation_regeneration_max_attempts=validation_settings[
            "validation_regeneration_max_attempts"
        ],
    )

    if resolver.missing:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="config_load_failed",
                module=logger.name,
                fields={"missing": resolver.missing},
            )
        )
        raise RuntimeError(
            f"Missing required config/env values: {', '.join(resolver.missing)}"
        )
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.state_db).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.reports_db).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.ingest_lock_path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.cost_ledger_path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.cost_daily_path).parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="config_load_complete",
            module=logger.name,
            fields=_config_load_complete_fields(
                settings,
                paths_settings=paths_settings,
            ),
        )
    )
    return settings


def _normalize_site_url(site_url: str) -> str:
    return site_url.rstrip("/")


def _site_url_from_admin(admin_url: str) -> str:
    url = admin_url.rstrip("/")
    if url.endswith("/wp-admin"):
        url = url[: -len("/wp-admin")]
    return _normalize_site_url(url)


def load_publish_settings(
    request: ConfigLoadRequest, ctx: RunContext
) -> PublishSettings:
    load_dotenv(find_dotenv(filename=".env", usecwd=True))
    config_path = _resolve_bootstrap_config_path(request.path)

    logger.info(
        log_event(
            ctx,
            role="service",
            event="publish_config_load_start",
            module=logger.name,
            fields={"path": str(config_path)},
        )
    )
    data = _load_config(str(config_path))
    resolver = _ConfigResolver()
    need = resolver.need
    missing = resolver.missing

    paths = data.get("paths", {}) or {}
    publish = data.get("publish", {}) or {}
    wp_cfg = publish.get("wp", {}) or {}
    validation_cfg = publish.get("validation", {}) or {}
    category_mapping_path = paths.get("category_mappings") or str(
        Path(__file__).resolve().parents[1] / "config" / "category-mappings.yaml"
    )

    output_dir = need(paths, "output_dir", "paths.output_dir", "OUTPUT_DIR")
    state_db = need(paths, "state_db", "paths.state_db", "STATE_DB")
    reports_db = need(paths, "reports_db", "paths.reports_db", "REPORTS_DB")

    admin_url = wp_cfg.get("admin_url") or _env_value("WP_ADMIN_URL")
    site_url = wp_cfg.get("site_url") or _env_value("WP_SITE_URL")
    if not site_url and admin_url:
        site_url = _site_url_from_admin(admin_url)
    if _is_missing(site_url):
        missing.append("publish.wp.site_url|env:WP_SITE_URL|env:WP_ADMIN_URL")
    site_url = site_url or ""

    app_password = os.getenv("WP_APP_PASSWORD", "")
    bearer_token = os.getenv("WP_BEARER_TOKEN", "")
    if not app_password and not bearer_token:
        missing.append("env:WP_APP_PASSWORD|WP_BEARER_TOKEN")

    ssl_verify_raw = wp_cfg.get("ssl_verify")
    if _is_missing(ssl_verify_raw):
        ssl_verify_raw = _env_value("WP_SSL_VERIFY")
    ssl_verify = _to_bool(ssl_verify_raw, True)

    ca_bundle_path_raw = wp_cfg.get("ca_bundle_path")
    if _is_missing(ca_bundle_path_raw):
        ca_bundle_path_raw = _env_value("WP_CA_BUNDLE_PATH")
    ca_bundle_path = _resolve_optional_path(
        ca_bundle_path_raw,
        base_path=config_path.parent,
    )
    if ssl_verify and ca_bundle_path and not Path(ca_bundle_path).exists():
        missing.append("publish.wp.ca_bundle_path|env:WP_CA_BUNDLE_PATH")

    wp = WordPressAuthSettings(
        schema_version="1.0",
        site_url=_normalize_site_url(site_url),
        username=need(wp_cfg, "username", "publish.wp.username", "WP_USERNAME"),
        app_password=app_password or None,
        bearer_token=bearer_token or None,
        post_status=wp_cfg.get("post_status")
        or _env_value("WP_POST_STATUS")
        or _default_config_value("publish", "wp", "post_status", fallback="publish"),
        post_type=(
            str(
                wp_cfg.get("post_type")
                or _env_value("WP_POST_TYPE")
                or _default_config_value(
                    "publish", "wp", "post_type", fallback="ml_report"
                )
            )
            .strip()
            .strip("/")
            or str(
                _default_config_value(
                    "publish", "wp", "post_type", fallback="ml_report"
                )
            )
        ),
        ssl_verify=ssl_verify,
        ca_bundle_path=ca_bundle_path or None,
    )

    validation_policy_raw = (
        validation_cfg.get("policy")
        or _env_value("PUBLISH_VALIDATION_POLICY")
        or _default_config_value("publish", "validation", "policy", fallback="block")
    )
    validation_policy = str(validation_policy_raw).strip().lower()
    if validation_policy not in {"block", "warn"}:
        validation_policy = "block"

    if resolver.missing:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publish_config_load_failed",
                module=logger.name,
                fields={"missing": resolver.missing},
            )
        )
        raise RuntimeError(
            f"Missing required config/env values: {', '.join(resolver.missing)}"
        )

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(state_db).parent.mkdir(parents=True, exist_ok=True)

    settings = PublishSettings(
        schema_version=str(data.get("schema_version", "1.0")),
        output_dir=output_dir,
        state_db=state_db,
        reports_db=reports_db,
        category_mapping_path=category_mapping_path,
        validation_policy=validation_policy,
        wp=wp,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publish_config_load_complete",
            module=logger.name,
            fields={
                "output_dir": settings.output_dir,
                "state_db": settings.state_db,
                "reports_db": settings.reports_db,
                "site_url": settings.wp.site_url,
                "username": settings.wp.username,
                "post_status": settings.wp.post_status,
                "post_type": settings.wp.post_type,
                "ssl_verify": settings.wp.ssl_verify,
                "ca_bundle_path": settings.wp.ca_bundle_path or "",
                "validation_policy": settings.validation_policy,
            },
        )
    )
    return settings


def load_browser_download_settings(
    request: ConfigLoadRequest, ctx: RunContext
) -> BrowserDownloadSettings:
    load_dotenv(find_dotenv(filename=".env", usecwd=True))
    config_path = _resolve_bootstrap_config_path(request.path)

    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_download_config_load_start",
            module=logger.name,
            fields={"path": str(config_path)},
        )
    )
    data = _load_config(str(config_path))
    runtime_base_path = _resolve_runtime_base_path(config_path)
    resolver = _ConfigResolver()

    paths = data.get("paths", {}) or {}
    ingest = data.get("ingest", {}) or {}
    drive_cfg = ingest.get("drive", {}) or {}
    browser_download = data.get("browser_download", {}) or {}
    drive_upload_cfg = browser_download.get("drive_upload", {}) or {}
    retry_cfg = browser_download.get("retry", {}) or {}
    drive_upload_enabled = _to_bool(
        drive_upload_cfg.get("enabled")
        if not _is_missing(drive_upload_cfg.get("enabled"))
        else _env_value("BROWSER_DOWNLOAD_DRIVE_UPLOAD_ENABLED"),
        _to_bool(
            _default_config_value(
                "browser_download", "drive_upload", "enabled", fallback=True
            ),
            True,
        ),
    )
    drive_upload_required = _to_bool(
        drive_upload_cfg.get("required")
        if not _is_missing(drive_upload_cfg.get("required"))
        else _env_value("BROWSER_DOWNLOAD_DRIVE_UPLOAD_REQUIRED"),
        _to_bool(
            _default_config_value(
                "browser_download", "drive_upload", "required", fallback=True
            ),
            True,
        ),
    )

    output_root = (
        browser_download.get("output_dir")
        or _env_value("BROWSER_DOWNLOAD_OUTPUT_DIR")
        or str(Path(paths.get("output_dir") or "./out") / "browser_downloads")
    )
    output_dir = _resolve_optional_path(output_root, base_path=runtime_base_path)
    if _is_missing(output_dir):
        resolver.missing.append(
            "browser_download.output_dir|env:BROWSER_DOWNLOAD_OUTPUT_DIR"
        )
    state_db = _resolve_optional_path(
        paths.get("state_db") or _env_value("STATE_DB"),
        base_path=runtime_base_path,
    )
    if _is_missing(state_db):
        resolver.missing.append("paths.state_db|env:STATE_DB")
    reports_db = _resolve_optional_path(
        paths.get("reports_db") or _env_value("REPORTS_DB"),
        base_path=runtime_base_path,
    )
    if _is_missing(reports_db):
        resolver.missing.append("paths.reports_db|env:REPORTS_DB")
    identity_config_path = _resolve_optional_path(
        browser_download.get("identity_config_path")
        or _env_value("BROWSER_DOWNLOAD_IDENTITY_CONFIG_PATH")
        or DEFAULT_BROWSER_DOWNLOAD_IDENTITY_PATH.name,
        base_path=config_path.parent,
    )
    if _is_missing(identity_config_path):
        resolver.missing.append(
            "browser_download.identity_config_path|env:BROWSER_DOWNLOAD_IDENTITY_CONFIG_PATH"
        )
    drive_auth_settings: dict[str, str | None] = {
        "drive_auth_mode": "service_account",
        "google_sa_path": "",
        "google_oauth_client_path": None,
        "google_oauth_token_path": None,
    }
    drive_settings = _resolve_drive_settings(drive_cfg)
    if drive_upload_enabled:
        drive_auth_settings = _resolve_drive_auth_settings(
            ingest,
            drive_cfg,
            runtime_base_path=runtime_base_path,
            resolver=resolver,
        )

    api_key = _env_value("OPENROUTER_API_KEY")
    if _is_missing(api_key):
        resolver.missing.append("env:OPENROUTER_API_KEY")

    http_referer: str | None = _env_value("OPENROUTER_HTTP_REFERER")
    if _is_missing(http_referer):
        http_referer = None

    model = str(
        browser_download.get("model")
        or _env_value("BROWSER_DOWNLOAD_MODEL")
        or _default_config_value(
            "browser_download", "model", fallback="openai/gpt-5-mini"
        )
    ).strip()
    if not model:
        resolver.missing.append("browser_download.model|env:BROWSER_DOWNLOAD_MODEL")

    if resolver.missing:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_download_config_load_failed",
                module=logger.name,
                fields={"missing": resolver.missing},
            )
        )
        raise RuntimeError(
            f"Missing required config/env values: {', '.join(resolver.missing)}"
        )

    identity_profile = _load_browser_download_identity(
        identity_config_path,
        load_yaml_mapping=_load_yaml_mapping,
        is_missing=_is_missing,
    )

    settings = BrowserDownloadSettings(
        schema_version=str(data.get("schema_version", "1.0")),
        openrouter_api_key=api_key,
        model=model,
        temperature=_to_float(
            browser_download.get("temperature")
            if not _is_missing(browser_download.get("temperature"))
            else _env_value("BROWSER_DOWNLOAD_TEMPERATURE"),
            _to_float(
                _default_config_value("browser_download", "temperature", fallback=0.0),
                0.0,
            ),
        ),
        timeout_seconds=max(
            _to_float(
                browser_download.get("timeout_seconds")
                if not _is_missing(browser_download.get("timeout_seconds"))
                else _env_value("BROWSER_DOWNLOAD_TIMEOUT_SECONDS"),
                _to_float(
                    _default_config_value(
                        "browser_download", "timeout_seconds", fallback=180.0
                    ),
                    180.0,
                ),
            ),
            1.0,
        ),
        max_steps=max(
            _to_int(
                browser_download.get("max_steps")
                if not _is_missing(browser_download.get("max_steps"))
                else _env_value("BROWSER_DOWNLOAD_MAX_STEPS"),
                _to_int(
                    _default_config_value("browser_download", "max_steps", fallback=30),
                    30,
                ),
            ),
            1,
        ),
        output_dir=output_dir,
        state_db=state_db,
        reports_db=reports_db,
        identity_config_path=identity_config_path,
        identity_profile=identity_profile,
        openrouter_http_referer=http_referer,
        headed=_to_bool(
            browser_download.get("headed")
            if not _is_missing(browser_download.get("headed"))
            else _env_value("BROWSER_DOWNLOAD_HEADED"),
            _to_bool(
                _default_config_value("browser_download", "headed", fallback=False),
                False,
            ),
        ),
        retry_retries=max(
            _to_int(
                retry_cfg.get("retries")
                if not _is_missing(retry_cfg.get("retries"))
                else _env_value("BROWSER_DOWNLOAD_RETRIES"),
                _to_int(
                    _default_config_value(
                        "browser_download", "retry", "retries", fallback=1
                    ),
                    1,
                ),
            ),
            0,
        ),
        retry_base_delay_seconds=max(
            _to_float(
                retry_cfg.get("base_delay_seconds")
                if not _is_missing(retry_cfg.get("base_delay_seconds"))
                else _env_value("BROWSER_DOWNLOAD_BASE_DELAY_SECONDS"),
                _to_float(
                    _default_config_value(
                        "browser_download",
                        "retry",
                        "base_delay_seconds",
                        fallback=1.0,
                    ),
                    1.0,
                ),
            ),
            0.0,
        ),
        retry_backoff_step_seconds=max(
            _to_float(
                retry_cfg.get("backoff_step_seconds")
                if not _is_missing(retry_cfg.get("backoff_step_seconds"))
                else _env_value("BROWSER_DOWNLOAD_BACKOFF_STEP_SECONDS"),
                _to_float(
                    _default_config_value(
                        "browser_download",
                        "retry",
                        "backoff_step_seconds",
                        fallback=1.0,
                    ),
                    1.0,
                ),
            ),
            0.0,
        ),
        retry_jitter_seconds=max(
            _to_float(
                retry_cfg.get("jitter_seconds")
                if not _is_missing(retry_cfg.get("jitter_seconds"))
                else _env_value("BROWSER_DOWNLOAD_JITTER_SECONDS"),
                _to_float(
                    _default_config_value(
                        "browser_download", "retry", "jitter_seconds", fallback=0.25
                    ),
                    0.25,
                ),
            ),
            0.0,
        ),
        drive_upload_enabled=drive_upload_enabled,
        drive_upload_required=drive_upload_required,
        drive_upload_google_sa_path=str(drive_auth_settings["google_sa_path"] or ""),
        drive_upload_auth_mode=str(
            drive_auth_settings["drive_auth_mode"] or "service_account"
        ),
        drive_upload_oauth_client_path=drive_auth_settings["google_oauth_client_path"],
        drive_upload_oauth_token_path=drive_auth_settings["google_oauth_token_path"],
        drive_upload_supports_all_drives=drive_settings["drive_supports_all_drives"],
        drive_upload_include_items_from_all_drives=drive_settings[
            "drive_include_items_from_all_drives"
        ],
        drive_upload_drive_id=drive_settings["drive_id"],
    )

    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.state_db).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.reports_db).parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_download_config_load_complete",
            module=logger.name,
            fields={
                "output_dir": settings.output_dir,
                "state_db": settings.state_db,
                "reports_db": settings.reports_db,
                "identity_config_path": settings.identity_config_path,
                "identity_field_count": len(settings.identity_profile.fields),
                "model": settings.model,
                "temperature": settings.temperature,
                "timeout_seconds": settings.timeout_seconds,
                "max_steps": settings.max_steps,
                "headed": settings.headed,
                "retry_retries": settings.retry_retries,
                "retry_base_delay_seconds": settings.retry_base_delay_seconds,
                "retry_backoff_step_seconds": settings.retry_backoff_step_seconds,
                "retry_jitter_seconds": settings.retry_jitter_seconds,
                "drive_upload_enabled": settings.drive_upload_enabled,
                "drive_upload_required": settings.drive_upload_required,
                "drive_upload_auth_mode": settings.drive_upload_auth_mode,
            },
        )
    )
    return settings


def load_publisher_inventory_settings(
    request: ConfigLoadRequest, ctx: RunContext
) -> PublisherInventorySettings:
    load_dotenv(find_dotenv(filename=".env", usecwd=True))
    config_path = _resolve_bootstrap_config_path(request.path)

    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_config_load_start",
            module=logger.name,
            fields={"path": str(config_path)},
        )
    )
    data = _load_config(str(config_path))
    runtime_base_path = _resolve_runtime_base_path(config_path)
    resolver = _ConfigResolver()

    paths = data.get("paths", {}) or {}
    ingest = data.get("ingest", {}) or {}
    drive_cfg = ingest.get("drive", {}) or {}
    llm_cfg = ingest.get("llm", {}) or {}
    browser_download = data.get("browser_download", {}) or {}
    browser_retry_cfg = browser_download.get("retry", {}) or {}
    publisher_discovery = data.get("publisher_discovery", {}) or {}
    candidate_screening_cfg = publisher_discovery.get("candidate_screening", {}) or {}
    candidate_quality_cfg = publisher_discovery.get("candidate_quality_check", {}) or {}
    analysis_cfg = data.get("analysis", {}) or {}
    cost_cfg = data.get("cost", {}) or {}
    retry_cfg = publisher_discovery.get("retry", {}) or browser_retry_cfg

    browser_output_root = (
        browser_download.get("output_dir")
        or _env_value("BROWSER_DOWNLOAD_OUTPUT_DIR")
        or str(Path(paths.get("output_dir") or "./out") / "browser_downloads")
    )
    output_root = (
        publisher_discovery.get("output_dir")
        or _env_value("PUBLISHER_DISCOVERY_OUTPUT_DIR")
        or browser_output_root
    )
    output_dir = _resolve_optional_path(output_root, base_path=runtime_base_path)
    if _is_missing(output_dir):
        resolver.missing.append(
            "publisher_discovery.output_dir|env:PUBLISHER_DISCOVERY_OUTPUT_DIR"
        )

    reports_db = _resolve_optional_path(
        paths.get("reports_db") or _env_value("REPORTS_DB"),
        base_path=runtime_base_path,
    )
    if _is_missing(reports_db):
        resolver.missing.append("paths.reports_db|env:REPORTS_DB")

    drive_auth_settings = _resolve_drive_auth_settings(
        ingest,
        drive_cfg,
        runtime_base_path=runtime_base_path,
        resolver=resolver,
    )
    llm_runtime = _resolve_llm_runtime_settings(llm_cfg)
    paths_settings = _resolve_paths_settings(paths, resolver)
    analysis_settings = _resolve_analysis_settings(
        analysis_cfg,
        cost_cfg,
        html_tag_acronyms_path=paths_settings["html_tag_acronyms_path"],
    )

    api_key = _env_value("OPENROUTER_API_KEY")
    if _is_missing(api_key):
        resolver.missing.append("env:OPENROUTER_API_KEY")

    http_referer: str | None = _env_value("OPENROUTER_HTTP_REFERER")
    if _is_missing(http_referer):
        http_referer = None

    model = str(
        publisher_discovery.get("model")
        or _env_value("PUBLISHER_DISCOVERY_MODEL")
        or browser_download.get("model")
        or _env_value("BROWSER_DOWNLOAD_MODEL")
        or _default_config_value(
            "publisher_discovery",
            "model",
            fallback=_default_config_value(
                "browser_download", "model", fallback="openai/gpt-5-mini"
            ),
        )
    ).strip()
    if not model:
        resolver.missing.append(
            "publisher_discovery.model|env:PUBLISHER_DISCOVERY_MODEL"
        )

    candidate_screening_enabled = _to_bool(
        candidate_screening_cfg.get("enabled")
        if not _is_missing(candidate_screening_cfg.get("enabled"))
        else _env_value("PUBLISHER_DISCOVERY_CANDIDATE_SCREENING_ENABLED"),
        _to_bool(
            _default_config_value(
                "publisher_discovery",
                "candidate_screening",
                "enabled",
                fallback=True,
            ),
            True,
        ),
    )
    openai_api_key = _env_value("OPENAI_API_KEY")
    if candidate_screening_enabled and _is_missing(openai_api_key):
        resolver.missing.append("env:OPENAI_API_KEY")

    if resolver.missing:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_config_load_failed",
                module=logger.name,
                fields={"missing": resolver.missing},
            )
        )
        raise RuntimeError(
            f"Missing required config/env values: {', '.join(resolver.missing)}"
        )

    settings = PublisherInventorySettings(
        schema_version=str(data.get("schema_version", "1.0")),
        openrouter_api_key=api_key,
        model=model,
        temperature=_to_float(
            publisher_discovery.get("temperature")
            if not _is_missing(publisher_discovery.get("temperature"))
            else (
                _env_value("PUBLISHER_DISCOVERY_TEMPERATURE")
                or browser_download.get("temperature")
                or _env_value("BROWSER_DOWNLOAD_TEMPERATURE")
            ),
            _to_float(
                _default_config_value(
                    "publisher_discovery", "temperature", fallback=0.0
                ),
                0.0,
            ),
        ),
        timeout_seconds=max(
            _to_float(
                publisher_discovery.get("timeout_seconds")
                if not _is_missing(publisher_discovery.get("timeout_seconds"))
                else (
                    _env_value("PUBLISHER_DISCOVERY_TIMEOUT_SECONDS")
                    or browser_download.get("timeout_seconds")
                    or _env_value("BROWSER_DOWNLOAD_TIMEOUT_SECONDS")
                ),
                _to_float(
                    _default_config_value(
                        "publisher_discovery", "timeout_seconds", fallback=360.0
                    ),
                    360.0,
                ),
            ),
            1.0,
        ),
        max_steps=max(
            _to_int(
                publisher_discovery.get("max_steps")
                if not _is_missing(publisher_discovery.get("max_steps"))
                else (
                    _env_value("PUBLISHER_DISCOVERY_MAX_STEPS")
                    or browser_download.get("max_steps")
                    or _env_value("BROWSER_DOWNLOAD_MAX_STEPS")
                ),
                _to_int(
                    _default_config_value(
                        "publisher_discovery", "max_steps", fallback=30
                    ),
                    30,
                ),
            ),
            1,
        ),
        output_dir=output_dir,
        reports_db=reports_db,
        google_sa_path=drive_auth_settings["google_sa_path"],
        prompt_namespace=str(
            publisher_discovery.get("prompt_namespace")
            or _env_value("PUBLISHER_DISCOVERY_PROMPT_NAMESPACE")
            or _default_config_value(
                "publisher_discovery",
                "prompt_namespace",
                fallback=DEFAULT_PUBLISHER_INVENTORY_PROMPT_NAMESPACE,
            )
        ).strip(),
        pagination_max_pages=max(
            _to_int(
                publisher_discovery.get("pagination_max_pages")
                if not _is_missing(publisher_discovery.get("pagination_max_pages"))
                else _env_value("PUBLISHER_DISCOVERY_PAGINATION_MAX_PAGES"),
                _to_int(
                    _default_config_value(
                        "publisher_discovery", "pagination_max_pages", fallback=75
                    ),
                    75,
                ),
            ),
            1,
        ),
        http_timeout_seconds=max(
            _to_float(
                publisher_discovery.get("http_timeout_seconds")
                if not _is_missing(publisher_discovery.get("http_timeout_seconds"))
                else _env_value("PUBLISHER_DISCOVERY_HTTP_TIMEOUT_SECONDS"),
                _to_float(
                    _default_config_value(
                        "publisher_discovery", "http_timeout_seconds", fallback=30.0
                    ),
                    30.0,
                ),
            ),
            1.0,
        ),
        command_time_budget_seconds=max(
            _to_float(
                publisher_discovery.get("command_time_budget_seconds")
                if not _is_missing(
                    publisher_discovery.get("command_time_budget_seconds")
                )
                else _env_value("PUBLISHER_DISCOVERY_COMMAND_TIME_BUDGET_SECONDS"),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
                        "command_time_budget_seconds",
                        fallback=570.0,
                    ),
                    570.0,
                ),
            ),
            1.0,
        ),
        drive_auth_mode=drive_auth_settings["drive_auth_mode"],
        google_oauth_client_path=drive_auth_settings["google_oauth_client_path"],
        google_oauth_token_path=drive_auth_settings["google_oauth_token_path"],
        openrouter_http_referer=http_referer,
        headed=_to_bool(
            publisher_discovery.get("headed")
            if not _is_missing(publisher_discovery.get("headed"))
            else (
                _env_value("PUBLISHER_DISCOVERY_HEADED")
                or browser_download.get("headed")
                or _env_value("BROWSER_DOWNLOAD_HEADED")
            ),
            _to_bool(
                _default_config_value("publisher_discovery", "headed", fallback=False),
                False,
            ),
        ),
        force_browser=_to_bool(
            publisher_discovery.get("force_browser")
            if not _is_missing(publisher_discovery.get("force_browser"))
            else _env_value("PUBLISHER_DISCOVERY_FORCE_BROWSER"),
            _to_bool(
                _default_config_value(
                    "publisher_discovery", "force_browser", fallback=False
                ),
                False,
            ),
        ),
        enable_deferred_candidate_recovery=_to_bool(
            publisher_discovery.get("enable_deferred_candidate_recovery")
            if not _is_missing(
                publisher_discovery.get("enable_deferred_candidate_recovery")
            )
            else _env_value("PUBLISHER_DISCOVERY_ENABLE_DEFERRED_CANDIDATE_RECOVERY"),
            _to_bool(
                _default_config_value(
                    "publisher_discovery",
                    "enable_deferred_candidate_recovery",
                    fallback=False,
                ),
                False,
            ),
        ),
        enable_structured_route_reuse=_to_bool(
            publisher_discovery.get("enable_structured_route_reuse")
            if not _is_missing(publisher_discovery.get("enable_structured_route_reuse"))
            else _env_value("PUBLISHER_DISCOVERY_ENABLE_STRUCTURED_ROUTE_REUSE"),
            _to_bool(
                _default_config_value(
                    "publisher_discovery",
                    "enable_structured_route_reuse",
                    fallback=False,
                ),
                False,
            ),
        ),
        enable_preflight_classifier_and_direct_detail=_to_bool(
            publisher_discovery.get("enable_preflight_classifier_and_direct_detail")
            if not _is_missing(
                publisher_discovery.get("enable_preflight_classifier_and_direct_detail")
            )
            else _env_value(
                "PUBLISHER_DISCOVERY_ENABLE_PREFLIGHT_CLASSIFIER_AND_DIRECT_DETAIL"
            ),
            _to_bool(
                _default_config_value(
                    "publisher_discovery",
                    "enable_preflight_classifier_and_direct_detail",
                    fallback=False,
                ),
                False,
            ),
        ),
        retry_retries=max(
            _to_int(
                retry_cfg.get("retries")
                if not _is_missing(retry_cfg.get("retries"))
                else (
                    _env_value("PUBLISHER_DISCOVERY_RETRIES")
                    or _env_value("BROWSER_DOWNLOAD_RETRIES")
                ),
                _to_int(
                    _default_config_value(
                        "publisher_discovery", "retry", "retries", fallback=1
                    ),
                    1,
                ),
            ),
            0,
        ),
        retry_base_delay_seconds=max(
            _to_float(
                retry_cfg.get("base_delay_seconds")
                if not _is_missing(retry_cfg.get("base_delay_seconds"))
                else (
                    _env_value("PUBLISHER_DISCOVERY_BASE_DELAY_SECONDS")
                    or _env_value("BROWSER_DOWNLOAD_BASE_DELAY_SECONDS")
                ),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
                        "retry",
                        "base_delay_seconds",
                        fallback=1.0,
                    ),
                    1.0,
                ),
            ),
            0.0,
        ),
        retry_backoff_step_seconds=max(
            _to_float(
                retry_cfg.get("backoff_step_seconds")
                if not _is_missing(retry_cfg.get("backoff_step_seconds"))
                else (
                    _env_value("PUBLISHER_DISCOVERY_BACKOFF_STEP_SECONDS")
                    or _env_value("BROWSER_DOWNLOAD_BACKOFF_STEP_SECONDS")
                ),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
                        "retry",
                        "backoff_step_seconds",
                        fallback=1.0,
                    ),
                    1.0,
                ),
            ),
            0.0,
        ),
        retry_jitter_seconds=max(
            _to_float(
                retry_cfg.get("jitter_seconds")
                if not _is_missing(retry_cfg.get("jitter_seconds"))
                else (
                    _env_value("PUBLISHER_DISCOVERY_JITTER_SECONDS")
                    or _env_value("BROWSER_DOWNLOAD_JITTER_SECONDS")
                ),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
                        "retry",
                        "jitter_seconds",
                        fallback=0.25,
                    ),
                    0.25,
                ),
            ),
            0.0,
        ),
        openai_api_key=openai_api_key,
        openai_models=_normalize_openai_models(
            data.get("openai_models")
            or _default_config_value("openai_models", fallback={})
        ),
        openai_seed=_opt_int(
            ingest.get("seed") if not _is_missing(ingest.get("seed")) else None
        ),
        candidate_screening_enabled=candidate_screening_enabled,
        candidate_screening_model=str(
            candidate_screening_cfg.get("model")
            or _env_value("PUBLISHER_DISCOVERY_CANDIDATE_SCREENING_MODEL")
            or _default_config_value(
                "publisher_discovery",
                "candidate_screening",
                "model",
                fallback="gpt-5-nano",
            )
        ).strip(),
        candidate_screening_temperature=_to_float(
            candidate_screening_cfg.get("temperature")
            if not _is_missing(candidate_screening_cfg.get("temperature"))
            else _env_value("PUBLISHER_DISCOVERY_CANDIDATE_SCREENING_TEMPERATURE"),
            _to_float(
                _default_config_value(
                    "publisher_discovery",
                    "candidate_screening",
                    "temperature",
                    fallback=1.0,
                ),
                1.0,
            ),
        ),
        candidate_screening_timeout_seconds=max(
            _to_float(
                candidate_screening_cfg.get("timeout_seconds")
                if not _is_missing(candidate_screening_cfg.get("timeout_seconds"))
                else _env_value(
                    "PUBLISHER_DISCOVERY_CANDIDATE_SCREENING_TIMEOUT_SECONDS"
                ),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
                        "candidate_screening",
                        "timeout_seconds",
                        fallback=120.0,
                    ),
                    120.0,
                ),
            ),
            1.0,
        ),
        candidate_screening_batch_size=max(
            _to_int(
                candidate_screening_cfg.get("batch_size")
                if not _is_missing(candidate_screening_cfg.get("batch_size"))
                else _env_value("PUBLISHER_DISCOVERY_CANDIDATE_SCREENING_BATCH_SIZE"),
                _to_int(
                    _default_config_value(
                        "publisher_discovery",
                        "candidate_screening",
                        "batch_size",
                        fallback=10,
                    ),
                    10,
                ),
            ),
            1,
        ),
        candidate_screening_prompt_namespace=str(
            candidate_screening_cfg.get("prompt_namespace")
            or _env_value("PUBLISHER_DISCOVERY_CANDIDATE_SCREENING_PROMPT_NAMESPACE")
            or _default_config_value(
                "publisher_discovery",
                "candidate_screening",
                "prompt_namespace",
                fallback=DEFAULT_PUBLISHER_INVENTORY_CANDIDATE_SCREENING_PROMPT_NAMESPACE,
            )
        ).strip(),
        candidate_quality_check_enabled=_to_bool(
            candidate_quality_cfg.get("enabled")
            if not _is_missing(candidate_quality_cfg.get("enabled"))
            else _env_value("PUBLISHER_DISCOVERY_CANDIDATE_QUALITY_CHECK_ENABLED"),
            _to_bool(
                _default_config_value(
                    "publisher_discovery",
                    "candidate_quality_check",
                    "enabled",
                    fallback=True,
                ),
                True,
            ),
        ),
        candidate_quality_check_timeout_seconds=max(
            _to_float(
                candidate_quality_cfg.get("timeout_seconds")
                if not _is_missing(candidate_quality_cfg.get("timeout_seconds"))
                else _env_value(
                    "PUBLISHER_DISCOVERY_CANDIDATE_QUALITY_CHECK_TIMEOUT_SECONDS"
                ),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
                        "candidate_quality_check",
                        "timeout_seconds",
                        fallback=15.0,
                    ),
                    15.0,
                ),
            ),
            1.0,
        ),
        candidate_quality_check_max_workers=max(
            _to_int(
                candidate_quality_cfg.get("max_workers")
                if not _is_missing(candidate_quality_cfg.get("max_workers"))
                else _env_value(
                    "PUBLISHER_DISCOVERY_CANDIDATE_QUALITY_CHECK_MAX_WORKERS"
                ),
                _to_int(
                    _default_config_value(
                        "publisher_discovery",
                        "candidate_quality_check",
                        "max_workers",
                        fallback=6,
                    ),
                    6,
                ),
            ),
            1,
        ),
        cost_ledger_path=analysis_settings["cost_ledger_path"],
        cost_daily_path=analysis_settings["cost_daily_path"],
        model_pricing=analysis_settings["model_pricing"],
        llm_retry_retries=llm_runtime["llm_retry_retries"],
        llm_retry_base_delay_seconds=llm_runtime["llm_retry_base_delay_seconds"],
        llm_retry_backoff_step_seconds=llm_runtime["llm_retry_backoff_step_seconds"],
        llm_retry_jitter_seconds=llm_runtime["llm_retry_jitter_seconds"],
        llm_circuit_breaker_failure_threshold=llm_runtime[
            "llm_circuit_breaker_failure_threshold"
        ],
        llm_circuit_breaker_recovery_seconds=llm_runtime[
            "llm_circuit_breaker_recovery_seconds"
        ],
    )

    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.reports_db).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.cost_ledger_path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.cost_daily_path).parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_config_load_complete",
            module=logger.name,
            fields={
                "output_dir": settings.output_dir,
                "reports_db": settings.reports_db,
                "google_sa_path": settings.google_sa_path,
                "drive_auth_mode": settings.drive_auth_mode,
                "google_oauth_client_path": settings.google_oauth_client_path or "",
                "google_oauth_token_path": settings.google_oauth_token_path or "",
                "model": settings.model,
                "temperature": settings.temperature,
                "timeout_seconds": settings.timeout_seconds,
                "max_steps": settings.max_steps,
                "prompt_namespace": settings.prompt_namespace,
                "pagination_max_pages": settings.pagination_max_pages,
                "http_timeout_seconds": settings.http_timeout_seconds,
                "command_time_budget_seconds": settings.command_time_budget_seconds,
                "headed": settings.headed,
                "force_browser": settings.force_browser,
                "enable_deferred_candidate_recovery": settings.enable_deferred_candidate_recovery,
                "enable_structured_route_reuse": settings.enable_structured_route_reuse,
                "enable_preflight_classifier_and_direct_detail": settings.enable_preflight_classifier_and_direct_detail,
                "retry_retries": settings.retry_retries,
                "retry_base_delay_seconds": settings.retry_base_delay_seconds,
                "retry_backoff_step_seconds": settings.retry_backoff_step_seconds,
                "retry_jitter_seconds": settings.retry_jitter_seconds,
                "candidate_screening_enabled": settings.candidate_screening_enabled,
                "candidate_screening_model": settings.candidate_screening_model,
                "candidate_screening_temperature": settings.candidate_screening_temperature,
                "candidate_screening_timeout_seconds": settings.candidate_screening_timeout_seconds,
                "candidate_screening_batch_size": settings.candidate_screening_batch_size,
                "candidate_screening_prompt_namespace": settings.candidate_screening_prompt_namespace,
                "candidate_quality_check_enabled": settings.candidate_quality_check_enabled,
                "candidate_quality_check_timeout_seconds": settings.candidate_quality_check_timeout_seconds,
                "candidate_quality_check_max_workers": settings.candidate_quality_check_max_workers,
                "llm_retry_retries": llm_runtime["llm_retry_retries"],
                "llm_retry_base_delay_seconds": llm_runtime[
                    "llm_retry_base_delay_seconds"
                ],
                "llm_retry_backoff_step_seconds": llm_runtime[
                    "llm_retry_backoff_step_seconds"
                ],
                "llm_retry_jitter_seconds": llm_runtime["llm_retry_jitter_seconds"],
            },
        )
    )
    return settings


def upsert_browser_download_identity_fields(
    request: BrowserDownloadIdentityFieldUpsertRequest,
    ctx: RunContext,
) -> BrowserDownloadIdentityFieldUpsertResponse:
    identity_path = Path(request.path).expanduser().resolve()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_download_identity_upsert_start",
            module=logger.name,
            fields={
                "path": str(identity_path),
                "encountered_form_fields": request.encountered_form_fields,
            },
        )
    )
    identity_profile = _load_browser_download_identity(
        str(identity_path),
        load_yaml_mapping=_load_yaml_mapping,
        is_missing=_is_missing,
    )
    existing_tokens: set[str] = set()
    for field in identity_profile.fields:
        existing_tokens.update(_identity_field_match_tokens(field))

    added_fields: list[BrowserDownloadIdentityField] = []
    seen_new_tokens: set[str] = set()
    for raw_label in request.encountered_form_fields:
        label = str(raw_label or "").strip()
        normalized = _normalize_browser_download_identity_key(label)
        if not label or not normalized:
            continue
        if not _should_upsert_browser_download_identity_field(
            label=label,
            normalized_key=normalized,
        ):
            continue
        if normalized in existing_tokens or normalized in seen_new_tokens:
            continue
        seen_new_tokens.add(normalized)
        added_fields.append(
            BrowserDownloadIdentityField(
                schema_version="1.0",
                key=normalized,
                label=label,
                value=None,
                aliases=[],
            )
        )

    if added_fields:
        payload = {
            "schema_version": identity_profile.schema_version,
            "fields": [
                {
                    "schema_version": field.schema_version,
                    "key": field.key,
                    "label": field.label,
                    "value": field.value,
                    "aliases": field.aliases,
                }
                for field in [*identity_profile.fields, *added_fields]
            ],
        }
        if identity_profile.delivery_emails:
            payload["delivery_emails"] = list(identity_profile.delivery_emails)
        if identity_profile.publisher_overrides:
            payload["publisher_overrides"] = [
                {
                    "schema_version": override.schema_version,
                    "host_pattern": override.host_pattern,
                    "delivery_emails": list(override.delivery_emails),
                    "field_values": [
                        {
                            "schema_version": field.schema_version,
                            "key": field.key,
                            "label": field.label,
                            "value": field.value,
                            "aliases": field.aliases,
                        }
                        for field in override.field_values
                    ],
                }
                for override in identity_profile.publisher_overrides
            ]
        identity_path.parent.mkdir(parents=True, exist_ok=True)
        identity_path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )

    response = BrowserDownloadIdentityFieldUpsertResponse(
        schema_version="1.0",
        path=str(identity_path),
        added_field_keys=[field.key for field in added_fields],
        total_fields=len(identity_profile.fields) + len(added_fields),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_download_identity_upsert_complete",
            module=logger.name,
            fields=asdict(response),
        )
    )
    return response
