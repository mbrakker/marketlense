from __future__ import annotations

from typing import Any

from src.contracts.config import (
    AppConfigReadRequest,
    AppConfigWriteRequest,
    ConfigLoadRequest,
)
from src.services.config_service import (
    load_publish_settings,
    load_settings,
    read_app_config,
    write_app_config,
)
from src.ui.common import UI_SURFACE_EXCEPTIONS, _ctx


def _try_load_settings() -> tuple[Any | None, str | None]:
    try:
        settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            _ctx("load_settings"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:  # pragma: no cover - UI safeguard
        return None, str(exc)
    return settings, None


def _try_load_publish_settings() -> tuple[Any | None, str | None]:
    try:
        settings = load_publish_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            _ctx("load_publish_settings"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:  # pragma: no cover - UI safeguard
        return None, str(exc)
    return settings, None


def _try_read_app_config() -> tuple[Any | None, str | None]:
    try:
        response = read_app_config(
            AppConfigReadRequest(schema_version="1.0", path=""),
            _ctx("read_app_config"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:  # pragma: no cover - UI safeguard
        return None, str(exc)
    return response, None


def _try_write_app_config(
    content: str, *, make_backup: bool
) -> tuple[Any | None, str | None]:
    try:
        response = write_app_config(
            AppConfigWriteRequest(
                schema_version="1.0",
                path="",
                content=content,
                make_backup=make_backup,
            ),
            _ctx("write_app_config"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:  # pragma: no cover - UI safeguard
        return None, str(exc)
    return response, None
