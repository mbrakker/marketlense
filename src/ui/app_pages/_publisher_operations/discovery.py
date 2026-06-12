from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

import streamlit as st

from src.ui import state as ui_state

from .requests import build_publisher_discovery_request_payload
from .requests import *  # noqa: F401,F403
from .shared import (
    _load_saved_publishers,
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
            st.warning(
                "Pick a saved publisher or enter an insights URL before launching discovery."
            )
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


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
