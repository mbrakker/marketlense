from __future__ import annotations

from src.services._config_service.common import *
from src.services._config_service.settings_resolvers import *


def load_publisher_inventory_settings(
    request: ConfigLoadRequest, ctx: RunContext
) -> PublisherInventorySettings:
    load_dotenv(find_dotenv(filename=".env", usecwd=True))
    config_path = _resolve_bootstrap_config_path(request.path)

    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_config_load_start",
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
    llm_cfg = ingest.get("llm", {}) or {}
    browser_download = data.get("browser_download", {}) or {}
    browser_retry_cfg = browser_download.get("retry", {}) or {}
    publisher_discovery = data.get("publisher_discovery", {}) or {}
    candidate_screening_cfg = publisher_discovery.get("candidate_screening", {}) or {}
    candidate_quality_cfg = publisher_discovery.get("candidate_quality_check", {}) or {}
    resource_quality_cfg = publisher_discovery.get("resource_quality_ranking", {}) or {}
    analysis_cfg = data.get("analysis", {}) or {}
    cost_cfg = data.get("cost", {}) or {}
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
    llm_runtime = _resolve_llm_runtime_settings(llm_cfg)
    paths_settings = _resolve_paths_settings(paths, resolver)
    analysis_settings = _resolve_analysis_settings(
        analysis_cfg,
        cost_cfg,
        html_tag_acronyms_path=paths_settings["html_tag_acronyms_path"],
    )

    api_key = _env_value("OPENROUTER_API_KEY")
    if _is_missing(api_key):
        resolver.missing.append("env:OPENROUTER_API_KEY")

    http_referer: str | None = _env_value("OPENROUTER_HTTP_REFERER")
    if _is_missing(http_referer):
        http_referer = None

    model = str(
        publisher_discovery.get("model")
        or _env_value("PUBLISHER_DISCOVERY_MODEL")
        or browser_download.get("model")
        or _env_value("BROWSER_DOWNLOAD_MODEL")
        or _default_config_value(
            "publisher_discovery",
            "model",
            fallback=_default_config_value(
                "browser_download", "model", fallback="openai/gpt-5-mini"
            ),
        )
    ).strip()
    if not model:
        resolver.missing.append(
            "publisher_discovery.model|env:PUBLISHER_DISCOVERY_MODEL"
        )

    candidate_screening_enabled = _to_bool(
        candidate_screening_cfg.get("enabled")
        if not _is_missing(candidate_screening_cfg.get("enabled"))
        else _env_value("PUBLISHER_DISCOVERY_CANDIDATE_SCREENING_ENABLED"),
        _to_bool(
            _default_config_value(
                "publisher_discovery",
                "candidate_screening",
                "enabled",
                fallback=True,
            ),
            True,
        ),
    )
    openai_api_key = _env_value("OPENAI_API_KEY")
    if candidate_screening_enabled and _is_missing(openai_api_key):
        resolver.missing.append("env:OPENAI_API_KEY")

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
            _to_float(
                _default_config_value(
                    "publisher_discovery", "temperature", fallback=0.0
                ),
                0.0,
            ),
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
                _to_float(
                    _default_config_value(
                        "publisher_discovery", "timeout_seconds", fallback=360.0
                    ),
                    360.0,
                ),
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
                _to_int(
                    _default_config_value(
                        "publisher_discovery", "max_steps", fallback=30
                    ),
                    30,
                ),
            ),
            1,
        ),
        output_dir=output_dir,
        reports_db=reports_db,
        google_sa_path=drive_auth_settings["google_sa_path"],
        prompt_namespace=str(
            publisher_discovery.get("prompt_namespace")
            or _env_value("PUBLISHER_DISCOVERY_PROMPT_NAMESPACE")
            or _default_config_value(
                "publisher_discovery",
                "prompt_namespace",
                fallback=DEFAULT_PUBLISHER_INVENTORY_PROMPT_NAMESPACE,
            )
        ).strip(),
        pagination_max_pages=max(
            _to_int(
                publisher_discovery.get("pagination_max_pages")
                if not _is_missing(publisher_discovery.get("pagination_max_pages"))
                else _env_value("PUBLISHER_DISCOVERY_PAGINATION_MAX_PAGES"),
                _to_int(
                    _default_config_value(
                        "publisher_discovery", "pagination_max_pages", fallback=75
                    ),
                    75,
                ),
            ),
            1,
        ),
        http_timeout_seconds=max(
            _to_float(
                publisher_discovery.get("http_timeout_seconds")
                if not _is_missing(publisher_discovery.get("http_timeout_seconds"))
                else _env_value("PUBLISHER_DISCOVERY_HTTP_TIMEOUT_SECONDS"),
                _to_float(
                    _default_config_value(
                        "publisher_discovery", "http_timeout_seconds", fallback=30.0
                    ),
                    30.0,
                ),
            ),
            1.0,
        ),
        command_time_budget_seconds=max(
            _to_float(
                publisher_discovery.get("command_time_budget_seconds")
                if not _is_missing(
                    publisher_discovery.get("command_time_budget_seconds")
                )
                else _env_value("PUBLISHER_DISCOVERY_COMMAND_TIME_BUDGET_SECONDS"),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
                        "command_time_budget_seconds",
                        fallback=570.0,
                    ),
                    570.0,
                ),
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
            _to_bool(
                _default_config_value("publisher_discovery", "headed", fallback=False),
                False,
            ),
        ),
        force_browser=_to_bool(
            publisher_discovery.get("force_browser")
            if not _is_missing(publisher_discovery.get("force_browser"))
            else _env_value("PUBLISHER_DISCOVERY_FORCE_BROWSER"),
            _to_bool(
                _default_config_value(
                    "publisher_discovery", "force_browser", fallback=False
                ),
                False,
            ),
        ),
        enable_deferred_candidate_recovery=_to_bool(
            publisher_discovery.get("enable_deferred_candidate_recovery")
            if not _is_missing(
                publisher_discovery.get("enable_deferred_candidate_recovery")
            )
            else _env_value("PUBLISHER_DISCOVERY_ENABLE_DEFERRED_CANDIDATE_RECOVERY"),
            _to_bool(
                _default_config_value(
                    "publisher_discovery",
                    "enable_deferred_candidate_recovery",
                    fallback=True,
                ),
                True,
            ),
        ),
        enable_structured_route_reuse=_to_bool(
            publisher_discovery.get("enable_structured_route_reuse")
            if not _is_missing(publisher_discovery.get("enable_structured_route_reuse"))
            else _env_value("PUBLISHER_DISCOVERY_ENABLE_STRUCTURED_ROUTE_REUSE"),
            _to_bool(
                _default_config_value(
                    "publisher_discovery",
                    "enable_structured_route_reuse",
                    fallback=True,
                ),
                True,
            ),
        ),
        enable_preflight_classifier_and_direct_detail=_to_bool(
            publisher_discovery.get("enable_preflight_classifier_and_direct_detail")
            if not _is_missing(
                publisher_discovery.get("enable_preflight_classifier_and_direct_detail")
            )
            else _env_value(
                "PUBLISHER_DISCOVERY_ENABLE_PREFLIGHT_CLASSIFIER_AND_DIRECT_DETAIL"
            ),
            _to_bool(
                _default_config_value(
                    "publisher_discovery",
                    "enable_preflight_classifier_and_direct_detail",
                    fallback=True,
                ),
                True,
            ),
        ),
        retry_retries=max(
            _to_int(
                retry_cfg.get("retries")
                if not _is_missing(retry_cfg.get("retries"))
                else (
                    _env_value("PUBLISHER_DISCOVERY_RETRIES")
                    or _env_value("BROWSER_DOWNLOAD_RETRIES")
                ),
                _to_int(
                    _default_config_value(
                        "publisher_discovery", "retry", "retries", fallback=1
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
                else (
                    _env_value("PUBLISHER_DISCOVERY_BASE_DELAY_SECONDS")
                    or _env_value("BROWSER_DOWNLOAD_BASE_DELAY_SECONDS")
                ),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
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
                else (
                    _env_value("PUBLISHER_DISCOVERY_BACKOFF_STEP_SECONDS")
                    or _env_value("BROWSER_DOWNLOAD_BACKOFF_STEP_SECONDS")
                ),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
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
                else (
                    _env_value("PUBLISHER_DISCOVERY_JITTER_SECONDS")
                    or _env_value("BROWSER_DOWNLOAD_JITTER_SECONDS")
                ),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
                        "retry",
                        "jitter_seconds",
                        fallback=0.25,
                    ),
                    0.25,
                ),
            ),
            0.0,
        ),
        openai_api_key=openai_api_key,
        openai_models=_normalize_openai_models(
            data.get("openai_models")
            or _default_config_value("openai_models", fallback={})
        ),
        openai_seed=_opt_int(
            ingest.get("seed") if not _is_missing(ingest.get("seed")) else None
        ),
        candidate_screening_enabled=candidate_screening_enabled,
        candidate_screening_model=str(
            candidate_screening_cfg.get("model")
            or _env_value("PUBLISHER_DISCOVERY_CANDIDATE_SCREENING_MODEL")
            or _default_config_value(
                "publisher_discovery",
                "candidate_screening",
                "model",
                fallback="gpt-5-nano",
            )
        ).strip(),
        candidate_screening_temperature=_to_float(
            candidate_screening_cfg.get("temperature")
            if not _is_missing(candidate_screening_cfg.get("temperature"))
            else _env_value("PUBLISHER_DISCOVERY_CANDIDATE_SCREENING_TEMPERATURE"),
            _to_float(
                _default_config_value(
                    "publisher_discovery",
                    "candidate_screening",
                    "temperature",
                    fallback=1.0,
                ),
                1.0,
            ),
        ),
        candidate_screening_timeout_seconds=max(
            _to_float(
                candidate_screening_cfg.get("timeout_seconds")
                if not _is_missing(candidate_screening_cfg.get("timeout_seconds"))
                else _env_value(
                    "PUBLISHER_DISCOVERY_CANDIDATE_SCREENING_TIMEOUT_SECONDS"
                ),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
                        "candidate_screening",
                        "timeout_seconds",
                        fallback=120.0,
                    ),
                    120.0,
                ),
            ),
            1.0,
        ),
        candidate_screening_batch_size=max(
            _to_int(
                candidate_screening_cfg.get("batch_size")
                if not _is_missing(candidate_screening_cfg.get("batch_size"))
                else _env_value("PUBLISHER_DISCOVERY_CANDIDATE_SCREENING_BATCH_SIZE"),
                _to_int(
                    _default_config_value(
                        "publisher_discovery",
                        "candidate_screening",
                        "batch_size",
                        fallback=10,
                    ),
                    10,
                ),
            ),
            1,
        ),
        candidate_screening_prompt_namespace=str(
            candidate_screening_cfg.get("prompt_namespace")
            or _env_value("PUBLISHER_DISCOVERY_CANDIDATE_SCREENING_PROMPT_NAMESPACE")
            or _default_config_value(
                "publisher_discovery",
                "candidate_screening",
                "prompt_namespace",
                fallback=DEFAULT_PUBLISHER_INVENTORY_CANDIDATE_SCREENING_PROMPT_NAMESPACE,
            )
        ).strip(),
        candidate_quality_check_enabled=_to_bool(
            candidate_quality_cfg.get("enabled")
            if not _is_missing(candidate_quality_cfg.get("enabled"))
            else _env_value("PUBLISHER_DISCOVERY_CANDIDATE_QUALITY_CHECK_ENABLED"),
            _to_bool(
                _default_config_value(
                    "publisher_discovery",
                    "candidate_quality_check",
                    "enabled",
                    fallback=True,
                ),
                True,
            ),
        ),
        candidate_quality_check_timeout_seconds=max(
            _to_float(
                candidate_quality_cfg.get("timeout_seconds")
                if not _is_missing(candidate_quality_cfg.get("timeout_seconds"))
                else _env_value(
                    "PUBLISHER_DISCOVERY_CANDIDATE_QUALITY_CHECK_TIMEOUT_SECONDS"
                ),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
                        "candidate_quality_check",
                        "timeout_seconds",
                        fallback=15.0,
                    ),
                    15.0,
                ),
            ),
            1.0,
        ),
        candidate_quality_check_max_workers=max(
            _to_int(
                candidate_quality_cfg.get("max_workers")
                if not _is_missing(candidate_quality_cfg.get("max_workers"))
                else _env_value(
                    "PUBLISHER_DISCOVERY_CANDIDATE_QUALITY_CHECK_MAX_WORKERS"
                ),
                _to_int(
                    _default_config_value(
                        "publisher_discovery",
                        "candidate_quality_check",
                        "max_workers",
                        fallback=6,
                    ),
                    6,
                ),
            ),
            1,
        ),
        resource_quality_ranking_enabled=_to_bool(
            resource_quality_cfg.get("enabled")
            if not _is_missing(resource_quality_cfg.get("enabled"))
            else _env_value("PUBLISHER_DISCOVERY_RESOURCE_QUALITY_RANKING_ENABLED"),
            _to_bool(
                _default_config_value(
                    "publisher_discovery",
                    "resource_quality_ranking",
                    "enabled",
                    fallback=True,
                ),
                True,
            ),
        ),
        resource_quality_score_window_size=max(
            _to_int(
                resource_quality_cfg.get("score_window_size")
                if not _is_missing(resource_quality_cfg.get("score_window_size"))
                else _env_value(
                    "PUBLISHER_DISCOVERY_RESOURCE_QUALITY_SCORE_WINDOW_SIZE"
                ),
                _to_int(
                    _default_config_value(
                        "publisher_discovery",
                        "resource_quality_ranking",
                        "score_window_size",
                        fallback=5,
                    ),
                    5,
                ),
            ),
            1,
        ),
        resource_quality_min_sample_size=max(
            _to_int(
                resource_quality_cfg.get("min_sample_size")
                if not _is_missing(resource_quality_cfg.get("min_sample_size"))
                else _env_value("PUBLISHER_DISCOVERY_RESOURCE_QUALITY_MIN_SAMPLE_SIZE"),
                _to_int(
                    _default_config_value(
                        "publisher_discovery",
                        "resource_quality_ranking",
                        "min_sample_size",
                        fallback=2,
                    ),
                    2,
                ),
            ),
            1,
        ),
        resource_quality_consistency_weight=max(
            _to_float(
                resource_quality_cfg.get("consistency_weight")
                if not _is_missing(resource_quality_cfg.get("consistency_weight"))
                else _env_value(
                    "PUBLISHER_DISCOVERY_RESOURCE_QUALITY_CONSISTENCY_WEIGHT"
                ),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
                        "resource_quality_ranking",
                        "consistency_weight",
                        fallback=0.35,
                    ),
                    0.35,
                ),
            ),
            0.0,
        ),
        resource_quality_average_weight=max(
            _to_float(
                resource_quality_cfg.get("average_weight")
                if not _is_missing(resource_quality_cfg.get("average_weight"))
                else _env_value("PUBLISHER_DISCOVERY_RESOURCE_QUALITY_AVERAGE_WEIGHT"),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
                        "resource_quality_ranking",
                        "average_weight",
                        fallback=0.50,
                    ),
                    0.50,
                ),
            ),
            0.0,
        ),
        resource_quality_confidence_weight=max(
            _to_float(
                resource_quality_cfg.get("confidence_weight")
                if not _is_missing(resource_quality_cfg.get("confidence_weight"))
                else _env_value(
                    "PUBLISHER_DISCOVERY_RESOURCE_QUALITY_CONFIDENCE_WEIGHT"
                ),
                _to_float(
                    _default_config_value(
                        "publisher_discovery",
                        "resource_quality_ranking",
                        "confidence_weight",
                        fallback=0.15,
                    ),
                    0.15,
                ),
            ),
            0.0,
        ),
        resource_quality_low_score_demotion_threshold=_to_float(
            resource_quality_cfg.get("low_score_demotion_threshold")
            if not _is_missing(resource_quality_cfg.get("low_score_demotion_threshold"))
            else _env_value(
                "PUBLISHER_DISCOVERY_RESOURCE_QUALITY_LOW_SCORE_DEMOTION_THRESHOLD"
            ),
            _to_float(
                _default_config_value(
                    "publisher_discovery",
                    "resource_quality_ranking",
                    "low_score_demotion_threshold",
                    fallback=45.0,
                ),
                45.0,
            ),
        ),
        cost_ledger_path=analysis_settings["cost_ledger_path"],
        cost_daily_path=analysis_settings["cost_daily_path"],
        model_pricing=analysis_settings["model_pricing"],
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
    )

    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.reports_db).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.cost_ledger_path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.cost_daily_path).parent.mkdir(parents=True, exist_ok=True)
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
                "command_time_budget_seconds": settings.command_time_budget_seconds,
                "headed": settings.headed,
                "force_browser": settings.force_browser,
                "enable_deferred_candidate_recovery": settings.enable_deferred_candidate_recovery,
                "enable_structured_route_reuse": settings.enable_structured_route_reuse,
                "enable_preflight_classifier_and_direct_detail": settings.enable_preflight_classifier_and_direct_detail,
                "retry_retries": settings.retry_retries,
                "retry_base_delay_seconds": settings.retry_base_delay_seconds,
                "retry_backoff_step_seconds": settings.retry_backoff_step_seconds,
                "retry_jitter_seconds": settings.retry_jitter_seconds,
                "candidate_screening_enabled": settings.candidate_screening_enabled,
                "candidate_screening_model": settings.candidate_screening_model,
                "candidate_screening_temperature": settings.candidate_screening_temperature,
                "candidate_screening_timeout_seconds": settings.candidate_screening_timeout_seconds,
                "candidate_screening_batch_size": settings.candidate_screening_batch_size,
                "candidate_screening_prompt_namespace": settings.candidate_screening_prompt_namespace,
                "candidate_quality_check_enabled": settings.candidate_quality_check_enabled,
                "candidate_quality_check_timeout_seconds": settings.candidate_quality_check_timeout_seconds,
                "candidate_quality_check_max_workers": settings.candidate_quality_check_max_workers,
                "resource_quality_ranking_enabled": settings.resource_quality_ranking_enabled,
                "resource_quality_score_window_size": settings.resource_quality_score_window_size,
                "resource_quality_min_sample_size": settings.resource_quality_min_sample_size,
                "resource_quality_consistency_weight": settings.resource_quality_consistency_weight,
                "resource_quality_average_weight": settings.resource_quality_average_weight,
                "resource_quality_confidence_weight": settings.resource_quality_confidence_weight,
                "resource_quality_low_score_demotion_threshold": settings.resource_quality_low_score_demotion_threshold,
                "llm_retry_retries": llm_runtime["llm_retry_retries"],
                "llm_retry_base_delay_seconds": llm_runtime[
                    "llm_retry_base_delay_seconds"
                ],
                "llm_retry_backoff_step_seconds": llm_runtime[
                    "llm_retry_backoff_step_seconds"
                ],
                "llm_retry_jitter_seconds": llm_runtime["llm_retry_jitter_seconds"],
            },
        )
    )
    return settings


__all__ = [name for name in globals() if not name.startswith("__")]
