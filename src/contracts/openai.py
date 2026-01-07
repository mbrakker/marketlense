from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.contracts.report_models import ReportPayload


@dataclass(frozen=True)
class OpenAIAnalyzeRequest:
    schema_version: str = field(metadata={"doc": "OpenAI analyze request schema version."})
    system_prompt: str = field(metadata={"doc": "Rendered system prompt text."})
    user_prompt: str = field(metadata={"doc": "Rendered user prompt text."})
    prompt_system_sha256: str = field(metadata={"doc": "SHA-256 hash of the system prompt template."})
    prompt_user_sha256: str = field(metadata={"doc": "SHA-256 hash of the user prompt template."})
    model: str = field(metadata={"doc": "OpenAI model ID."})
    temperature: float = field(metadata={"doc": "Sampling temperature."})
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    seed: Optional[int] = field(default=None, metadata={"doc": "Optional seed for deterministic sampling."})
    timeout_seconds: Optional[float] = field(default=None, metadata={"doc": "Request timeout in seconds, if set."})
    tool_calls: int = field(default=0, metadata={"doc": "Expected number of tool calls billed (if known, else 0)."})
    cached_input_tokens: Optional[int] = field(default=None, metadata={"doc": "Input tokens served from cache, if reported."})
    cost_ledger_path: str = field(default="./out/cost-ledger.jsonl", metadata={"doc": "Filesystem path for the cost ledger JSONL output."})
    cost_daily_path: str = field(default="./out/cost-daily.json", metadata={"doc": "Filesystem path for daily cost rollups."})
    model_pricing: dict = field(default_factory=dict, metadata={"doc": "Per-model pricing table for cost estimation."})


@dataclass(frozen=True)
class OpenAIAnalyzeResponse:
    schema_version: str = field(metadata={"doc": "OpenAI analyze response schema version."})
    payload: ReportPayload = field(metadata={"doc": "Parsed report payload."})
    prompt_system_sha256: str = field(metadata={"doc": "SHA-256 hash of the system prompt template."})
    prompt_user_sha256: str = field(metadata={"doc": "SHA-256 hash of the user prompt template."})
    model: str = field(metadata={"doc": "OpenAI model ID used."})
    temperature: float = field(metadata={"doc": "Sampling temperature used."})
    raw_content: str = field(metadata={"doc": "Raw model response content."})
    prompt_tokens: Optional[int] = field(default=None, metadata={"doc": "Provider prompt token count, if available."})
    completion_tokens: Optional[int] = field(default=None, metadata={"doc": "Provider completion token count, if available."})
    total_tokens: Optional[int] = field(default=None, metadata={"doc": "Provider total token count, if available."})
    request_id: Optional[str] = field(default=None, metadata={"doc": "Provider request ID, if available."})
