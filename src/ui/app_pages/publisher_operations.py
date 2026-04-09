from __future__ import annotations

import os

import streamlit as st

from src.contracts.drive import DriveOAuthAuthorizeRequest
from src.contracts.publisher_profiles import PublisherSyncRequest
from src.services.config_service import load_browser_download_settings
from src.services.drive_service import authorize_oauth_user
from src.orchestrators.publisher_sync_orchestrator import run_publisher_sync
from src.contracts.config import ConfigLoadRequest
from src.ui import state as ui_state
from src.ui.common import UI_SURFACE_EXCEPTIONS, _ctx, _page_shell, _tip
from src.ui.run_control import launch_background_run, poll_selected_run


def _selected_run_payload(settings: object, *, run_type: str):
    polled = poll_selected_run(settings, max_bytes=64000)
    if polled is None or polled.record.run_type != run_type:
        return None
    return polled


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


def render_publisher_discovery() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    clicked, filters, main_col, detail_col = _page_shell(
        "Publisher Discovery",
        status_label="Ready",
        status_level="info",
        primary_action="Run Discovery",
        primary_help=_tip(
            "Launch publisher inventory discovery as a tracked background job.",
            "Paste one insights URL to audit route quality and diff results.",
        ),
        primary_key="run_publisher_discovery",
    )
    with filters:
        insights_url = st.text_input(
            "Insights URL",
            value="",
            help=_tip(
                "Absolute publisher insights or reports URL to discover against.",
                "Example: https://example.com/insights",
            ),
        )
    if clicked:
        if not insights_url.strip():
            st.warning("Insights URL is required.")
        else:
            response = launch_background_run(
                settings,
                run_type="publisher_discovery",
                display_name="Publisher discovery",
                request_payload=build_publisher_discovery_request_payload(
                    insights_url=insights_url
                ),
            )
            st.success(f"Discovery launched: {response.record.run_id}")
    polled = _selected_run_payload(settings, run_type="publisher_discovery")
    with main_col:
        st.subheader("Workflow")
        st.caption("Runs publisher inventory discovery through the existing orchestrator and persists status in the run registry.")
        if polled is not None:
            st.subheader("Latest selected run summary")
            st.json(polled.record.result_summary)
    with detail_col:
        st.subheader("Selected run")
        if polled is None:
            st.caption("Launch or select a publisher discovery run from Run Center.")
        else:
            st.json(polled.record.__dict__)
            if polled.record.artifact_paths:
                st.dataframe(
                    [{"path": path} for path in polled.record.artifact_paths],
                    use_container_width=True,
                    hide_index=True,
                )
            if polled.output_chunk is not None:
                st.code(polled.output_chunk.text or "[worker] no output yet")


def render_report_download_lab() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    clicked, filters, main_col, detail_col = _page_shell(
        "Report Download Lab",
        status_label="Ready",
        status_level="info",
        primary_action="Run Download",
        primary_help=_tip(
            "Launch report acquisition as a tracked background job.",
            "Provide a report landing page and optional delivery email for gated flows.",
        ),
        primary_key="run_report_download_lab",
    )
    with filters:
        left, right = st.columns(2)
        with left:
            url = st.text_input(
                "Report URL",
                value="",
                help=_tip(
                    "Absolute report landing page URL to acquire.",
                    "Example: https://example.com/report",
                ),
            )
        with right:
            delivery_email = st.text_input(
                "Delivery email (optional)",
                value="",
                help=_tip(
                    "Optional email address to use when the report is gated behind an email form.",
                    "Leave blank for open PDF or on-site routes.",
                ),
            )
    if clicked:
        if not url.strip():
            st.warning("Report URL is required.")
        else:
            response = launch_background_run(
                settings,
                run_type="report_download",
                display_name="Report download",
                request_payload=build_report_download_request_payload(
                    url=url,
                    delivery_email=delivery_email,
                ),
            )
            st.success(f"Report download launched: {response.record.run_id}")
    polled = _selected_run_payload(settings, run_type="report_download")
    with main_col:
        st.subheader("Route inspector")
        if polled is None:
            st.caption("Launch or select a report download run from Run Center.")
        else:
            st.json(polled.record.result_summary)
    with detail_col:
        st.subheader("Selected run")
        if polled is not None:
            st.json(polled.record.__dict__)
            if polled.record.artifact_paths:
                st.dataframe(
                    [{"path": path} for path in polled.record.artifact_paths],
                    use_container_width=True,
                    hide_index=True,
                )
            if polled.output_chunk is not None:
                st.code(polled.output_chunk.text or "[worker] no output yet")


def render_acquisition_audit() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    clicked, filters, main_col, detail_col = _page_shell(
        "Acquisition Audit",
        status_label="Ready",
        status_level="info",
        primary_action="Run Audit",
        primary_help=_tip(
            "Launch acquisition-path auditing as a tracked background job.",
            "Use bounded publisher and candidate limits for controlled audits.",
        ),
        primary_key="run_acquisition_audit",
    )
    with filters:
        left, mid, right = st.columns(3)
        with left:
            publisher_limit = st.number_input(
                "Publisher limit",
                min_value=1,
                max_value=500,
                value=5,
                step=1,
                help=_tip(
                    "Maximum number of publishers to audit.",
                    "Start with 5 for a bounded audit run.",
                ),
            )
        with mid:
            candidate_limit = st.number_input(
                "Candidate limit per publisher",
                min_value=1,
                max_value=100,
                value=10,
                step=1,
                help=_tip(
                    "Maximum number of candidates to audit per publisher.",
                    "Use 3 during route-debugging sessions.",
                ),
            )
        with right:
            delivery_email = st.text_input(
                "Delivery email (optional)",
                value="",
                help=_tip(
                    "Optional delivery email used when acquisition reaches an email-gated route.",
                    "Leave blank for download-only audits.",
                ),
            )
    if clicked:
        response = launch_background_run(
            settings,
            run_type="acquisition_audit",
            display_name="Acquisition audit",
            request_payload=build_acquisition_audit_request_payload(
                publisher_limit=int(publisher_limit),
                candidate_limit_per_publisher=int(candidate_limit),
                delivery_email=delivery_email,
            ),
        )
        st.success(f"Acquisition audit launched: {response.record.run_id}")
    polled = _selected_run_payload(settings, run_type="acquisition_audit")
    with main_col:
        st.subheader("Audit summary")
        if polled is None:
            st.caption("Launch or select an acquisition audit run from Run Center.")
        else:
            st.json(polled.record.result_summary)
    with detail_col:
        st.subheader("Selected run")
        if polled is not None:
            st.json(polled.record.__dict__)
            if polled.record.artifact_paths:
                st.dataframe(
                    [{"path": path} for path in polled.record.artifact_paths],
                    use_container_width=True,
                    hide_index=True,
                )
            if polled.output_chunk is not None:
                st.code(polled.output_chunk.text or "[worker] no output yet")


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
            "Use after updating the Notion-derived publisher snapshot file.",
        ),
        primary_key="run_publisher_sync",
    )
    with filters:
        snapshot_path = st.text_input(
            "Snapshot path override",
            value=settings.publisher_profiles_path,
            help=_tip(
                "Optional snapshot JSON override used for sync.",
                "Leave the default checked-in snapshot path for the normal sync flow.",
            ),
        )
    if clicked:
        try:
            result = run_publisher_sync(
                PublisherSyncRequest(
                    schema_version="1.0",
                    snapshot_path=snapshot_path.strip(),
                    reports_db=settings.reports_db,
                ),
                _ctx("publisher_sync"),
            )
            st.session_state["last_publisher_sync_result"] = result
            st.success(f"Publisher sync complete: {result.replaced_count} rows replaced.")
        except UI_SURFACE_EXCEPTIONS as exc:
            st.error(str(exc))
    result = st.session_state.get("last_publisher_sync_result")
    with main_col:
        st.subheader("Sync result")
        if result is None:
            st.caption("No publisher sync executed in this session.")
        else:
            st.json(result.__dict__ if hasattr(result, "__dict__") else result)
    with detail_col:
        st.subheader("Inputs")
        st.code(f"snapshot={snapshot_path}\nreports_db={settings.reports_db}")


def render_auth_access() -> None:
    settings = ui_state.get_app_settings()
    publish_settings = ui_state.get_publish_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    clicked, filters, main_col, detail_col = _page_shell(
        "Auth & External Access",
        status_label="Status",
        status_level="info",
        primary_action="Drive OAuth Login",
        primary_help=_tip(
            "Run the interactive Drive OAuth user-consent flow.",
            "Use when drive auth mode is oauth_user and the token file is missing or expired.",
        ),
        primary_key="run_drive_oauth_login",
    )
    with filters:
        left, right = st.columns(2)
        with left:
            client_json = st.text_input(
                "OAuth client JSON",
                value=str(settings.google_oauth_client_path or ""),
                help=_tip(
                    "OAuth desktop client JSON used for Drive user consent.",
                    "This should point at google_oauth_client.json when using oauth_user mode.",
                ),
            )
        with right:
            token_json = st.text_input(
                "OAuth token JSON",
                value=str(settings.google_oauth_token_path or ""),
                help=_tip(
                    "OAuth token output file used for Drive user auth reuse.",
                    "This should point at google_oauth_token.json for local development.",
                ),
            )
    if clicked:
        try:
            result = authorize_oauth_user(
                DriveOAuthAuthorizeRequest(
                    schema_version="1.0",
                    client_secret_path=client_json.strip(),
                    token_output_path=token_json.strip(),
                    open_browser=True,
                    port=0,
                ),
                _ctx("drive_oauth_login"),
            )
            st.session_state["last_drive_oauth_result"] = result
            st.success("Drive OAuth login complete.")
        except UI_SURFACE_EXCEPTIONS as exc:
            st.error(str(exc))
    browser_settings = None
    browser_error = None
    try:
        browser_settings = load_browser_download_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            _ctx("browser_download_settings"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:
        browser_error = str(exc)
    with main_col:
        st.subheader("Presence and source status")
        rows = [
            {
                "name": "Drive auth mode",
                "status": settings.drive_auth_mode,
                "path": "",
            },
            {
                "name": "Google OAuth client",
                "status": "present" if client_json.strip() and os.path.exists(client_json.strip()) else "missing",
                "path": client_json.strip(),
            },
            {
                "name": "Google OAuth token",
                "status": "present" if token_json.strip() and os.path.exists(token_json.strip()) else "missing",
                "path": token_json.strip(),
            },
            {
                "name": "OPENAI_API_KEY",
                "status": "present" if os.getenv("OPENAI_API_KEY", "").strip() else "missing",
                "path": "env",
            },
            {
                "name": "OPENROUTER_API_KEY",
                "status": "present" if os.getenv("OPENROUTER_API_KEY", "").strip() else "missing",
                "path": "env",
            },
            {
                "name": "WP app password",
                "status": "present" if publish_settings and publish_settings.wp.app_password else "missing",
                "path": "env/config-service",
            },
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        if browser_settings is not None:
            st.subheader("Browser download identity")
            st.code(browser_settings.identity_config_path)
        elif browser_error:
            st.warning(browser_error)
    with detail_col:
        st.subheader("Last OAuth result")
        oauth_result = st.session_state.get("last_drive_oauth_result")
        if oauth_result is None:
            st.caption("No OAuth login run in this session.")
        else:
            st.json(oauth_result.__dict__ if hasattr(oauth_result, "__dict__") else oauth_result)
