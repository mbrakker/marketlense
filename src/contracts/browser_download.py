from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class BrowserDownloadIdentityField:
    schema_version: str = field(
        metadata={"doc": "Browser download identity field schema version."}
    )
    key: str = field(
        metadata={"doc": "Stable machine key used to match this field across forms."}
    )
    label: str = field(
        metadata={"doc": "Human-readable field label stored in the identity YAML."}
    )
    value: Optional[str] = field(
        default=None,
        metadata={"doc": "Configured value used when a matching form field is found."},
    )
    aliases: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Additional labels or names that should map to this identity field."
        },
    )


@dataclass(frozen=True)
class BrowserDownloadIdentity:
    schema_version: str = field(
        metadata={"doc": "Browser download identity schema version."}
    )
    fields: list[BrowserDownloadIdentityField] = field(
        metadata={
            "doc": "Configured identity fields available for browser form filling."
        }
    )


@dataclass(frozen=True)
class BrowserDownloadIdentityFieldUpsertRequest:
    schema_version: str = field(
        metadata={"doc": "Identity-field upsert request schema version."}
    )
    path: str = field(
        metadata={
            "doc": "Absolute YAML path used to persist browser form identity fields."
        }
    )
    encountered_form_fields: list[str] = field(
        metadata={
            "doc": "Distinct human-readable field labels encountered during a browser run."
        }
    )


@dataclass(frozen=True)
class BrowserDownloadIdentityFieldUpsertResponse:
    schema_version: str = field(
        metadata={"doc": "Identity-field upsert response schema version."}
    )
    path: str = field(
        metadata={"doc": "Absolute YAML path that was inspected and updated."}
    )
    added_field_keys: list[str] = field(
        metadata={
            "doc": "New identity keys added to the YAML for future manual completion."
        }
    )
    total_fields: int = field(
        metadata={
            "doc": "Total number of identity fields stored after the upsert completed."
        }
    )


@dataclass(frozen=True)
class BrowserDownloadSettings:
    schema_version: str = field(
        metadata={"doc": "Browser download settings schema version."}
    )
    openrouter_api_key: str = field(
        metadata={"doc": "OpenRouter API key used by the local browser-use agent."}
    )
    model: str = field(
        metadata={"doc": "Model ID used by the local browser-use agent."}
    )
    temperature: float = field(
        metadata={"doc": "Sampling temperature for the browser-use agent."}
    )
    timeout_seconds: float = field(
        metadata={"doc": "Per-model timeout in seconds for browser-use LLM calls."}
    )
    max_steps: int = field(
        metadata={"doc": "Maximum browser-use agent steps per report download run."}
    )
    output_dir: str = field(
        metadata={"doc": "Root directory where browser-managed downloads are stored."}
    )
    state_db: str = field(
        metadata={"doc": "SQLite state DB used to remember successful per-URL routes."}
    )
    reports_db: str = field(
        metadata={"doc": "SQLite reports DB used to store downloaded-report source rows."}
    )
    identity_config_path: str = field(
        metadata={
            "doc": "Absolute YAML path used to load browser form identity values."
        }
    )
    identity_profile: BrowserDownloadIdentity = field(
        metadata={"doc": "Loaded browser form identity fields supplied to browser-use."}
    )
    openrouter_http_referer: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional HTTP-Referer header sent to OpenRouter for browser-use requests."
        },
    )
    headed: bool = field(
        default=False,
        metadata={
            "doc": "Whether to run the local browser visibly instead of headless."
        },
    )
    retry_retries: int = field(
        default=1,
        metadata={"doc": "Retry count for orchestrated browser download attempts."},
    )
    retry_base_delay_seconds: float = field(
        default=1.0,
        metadata={"doc": "Base delay before the first browser download retry."},
    )
    retry_backoff_step_seconds: float = field(
        default=1.0,
        metadata={"doc": "Linear backoff step added per browser download retry."},
    )
    retry_jitter_seconds: float = field(
        default=0.25,
        metadata={"doc": "Maximum jitter added to browser download retry delays."},
    )


@dataclass(frozen=True)
class BrowserReportDownloadRequest:
    schema_version: str = field(
        metadata={"doc": "Browser report download request schema version."}
    )
    url: str = field(
        metadata={"doc": "Absolute source URL for the report landing page."}
    )
    settings: BrowserDownloadSettings = field(
        metadata={"doc": "Browser-use execution settings."}
    )
    delivery_email: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional email address to submit when a report is gated behind email delivery."
        },
    )
    route_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Previously successful route summary used to bias the next browser attempt."
        },
    )
    route_kind_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Previously observed route kind (`pdf_download` or `email_delivery`) when available."
        },
    )


@dataclass(frozen=True)
class BrowserReportDownloadResult:
    schema_version: str = field(
        metadata={"doc": "Browser report download result schema version."}
    )
    source_url: str = field(metadata={"doc": "Original URL provided by the caller."})
    normalized_url: str = field(
        metadata={"doc": "Normalized URL used for route-memory lookup and storage."}
    )
    route_kind: str = field(
        metadata={"doc": "Detected delivery path: `pdf_download` or `email_delivery`."}
    )
    outcome: str = field(
        metadata={
            "doc": "Observed outcome: `downloaded`, `email_requested`, or `email_required`."
        }
    )
    route_summary: str = field(
        metadata={"doc": "Concise summary of the successful browser route."}
    )
    final_page_url: str = field(
        metadata={"doc": "Final browser URL after the agent finished."}
    )
    used_route_hint: bool = field(
        metadata={"doc": "Whether the execution used a previously stored route hint."}
    )
    encountered_form_fields: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Distinct form field labels or names encountered while following the route."
        },
    )
    downloaded_file_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Absolute path of the downloaded report when outcome=`downloaded`."
        },
    )
    downloaded_file_name: Optional[str] = field(
        default=None,
        metadata={"doc": "Downloaded file name when a file was saved locally."},
    )
    downloaded_mime_type: Optional[str] = field(
        default=None,
        metadata={"doc": "Detected MIME type for the downloaded file when available."},
    )
    downloaded_size_bytes: Optional[int] = field(
        default=None,
        metadata={"doc": "Downloaded file size in bytes when a local file exists."},
    )


@dataclass(frozen=True)
class ReportDownloadOrchestratorRequest:
    schema_version: str = field(
        metadata={"doc": "Report download orchestrator request schema version."}
    )
    url: str = field(metadata={"doc": "Absolute report landing-page URL."})
    settings: BrowserDownloadSettings = field(
        metadata={"doc": "Browser download settings loaded from configuration."}
    )
    state_db: str = field(
        metadata={"doc": "SQLite state DB used to remember successful per-URL routes."}
    )
    reports_db: str = field(
        metadata={"doc": "SQLite reports DB used to store downloaded-report source rows."}
    )
    delivery_email: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional email address used when a report can only be delivered by email."
        },
    )


@dataclass(frozen=True)
class ReportDownloadOrchestratorResult:
    schema_version: str = field(
        metadata={"doc": "Report download orchestrator result schema version."}
    )
    source_url: str = field(metadata={"doc": "Original URL provided by the caller."})
    normalized_url: str = field(
        metadata={"doc": "Normalized URL used for state lookup and storage."}
    )
    route_kind: str = field(
        metadata={"doc": "Detected delivery path: `pdf_download` or `email_delivery`."}
    )
    outcome: str = field(
        metadata={
            "doc": "Observed outcome: `downloaded`, `email_requested`, or `email_required`."
        }
    )
    route_summary: str = field(
        metadata={"doc": "Stored summary of the best-known route for this URL."}
    )
    final_page_url: str = field(
        metadata={"doc": "Final browser URL after orchestration completed."}
    )
    used_memory_route: bool = field(
        metadata={
            "doc": "Whether a remembered route hint was used on the successful run."
        }
    )
    encountered_form_fields: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Distinct form field labels or names encountered while following the route."
        },
    )
    identity_fields_added: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "New identity keys added to the browser identity YAML after this run."
        },
    )
    downloaded_file_path: Optional[str] = field(
        default=None,
        metadata={"doc": "Absolute local report path when the file was downloaded."},
    )
    downloaded_file_name: Optional[str] = field(
        default=None,
        metadata={"doc": "Downloaded file name when a file was saved locally."},
    )
    downloaded_mime_type: Optional[str] = field(
        default=None,
        metadata={"doc": "Detected MIME type for the downloaded file when available."},
    )
    downloaded_size_bytes: Optional[int] = field(
        default=None,
        metadata={"doc": "Downloaded file size in bytes when a local file exists."},
    )
