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
class BrowserHelperStandardFormSubmitResult:
    schema_version: str = field(
        metadata={"doc": "Browser helper standard-form submit-result schema version."}
    )
    status: str = field(
        metadata={"doc": "Standard form submit status: `ok`, `blocked`, or `failed`."}
    )
    attempted_count: int = field(
        metadata={"doc": "Number of standard form controls inspected for repair."}
    )
    filled_count: int = field(
        metadata={"doc": "Number of text-like controls filled from configured identity."}
    )
    selected_count: int = field(
        metadata={"doc": "Number of native select controls set and verified."}
    )
    mandatory_agreement_checked_count: int = field(
        metadata={"doc": "Number of mandatory legal/report-delivery checkboxes checked."}
    )
    submitted: bool = field(
        metadata={"doc": "Whether the helper clicked a submit control after repair."}
    )
    unresolved_fields: tuple[str, ...] = field(
        default_factory=tuple,
        metadata={"doc": "Labels for required controls that still did not verify."},
    )
    resolved_fields: tuple[str, ...] = field(
        default_factory=tuple,
        metadata={"doc": "Labels for controls that were repaired and verified."},
    )
    final_url: str = field(
        default="",
        metadata={"doc": "Page URL after the helper action."},
    )
    blocker_code: Optional[str] = field(
        default=None,
        metadata={"doc": "Typed blocker code when required controls remain unresolved."},
    )
    error: str = field(
        default="",
        metadata={"doc": "Sanitized helper failure detail when status is `failed`."},
    )

