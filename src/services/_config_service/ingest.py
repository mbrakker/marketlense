from __future__ import annotations

# Compatibility resolver facade intentionally shares the common configuration helpers.
# ruff: noqa: F403, F405
from src.services._config_service.common import *


def _resolve_ingest_runtime_settings(
    ingest: dict[str, Any],
) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        ingest,
        [
            _SettingSpec(
                field_name="temperature",
                config_key="temperature",
                default=_to_float(
                    _default_config_value("ingest", "temperature", fallback=1.0), 1.0
                ),
                coerce=_to_float,
                env_key="TEMPERATURE",
            ),
            _SettingSpec(
                field_name="batch_limit",
                config_key="batch_limit",
                default=_to_int(
                    _default_config_value("ingest", "batch_limit", fallback=20), 20
                ),
                coerce=_to_int,
                env_key="BATCH_LIMIT",
            ),
            _SettingSpec(
                field_name="ingest_worker_limit",
                config_key="worker_limit",
                default=_to_int(
                    _default_config_value("ingest", "worker_limit", fallback=2), 2
                ),
                coerce=_to_int,
                env_key="INGEST_WORKER_LIMIT",
                minimum=1,
            ),
            _SettingSpec(
                field_name="report_worker_limit",
                config_key="report_worker_limit",
                default=_to_int(
                    _default_config_value("ingest", "report_worker_limit", fallback=2),
                    2,
                ),
                coerce=_to_int,
                env_key="INGEST_REPORT_WORKER_LIMIT",
                minimum=1,
            ),
            _SettingSpec(
                field_name="openai_timeout_seconds",
                config_key="timeout_seconds",
                default=_to_float(
                    _default_config_value("ingest", "timeout_seconds", fallback=600.0),
                    600.0,
                ),
                coerce=_to_float,
                env_key="OPENAI_TIMEOUT_SECONDS",
            ),
            _SettingSpec(
                field_name="ingest_lock_ttl_seconds",
                config_key="lock_ttl_seconds",
                default=_to_float(
                    _default_config_value(
                        "ingest", "lock_ttl_seconds", fallback=7200.0
                    ),
                    7200.0,
                ),
                coerce=_to_float,
                env_key="INGEST_LOCK_TTL_SECONDS",
            ),
            _SettingSpec(
                field_name="taxonomy_temperature",
                config_key="taxonomy_temperature",
                default=_to_float(
                    _default_config_value(
                        "ingest", "taxonomy_temperature", fallback=0.0
                    ),
                    0.0,
                ),
                coerce=_to_float,
                env_key="TAXONOMY_TEMPERATURE",
                env_first=True,
            ),
        ],
    )
    run_budget_cfg = ingest.get("run_budget", {}) or {}
    if not isinstance(run_budget_cfg, dict):
        run_budget_cfg = {}
    resolved["run_budget_max_pdfs"] = _optional_positive_int(
        run_budget_cfg.get("max_pdfs")
    )
    resolved["run_budget_max_retries"] = _optional_nonnegative_int(
        run_budget_cfg.get("max_retries")
    )
    resolved["run_budget_max_runtime_seconds"] = _optional_positive_int(
        run_budget_cfg.get("max_runtime_seconds")
    )
    resolved["run_budget_enabled_effect_kinds"] = tuple(
        str(effect).strip()
        for effect in (run_budget_cfg.get("enabled_effect_kinds") or [])
        if str(effect).strip()
    )
    resolved["run_budget_limit_decision"] = str(
        run_budget_cfg.get("limit_decision") or "stop"
    ).strip().lower()
    resolved["taxonomy_temperature"] = _to_float(
        _resolve_setting_raw(
            ingest,
            _SettingSpec(
                field_name="taxonomy_temperature",
                config_key="taxonomy_temperature",
                default=resolved["temperature"],
                coerce=_to_float,
                env_key="TAXONOMY_TEMPERATURE",
                env_first=True,
            ),
        ),
        resolved["temperature"],
    )
    resolved["openai_seed"] = _opt_int(ingest.get("seed"))
    quarantine_cfg = ingest.get("source_quarantine") or {}
    if not isinstance(quarantine_cfg, dict):
        quarantine_cfg = {}
    resolved["source_quarantine_enabled"] = _to_bool(
        quarantine_cfg.get("enabled"), True
    )
    return resolved


def _optional_positive_int(value: object) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return max(_to_int(value, 0), 1)


def _optional_nonnegative_int(value: object) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return max(_to_int(value, 0), 0)


__all__ = [name for name in globals() if not name.startswith("__")]
