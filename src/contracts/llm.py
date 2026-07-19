from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from src.contracts.run_context import RunContext


@dataclass(frozen=True)
class LLMRoutingPolicy:
    schema_version: str = field(metadata={"doc": "LLM routing-policy schema version."})
    model: str = field(metadata={"doc": "Provider-local model selected for scope."})
    tier: str = field(metadata={"doc": "Quality/cost tier selected for scope."})
    max_input_tokens: int = field(
        metadata={"doc": "Maximum input-token budget before deterministic compaction."}
    )
    compaction_enabled: bool = field(
        metadata={"doc": "Whether anchor-preserving compaction is permitted."}
    )
    quality_threshold: float = field(
        metadata={"doc": "Minimum quality threshold required for the selected tier."}
    )
    same_provider_fallback: bool = field(
        metadata={
            "doc": "Whether retry fallback must remain with the selected provider."
        }
    )


@dataclass(frozen=True)
class LLMRoutingDecision:
    schema_version: str = field(
        metadata={"doc": "Resolved LLM routing-decision schema version."}
    )
    namespace: str = field(metadata={"doc": "Normalized prompt namespace."})
    model: str = field(metadata={"doc": "Resolved provider-local model."})
    tier: str = field(metadata={"doc": "Resolved routing tier."})
    max_input_tokens: int = field(metadata={"doc": "Resolved input-token budget."})
    compaction_enabled: bool = field(
        metadata={"doc": "Resolved compaction permission."}
    )
    quality_threshold: float = field(metadata={"doc": "Resolved quality threshold."})
    same_provider_fallback: bool = field(
        metadata={"doc": "Resolved provider-fallback constraint."}
    )
    policy_source: str = field(
        metadata={"doc": "Longest-prefix policy key or default source."}
    )


SeedPolicy = Literal["inherit", "fixed", "disabled"]
FallbackPolicy = Literal["same_provider_only", "disabled"]


@dataclass(frozen=True)
class LLMExecutionPolicy:
    """Versioned, namespace-scoped controls for one model invocation.

    The policy deliberately contains only provider-call compatibility controls.
    Orchestrators retain retry scheduling and budget authority.
    """

    schema_version: str = field(metadata={"doc": "Execution-policy schema version."})
    namespace_prefix: str = field(
        metadata={"doc": "Normalized exact namespace or prefix governed by policy."}
    )
    provider: str = field(metadata={"doc": "Approved provider identifier."})
    model: str = field(metadata={"doc": "Provider-local model identifier."})
    temperature: float = field(metadata={"doc": "Sampling temperature."})
    seed_policy: SeedPolicy = field(
        default="inherit", metadata={"doc": "How the configured seed is resolved."}
    )
    seed: Optional[int] = field(
        default=None, metadata={"doc": "Fixed seed when seed_policy is fixed."}
    )
    max_output_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Maximum output tokens when supported."}
    )
    reasoning_effort: str = field(
        default="", metadata={"doc": "Provider reasoning configuration when supported."}
    )
    structured_output_mode: str = field(
        default="json_object", metadata={"doc": "Configured structured output mode."}
    )
    structured_output_schema_identity: str = field(
        default="", metadata={"doc": "Stable output-schema identity, never raw schema."}
    )
    output_validator_identity: str = field(
        default="",
        metadata={
            "doc": "Stable validator identity applied to structured output, never validator source."
        },
    )
    retrieval_mode: str = field(
        default="inherit",
        metadata={
            "doc": "Configured retrieval mode or inherit for the call-site capability."
        },
    )
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Provider request timeout."}
    )
    provider_retry_count: int = field(
        default=0,
        metadata={"doc": "Provider retry count; runtime services keep this at zero."},
    )
    max_input_tokens: int = field(
        default=0, metadata={"doc": "Input/compaction budget; zero disables limit."}
    )
    compaction_enabled: bool = field(
        default=False, metadata={"doc": "Whether deterministic compaction is allowed."}
    )
    fallback_policy: FallbackPolicy = field(
        default="same_provider_only",
        metadata={"doc": "Explicit provider fallback constraint."},
    )
    pricing_key: str = field(
        default="", metadata={"doc": "Pricing configuration key; defaults to model."}
    )


@dataclass(frozen=True)
class LLMExecutionPolicyDecision:
    """Resolved immutable policy plus its deterministic identity."""

    schema_version: str = field(metadata={"doc": "Resolved policy schema version."})
    namespace: str = field(metadata={"doc": "Normalized requested namespace."})
    policy_source: str = field(
        metadata={"doc": "Matched prefix or compatibility source."}
    )
    policy: LLMExecutionPolicy = field(metadata={"doc": "Resolved execution policy."})
    policy_hash: str = field(
        metadata={"doc": "Stable hash of canonical policy fields."}
    )
    compatibility_mode: bool = field(
        default=False,
        metadata={"doc": "Whether old global settings supplied an unmigrated policy."},
    )


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


@dataclass(frozen=True)
class BrowserUseLLMClients:
    schema_version: str = field(
        metadata={"doc": "Browser-use LLM client bundle schema version."}
    )
    primary_provider: str = field(
        metadata={"doc": "Provider selected as the browser-use primary LLM."}
    )
    primary_model: str = field(
        metadata={"doc": "Model ID selected for the browser-use primary LLM."}
    )
    primary_llm: Any = field(
        metadata={"doc": "Constructed browser-use primary chat client object."}
    )
    fallback_provider: Optional[str] = field(
        default=None,
        metadata={"doc": "Provider selected as browser-use fallback LLM, if any."},
    )
    fallback_model: Optional[str] = field(
        default=None,
        metadata={"doc": "Model ID selected for the browser-use fallback LLM, if any."},
    )
    fallback_llm: Any = field(
        default=None,
        metadata={
            "doc": "Constructed browser-use fallback chat client object, if any."
        },
    )
