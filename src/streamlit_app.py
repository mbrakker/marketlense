from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Ensure `src.*` imports resolve when launched via `streamlit run src/streamlit_app.py`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.config_service import load_publish_settings, load_settings
from src.services.logging_service import setup_logging
from src.contracts.config import ConfigLoadRequest
from src.contracts.logging import LoggingSetupRequest
from src.ui.common import UI_SURFACE_EXCEPTIONS, _chip_html, _ctx, _inject_theme, _tip
from src.ui.state import initialize_ui_state
from src.ui.app_pages.configuration import render_settings_prompts
from src.ui.app_pages.content_qa import (
    render_analysis_evidence,
    render_report_command_center,
    render_validation_center,
)
from src.ui.app_pages.core_operations import (
    render_candidate_extraction,
    render_cover_images,
    render_ingest_control,
    render_publishing_and_taxonomy,
)
from src.ui.app_pages.observability import (
    render_cost_usage,
    render_developer_tools,
    render_logs_events,
    render_system_storage,
)
from src.ui.app_pages.overview import render_cockpit_overview, render_run_center
from src.ui.app_pages.publisher_operations import (
    render_acquisition_audit,
    render_auth_access,
    render_publisher_discovery,
    render_publisher_sync,
    render_report_download_lab,
)

NAVIGATION_GROUPS = {
    "Overview": ["Cockpit Overview", "Run Center"],
    "Core operations": [
        "Ingest Control",
        "Candidate Extraction",
        "Cover Images",
        "Publishing & Taxonomy",
    ],
    "Publisher operations": [
        "Publisher Discovery",
        "Report Download Lab",
        "Acquisition Audit",
        "Publisher Sync",
        "Auth & External Access",
    ],
    "Content QA": [
        "Report Command Center",
        "Analysis & Evidence",
        "Validation Center",
    ],
    "Observability": [
        "Cost & Usage",
        "Logs & Live Events",
        "System & Storage",
        "Developer & Test Tools",
    ],
    "Configuration": ["Settings & Prompts"],
}
NAV_SECTIONS = [section for sections in NAVIGATION_GROUPS.values() for section in sections]
_EXPORTED_UI_HELPERS = (_tip, _chip_html)

__all__ = [
    "NAVIGATION_GROUPS",
    "NAV_SECTIONS",
    "_tip",
    "_chip_html",
    "_inject_theme",
    "main",
    "st",
]


def _load_runtime_state() -> tuple[object | None, object | None, str | None, str | None]:
    settings = None
    publish_settings = None
    publish_error = None
    settings_error = None
    try:
        settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), _ctx("load_settings"))
    except UI_SURFACE_EXCEPTIONS as exc:
        settings_error = str(exc)
    try:
        publish_settings = load_publish_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            _ctx("load_publish_settings"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:
        publish_error = str(exc)
    return settings, publish_settings, publish_error, settings_error


def _build_navigation(valid_settings: bool):
    if not valid_settings:
        return st.navigation(
            {"Configuration": [st.Page(render_settings_prompts, title="Settings & Prompts", icon=":material/settings:")]},
            position="sidebar",
        )
    return st.navigation(
        {
            "Overview": [
                st.Page(render_cockpit_overview, title="Cockpit Overview", icon=":material/dashboard:"),
                st.Page(render_run_center, title="Run Center", icon=":material/play_circle:"),
            ],
            "Core operations": [
                st.Page(render_ingest_control, title="Ingest Control", icon=":material/file_download:"),
                st.Page(render_candidate_extraction, title="Candidate Extraction", icon=":material/table_chart:"),
                st.Page(render_cover_images, title="Cover Images", icon=":material/image:"),
                st.Page(render_publishing_and_taxonomy, title="Publishing & Taxonomy", icon=":material/publish:"),
            ],
            "Publisher operations": [
                st.Page(render_publisher_discovery, title="Publisher Discovery", icon=":material/travel_explore:"),
                st.Page(render_report_download_lab, title="Report Download Lab", icon=":material/download:"),
                st.Page(render_acquisition_audit, title="Acquisition Audit", icon=":material/assignment:"),
                st.Page(render_publisher_sync, title="Publisher Sync", icon=":material/sync:"),
                st.Page(render_auth_access, title="Auth & External Access", icon=":material/key:"),
            ],
            "Content QA": [
                st.Page(render_report_command_center, title="Report Command Center", icon=":material/article:"),
                st.Page(render_analysis_evidence, title="Analysis & Evidence", icon=":material/analytics:"),
                st.Page(render_validation_center, title="Validation Center", icon=":material/rule:"),
            ],
            "Observability": [
                st.Page(render_cost_usage, title="Cost & Usage", icon=":material/query_stats:"),
                st.Page(render_logs_events, title="Logs & Live Events", icon=":material/terminal:"),
                st.Page(render_system_storage, title="System & Storage", icon=":material/storage:"),
                st.Page(render_developer_tools, title="Developer & Test Tools", icon=":material/build:"),
            ],
            "Configuration": [
                st.Page(render_settings_prompts, title="Settings & Prompts", icon=":material/settings:"),
            ],
        },
        position="sidebar",
    )


def main() -> None:
    st.set_page_config(page_title="Market Lense Control Panel", page_icon="ML", layout="wide")
    _inject_theme()
    if not st.session_state.get("gui_logging_ready"):
        setup_logging(LoggingSetupRequest(schema_version="1.0"), _ctx("setup_logging"))
        st.session_state["gui_logging_ready"] = True
    settings, publish_settings, publish_error, settings_error = _load_runtime_state()
    initialize_ui_state(
        settings=settings,
        publish_settings=publish_settings,
        publish_error=publish_error,
        settings_error=settings_error,
    )
    page = _build_navigation(settings is not None)
    page.run()


if __name__ == "__main__":
    main()
