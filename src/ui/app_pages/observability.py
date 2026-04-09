from __future__ import annotations

import streamlit as st

from src.ui import streamlit_pages as legacy
from src.ui import state as ui_state


def render_cost_usage() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    legacy._render_cost_and_usage(settings)


def render_logs_events() -> None:
    legacy._render_logs_and_terminal()


def render_system_storage() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    legacy._render_system_and_storage(settings)


def render_developer_tools() -> None:
    legacy._render_developer_tools()
