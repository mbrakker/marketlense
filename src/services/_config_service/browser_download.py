# ruff: noqa: F403,F405
from __future__ import annotations

from src.contracts.run_budget import RunBudgetLimits
from src.services._config_service.common import *


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
    cost_cfg = _resolve_cost_config(
        data,
        config_path=config_path,
        runtime_base_path=runtime_base_path,
    )
    resolver = _ConfigResolver()

    paths = data.get("paths", {}) or {}
    analysis_cfg = data.get("analysis", {}) or {}
    ingest = data.get("ingest", {}) or {}
    drive_cfg = ingest.get("drive", {}) or {}
    browser_download = data.get("browser_download", {}) or {}
    drive_upload_cfg = browser_download.get("drive_upload", {}) or {}
    failure_forensics_cfg = browser_download.get("failure_forensics", {}) or {}
    session_reuse_cfg = browser_download.get("session_reuse", {}) or {}
    warm_worker_pool_cfg = browser_download.get("warm_worker_pool", {}) or {}
    captcha_handoff_cfg = browser_download.get("captcha_handoff", {}) or {}
    route_suppression_cfg = browser_download.get("route_suppression", {}) or {}
    run_budget_cfg = browser_download.get("run_budget", {}) or {}
    authority_cfg = (data.get("cost", {}) or {}).get("budget_authority", {}) or {}
    route_budgets_cfg = browser_download.get("route_budgets", {}) or {}
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
    drive_upload_parent_folder_id = str(
        drive_upload_cfg.get("parent_folder_id")
        if not _is_missing(drive_upload_cfg.get("parent_folder_id"))
        else _env_value("BROWSER_DOWNLOAD_DRIVE_UPLOAD_PARENT_FOLDER_ID")
        or ingest.get("gdrive_folder_id")
        or _env_value("GDRIVE_FOLDER_ID")
        or ""
    ).strip()
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
        or str(DEFAULT_BROWSER_DOWNLOAD_IDENTITY_PATH),
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
    route_memory_ttl_seconds = max(
        _to_int(
            browser_download.get("route_memory_ttl_seconds")
            if not _is_missing(browser_download.get("route_memory_ttl_seconds"))
            else _env_value("BROWSER_ROUTE_MEMORY_TTL_SECONDS"),
            30 * 24 * 60 * 60,
        ),
        1,
    )
    route_suppression_failure_classes = tuple(
        sorted(
            {
                str(item).strip()
                for item in route_suppression_cfg.get("terminal_failure_classes", [])
                if str(item).strip()
            }
            or {"blocked_captcha", "blocked_email_domain"}
        )
    )
    route_suppression_minimum_sample_size = max(
        _to_int(route_suppression_cfg.get("minimum_sample_size"), 3), 3
    )
    route_suppression_threshold = min(
        1.0,
        max(
            0.0,
            _to_float(route_suppression_cfg.get("terminal_failure_threshold"), 1.0),
        ),
    )
    route_suppression_ttl_seconds = max(
        _to_int(route_suppression_cfg.get("ttl_seconds"), 7 * 24 * 60 * 60), 1
    )
    route_playbook_promotion_mode = (
        str(
            browser_download.get("route_playbook_promotion_mode")
            or _env_value("BROWSER_ROUTE_PLAYBOOK_PROMOTION_MODE")
            or "disabled"
        ).strip()
        or "disabled"
    )
    if route_playbook_promotion_mode not in {
        "disabled",
        "dry_run",
        "canary",
        "write",
    }:
        raise RuntimeError(
            "browser_download.route_playbook_promotion_mode must be one of "
            "`disabled`, `dry_run`, `canary`, or `write`"
        )
    private_api_playbook_promotion_mode = (
        str(
            browser_download.get("private_api_playbook_promotion_mode")
            or _env_value("BROWSER_PRIVATE_API_PLAYBOOK_PROMOTION_MODE")
            or "disabled"
        ).strip()
        or "disabled"
    )
    if private_api_playbook_promotion_mode not in {
        "disabled",
        "dry_run",
        "canary",
        "write",
    }:
        raise RuntimeError(
            "browser_download.private_api_playbook_promotion_mode must be one of "
            "`disabled`, `dry_run`, `canary`, or `write`"
        )
    private_api_playbook_min_success_count = int(
        browser_download.get("private_api_playbook_min_success_count")
        or _env_value("BROWSER_PRIVATE_API_PLAYBOOK_MIN_SUCCESS_COUNT")
        or 3
    )
    private_api_playbook_min_distinct_source_urls = int(
        browser_download.get("private_api_playbook_min_distinct_source_urls")
        or _env_value("BROWSER_PRIVATE_API_PLAYBOOK_MIN_DISTINCT_SOURCE_URLS")
        or 2
    )
    route_budgets = _load_browser_route_budgets(route_budgets_cfg)
    cost_ledger_path = _resolve_optional_path(
        analysis_cfg.get("cost_ledger_path")
        or _env_value("COST_LEDGER_PATH")
        or "./out/cost-ledger.jsonl",
        base_path=runtime_base_path,
    )
    cost_daily_path = _resolve_optional_path(
        cost_cfg.get("daily_path")
        or _env_value("COST_DAILY_PATH")
        or "./out/cost-daily.json",
        base_path=runtime_base_path,
    )
    usage_db_path = _resolve_optional_path(
        cost_cfg.get("usage_db_path")
        or _env_value("LLM_USAGE_DB_PATH")
        or "./state/llm_usage.sqlite",
        base_path=runtime_base_path,
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
    warm_worker_pool_policy = BrowserDownloadWarmWorkerPoolPolicy(
        schema_version=str(warm_worker_pool_cfg.get("schema_version", "1.0")),
        enabled=_to_bool(
            warm_worker_pool_cfg.get("enabled")
            if not _is_missing(warm_worker_pool_cfg.get("enabled"))
            else _env_value("BROWSER_WARM_WORKER_POOL_ENABLED"),
            False,
        ),
        max_workers=max(
            _to_int(
                warm_worker_pool_cfg.get("max_workers")
                if not _is_missing(warm_worker_pool_cfg.get("max_workers"))
                else _env_value("BROWSER_WARM_WORKER_POOL_MAX_WORKERS"),
                1,
            ),
            1,
        ),
        max_runs_per_worker=max(
            _to_int(
                warm_worker_pool_cfg.get("max_runs_per_worker")
                if not _is_missing(warm_worker_pool_cfg.get("max_runs_per_worker"))
                else _env_value("BROWSER_WARM_WORKER_POOL_MAX_RUNS"),
                3,
            ),
            1,
        ),
        max_memory_mb=max(
            _to_int(
                warm_worker_pool_cfg.get("max_memory_mb")
                if not _is_missing(warm_worker_pool_cfg.get("max_memory_mb"))
                else _env_value("BROWSER_WARM_WORKER_POOL_MAX_MEMORY_MB"),
                768,
            ),
            128,
        ),
        idle_ttl_seconds=max(
            _to_float(
                warm_worker_pool_cfg.get("idle_ttl_seconds")
                if not _is_missing(warm_worker_pool_cfg.get("idle_ttl_seconds"))
                else _env_value("BROWSER_WARM_WORKER_POOL_IDLE_TTL_SECONDS"),
                300.0,
            ),
            1.0,
        ),
        fallback_to_subprocess=_to_bool(
            warm_worker_pool_cfg.get("fallback_to_subprocess")
            if not _is_missing(warm_worker_pool_cfg.get("fallback_to_subprocess"))
            else _env_value("BROWSER_WARM_WORKER_POOL_FALLBACK_TO_SUBPROCESS"),
            True,
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

    openai_api_key = _env_value("OPENAI_API_KEY")
    openrouter_api_key = _env_value("OPENROUTER_API_KEY")
    if _is_missing(openai_api_key) and _is_missing(openrouter_api_key):
        resolver.missing.append("env:OPENAI_API_KEY or env:OPENROUTER_API_KEY")

    http_referer: str | None = _env_value("OPENROUTER_HTTP_REFERER")
    if _is_missing(http_referer):
        http_referer = None

    model = _normalize_openai_browser_model(
        browser_download.get("model")
        or _env_value("BROWSER_DOWNLOAD_MODEL")
        or _default_config_value("browser_download", "model", fallback="gpt-5-mini")
    )
    if not model:
        resolver.missing.append("browser_download.model|env:BROWSER_DOWNLOAD_MODEL")
    openrouter_model = _normalize_openrouter_browser_model(
        browser_download.get("openrouter_model")
        or _env_value("BROWSER_DOWNLOAD_OPENROUTER_MODEL")
        or browser_download.get("model")
        or _env_value("BROWSER_DOWNLOAD_MODEL")
        or _default_config_value(
            "browser_download", "openrouter_model", fallback="openai/gpt-5-mini"
        )
    )

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
        openrouter_api_key=openrouter_api_key,
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
        max_tokens=max(
            _to_int(
                browser_download.get("max_tokens")
                if not _is_missing(browser_download.get("max_tokens"))
                else _env_value("BROWSER_DOWNLOAD_MAX_TOKENS"),
                _to_int(
                    _default_config_value(
                        "browser_download", "max_tokens", fallback=12000
                    ),
                    12000,
                ),
            ),
            1024,
        ),
        output_dir=output_dir,
        state_db=state_db,
        reports_db=reports_db,
        identity_config_path=identity_config_path,
        identity_profile=identity_profile,
        openrouter_http_referer=http_referer,
        openai_api_key=openai_api_key,
        openrouter_model=openrouter_model,
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
        drive_upload_parent_folder_id=drive_upload_parent_folder_id,
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
        route_memory_ttl_seconds=route_memory_ttl_seconds,
        route_playbook_promotion_mode=route_playbook_promotion_mode,
        private_api_playbook_promotion_mode=private_api_playbook_promotion_mode,
        private_api_playbook_min_success_count=private_api_playbook_min_success_count,
        private_api_playbook_min_distinct_source_urls=(
            private_api_playbook_min_distinct_source_urls
        ),
        session_reuse_policy=session_reuse_policy,
        warm_worker_pool_policy=warm_worker_pool_policy,
        captcha_handoff_policy=BrowserDownloadCaptchaHandoffPolicy(
            schema_version="1.0",
            enabled=_to_bool(
                captcha_handoff_cfg.get("enabled")
                if not _is_missing(captcha_handoff_cfg.get("enabled"))
                else _env_value("BROWSER_DOWNLOAD_CAPTCHA_HANDOFF_ENABLED"),
                _to_bool(
                    _default_config_value(
                        "browser_download",
                        "captcha_handoff",
                        "enabled",
                        fallback=False,
                    ),
                    False,
                ),
            ),
            timeout_seconds=max(
                _to_float(
                    captcha_handoff_cfg.get("timeout_seconds")
                    if not _is_missing(captcha_handoff_cfg.get("timeout_seconds"))
                    else _env_value("BROWSER_DOWNLOAD_CAPTCHA_HANDOFF_TIMEOUT_SECONDS"),
                    _to_float(
                        _default_config_value(
                            "browser_download",
                            "captcha_handoff",
                            "timeout_seconds",
                            fallback=120.0,
                        ),
                        120.0,
                    ),
                ),
                1.0,
            ),
        ),
        route_budgets=route_budgets,
        model_pricing=cost_cfg["pricing"],
        cost_ledger_path=cost_ledger_path,
        cost_daily_path=cost_daily_path,
        usage_db_path=usage_db_path,
        run_budget_enabled=_to_bool(run_budget_cfg.get("enabled"), True),
        run_budget_max_browser_launches=(
            max(_to_int(run_budget_cfg.get("max_browser_launches"), 0), 1)
            if not _is_missing(run_budget_cfg.get("max_browser_launches"))
            else None
        ),
        run_budget_max_pdfs=(
            max(_to_int(run_budget_cfg.get("max_pdfs"), 0), 1)
            if not _is_missing(run_budget_cfg.get("max_pdfs"))
            else None
        ),
        run_budget_max_drive_writes=(
            max(_to_int(run_budget_cfg.get("max_drive_writes"), 0), 1)
            if not _is_missing(run_budget_cfg.get("max_drive_writes"))
            else None
        ),
        route_suppression_policy=BrowserDownloadRouteSuppressionPolicy(
            schema_version="1.0",
            enabled=_to_bool(route_suppression_cfg.get("enabled"), True),
            minimum_sample_size=route_suppression_minimum_sample_size,
            terminal_failure_threshold=route_suppression_threshold,
            ttl_seconds=route_suppression_ttl_seconds,
            terminal_failure_classes=route_suppression_failure_classes,
        ),
        run_budget_max_drive_reads=(
            max(_to_int(run_budget_cfg.get("max_drive_reads"), 0), 1)
            if not _is_missing(run_budget_cfg.get("max_drive_reads"))
            else None
        ),
        run_budget_max_mailbox_reads=(
            max(_to_int(run_budget_cfg.get("max_mailbox_reads"), 0), 1)
            if not _is_missing(run_budget_cfg.get("max_mailbox_reads"))
            else None
        ),
        run_budget_max_retries=(
            max(_to_int(run_budget_cfg.get("max_retries"), 0), 0)
            if not _is_missing(run_budget_cfg.get("max_retries"))
            else None
        ),
        run_budget_max_runtime_seconds=(
            max(_to_int(run_budget_cfg.get("max_runtime_seconds"), 0), 1)
            if not _is_missing(run_budget_cfg.get("max_runtime_seconds"))
            else None
        ),
        run_budget_enabled_effect_kinds=tuple(
            str(kind).strip()
            for kind in authority_cfg.get("enabled_effect_kinds", [])
            if str(kind).strip()
        ),
        run_budget_limit_decision=(
            str(run_budget_cfg.get("limit_decision") or "stop").strip().lower()
        ),
        run_budget_policy_version=str(
            authority_cfg.get("policy_version") or "budget-authority-v2"
        ).strip(),
        run_budget_reservation_ttl_seconds=max(
            _to_int(authority_cfg.get("reservation_ttl_seconds"), 300), 1
        ),
        run_budget_limits_run=_load_budget_limits(authority_cfg.get("run")),
        run_budget_limits_day=_load_budget_limits(authority_cfg.get("day")),
        run_budget_limits_publisher=_load_budget_limits(authority_cfg.get("publisher")),
        daily_spend_warn_usd=_to_float(cost_cfg.get("daily_spend_warn_usd"), 3.0),
        daily_spend_pause_usd=_to_float(cost_cfg.get("daily_spend_pause_usd"), 5.0),
        daily_spend_stop_usd=_to_float(cost_cfg.get("daily_spend_stop_usd"), 6.0),
        accounting_queue_size=max(
            _to_int(
                browser_download.get("accounting_queue_size")
                or _env_value("BROWSER_ACCOUNTING_QUEUE_SIZE")
                or 256,
                256,
            ),
            1,
        ),
        accounting_flush_timeout_seconds=max(
            _to_float(
                browser_download.get("accounting_flush_timeout_seconds")
                or _env_value("BROWSER_ACCOUNTING_FLUSH_TIMEOUT_SECONDS")
                or 5.0,
                5.0,
            ),
            0.1,
        ),
    )

    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.state_db).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.reports_db).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.usage_db_path).parent.mkdir(parents=True, exist_ok=True)
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
                "openai_api_key_present": bool(settings.openai_api_key),
                "openrouter_api_key_present": bool(settings.openrouter_api_key),
                "openrouter_model": settings.openrouter_model,
                "temperature": settings.temperature,
                "timeout_seconds": settings.timeout_seconds,
                "max_steps": settings.max_steps,
                "max_tokens": settings.max_tokens,
                "headed": settings.headed,
                "retry_retries": settings.retry_retries,
                "retry_base_delay_seconds": settings.retry_base_delay_seconds,
                "retry_backoff_step_seconds": settings.retry_backoff_step_seconds,
                "retry_jitter_seconds": settings.retry_jitter_seconds,
                "drive_upload_enabled": settings.drive_upload_enabled,
                "drive_upload_required": settings.drive_upload_required,
                "has_drive_upload_parent_folder": bool(
                    settings.drive_upload_parent_folder_id
                ),
                "drive_upload_auth_mode": settings.drive_upload_auth_mode,
                "failure_forensics_enabled": settings.failure_forensics_enabled,
                "failure_forensics_policy": settings.failure_forensics_policy,
                "route_playbook_dir": settings.route_playbook_dir,
                "route_playbook_stale_policy": settings.route_playbook_stale_policy,
                "route_memory_ttl_seconds": settings.route_memory_ttl_seconds,
                "route_playbook_promotion_mode": (
                    settings.route_playbook_promotion_mode
                ),
                "private_api_playbook_promotion_mode": (
                    settings.private_api_playbook_promotion_mode
                ),
                "private_api_playbook_min_success_count": (
                    settings.private_api_playbook_min_success_count
                ),
                "private_api_playbook_min_distinct_source_urls": (
                    settings.private_api_playbook_min_distinct_source_urls
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
                "warm_worker_pool_enabled": (settings.warm_worker_pool_policy.enabled),
                "warm_worker_pool_max_workers": (
                    settings.warm_worker_pool_policy.max_workers
                ),
                "warm_worker_pool_max_runs_per_worker": (
                    settings.warm_worker_pool_policy.max_runs_per_worker
                ),
                "warm_worker_pool_max_memory_mb": (
                    settings.warm_worker_pool_policy.max_memory_mb
                ),
                "captcha_handoff_enabled": (settings.captcha_handoff_policy.enabled),
                "captcha_handoff_timeout_seconds": (
                    settings.captcha_handoff_policy.timeout_seconds
                ),
                "route_suppression_enabled": settings.route_suppression_policy.enabled,
                "route_suppression_minimum_sample_size": (
                    settings.route_suppression_policy.minimum_sample_size
                ),
                "route_suppression_terminal_failure_threshold": (
                    settings.route_suppression_policy.terminal_failure_threshold
                ),
                "route_suppression_ttl_seconds": (
                    settings.route_suppression_policy.ttl_seconds
                ),
                "route_budget_count": len(settings.route_budgets),
            },
        )
    )
    return settings


def _load_browser_route_budgets(payload: object) -> list[BrowserDownloadRouteBudget]:
    raw_items: list[tuple[str, object]] = []
    if isinstance(payload, dict):
        raw_items = [
            (str(route_family), value) for route_family, value in payload.items()
        ]
    elif isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                raise RuntimeError(
                    "browser_download.route_budgets items must be mappings"
                )
            route_family = str(item.get("route_family") or "").strip()
            raw_items.append((route_family, item))
    elif payload:
        raise RuntimeError("browser_download.route_budgets must be a mapping or list")

    budgets: list[BrowserDownloadRouteBudget] = []
    seen: set[str] = set()
    for route_family, raw_budget in raw_items:
        normalized_family = str(route_family or "").strip()
        if not normalized_family:
            raise RuntimeError(
                "browser_download.route_budgets route_family is required"
            )
        if normalized_family in seen:
            raise RuntimeError(
                f"browser_download.route_budgets duplicates {normalized_family}"
            )
        if not isinstance(raw_budget, dict):
            raise RuntimeError(
                f"browser_download.route_budgets.{normalized_family} must be a mapping"
            )
        raw_max_steps = raw_budget.get("max_steps")
        raw_timeout_seconds = raw_budget.get("timeout_seconds")
        max_steps = (
            max(_to_int(raw_max_steps, 0), 1)
            if not _is_missing(raw_max_steps)
            else None
        )
        timeout_seconds = (
            max(_to_float(raw_timeout_seconds, 0.0), 1.0)
            if not _is_missing(raw_timeout_seconds)
            else None
        )
        if max_steps is None and timeout_seconds is None:
            raise RuntimeError(
                f"browser_download.route_budgets.{normalized_family} must set max_steps or timeout_seconds"
            )
        budgets.append(
            BrowserDownloadRouteBudget(
                schema_version=str(raw_budget.get("schema_version", "1.0")),
                route_family=normalized_family,
                max_steps=max_steps,
                timeout_seconds=timeout_seconds,
            )
        )
        seen.add(normalized_family)
    return budgets


def _normalize_openai_browser_model(value: object) -> str:
    model = str(value or "").strip()
    if model.startswith("openai/"):
        model = model.split("/", 1)[1].strip()
    return model


def _normalize_openrouter_browser_model(value: object) -> str:
    model = str(value or "").strip()
    if not model:
        return ""
    if "/" in model:
        return model
    return f"openai/{model}"


__all__ = [name for name in globals() if not name.startswith("__")]
