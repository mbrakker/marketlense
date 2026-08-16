from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BrowserRoutePlaybookStep:
    schema_version: str = field(
        metadata={"doc": "Browser route playbook step schema version."}
    )
    action: str = field(
        metadata={
            "doc": "Reusable browser action category, for example `click_cta`, `inspect_form`, or `capture_longread`."
        }
    )
    target: str = field(
        metadata={
            "doc": "Stable target description such as visible copy, semantic page area, or URL marker."
        }
    )
    verification: str = field(
        metadata={
            "doc": "Evidence expected after this playbook step, such as artifact, confirmation text, URL change, or capture hash."
        }
    )
    selector_type: str = field(
        default="",
        metadata={
            "doc": "Optional deterministic selector type: css, text, url, or none."
        },
    )
    selector: str = field(
        default="",
        metadata={"doc": "Optional deterministic selector value for executor use."},
    )
    value: str = field(
        default="",
        metadata={"doc": "Optional fill/select value for deterministic executor use."},
    )
    value_reference: str = field(
        default="",
        metadata={
            "doc": "Optional identity placeholder for a fill/select action; never a personal value."
        },
    )
    expected_url_contains: str = field(
        default="",
        metadata={"doc": "Optional URL substring expected after the step."},
    )
    expected_text: str = field(
        default="",
        metadata={"doc": "Optional page text expected after the step."},
    )


@dataclass(frozen=True)
class BrowserRoutePlaybookHistoryEntry:
    schema_version: str = field(
        metadata={"doc": "Browser route playbook history entry schema version."}
    )
    changed_at: str = field(
        metadata={
            "doc": "UTC ISO date or timestamp when this playbook revision changed."
        }
    )
    source: str = field(
        metadata={
            "doc": "Source of the revision, for example `seeded_from_existing_route_evidence` or `validated_route_promotion`."
        }
    )
    summary: str = field(
        metadata={"doc": "Concise reviewable summary of the playbook change."}
    )


@dataclass(frozen=True)
class BrowserRoutePrivateApiEvidence:
    schema_version: str = field(
        metadata={"doc": "Browser route private-API evidence schema version."}
    )
    evidence_id: str = field(
        metadata={"doc": "Stable private-API evidence identifier within a playbook."}
    )
    endpoint_pattern: str = field(
        metadata={
            "doc": "Endpoint URL template learned from repeated browser network evidence."
        }
    )
    method: str = field(
        metadata={"doc": "HTTP method for the deterministic private-API probe."}
    )
    request_shape_summary: str = field(
        metadata={
            "doc": "Prompt-safe documentation of required request shape, parameters, and safe headers."
        }
    )
    response_pdf_url_json_pointer: str = field(
        metadata={
            "doc": "JSON pointer used to extract the PDF URL from the private-API response."
        }
    )
    expected_status_codes: list[int] = field(
        metadata={
            "doc": "HTTP statuses accepted before response-shape validation proceeds."
        }
    )
    required_response_markers: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Case-insensitive response-text markers that must be present before using the response."
        },
    )
    success_count: int = field(
        default=0,
        metadata={
            "doc": "Number of validated successful acquisitions observed before promotion."
        },
    )
    fallback_route_family: str = field(
        default="",
        metadata={
            "doc": "Route family to fall back to when the deterministic endpoint is stale."
        },
    )


@dataclass(frozen=True)
class BrowserRoutePlaybook:
    schema_version: str = field(
        metadata={"doc": "Browser route playbook schema version."}
    )
    playbook_id: str = field(
        metadata={"doc": "Stable unique playbook identifier cited in prompts and logs."}
    )
    version: str = field(
        metadata={"doc": "Semantic playbook version cited with the playbook ID."}
    )
    status: str = field(
        metadata={
            "doc": "Playbook lifecycle status, for example `active` or `deprecated`."
        }
    )
    updated_at: str = field(
        metadata={"doc": "UTC ISO date or timestamp of the latest playbook update."}
    )
    stale_after_days: int = field(
        metadata={"doc": "Maximum age in days before the playbook is considered stale."}
    )
    publisher_pattern: str = field(
        metadata={
            "doc": "Human-readable publisher or domain pattern this playbook covers."
        }
    )
    host_patterns: list[str] = field(
        metadata={
            "doc": "Host glob or suffix patterns eligible for this playbook. `*` means publisher-agnostic."
        }
    )
    url_path_markers: list[str] = field(
        metadata={
            "doc": "Lowercase path/query markers that indicate this route pattern may apply."
        }
    )
    route_family: str = field(
        metadata={
            "doc": "Browser route family this playbook supports, for example `browser_pdf_click`."
        }
    )
    route_kind: str = field(
        metadata={
            "doc": "Expected route kind, for example `pdf_download`, `email_delivery`, or `onsite_report`."
        }
    )
    summary: str = field(
        metadata={"doc": "Concise prompt-safe route guidance summary."}
    )
    steps: list[BrowserRoutePlaybookStep] = field(
        metadata={"doc": "Ordered reusable route steps with verification expectations."}
    )
    traps: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Known traps to avoid, without secrets, credentials, or one-off run narration."
        },
    )
    evidence_notes: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Durable evidence notes explaining why the route pattern is reusable."
        },
    )
    source_evidence: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Reviewable source labels for the evidence used to create or update the playbook."
        },
    )
    private_api_evidence: list[BrowserRoutePrivateApiEvidence] = field(
        default_factory=list,
        metadata={
            "doc": "Validated private XHR/fetch endpoint evidence promoted from browser network observations."
        },
    )
    history: list[BrowserRoutePlaybookHistoryEntry] = field(
        default_factory=list,
        metadata={"doc": "Version/history metadata for reviewable playbook diffs."},
    )


@dataclass(frozen=True)
class BrowserRoutePlaybookSelection:
    schema_version: str = field(
        metadata={"doc": "Browser route playbook selection schema version."}
    )
    playbook_id: str = field(
        metadata={"doc": "Selected playbook ID cited in prompts and logs."}
    )
    version: str = field(
        metadata={"doc": "Selected playbook version cited with the ID."}
    )
    route_family: str = field(
        metadata={"doc": "Route family supported by the selected playbook."}
    )
    route_kind: str = field(
        metadata={"doc": "Expected route kind supported by the selected playbook."}
    )
    match_reason: str = field(
        metadata={"doc": "Short reason the playbook matched this URL and route."}
    )
    summary: str = field(metadata={"doc": "Prompt-safe selected playbook summary."})
    step_lines: list[str] = field(
        metadata={"doc": "Prompt-safe ordered playbook steps with verification notes."}
    )
    trap_lines: list[str] = field(
        default_factory=list,
        metadata={"doc": "Prompt-safe route traps to avoid."},
    )
    private_api_evidence: list[BrowserRoutePrivateApiEvidence] = field(
        default_factory=list,
        metadata={
            "doc": "Deterministic private-API route evidence available before launching browser-use."
        },
    )


@dataclass(frozen=True)
class BrowserRoutePlaybookSelectionResult:
    schema_version: str = field(
        metadata={"doc": "Browser route playbook selection result schema version."}
    )
    selected_playbooks: list[BrowserRoutePlaybookSelection] = field(
        metadata={"doc": "Fresh selected playbooks that may be cited in prompts."}
    )
    stale_playbook_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Matching playbook IDs skipped because they are stale."},
    )
    fallback_to_discovery: bool = field(
        default=False,
        metadata={
            "doc": "Whether normal route discovery should proceed because no fresh playbook was selected."
        },
    )


@dataclass(frozen=True)
class BrowserRoutePlaybookExecutionRequest:
    schema_version: str = field(
        metadata={"doc": "Deterministic playbook execution request schema version."}
    )
    playbook: BrowserRoutePlaybook = field(
        metadata={"doc": "Normal browser route playbook to execute deterministically."}
    )
    normalized_url: str = field(
        metadata={"doc": "Normalized report URL used as execution context."}
    )
    page_driver: Any = field(
        metadata={
            "doc": "Injected browser page-driver boundary implementing deterministic open/click/fill/verify methods."
        }
    )
    identity_values: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "doc": "Injected configured identity values resolved only at deterministic execution time."
        },
    )


@dataclass(frozen=True)
class BrowserRoutePlaybookStepExecution:
    schema_version: str = field(
        metadata={"doc": "Deterministic playbook step execution schema version."}
    )
    index: int = field(metadata={"doc": "Zero-based step index."})
    action: str = field(metadata={"doc": "Executed playbook action."})
    target: str = field(metadata={"doc": "Executed target."})
    status: str = field(metadata={"doc": "executed, skipped, or drifted."})
    evidence: str = field(metadata={"doc": "Observed verification evidence."})
    drift_reason: str = field(
        default="", metadata={"doc": "Reason execution drifted, if any."}
    )


@dataclass(frozen=True)
class BrowserRoutePlaybookExecutionResponse:
    schema_version: str = field(
        metadata={"doc": "Deterministic playbook execution response schema version."}
    )
    status: str = field(metadata={"doc": "completed, skipped, or drifted."})
    playbook_id: str = field(metadata={"doc": "Executed playbook ID."})
    step_results: list[BrowserRoutePlaybookStepExecution] = field(
        metadata={"doc": "Ordered deterministic step results."}
    )
    drift_reasons: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Reasons a route playbook drifted from deterministic execution."
        },
    )


@dataclass(frozen=True)
class BrowserRoutePlaybookPromotionRequest:
    schema_version: str = field(
        metadata={"doc": "Browser route playbook promotion request schema version."}
    )
    playbook_dir: str = field(
        metadata={"doc": "Directory where promoted browser route playbooks are stored."}
    )
    source_url: str = field(
        metadata={"doc": "Validated source URL used to derive host/path patterns."}
    )
    route_family: str = field(
        metadata={"doc": "Verified route family to promote into a playbook."}
    )
    route_kind: str = field(
        metadata={"doc": "Verified route kind to promote into a playbook."}
    )
    route_summary: str = field(
        metadata={"doc": "Verified route summary to store as prompt-safe guidance."}
    )
    route_status: str = field(
        metadata={"doc": "Verification status of the successful route evidence."}
    )
    outcome: str = field(
        metadata={"doc": "Successful route outcome backing the promotion."}
    )
    route_steps: list[BrowserRoutePlaybookStep] = field(
        metadata={"doc": "Reviewable route steps derived from validated evidence."}
    )
    evidence_labels: list[str] = field(
        default_factory=list,
        metadata={"doc": "Evidence labels backing this playbook promotion."},
    )
    observed_at: str = field(
        default="",
        metadata={
            "doc": "UTC ISO timestamp for deterministic tests or live promotion metadata."
        },
    )
    write_file: bool = field(
        default=True,
        metadata={
            "doc": "Whether the promotion service should persist the reviewable playbook YAML. False returns the same target path and diff metadata without writing."
        },
    )


@dataclass(frozen=True)
class BrowserRoutePrivateApiPromotionRequest:
    schema_version: str = field(
        metadata={"doc": "Private-API playbook promotion request schema version."}
    )
    playbook_dir: str = field(
        metadata={"doc": "Root browser-route playbook directory."}
    )
    source_url: str = field(
        metadata={"doc": "Validated source URL used to derive host/path patterns."}
    )
    route_family: str = field(
        metadata={"doc": "Browser route family replaced by the deterministic route."}
    )
    route_kind: str = field(
        metadata={"doc": "Expected result kind produced by the private API route."}
    )
    endpoint_pattern: str = field(
        metadata={"doc": "Endpoint URL template learned from browser network evidence."}
    )
    method: str = field(metadata={"doc": "HTTP method for the learned endpoint."})
    request_shape_summary: str = field(
        metadata={"doc": "Reviewable request-shape documentation."}
    )
    response_pdf_url_json_pointer: str = field(
        metadata={"doc": "JSON pointer that extracts the PDF URL from the response."}
    )
    validated_success_count: int = field(
        metadata={"doc": "Validated repeated successes backing promotion."}
    )
    fallback_route_family: str = field(
        metadata={"doc": "Route family used when the endpoint is stale or rejected."}
    )
    expected_status_codes: list[int] = field(
        default_factory=lambda: [200],
        metadata={"doc": "HTTP statuses accepted before response validation."},
    )
    required_response_markers: list[str] = field(
        default_factory=list,
        metadata={"doc": "Required response-text markers for conservative validation."},
    )
    evidence_labels: list[str] = field(
        default_factory=list,
        metadata={"doc": "Evidence labels backing this private-API promotion."},
    )
    observed_at: str = field(
        default="",
        metadata={"doc": "UTC ISO timestamp for deterministic tests."},
    )
    write_file: bool = field(
        default=True,
        metadata={
            "doc": "Whether promotion should persist the private-API playbook YAML. False returns path and diff metadata without writing."
        },
    )


@dataclass(frozen=True)
class BrowserRoutePrivateApiPromotionCandidate:
    schema_version: str = field(
        metadata={"doc": "Private-API auto-promotion candidate schema version."}
    )
    fingerprint: str = field(
        metadata={
            "doc": "Stable fingerprint for the host, method, endpoint pattern, and response JSON pointer."
        }
    )
    source_url: str = field(
        metadata={
            "doc": "Report source URL whose verified browser run produced the candidate."
        }
    )
    publisher_host: str = field(
        metadata={"doc": "Publisher host associated with the candidate endpoint."}
    )
    endpoint_pattern: str = field(
        metadata={"doc": "Reviewable endpoint pattern with source URL placeholders."}
    )
    endpoint_url: str = field(
        metadata={"doc": "Concrete endpoint URL validated during this observation."}
    )
    method: str = field(metadata={"doc": "HTTP method validated for the endpoint."})
    request_shape_summary: str = field(
        metadata={"doc": "Prompt-safe summary of the validated request shape."}
    )
    response_pdf_url_json_pointer: str = field(
        metadata={"doc": "JSON pointer that yielded the selected PDF URL."}
    )
    selected_pdf_url: str = field(
        metadata={"doc": "PDF URL extracted from the validated endpoint response."}
    )
    expected_status_codes: list[int] = field(
        metadata={"doc": "Accepted status codes observed for the endpoint."}
    )
    required_response_markers: list[str] = field(
        metadata={"doc": "Response markers required before accepting the endpoint."}
    )
    fallback_route_family: str = field(
        metadata={"doc": "Route family used when the private endpoint is stale."}
    )
    route_family: str = field(
        metadata={"doc": "Browser route family replaced by the deterministic route."}
    )
    route_kind: str = field(
        metadata={"doc": "Route kind produced by the deterministic endpoint."}
    )
    evidence_labels: list[str] = field(
        default_factory=list,
        metadata={"doc": "Evidence labels backing this candidate observation."},
    )


@dataclass(frozen=True)
class BrowserRoutePlaybookPromotionResponse:
    schema_version: str = field(
        metadata={"doc": "Browser route playbook promotion response schema version."}
    )
    playbook_id: str = field(
        metadata={"doc": "Created or updated playbook ID; empty when not promotable."}
    )
    version: str = field(
        metadata={"doc": "Version written after promotion; empty when not promotable."}
    )
    path: str = field(
        metadata={
            "doc": "Absolute path of the created or updated playbook file; empty when not promotable."
        }
    )
    status: str = field(
        metadata={"doc": "Promotion status, for example `created` or `updated`."}
    )
    review_diff: str = field(
        metadata={"doc": "Unified diff showing the reviewable file change."}
    )
    reason: str = field(
        default="",
        metadata={
            "doc": "Stable non-promotion reason when status is `not_promotable`; empty after a created, updated, or dry-run promotion."
        },
    )
