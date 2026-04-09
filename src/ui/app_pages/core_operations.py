from __future__ import annotations

import streamlit as st

from src.ui import streamlit_pages as legacy
from src.ui import state as ui_state


def render_ingest_control() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    legacy._render_ingest_control(settings)


def render_candidate_extraction() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    legacy._render_candidate_extraction(settings)


def render_cover_images() -> None:
    settings = ui_state.get_app_settings()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    legacy._render_cover_images(settings)


def render_publishing_and_taxonomy() -> None:
    settings = ui_state.get_app_settings()
    publish_settings = ui_state.get_publish_settings()
    publish_error = ui_state.get_publish_error()
    if settings is None:
        st.error(ui_state.get_settings_error() or "App settings unavailable.")
        return
    mode = st.segmented_control(
        "Mode",
        options=["Publishing", "Taxonomy"],
        default="Publishing",
        help=legacy._tip(
            "Switch between WordPress publishing controls and taxonomy management.",
            "Use 'Taxonomy' after category mapping changes, then switch back to 'Publishing'.",
        ),
    )
    if mode == "Publishing":
        legacy._render_publishing_control(settings, publish_settings, publish_error)
    else:
        legacy._render_category_manager(settings, publish_settings)
