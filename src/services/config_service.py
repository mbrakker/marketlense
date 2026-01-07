from __future__ import annotations

import os
import logging
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
import yaml

from src.contracts.config import AppSettings, ConfigLoadRequest
from src.contracts.publish import PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.wordpress import WordPressAuthSettings
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.config_service")

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "app.yaml"


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _env_value(key: str) -> str:
    return os.getenv(key, "").strip()


def _load_config(path: str) -> dict:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise RuntimeError(f"Config file not found: {path}")
    try:
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Config YAML invalid: {path}") from exc


def load_settings(request: ConfigLoadRequest, ctx: RunContext) -> AppSettings:
    load_dotenv(find_dotenv(filename=".env", usecwd=True))

    logger.info(log_event(
        ctx,
        role="service",
        event="config_load_start",
        module=logger.name,
        fields={"path": request.path or str(CONFIG_PATH)},
    ))
    data = _load_config(request.path or str(CONFIG_PATH))
    missing = []

    def need_env(key: str) -> str:
        v = os.getenv(key, "")
        if not v:
            missing.append(f"env:{key}")
        return v

    def need(section: dict, key: str, label: str, env_key: str | None = None) -> str:
        v = section.get(key)
        if _is_missing(v) and env_key:
            env_v = _env_value(env_key)
            if not _is_missing(env_v):
                return env_v
        if _is_missing(v):
            missing.append(label if not env_key else f"{label}|env:{env_key}")
            return ""
        return str(v)

    paths = data.get("paths", {}) or {}
    ingest = data.get("ingest", {}) or {}
    pdf_text = ingest.get("pdf_text", {}) or {}
    rank = data.get("rank", {}) or {}
    contents_page = ingest.get("contents_page", {}) or {}
    category_mapping_path = paths.get("category_mappings") or str(Path(__file__).resolve().parents[1] / "config" / "category-mappings.yaml")

    openai_model = need(ingest, "openai_model", "ingest.openai_model", "OPENAI_MODEL")
    temperature_raw = ingest.get("temperature")
    if _is_missing(temperature_raw):
        temperature_raw = _env_value("TEMPERATURE")
    temperature = float(temperature_raw) if not _is_missing(temperature_raw) else 1.0
    rank_model = rank.get("model") or openai_model
    rank_temperature = float(rank.get("temperature", temperature))
    openai_seed_raw = ingest.get("seed")
    rank_seed_raw = rank.get("seed")
    batch_limit_raw = ingest.get("batch_limit")
    if _is_missing(batch_limit_raw):
        batch_limit_raw = _env_value("BATCH_LIMIT")
    batch_limit = int(batch_limit_raw) if not _is_missing(batch_limit_raw) else 20
    timeout_raw = ingest.get("timeout_seconds")
    if _is_missing(timeout_raw):
        timeout_raw = _env_value("OPENAI_TIMEOUT_SECONDS")
    openai_timeout_seconds = float(timeout_raw) if not _is_missing(timeout_raw) else 600.0
    rank_timeout_raw = rank.get("timeout_seconds")
    rank_timeout_seconds = float(rank_timeout_raw) if not _is_missing(rank_timeout_raw) else openai_timeout_seconds
    lock_ttl_raw = ingest.get("lock_ttl_seconds")
    if _is_missing(lock_ttl_raw):
        lock_ttl_raw = _env_value("INGEST_LOCK_TTL_SECONDS")
    ingest_lock_ttl_seconds = float(lock_ttl_raw) if not _is_missing(lock_ttl_raw) else 7200.0
    contents_max_pages = int(contents_page.get("max_pages", 8))
    contents_min_headings = int(contents_page.get("min_headings", 3))
    contents_keywords_cfg = contents_page.get("keywords") or ["table of contents", "contents", "index"]
    contents_keywords = [str(k).strip() for k in contents_keywords_cfg if str(k).strip()]
    if not contents_keywords:
        contents_keywords = ["table of contents", "contents", "index"]
    contents_preview_dpi = int(contents_page.get("render_dpi", 144))

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

    def _opt_int(value) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    settings = AppSettings(
        schema_version=str(data.get("schema_version", "1.0")),
        google_sa_path=need(ingest, "google_sa_path", "ingest.google_sa_path", "GOOGLE_SERVICE_ACCOUNT_JSON"),
        gdrive_folder_id=need(ingest, "gdrive_folder_id", "ingest.gdrive_folder_id", "GDRIVE_FOLDER_ID"),
        openai_api_key=need_env("OPENAI_API_KEY"),
        openai_model=openai_model,
        batch_limit=batch_limit,
        output_dir=output_dir,
        cache_dir=cache_dir,
        state_db=state_db,
        reports_db=reports_db,
        category_mapping_path=category_mapping_path,
        ingest_lock_path=ingest_lock_path,
        ingest_lock_ttl_seconds=ingest_lock_ttl_seconds,
        temperature=temperature,
        openai_seed=_opt_int(openai_seed_raw),
        pdf_text_max_pages=int(pdf_text.get("max_pages", 5)),
        pdf_text_max_chars=int(pdf_text.get("max_chars", 80_000)),
        rank_model=rank_model,
        rank_temperature=rank_temperature,
        rank_seed=_opt_int(rank_seed_raw),
        openai_timeout_seconds=openai_timeout_seconds,
        rank_timeout_seconds=rank_timeout_seconds,
        contents_max_pages=contents_max_pages,
        contents_min_headings=contents_min_headings,
        contents_keywords=contents_keywords,
        contents_preview_dpi=contents_preview_dpi,
    )

    if missing:
        logger.info(log_event(
            ctx,
            role="service",
            event="config_load_failed",
            module=logger.name,
            fields={"missing": missing},
        ))
        raise RuntimeError(f"Missing required config/env values: {', '.join(missing)}")
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.state_db).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.reports_db).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.ingest_lock_path).parent.mkdir(parents=True, exist_ok=True)
    logger.info(log_event(
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
            "ingest_lock_path": settings.ingest_lock_path,
            "ingest_lock_ttl_seconds": settings.ingest_lock_ttl_seconds,
            "openai_model": settings.openai_model,
            "temperature": settings.temperature,
            "openai_seed": settings.openai_seed,
            "rank_model": settings.rank_model,
            "rank_temperature": settings.rank_temperature,
            "rank_seed": settings.rank_seed,
            "pdf_text_max_pages": settings.pdf_text_max_pages,
            "pdf_text_max_chars": settings.pdf_text_max_chars,
            "openai_timeout_seconds": settings.openai_timeout_seconds,
            "rank_timeout_seconds": settings.rank_timeout_seconds,
            "contents_max_pages": settings.contents_max_pages,
            "contents_min_headings": settings.contents_min_headings,
            "contents_keywords": settings.contents_keywords,
            "contents_preview_dpi": settings.contents_preview_dpi,
        },
    ))
    return settings


def _normalize_site_url(site_url: str) -> str:
    return site_url.rstrip("/")


def _site_url_from_admin(admin_url: str) -> str:
    url = admin_url.rstrip("/")
    if url.endswith("/wp-admin"):
        url = url[: -len("/wp-admin")]
    return _normalize_site_url(url)


def load_publish_settings(request: ConfigLoadRequest, ctx: RunContext) -> PublishSettings:
    load_dotenv(find_dotenv(filename=".env", usecwd=True))

    logger.info(log_event(
        ctx,
        role="service",
        event="publish_config_load_start",
        module=logger.name,
        fields={"path": request.path or str(CONFIG_PATH)},
    ))
    data = _load_config(request.path or str(CONFIG_PATH))
    missing = []

    def need_env(k: str) -> str:
        v = os.getenv(k, "")
        if not v:
            missing.append(f"env:{k}")
        return v

    def need(section: dict, key: str, label: str, env_key: str | None = None) -> str:
        v = section.get(key)
        if _is_missing(v) and env_key:
            env_v = _env_value(env_key)
            if not _is_missing(env_v):
                return env_v
        if _is_missing(v):
            missing.append(label if not env_key else f"{label}|env:{env_key}")
            return ""
        return str(v)

    paths = data.get("paths", {}) or {}
    publish = data.get("publish", {}) or {}
    wp_cfg = publish.get("wp", {}) or {}
    category_mapping_path = paths.get("category_mappings") or str(Path(__file__).resolve().parents[1] / "config" / "category-mappings.yaml")

    output_dir = need(paths, "output_dir", "paths.output_dir", "OUTPUT_DIR")
    state_db = need(paths, "state_db", "paths.state_db", "STATE_DB")
    reports_db = need(paths, "reports_db", "paths.reports_db", "REPORTS_DB")

    admin_url = wp_cfg.get("admin_url") or _env_value("WP_ADMIN_URL")
    site_url = wp_cfg.get("site_url") or _env_value("WP_SITE_URL")
    if not site_url and admin_url:
        site_url = _site_url_from_admin(admin_url)
    if _is_missing(site_url):
        missing.append("publish.wp.site_url|env:WP_SITE_URL|env:WP_ADMIN_URL")

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
        post_status=wp_cfg.get("post_status") or _env_value("WP_POST_STATUS") or "publish",
    )

    if missing:
        logger.info(log_event(
            ctx,
            role="service",
            event="publish_config_load_failed",
            module=logger.name,
            fields={"missing": missing},
        ))
        raise RuntimeError(f"Missing required config/env values: {', '.join(missing)}")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(state_db).parent.mkdir(parents=True, exist_ok=True)

    settings = PublishSettings(
        schema_version=str(data.get("schema_version", "1.0")),
        output_dir=output_dir,
        state_db=state_db,
        reports_db=reports_db,
        category_mapping_path=category_mapping_path,
        wp=wp,
    )
    logger.info(log_event(
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
        },
    ))
    return settings
