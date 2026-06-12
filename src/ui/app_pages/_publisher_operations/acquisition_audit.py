from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

import streamlit as st

from src.ui import state as ui_state

from .requests import (
    build_acquisition_audit_request_payload,
    resolve_audit_limits,
    resolve_delivery_email_value,
)
from .requests import *  # noqa: F401,F403
from .shared import (
    _AUDIT_PRESETS,
    _load_browser_defaults,
    _page_shell,
    _render_guided_panel,
    _render_readonly_fields,
    _render_run_details,
    _render_run_summary,
    _run_status_presentation,
    _selected_run_payload,
    _tip,
    launch_background_run,
)
from .shared import *  # noqa: F401,F403


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
                    "value": str(
                        getattr(browser_settings, "identity_config_path", "")
                        or "Unavailable"
                    ),
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


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
