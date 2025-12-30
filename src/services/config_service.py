from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

from src.contracts.config import AppSettings
from src.contracts.publish import PublishSettings
from src.contracts.wordpress import WordPressAuthSettings


def load_settings() -> AppSettings:
    load_dotenv(find_dotenv(filename=".env", usecwd=True))

    missing = []

    def need(k: str) -> str:
        v = os.getenv(k)
        if not v:
            missing.append(k)
        return v or ""

    settings = AppSettings(
        schema_version="1.0",
        google_sa_path=need("GOOGLE_SERVICE_ACCOUNT_JSON"),
        gdrive_folder_id=need("GDRIVE_FOLDER_ID"),
        openai_api_key=need("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5"),
        batch_limit=int(os.getenv("BATCH_LIMIT", "20")),
        output_dir=os.getenv("OUTPUT_DIR", "./out"),
        cache_dir=os.getenv("CACHE_DIR", "./cache"),
        state_db=os.getenv("STATE_DB", "./state/index.sqlite"),
        temperature=float(os.getenv("TEMPERATURE", "1")),
    )

    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.state_db).parent.mkdir(parents=True, exist_ok=True)
    return settings


def _normalize_site_url(site_url: str) -> str:
    return site_url.rstrip("/")


def _site_url_from_admin(admin_url: str) -> str:
    url = admin_url.rstrip("/")
    if url.endswith("/wp-admin"):
        url = url[: -len("/wp-admin")]
    return _normalize_site_url(url)


def load_publish_settings() -> PublishSettings:
    load_dotenv(find_dotenv(filename=".env", usecwd=True))

    missing = []

    def need(k: str) -> str:
        v = os.getenv(k)
        if not v:
            missing.append(k)
        return v or ""

    output_dir = os.getenv("OUTPUT_DIR", "./out")
    state_db = os.getenv("STATE_DB", "./state/index.sqlite")

    admin_url = os.getenv("WP_ADMIN_URL", "")
    site_url = os.getenv("WP_SITE_URL", "")
    if not site_url and admin_url:
        site_url = _site_url_from_admin(admin_url)

    wp = WordPressAuthSettings(
        schema_version="1.0",
        site_url=need("WP_SITE_URL") if not site_url else _normalize_site_url(site_url),
        username=os.getenv("WP_USERNAME"),
        app_password=os.getenv("WP_APP_PASSWORD"),
        bearer_token=os.getenv("WP_BEARER_TOKEN"),
        post_status=os.getenv("WP_POST_STATUS", "publish"),
    )

    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(state_db).parent.mkdir(parents=True, exist_ok=True)

    return PublishSettings(
        schema_version="1.0",
        output_dir=output_dir,
        state_db=state_db,
        wp=wp,
    )
