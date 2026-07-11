from __future__ import annotations

from src.services._config_service.common import *


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
        google_sa_path = ""
    return {
        "drive_auth_mode": auth_mode,
        "google_sa_path": google_sa_path,
        "google_oauth_client_path": oauth_client_path or None,
        "google_oauth_token_path": oauth_token_path or None,
    }


__all__ = [name for name in globals() if not name.startswith("__")]
