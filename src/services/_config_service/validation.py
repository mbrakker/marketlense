from __future__ import annotations

from src.services._config_service.common import *

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
    return resolved

__all__ = [name for name in globals() if not name.startswith("__")]
