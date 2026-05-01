from __future__ import annotations

from src.services._config_service.common import *

def _resolve_analysis_settings(
    analysis_cfg: dict[str, Any],
    cost_cfg: dict[str, Any],
    *,
    html_tag_acronyms_path: str,
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
    resolved["cost_ledger_path"] = str(
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
        )
    )
    resolved["cost_daily_path"] = str(
        cost_cfg.get("daily_path")
        or _default_config_value("cost", "daily_path", fallback="./out/cost-daily.json")
    )
    resolved["model_pricing"] = cost_cfg.get("pricing") or _default_config_value(
        "cost", "pricing", fallback={}
    )
    resolved["html_tag_acronyms"] = _load_html_tag_acronyms(html_tag_acronyms_path)
    return resolved

__all__ = [name for name in globals() if not name.startswith("__")]
