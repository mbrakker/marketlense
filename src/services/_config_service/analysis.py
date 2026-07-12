from __future__ import annotations

# ruff: noqa: F403, F405
from src.services._config_service.common import *


def _resolve_analysis_settings(
    analysis_cfg: dict[str, Any],
    cost_cfg: dict[str, Any],
    *,
    html_tag_acronyms_path: str,
    runtime_base_path: Path,
) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        analysis_cfg,
        [
            _SettingSpec(
                field_name="vector_store_keep",
                config_key="vector_store_keep",
                default=_to_config_bool(
                    _default_config_value(
                        "analysis", "vector_store_keep", fallback=True
                    ),
                    True,
                ),
                coerce=_to_config_bool,
                env_key="VECTOR_STORE_KEEP",
                env_first=True,
            ),
            _SettingSpec(
                field_name="artifacts_use_vector_store",
                config_key="artifacts_use_vector_store",
                default=_to_config_bool(
                    _default_config_value(
                        "analysis", "artifacts_use_vector_store", fallback=False
                    ),
                    False,
                ),
                coerce=_to_config_bool,
                env_key="ARTIFACTS_USE_VECTOR_STORE",
                env_first=True,
            ),
            _SettingSpec(
                field_name="vector_store_retention_days",
                config_key="vector_store_retention_days",
                default=int(
                    _default_config_value(
                        "analysis", "vector_store_retention_days", fallback=30
                    )
                    or 30
                ),
                coerce=_to_int,
                env_key="VECTOR_STORE_RETENTION_DAYS",
                env_first=True,
                minimum=0,
            ),
            _SettingSpec(
                field_name="validation_grounding_use_vector_store",
                config_key="validation_grounding_use_vector_store",
                default=_to_config_bool(
                    _default_config_value(
                        "analysis",
                        "validation_grounding_use_vector_store",
                        fallback=False,
                    ),
                    False,
                ),
                coerce=_to_config_bool,
                env_key="VALIDATION_GROUNDING_USE_VECTOR_STORE",
                env_first=True,
            ),
            _SettingSpec(
                field_name="strict_schema_validation",
                config_key="strict_schema_validation",
                default=_to_config_bool(
                    _default_config_value(
                        "analysis", "strict_schema_validation", fallback=True
                    ),
                    True,
                ),
                coerce=_to_config_bool,
                env_key="STRICT_SCHEMA_VALIDATION",
                env_first=True,
            ),
        ],
    )
    resolved["cost_ledger_path"] = _resolve_optional_path(
        _resolve_setting_raw(
            analysis_cfg,
            _SettingSpec(
                field_name="cost_ledger_path",
                config_key="cost_ledger_path",
                default=str(
                    _default_config_value(
                        "analysis",
                        "cost_ledger_path",
                        fallback="./out/cost-ledger.jsonl",
                    )
                ),
                coerce=_to_str,
                env_key="COST_LEDGER_PATH",
                env_first=True,
            ),
        )
        or str(
            _default_config_value(
                "analysis", "cost_ledger_path", fallback="./out/cost-ledger.jsonl"
            )
        ),
        base_path=runtime_base_path,
    )
    resolved["cost_daily_path"] = _resolve_optional_path(
        cost_cfg.get("daily_path")
        or _env_value("COST_DAILY_PATH")
        or _default_config_value(
            "cost", "daily_path", fallback="./out/cost-daily.json"
        ),
        base_path=runtime_base_path,
    )
    resolved["usage_db_path"] = _resolve_optional_path(
        _resolve_setting_raw(
            cost_cfg,
            _SettingSpec(
                field_name="usage_db_path",
                config_key="usage_db_path",
                default=str(
                    _default_config_value(
                        "cost", "usage_db_path", fallback="./state/llm_usage.sqlite"
                    )
                ),
                coerce=_to_str,
                env_key="LLM_USAGE_DB_PATH",
                env_first=True,
            ),
        )
        or "./state/llm_usage.sqlite",
        base_path=runtime_base_path,
    )
    resolved["model_pricing"] = cost_cfg.get("pricing") or _default_config_value(
        "cost", "pricing", fallback={}
    )
    resolved["html_tag_acronyms"] = _load_html_tag_acronyms(html_tag_acronyms_path)
    return resolved


__all__ = [name for name in globals() if not name.startswith("__")]
