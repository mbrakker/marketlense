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


@dataclass(frozen=True)
class OpenAIAnalyzeResponse:
    schema_version: str = field(metadata={"doc": "OpenAI analyze response schema version."})
    payload: ReportPayload = field(metadata={"doc": "Parsed report payload."})
    prompt_system_sha256: str = field(metadata={"doc": "SHA-256 hash of the system prompt template."})
    prompt_user_sha256: str = field(metadata={"doc": "SHA-256 hash of the user prompt template."})
    model: str = field(metadata={"doc": "OpenAI model ID used."})
    temperature: float = field(metadata={"doc": "Sampling temperature used."})
    raw_content: str = field(metadata={"doc": "Raw model response content."})
    request_id: Optional[str] = field(default=None, metadata={"doc": "Provider request ID, if available."})
