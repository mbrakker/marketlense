from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any


logger = logging.getLogger("market_lense.browser_report_download_service.cdp")

_CDP_ALLOWLIST: dict[str, str] = {
    "Runtime.evaluate": "Read bounded terminal page state for evidence capture.",
    "Page.enable": "Subscribe to bounded terminal Page events such as JavaScript dialogs.",
    "Page.captureScreenshot": "Persist terminal screenshot evidence when browser-use screenshot hooks fail.",
    "Page.printToPDF": "Persist browser-rendered PDF captures for printable on-site reports.",
    "Page.getLayoutMetrics": "Reject zero-size or stale terminal targets before evidence capture.",
    "Page.handleJavaScriptDialog": "Handle terminal JavaScript dialogs according to browser-download policy.",
    "Target.getTargetInfo": "Inspect focused target identity for diagnostics and logging.",
    "Target.getTargets": "Find a real page target when browser-use session state is unavailable.",
    "Target.attachToTarget": "Create a transient evidence-only CDP session for an allowlisted read.",
    "Target.detachFromTarget": "Clean up a transient evidence-only CDP session.",
    "Target.activateTarget": "Focus a verified user-facing target when headed evidence needs it.",
}
_TARGET_LEVEL_METHODS = {
    "Target.getTargetInfo",
    "Target.getTargets",
    "Target.attachToTarget",
    "Target.detachFromTarget",
    "Target.activateTarget",
}
_INTERNAL_TARGET_URL_PREFIXES = (
    "about:",
    "brave://",
    "chrome://",
    "chrome-error://",
    "chrome-extension://",
    "chrome-search://",
    "chrome-untrusted://",
    "devtools://",
    "edge://",
    "opera://",
    "vivaldi://",
)
_CDP_OPERATION_TIMEOUT_SECONDS = 8.0
_CDP_PRINT_TO_PDF_TIMEOUT_SECONDS = 30.0
_CDP_DIALOG_DRAIN_SECONDS = 0.75
_CDP_DIALOG_MESSAGE_MAX_CHARS = 300


@dataclass(frozen=True)
class BrowserDownloadCdpCallResult:
    schema_version: str = field(metadata={"doc": "CDP call-result schema version."})
    method: str = field(
        metadata={"doc": "Allowlisted Chrome DevTools Protocol method."}
    )
    target_id: str = field(
        metadata={
            "doc": "Browser-use target ID used for this CDP call, else empty string."
        }
    )
    session_id: str = field(
        metadata={
            "doc": "Browser-use CDP session ID used for this CDP call, else empty string."
        }
    )
    status: str = field(metadata={"doc": "Call status: `ok` or `failed`."})
    result: dict[str, Any] = field(
        metadata={
            "doc": "Raw CDP result dictionary when the call succeeds, else empty dict."
        }
    )


@dataclass(frozen=True)
class BrowserDownloadTargetHygieneResult:
    schema_version: str = field(
        metadata={"doc": "Browser target-hygiene result schema version."}
    )
    status: str = field(
        metadata={
            "doc": "Target hygiene status: `ok`, `reattached`, `rejected`, or `failed`."
        }
    )
    selected_target_id: str = field(
        metadata={"doc": "Selected user-facing CDP target ID, else empty string."}
    )
    selected_url: str = field(
        metadata={"doc": "Selected target URL, else empty string."}
    )
    selected_title: str = field(
        metadata={"doc": "Selected target title, else empty string."}
    )
    reason: str = field(
        metadata={"doc": "Short diagnostic explaining the target hygiene decision."}
    )
    activated: bool = field(
        metadata={"doc": "Whether the helper explicitly activated the selected target."}
    )
    attached: bool = field(
        metadata={"doc": "Whether the selected target had or received a CDP session."}
    )
    viewport_width: int = field(
        default=0,
        metadata={"doc": "Observed target viewport width, or 0 when unavailable."},
    )
    viewport_height: int = field(
        default=0,
        metadata={"doc": "Observed target viewport height, or 0 when unavailable."},
    )


@dataclass(frozen=True)
class _ResolvedCdpSession:
    client: Any = field(metadata={"doc": "CDP client used for the call."})
    target_id: str = field(metadata={"doc": "Resolved CDP target ID."})
    session_id: str = field(metadata={"doc": "Resolved CDP session ID."})
    transient: bool = field(
        metadata={"doc": "Whether this helper attached a temporary CDP session."}
    )
