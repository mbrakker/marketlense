from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.contracts.run_context import RunContext


@dataclass(frozen=True)
class LLMContextCompactionPolicy:
    schema_version: str = field(
        metadata={"doc": "LLM context-compaction policy schema version."}
    )
    enabled: bool = field(
        default=False,
        metadata={"doc": "Whether deterministic prompt context compaction is enabled."},
    )
    max_input_tokens: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Estimated input-token ceiling that triggers compaction when exceeded."
        },
    )
    max_estimated_input_cost_usd: Optional[float] = field(
        default=None,
        metadata={
            "doc": "Estimated total prompt-call cost ceiling that triggers compaction when exceeded."
        },
    )
    expected_output_tokens: int = field(
        default=0,
        metadata={
            "doc": "Expected output-token budget used only for pre-call cost estimation."
        },
    )
    strategy: str = field(
        default="anchor_preserving_head_tail",
        metadata={
            "doc": "Deterministic compaction strategy; currently anchor_preserving_head_tail."
        },
    )
    max_anchor_lines: int = field(
        default=40,
        metadata={
            "doc": "Maximum anchor lines retained before head/tail context is added."
        },
    )
    min_tail_lines: int = field(
        default=8,
        metadata={
            "doc": "Minimum tail-context lines preferred when compaction has remaining budget."
        },
    )


@dataclass(frozen=True)
class LLMContextCompactionResult:
    schema_version: str = field(
        metadata={"doc": "LLM context-compaction result schema version."}
    )
    compacted: bool = field(metadata={"doc": "Whether the user prompt was compacted."})
    strategy: str = field(metadata={"doc": "Compaction strategy applied."})
    trigger_reason: str = field(
        metadata={"doc": "Budget trigger reason or skip reason."}
    )
    original_input_tokens_est: int = field(
        metadata={"doc": "Estimated system + user input tokens before compaction."}
    )
    compacted_input_tokens_est: int = field(
        metadata={"doc": "Estimated system + user input tokens after compaction."}
    )
    avoided_input_tokens_est: int = field(
        metadata={"doc": "Estimated input tokens avoided by compaction."}
    )
    estimated_original_cost_usd: float = field(
        metadata={"doc": "Estimated pre-compaction model-call cost."}
    )
    estimated_compacted_cost_usd: float = field(
        metadata={"doc": "Estimated compacted model-call cost."}
    )
    estimated_avoided_cost_usd: float = field(
        metadata={"doc": "Estimated cost avoided by compaction."}
    )
    retained_anchor_count: int = field(
        metadata={"doc": "Number of required anchor lines retained."}
    )
    original_user_chars: int = field(
        metadata={"doc": "Original user-prompt character count."}
    )
    compacted_user_chars: int = field(
        metadata={"doc": "Compacted user-prompt character count."}
    )


@dataclass(frozen=True)
class LLMClientPolicy:
    schema_version: str = field(metadata={"doc": "LLM client policy schema version."})
    scope: str = field(
        metadata={
            "doc": "Stable scope name used for circuit-breaker and rate-limit state."
        }
    )
    retries: int = field(
        default=0,
        metadata={
            "doc": "Legacy compatibility value; ignored because orchestrators own retries."
        },
    )
    base_delay_seconds: float = field(
        default=0.0,
        metadata={
            "doc": "Legacy compatibility value; service retry delay is disabled."
        },
    )
    backoff_step_seconds: float = field(
        default=0.0,
        metadata={"doc": "Legacy compatibility value; service backoff is disabled."},
    )
    jitter_seconds: float = field(
        default=0.0,
        metadata={
            "doc": "Legacy compatibility value; service retry jitter is disabled."
        },
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
    openrouter_chat_json: Optional[Callable[[Any, RunContext], Any]] = field(
        default=None,
        metadata={
            "doc": "Optional OpenRouter JSON chat fallback operation returning the same response contract."
        },
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
