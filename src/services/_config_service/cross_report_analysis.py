from __future__ import annotations

from src.services._config_service.common import *


def _raise_cross_report_config_error(field_name: str, value: Any, reason: str) -> None:
    raise AppError(
        code="cross_report_analysis_config_invalid",
        message=f"Invalid cross_report_analysis.{field_name}: {reason}",
        retryable=False,
        severity="error",
        context={"field": field_name, "value": value, "reason": reason},
    )


def _positive_int(
    section: dict[str, Any],
    *,
    field_name: str,
    config_key: str,
    default: int,
    minimum: int = 1,
) -> int:
    if config_key not in section:
        raw_value = None
        value = default
    else:
        raw_value = section[config_key]
        try:
            if isinstance(raw_value, bool):
                raise ValueError
            value = int(raw_value)
            if isinstance(raw_value, float) and not raw_value.is_integer():
                raise ValueError
        except (TypeError, ValueError):
            _raise_cross_report_config_error(
                field_name,
                raw_value,
                "must be an integer",
            )
            return default
    if value < minimum:
        _raise_cross_report_config_error(
            field_name,
            raw_value,
            f"must be >= {minimum}",
        )
    return value


def _positive_float(
    section: dict[str, Any],
    *,
    field_name: str,
    config_key: str,
    default: float,
    minimum: float,
) -> float:
    raw_value = section.get(config_key)
    value = _to_float(raw_value, default)
    if value < minimum:
        _raise_cross_report_config_error(
            field_name,
            raw_value,
            f"must be >= {minimum}",
        )
    return value


def _required_string(
    section: dict[str, Any],
    *,
    field_name: str,
    config_key: str,
    default: str,
) -> str:
    if config_key not in section:
        return default
    raw_value = section[config_key]
    if not isinstance(raw_value, str) or not raw_value.strip():
        _raise_cross_report_config_error(
            field_name, raw_value, "required non-blank string"
        )
        return default
    return raw_value.strip()


_DEFAULT_SIGNAL_SCORE_WEIGHTS = {
    "contradiction": 0.5,
    "diversity": 1.0,
    "recency": 1.0,
    "recurrence": 1.0,
    "support": 1.0,
    "taxonomy_fit": 1.0,
}


def _signal_score_weights(section: dict[str, Any]) -> dict[str, float]:
    default_weights = dict(
        _default_config_value(
            "cross_report_analysis",
            "signal_score_weights",
            fallback=_DEFAULT_SIGNAL_SCORE_WEIGHTS,
        )
        or _DEFAULT_SIGNAL_SCORE_WEIGHTS
    )
    weights = {
        key: _to_float(default_weights.get(key), default_value)
        for key, default_value in _DEFAULT_SIGNAL_SCORE_WEIGHTS.items()
    }
    raw_weights = section.get("signal_score_weights") or {}
    if not isinstance(raw_weights, dict):
        _raise_cross_report_config_error(
            "signal_score_weights",
            raw_weights,
            "must be a mapping",
        )
    for key, raw_value in raw_weights.items():
        if key not in weights:
            _raise_cross_report_config_error(
                "signal_score_weights",
                raw_weights,
                f"unknown weight {key}",
            )
        value = _to_float(raw_value, weights[key])
        if value < 0:
            _raise_cross_report_config_error(
                "signal_score_weights",
                raw_weights,
                f"{key} must be >= 0",
            )
        weights[key] = value
    return dict(sorted(weights.items()))


def _resolve_cross_report_analysis_settings(
    cross_report_cfg: dict[str, Any],
) -> dict[str, Any]:
    return {
        "cross_report_analysis_enabled": _to_config_bool(
            cross_report_cfg.get("enabled"),
            _to_config_bool(
                _default_config_value(
                    "cross_report_analysis", "enabled", fallback=False
                ),
                False,
            ),
        ),
        "cross_report_analysis_max_source_reports": _positive_int(
            cross_report_cfg,
            field_name="max_source_reports",
            config_key="max_source_reports",
            default=_to_int(
                _default_config_value(
                    "cross_report_analysis", "max_source_reports", fallback=6
                ),
                6,
            ),
        ),
        "cross_report_analysis_max_evidence_items": _positive_int(
            cross_report_cfg,
            field_name="max_evidence_items",
            config_key="max_evidence_items",
            default=_to_int(
                _default_config_value(
                    "cross_report_analysis", "max_evidence_items", fallback=48
                ),
                48,
            ),
        ),
        "cross_report_analysis_max_prompt_chars": _positive_int(
            cross_report_cfg,
            field_name="max_prompt_chars",
            config_key="max_prompt_chars",
            default=_to_int(
                _default_config_value(
                    "cross_report_analysis", "max_prompt_chars", fallback=60000
                ),
                60000,
            ),
        ),
        "cross_report_analysis_prompt_namespace": _required_string(
            cross_report_cfg,
            field_name="prompt_namespace",
            config_key="prompt_namespace",
            default=str(
                _default_config_value(
                    "cross_report_analysis",
                    "prompt_namespace",
                    fallback="cross_report_analysis/synthesis",
                )
            ),
        ),
        "cross_report_analysis_model": _required_string(
            cross_report_cfg,
            field_name="model",
            config_key="model",
            default=str(
                _default_config_value(
                    "cross_report_analysis", "model", fallback="gpt-5.6-luna"
                )
            ),
        ),
        "cross_report_analysis_temperature": _to_float(
            cross_report_cfg.get("temperature"),
            _to_float(
                _default_config_value(
                    "cross_report_analysis", "temperature", fallback=1.0
                ),
                1.0,
            ),
        ),
        "cross_report_analysis_timeout_seconds": _positive_float(
            cross_report_cfg,
            field_name="timeout_seconds",
            config_key="timeout_seconds",
            default=_to_float(
                _default_config_value(
                    "cross_report_analysis", "timeout_seconds", fallback=600.0
                ),
                600.0,
            ),
            minimum=1.0,
        ),
        "cross_report_analysis_cache_enabled": _to_config_bool(
            cross_report_cfg.get("cache_enabled"),
            _to_config_bool(
                _default_config_value(
                    "cross_report_analysis", "cache_enabled", fallback=True
                ),
                True,
            ),
        ),
        "cross_report_analysis_auto_theme_enabled": _to_config_bool(
            cross_report_cfg.get("auto_theme_enabled"),
            _to_config_bool(
                _default_config_value(
                    "cross_report_analysis", "auto_theme_enabled", fallback=True
                ),
                True,
            ),
        ),
        "cross_report_analysis_theme_rotation_window_days": _positive_int(
            cross_report_cfg,
            field_name="theme_rotation_window_days",
            config_key="theme_rotation_window_days",
            default=_to_int(
                _default_config_value(
                    "cross_report_analysis",
                    "theme_rotation_window_days",
                    fallback=30,
                ),
                30,
            ),
            minimum=0,
        ),
        "cross_report_analysis_min_theme_source_publishers": _positive_int(
            cross_report_cfg,
            field_name="min_theme_source_publishers",
            config_key="min_theme_source_publishers",
            default=_to_int(
                _default_config_value(
                    "cross_report_analysis",
                    "min_theme_source_publishers",
                    fallback=2,
                ),
                2,
            ),
        ),
        "cross_report_analysis_publish_enabled": _to_config_bool(
            cross_report_cfg.get("publish_enabled"),
            _to_config_bool(
                _default_config_value(
                    "cross_report_analysis", "publish_enabled", fallback=False
                ),
                False,
            ),
        ),
        "cross_report_analysis_publish_requires_validation_pass": _to_config_bool(
            cross_report_cfg.get("publish_requires_validation_pass"),
            _to_config_bool(
                _default_config_value(
                    "cross_report_analysis",
                    "publish_requires_validation_pass",
                    fallback=True,
                ),
                True,
            ),
        ),
        "cross_report_analysis_signal_score_weights": _signal_score_weights(
            cross_report_cfg
        ),
    }


__all__ = [name for name in globals() if not name.startswith("__")]
