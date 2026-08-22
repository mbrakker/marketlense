from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .runtime import BrowserReportDownloadResult


@dataclass(frozen=True)
class BrowserPreflightReuseState:
    schema_version: str = field(
        metadata={"doc": "Browser preflight reuse-state schema version."}
    )
    status: str = field(
        metadata={"doc": "available, unavailable, or skipped."}
    )
    final_url: str = field(metadata={"doc": "Final page URL captured by preflight."})
    cookie_names: list[str] = field(
        default_factory=list,
        metadata={"doc": "Cookie names available for same-session escalation."},
    )
    local_storage_keys: list[str] = field(
        default_factory=list,
        metadata={"doc": "Local-storage keys available for same-session escalation."},
    )
    candidate_pdf_urls: list[str] = field(
        default_factory=list,
        metadata={"doc": "PDF candidates that escalation can reuse."},
    )
    cleanup_required: bool = field(
        default=False,
        metadata={"doc": "Whether a live browser session must be cleaned up."},
    )


@dataclass(frozen=True)
class BrowserPreflightProbeResult:
    schema_version: str = field(
        metadata={"doc": "Browser preflight probe-result schema version."}
    )
    status: str = field(
        metadata={
            "doc": "Probe status: `confirmed_direct_pdf`, `terminal_static_archive`, `escalated`, or `failed`."
        }
    )
    started_url: str = field(
        metadata={"doc": "Execution URL opened by the bounded browser preflight."}
    )
    final_url: str = field(
        metadata={"doc": "Best known browser URL after the bounded preflight."}
    )
    final_title: str = field(
        metadata={"doc": "Best known browser title after the bounded preflight."}
    )
    html_size: int = field(
        metadata={"doc": "Captured rendered HTML character length when available."}
    )
    event_drain_seconds: float = field(
        metadata={"doc": "Bounded event-drain wait duration in seconds."}
    )
    duration_seconds: float = field(
        metadata={"doc": "Total preflight probe wall-clock duration in seconds."}
    )
    candidate_pdf_urls: list[str] = field(
        metadata={
            "doc": "PDF-like URLs discovered from rendered DOM, JavaScript extraction, or drained browser events."
        }
    )
    selected_pdf_url: str = field(
        metadata={
            "doc": "PDF URL selected for direct download when the preflight confirmed a route, else empty string."
        }
    )
    observed_event_urls: list[str] = field(
        metadata={"doc": "Document-like URLs observed from the bounded event drain."}
    )
    network_event_count: int = field(
        metadata={"doc": "Number of browser resource/navigation events drained."}
    )
    evidence_labels: list[str] = field(
        metadata={"doc": "Stable labels describing the evidence collected."}
    )
    escalation_reason: str = field(
        metadata={
            "doc": "Reason the probe escalated to the full browser-use agent, or empty on confirmed routes."
        }
    )
    avoided_agent_call: bool = field(
        metadata={"doc": "Whether the probe avoided a full browser-use LLM agent call."}
    )
    false_negative_rate_sample: float = field(
        metadata={
            "doc": "Per-run false-negative metric sample: 0.0 for confirmed/verified preflight outcomes, 1.0 when later full-agent evidence shows the probe missed an avoidable direct route, else 0.0."
        }
    )
    reuse_state: Optional[BrowserPreflightReuseState] = field(
        default=None,
        metadata={"doc": "Reusable preflight state available to browser escalation."},
    )


@dataclass(frozen=True)
class BrowserPreflightProbeResponse:
    schema_version: str = field(
        metadata={"doc": "Browser preflight probe-response schema version."}
    )
    probe: BrowserPreflightProbeResult = field(
        metadata={"doc": "Typed bounded browser preflight evidence."}
    )
    result: Optional[BrowserReportDownloadResult] = field(
        default=None,
        metadata={
            "doc": "Direct browser-download result when preflight avoided the full agent, else null."
        },
    )
