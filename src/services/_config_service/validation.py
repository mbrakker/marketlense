from __future__ import annotations

from typing import Any

from src.services._config_service.common import (
    _default_config_value,
    _resolve_allowed_string,
    _resolve_scalar_settings,
    _SettingSpec,
    _to_int,
)


def _resolve_validation_settings(validation_cfg: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        validation_cfg,
        [
            _SettingSpec(
                field_name="validation_regeneration_max_attempts",
                config_key="regeneration_max_attempts",
                default=_to_int(
                    _default_config_value(
                        "ingest",
                        "validation",
                        "regeneration_max_attempts",
                        fallback=3,
                    ),
                    3,
                ),
                coerce=_to_int,
                env_key="VALIDATION_REGENERATION_MAX_ATTEMPTS",
                minimum=1,
            ),
        ],
    )
    resolved["validation_data_gap_policy"] = _resolve_allowed_string(
        validation_cfg.get(
            "data_gap_policy",
            _default_config_value(
                "ingest", "validation", "data_gap_policy", fallback="warn"
            ),
        ),
        default=str(
            _default_config_value(
                "ingest", "validation", "data_gap_policy", fallback="warn"
            )
        ),
        allowed={"warn", "fail"},
    )
    editorial_cfg = validation_cfg.get("public_editorial_quality", {})
    waivers = (
        editorial_cfg.get("disabled_rule_waivers", {})
        if isinstance(editorial_cfg, dict)
        else {}
    )
    if not isinstance(waivers, dict):
        waivers = {}
    resolved["public_editorial_quality_disabled_rule_waivers"] = {
        str(rule).strip(): str(reason).strip()
        for rule, reason in waivers.items()
        if str(rule).strip() and str(reason).strip()
    }
    return resolved


__all__ = [name for name in globals() if not name.startswith("__")]
