from __future__ import annotations

from dataclasses import dataclass, field


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


@dataclass(frozen=True)
class BrowserRoutePlaybookPromotionResponse:
    schema_version: str = field(
        metadata={"doc": "Browser route playbook promotion response schema version."}
    )
    playbook_id: str = field(metadata={"doc": "Created or updated playbook ID."})
    version: str = field(metadata={"doc": "Version written after the promotion."})
    path: str = field(
        metadata={"doc": "Absolute path of the created or updated playbook file."}
    )
    status: str = field(
        metadata={"doc": "Promotion status, for example `created` or `updated`."}
    )
    review_diff: str = field(
        metadata={"doc": "Unified diff showing the reviewable file change."}
    )
