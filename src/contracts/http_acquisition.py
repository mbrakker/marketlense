from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class HttpAcquisitionResponsePolicy:
    schema_version: str = field(
        metadata={"doc": "HTTP acquisition response-policy schema version."}
    )
    require_success_status: bool = field(
        metadata={
            "doc": "Whether HTTP statuses >= 400 should fail the request immediately."
        }
    )
    capture_text: bool = field(
        metadata={
            "doc": "Whether the executor should decode and return a bounded text body."
        }
    )
    capture_binary: bool = field(
        default=False,
        metadata={
            "doc": "Whether the executor should return bounded raw response bytes."
        },
    )
    capture_content_type_markers: tuple[str, ...] = field(
        default_factory=tuple,
        metadata={
            "doc": "Optional case-insensitive content-type markers that gate body capture."
        },
    )
    max_body_bytes: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Maximum number of response-body bytes to retain in memory before truncation or failure."
        },
    )
    truncate_body: bool = field(
        default=False,
        metadata={
            "doc": "Whether oversized in-memory bodies should be truncated instead of failing."
        },
    )
    stream_to_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional absolute filesystem path where the response body should be streamed."
        },
    )
    max_stream_bytes: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Maximum number of streamed bytes allowed before the executor fails."
        },
    )
    chunk_size_bytes: int = field(
        default=65536,
        metadata={"doc": "Chunk size used when reading or streaming the response body."},
    )


@dataclass(frozen=True)
class HttpAcquisitionRequest:
    schema_version: str = field(
        metadata={"doc": "HTTP acquisition request schema version."}
    )
    purpose: str = field(
        metadata={
            "doc": "Short purpose label describing why this HTTP acquisition is being performed."
        }
    )
    method: str = field(
        metadata={"doc": "Upper- or lower-case HTTP method name to execute."}
    )
    url: str = field(
        metadata={"doc": "Absolute request URL submitted to the remote HTTP server."}
    )
    headers: dict[str, str] = field(
        metadata={"doc": "Normalized outbound request headers."}
    )
    timeout_seconds: float = field(
        metadata={"doc": "Per-request timeout in seconds."}
    )
    response_policy: HttpAcquisitionResponsePolicy = field(
        metadata={"doc": "Bounded response handling policy for the request."}
    )
    error_code: str = field(
        metadata={"doc": "Typed AppError code used when the request fails."}
    )
    error_message: str = field(
        metadata={"doc": "Typed AppError message used when the request fails."}
    )
    allow_redirects: Optional[bool] = field(
        default=None,
        metadata={
            "doc": "Optional redirect behavior override; omitted when the caller needs the transport default."
        },
    )
    data: Optional[dict[str, str]] = field(
        default=None,
        metadata={"doc": "Optional form body submitted with POST-like requests."},
    )
    range_header: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional byte-range header value added to the request when provided."
        },
    )
    context_fields: dict[str, object] = field(
        default_factory=dict,
        metadata={
            "doc": "Additional sanitized context fields copied into error and executor logs."
        },
    )
    body_too_large_code: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional AppError code used when the response exceeds the configured in-memory or stream size cap."
        },
    )
    body_too_large_message: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional AppError message used when the response exceeds the configured in-memory or stream size cap."
        },
    )
    write_error_code: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional AppError code used when streaming the response body to disk fails."
        },
    )
    write_error_message: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional AppError message used when streaming the response body to disk fails."
        },
    )


@dataclass(frozen=True)
class HttpAcquisitionResponse:
    schema_version: str = field(
        metadata={"doc": "HTTP acquisition response schema version."}
    )
    purpose: str = field(
        metadata={"doc": "Purpose label copied from the originating request."}
    )
    method: str = field(
        metadata={"doc": "Normalized HTTP method that was executed."}
    )
    request_url: str = field(
        metadata={"doc": "Original request URL before redirects."}
    )
    final_url: str = field(
        metadata={"doc": "Final response URL after redirects."}
    )
    status_code: int = field(
        metadata={"doc": "Final HTTP response status code."}
    )
    headers: dict[str, str] = field(
        metadata={"doc": "Sanitized response headers returned by the remote server."}
    )
    content_type: str = field(
        metadata={"doc": "Normalized response content-type header value."}
    )
    content_length_bytes: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Parsed content-length header when the server provided one."
        },
    )
    text_body: Optional[str] = field(
        default=None,
        metadata={"doc": "Captured decoded text body when requested by policy."},
    )
    body_bytes: Optional[bytes] = field(
        default=None,
        metadata={"doc": "Captured raw body bytes when requested by policy."},
    )
    body_truncated: bool = field(
        default=False,
        metadata={
            "doc": "Whether the captured in-memory response body was truncated by policy."
        },
    )
    streamed_to_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Filesystem path where the response was streamed when applicable."
        },
    )
    streamed_bytes: Optional[int] = field(
        default=None,
        metadata={"doc": "Total number of bytes streamed to disk when applicable."},
    )
    used_pooled_session: bool = field(
        default=False,
        metadata={
            "doc": "Whether the request used a pooled requests.Session instead of the direct module-level function."
        },
    )
    pool_key: str = field(
        default="",
        metadata={
            "doc": "Session-pool key derived from the request host for pooled requests."
        },
    )
