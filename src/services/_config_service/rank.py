from __future__ import annotations

from src.services._config_service.common import *

def _resolve_rank_settings(
    rank: dict[str, Any],
    *,
    openai_model: str,
    temperature: float,
    openai_timeout_seconds: float,
) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        rank,
        [
            _SettingSpec(
                field_name="rank_temperature",
                config_key="temperature",
                default=temperature,
                coerce=_to_float,
            ),
            _SettingSpec(
                field_name="rank_max_candidates",
                config_key="max_candidates",
                default=_to_int(
                    _default_config_value("rank", "max_candidates", fallback=40), 40
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_selected_max",
                config_key="selected_max",
                default=_to_int(
                    _default_config_value("rank", "selected_max", fallback=5), 5
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_min_overall_score",
                config_key="min_overall_score",
                default=_to_int(
                    _default_config_value("rank", "min_overall_score", fallback=78),
                    78,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_min_quality_score",
                config_key="min_quality_score",
                default=_to_int(
                    _default_config_value("rank", "min_quality_score", fallback=75),
                    75,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_min_insight_score",
                config_key="min_insight_score",
                default=_to_int(
                    _default_config_value("rank", "min_insight_score", fallback=75),
                    75,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="rank_min_data_score",
                config_key="min_data_score",
                default=_to_int(
                    _default_config_value("rank", "min_data_score", fallback=70), 70
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="crop_refine_enabled",
                config_key="crop_refine_enabled",
                default=_to_config_bool(
                    _default_config_value("rank", "crop_refine_enabled", fallback=True),
                    True,
                ),
                coerce=_to_config_bool,
            ),
            _SettingSpec(
                field_name="crop_refine_page_dpi",
                config_key="crop_refine_page_dpi",
                default=_to_int(
                    _default_config_value("rank", "crop_refine_page_dpi", fallback=110),
                    110,
                ),
                coerce=_to_int,
            ),
            _SettingSpec(
                field_name="crop_refine_temperature",
                config_key="crop_refine_temperature",
                default=_to_float(
                    _default_config_value(
                        "rank", "crop_refine_temperature", fallback=0.0
                    ),
                    0.0,
                ),
                coerce=_to_float,
            ),
            _SettingSpec(
                field_name="rank_timeout_seconds",
                config_key="timeout_seconds",
                default=openai_timeout_seconds,
                coerce=_to_float,
            ),
        ],
    )
    resolved["rank_model"] = (
        str(rank.get("model") or "").strip()
        or str(_default_config_value("rank", "model", fallback="")).strip()
        or openai_model
    )
    resolved["rank_seed"] = _opt_int(rank.get("seed"))
    resolved["crop_refine_mode"] = _resolve_allowed_string(
        rank.get(
            "crop_refine_mode",
            _default_config_value("rank", "crop_refine_mode", fallback="adaptive"),
        ),
        default=str(
            _default_config_value("rank", "crop_refine_mode", fallback="adaptive")
        ),
        allowed={"adaptive", "always", "off"},
    )
    resolved["crop_refine_timeout_seconds"] = _to_float(
        rank.get("crop_refine_timeout_seconds"),
        resolved["rank_timeout_seconds"],
    )
    return resolved

__all__ = [name for name in globals() if not name.startswith("__")]
