from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.contracts.llm import LLMContextCompactionPolicy
from src.contracts.pdf_ocr import PdfOcrPageText
from src.contracts.report_models import ReportPayload
from src.contracts.run_budget import RunBudget


@dataclass(frozen=True)
class OpenAIEmbeddingRequest:
    schema_version: str = field(
        metadata={"doc": "OpenAI embedding request schema version."}
    )
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    model: str = field(metadata={"doc": "OpenAI embedding model ID."})
    inputs: List[str] = field(metadata={"doc": "Ordered texts to embed."})
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )
    cost_ledger_path: str = field(
        default="./out/cost-ledger.jsonl",
        metadata={"doc": "Filesystem path for the cost ledger JSONL output."},
    )
    cost_daily_path: str = field(
        default="./out/cost-daily.json",
        metadata={"doc": "Filesystem path for daily cost rollups."},
    )
    model_pricing: dict = field(
        default_factory=dict,
        metadata={"doc": "Per-model pricing table for cost estimation."},
    )
    context_compaction_policy: LLMContextCompactionPolicy = field(
        default_factory=lambda: LLMContextCompactionPolicy(schema_version="1.0"),
        metadata={"doc": "Optional deterministic pre-call context compaction policy."},
    )
    publisher_name: str = field(
        default="", metadata={"doc": "Publisher context for usage reporting, if known."}
    )
    report_name: str = field(
        default="", metadata={"doc": "Report context for usage reporting, if known."}
    )
    source_url: str = field(
        default="",
        metadata={"doc": "Source/report URL context for usage reporting, if known."},
    )
    prompt_namespace: str = field(
        default="", metadata={"doc": "Prompt namespace for usage reporting, if known."}
    )
    prompt_hash: str = field(
        default="", metadata={"doc": "Prompt hash for usage reporting, if known."}
    )
    usage_db_path: str = field(
        default="./state/llm_usage.sqlite",
        metadata={"doc": "Canonical SQLite usage ledger path for this provider call."},
    )


@dataclass(frozen=True)
class OpenAIEmbeddingResponse:
    schema_version: str = field(
        metadata={"doc": "OpenAI embedding response schema version."}
    )
    embeddings: List[List[float]] = field(
        metadata={"doc": "Embedding vectors in the same order as the request inputs."}
    )
    model: str = field(metadata={"doc": "Embedding model used by the provider."})
    dimensions: int = field(metadata={"doc": "Vector dimensionality."})
    request_id: Optional[str] = field(
        metadata={"doc": "Provider request identifier, if available."}
    )
    input_tokens: Optional[int] = field(
        metadata={"doc": "Provider input token count, if available."}
    )
    total_tokens: Optional[int] = field(
        metadata={"doc": "Provider total token count, if available."}
    )


@dataclass(frozen=True)
class OpenAIUsageAccountingRequest:
    schema_version: str = field(
        metadata={"doc": "OpenAI usage accounting request schema version."}
    )
    step_name: str = field(
        metadata={"doc": "Logical OpenAI step name used for cost aggregation."}
    )
    model: str = field(metadata={"doc": "OpenAI model ID used for the call."})
    input_tokens: Optional[int] = field(
        metadata={"doc": "Provider input token count, if available."}
    )
    output_tokens: Optional[int] = field(
        metadata={"doc": "Provider output token count, if available."}
    )
    tool_calls: int = field(
        metadata={"doc": "Provider tool-call count billed for the call."}
    )
    cost_ledger_path: str = field(
        metadata={"doc": "Filesystem path for the cost ledger JSONL output."}
    )
    cost_daily_path: str = field(
        metadata={"doc": "Filesystem path for daily cost rollups."}
    )
    model_pricing: Dict[str, Any] = field(
        metadata={"doc": "Per-model pricing table for cost estimation."}
    )
    emit_cost_ledger: bool = field(
        default=True,
        metadata={
            "doc": "Whether to append this event to the JSON cost ledger and refresh daily rollups."
        },
    )
    request_id: Optional[str] = field(
        default=None, metadata={"doc": "Provider request ID, if available."}
    )
    cached_input_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Input tokens served from cache, if reported."}
    )
    provider: str = field(
        default="openai",
        metadata={"doc": "Provider that returned usage, e.g. openai or openrouter."},
    )
    action: Optional[str] = field(
        default=None,
        metadata={"doc": "Application action name; defaults to step_name."},
    )
    reservation_operation: str = field(
        default="",
        metadata={
            "doc": "Provider operation used to release the matching in-flight spend reservation."
        },
    )
    total_tokens: Optional[int] = field(
        default=None,
        metadata={"doc": "Provider total token count, if reported."},
    )
    usage_db_path: str = field(
        default="./state/llm_usage.sqlite",
        metadata={"doc": "SQLite database path for durable LLM token usage records."},
    )
    publisher_name: str = field(
        default="", metadata={"doc": "Publisher context for usage reporting, if known."}
    )
    report_name: str = field(
        default="", metadata={"doc": "Report context for usage reporting, if known."}
    )
    source_url: str = field(
        default="",
        metadata={"doc": "Source/report URL context for usage reporting, if known."},
    )
    prompt_namespace: str = field(
        default="",
        metadata={"doc": "Prompt namespace associated with the call, if known."},
    )
    prompt_hash: str = field(
        default="", metadata={"doc": "Prompt hash associated with the call, if known."}
    )
    provider_decision: str = field(
        default="", metadata={"doc": "Provider routing decision, if known."}
    )
    cache_decision: str = field(
        default="", metadata={"doc": "Semantic cache decision, if known."}
    )
    temperature: Optional[float] = field(
        default=None,
        metadata={"doc": "Sampling temperature used for the call, if known."},
    )
    seed: Optional[int] = field(
        default=None, metadata={"doc": "Seed used for the call, if configured."}
    )
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Provider timeout in seconds, if configured."}
    )
    call_ordinal: Optional[int] = field(
        default=None,
        metadata={
            "doc": (
                "Optional stable ordinal distinguishing provider calls in the active "
                "run context. None is allocated atomically by the canonical ledger."
            )
        },
    )
    provider_call_status: str = field(
        default="completed",
        metadata={"doc": "Provider transport outcome for this usage event."},
    )
    parse_status: str = field(
        default="not_applicable", metadata={"doc": "Current response parsing outcome."}
    )
    schema_validation_status: str = field(
        default="not_applicable",
        metadata={"doc": "Current response schema-validation outcome."},
    )
    error_stage: str = field(
        default="", metadata={"doc": "Bounded terminal error stage, when any."}
    )
    error_code: str = field(
        default="",
        metadata={"doc": "Bounded terminal application error code, when any."},
    )
    extra: Dict[str, Any] = field(
        default_factory=dict, metadata={"doc": "Additional non-secret usage metadata."}
    )


@dataclass(frozen=True)
class OpenAIUsageAccountingResponse:
    schema_version: str = field(
        metadata={"doc": "OpenAI usage accounting response schema version."}
    )
    recorded: bool = field(
        metadata={"doc": "Whether usage was appended to the cost ledger."}
    )
    estimated_cost_usd: float = field(
        metadata={"doc": "Estimated USD cost for the OpenAI call."}
    )
    ledger_path: str = field(metadata={"doc": "Cost ledger path used."})
    daily_path: str = field(metadata={"doc": "Daily rollup path used."})
    error: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Sanitized non-fatal accounting error, when recording failed."
        },
    )
    usage_db_path: str = field(
        default="",
        metadata={"doc": "SQLite usage ledger path used, when configured."},
    )
    usage_db_recorded: bool = field(
        default=False,
        metadata={"doc": "Whether the SQLite usage ledger write succeeded."},
    )
    usage_db_row_id: Optional[int] = field(
        default=None,
        metadata={"doc": "Inserted SQLite usage ledger row ID, if recorded."},
    )
    event_key: str = field(
        default="",
        metadata={"doc": "Deterministic idempotency key for the durable usage event."},
    )
    call_ordinal: Optional[int] = field(
        default=None,
        metadata={"doc": "Resolved canonical ordinal for the durable usage event."},
    )
    usage_db_inserted: bool = field(
        default=False,
        metadata={
            "doc": "Whether SQLite inserted this event instead of recognizing a replay."
        },
    )
    pricing_status: str = field(
        default="missing",
        metadata={
            "doc": "Pricing resolution result: matched, alias_matched, missing, or invalid."
        },
    )
    pricing_key: str = field(
        default="",
        metadata={"doc": "Pricing table key used for the cost estimate, if any."},
    )
    pricing_version: str = field(
        default="",
        metadata={"doc": "Configured pricing-table version used for the estimate."},
    )


@dataclass(frozen=True)
class OpenAIUsageOutcomeUpdateRequest:
    schema_version: str = field(
        metadata={"doc": "Usage outcome update request schema version."}
    )
    usage_db_path: str = field(metadata={"doc": "SQLite usage ledger path to update."})
    event_key: str = field(metadata={"doc": "Deterministic event key to finalize."})
    parse_status: str = field(
        metadata={"doc": "Final parse status for the provider response."}
    )
    schema_validation_status: str = field(
        metadata={"doc": "Final schema-validation status for the provider response."}
    )
    error_stage: str = field(
        default="", metadata={"doc": "Bounded terminal error stage, when any."}
    )
    error_code: str = field(
        default="", metadata={"doc": "Bounded terminal error code, when any."}
    )
    cost_ledger_path: str = field(
        default="",
        metadata={
            "doc": "Compatibility JSONL path to finalize when accounting succeeds."
        },
    )
    cost_daily_path: str = field(
        default="",
        metadata={"doc": "Daily rollup path to finalize when accounting succeeds."},
    )


@dataclass(frozen=True)
class OpenAIAnalyzeRequest:
    schema_version: str = field(
        metadata={"doc": "OpenAI analyze request schema version."}
    )
    system_prompt: str = field(metadata={"doc": "Rendered system prompt text."})
    user_prompt: str = field(metadata={"doc": "Rendered user prompt text."})
    prompt_system_sha256: str = field(
        metadata={"doc": "SHA-256 hash of the system prompt template."}
    )
    prompt_user_sha256: str = field(
        metadata={"doc": "SHA-256 hash of the user prompt template."}
    )
    model: str = field(metadata={"doc": "OpenAI model ID."})
    temperature: float = field(metadata={"doc": "Sampling temperature."})
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    seed: Optional[int] = field(
        default=None, metadata={"doc": "Optional seed for deterministic sampling."}
    )
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )
    tool_calls: int = field(
        default=0,
        metadata={"doc": "Expected number of tool calls billed (if known, else 0)."},
    )
    cached_input_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Input tokens served from cache, if reported."}
    )
    cost_ledger_path: str = field(
        default="./out/cost-ledger.jsonl",
        metadata={"doc": "Filesystem path for the cost ledger JSONL output."},
    )
    cost_daily_path: str = field(
        default="./out/cost-daily.json",
        metadata={"doc": "Filesystem path for daily cost rollups."},
    )
    model_pricing: dict = field(
        default_factory=dict,
        metadata={"doc": "Per-model pricing table for cost estimation."},
    )
    publisher_name: str = field(
        default="", metadata={"doc": "Publisher context for usage reporting, if known."}
    )
    report_name: str = field(
        default="", metadata={"doc": "Report context for usage reporting, if known."}
    )
    source_url: str = field(
        default="",
        metadata={"doc": "Source/report URL context for usage reporting, if known."},
    )
    prompt_namespace: str = field(
        default="", metadata={"doc": "Prompt namespace for usage reporting, if known."}
    )
    prompt_hash: str = field(
        default="", metadata={"doc": "Prompt hash for usage reporting, if known."}
    )
    usage_db_path: str = field(
        default="./state/llm_usage.sqlite",
        metadata={"doc": "Canonical SQLite usage ledger path for this provider call."},
    )


@dataclass(frozen=True)
class OpenAIAnalyzeResponse:
    schema_version: str = field(
        metadata={"doc": "OpenAI analyze response schema version."}
    )
    payload: ReportPayload = field(metadata={"doc": "Parsed report payload."})
    prompt_system_sha256: str = field(
        metadata={"doc": "SHA-256 hash of the system prompt template."}
    )
    prompt_user_sha256: str = field(
        metadata={"doc": "SHA-256 hash of the user prompt template."}
    )
    model: str = field(metadata={"doc": "OpenAI model ID used."})
    temperature: float = field(metadata={"doc": "Sampling temperature used."})
    raw_content: str = field(metadata={"doc": "Raw model response content."})
    prompt_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Provider prompt token count, if available."}
    )
    completion_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Provider completion token count, if available."}
    )
    total_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Provider total token count, if available."}
    )
    request_id: Optional[str] = field(
        default=None, metadata={"doc": "Provider request ID, if available."}
    )


@dataclass(frozen=True)
class OpenAIResponseRequest:
    schema_version: str = field(
        metadata={"doc": "OpenAI responses request schema version."}
    )
    system_prompt: str = field(metadata={"doc": "Rendered system prompt text."})
    user_prompt: str = field(metadata={"doc": "Rendered user prompt text."})
    vector_store_id: str = field(
        metadata={"doc": "Vector store identifier for file search."}
    )
    model: str = field(metadata={"doc": "OpenAI model ID."})
    temperature: float = field(metadata={"doc": "Sampling temperature."})
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    seed: Optional[int] = field(
        default=None, metadata={"doc": "Optional seed for deterministic sampling."}
    )
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )
    cost_ledger_path: str = field(
        default="./out/cost-ledger.jsonl",
        metadata={"doc": "Filesystem path for the cost ledger JSONL output."},
    )
    cost_daily_path: str = field(
        default="./out/cost-daily.json",
        metadata={"doc": "Filesystem path for daily cost rollups."},
    )
    model_pricing: dict = field(
        default_factory=dict,
        metadata={"doc": "Per-model pricing table for cost estimation."},
    )
    response_cache_enabled: bool = field(
        default=False,
        metadata={
            "doc": "Whether semantic response caching is enabled for this request."
        },
    )
    response_cache_dir: str = field(
        default="./cache",
        metadata={"doc": "Root cache directory for semantic OpenAI responses."},
    )
    response_cache_ttl_seconds: Optional[float] = field(
        default=604800.0,
        metadata={
            "doc": "Semantic response cache TTL in seconds; None disables expiry."
        },
    )
    context_compaction_policy: LLMContextCompactionPolicy = field(
        default_factory=lambda: LLMContextCompactionPolicy(schema_version="1.0"),
        metadata={"doc": "Optional deterministic pre-call context compaction policy."},
    )
    publisher_name: str = field(
        default="", metadata={"doc": "Publisher context for usage reporting, if known."}
    )
    report_name: str = field(
        default="", metadata={"doc": "Report context for usage reporting, if known."}
    )
    source_url: str = field(
        default="",
        metadata={"doc": "Source/report URL context for usage reporting, if known."},
    )
    prompt_namespace: str = field(
        default="", metadata={"doc": "Prompt namespace for usage reporting, if known."}
    )
    prompt_hash: str = field(
        default="", metadata={"doc": "Prompt hash for usage reporting, if known."}
    )
    usage_db_path: str = field(
        default="./state/llm_usage.sqlite",
        metadata={"doc": "Canonical SQLite usage ledger path for this provider call."},
    )
    same_provider_fallback: bool = field(
        default=False,
        metadata={"doc": "Whether retry fallback must remain with the selected provider."},
    )


@dataclass(frozen=True)
class OpenAIResponseResult:
    schema_version: str = field(
        metadata={"doc": "OpenAI responses result schema version."}
    )
    text: str = field(metadata={"doc": "Raw response text."})
    parsed_json: Optional[dict] = field(
        default=None,
        metadata={"doc": "Parsed JSON payload if the response was valid JSON."},
    )
    input_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Provider input token count, if available."}
    )
    output_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Provider output token count, if available."}
    )
    tool_calls: Optional[int] = field(
        default=None, metadata={"doc": "Number of tool calls billed, if available."}
    )
    model: str = field(default="", metadata={"doc": "Model ID used."})
    total_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Provider total token count, if available."}
    )
    request_id: Optional[str] = field(
        default=None, metadata={"doc": "Provider request ID, if available."}
    )


@dataclass(frozen=True)
class OpenAIJSONPromptRequest:
    schema_version: str = field(
        metadata={"doc": "OpenAI JSON prompt request schema version."}
    )
    system_prompt: str = field(metadata={"doc": "Rendered system prompt text."})
    user_prompt: str = field(metadata={"doc": "Rendered user prompt text."})
    model: str = field(metadata={"doc": "OpenAI model ID."})
    temperature: float = field(metadata={"doc": "Sampling temperature."})
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    seed: Optional[int] = field(
        default=None, metadata={"doc": "Optional seed for deterministic sampling."}
    )
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )
    cost_ledger_path: str = field(
        default="./out/cost-ledger.jsonl",
        metadata={"doc": "Filesystem path for the cost ledger JSONL output."},
    )
    cost_daily_path: str = field(
        default="./out/cost-daily.json",
        metadata={"doc": "Filesystem path for daily cost rollups."},
    )
    model_pricing: dict = field(
        default_factory=dict,
        metadata={"doc": "Per-model pricing table for cost estimation."},
    )
    response_cache_enabled: bool = field(
        default=False,
        metadata={
            "doc": "Whether semantic response caching is enabled for this request."
        },
    )
    response_cache_dir: str = field(
        default="./cache",
        metadata={"doc": "Root cache directory for semantic OpenAI responses."},
    )
    response_cache_ttl_seconds: Optional[float] = field(
        default=604800.0,
        metadata={
            "doc": "Semantic response cache TTL in seconds; None disables expiry."
        },
    )
    context_compaction_policy: LLMContextCompactionPolicy = field(
        default_factory=lambda: LLMContextCompactionPolicy(schema_version="1.0"),
        metadata={"doc": "Optional deterministic pre-call context compaction policy."},
    )
    publisher_name: str = field(
        default="", metadata={"doc": "Publisher context for usage reporting, if known."}
    )
    report_name: str = field(
        default="", metadata={"doc": "Report context for usage reporting, if known."}
    )
    source_url: str = field(
        default="",
        metadata={"doc": "Source/report URL context for usage reporting, if known."},
    )
    prompt_namespace: str = field(
        default="", metadata={"doc": "Prompt namespace for usage reporting, if known."}
    )
    prompt_hash: str = field(
        default="", metadata={"doc": "Prompt hash for usage reporting, if known."}
    )
    usage_db_path: str = field(
        default="./state/llm_usage.sqlite",
        metadata={"doc": "Canonical SQLite usage ledger path for this provider call."},
    )
    run_budget: RunBudget | None = field(
        default=None,
        metadata={"doc": "Optional canonical scoped budget for this provider call."},
    )
    workflow_id: str = field(
        default="llm",
        metadata={"doc": "Workflow identifier recorded by the budget authority."},
    )
    daily_spend_warn_usd: float = field(
        default=3.0,
        metadata={"doc": "UTC canonical-spend threshold that warns before this call."},
    )
    daily_spend_pause_usd: float = field(
        default=5.0,
        metadata={"doc": "UTC canonical-spend threshold that defers this call."},
    )
    daily_spend_stop_usd: float = field(
        default=6.0,
        metadata={"doc": "UTC canonical-spend threshold that hard-stops this call."},
    )
    same_provider_fallback: bool = field(
        default=False,
        metadata={"doc": "Whether retry fallback must remain with the selected provider."},
    )


@dataclass(frozen=True)
class OpenAIJSONImagePromptRequest:
    schema_version: str = field(
        metadata={"doc": "OpenAI JSON+image prompt request schema version."}
    )
    system_prompt: str = field(metadata={"doc": "Rendered system prompt text."})
    user_prompt: str = field(metadata={"doc": "Rendered user prompt text."})
    model: str = field(metadata={"doc": "OpenAI model ID."})
    temperature: float = field(metadata={"doc": "Sampling temperature."})
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    image_paths: List[str] = field(
        metadata={"doc": "Filesystem paths to images provided as visual context."}
    )
    seed: Optional[int] = field(
        default=None, metadata={"doc": "Optional seed for deterministic sampling."}
    )
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )
    cost_ledger_path: str = field(
        default="./out/cost-ledger.jsonl",
        metadata={"doc": "Filesystem path for the cost ledger JSONL output."},
    )
    cost_daily_path: str = field(
        default="./out/cost-daily.json",
        metadata={"doc": "Filesystem path for daily cost rollups."},
    )
    model_pricing: dict = field(
        default_factory=dict,
        metadata={"doc": "Per-model pricing table for cost estimation."},
    )
    response_cache_enabled: bool = field(
        default=False,
        metadata={
            "doc": "Whether semantic response caching is enabled for this request."
        },
    )
    response_cache_dir: str = field(
        default="./cache",
        metadata={"doc": "Root cache directory for semantic OpenAI responses."},
    )
    response_cache_ttl_seconds: Optional[float] = field(
        default=604800.0,
        metadata={
            "doc": "Semantic response cache TTL in seconds; None disables expiry."
        },
    )
    context_compaction_policy: LLMContextCompactionPolicy = field(
        default_factory=lambda: LLMContextCompactionPolicy(schema_version="1.0"),
        metadata={"doc": "Optional deterministic pre-call context compaction policy."},
    )
    publisher_name: str = field(
        default="", metadata={"doc": "Publisher context for usage reporting, if known."}
    )
    report_name: str = field(
        default="", metadata={"doc": "Report context for usage reporting, if known."}
    )
    source_url: str = field(
        default="",
        metadata={"doc": "Source/report URL context for usage reporting, if known."},
    )
    prompt_namespace: str = field(
        default="", metadata={"doc": "Prompt namespace for usage reporting, if known."}
    )
    prompt_hash: str = field(
        default="", metadata={"doc": "Prompt hash for usage reporting, if known."}
    )
    usage_db_path: str = field(
        default="./state/llm_usage.sqlite",
        metadata={"doc": "Canonical SQLite usage ledger path for this provider call."},
    )


@dataclass(frozen=True)
class OpenAIPdfOcrRequest:
    schema_version: str = field(
        metadata={"doc": "OpenAI PDF OCR request schema version."}
    )
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    pdf_path: str = field(
        metadata={"doc": "Filesystem path to the source PDF submitted for OCR."}
    )
    model: str = field(metadata={"doc": "OpenAI model ID used for OCR."})
    system_prompt: str = field(metadata={"doc": "Rendered system prompt text."})
    user_prompt: str = field(metadata={"doc": "Rendered user prompt text."})
    timeout_seconds: Optional[float] = field(
        default=None,
        metadata={"doc": "Request timeout in seconds for the OCR call, if set."},
    )
    cost_ledger_path: str = field(
        default="./out/cost-ledger.jsonl",
        metadata={"doc": "Filesystem path for the cost ledger JSONL output."},
    )
    cost_daily_path: str = field(
        default="./out/cost-daily.json",
        metadata={"doc": "Filesystem path for daily cost rollups."},
    )
    model_pricing: dict = field(
        default_factory=dict,
        metadata={"doc": "Per-model pricing table for cost estimation."},
    )
    response_cache_enabled: bool = field(
        default=False,
        metadata={
            "doc": "Whether semantic response caching is enabled for this request."
        },
    )
    response_cache_dir: str = field(
        default="./cache",
        metadata={"doc": "Root cache directory for semantic OpenAI responses."},
    )
    response_cache_ttl_seconds: Optional[float] = field(
        default=604800.0,
        metadata={
            "doc": "Semantic response cache TTL in seconds; None disables expiry."
        },
    )
    context_compaction_policy: LLMContextCompactionPolicy = field(
        default_factory=lambda: LLMContextCompactionPolicy(schema_version="1.0"),
        metadata={"doc": "Optional deterministic pre-call context compaction policy."},
    )
    publisher_name: str = field(
        default="", metadata={"doc": "Publisher context for usage reporting, if known."}
    )
    report_name: str = field(
        default="", metadata={"doc": "Report context for usage reporting, if known."}
    )
    source_url: str = field(
        default="",
        metadata={"doc": "Source/report URL context for usage reporting, if known."},
    )
    prompt_namespace: str = field(
        default="", metadata={"doc": "Prompt namespace for usage reporting, if known."}
    )
    prompt_hash: str = field(
        default="", metadata={"doc": "Prompt hash for usage reporting, if known."}
    )
    usage_db_path: str = field(
        default="./state/llm_usage.sqlite",
        metadata={"doc": "Canonical SQLite usage ledger path for this provider call."},
    )


@dataclass(frozen=True)
class OpenAIPdfOcrResponse:
    schema_version: str = field(
        metadata={"doc": "OpenAI PDF OCR response schema version."}
    )
    pages: List[PdfOcrPageText] = field(
        metadata={"doc": "Structured OCR page text returned by OpenAI."}
    )
    raw_text: str = field(metadata={"doc": "Raw response text returned by the model."})
    model: str = field(metadata={"doc": "Resolved OpenAI model ID used."})
    input_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Provider input token count, if available."}
    )
    output_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Provider output token count, if available."}
    )
    tool_calls: Optional[int] = field(
        default=None, metadata={"doc": "Provider tool-call count, if available."}
    )
    request_id: Optional[str] = field(
        default=None, metadata={"doc": "Provider request identifier, if available."}
    )


@dataclass(frozen=True)
class OpenAIVectorStoreCreateRequest:
    schema_version: str = field(
        metadata={"doc": "OpenAI vector store create request schema version."}
    )
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    name: str = field(metadata={"doc": "Human-readable vector store name."})
    metadata: Dict[str, str] = field(
        default_factory=dict,
        metadata={"doc": "Metadata map stored on the vector store."},
    )
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )


@dataclass(frozen=True)
class OpenAIVectorStoreCreateResponse:
    schema_version: str = field(
        metadata={"doc": "OpenAI vector store create response schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Created vector store ID."})


@dataclass(frozen=True)
class OpenAIVectorStoreFileUploadRequest:
    schema_version: str = field(
        metadata={"doc": "OpenAI file upload request schema version."}
    )
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    file_path: str = field(
        metadata={"doc": "Filesystem path to the file that should be uploaded."}
    )
    purpose: str = field(
        default="assistants", metadata={"doc": "OpenAI file purpose parameter."}
    )
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )


@dataclass(frozen=True)
class OpenAIVectorStoreFileUploadResponse:
    schema_version: str = field(
        metadata={"doc": "OpenAI file upload response schema version."}
    )
    openai_file_id: str = field(metadata={"doc": "Uploaded OpenAI file ID."})


@dataclass(frozen=True)
class OpenAIVectorStoreAttachFileRequest:
    schema_version: str = field(
        metadata={"doc": "OpenAI vector store attach file request schema version."}
    )
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    vector_store_id: str = field(metadata={"doc": "Target vector store identifier."})
    openai_file_id: str = field(metadata={"doc": "OpenAI file identifier to attach."})
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )


@dataclass(frozen=True)
class OpenAIVectorStoreAttachFileResponse:
    schema_version: str = field(
        metadata={"doc": "OpenAI vector store attach file response schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Target vector store identifier."})
    openai_file_id: str = field(
        metadata={"doc": "OpenAI file identifier that is now attached."}
    )


@dataclass(frozen=True)
class OpenAIVectorStoreStatusRequest:
    schema_version: str = field(
        metadata={"doc": "OpenAI vector store status request schema version."}
    )
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    vector_store_id: str = field(metadata={"doc": "Vector store identifier."})
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )


@dataclass(frozen=True)
class OpenAIVectorStoreStatusResponse:
    schema_version: str = field(
        metadata={"doc": "OpenAI vector store status response schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Vector store identifier."})
    status: str = field(metadata={"doc": "Provider status for the vector store."})
    indexed_at_utc: Optional[str] = field(
        default=None,
        metadata={"doc": "Provider timestamp for creation/indexing, if available."},
    )
    last_error: Optional[str] = field(
        default=None, metadata={"doc": "Provider error text, if available."}
    )


@dataclass(frozen=True)
class OpenAIVectorStoreDeleteRequest:
    schema_version: str = field(
        metadata={"doc": "OpenAI vector store delete request schema version."}
    )
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    vector_store_id: str = field(metadata={"doc": "Vector store identifier."})
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )


@dataclass(frozen=True)
class OpenAIVectorStoreDeleteResponse:
    schema_version: str = field(
        metadata={"doc": "OpenAI vector store delete response schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Deleted vector store identifier."})
    deleted: bool = field(
        metadata={"doc": "True when the provider reports the vector store was deleted."}
    )


@dataclass(frozen=True)
class OpenAIVectorStoreUpdateMetadataRequest:
    schema_version: str = field(
        metadata={"doc": "OpenAI vector store metadata update request schema version."}
    )
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    vector_store_id: str = field(metadata={"doc": "Vector store identifier to update."})
    metadata: Dict[str, str] = field(
        default_factory=dict,
        metadata={"doc": "Metadata map that replaces/updates provider metadata."},
    )
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )


@dataclass(frozen=True)
class OpenAIVectorStoreUpdateMetadataResponse:
    schema_version: str = field(
        metadata={"doc": "OpenAI vector store metadata update response schema version."}
    )
    vector_store_id: str = field(metadata={"doc": "Updated vector store identifier."})
