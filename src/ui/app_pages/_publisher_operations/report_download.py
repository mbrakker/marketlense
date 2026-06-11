from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

from .requests import *  # noqa: F401,F403
from .shared import *  # noqa: F401,F403


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
            st.warning(
                "Pick a saved publisher page or enter a report URL before launching download."
            )
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
                    "value": str(
                        getattr(browser_settings, "identity_config_path", "")
                        or "Unavailable"
                    ),
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


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
