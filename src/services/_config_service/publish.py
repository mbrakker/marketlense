from __future__ import annotations

# ruff: noqa: F403, F405

from src.services._config_service.common import *
from src.contracts.run_budget import RunBudgetLimits


def _load_budget_limits(raw: object) -> RunBudgetLimits | None:
    if not isinstance(raw, dict) or not raw:
        return None

    def limit(name: str) -> int | None:
        value = raw.get(name)
        return None if _is_missing(value) else max(0, _to_int(value, 0))

    spend = raw.get("max_spend_usd")
    return RunBudgetLimits(
        schema_version="1.0",
        max_spend_usd=(None if _is_missing(spend) else max(0.0, _to_float(spend, 0.0))),
        max_tokens=limit("max_tokens"),
        max_calls=limit("max_calls"),
        max_steps=limit("max_steps"),
        max_runtime_seconds=limit("max_runtime_seconds"),
        max_retries=limit("max_retries"),
        max_browser_launches=limit("max_browser_launches"),
        max_drive_writes=limit("max_drive_writes"),
        max_drive_reads=limit("max_drive_reads"),
        max_wordpress_writes=limit("max_wordpress_writes"),
        max_pdfs=limit("max_pdfs"),
        max_mailbox_reads=limit("max_mailbox_reads"),
    )


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
    runtime_base_path = _resolve_runtime_base_path(config_path)
    resolver = _ConfigResolver()
    need = resolver.need
    missing = resolver.missing

    paths = data.get("paths", {}) or {}
    publish = data.get("publish", {}) or {}
    wp_cfg = publish.get("wp", {}) or {}
    validation_cfg = publish.get("validation", {}) or {}
    run_budget_cfg = publish.get("run_budget", {}) or {}
    cost_cfg = data.get("cost", {}) or {}
    authority_cfg = cost_cfg.get("budget_authority", {}) or {}
    category_mapping_path = _resolve_optional_path(
        paths.get("category_mappings")
        or str(
            Path(__file__).resolve().parents[2] / "config" / "category-mappings.yaml"
        ),
        base_path=runtime_base_path,
    )

    output_dir = resolver.need_path(
        paths,
        "output_dir",
        "paths.output_dir",
        base_path=runtime_base_path,
        env_key="OUTPUT_DIR",
    )
    state_db = resolver.need_path(
        paths,
        "state_db",
        "paths.state_db",
        base_path=runtime_base_path,
        env_key="STATE_DB",
    )
    reports_db = resolver.need_path(
        paths,
        "reports_db",
        "paths.reports_db",
        base_path=runtime_base_path,
        env_key="REPORTS_DB",
    )

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

    ssl_verify_raw: object = _env_value("WP_SSL_VERIFY")
    if _is_missing(ssl_verify_raw):
        ssl_verify_raw = wp_cfg.get("ssl_verify")
    ssl_verify = _to_bool(ssl_verify_raw, True)

    ca_bundle_path_raw: object = _env_value("WP_CA_BUNDLE_PATH")
    if _is_missing(ca_bundle_path_raw):
        ca_bundle_path_raw = wp_cfg.get("ca_bundle_path")
    ca_bundle_path = _resolve_optional_path(
        ca_bundle_path_raw,
        base_path=runtime_base_path,
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
    media_upload_workers_raw = (
        publish.get("media_upload_workers")
        or _env_value("PUBLISH_MEDIA_UPLOAD_WORKERS")
        or _default_config_value("publish", "media_upload_workers", fallback=4)
    )
    media_upload_workers = max(_to_int(media_upload_workers_raw, 4), 1)
    publish_interval_seconds_raw = (
        publish.get("publish_interval_seconds")
        or _env_value("PUBLISH_INTERVAL_SECONDS")
        or _default_config_value("publish", "publish_interval_seconds", fallback=0)
    )
    publish_interval_seconds = max(_to_int(publish_interval_seconds_raw, 0), 0)
    usage_db_path = _resolve_optional_path(
        cost_cfg.get("usage_db_path"), base_path=runtime_base_path
    )
    projection_ledger_path = _resolve_optional_path(
        cost_cfg.get("ledger_path"), base_path=runtime_base_path
    )
    projection_daily_path = _resolve_optional_path(
        cost_cfg.get("daily_path"), base_path=runtime_base_path
    )

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
        media_upload_workers=media_upload_workers,
        publish_interval_seconds=publish_interval_seconds,
        validation_policy=validation_policy,
        run_budget_enabled=_to_bool(run_budget_cfg.get("enabled"), True),
        usage_db_path=usage_db_path,
        projection_ledger_path=projection_ledger_path,
        projection_daily_path=projection_daily_path,
        projection_pending_event_threshold=max(
            _to_int(run_budget_cfg.get("projection_pending_event_threshold"), 50),
            0,
        ),
        run_budget_max_wordpress_writes=(
            max(_to_int(run_budget_cfg.get("max_wordpress_writes"), 0), 1)
            if not _is_missing(run_budget_cfg.get("max_wordpress_writes"))
            else None
        ),
        run_budget_enabled_effect_kinds=tuple(
            str(kind).strip()
            for kind in authority_cfg.get("enabled_effect_kinds", [])
            if str(kind).strip()
        ),
        run_budget_limit_decision=str(run_budget_cfg.get("limit_decision") or "stop")
        .strip()
        .lower(),
        run_budget_policy_version=str(
            authority_cfg.get("policy_version") or "budget-authority-v2"
        ).strip(),
        run_budget_reservation_ttl_seconds=max(
            _to_int(authority_cfg.get("reservation_ttl_seconds"), 300), 1
        ),
        run_budget_limits_run=_load_budget_limits(authority_cfg.get("run")),
        run_budget_limits_day=_load_budget_limits(authority_cfg.get("day")),
        run_budget_limits_publisher=_load_budget_limits(authority_cfg.get("publisher")),
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
                "media_upload_workers": settings.media_upload_workers,
                "publish_interval_seconds": settings.publish_interval_seconds,
                "ssl_verify": settings.wp.ssl_verify,
                "ca_bundle_path": settings.wp.ca_bundle_path or "",
                "validation_policy": settings.validation_policy,
            },
        )
    )
    return settings


__all__ = [name for name in globals() if not name.startswith("__")]
