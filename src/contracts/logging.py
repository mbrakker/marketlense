from __future__ import annotations

from dataclasses import dataclass, field


LOG_EVENT_SCHEMA_VERSION = "1.1"
REQUIRED_LOG_EVENT_FIELDS = frozenset(
    {
        "run_id",
        "task_id",
        "span_id",
        "trace_id",
        "parent_span_id",
        "span_name",
        "span_depth",
        "timestamp_utc",
        "module",
        "role",
        "event",
    }
)
LOG_EVENT_ROLES = frozenset({"service", "generator", "orchestrator", "utility", "ui"})


@dataclass(frozen=True)
class LoggingSetupRequest:
    schema_version: str = field(
        metadata={"doc": "Logging setup request schema version."}
    )
    level: int = field(
        default=20,
        metadata={"doc": "Python logging level integer (e.g., logging.INFO)."},
    )


@dataclass(frozen=True)
class LoggingSetupResponse:
    schema_version: str = field(
        metadata={"doc": "Logging setup response schema version."}
    )
    level: int = field(metadata={"doc": "Applied logging level."})
    log_dir: str = field(metadata={"doc": "Directory where log files are written."})
    log_path: str = field(metadata={"doc": "Resolved log file path."})
    use_rich: bool = field(metadata={"doc": "Whether rich console logging is enabled."})


@dataclass(frozen=True)
class LogEventValidationResult:
    schema_version: str = field(
        metadata={"doc": "Log event validation result schema version."}
    )
    valid: bool = field(
        metadata={"doc": "True when the log event matches shape rules."}
    )
    missing_fields: tuple[str, ...] = field(
        metadata={"doc": "Required top-level log fields missing from the payload."}
    )
    invalid_fields: tuple[str, ...] = field(
        metadata={"doc": "Present fields with invalid values or types."}
    )
