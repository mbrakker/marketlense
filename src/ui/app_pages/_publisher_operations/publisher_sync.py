from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

import streamlit as st

from src.contracts.publisher_profiles import PublisherSyncRequest
from src.orchestrators.publisher_sync_orchestrator import run_publisher_sync
from src.ui import state as ui_state
from src.ui.common import UI_SURFACE_EXCEPTIONS, _ctx

from .requests import resolve_path_choice
from .requests import *  # noqa: F401,F403
from .shared import (
    _page_shell,
    _render_empty_state,
    _render_guided_panel,
    _render_payload_area,
    _render_readonly_fields,
    _tip,
)
from .shared import *  # noqa: F401,F403


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
            "Use the configured snapshot unless you have a one-off replacement file for this session.",
        ),
        primary_key="run_publisher_sync",
    )
    with filters:
        _render_guided_panel(
            "Choose which snapshot to sync",
            "Most operators should use the configured snapshot path. Switch to a custom path only when you intentionally want to sync a different JSON file.",
            tooltip=_tip(
                "Guided setup for publisher sync.",
                "The configured path is the safest default because it follows the project's normal snapshot source.",
            ),
        )
        path_mode = st.segmented_control(
            "Snapshot source",
            options=["Configured path", "Custom path"],
            default="Configured path",
            help=_tip(
                "Choose whether to use the configured snapshot file or type a one-off override.",
                "Use the configured path for normal operations.",
            ),
            key="publisher_sync_path_mode",
        )
        snapshot_path = resolve_path_choice(
            mode=path_mode,
            configured_path=str(settings.publisher_profiles_path or ""),
            custom_path="",
        )
        if path_mode == "Custom path":
            snapshot_path = resolve_path_choice(
                mode=path_mode,
                configured_path=str(settings.publisher_profiles_path or ""),
                custom_path=st.text_input(
                    "Custom snapshot path",
                    value=str(settings.publisher_profiles_path or ""),
                    help=_tip(
                        "Optional snapshot JSON override used for this sync only.",
                        "Use a full path to a publisher snapshot JSON file when you need a one-off sync source.",
                    ),
                    key="publisher_sync_custom_path",
                ),
            )
        else:
            st.text_input(
                "Configured snapshot path",
                value=str(settings.publisher_profiles_path or ""),
                disabled=True,
                help=_tip(
                    "Default publisher snapshot file used by the project.",
                    "This is the normal path regular operators should keep for sync.",
                ),
                key="publisher_sync_configured_path",
            )
        st.text_input(
            "Target database",
            value=str(settings.reports_db or ""),
            disabled=True,
            help=_tip(
                "Reports SQLite database that will receive the synchronized publisher rows.",
                "This is the destination for the sync action.",
            ),
            key="publisher_sync_reports_db",
        )
    if clicked:
        if not snapshot_path.strip():
            st.warning(
                "Choose a configured snapshot or enter a custom snapshot path before syncing."
            )
        else:
            try:
                result = run_publisher_sync(
                    PublisherSyncRequest(
                        schema_version="1.0",
                        snapshot_path=snapshot_path.strip(),
                        reports_db=settings.reports_db,
                    ),
                    ctx=_ctx("publisher_sync"),
                )
                st.session_state["last_publisher_sync_result"] = result
                st.success(
                    f"Publisher sync complete: {result.replaced_count} rows replaced."
                )
            except UI_SURFACE_EXCEPTIONS as exc:
                st.error(str(exc))
    result = st.session_state.get("last_publisher_sync_result")
    with main_col:
        _render_guided_panel(
            "What this action does",
            "The sync reads the publisher snapshot JSON and replaces the publisher rows stored in the reports database.",
            tooltip=_tip(
                "Short plain-language description of publisher sync.",
                "Use this after the snapshot file has been refreshed and you want the database to match it.",
            ),
        )
        st.subheader("Latest sync result")
        if result is None:
            _render_empty_state(
                "No publisher sync has run in this session",
                "Run sync to see how many publisher rows were replaced and which snapshot file was used.",
            )
        else:
            _render_readonly_fields(
                [
                    {
                        "label": "Rows replaced",
                        "value": str(getattr(result, "replaced_count", "") or ""),
                        "help": _tip(
                            "How many publisher rows were written into the reports database by the latest sync.",
                            "A non-zero count means the database was refreshed from the snapshot.",
                        ),
                    },
                    {
                        "label": "Source page",
                        "value": str(getattr(result, "source_page_url", "") or ""),
                        "help": _tip(
                            "Original Notion source page recorded in the synchronized snapshot.",
                            "This helps confirm where the synced publisher data came from.",
                        ),
                    },
                ],
                columns=2,
                key_prefix="publisher_sync_result_fields",
            )
            _render_payload_area(
                "Sync details",
                result.__dict__ if hasattr(result, "__dict__") else result,
                help_text=_tip(
                    "Full structured result from the latest publisher sync in this session.",
                    "Use this if you need the raw metadata behind the sync action.",
                ),
                key="publisher_sync_result_payload",
                height=220,
            )
    with detail_col:
        st.subheader("Current selection")
        _render_readonly_fields(
            [
                {
                    "label": "Snapshot path for next sync",
                    "value": snapshot_path or "Not set yet",
                    "help": _tip(
                        "Snapshot JSON file that will be used for the next sync action.",
                        "Review this before launching sync, especially when using a custom path.",
                    ),
                },
                {
                    "label": "Reports database",
                    "value": str(settings.reports_db or ""),
                    "help": _tip(
                        "Database file that will receive the synchronized publisher rows.",
                        "This is the destination for the next sync action.",
                    ),
                },
            ],
            columns=1,
            key_prefix="publisher_sync_selection",
        )


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
