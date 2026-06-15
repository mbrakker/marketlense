from __future__ import annotations

from src.services._config_service.common import *


def _resolve_llm_runtime_settings(llm_cfg: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_scalar_settings(
        llm_cfg,
        [
            _SettingSpec(
                field_name="llm_retry_retries",
                config_key="retries",
                default=_to_int(
                    _default_config_value("ingest", "llm", "retries", fallback=0), 0
                ),
                coerce=_to_int,
                minimum=0,
            ),
            _SettingSpec(
                field_name="llm_retry_base_delay_seconds",
                config_key="base_delay_seconds",
                default=_to_float(
                    _default_config_value(
                        "ingest", "llm", "base_delay_seconds", fallback=0.0
                    ),
                    0.0,
                ),
                coerce=_to_float,
                minimum=0.0,
            ),
            _SettingSpec(
                field_name="llm_retry_backoff_step_seconds",
                config_key="backoff_step_seconds",
                default=_to_float(
                    _default_config_value(
                        "ingest", "llm", "backoff_step_seconds", fallback=0.0
                    ),
                    0.0,
                ),
                coerce=_to_float,
                minimum=0.0,
            ),
            _SettingSpec(
                field_name="llm_retry_jitter_seconds",
                config_key="jitter_seconds",
                default=_to_float(
                    _default_config_value(
                        "ingest", "llm", "jitter_seconds", fallback=0.0
                    ),
                    0.0,
                ),
                coerce=_to_float,
                minimum=0.0,
            ),
            _SettingSpec(
                field_name="llm_circuit_breaker_failure_threshold",
                config_key="circuit_breaker_failure_threshold",
                default=_to_int(
                    _default_config_value(
                        "ingest",
                        "llm",
                        "circuit_breaker_failure_threshold",
                        fallback=3,
                    ),
                    3,
                ),
                coerce=_to_int,
                minimum=0,
            ),
            _SettingSpec(
                field_name="llm_circuit_breaker_recovery_seconds",
                config_key="circuit_breaker_recovery_seconds",
                default=_to_float(
                    _default_config_value(
                        "ingest",
                        "llm",
                        "circuit_breaker_recovery_seconds",
                        fallback=30.0,
                    ),
                    30.0,
                ),
                coerce=_to_float,
                minimum=0.0,
            ),
        ],
    )
    configured_retry_values = {
        "retries": int(resolved["llm_retry_retries"]),
        "base_delay_seconds": float(resolved["llm_retry_base_delay_seconds"]),
        "backoff_step_seconds": float(resolved["llm_retry_backoff_step_seconds"]),
        "jitter_seconds": float(resolved["llm_retry_jitter_seconds"]),
    }
    if any(value != 0 for value in configured_retry_values.values()):
        raise AppError(
            code="llm_service_retry_config_forbidden",
            message="LLM service retry settings must be zero; orchestrators own retries",
            retryable=False,
            context={
                "configured_retry_values": configured_retry_values,
                "retry_owner": "orchestrator",
            },
        )
    return resolved


__all__ = [name for name in globals() if not name.startswith("__")]
