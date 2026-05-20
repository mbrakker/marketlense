from __future__ import annotations

from src.services._config_service.common import *
from src.services._config_service.settings_resolvers import *


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
    failure_forensics_cfg = browser_download.get("failure_forensics", {}) or {}
    session_reuse_cfg = browser_download.get("session_reuse", {}) or {}
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
    failure_forensics_enabled = _to_bool(
        failure_forensics_cfg.get("enabled")
        if not _is_missing(failure_forensics_cfg.get("enabled"))
        else _env_value("BROWSER_DOWNLOAD_FAILURE_FORENSICS_ENABLED"),
        _to_bool(
            _default_config_value(
                "browser_download", "failure_forensics", "enabled", fallback=True
            ),
            True,
        ),
    )
    failure_forensics_policy = (
        str(
            failure_forensics_cfg.get("policy")
            if not _is_missing(failure_forensics_cfg.get("policy"))
            else _env_value("BROWSER_DOWNLOAD_FAILURE_FORENSICS_POLICY")
            or _default_config_value(
                "browser_download",
                "failure_forensics",
                "policy",
                fallback="copy_artifacts",
            )
        ).strip()
        or "copy_artifacts"
    )
    if failure_forensics_policy not in {"copy_artifacts", "metadata_only"}:
        raise RuntimeError(
            "browser_download.failure_forensics.policy must be one of "
            "`copy_artifacts` or `metadata_only`"
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
    route_playbook_dir = _resolve_optional_path(
        browser_download.get("route_playbook_dir")
        or _env_value("BROWSER_ROUTE_PLAYBOOK_DIR")
        or "./src/playbooks/browser_routes",
        base_path=runtime_base_path,
    )
    route_playbook_stale_policy = (
        str(
            browser_download.get("route_playbook_stale_policy")
            or _env_value("BROWSER_ROUTE_PLAYBOOK_STALE_POLICY")
            or "fallback"
        ).strip()
        or "fallback"
    )
    if route_playbook_stale_policy not in {"fallback", "fail"}:
        raise RuntimeError(
            "browser_download.route_playbook_stale_policy must be one of "
            "`fallback` or `fail`"
        )
    route_playbook_promotion_mode = (
        str(
            browser_download.get("route_playbook_promotion_mode")
            or _env_value("BROWSER_ROUTE_PLAYBOOK_PROMOTION_MODE")
            or "disabled"
        ).strip()
        or "disabled"
    )
    if route_playbook_promotion_mode not in {"disabled", "dry_run", "write"}:
        raise RuntimeError(
            "browser_download.route_playbook_promotion_mode must be one of "
            "`disabled`, `dry_run`, or `write`"
        )
    session_reuse_policy = BrowserDownloadSessionReusePolicy(
        schema_version="1.0",
        enabled=_to_bool(
            session_reuse_cfg.get("enabled")
            if not _is_missing(session_reuse_cfg.get("enabled"))
            else _env_value("BROWSER_SESSION_REUSE_ENABLED"),
            False,
        ),
        mode=str(
            session_reuse_cfg.get("mode")
            or _env_value("BROWSER_SESSION_REUSE_MODE")
            or "disabled"
        ).strip(),
        session_key=str(
            session_reuse_cfg.get("session_key")
            or _env_value("BROWSER_SESSION_REUSE_KEY")
            or ""
        ).strip(),
        publisher_scope=str(
            session_reuse_cfg.get("publisher_scope")
            or _env_value("BROWSER_SESSION_REUSE_PUBLISHER_SCOPE")
            or ""
        ).strip(),
        ttl_seconds=max(
            _to_float(
                session_reuse_cfg.get("ttl_seconds")
                if not _is_missing(session_reuse_cfg.get("ttl_seconds"))
                else _env_value("BROWSER_SESSION_REUSE_TTL_SECONDS"),
                0.0,
            ),
            0.0,
        ),
        base_dir=str(
            session_reuse_cfg.get("base_dir")
            or _env_value("BROWSER_SESSION_REUSE_BASE_DIR")
            or ""
        ).strip(),
        cleanup_expired=_to_bool(
            session_reuse_cfg.get("cleanup_expired")
            if not _is_missing(session_reuse_cfg.get("cleanup_expired"))
            else _env_value("BROWSER_SESSION_REUSE_CLEANUP_EXPIRED"),
            True,
        ),
        allow_cross_publisher=_to_bool(
            session_reuse_cfg.get("allow_cross_publisher")
            if not _is_missing(session_reuse_cfg.get("allow_cross_publisher"))
            else _env_value("BROWSER_SESSION_REUSE_ALLOW_CROSS_PUBLISHER"),
            False,
        ),
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
        failure_forensics_enabled=failure_forensics_enabled,
        failure_forensics_policy=failure_forensics_policy,
        route_playbook_dir=route_playbook_dir,
        route_playbook_stale_policy=route_playbook_stale_policy,
        route_playbook_promotion_mode=route_playbook_promotion_mode,
        session_reuse_policy=session_reuse_policy,
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
                "failure_forensics_enabled": settings.failure_forensics_enabled,
                "failure_forensics_policy": settings.failure_forensics_policy,
                "route_playbook_dir": settings.route_playbook_dir,
                "route_playbook_stale_policy": settings.route_playbook_stale_policy,
                "route_playbook_promotion_mode": (
                    settings.route_playbook_promotion_mode
                ),
                "session_reuse_enabled": settings.session_reuse_policy.enabled,
                "session_reuse_mode": settings.session_reuse_policy.mode,
                "session_reuse_has_key": bool(
                    settings.session_reuse_policy.session_key
                ),
                "session_reuse_publisher_scope": (
                    settings.session_reuse_policy.publisher_scope
                ),
                "session_reuse_ttl_seconds": (
                    settings.session_reuse_policy.ttl_seconds
                ),
            },
        )
    )
    return settings


__all__ = [name for name in globals() if not name.startswith("__")]
