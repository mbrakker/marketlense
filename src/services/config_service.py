from __future__ import annotations

import os
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
from src.contracts.ingest import IngestSettings
from src.contracts.publish import PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.wordpress import WordPressAuthSettings
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.config_service")

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "app.yaml"
DEFAULT_HTML_TAG_ACRONYMS_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "html-tag-acronyms.yaml"
)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _env_value(key: str) -> str:
    return os.getenv(key, "").strip()


def _to_float(value: Any, default: float) -> float:
    if _is_missing(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int) -> int:
    if _is_missing(value):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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


def _to_ingest_settings(app_settings: AppSettings) -> IngestSettings:
    return IngestSettings(**asdict(app_settings))


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

    def _as_bool(value: object, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if _is_missing(value):
            return default
        value_str = str(value).strip().lower()
        if value_str in {"1", "true", "yes", "y", "on", "t"}:
            return True
        if value_str in {"0", "false", "no", "n", "off", "f"}:
            return False
        return default

    logger.info(
        log_event(
            ctx,
            role="service",
            event="config_load_start",
            module=logger.name,
            fields={"path": request.path or str(CONFIG_PATH)},
        )
    )
    data = _load_config(request.path or str(CONFIG_PATH))
    resolver = _ConfigResolver()
    need = resolver.need
    need_env = resolver.need_env

    paths = data.get("paths", {}) or {}
    ingest = data.get("ingest", {}) or {}
    drive_cfg = ingest.get("drive", {}) or {}
    pdf_text = ingest.get("pdf_text", {}) or {}
    rank = data.get("rank", {}) or {}
    validation_cfg = ingest.get("validation", {}) or {}
    contents_page = ingest.get("contents_page", {}) or {}
    evidence_packs_cfg = ingest.get("evidence_packs", {}) or {}
    artifacts_cfg = ingest.get("artifacts", {}) or {}
    category_mapping_path = paths.get("category_mappings") or str(
        Path(__file__).resolve().parents[1] / "config" / "category-mappings.yaml"
    )
    html_tag_acronyms_path = paths.get("html_tag_acronyms") or str(
        DEFAULT_HTML_TAG_ACRONYMS_PATH
    )
    cover_style_path = paths.get("cover_styles") or str(
        Path(__file__).resolve().parents[1] / "config" / "cover-styles.yaml"
    )
    analysis_cfg = data.get("analysis", {}) or {}
    cost_cfg = data.get("cost", {}) or {}

    openai_model = need(ingest, "openai_model", "ingest.openai_model", "OPENAI_MODEL")
    openai_models_raw = data.get("openai_models") or {}
    openai_models: dict[str, str] = {}
    if isinstance(openai_models_raw, dict):
        for key, value in openai_models_raw.items():
            key_str = str(key).strip()
            val_str = str(value).strip()
            if key_str and val_str:
                openai_models[key_str] = val_str
    temperature_raw = ingest.get("temperature")
    if _is_missing(temperature_raw):
        temperature_raw = _env_value("TEMPERATURE")
    temperature = _to_float(temperature_raw, 1.0)
    rank_model = rank.get("model") or openai_model
    rank_temperature = _to_float(rank.get("temperature"), temperature)
    rank_max_candidates = _to_int(rank.get("max_candidates"), 40)
    rank_selected_max = _to_int(rank.get("selected_max"), 5)
    rank_min_overall_score = _to_int(rank.get("min_overall_score"), 78)
    rank_min_quality_score = _to_int(rank.get("min_quality_score"), 75)
    rank_min_insight_score = _to_int(rank.get("min_insight_score"), 75)
    rank_min_data_score = _to_int(rank.get("min_data_score"), 70)
    crop_refine_enabled = _as_bool(rank.get("crop_refine_enabled"), default=True)
    crop_refine_mode_raw = str(rank.get("crop_refine_mode", "adaptive")).strip().lower()
    crop_refine_mode = (
        crop_refine_mode_raw
        if crop_refine_mode_raw in {"adaptive", "always", "off"}
        else "adaptive"
    )
    crop_refine_page_dpi = _to_int(rank.get("crop_refine_page_dpi"), 110)
    crop_refine_temperature = _to_float(rank.get("crop_refine_temperature"), 0.0)
    openai_seed_raw = ingest.get("seed")
    rank_seed_raw = rank.get("seed")
    batch_limit_raw = ingest.get("batch_limit")
    if _is_missing(batch_limit_raw):
        batch_limit_raw = _env_value("BATCH_LIMIT")
    batch_limit = _to_int(batch_limit_raw, 20)
    worker_limit_raw = ingest.get("worker_limit")
    if _is_missing(worker_limit_raw):
        worker_limit_raw = _env_value("INGEST_WORKER_LIMIT")
    ingest_worker_limit = _to_int(worker_limit_raw, 2)
    if ingest_worker_limit < 1:
        ingest_worker_limit = 1
    report_worker_limit_raw = ingest.get("report_worker_limit")
    if _is_missing(report_worker_limit_raw):
        report_worker_limit_raw = _env_value("INGEST_REPORT_WORKER_LIMIT")
    report_worker_limit = _to_int(report_worker_limit_raw, 2)
    if report_worker_limit < 1:
        report_worker_limit = 1
    timeout_raw = ingest.get("timeout_seconds")
    if _is_missing(timeout_raw):
        timeout_raw = _env_value("OPENAI_TIMEOUT_SECONDS")
    openai_timeout_seconds = _to_float(timeout_raw, 600.0)
    rank_timeout_raw = rank.get("timeout_seconds")
    rank_timeout_seconds = _to_float(rank_timeout_raw, openai_timeout_seconds)
    crop_refine_timeout_raw = rank.get("crop_refine_timeout_seconds")
    crop_refine_timeout_seconds = _to_float(
        crop_refine_timeout_raw, rank_timeout_seconds
    )
    lock_ttl_raw = ingest.get("lock_ttl_seconds")
    if _is_missing(lock_ttl_raw):
        lock_ttl_raw = _env_value("INGEST_LOCK_TTL_SECONDS")
    ingest_lock_ttl_seconds = _to_float(lock_ttl_raw, 7200.0)
    contents_max_pages = _to_int(contents_page.get("max_pages"), 8)
    contents_min_headings = _to_int(contents_page.get("min_headings"), 3)
    contents_keywords_cfg = contents_page.get("keywords") or [
        "table of contents",
        "contents",
        "index",
    ]
    contents_keywords = [
        str(k).strip() for k in contents_keywords_cfg if str(k).strip()
    ]
    if not contents_keywords:
        contents_keywords = ["table of contents", "contents", "index"]
    contents_preview_enabled = _as_bool(
        contents_page.get("preview_enabled"), default=True
    )
    contents_preview_dpi = _to_int(contents_page.get("render_dpi"), 144)
    evidence_pack_parallel_workers_raw = evidence_packs_cfg.get("parallel_workers")
    if _is_missing(evidence_pack_parallel_workers_raw):
        evidence_pack_parallel_workers_raw = _env_value(
            "EVIDENCE_PACK_PARALLEL_WORKERS"
        )
    evidence_pack_parallel_workers = _to_int(evidence_pack_parallel_workers_raw, 3)
    if evidence_pack_parallel_workers < 1:
        evidence_pack_parallel_workers = 1
    evidence_pack_global_max_in_flight_raw = evidence_packs_cfg.get(
        "global_max_in_flight"
    )
    if _is_missing(evidence_pack_global_max_in_flight_raw):
        evidence_pack_global_max_in_flight_raw = _env_value(
            "EVIDENCE_PACK_GLOBAL_MAX_IN_FLIGHT"
        )
    evidence_pack_global_max_in_flight = _to_int(
        evidence_pack_global_max_in_flight_raw, 2
    )
    if evidence_pack_global_max_in_flight < 1:
        evidence_pack_global_max_in_flight = 1
    evidence_pack_global_min_interval_ms_raw = evidence_packs_cfg.get(
        "global_min_interval_ms"
    )
    if _is_missing(evidence_pack_global_min_interval_ms_raw):
        evidence_pack_global_min_interval_ms_raw = _env_value(
            "EVIDENCE_PACK_GLOBAL_MIN_INTERVAL_MS"
        )
    evidence_pack_global_min_interval_ms = _to_int(
        evidence_pack_global_min_interval_ms_raw, 250
    )
    if evidence_pack_global_min_interval_ms < 0:
        evidence_pack_global_min_interval_ms = 0
    evidence_pack_doc_map_max_attempts_raw = evidence_packs_cfg.get(
        "doc_map_max_attempts"
    )
    if _is_missing(evidence_pack_doc_map_max_attempts_raw):
        evidence_pack_doc_map_max_attempts_raw = _env_value(
            "EVIDENCE_PACK_DOC_MAP_MAX_ATTEMPTS"
        )
    evidence_pack_doc_map_max_attempts = _to_int(
        evidence_pack_doc_map_max_attempts_raw, 3
    )
    if evidence_pack_doc_map_max_attempts < 1:
        evidence_pack_doc_map_max_attempts = 1
    evidence_pack_doc_map_retry_delay_ms_raw = evidence_packs_cfg.get(
        "doc_map_retry_delay_ms"
    )
    if _is_missing(evidence_pack_doc_map_retry_delay_ms_raw):
        evidence_pack_doc_map_retry_delay_ms_raw = _env_value(
            "EVIDENCE_PACK_DOC_MAP_RETRY_DELAY_MS"
        )
    evidence_pack_doc_map_retry_delay_ms = _to_int(
        evidence_pack_doc_map_retry_delay_ms_raw, 500
    )
    if evidence_pack_doc_map_retry_delay_ms < 0:
        evidence_pack_doc_map_retry_delay_ms = 0
    evidence_pack_registry_raw = evidence_packs_cfg.get("registry")
    env_evidence_pack_registry = _env_value("EVIDENCE_PACK_REGISTRY")
    if env_evidence_pack_registry:
        evidence_pack_registry_raw = [
            token.strip()
            for token in env_evidence_pack_registry.split(",")
            if token.strip()
        ]
    default_pack_registry = [
        "doc_map",
        "scope",
        "methods",
        "findings",
        "limitations",
        "quote_candidates",
    ]
    evidence_pack_registry: list[str] = []
    if isinstance(evidence_pack_registry_raw, list):
        for value in evidence_pack_registry_raw:
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
    enable_new_variety_packs_raw = evidence_packs_cfg.get("enable_new_variety_packs")
    if _is_missing(enable_new_variety_packs_raw):
        enable_new_variety_packs_raw = _env_value(
            "EVIDENCE_PACK_ENABLE_NEW_VARIETY_PACKS"
        )
    evidence_pack_enable_new_variety_packs = _as_bool(
        enable_new_variety_packs_raw, default=False
    )
    artifact_parallel_workers_raw = artifacts_cfg.get("parallel_workers")
    if _is_missing(artifact_parallel_workers_raw):
        artifact_parallel_workers_raw = _env_value("ARTIFACT_PARALLEL_WORKERS")
    artifact_parallel_workers = _to_int(artifact_parallel_workers_raw, 4)
    if artifact_parallel_workers < 1:
        artifact_parallel_workers = 1
    artifact_global_max_in_flight_raw = artifacts_cfg.get("global_max_in_flight")
    if _is_missing(artifact_global_max_in_flight_raw):
        artifact_global_max_in_flight_raw = _env_value("ARTIFACT_GLOBAL_MAX_IN_FLIGHT")
    artifact_global_max_in_flight = _to_int(artifact_global_max_in_flight_raw, 2)
    if artifact_global_max_in_flight < 1:
        artifact_global_max_in_flight = 1
    artifact_global_min_interval_ms_raw = artifacts_cfg.get("global_min_interval_ms")
    if _is_missing(artifact_global_min_interval_ms_raw):
        artifact_global_min_interval_ms_raw = _env_value(
            "ARTIFACT_GLOBAL_MIN_INTERVAL_MS"
        )
    artifact_global_min_interval_ms = _to_int(artifact_global_min_interval_ms_raw, 250)
    if artifact_global_min_interval_ms < 0:
        artifact_global_min_interval_ms = 0
    pdf_text_min_density = _to_float(pdf_text.get("min_density"), 250.0)
    pdf_text_sample_pages = _to_int(pdf_text.get("sample_pages"), 3)
    data_gap_policy_raw = (
        str(validation_cfg.get("data_gap_policy", "warn")).strip().lower()
    )
    validation_data_gap_policy = (
        data_gap_policy_raw if data_gap_policy_raw in {"warn", "fail"} else "warn"
    )

    output_dir = need(paths, "output_dir", "paths.output_dir", "OUTPUT_DIR")
    cache_dir = need(paths, "cache_dir", "paths.cache_dir", "CACHE_DIR")
    state_db = need(paths, "state_db", "paths.state_db", "STATE_DB")
    reports_db = need(paths, "reports_db", "paths.reports_db", "REPORTS_DB")
    lock_path_raw = paths.get("ingest_lock")
    if _is_missing(lock_path_raw):
        lock_path_raw = _env_value("INGEST_LOCK_PATH")
    if _is_missing(lock_path_raw):
        lock_path_raw = str(Path(state_db).parent / "ingest.lock")
    ingest_lock_path = str(lock_path_raw)

    def _opt_int(value: object) -> int | None:
        if _is_missing(value):
            return None
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    env_vector_store_keep = _env_value("VECTOR_STORE_KEEP")
    env_artifacts_use_vector_store = _env_value("ARTIFACTS_USE_VECTOR_STORE")
    env_validation_grounding_use_vector_store = _env_value(
        "VALIDATION_GROUNDING_USE_VECTOR_STORE"
    )
    env_cost_ledger_path = _env_value("COST_LEDGER_PATH")
    env_strict_schema_validation = _env_value("STRICT_SCHEMA_VALIDATION")
    vector_store_keep_raw = (
        env_vector_store_keep
        if env_vector_store_keep
        else analysis_cfg.get("vector_store_keep")
    )
    vector_store_keep = _as_bool(vector_store_keep_raw, default=True)
    artifacts_use_vector_store_raw = (
        env_artifacts_use_vector_store
        if env_artifacts_use_vector_store
        else analysis_cfg.get("artifacts_use_vector_store")
    )
    artifacts_use_vector_store = _as_bool(artifacts_use_vector_store_raw, default=False)
    validation_grounding_use_vector_store_raw = (
        env_validation_grounding_use_vector_store
        if env_validation_grounding_use_vector_store
        else analysis_cfg.get("validation_grounding_use_vector_store")
    )
    validation_grounding_use_vector_store = _as_bool(
        validation_grounding_use_vector_store_raw, default=False
    )
    strict_schema_validation_raw = (
        env_strict_schema_validation
        if env_strict_schema_validation
        else analysis_cfg.get("strict_schema_validation")
    )
    strict_schema_validation = _as_bool(strict_schema_validation_raw, default=True)
    cost_ledger_path = str(
        env_cost_ledger_path
        or analysis_cfg.get("cost_ledger_path")
        or "./out/cost-ledger.jsonl"
    )
    cost_daily_path = str(cost_cfg.get("daily_path") or "./out/cost-daily.json")
    model_pricing = cost_cfg.get("pricing") or {}
    cover_cache_enabled = _as_bool(ingest.get("cover_cache_enabled"), default=True)
    html_tag_acronyms = _load_html_tag_acronyms(html_tag_acronyms_path)

    drive_supports_all_drives = _as_bool(
        drive_cfg.get("supports_all_drives"), default=True
    )
    drive_include_items_from_all_drives = _as_bool(
        drive_cfg.get("include_items_from_all_drives"), default=True
    )
    drive_id_raw = drive_cfg.get("drive_id")
    drive_id = str(drive_id_raw).strip() if not _is_missing(drive_id_raw) else None
    drive_list_mode_raw = str(drive_cfg.get("list_mode", "metadata")).strip().lower()
    drive_list_mode = (
        drive_list_mode_raw
        if drive_list_mode_raw in {"full", "metadata"}
        else "metadata"
    )

    settings = AppSettings(
        schema_version=str(data.get("schema_version", "1.0")),
        google_sa_path=need(
            ingest,
            "google_sa_path",
            "ingest.google_sa_path",
            "GOOGLE_SERVICE_ACCOUNT_JSON",
        ),
        gdrive_folder_id=need(
            ingest, "gdrive_folder_id", "ingest.gdrive_folder_id", "GDRIVE_FOLDER_ID"
        ),
        drive_supports_all_drives=drive_supports_all_drives,
        drive_include_items_from_all_drives=drive_include_items_from_all_drives,
        drive_id=drive_id,
        drive_list_mode=drive_list_mode,
        openai_api_key=need_env("OPENAI_API_KEY"),
        openai_model=openai_model,
        openai_models=openai_models,
        batch_limit=batch_limit,
        ingest_worker_limit=ingest_worker_limit,
        report_worker_limit=report_worker_limit,
        output_dir=output_dir,
        cache_dir=cache_dir,
        state_db=state_db,
        reports_db=reports_db,
        category_mapping_path=category_mapping_path,
        cover_style_path=cover_style_path,
        ingest_lock_path=ingest_lock_path,
        ingest_lock_ttl_seconds=ingest_lock_ttl_seconds,
        temperature=temperature,
        openai_seed=_opt_int(openai_seed_raw),
        pdf_text_max_pages=_to_int(pdf_text.get("max_pages"), 5),
        pdf_text_max_chars=_to_int(pdf_text.get("max_chars"), 80_000),
        pdf_text_min_density=pdf_text_min_density,
        pdf_text_sample_pages=pdf_text_sample_pages,
        rank_model=rank_model,
        rank_temperature=rank_temperature,
        rank_seed=_opt_int(rank_seed_raw),
        rank_max_candidates=rank_max_candidates,
        rank_selected_max=rank_selected_max,
        rank_min_overall_score=rank_min_overall_score,
        rank_min_quality_score=rank_min_quality_score,
        rank_min_insight_score=rank_min_insight_score,
        rank_min_data_score=rank_min_data_score,
        crop_refine_enabled=crop_refine_enabled,
        crop_refine_mode=crop_refine_mode,
        crop_refine_page_dpi=crop_refine_page_dpi,
        crop_refine_temperature=crop_refine_temperature,
        crop_refine_timeout_seconds=crop_refine_timeout_seconds,
        openai_timeout_seconds=openai_timeout_seconds,
        rank_timeout_seconds=rank_timeout_seconds,
        contents_max_pages=contents_max_pages,
        contents_min_headings=contents_min_headings,
        contents_keywords=contents_keywords,
        contents_preview_enabled=contents_preview_enabled,
        contents_preview_dpi=contents_preview_dpi,
        evidence_pack_parallel_workers=evidence_pack_parallel_workers,
        evidence_pack_global_max_in_flight=evidence_pack_global_max_in_flight,
        evidence_pack_global_min_interval_ms=evidence_pack_global_min_interval_ms,
        evidence_pack_doc_map_max_attempts=evidence_pack_doc_map_max_attempts,
        evidence_pack_doc_map_retry_delay_ms=evidence_pack_doc_map_retry_delay_ms,
        evidence_pack_registry=evidence_pack_registry,
        evidence_pack_enable_new_variety_packs=evidence_pack_enable_new_variety_packs,
        artifact_parallel_workers=artifact_parallel_workers,
        artifact_global_max_in_flight=artifact_global_max_in_flight,
        artifact_global_min_interval_ms=artifact_global_min_interval_ms,
        vector_store_keep=vector_store_keep,
        artifacts_use_vector_store=artifacts_use_vector_store,
        validation_grounding_use_vector_store=validation_grounding_use_vector_store,
        strict_schema_validation=strict_schema_validation,
        cover_cache_enabled=cover_cache_enabled,
        cost_ledger_path=cost_ledger_path,
        cost_daily_path=cost_daily_path,
        model_pricing=model_pricing,
        html_tag_acronyms=html_tag_acronyms,
        validation_data_gap_policy=validation_data_gap_policy,
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
                "category_mapping_path": settings.category_mapping_path,
                "html_tag_acronyms_path": html_tag_acronyms_path,
                "ingest_lock_path": settings.ingest_lock_path,
                "ingest_lock_ttl_seconds": settings.ingest_lock_ttl_seconds,
                "drive_supports_all_drives": settings.drive_supports_all_drives,
                "drive_include_items_from_all_drives": settings.drive_include_items_from_all_drives,
                "drive_id": settings.drive_id or "",
                "drive_list_mode": settings.drive_list_mode,
                "openai_model": settings.openai_model,
                "openai_models": settings.openai_models,
                "temperature": settings.temperature,
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
                "pdf_text_max_pages": settings.pdf_text_max_pages,
                "pdf_text_max_chars": settings.pdf_text_max_chars,
                "pdf_text_min_density": settings.pdf_text_min_density,
                "pdf_text_sample_pages": settings.pdf_text_sample_pages,
                "openai_timeout_seconds": settings.openai_timeout_seconds,
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
            str(
                wp_cfg.get("post_type")
                or _env_value("WP_POST_TYPE")
                or "ml_report"
            )
            .strip()
            .strip("/")
            or "ml_report"
        ),
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
                "validation_policy": settings.validation_policy,
            },
        )
    )
    return settings
