from __future__ import annotations

import streamlit as st

from src.ui import streamlit_pages as legacy
from src.ui import state as ui_state


def render_report_command_center() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    legacy._render_report_command_center(settings)


def render_analysis_evidence() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    legacy._render_analysis_and_evidence(settings)


def render_validation_center() -> None:
    settings = ui_state.get_app_settings()
    publish_settings = ui_state.get_publish_settings()
    publish_error = ui_state.get_publish_error()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    legacy._render_validation_center(settings, publish_settings, publish_error)
