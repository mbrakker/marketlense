from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class BrowserHelperPageInfo:
    schema_version: str = field(
        metadata={"doc": "Browser helper page-info schema version."}
    )
    url: str = field(metadata={"doc": "Best known page URL, excluding blank pages."})
    title: str = field(metadata={"doc": "Best known page title."})
    html_size: int = field(
        metadata={"doc": "Character length of the captured page HTML."}
    )
    html: str = field(
        metadata={
            "doc": "Full captured page HTML for terminal evidence and downstream validation."
        }
    )
    html_excerpt: str = field(
        metadata={"doc": "Bounded page HTML excerpt for diagnostics."}
    )
    is_real_tab: bool = field(
        metadata={
            "doc": "Whether the page URL appears to be a user-facing browser tab."
        }
    )
    source_labels: tuple[str, ...] = field(
        metadata={
            "doc": "Ordered helper sources that produced URL, title, or HTML fields."
        }
    )


@dataclass(frozen=True)
class BrowserHelperScreenshot:
    schema_version: str = field(
        metadata={"doc": "Browser helper screenshot-result schema version."}
    )
    status: str = field(metadata={"doc": "Screenshot status: `ok` or `failed`."})
    path: str = field(
        metadata={"doc": "Absolute screenshot path when capture succeeded."}
    )
    source: str = field(
        metadata={
            "doc": "Capture source used, for example `browser`, `page`, `page_take_screenshot`, or `cdp`."
        }
    )
    size_bytes: int = field(metadata={"doc": "Captured screenshot size in bytes."})


@dataclass(frozen=True)
class BrowserHelperJsResult:
    schema_version: str = field(
        metadata={"doc": "Browser helper JavaScript result schema version."}
    )
    status: str = field(
        metadata={"doc": "JavaScript evaluation status: `ok` or `failed`."}
    )
    result: object = field(
        metadata={"doc": "Structured JavaScript result value when serializable."}
    )
    result_type: str = field(
        metadata={"doc": "Python type name of the adapted result."}
    )
    snippet: str = field(metadata={"doc": "Sanitized bounded JavaScript snippet."})
    result_serializable: bool = field(
        default=True,
        metadata={
            "doc": "Whether the JavaScript result could be represented as JSON without fallback stringification."
        },
    )
    error: str = field(
        default="",
        metadata={"doc": "Sanitized JavaScript or browser evaluation error."},
    )
    error_line: Optional[int] = field(
        default=None,
        metadata={"doc": "Best known JavaScript exception line number when available."},
    )
    error_column: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Best known JavaScript exception column number when available."
        },
    )


@dataclass(frozen=True)
class BrowserHelperAutocompleteResult:
    schema_version: str = field(
        metadata={"doc": "Browser helper autocomplete-result schema version."}
    )
    status: str = field(
        metadata={"doc": "Autocomplete status: `ok`, `blocked`, or `failed`."}
    )
    attempted_count: int = field(
        metadata={"doc": "Number of form autocomplete controls attempted."}
    )
    selected_count: int = field(
        metadata={"doc": "Number of controls with a verified selected value."}
    )
    submitted: bool = field(
        metadata={"doc": "Whether the helper clicked a submit control after selection."}
    )
    unresolved_fields: tuple[str, ...] = field(
        default_factory=tuple,
        metadata={
            "doc": "Labels for required autocomplete fields that still did not verify."
        }
    )
    selected_fields: tuple[str, ...] = field(
        default_factory=tuple,
        metadata={"doc": "Labels for autocomplete fields that verified successfully."}
    )
    final_url: str = field(
        default="",
        metadata={"doc": "Page URL after the helper action."},
    )
    blocker_code: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Typed blocker code when required autocomplete fields remain unresolved."
        },
    )
    error: str = field(
        default="",
        metadata={"doc": "Sanitized helper failure detail when status is `failed`."},
    )


@dataclass(frozen=True)
class BrowserHelperWaitResult:
    schema_version: str = field(
        metadata={"doc": "Browser helper wait-result schema version."}
    )
    status: str = field(metadata={"doc": "Wait status: `ok` or `failed`."})
    waited_for: str = field(
        metadata={"doc": "Load state or wait primitive requested by the caller."}
    )
    elapsed_seconds: float = field(
        metadata={"doc": "Measured wall-clock wait duration in seconds."}
    )
    error: str = field(
        default="",
        metadata={"doc": "Sanitized wait failure detail when status is `failed`."},
    )


@dataclass(frozen=True)
class BrowserHelperRealTabResult:
    schema_version: str = field(
        metadata={"doc": "Browser helper real-tab diagnostic schema version."}
    )
    status: str = field(metadata={"doc": "Real-tab status: `ok` or `failed`."})
    is_real_tab: bool = field(
        metadata={"doc": "Whether a user-facing page tab is available."}
    )
    url: str = field(metadata={"doc": "Best known user-facing tab URL."})
    title: str = field(metadata={"doc": "Best known user-facing tab title."})
    target_id: str = field(
        default="",
        metadata={"doc": "CDP target ID for the selected real page when available."},
    )
    error: str = field(
        default="",
        metadata={"doc": "Sanitized failure detail when status is `failed`."},
    )


@dataclass(frozen=True)
class BrowserHelperHttpGetResult:
    schema_version: str = field(
        metadata={"doc": "Browser helper HTTP GET result schema version."}
    )
    status: str = field(metadata={"doc": "HTTP helper status: `ok` or `failed`."})
    request_url: str = field(metadata={"doc": "Original HTTP GET URL."})
    final_url: str = field(metadata={"doc": "Final URL after redirects."})
    status_code: int = field(metadata={"doc": "HTTP response status code."})
    content_type: str = field(metadata={"doc": "HTTP response content type."})
    body_size_bytes: int = field(
        metadata={"doc": "Captured text body size in UTF-8 bytes."}
    )
    body_excerpt: str = field(
        metadata={"doc": "Bounded decoded response body excerpt."}
    )
    body_truncated: bool = field(
        metadata={"doc": "Whether the captured body was truncated by policy."}
    )
    error: Optional[str] = field(
        default=None,
        metadata={"doc": "Sanitized failure detail when status is `failed`."},
    )
