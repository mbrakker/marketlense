from __future__ import annotations

import json
import os
from html import escape
from urllib.parse import urlsplit

import streamlit as st

from src.contracts.config import ConfigLoadRequest
from src.contracts.drive import DriveOAuthAuthorizeRequest
from src.contracts.publisher_profiles import (
    PublisherProfilesSnapshotLoadRequest,
    PublisherSyncRequest,
)
from src.contracts.ui_run_control import UiRunPollResponse
from src.generators.publisher_profiles_generator import (
    load_publisher_profiles_snapshot,
)
from src.orchestrators.publisher_sync_orchestrator import run_publisher_sync
from src.services.config_service import load_browser_download_settings
from src.services.drive_service import authorize_oauth_user
from src.ui import state as ui_state
from src.ui.common import (
    UI_SURFACE_EXCEPTIONS,
    _ctx,
    _page_shell,
    _render_empty_state,
    _tip,
)
from src.ui.run_control import launch_background_run, poll_selected_run

_AUDIT_PRESETS: dict[str, tuple[int, int]] = {
    "Quick": (3, 3),
    "Standard": (5, 10),
    "Deep": (12, 20),
}


def _selected_run_payload(
    settings: object, *, run_type: str
) -> UiRunPollResponse | None:
    polled = poll_selected_run(settings, max_bytes=64000)
    if polled is None or polled.record.run_type != run_type:
        return None
    return polled


def _run_status_presentation(polled: UiRunPollResponse | None) -> tuple[str, str]:
    if polled is None:
        return "Ready", "info"
    status = str(getattr(polled.record, "status", "") or "").strip().lower()
    label = status.replace("_", " ").title() or "Ready"
    level_map = {
        "queued": "info",
        "running": "info",
        "succeeded": "success",
        "failed": "error",
        "canceled": "warn",
    }
    return label, level_map.get(status, "info")


def _format_payload(payload: object) -> str:
    if payload in (None, "", [], {}):
        return "{}"
    try:
        return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, default=str)
    except TypeError:
        return str(payload)


def build_publisher_discovery_request_payload(*, insights_url: str) -> dict[str, str]:
    return {"insights_url": str(insights_url or "").strip()}


def build_report_download_request_payload(
    *,
    url: str,
    delivery_email: str,
) -> dict[str, str]:
    return {
        "url": str(url or "").strip(),
        "delivery_email": str(delivery_email or "").strip(),
    }


def build_acquisition_audit_request_payload(
    *,
    publisher_limit: int,
    candidate_limit_per_publisher: int,
    delivery_email: str,
) -> dict[str, int | str]:
    return {
        "publisher_limit": int(publisher_limit),
        "candidate_limit_per_publisher": int(candidate_limit_per_publisher),
        "delivery_email": str(delivery_email or "").strip(),
    }


def build_publisher_choice_options(publishers: list[object]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for publisher in publishers:
        name = str(getattr(publisher, "name", "") or "").strip()
        url = str(getattr(publisher, "insights_url", "") or "").strip()
        if not name or not url:
            continue
        host = str(urlsplit(url).hostname or "").strip().lower()
        label = name if not host else f"{name} ({host})"
        options.append(
            {
                "label": label,
                "name": name,
                "url": url,
                "host": host,
            }
        )
    options.sort(key=lambda item: item["name"].casefold())
    return options


def build_saved_delivery_email_options(browser_settings: object | None) -> list[str]:
    identity_profile = getattr(browser_settings, "identity_profile", None)
    if identity_profile is None:
        return []
    raw_values: list[object] = []
    raw_values.extend(getattr(identity_profile, "delivery_emails", []) or [])
    for field in getattr(identity_profile, "fields", []) or []:
        raw_values.append(getattr(field, "value", None))
    for override in getattr(identity_profile, "publisher_overrides", []) or []:
        raw_values.extend(getattr(override, "delivery_emails", []) or [])
        for field in getattr(override, "field_values", []) or []:
            raw_values.append(getattr(field, "value", None))

    emails: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        token = str(raw_value or "").strip()
        if "@" not in token:
            continue
        marker = token.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        emails.append(token)
    return emails


def resolve_delivery_email_value(
    *,
    mode: str,
    saved_email: str,
    custom_email: str,
) -> str:
    if mode == "Use saved email":
        return str(saved_email or "").strip()
    if mode == "Custom email":
        return str(custom_email or "").strip()
    return ""


def resolve_audit_limits(
    *,
    preset: str,
    custom_publisher_limit: int,
    custom_candidate_limit: int,
) -> tuple[int, int]:
    if preset in _AUDIT_PRESETS:
        return _AUDIT_PRESETS[preset]
    return int(custom_publisher_limit), int(custom_candidate_limit)


def resolve_path_choice(
    *,
    mode: str,
    configured_path: str,
    custom_path: str,
) -> str:
    if mode == "Custom path":
        return str(custom_path or "").strip()
    return str(configured_path or "").strip()


def _render_guided_panel(title: str, description: str, *, tooltip: str) -> None:
    st.markdown(
        (
            f'<div class="ml-panel" title="{escape(tooltip)}">'
            f"<h4>{escape(title)}</h4>"
            f"<p>{escape(description)}</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_readonly_fields(
    fields: list[dict[str, str]],
    *,
    columns: int,
    key_prefix: str,
) -> None:
    if not fields:
        return
    safe_columns = max(1, int(columns))
    for row_start in range(0, len(fields), safe_columns):
        chunk = fields[row_start : row_start + safe_columns]
        row_columns = st.columns(len(chunk), gap="large")
        for index, field in enumerate(chunk):
            with row_columns[index]:
                st.text_input(
                    field["label"],
                    value=field["value"],
                    disabled=True,
                    help=field["help"],
                    key=f"{key_prefix}_{row_start}_{index}",
                )


def _render_payload_area(
    label: str,
    payload: object,
    *,
    help_text: str,
    key: str,
    height: int = 220,
) -> None:
    st.text_area(
        label,
        value=_format_payload(payload),
        disabled=True,
        height=height,
        help=help_text,
        key=key,
    )


def _render_run_summary(
    polled: UiRunPollResponse | None,
    *,
    key_prefix: str,
    empty_title: str,
    empty_detail: str,
    summary_label: str,
) -> None:
    if polled is None:
        _render_empty_state(empty_title, empty_detail)
        return
    record = polled.record
    _render_readonly_fields(
        [
            {
                "label": "Run status",
                "value": str(getattr(record, "status", "") or "").replace("_", " ").title(),
                "help": _tip(
                    "Current lifecycle state for the selected background job.",
                    "Succeeded means the worker finished without an error.",
                ),
            },
            {
                "label": "Artifacts saved",
                "value": f"{len(getattr(record, 'artifact_paths', []) or [])} file(s)",
                "help": _tip(
                    "How many output files this run has registered so far.",
                    "Use this count to confirm whether the run produced saved artifacts.",
                ),
            },
        ],
        columns=2,
        key_prefix=f"{key_prefix}_summary_fields",
    )
    _render_payload_area(
        summary_label,
        getattr(record, "result_summary", {}) or {},
        help_text=_tip(
            "Structured summary returned by the workflow after it completed or progressed.",
            "This is the quickest place to inspect the latest result without opening raw logs.",
        ),
        key=f"{key_prefix}_summary_payload",
        height=260,
    )


def _render_run_details(
    polled: UiRunPollResponse | None,
    *,
    key_prefix: str,
    empty_title: str,
    empty_detail: str,
) -> None:
    if polled is None:
        _render_empty_state(empty_title, empty_detail)
        return
    record = polled.record
    _render_readonly_fields(
        [
            {
                "label": "Run ID",
                "value": str(getattr(record, "run_id", "") or ""),
                "help": _tip(
                    "Stable identifier for the selected background run.",
                    "Use this ID when matching the page state with Run Center.",
                ),
            },
            {
                "label": "Workflow",
                "value": str(getattr(record, "display_name", "") or getattr(record, "run_type", "") or ""),
                "help": _tip(
                    "Human-readable workflow name for the selected run.",
                    "This tells you which background tool produced the results shown here.",
                ),
            },
            {
                "label": "Started at",
                "value": str(getattr(record, "started_at_utc", "") or ""),
                "help": _tip(
                    "UTC timestamp when the background worker started execution.",
                    "If this is blank, the run is still queued.",
                ),
            },
            {
                "label": "Finished at",
                "value": str(getattr(record, "finished_at_utc", "") or ""),
                "help": _tip(
                    "UTC timestamp when the background worker finished.",
                    "Blank means the run is still active or has not written a terminal state yet.",
                ),
            },
        ],
        columns=1,
        key_prefix=f"{key_prefix}_detail_fields",
    )
    artifact_paths = getattr(record, "artifact_paths", []) or []
    if artifact_paths:
        _render_payload_area(
            "Saved file paths",
            artifact_paths,
            help_text=_tip(
                "Exact files registered by the run as saved artifacts.",
                "Open these paths when you want the generated evidence or exports.",
            ),
            key=f"{key_prefix}_artifact_paths",
            height=150,
        )
    output_chunk = getattr(polled, "output_chunk", None)
    if output_chunk is not None:
        st.text_area(
            "Latest worker output",
            value=str(getattr(output_chunk, "text", "") or "[worker] no output yet"),
            disabled=True,
            height=180,
            help=_tip(
                "Latest captured console output from the background worker.",
                "Use this to understand what the worker is doing right now.",
            ),
            key=f"{key_prefix}_worker_output",
        )
    _render_payload_area(
        "Technical details",
        record.__dict__,
        help_text=_tip(
            "Raw run metadata stored in the run registry.",
            "Use this if you need the full structured record behind the current page state.",
        ),
        key=f"{key_prefix}_technical_details",
        height=220,
    )


def _load_saved_publishers(settings: object) -> tuple[list[dict[str, str]], str | None]:
    try:
        response = load_publisher_profiles_snapshot(
            PublisherProfilesSnapshotLoadRequest(
                schema_version="1.0",
                snapshot_path=str(getattr(settings, "publisher_profiles_path", "") or ""),
            ),
            _ctx("publisher_profiles_snapshot"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:
        return [], str(exc)
    return build_publisher_choice_options(list(response.publishers)), None


def _load_browser_defaults() -> tuple[object | None, list[str], str | None]:
    try:
        browser_settings = load_browser_download_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            _ctx("browser_download_settings"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:
        return None, [], str(exc)
    return browser_settings, build_saved_delivery_email_options(browser_settings), None


def render_publisher_discovery() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    publisher_options, publisher_error = _load_saved_publishers(settings)
    polled = _selected_run_payload(settings, run_type="publisher_discovery")
    status_label, status_level = _run_status_presentation(polled)
    clicked, filters, main_col, detail_col = _page_shell(
        "Publisher Discovery",
        status_label=status_label,
        status_level=status_level,
        primary_action="Run Discovery",
        primary_help=_tip(
            "Launch publisher inventory discovery as a tracked background job.",
            "Pick a saved publisher page or type a custom insights URL to inspect route quality.",
        ),
        primary_key="run_publisher_discovery",
    )
    with filters:
        _render_guided_panel(
            "Pick a publisher page and start the scan",
            "Use a saved publisher when possible. Switch to a custom URL only when the page is not already in your snapshot.",
            tooltip=_tip(
                "Guided setup for publisher discovery.",
                "Saved publishers reduce typing and lower the chance of malformed URLs.",
            ),
        )
        if publisher_error:
            st.warning(
                "Saved publisher suggestions are unavailable right now. You can still run discovery with a custom URL."
            )
        source_mode_options = (
            ["Saved publisher", "Custom URL"] if publisher_options else ["Custom URL"]
        )
        source_mode = st.segmented_control(
            "Start from",
            options=source_mode_options,
            default=source_mode_options[0],
            help=_tip(
                "Choose whether to start from a known publisher page or type a one-off URL.",
                "Use 'Saved publisher' for the simplest operator workflow.",
            ),
            key="publisher_discovery_source_mode",
        )
        selected_url = ""
        if source_mode == "Saved publisher":
            selected_label = st.selectbox(
                "Saved publisher",
                options=[item["label"] for item in publisher_options],
                help=_tip(
                    "Choose a publisher already stored in your snapshot.",
                    "The app will use that publisher's saved insights page for discovery.",
                ),
                key="publisher_discovery_saved_publisher",
            )
            option_lookup = {item["label"]: item for item in publisher_options}
            selected_url = option_lookup[selected_label]["url"]
            st.text_input(
                "Selected insights URL",
                value=selected_url,
                disabled=True,
                help=_tip(
                    "Resolved publisher page that will be sent to the workflow.",
                    "Switch to custom mode only if you need a page not listed here.",
                ),
                key="publisher_discovery_selected_url",
            )
        else:
            selected_url = st.text_input(
                "Insights URL",
                value="",
                help=_tip(
                    "Absolute publisher insights or reports URL to discover against.",
                    "Example: https://example.com/insights",
                ),
                key="publisher_discovery_custom_url",
            ).strip()
    if clicked:
        if not selected_url.strip():
            st.warning("Pick a saved publisher or enter an insights URL before launching discovery.")
        else:
            response = launch_background_run(
                settings,
                run_type="publisher_discovery",
                display_name="Publisher discovery",
                request_payload=build_publisher_discovery_request_payload(
                    insights_url=selected_url
                ),
            )
            st.success(f"Discovery launched: {response.record.run_id}")
    with main_col:
        _render_guided_panel(
            "What this run does",
            "The workflow checks the selected publisher page, traces discovery routes, and stores a structured result you can revisit from Run Center.",
            tooltip=_tip(
                "Short plain-language description of publisher discovery.",
                "Use this run when you need to confirm how the app finds a publisher's report inventory.",
            ),
        )
        st.subheader("Discovery summary")
        _render_run_summary(
            polled,
            key_prefix="publisher_discovery",
            empty_title="No discovery summary yet",
            empty_detail="Run discovery to see route quality, diff items, and saved artifact details.",
            summary_label="Latest discovery result",
        )
    with detail_col:
        st.subheader("Current selection")
        _render_readonly_fields(
            [
                {
                    "label": "Chosen publisher page",
                    "value": selected_url or "Not set yet",
                    "help": _tip(
                        "The exact page that will be used for the next discovery run.",
                        "Review this value before launching the workflow.",
                    ),
                }
            ],
            columns=1,
            key_prefix="publisher_discovery_selection",
        )
        st.subheader("Run details")
        _render_run_details(
            polled,
            key_prefix="publisher_discovery",
            empty_title="No discovery run selected",
            empty_detail="Launch discovery here or select a matching run from Run Center to inspect it.",
        )


def render_report_download_lab() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    publisher_options, publisher_error = _load_saved_publishers(settings)
    browser_settings, saved_emails, browser_error = _load_browser_defaults()
    polled = _selected_run_payload(settings, run_type="report_download")
    status_label, status_level = _run_status_presentation(polled)
    clicked, filters, main_col, detail_col = _page_shell(
        "Report Download Lab",
        status_label=status_label,
        status_level=status_level,
        primary_action="Run Download",
        primary_help=_tip(
            "Launch report acquisition as a tracked background job.",
            "Use a saved publisher page and saved email when possible to avoid manual typing.",
        ),
        primary_key="run_report_download_lab",
    )
    with filters:
        _render_guided_panel(
            "Choose the page and delivery email",
            "Start from a saved publisher page when possible, then decide whether the workflow should submit a saved email, no email, or a custom email address.",
            tooltip=_tip(
                "Guided setup for report download.",
                "This page is designed so operators can work mostly from known-good choices instead of raw inputs.",
            ),
        )
        if publisher_error:
            st.warning(
                "Saved publisher suggestions are unavailable right now. You can still provide a custom report URL."
            )
        if browser_error:
            st.warning(
                "Saved delivery email suggestions are unavailable right now. You can still run with no email or type a custom one."
            )
        source_mode_options = (
            ["Saved publisher", "Custom URL"] if publisher_options else ["Custom URL"]
        )
        source_mode = st.segmented_control(
            "Page source",
            options=source_mode_options,
            default=source_mode_options[0],
            help=_tip(
                "Choose whether to start from a saved publisher page or a one-off report URL.",
                "Saved publisher pages are better for non-technical operators.",
            ),
            key="report_download_source_mode",
        )
        selected_url = ""
        if source_mode == "Saved publisher":
            selected_label = st.selectbox(
                "Saved publisher page",
                options=[item["label"] for item in publisher_options],
                help=_tip(
                    "Choose a saved publisher page from the snapshot.",
                    "The workflow will use that page as the starting point for report acquisition.",
                ),
                key="report_download_saved_publisher",
            )
            option_lookup = {item["label"]: item for item in publisher_options}
            selected_url = option_lookup[selected_label]["url"]
            st.text_input(
                "Selected page URL",
                value=selected_url,
                disabled=True,
                help=_tip(
                    "Resolved publisher page that will be sent to the download workflow.",
                    "Switch to custom mode if you need a page not listed here.",
                ),
                key="report_download_selected_url",
            )
        else:
            selected_url = st.text_input(
                "Report URL",
                value="",
                help=_tip(
                    "Absolute report landing page URL to acquire.",
                    "Example: https://example.com/report",
                ),
                key="report_download_custom_url",
            ).strip()

        email_mode_options = ["No email"]
        if saved_emails:
            email_mode_options.insert(0, "Use saved email")
        email_mode_options.append("Custom email")
        email_mode = st.segmented_control(
            "Delivery email",
            options=email_mode_options,
            default=email_mode_options[0],
            help=_tip(
                "Choose how the workflow should handle email-gated download forms.",
                "Use a saved email for the fastest setup when a known operator address already exists.",
            ),
            key="report_download_email_mode",
        )
        saved_email_value = saved_emails[0] if saved_emails else ""
        custom_email_value = ""
        if email_mode == "Use saved email" and saved_emails:
            if len(saved_emails) == 1:
                saved_email_value = saved_emails[0]
                st.text_input(
                    "Saved delivery email",
                    value=saved_email_value,
                    disabled=True,
                    help=_tip(
                        "Known operator email loaded from the browser download identity profile.",
                        "This value will be used when a report page requires an email submission.",
                    ),
                    key="report_download_saved_email_single",
                )
            else:
                saved_email_value = st.selectbox(
                    "Saved delivery email",
                    options=saved_emails,
                    help=_tip(
                        "Choose which configured operator email to submit on gated forms.",
                        "Pick the email address that should receive follow-up messages.",
                    ),
                    key="report_download_saved_email_multi",
                )
        elif email_mode == "Custom email":
            custom_email_value = st.text_input(
                "Custom delivery email",
                value="",
                help=_tip(
                    "Optional email address to use when the report is gated behind an email form.",
                    "Leave the mode on 'No email' for open PDF or direct-download pages.",
                ),
                key="report_download_custom_email",
            ).strip()

    resolved_email = resolve_delivery_email_value(
        mode=email_mode,
        saved_email=saved_email_value,
        custom_email=custom_email_value,
    )
    if clicked:
        if not selected_url.strip():
            st.warning("Pick a saved publisher page or enter a report URL before launching download.")
        else:
            response = launch_background_run(
                settings,
                run_type="report_download",
                display_name="Report download",
                request_payload=build_report_download_request_payload(
                    url=selected_url,
                    delivery_email=resolved_email,
                ),
            )
            st.success(f"Report download launched: {response.record.run_id}")
    with main_col:
        _render_guided_panel(
            "What this run does",
            "The workflow opens the selected page, decides which route worked, and records both the outcome and any saved file paths.",
            tooltip=_tip(
                "Short plain-language description of report download.",
                "Use this page when you want the control panel to handle a report acquisition workflow for you.",
            ),
        )
        st.subheader("Download summary")
        _render_run_summary(
            polled,
            key_prefix="report_download",
            empty_title="No download summary yet",
            empty_detail="Run report download to inspect route outcomes, saved files, and the latest structured result.",
            summary_label="Latest download result",
        )
    with detail_col:
        st.subheader("Current selection")
        _render_readonly_fields(
            [
                {
                    "label": "Chosen page URL",
                    "value": selected_url or "Not set yet",
                    "help": _tip(
                        "The exact page the workflow will open for the next download run.",
                        "Review this value before launching download.",
                    ),
                },
                {
                    "label": "Chosen delivery email",
                    "value": resolved_email or "No email will be submitted",
                    "help": _tip(
                        "Email address that will be used for gated forms, if any.",
                        "If this shows 'No email', the workflow will not submit an email field.",
                    ),
                },
                {
                    "label": "Identity profile file",
                    "value": str(getattr(browser_settings, "identity_config_path", "") or "Unavailable"),
                    "help": _tip(
                        "Source file used to load saved browser form identity values.",
                        "This helps operators understand where the saved delivery email came from.",
                    ),
                },
            ],
            columns=1,
            key_prefix="report_download_selection",
        )
        st.subheader("Run details")
        _render_run_details(
            polled,
            key_prefix="report_download",
            empty_title="No download run selected",
            empty_detail="Launch report download here or select a matching run from Run Center to inspect it.",
        )


def render_acquisition_audit() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    browser_settings, saved_emails, browser_error = _load_browser_defaults()
    polled = _selected_run_payload(settings, run_type="acquisition_audit")
    status_label, status_level = _run_status_presentation(polled)
    clicked, filters, main_col, detail_col = _page_shell(
        "Acquisition Audit",
        status_label=status_label,
        status_level=status_level,
        primary_action="Run Audit",
        primary_help=_tip(
            "Launch acquisition-path auditing as a tracked background job.",
            "Use a preset audit size for the simplest workflow and open custom limits only when needed.",
        ),
        primary_key="run_acquisition_audit",
    )
    with filters:
        _render_guided_panel(
            "Choose how deep the audit should go",
            "Start with a preset size. Only switch to custom limits when you need a very small debug run or a larger investigation.",
            tooltip=_tip(
                "Guided setup for acquisition audits.",
                "Presets reduce the amount of numeric tuning a regular operator needs to do.",
            ),
        )
        if browser_error:
            st.warning(
                "Saved delivery email suggestions are unavailable right now. You can still run with no email or type a custom one."
            )
        preset = st.segmented_control(
            "Audit size",
            options=["Quick", "Standard", "Deep", "Custom"],
            default="Standard",
            help=_tip(
                "Choose how many publishers and candidate pages the audit should inspect.",
                "Use 'Quick' for route debugging and 'Standard' for a normal health check.",
            ),
            key="acquisition_audit_size",
        )
        custom_publisher_limit = _AUDIT_PRESETS["Standard"][0]
        custom_candidate_limit = _AUDIT_PRESETS["Standard"][1]
        if preset == "Custom":
            limit_left, limit_right = st.columns(2, gap="large")
            with limit_left:
                custom_publisher_limit = st.number_input(
                    "Publishers to inspect",
                    min_value=1,
                    max_value=500,
                    value=_AUDIT_PRESETS["Standard"][0],
                    step=1,
                    help=_tip(
                        "Maximum number of publishers the audit should inspect.",
                        "Use a lower number for faster debug runs.",
                    ),
                    key="acquisition_audit_custom_publishers",
                )
            with limit_right:
                custom_candidate_limit = st.number_input(
                    "Candidates per publisher",
                    min_value=1,
                    max_value=100,
                    value=_AUDIT_PRESETS["Standard"][1],
                    step=1,
                    help=_tip(
                        "Maximum number of candidate pages the audit should inspect per publisher.",
                        "Lower this value when you only need a quick route-health sample.",
                    ),
                    key="acquisition_audit_custom_candidates",
                )
        resolved_publisher_limit, resolved_candidate_limit = resolve_audit_limits(
            preset=preset,
            custom_publisher_limit=int(custom_publisher_limit),
            custom_candidate_limit=int(custom_candidate_limit),
        )
        if preset != "Custom":
            _render_readonly_fields(
                [
                    {
                        "label": "Publishers to inspect",
                        "value": str(resolved_publisher_limit),
                        "help": _tip(
                            "Number of publishers the chosen preset will inspect.",
                            "This value changes automatically when you switch presets.",
                        ),
                    },
                    {
                        "label": "Candidates per publisher",
                        "value": str(resolved_candidate_limit),
                        "help": _tip(
                            "Number of candidate pages the chosen preset will inspect for each publisher.",
                            "This value changes automatically when you switch presets.",
                        ),
                    },
                ],
                columns=2,
                key_prefix="acquisition_audit_preset_summary",
            )

        email_mode_options = ["No email"]
        if saved_emails:
            email_mode_options.insert(0, "Use saved email")
        email_mode_options.append("Custom email")
        email_mode = st.segmented_control(
            "Delivery email",
            options=email_mode_options,
            default=email_mode_options[0],
            help=_tip(
                "Choose whether the audit may use an email address on gated report forms.",
                "Use a saved email when you want the audit to test email-protected routes automatically.",
            ),
            key="acquisition_audit_email_mode",
        )
        saved_email_value = saved_emails[0] if saved_emails else ""
        custom_email_value = ""
        if email_mode == "Use saved email" and saved_emails:
            if len(saved_emails) == 1:
                saved_email_value = saved_emails[0]
                st.text_input(
                    "Saved delivery email",
                    value=saved_email_value,
                    disabled=True,
                    help=_tip(
                        "Known operator email loaded from the browser identity profile.",
                        "This value will be used on email-gated routes during the audit.",
                    ),
                    key="acquisition_audit_saved_email_single",
                )
            else:
                saved_email_value = st.selectbox(
                    "Saved delivery email",
                    options=saved_emails,
                    help=_tip(
                        "Choose which configured operator email the audit may use.",
                        "Pick the email address that should receive gated download confirmations.",
                    ),
                    key="acquisition_audit_saved_email_multi",
                )
        elif email_mode == "Custom email":
            custom_email_value = st.text_input(
                "Custom delivery email",
                value="",
                help=_tip(
                    "Optional email address used when the audit hits an email-gated report page.",
                    "Leave the mode on 'No email' for download-only audits.",
                ),
                key="acquisition_audit_custom_email",
            ).strip()

    resolved_email = resolve_delivery_email_value(
        mode=email_mode,
        saved_email=saved_email_value,
        custom_email=custom_email_value,
    )
    if clicked:
        response = launch_background_run(
            settings,
            run_type="acquisition_audit",
            display_name="Acquisition audit",
            request_payload=build_acquisition_audit_request_payload(
                publisher_limit=resolved_publisher_limit,
                candidate_limit_per_publisher=resolved_candidate_limit,
                delivery_email=resolved_email,
            ),
        )
        st.success(f"Acquisition audit launched: {response.record.run_id}")
    with main_col:
        _render_guided_panel(
            "What this run does",
            "The workflow samples publisher routes, checks which acquisition paths still work, and stores a structured audit result you can review later.",
            tooltip=_tip(
                "Short plain-language description of acquisition audit.",
                "Use this page when you want a controlled health check across multiple publishers.",
            ),
        )
        st.subheader("Audit summary")
        _render_run_summary(
            polled,
            key_prefix="acquisition_audit",
            empty_title="No audit summary yet",
            empty_detail="Run an acquisition audit to inspect publisher recommendations, candidate counts, and saved artifacts.",
            summary_label="Latest audit result",
        )
    with detail_col:
        st.subheader("Current selection")
        _render_readonly_fields(
            [
                {
                    "label": "Publishers to inspect",
                    "value": str(resolved_publisher_limit),
                    "help": _tip(
                        "Number of publishers the next audit run will inspect.",
                        "Check this before launching when you need a fast or deep audit.",
                    ),
                },
                {
                    "label": "Candidates per publisher",
                    "value": str(resolved_candidate_limit),
                    "help": _tip(
                        "Number of candidate pages the next audit run will inspect for each publisher.",
                        "Use a smaller value for quick route debugging.",
                    ),
                },
                {
                    "label": "Chosen delivery email",
                    "value": resolved_email or "No email will be submitted",
                    "help": _tip(
                        "Email address that may be used on gated pages during the audit.",
                        "If this shows 'No email', the audit will not submit email fields.",
                    ),
                },
                {
                    "label": "Identity profile file",
                    "value": str(getattr(browser_settings, "identity_config_path", "") or "Unavailable"),
                    "help": _tip(
                        "Source file used to load saved browser identity values for the audit.",
                        "This explains where the saved delivery email came from.",
                    ),
                },
            ],
            columns=1,
            key_prefix="acquisition_audit_selection",
        )
        st.subheader("Run details")
        _render_run_details(
            polled,
            key_prefix="acquisition_audit",
            empty_title="No audit run selected",
            empty_detail="Launch an audit here or select a matching run from Run Center to inspect it.",
        )


def render_publisher_sync() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    clicked, filters, main_col, detail_col = _page_shell(
        "Publisher Sync",
        status_label="Ready",
        status_level="info",
        primary_action="Sync Publishers",
        primary_help=_tip(
            "Synchronize publisher snapshot JSON into the reports database.",
            "Use the configured snapshot unless you have a one-off replacement file for this session.",
        ),
        primary_key="run_publisher_sync",
    )
    with filters:
        _render_guided_panel(
            "Choose which snapshot to sync",
            "Most operators should use the configured snapshot path. Switch to a custom path only when you intentionally want to sync a different JSON file.",
            tooltip=_tip(
                "Guided setup for publisher sync.",
                "The configured path is the safest default because it follows the project's normal snapshot source.",
            ),
        )
        path_mode = st.segmented_control(
            "Snapshot source",
            options=["Configured path", "Custom path"],
            default="Configured path",
            help=_tip(
                "Choose whether to use the configured snapshot file or type a one-off override.",
                "Use the configured path for normal operations.",
            ),
            key="publisher_sync_path_mode",
        )
        snapshot_path = resolve_path_choice(
            mode=path_mode,
            configured_path=str(settings.publisher_profiles_path or ""),
            custom_path="",
        )
        if path_mode == "Custom path":
            snapshot_path = resolve_path_choice(
                mode=path_mode,
                configured_path=str(settings.publisher_profiles_path or ""),
                custom_path=st.text_input(
                    "Custom snapshot path",
                    value=str(settings.publisher_profiles_path or ""),
                    help=_tip(
                        "Optional snapshot JSON override used for this sync only.",
                        "Use a full path to a publisher snapshot JSON file when you need a one-off sync source.",
                    ),
                    key="publisher_sync_custom_path",
                ),
            )
        else:
            st.text_input(
                "Configured snapshot path",
                value=str(settings.publisher_profiles_path or ""),
                disabled=True,
                help=_tip(
                    "Default publisher snapshot file used by the project.",
                    "This is the normal path regular operators should keep for sync.",
                ),
                key="publisher_sync_configured_path",
            )
        st.text_input(
            "Target database",
            value=str(settings.reports_db or ""),
            disabled=True,
            help=_tip(
                "Reports SQLite database that will receive the synchronized publisher rows.",
                "This is the destination for the sync action.",
            ),
            key="publisher_sync_reports_db",
        )
    if clicked:
        if not snapshot_path.strip():
            st.warning("Choose a configured snapshot or enter a custom snapshot path before syncing.")
        else:
            try:
                result = run_publisher_sync(
                    PublisherSyncRequest(
                        schema_version="1.0",
                        snapshot_path=snapshot_path.strip(),
                        reports_db=settings.reports_db,
                    ),
                    ctx=_ctx("publisher_sync"),
                )
                st.session_state["last_publisher_sync_result"] = result
                st.success(f"Publisher sync complete: {result.replaced_count} rows replaced.")
            except UI_SURFACE_EXCEPTIONS as exc:
                st.error(str(exc))
    result = st.session_state.get("last_publisher_sync_result")
    with main_col:
        _render_guided_panel(
            "What this action does",
            "The sync reads the publisher snapshot JSON and replaces the publisher rows stored in the reports database.",
            tooltip=_tip(
                "Short plain-language description of publisher sync.",
                "Use this after the snapshot file has been refreshed and you want the database to match it.",
            ),
        )
        st.subheader("Latest sync result")
        if result is None:
            _render_empty_state(
                "No publisher sync has run in this session",
                "Run sync to see how many publisher rows were replaced and which snapshot file was used.",
            )
        else:
            _render_readonly_fields(
                [
                    {
                        "label": "Rows replaced",
                        "value": str(getattr(result, "replaced_count", "") or ""),
                        "help": _tip(
                            "How many publisher rows were written into the reports database by the latest sync.",
                            "A non-zero count means the database was refreshed from the snapshot.",
                        ),
                    },
                    {
                        "label": "Source page",
                        "value": str(getattr(result, "source_page_url", "") or ""),
                        "help": _tip(
                            "Original Notion source page recorded in the synchronized snapshot.",
                            "This helps confirm where the synced publisher data came from.",
                        ),
                    },
                ],
                columns=2,
                key_prefix="publisher_sync_result_fields",
            )
            _render_payload_area(
                "Sync details",
                result.__dict__ if hasattr(result, "__dict__") else result,
                help_text=_tip(
                    "Full structured result from the latest publisher sync in this session.",
                    "Use this if you need the raw metadata behind the sync action.",
                ),
                key="publisher_sync_result_payload",
                height=220,
            )
    with detail_col:
        st.subheader("Current selection")
        _render_readonly_fields(
            [
                {
                    "label": "Snapshot path for next sync",
                    "value": snapshot_path or "Not set yet",
                    "help": _tip(
                        "Snapshot JSON file that will be used for the next sync action.",
                        "Review this before launching sync, especially when using a custom path.",
                    ),
                },
                {
                    "label": "Reports database",
                    "value": str(settings.reports_db or ""),
                    "help": _tip(
                        "Database file that will receive the synchronized publisher rows.",
                        "This is the destination for the next sync action.",
                    ),
                },
            ],
            columns=1,
            key_prefix="publisher_sync_selection",
        )


def render_auth_access() -> None:
    settings = ui_state.get_app_settings()
    publish_settings = ui_state.get_publish_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return

    configured_client_path = str(settings.google_oauth_client_path or "")
    configured_token_path = str(settings.google_oauth_token_path or "")
    requires_oauth_files = settings.drive_auth_mode == "oauth_user"
    status_level = (
        "warn"
        if requires_oauth_files and (not configured_client_path.strip() or not configured_token_path.strip())
        else "info"
    )
    status_label = "Needs setup" if status_level == "warn" else "Ready"
    clicked, filters, main_col, detail_col = _page_shell(
        "Auth & External Access",
        status_label=status_label,
        status_level=status_level,
        primary_action="Drive OAuth Login",
        primary_help=_tip(
            "Run the interactive Drive OAuth user-consent flow.",
            "Use the configured OAuth files unless you intentionally need a one-off local override.",
        ),
        primary_key="run_drive_oauth_login",
    )
    with filters:
        _render_guided_panel(
            "Use configured OAuth files unless you are debugging",
            "Most operators should keep the configured OAuth client and token paths. Switch to custom paths only for a one-off local test.",
            tooltip=_tip(
                "Guided setup for Drive OAuth login.",
                "Configured files are the safest path for a non-technical operator because the project already expects them.",
            ),
        )
        path_mode = st.segmented_control(
            "OAuth file source",
            options=["Configured path", "Custom path"],
            default="Configured path",
            help=_tip(
                "Choose whether to use the project's configured OAuth files or type a local override.",
                "Use the configured path for the normal login flow.",
            ),
            key="auth_access_path_mode",
        )
        if path_mode == "Custom path":
            resolved_client_path = resolve_path_choice(
                mode=path_mode,
                configured_path=configured_client_path,
                custom_path=st.text_input(
                    "Custom OAuth client JSON",
                    value=configured_client_path,
                    help=_tip(
                        "Path to the OAuth desktop client JSON file used for Drive user consent.",
                        "Use a custom path only when your local machine needs a different OAuth client file.",
                    ),
                    key="auth_access_custom_client_json",
                ),
            )
            resolved_token_path = resolve_path_choice(
                mode=path_mode,
                configured_path=configured_token_path,
                custom_path=st.text_input(
                    "Custom OAuth token JSON",
                    value=configured_token_path,
                    help=_tip(
                        "Path where the authorized-user token JSON should be written or reused.",
                        "Use a custom path only when your local machine needs a different token file.",
                    ),
                    key="auth_access_custom_token_json",
                ),
            )
        else:
            resolved_client_path = resolve_path_choice(
                mode=path_mode,
                configured_path=configured_client_path,
                custom_path="",
            )
            resolved_token_path = resolve_path_choice(
                mode=path_mode,
                configured_path=configured_token_path,
                custom_path="",
            )
            _render_readonly_fields(
                [
                    {
                        "label": "Configured OAuth client JSON",
                        "value": configured_client_path or "Not configured",
                        "help": _tip(
                            "Configured OAuth desktop client JSON path used for Drive user consent.",
                            "This is the normal client file path when Drive auth mode is oauth_user.",
                        ),
                    },
                    {
                        "label": "Configured OAuth token JSON",
                        "value": configured_token_path or "Not configured",
                        "help": _tip(
                            "Configured OAuth authorized-user token path used for token reuse.",
                            "This is the normal token file path for local development.",
                        ),
                    },
                ],
                columns=2,
                key_prefix="auth_access_configured_paths",
            )
    if clicked:
        if not resolved_client_path.strip() or not resolved_token_path.strip():
            st.warning("Choose configured OAuth files or provide both custom OAuth file paths before logging in.")
        else:
            try:
                result = authorize_oauth_user(
                    DriveOAuthAuthorizeRequest(
                        schema_version="1.0",
                        client_secret_path=resolved_client_path,
                        token_output_path=resolved_token_path,
                        open_browser=True,
                        port=0,
                    ),
                    _ctx("drive_oauth_login"),
                )
                st.session_state["last_drive_oauth_result"] = result
                st.success("Drive OAuth login complete.")
            except UI_SURFACE_EXCEPTIONS as exc:
                st.error(str(exc))
    browser_settings, _, browser_error = _load_browser_defaults()
    with main_col:
        _render_guided_panel(
            "Service readiness",
            "This page shows whether the main external connections are present and where their configuration comes from, without exposing secret values.",
            tooltip=_tip(
                "Short plain-language description of the auth status page.",
                "Use this page when you want to check what is configured before running an external workflow.",
            ),
        )
        st.subheader("Presence and source status")
        _render_readonly_fields(
            [
                {
                    "label": "Drive auth mode",
                    "value": str(settings.drive_auth_mode or ""),
                    "help": _tip(
                        "Current Google Drive authentication mode loaded from configuration.",
                        "oauth_user expects local OAuth files, while service_account uses a service-account JSON file.",
                    ),
                },
                {
                    "label": "Google OAuth client",
                    "value": (
                        f"Present: {resolved_client_path}"
                        if resolved_client_path.strip() and os.path.exists(resolved_client_path.strip())
                        else f"Missing: {resolved_client_path or 'path not set'}"
                    ),
                    "help": _tip(
                        "Whether the OAuth client JSON file exists at the selected path.",
                        "This must be present before Drive OAuth login can start.",
                    ),
                },
                {
                    "label": "Google OAuth token",
                    "value": (
                        f"Present: {resolved_token_path}"
                        if resolved_token_path.strip() and os.path.exists(resolved_token_path.strip())
                        else f"Missing: {resolved_token_path or 'path not set'}"
                    ),
                    "help": _tip(
                        "Whether the OAuth token JSON file exists at the selected path.",
                        "It may be missing before the first login and present after a successful OAuth flow.",
                    ),
                },
                {
                    "label": "OpenAI API key",
                    "value": "Present in environment" if os.getenv("OPENAI_API_KEY", "").strip() else "Missing from environment",
                    "help": _tip(
                        "Whether an OpenAI API key is available to the app.",
                        "The actual secret value is never shown here.",
                    ),
                },
                {
                    "label": "OpenRouter API key",
                    "value": "Present in environment" if os.getenv("OPENROUTER_API_KEY", "").strip() else "Missing from environment",
                    "help": _tip(
                        "Whether an OpenRouter API key is available to the app.",
                        "The actual secret value is never shown here.",
                    ),
                },
                {
                    "label": "WordPress auth",
                    "value": (
                        "Present"
                        if publish_settings and getattr(publish_settings.wp, "app_password", "")
                        else "Missing"
                    ),
                    "help": _tip(
                        "Whether the WordPress publishing credentials are available to the app.",
                        "The secret itself is not displayed here.",
                    ),
                },
                {
                    "label": "Browser identity profile",
                    "value": str(getattr(browser_settings, "identity_config_path", "") or "Unavailable"),
                    "help": _tip(
                        "Path to the browser download identity profile used for gated report forms.",
                        "This file stores non-secret identity fields such as contact details and form defaults.",
                    ),
                },
            ],
            columns=2,
            key_prefix="auth_access_status",
        )
        if browser_error:
            st.warning(browser_error)
    with detail_col:
        st.subheader("Current selection")
        _render_readonly_fields(
            [
                {
                    "label": "OAuth client path for next login",
                    "value": resolved_client_path or "Not set yet",
                    "help": _tip(
                        "OAuth client JSON path that will be used for the next login action.",
                        "Review this value before launching Drive OAuth Login.",
                    ),
                },
                {
                    "label": "OAuth token path for next login",
                    "value": resolved_token_path or "Not set yet",
                    "help": _tip(
                        "OAuth token JSON path that will be used or created during the next login action.",
                        "Review this value before launching Drive OAuth Login.",
                    ),
                },
            ],
            columns=1,
            key_prefix="auth_access_selection",
        )
        st.subheader("Last OAuth result")
        oauth_result = st.session_state.get("last_drive_oauth_result")
        if oauth_result is None:
            _render_empty_state(
                "No OAuth login has run in this session",
                "Run Drive OAuth Login to store the latest local result here.",
            )
        else:
            _render_payload_area(
                "Latest OAuth result",
                oauth_result.__dict__ if hasattr(oauth_result, "__dict__") else oauth_result,
                help_text=_tip(
                    "Full structured result from the latest OAuth login in this session.",
                    "Use this when you need the raw metadata behind the most recent login flow.",
                ),
                key="auth_access_oauth_result",
                height=260,
            )
