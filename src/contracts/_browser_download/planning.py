from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace

from .runtime import BrowserDownloadRouteStep

@dataclass(frozen=True)
class ReportDownloadRoutePlanStep:
    schema_version: str = field(
        metadata={"doc": "Report download route-plan step schema version."}
    )
    step_name: str = field(
        metadata={"doc": "Stable orchestrator step name for this route attempt."}
    )
    route_family: str = field(
        metadata={
            "doc": "Planned route family for this attempt, for example `direct_pdf_probe` or `browser_email_form`."
        }
    )
    attempt_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Concrete URL the service should attempt first for this route step when known."
        },
    )
    route_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Previously successful route summary reused for this attempt when available."
        },
    )
    route_step_hints: list[BrowserDownloadRouteStep] = field(
        default_factory=list,
        metadata={
            "doc": "Previously successful structured route steps reused for this attempt when available."
        },
    )
    route_kind_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Previously observed route kind reused for this attempt when available."
        },
    )
    source_page_url_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Discovery source page URL to revisit when the candidate URL is thin, gated, or tracker-like."
        },
    )
    uses_memory_route: bool = field(
        default=False,
        metadata={"doc": "Whether this step reuses remembered route memory."},
    )
    fallback_on_retryable_error: bool = field(
        default=False,
        metadata={
            "doc": "Whether the orchestrator should continue to the next planned step when this attempt fails with a retryable error."
        },
    )
    recovery_class: str = field(
        default="",
        metadata={
            "doc": "Typed recovery class for observability and policy analysis, for example `browser_to_http_pdf_probe`."
        },
    )
    recovery_decision: str = field(
        default="primary",
        metadata={
            "doc": "Recovery policy decision for this step: `primary`, `allowed`, `blocked`, or `deferred`."
        },
    )


@dataclass(frozen=True)
class ReportDownloadRoutePlanRequest:
    schema_version: str = field(
        metadata={"doc": "Report download route-plan request schema version."}
    )
    normalized_url: str = field(
        metadata={"doc": "Normalized candidate URL used as the route-memory key."}
    )
    remembered_route: Optional["PublisherDownloadRouteMemory"] = field(
        default=None,
        metadata={"doc": "Previously remembered download route when available."},
    )
    candidate_trace: Optional[PublisherInventoryCandidateTrace] = field(
        default=None,
        metadata={
            "doc": "Optional discovery-phase candidate trace reused to choose and verify route order."
        },
    )
    publisher_discovery_route_kind: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional publisher-level discovery route kind from the inventory/diff phase."
        },
    )
    publisher_recommended_discovery_route_kind: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional publisher-level recommended discovery route kind from the inventory/diff phase."
        },
    )


@dataclass(frozen=True)
class ReportDownloadRoutePlanResponse:
    schema_version: str = field(
        metadata={"doc": "Report download route-plan response schema version."}
    )
    steps: list[ReportDownloadRoutePlanStep] = field(
        metadata={"doc": "Ordered download attempts the orchestrator should execute."}
    )
    planning_reason: str = field(
        metadata={
            "doc": "Short human-readable explanation of why this route order was chosen."
        }
    )
    blocked_recovery_classes: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Typed recovery classes that the trigger policy blocked or deferred because they did not add signal."
        },
    )


@dataclass(frozen=True)
class PublisherDownloadRoutePolicySignal:
    schema_version: str = field(
        metadata={"doc": "Publisher route-policy signal schema version."}
    )
    route_family: str = field(
        metadata={
            "doc": "Route family this policy signal describes, for example `http_pdf_probe` or `browser_email_form`."
        }
    )
    route_kind: str = field(
        metadata={
            "doc": "Most recent or dominant route kind observed for this route family."
        }
    )
    attempts: int = field(
        metadata={"doc": "Number of recorded attempts for this route family."}
    )
    verified_successes: int = field(
        metadata={
            "doc": "Number of verified successful outcomes recorded for this route family."
        }
    )
    blocked_attempts: int = field(
        metadata={
            "doc": "Number of attempts that ended with a typed blocker for this route family."
        }
    )
    success_rate: float = field(
        metadata={
            "doc": "Verified-success ratio for this route family, rounded to three decimals."
        }
    )
    confidence_score: float = field(
        metadata={"doc": "Policy confidence score for preferring this route family."}
    )
    rank_score: float = field(
        metadata={
            "doc": "Planner ranking score derived from success rate, confidence, recency, and blocker penalty."
        }
    )
    last_outcome: str = field(
        metadata={"doc": "Most recent outcome observed for this route family."}
    )
    last_route_status: str = field(
        metadata={
            "doc": "Most recent verification status observed for this route family."
        }
    )
    last_blocked_reason: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Most recent typed blocker reason observed for this route family, if any."
        },
    )
    recent_outcomes: list[str] = field(
        default_factory=list,
        metadata={"doc": "Recent outcome labels observed for this route family."},
    )


@dataclass(frozen=True)
class PublisherDownloadRouteMemory:
    schema_version: str = field(
        metadata={"doc": "Publisher remembered download-route schema version."}
    )
    route_kind: str = field(
        metadata={"doc": "Remembered route kind previously observed for this URL."}
    )
    route_summary: str = field(
        metadata={"doc": "Remembered route summary previously observed for this URL."}
    )
    outcome: str = field(
        metadata={"doc": "Remembered route outcome previously observed for this URL."}
    )
    route_family: str = field(
        metadata={"doc": "Remembered route family previously observed for this URL."}
    )
    route_status: str = field(
        metadata={
            "doc": "Remembered route verification status previously observed for this URL."
        }
    )
    resolved_target_url: str = field(
        metadata={"doc": "Remembered resolved target URL for this route."}
    )
    route_steps: list[BrowserDownloadRouteStep] = field(
        default_factory=list,
        metadata={
            "doc": "Remembered structured route steps previously observed for this URL."
        },
    )
    attempts: int = field(
        default=0,
        metadata={
            "doc": "Remembered attempt count backing this route-memory record when available."
        },
    )
    verified_successes: int = field(
        default=0,
        metadata={
            "doc": "Remembered verified success count backing this route-memory record when available."
        },
    )
    last_n_outcomes: list[str] = field(
        default_factory=list,
        metadata={"doc": "Recent remembered outcomes for this route when available."},
    )
    confidence_score: float = field(
        default=0.0,
        metadata={"doc": "Confidence score for reusing this remembered route."},
    )
    exact_route_found: bool = field(
        default=True,
        metadata={
            "doc": "Whether this memory includes exact normalized-URL route history; false means only broader publisher-scope policy was available."
        },
    )
    browser_had_structured_result: bool = field(
        default=True,
        metadata={
            "doc": "Whether the remembered success came from a structured browser result instead of fallback salvage."
        },
    )
    onsite_completeness_status: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Remembered on-site completeness verdict when the route kind is `onsite_report`."
        },
    )
    route_policy: list[PublisherDownloadRoutePolicySignal] = field(
        default_factory=list,
        metadata={
            "doc": "Ranked route-family policy signals learned from exact normalized-URL route history."
        },
    )
    publisher_route_policy: list[PublisherDownloadRoutePolicySignal] = field(
        default_factory=list,
        metadata={
            "doc": "Ranked route-family policy signals learned from same-publisher route history outside the exact URL."
        },
    )

