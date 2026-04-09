from __future__ import annotations

from src.ui import state as ui_state
from src.ui.settings_page import render_settings_and_prompts


def render_settings_prompts() -> None:
    render_settings_and_prompts(
        ui_state.get_app_settings(),
        ui_state.get_publish_settings(),
        ui_state.get_publish_error(),
        ui_state.get_settings_error(),
    )
