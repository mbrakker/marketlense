from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .session_reuse import BrowserDownloadSessionReusePolicy

BROWSER_DOWNLOAD_IDENTITY_SCHEMA_VERSION = "1.0"


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
    option_aliases: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Allowed visible enum/select option labels that represent the configured field value."
        },
    )


@dataclass(frozen=True)
class BrowserDownloadPublisherOverride:
    schema_version: str = field(
        metadata={"doc": "Browser download publisher-override schema version."}
    )
    host_pattern: str = field(
        metadata={
            "doc": "Exact host or host suffix used to match publisher-specific identity overrides."
        }
    )
    delivery_emails: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Publisher-specific delivery email addresses ranked ahead of the global identity emails."
        },
    )
    field_values: list[BrowserDownloadIdentityField] = field(
        default_factory=list,
        metadata={
            "doc": "Publisher-specific identity field values, including enum answers and field overrides."
        },
    )


@dataclass(frozen=True)
class BrowserDownloadConsentPolicy:
    schema_version: str = field(
        metadata={"doc": "Browser-download consent policy schema version."}
    )
    default_checkbox_policy: str = field(
        default="mandatory_privacy_terms_only",
        metadata={
            "doc": "Default checkbox policy for form completion; privacy-first by default."
        },
    )
    allow_marketing_opt_in: bool = field(
        default=False,
        metadata={"doc": "Whether optional marketing opt-ins may be checked."},
    )
    allow_optional_newsletter: bool = field(
        default=False,
        metadata={"doc": "Whether optional newsletter opt-ins may be checked."},
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
    delivery_emails: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Configured delivery email addresses that can be used for gated report forms."
        },
    )
    publisher_overrides: list[BrowserDownloadPublisherOverride] = field(
        default_factory=list,
        metadata={
            "doc": "Optional publisher-specific delivery-email and field-value overrides."
        },
    )
    consent_policy: BrowserDownloadConsentPolicy = field(
        default_factory=lambda: BrowserDownloadConsentPolicy(schema_version="1.0"),
        metadata={"doc": "Typed privacy and consent policy for form completion."},
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
        metadata={
            "doc": "SQLite reports DB used to store downloaded-report source rows."
        }
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
    drive_upload_enabled: bool = field(
        default=False,
        metadata={
            "doc": "Whether successful report acquisitions should upload local terminal artifacts to Google Drive."
        },
    )
    drive_upload_required: bool = field(
        default=True,
        metadata={
            "doc": "Whether Drive archival failure should fail the report download workflow."
        },
    )
    drive_upload_parent_folder_id: str = field(
        default="",
        metadata={
            "doc": "Drive parent folder ID where missing publisher archive folders should be created."
        },
    )
    drive_upload_google_sa_path: str = field(
        default="",
        metadata={
            "doc": "Filesystem path to the Google service account JSON used for Drive archival when auth mode is service_account."
        },
    )
    drive_upload_auth_mode: str = field(
        default="service_account",
        metadata={"doc": "Drive auth mode used for report acquisition archival."},
    )
    drive_upload_oauth_client_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional OAuth desktop client JSON path used for report acquisition archival."
        },
    )
    drive_upload_oauth_token_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "OAuth authorized-user token JSON path used for report acquisition archival."
        },
    )
    drive_upload_supports_all_drives: bool = field(
        default=True,
        metadata={"doc": "Whether Drive archival upload calls support shared drives."},
    )
    drive_upload_include_items_from_all_drives: bool = field(
        default=True,
        metadata={
            "doc": "Whether duplicate checks for Drive archival include items from shared drives."
        },
    )
    drive_upload_drive_id: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional shared Drive ID used when checking for duplicate archived artifacts."
        },
    )
    failure_forensics_enabled: bool = field(
        default=True,
        metadata={
            "doc": "Whether failed acquisition attempts should persist a typed failure-forensics pack."
        },
    )
    failure_forensics_policy: str = field(
        default="copy_artifacts",
        metadata={
            "doc": "Retention policy for failed-attempt forensic artifacts: `copy_artifacts` to persist bounded copies, or `metadata_only` to persist only bundle metadata plus original paths."
        },
    )
    route_playbook_dir: str = field(
        default="./src/playbooks/browser_routes",
        metadata={
            "doc": "Filesystem directory containing Marketlense-owned browser route playbook YAML files."
        },
    )
    route_playbook_stale_policy: str = field(
        default="fallback",
        metadata={
            "doc": "Behavior for matching stale route playbooks: `fallback` logs and uses normal discovery, `fail` raises a typed AppError."
        },
    )
    route_playbook_promotion_mode: str = field(
        default="disabled",
        metadata={
            "doc": "Promotion policy for verified browser-route memory: `disabled` logs skips, `dry_run` logs review diffs without writing files, and `write` persists reviewable playbook YAML."
        },
    )
    private_api_playbook_promotion_mode: str = field(
        default="disabled",
        metadata={
            "doc": "Promotion policy for validated private-API endpoint candidates: `disabled` skips detection, `dry_run` logs and records eligible candidates without writing YAML, and `write` persists reviewable private-API playbooks after thresholded validation."
        },
    )
    private_api_playbook_min_success_count: int = field(
        default=3,
        metadata={
            "doc": "Minimum validated private-API observations required before automatic promotion is eligible."
        },
    )
    private_api_playbook_min_distinct_source_urls: int = field(
        default=2,
        metadata={
            "doc": "Minimum distinct source URLs required before automatic private-API promotion is eligible."
        },
    )
    session_reuse_policy: BrowserDownloadSessionReusePolicy = field(
        default_factory=lambda: BrowserDownloadSessionReusePolicy(
            schema_version=BROWSER_DOWNLOAD_IDENTITY_SCHEMA_VERSION
        ),
        metadata={
            "doc": "Opt-in bounded browser profile reuse policy for developer canaries or same-publisher batches."
        },
    )
