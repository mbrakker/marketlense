from __future__ import annotations

from dataclasses import dataclass, field

from .session_reuse import BrowserDownloadSessionReusePolicy

BROWSER_DEVELOPER_DIAGNOSTICS_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class BrowserDeveloperDiagnosticsRequest:
    schema_version: str = field(
        metadata={"doc": "Browser developer diagnostics request schema version."}
    )
    profile_path: str = field(
        metadata={"doc": "Browser-use profile directory to inspect or create."}
    )
    downloads_path: str = field(
        metadata={"doc": "Browser-use downloads directory to inspect or create."}
    )
    headed: bool = field(
        metadata={"doc": "Whether to run the diagnostic browser in headed mode."}
    )
    verification_url: str = field(
        metadata={
            "doc": "URL opened during the developer diagnostic to verify tab and CDP state."
        }
    )
    cdp_url: str = field(
        default="",
        metadata={
            "doc": "Optional existing Chrome remote-debugging URL to connect to instead of launching a new browser."
        },
    )
    activate_verification_tab: bool = field(
        default=True,
        metadata={
            "doc": "Whether the diagnostic should activate the opened verification tab."
        },
    )
    cleanup_stale_once: bool = field(
        default=True,
        metadata={
            "doc": "Whether to attempt one bounded stale browser-use connection cleanup before verification."
        },
    )
    keep_browser_open: bool = field(
        default=False,
        metadata={
            "doc": "Whether to leave the diagnostic browser session open for manual inspection."
        },
    )
    timeout_seconds: float = field(
        default=20.0,
        metadata={"doc": "Bounded timeout for browser-use diagnostic operations."},
    )
    session_reuse_policy: BrowserDownloadSessionReusePolicy = field(
        default_factory=lambda: BrowserDownloadSessionReusePolicy(
            schema_version=BROWSER_DEVELOPER_DIAGNOSTICS_SCHEMA_VERSION
        ),
        metadata={
            "doc": "Optional developer-canary profile reuse policy for this diagnostic run."
        },
    )


@dataclass(frozen=True)
class BrowserDeveloperDiagnosticCheck:
    schema_version: str = field(
        metadata={"doc": "Browser developer diagnostic check schema version."}
    )
    name: str = field(metadata={"doc": "Stable check identifier."})
    status: str = field(metadata={"doc": "Check status: `ok`, `warning`, or `failed`."})
    message: str = field(metadata={"doc": "Human-readable diagnostic message."})
    detail: str = field(default="", metadata={"doc": "Bounded diagnostic detail."})


@dataclass(frozen=True)
class BrowserDeveloperDiagnosticsResult:
    schema_version: str = field(
        metadata={"doc": "Browser developer diagnostics result schema version."}
    )
    status: str = field(
        metadata={"doc": "Overall diagnostic status: `ok`, `warning`, or `failed`."}
    )
    profile_path: str = field(metadata={"doc": "Resolved profile directory path."})
    downloads_path: str = field(metadata={"doc": "Resolved downloads directory path."})
    cdp_url: str = field(metadata={"doc": "Resolved browser-use CDP URL when known."})
    active_tab_url: str = field(
        metadata={"doc": "Best known active verification tab URL."}
    )
    active_tab_title: str = field(
        metadata={"doc": "Best known active verification tab title."}
    )
    browser_use_connected: bool = field(
        metadata={"doc": "Whether browser-use session startup/connectivity succeeded."}
    )
    cdp_available: bool = field(
        metadata={"doc": "Whether an allowlisted CDP check succeeded."}
    )
    real_tab_available: bool = field(
        metadata={"doc": "Whether a user-facing page tab was available."}
    )
    cleanup_attempted: bool = field(
        metadata={"doc": "Whether stale session cleanup was attempted exactly once."}
    )
    cleanup_status: str = field(
        metadata={"doc": "Cleanup status: `ok`, `skipped`, or `failed`."}
    )
    verification_tab_activated: bool = field(
        metadata={"doc": "Whether the verification tab was explicitly activated."}
    )
    keep_browser_open: bool = field(
        metadata={"doc": "Whether the browser was intentionally left running."}
    )
    checks: tuple[BrowserDeveloperDiagnosticCheck, ...] = field(
        metadata={"doc": "Ordered diagnostic checks with messages and details."}
    )
    error: str = field(
        default="",
        metadata={"doc": "Sanitized top-level failure detail when status is `failed`."},
    )
