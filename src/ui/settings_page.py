from __future__ import annotations

from typing import Any


def render_structured_config_form(
    config_payload: dict[str, Any], *, editor_key: str
) -> None:
    from src.ui import streamlit_pages as pages

    pages._render_structured_config_form_legacy(
        config_payload=config_payload,
        editor_key=editor_key,
    )


def render_settings_and_prompts(
    settings: Any | None,
    publish_settings: Any | None,
    publish_error: str | None,
    settings_error: str | None = None,
) -> None:
    from src.ui import streamlit_pages as pages

    pages._render_settings_and_prompts_legacy(
        settings=settings,
        publish_settings=publish_settings,
        publish_error=publish_error,
        settings_error=settings_error,
    )
