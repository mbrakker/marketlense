from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LoggingSetupRequest:
    schema_version: str = field(metadata={"doc": "Logging setup request schema version."})
    level: int = field(default=20, metadata={"doc": "Python logging level integer (e.g., logging.INFO)."})


@dataclass(frozen=True)
class LoggingSetupResponse:
    schema_version: str = field(metadata={"doc": "Logging setup response schema version."})
    level: int = field(metadata={"doc": "Applied logging level."})
    log_dir: str = field(metadata={"doc": "Directory where log files are written."})
    log_path: str = field(metadata={"doc": "Resolved log file path."})
    use_rich: bool = field(metadata={"doc": "Whether rich console logging is enabled."})
