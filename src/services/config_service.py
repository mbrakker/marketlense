from __future__ import annotations

import os
import logging
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
    BrowserDownloadIdentity,
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
DEFAULT_HTML_TAG_ACRONYMS_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "html-tag-acronyms.yaml"
)
DEFAULT_BROWSER_DOWNLOAD_IDENTITY_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "browser_download_identity.yaml"
)
DEFAULT_PUBLISHER_INVENTORY_PROMPT_NAMESPACE = "publisher_inventory/discovery"


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


def _load_yaml_mapping(path: str, *, label: str) -> dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise RuntimeError(f"{label} YAML not found: {path}")
    try:
        payload = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(f"{label} YAML invalid: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} YAML must be a mapping: {path}")
    return payload


def _normalize_browser_download_identity_key(raw_value: Any) -> str:
    token = str(raw_value or "").strip().lower()
    characters: list[str] = []
    previous_was_separator = False
    for char in token:
        if char.isalnum():
            characters.append(char)
            previous_was_separator = False
            continue
        if previous_was_separator:
            continue
        characters.append("_")
        previous_was_separator = True
    normalized = "".join(characters).strip("_")
    return normalized


def _normalize_browser_download_identity_aliases(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    aliases: list[str] = []
    seen: set[str] = set()
    for item in raw_value:
        token = str(item or "").strip()
        if not token:
            continue
        normalized = token.casefold()
        if normalized in seen:
            continue
        aliases.append(token)
        seen.add(normalized)
    return aliases


def _load_browser_download_identity(path: str) -> BrowserDownloadIdentity:
    payload = _load_yaml_mapping(path, label="Browser download identity")
    raw_fields = payload.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise RuntimeError(
            f"Browser download identity YAML must contain a non-empty 'fields' list: {path}"
        )
    fields: list[BrowserDownloadIdentityField] = []
    seen_keys: set[str] = set()
    for entry in raw_fields:
        if not isinstance(entry, dict):
            raise RuntimeError(
                f"Browser download identity fields must be mappings: {path}"
            )
        key = _normalize_browser_download_identity_key(entry.get("key"))
        label = str(entry.get("label") or "").strip()
        if not key or not label:
            raise RuntimeError(
                f"Browser download identity fields require non-empty key and label: {path}"
            )
        if key in seen_keys:
            raise RuntimeError(
                f"Browser download identity field keys must be unique; duplicate '{key}' in {path}"
            )
        seen_keys.add(key)
        raw_value = entry.get("value")
        value = None if _is_missing(raw_value) else str(raw_value).strip()
        fields.append(
            BrowserDownloadIdentityField(
                schema_version=str(entry.get("schema_version") or "1.0"),
                key=key,
                label=label,
                value=value,
                aliases=_normalize_browser_download_identity_aliases(
                    entry.get("aliases")
                ),
            )
        )
    return BrowserDownloadIdentity(
        schema_version=str(payload.get("schema_version") or "1.0"),
        fields=fields,
    )


def _identity_field_match_tokens(field: BrowserDownloadIdentityField) -> set[str]:
    tokens = {
        _normalize_browser_download_identity_key(field.key),
        _normalize_browser_download_identity_key(field.label),
    }
    for alias in field.aliases:
        token = _normalize_browser_download_identity_key(alias)
        if token:
            tokens.add(token)
    return {token for token in tokens if token}


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
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise RuntimeError(f"HTML acronym YAML not found: {path}")
    try:
        payload = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(f"HTML acronym YAML invalid: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"HTML acronym YAML must be a mapping: {path}")
    acronyms = _normalize_html_tag_acronyms(payload.get("html_tag_acronyms"))
    if not acronyms:
        raise RuntimeError(
            f"HTML acronym YAML must contain a non-empty 'html_tag_acronyms' list: {path}"
        )
    return acronyms


def _load_config(path: str) -> dict:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise RuntimeError(f"Config file not found: {path}")
    try:
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Config YAML invalid: {path}") from exc


def _resolve_config_path(path: str) -> Path:
    raw_path = path.strip()
    if raw_path:
        return Path(raw_path)
    return CONFIG_PATH


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
        payload = yaml.safe_load(content) or {}
    except yaml.YAMLError as exc:
        raise AppError(
            code="config_yaml_invalid",
            message=f"Config YAML invalid: {cfg_path}",
            cause=exc,
            retryable=False,
            context={"path": str(cfg_path)},
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="config_yaml_root_invalid",
            message=f"Config YAML root must be a mapping: {cfg_path}",
            retryable=False,
            context={"path": str(cfg_path), "root_type": type(payload).__name__},
        )
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
        payload = yaml.safe_load(normalized_content) or {}
    except yaml.YAMLError as exc:
        raise AppError(
            code="config_yaml_invalid",
            message=f"Config YAML invalid: {cfg_path}",
            cause=exc,
            retryable=False,
            context={"path": str(cfg_path)},
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="config_yaml_root_invalid",
            message=f"Config YAML root must be a mapping: {cfg_path}",
            retryable=False,
            context={"path": str(cfg_path), "root_type": type(payload).__name__},
        )

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
    default_pack_registry = [
        "doc_map",
        "scope",
        "methods",
        "findings",
        "limitations",
        "quote_candidates",
    ]
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
                default=1.0,
                coerce=_to_float,
                env_key="TEMPERATURE",
            ),
            _SettingSpec(
                field_name="batch_limit",
                config_key="batch_limit",
                default=20,
                coerce=_to_int,
                env_key="BATCH_LIMIT",
            ),
            _SettingSpec(
                field_name="ingest_worker_limit",
                config_key="worker_limit",
                default=2,
                coerce=_to_int,
                env_key="INGEST_WORKER_LIMIT",
                minimum=1,
            ),
            _SettingSpec(
                field_name="report_worker_limit",
                config_key="report_worker_limit",
                default=2,
                coerce=_to_int,
                env_key="INGEST_REPORT_WORKER_LIMIT",
                minimum=1,
            ),
            _SettingSpec(
                field_name="openai_timeout_seconds",
                config_key="timeout_seconds",
                default=600.0,
                coerce=_to_float,
                env_key="OPENAI_TIMEOUT_SECONDS",
            ),
            _SettingSpec(
                field_name="ingest_lock_ttl_seconds",
                config_key="lock_ttl_seconds",
                default=7200.0,
                coerce=_to_float,
                env_key="INGEST_LOCK_TTL_SECONDS",
            ),
            _SettingSpec(
                field_name="taxonomy_temperature",
                config_key="taxonomy_temperature",
                default=0.0,
                coerce=_to_float,
                env_key="TAXONOMY_TEMPERATURE",
                env_first=True,
            ),
            _SettingSpec(
                field_name="cover_cache_enabled",
                config_key="cover_cache_enabled",
                default=True,
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
                default=1,
                coerce=_to_int,
                minimum=0,
            ),
            _SettingSpec(
                field_name="llm_retry_base_delay_seconds",
                config_key="base_delay_seconds",
                default=1.0,
                coerce=_to_float,
                minimum=0.0,
            ),
            _SettingSpec(
                field_name="llm_retry_backoff_step_seconds",
                config_key="backoff_step_seconds",
                default=1.0,
                coerce=_to_float,
                minimum=0.0,
            ),
            _SettingSpec(
                field_name="llm_retry_jitter_seconds",
                config_key="jitter_seconds",
                default=0.25,
                coerce=_to_float,
                minimum=0.0,
            ),
            _SettingSpec(
                field_name="llm_circuit_breaker_failure_threshold",
                config_key="circuit_breaker_failure_threshold",
                default=3,
                coerce=_to_int,
                minimum=0,
            ),
            _SettingSpec(
                field_name="llm_circuit_breaker_recovery_seconds",
                config_key="circuit_breaker_recovery_seconds",
                default=30.0,
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
                default=40,
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_selected_max",
                config_key="selected_max",
                default=5,
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_min_overall_score",
                config_key="min_overall_score",
                default=78,
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_min_quality_score",
                config_key="min_quality_score",
                default=75,
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_min_insight_score",
                config_key="min_insight_score",
                default=75,
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_min_data_score",
                config_key="min_data_score",
                default=70,
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="crop_refine_enabled",
                config_key="crop_refine_enabled",
                default=True,
                coerce=_to_config_bool,
            ),
            _SettingSpec(
                field_name="crop_refine_page_dpi",
                config_key="crop_refine_page_dpi",
                default=110,
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="crop_refine_temperature",
                config_key="crop_refine_temperature",
                default=0.0,
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
    resolved["rank_model"] = rank.get("model") or openai_model
    resolved["rank_seed"] = _opt_int(rank.get("seed"))
    resolved["crop_refine_mode"] = _resolve_allowed_string(
        rank.get("crop_refine_mode", "adaptive"),
        default="adaptive",
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
                default=False,
                coerce=_to_config_bool,
                env_key="FIGURE_CAPTION_ENABLED",
            ),
            _SettingSpec(
                field_name="figure_caption_temperature",
                config_key="temperature",
                default=0.2,
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
                default=500,
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
                default="report_vs/figure_caption",
                coerce=_to_str,
                env_key="FIGURE_CAPTION_PROMPT_NAMESPACE",
            ),
        ),
        "report_vs/figure_caption",
    )
    return resolved


def _resolve_contents_settings(contents_page: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        contents_page,
        [
            _SettingSpec(
                field_name="contents_max_pages",
                config_key="max_pages",
                default=8,
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="contents_min_headings",
                config_key="min_headings",
                default=3,
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="contents_preview_enabled",
                config_key="preview_enabled",
                default=True,
                coerce=_to_config_bool,
            ),
            _SettingSpec(
                field_name="contents_preview_dpi",
                config_key="render_dpi",
                default=144,
                coerce=_to_int,
            ),
        ],
    )
    resolved["contents_keywords"] = _normalize_keyword_list(
        contents_page.get("keywords"),
        default_values=["table of contents", "contents", "index"],
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
                default=3,
                coerce=_to_int,
                env_key="EVIDENCE_PACK_PARALLEL_WORKERS",
                minimum=1,
            ),
            _SettingSpec(
                field_name="evidence_pack_global_max_in_flight",
                config_key="global_max_in_flight",
                default=2,
                coerce=_to_int,
                env_key="EVIDENCE_PACK_GLOBAL_MAX_IN_FLIGHT",
                minimum=1,
            ),
            _SettingSpec(
                field_name="evidence_pack_global_min_interval_ms",
                config_key="global_min_interval_ms",
                default=250,
                coerce=_to_int,
                env_key="EVIDENCE_PACK_GLOBAL_MIN_INTERVAL_MS",
                minimum=0,
            ),
            _SettingSpec(
                field_name="evidence_pack_doc_map_max_attempts",
                config_key="doc_map_max_attempts",
                default=3,
                coerce=_to_int,
                env_key="EVIDENCE_PACK_DOC_MAP_MAX_ATTEMPTS",
                minimum=1,
            ),
            _SettingSpec(
                field_name="evidence_pack_doc_map_retry_delay_ms",
                config_key="doc_map_retry_delay_ms",
                default=500,
                coerce=_to_int,
                env_key="EVIDENCE_PACK_DOC_MAP_RETRY_DELAY_MS",
                minimum=0,
            ),
            _SettingSpec(
                field_name="evidence_pack_enable_new_variety_packs",
                config_key="enable_new_variety_packs",
                default=False,
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
                default=4,
                coerce=_to_int,
                env_key="ARTIFACT_PARALLEL_WORKERS",
                minimum=1,
            ),
            _SettingSpec(
                field_name="artifact_global_max_in_flight",
                config_key="global_max_in_flight",
                default=2,
                coerce=_to_int,
                env_key="ARTIFACT_GLOBAL_MAX_IN_FLIGHT",
                minimum=1,
            ),
            _SettingSpec(
                field_name="artifact_global_min_interval_ms",
                config_key="global_min_interval_ms",
                default=250,
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
                default=5,
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="pdf_text_max_chars",
                config_key="max_chars",
                default=80_000,
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="pdf_text_min_density",
                config_key="min_density",
                default=250.0,
                coerce=_to_float,
            ),
            _SettingSpec(
                field_name="pdf_text_sample_pages",
                config_key="sample_pages",
                default=3,
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
                    default=False,
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
                    default=True,
                    coerce=_to_bool,
                ),
                _SettingSpec(
                    field_name="pdf_text_ocr_chunk_page_count",
                    config_key="chunk_page_count",
                    default=8,
                    coerce=_to_int,
                    minimum=1,
                ),
            ],
        )
    )
    resolved["pdf_text_ocr_model"] = _to_str(
        ocr_fallback_cfg.get("model"),
        "gpt-5-mini",
    )
    resolved["pdf_text_ocr_prompt_namespace"] = _to_str(
        ocr_fallback_cfg.get("prompt_namespace"),
        "pdf_text/ocr_fallback",
    )
    return resolved


def _resolve_validation_settings(validation_cfg: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        validation_cfg,
        [
            _SettingSpec(
                field_name="validation_regeneration_max_attempts",
                config_key="regeneration_max_attempts",
                default=3,
                coerce=_to_int,
                env_key="VALIDATION_REGENERATION_MAX_ATTEMPTS",
                minimum=1,
            ),
        ],
    )
    resolved["validation_data_gap_policy"] = _resolve_allowed_string(
        validation_cfg.get("data_gap_policy", "warn"),
        default="warn",
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
                default=True,
                coerce=_to_config_bool,
                env_key="VECTOR_STORE_KEEP",
                env_first=True,
            ),
            _SettingSpec(
                field_name="artifacts_use_vector_store",
                config_key="artifacts_use_vector_store",
                default=False,
                coerce=_to_config_bool,
                env_key="ARTIFACTS_USE_VECTOR_STORE",
                env_first=True,
            ),
            _SettingSpec(
                field_name="validation_grounding_use_vector_store",
                config_key="validation_grounding_use_vector_store",
                default=False,
                coerce=_to_config_bool,
                env_key="VALIDATION_GROUNDING_USE_VECTOR_STORE",
                env_first=True,
            ),
            _SettingSpec(
                field_name="strict_schema_validation",
                config_key="strict_schema_validation",
                default=True,
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
                default="./out/cost-ledger.jsonl",
                coerce=_to_str,
                env_key="COST_LEDGER_PATH",
                env_first=True,
            ),
        )
        or "./out/cost-ledger.jsonl"
    )
    resolved["cost_daily_path"] = str(
        cost_cfg.get("daily_path") or "./out/cost-daily.json"
    )
    resolved["model_pricing"] = cost_cfg.get("pricing") or {}
    resolved["html_tag_acronyms"] = _load_html_tag_acronyms(html_tag_acronyms_path)
    return resolved


def _resolve_drive_settings(drive_cfg: dict[str, Any]) -> dict[str, Any]:
    drive_id_raw = drive_cfg.get("drive_id")
    return {
        "drive_supports_all_drives": _to_config_bool(
            drive_cfg.get("supports_all_drives"), True
        ),
        "drive_include_items_from_all_drives": _to_config_bool(
            drive_cfg.get("include_items_from_all_drives"), True
        ),
        "drive_id": str(drive_id_raw).strip()
        if not _is_missing(drive_id_raw)
        else None,
        "drive_list_mode": _resolve_allowed_string(
            drive_cfg.get("list_mode", "metadata"),
            default="metadata",
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
        drive_cfg.get("auth_mode") or _env_value("GOOGLE_DRIVE_AUTH_MODE"),
        default="service_account",
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
    filtered_payload = {
        key: value for key, value in payload.items() if key in allowed
    }
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
    config_path = Path(request.path or str(CONFIG_PATH)).resolve()
    runtime_base_path = _resolve_runtime_base_path(config_path)
    data = _load_config(str(config_path))
    resolver = _ConfigResolver()
    need = resolver.need
    need_env = resolver.need_env

    paths = data.get("paths", {}) or {}
    ingest = data.get("ingest", {}) or {}
    llm_cfg = ingest.get("llm", {}) or {}
    drive_cfg = ingest.get("drive", {}) or {}
    pdf_text = ingest.get("pdf_text", {}) or {}
    figure_captions_cfg = ingest.get("figure_captions", {}) or {}
    rank = data.get("rank", {}) or {}
    validation_cfg = ingest.get("validation", {}) or {}
    contents_page = ingest.get("contents_page", {}) or {}
    evidence_packs_cfg = ingest.get("evidence_packs", {}) or {}
    artifacts_cfg = ingest.get("artifacts", {}) or {}
    analysis_cfg = data.get("analysis", {}) or {}
    cost_cfg = data.get("cost", {}) or {}
    paths_settings = _resolve_paths_settings(paths, resolver)
    openai_model = need(ingest, "openai_model", "ingest.openai_model", "OPENAI_MODEL")
    ingest_runtime = _resolve_ingest_runtime_settings(ingest)
    llm_runtime = _resolve_llm_runtime_settings(llm_cfg)
    rank_settings = _resolve_rank_settings(
        rank,
        openai_model=openai_model,
        temperature=ingest_runtime["temperature"],
        openai_timeout_seconds=ingest_runtime["openai_timeout_seconds"],
    )
    figure_caption_settings = _resolve_figure_caption_settings(
        figure_captions_cfg,
        openai_timeout_seconds=ingest_runtime["openai_timeout_seconds"],
    )
    contents_settings = _resolve_contents_settings(contents_page)
    evidence_pack_settings = _resolve_evidence_pack_settings(evidence_packs_cfg)
    artifact_settings = _resolve_artifact_settings(artifacts_cfg)
    pdf_text_settings = _resolve_pdf_text_settings(pdf_text, ingest)
    validation_settings = _resolve_validation_settings(validation_cfg)
    analysis_settings = _resolve_analysis_settings(
        analysis_cfg,
        cost_cfg,
        html_tag_acronyms_path=paths_settings["html_tag_acronyms_path"],
    )
    drive_settings = _resolve_drive_settings(drive_cfg)
    drive_auth_settings = _resolve_drive_auth_settings(
        ingest,
        drive_cfg,
        runtime_base_path=runtime_base_path,
        resolver=resolver,
    )

    settings = AppSettings(
        schema_version=str(data.get("schema_version", "1.0")),
        google_sa_path=drive_auth_settings["google_sa_path"],
        gdrive_folder_id=need(
            ingest, "gdrive_folder_id", "ingest.gdrive_folder_id", "GDRIVE_FOLDER_ID"
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
        openai_models=_normalize_openai_models(data.get("openai_models") or {}),
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
            fields={
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
            },
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

    logger.info(
        log_event(
            ctx,
            role="service",
            event="publish_config_load_start",
            module=logger.name,
            fields={"path": request.path or str(CONFIG_PATH)},
        )
    )
    data = _load_config(request.path or str(CONFIG_PATH))
    config_path = Path(request.path or str(CONFIG_PATH)).resolve()
    runtime_base_path = _resolve_runtime_base_path(config_path)
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
        or "publish",
        post_type=(
            str(wp_cfg.get("post_type") or _env_value("WP_POST_TYPE") or "ml_report")
            .strip()
            .strip("/")
            or "ml_report"
        ),
        ssl_verify=ssl_verify,
        ca_bundle_path=ca_bundle_path or None,
    )

    validation_policy_raw = (
        validation_cfg.get("policy")
        or _env_value("PUBLISH_VALIDATION_POLICY")
        or "block"
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

    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_download_config_load_start",
            module=logger.name,
            fields={"path": request.path or str(CONFIG_PATH)},
        )
    )
    data = _load_config(request.path or str(CONFIG_PATH))
    config_path = Path(request.path or str(CONFIG_PATH)).resolve()
    runtime_base_path = _resolve_runtime_base_path(config_path)
    resolver = _ConfigResolver()

    paths = data.get("paths", {}) or {}
    ingest = data.get("ingest", {}) or {}
    browser_download = data.get("browser_download", {}) or {}
    retry_cfg = browser_download.get("retry", {}) or {}

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

    api_key = _env_value("OPENROUTER_API_KEY")
    if _is_missing(api_key):
        resolver.missing.append("env:OPENROUTER_API_KEY")

    http_referer = _env_value("OPENROUTER_HTTP_REFERER")
    if _is_missing(http_referer):
        http_referer = None

    model = str(
        browser_download.get("model")
        or _env_value("BROWSER_DOWNLOAD_MODEL")
        or "openai/gpt-5-mini"
        or ""
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

    identity_profile = _load_browser_download_identity(identity_config_path)

    settings = BrowserDownloadSettings(
        schema_version=str(data.get("schema_version", "1.0")),
        openrouter_api_key=api_key,
        model=model,
        temperature=_to_float(
            browser_download.get("temperature")
            if not _is_missing(browser_download.get("temperature"))
            else _env_value("BROWSER_DOWNLOAD_TEMPERATURE"),
            0.0,
        ),
        timeout_seconds=max(
            _to_float(
                browser_download.get("timeout_seconds")
                if not _is_missing(browser_download.get("timeout_seconds"))
                else _env_value("BROWSER_DOWNLOAD_TIMEOUT_SECONDS"),
                180.0,
            ),
            1.0,
        ),
        max_steps=max(
            _to_int(
                browser_download.get("max_steps")
                if not _is_missing(browser_download.get("max_steps"))
                else _env_value("BROWSER_DOWNLOAD_MAX_STEPS"),
                30,
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
            False,
        ),
        retry_retries=max(
            _to_int(
                retry_cfg.get("retries")
                if not _is_missing(retry_cfg.get("retries"))
                else _env_value("BROWSER_DOWNLOAD_RETRIES"),
                1,
            ),
            0,
        ),
        retry_base_delay_seconds=max(
            _to_float(
                retry_cfg.get("base_delay_seconds")
                if not _is_missing(retry_cfg.get("base_delay_seconds"))
                else _env_value("BROWSER_DOWNLOAD_BASE_DELAY_SECONDS"),
                1.0,
            ),
            0.0,
        ),
        retry_backoff_step_seconds=max(
            _to_float(
                retry_cfg.get("backoff_step_seconds")
                if not _is_missing(retry_cfg.get("backoff_step_seconds"))
                else _env_value("BROWSER_DOWNLOAD_BACKOFF_STEP_SECONDS"),
                1.0,
            ),
            0.0,
        ),
        retry_jitter_seconds=max(
            _to_float(
                retry_cfg.get("jitter_seconds")
                if not _is_missing(retry_cfg.get("jitter_seconds"))
                else _env_value("BROWSER_DOWNLOAD_JITTER_SECONDS"),
                0.25,
            ),
            0.0,
        ),
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
            },
        )
    )
    return settings


def load_publisher_inventory_settings(
    request: ConfigLoadRequest, ctx: RunContext
) -> PublisherInventorySettings:
    load_dotenv(find_dotenv(filename=".env", usecwd=True))

    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_config_load_start",
            module=logger.name,
            fields={"path": request.path or str(CONFIG_PATH)},
        )
    )
    data = _load_config(request.path or str(CONFIG_PATH))
    config_path = Path(request.path or str(CONFIG_PATH)).resolve()
    runtime_base_path = _resolve_runtime_base_path(config_path)
    resolver = _ConfigResolver()

    paths = data.get("paths", {}) or {}
    ingest = data.get("ingest", {}) or {}
    drive_cfg = ingest.get("drive", {}) or {}
    browser_download = data.get("browser_download", {}) or {}
    browser_retry_cfg = browser_download.get("retry", {}) or {}
    publisher_discovery = data.get("publisher_discovery", {}) or {}
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

    api_key = _env_value("OPENROUTER_API_KEY")
    if _is_missing(api_key):
        resolver.missing.append("env:OPENROUTER_API_KEY")

    http_referer = _env_value("OPENROUTER_HTTP_REFERER")
    if _is_missing(http_referer):
        http_referer = None

    model = str(
        publisher_discovery.get("model")
        or _env_value("PUBLISHER_DISCOVERY_MODEL")
        or browser_download.get("model")
        or _env_value("BROWSER_DOWNLOAD_MODEL")
        or "openai/gpt-5-mini"
    ).strip()
    if not model:
        resolver.missing.append("publisher_discovery.model|env:PUBLISHER_DISCOVERY_MODEL")

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
            0.0,
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
                180.0,
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
                30,
            ),
            1,
        ),
        output_dir=output_dir,
        reports_db=reports_db,
        google_sa_path=drive_auth_settings["google_sa_path"],
        prompt_namespace=str(
            publisher_discovery.get("prompt_namespace")
            or _env_value("PUBLISHER_DISCOVERY_PROMPT_NAMESPACE")
            or DEFAULT_PUBLISHER_INVENTORY_PROMPT_NAMESPACE
        ).strip(),
        pagination_max_pages=max(
            _to_int(
                publisher_discovery.get("pagination_max_pages")
                if not _is_missing(publisher_discovery.get("pagination_max_pages"))
                else _env_value("PUBLISHER_DISCOVERY_PAGINATION_MAX_PAGES"),
                10,
            ),
            1,
        ),
        http_timeout_seconds=max(
            _to_float(
                publisher_discovery.get("http_timeout_seconds")
                if not _is_missing(publisher_discovery.get("http_timeout_seconds"))
                else _env_value("PUBLISHER_DISCOVERY_HTTP_TIMEOUT_SECONDS"),
                30.0,
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
            False,
        ),
        force_browser=_to_bool(
            publisher_discovery.get("force_browser")
            if not _is_missing(publisher_discovery.get("force_browser"))
            else _env_value("PUBLISHER_DISCOVERY_FORCE_BROWSER"),
            False,
        ),
        retry_retries=max(
            _to_int(
                retry_cfg.get("retries")
                if not _is_missing(retry_cfg.get("retries"))
                else (
                    _env_value("PUBLISHER_DISCOVERY_RETRIES")
                    or _env_value("BROWSER_DOWNLOAD_RETRIES")
                ),
                1,
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
                1.0,
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
                1.0,
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
                0.25,
            ),
            0.0,
        ),
    )

    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.reports_db).parent.mkdir(parents=True, exist_ok=True)
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
                "headed": settings.headed,
                "force_browser": settings.force_browser,
                "retry_retries": settings.retry_retries,
                "retry_base_delay_seconds": settings.retry_base_delay_seconds,
                "retry_backoff_step_seconds": settings.retry_backoff_step_seconds,
                "retry_jitter_seconds": settings.retry_jitter_seconds,
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
    identity_profile = _load_browser_download_identity(str(identity_path))
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
