from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from src.services.run_registry_service import default_ui_run_registry_path

APP_SETTINGS_KEY = "ml_app_settings"
PUBLISH_SETTINGS_KEY = "ml_publish_settings"
PUBLISH_ERROR_KEY = "ml_publish_error"
SETTINGS_ERROR_KEY = "ml_settings_error"
SELECTED_RUN_ID_KEY = "ml_selected_run_id"
SELECTED_REPORT_ID_KEY = "ml_selected_report_id"
LIVE_TERMINAL_OUTPUT_KEY = "live_terminal_output"


def initialize_ui_state(
    *,
    settings: Any | None,
    publish_settings: Any | None,
    publish_error: str | None,
    settings_error: str | None,
) -> None:
    st.session_state[APP_SETTINGS_KEY] = settings
    st.session_state[PUBLISH_SETTINGS_KEY] = publish_settings
    st.session_state[PUBLISH_ERROR_KEY] = publish_error
    st.session_state[SETTINGS_ERROR_KEY] = settings_error
    st.session_state.setdefault(SELECTED_RUN_ID_KEY, "")
    st.session_state.setdefault(SELECTED_REPORT_ID_KEY, "")
    st.session_state.setdefault(LIVE_TERMINAL_OUTPUT_KEY, "")


def get_app_settings() -> Any | None:
    return st.session_state.get(APP_SETTINGS_KEY)


def get_publish_settings() -> Any | None:
    return st.session_state.get(PUBLISH_SETTINGS_KEY)


def get_publish_error() -> str | None:
    value = st.session_state.get(PUBLISH_ERROR_KEY)
    return str(value) if value else None


def get_settings_error() -> str | None:
    value = st.session_state.get(SETTINGS_ERROR_KEY)
    return str(value) if value else None


def get_selected_run_id() -> str:
    return str(st.session_state.get(SELECTED_RUN_ID_KEY) or "").strip()


def set_selected_run_id(run_id: str) -> None:
    st.session_state[SELECTED_RUN_ID_KEY] = str(run_id or "").strip()


def get_selected_report_id() -> str:
    return str(st.session_state.get(SELECTED_REPORT_ID_KEY) or "").strip()


def set_selected_report_id(report_id: str) -> None:
    st.session_state[SELECTED_REPORT_ID_KEY] = str(report_id or "").strip()


def get_ui_run_registry_path(settings: Any | None) -> str:
    if settings is None:
        return str((Path.cwd() / "state" / "ui_runs.sqlite").resolve())
    return default_ui_run_registry_path(str(settings.state_db))
