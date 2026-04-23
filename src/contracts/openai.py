from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.contracts.pdf_ocr import PdfOcrPageText
from src.contracts.report_models import ReportPayload


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
