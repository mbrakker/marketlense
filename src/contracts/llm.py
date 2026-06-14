from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.contracts.run_context import RunContext


@dataclass(frozen=True)
class LLMClientPolicy:
    schema_version: str = field(metadata={"doc": "LLM client policy schema version."})
    scope: str = field(
        metadata={
            "doc": "Stable scope name used for circuit-breaker and rate-limit state."
        }
    )
    retries: int = field(
        default=1,
        metadata={"doc": "Maximum retry count after the initial LLM call attempt."},
    )
    base_delay_seconds: float = field(
        default=1.0,
        metadata={"doc": "Base delay in seconds before the first retry."},
    )
    backoff_step_seconds: float = field(
        default=1.0,
        metadata={"doc": "Additional linear backoff delay added per retry attempt."},
    )
    jitter_seconds: float = field(
        default=0.25,
        metadata={"doc": "Maximum random jitter in seconds added to retry delays."},
    )
    rate_limit_max_in_flight: Optional[int] = field(
        default=None,
        metadata={"doc": "Optional global in-flight concurrency cap for this scope."},
    )
    rate_limit_min_interval_ms: int = field(
        default=0,
        metadata={
            "doc": "Optional minimum interval between call starts for this scope."
        },
    )
    circuit_breaker_failure_threshold: int = field(
        default=3,
        metadata={
            "doc": "Consecutive retryable failures required to open the circuit."
        },
    )
    circuit_breaker_recovery_seconds: float = field(
        default=30.0,
        metadata={"doc": "Cooldown in seconds before allowing a half-open probe call."},
    )


@dataclass(frozen=True)
class LLMProviderOperations:
    schema_version: str = field(
        metadata={"doc": "Provider operation bundle schema version."}
    )
    openai_chat_json: Optional[Callable[[Any, RunContext], Any]] = field(
        default=None,
        metadata={"doc": "Configured JSON chat provider operation."},
    )
    openai_chat_json_with_images: Optional[Callable[[Any, RunContext], Any]] = field(
        default=None,
        metadata={"doc": "Configured multimodal JSON provider operation."},
    )
    openai_ocr_pdf: Optional[Callable[[Any, RunContext], Any]] = field(
        default=None,
        metadata={"doc": "Configured PDF OCR provider operation."},
    )
    openai_respond_with_vector_store: Optional[Callable[[Any, RunContext], Any]] = (
        field(
            default=None,
            metadata={"doc": "Configured vector-store response provider operation."},
        )
    )
