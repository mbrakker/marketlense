from __future__ import annotations

from dotenv import find_dotenv, load_dotenv

from src.contracts.browser_download import (
    BrowserDownloadIdentityFieldUpsertRequest,
    BrowserDownloadIdentityFieldUpsertResponse,
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
from src.contracts.browser_download import BrowserDownloadSettings
from src.contracts.ingest import IngestSettings
from src.contracts.publish import PublishSettings
from src.contracts.publisher_inventory import PublisherInventorySettings
from src.contracts.run_context import RunContext
from src.contracts.wordpress import WordPressAuthSettings
from src.services._config_service import app_settings as _app_settings
from src.services._config_service import browser_download as _browser_download
from src.services._config_service import common as _common
from src.services._config_service import identity_upsert as _identity_upsert
from src.services._config_service import publish as _publish
from src.services._config_service import publisher_discovery as _publisher_discovery
from src.services._config_service.app_settings import build_ingest_settings
from src.services._config_service.common import (
    CONFIG_PATH,
    CONFIG_PATH_ENV_KEY,
    CONFIG_PROFILE_ENV_KEY,
    DEFAULT_LLM_COSTS_PATH,
    DEFAULT_BROWSER_DOWNLOAD_IDENTITY_PATH,
    DEFAULT_HTML_TAG_ACRONYMS_PATH,
    DEFAULT_PUBLISHER_INVENTORY_CANDIDATE_SCREENING_PROMPT_NAMESPACE,
    DEFAULT_PUBLISHER_INVENTORY_PROMPT_NAMESPACE,
    load_model_pricing,
    read_app_config,
    write_app_config,
)


def _sync_runtime_patch_points() -> None:
    for module in (
        _common,
        _app_settings,
        _publish,
        _browser_download,
        _publisher_discovery,
    ):
        setattr(module, "load_dotenv", load_dotenv)
        setattr(module, "find_dotenv", find_dotenv)


def load_settings(request: ConfigLoadRequest, ctx: RunContext) -> AppSettings:
    _sync_runtime_patch_points()
    return _app_settings.load_settings(request, ctx)


def load_publish_settings(
    request: ConfigLoadRequest, ctx: RunContext
) -> PublishSettings:
    _sync_runtime_patch_points()
    return _publish.load_publish_settings(request, ctx)


def load_browser_download_settings(
    request: ConfigLoadRequest, ctx: RunContext
) -> BrowserDownloadSettings:
    _sync_runtime_patch_points()
    return _browser_download.load_browser_download_settings(request, ctx)


def load_publisher_inventory_settings(
    request: ConfigLoadRequest, ctx: RunContext
) -> PublisherInventorySettings:
    _sync_runtime_patch_points()
    return _publisher_discovery.load_publisher_inventory_settings(request, ctx)


def upsert_browser_download_identity_fields(
    request: BrowserDownloadIdentityFieldUpsertRequest,
    ctx: RunContext,
) -> BrowserDownloadIdentityFieldUpsertResponse:
    return _identity_upsert.upsert_browser_download_identity_fields(request, ctx)


def resolve_openai_credential(
    request: OpenAICredentialResolveRequest,
    ctx: RunContext,
) -> OpenAICredentialResolveResponse:
    return _common.resolve_openai_credential(request, ctx)


__all__ = [
    "CONFIG_PATH",
    "CONFIG_PATH_ENV_KEY",
    "CONFIG_PROFILE_ENV_KEY",
    "DEFAULT_LLM_COSTS_PATH",
    "DEFAULT_BROWSER_DOWNLOAD_IDENTITY_PATH",
    "DEFAULT_HTML_TAG_ACRONYMS_PATH",
    "DEFAULT_PUBLISHER_INVENTORY_CANDIDATE_SCREENING_PROMPT_NAMESPACE",
    "DEFAULT_PUBLISHER_INVENTORY_PROMPT_NAMESPACE",
    "build_ingest_settings",
    "load_browser_download_settings",
    "load_publish_settings",
    "load_publisher_inventory_settings",
    "load_model_pricing",
    "load_settings",
    "read_app_config",
    "resolve_openai_credential",
    "upsert_browser_download_identity_fields",
    "write_app_config",
]
