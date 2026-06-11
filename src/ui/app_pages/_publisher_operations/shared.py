from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

import json
import os
from html import escape
from urllib.parse import urlsplit

import streamlit as st

from src.contracts.config import ConfigLoadRequest
from src.contracts.drive import DriveOAuthAuthorizeRequest
from src.contracts.publisher_profiles import (
    PublisherProfilesSnapshotLoadRequest,
    PublisherSyncRequest,
)
from src.contracts.ui_run_control import UiRunPollResponse
from src.generators.publisher_profiles_generator import (
    load_publisher_profiles_snapshot,
)
from src.orchestrators.publisher_sync_orchestrator import run_publisher_sync
from src.services.config_service import load_browser_download_settings
from src.services.drive_service import authorize_oauth_user
from src.ui import state as ui_state
from src.ui.common import (
    UI_SURFACE_EXCEPTIONS,
    _ctx,
    _page_shell,
    _render_empty_state,
    _tip,
)
from src.ui.run_control import launch_background_run, poll_selected_run

_AUDIT_PRESETS: dict[str, tuple[int, int]] = {
    "Quick": (3, 3),
    "Standard": (5, 10),
    "Deep": (12, 20),
}


def _selected_run_payload(
    settings: object, *, run_type: str
) -> UiRunPollResponse | None:
    from src.ui.app_pages import publisher_operations as boundary

    polled = boundary.poll_selected_run(settings, max_bytes=64000)
    if polled is None or polled.record.run_type != run_type:
        return None
    return polled


def _run_status_presentation(polled: UiRunPollResponse | None) -> tuple[str, str]:
    if polled is None:
        return "Ready", "info"
    status = str(getattr(polled.record, "status", "") or "").strip().lower()
    label = status.replace("_", " ").title() or "Ready"
    level_map = {
        "queued": "info",
        "running": "info",
        "succeeded": "success",
        "failed": "error",
        "canceled": "warn",
    }
    return label, level_map.get(status, "info")


def _format_payload(payload: object) -> str:
    if payload in (None, "", [], {}):
        return "{}"
    try:
        return json.dumps(
            payload, indent=2, sort_keys=True, ensure_ascii=True, default=str
        )
    except TypeError:
        return str(payload)


def _render_guided_panel(title: str, description: str, *, tooltip: str) -> None:
    st.markdown(
        (
            f'<div class="ml-panel" title="{escape(tooltip)}">'
            f"<h4>{escape(title)}</h4>"
            f"<p>{escape(description)}</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_readonly_fields(
    fields: list[dict[str, str]],
    *,
    columns: int,
    key_prefix: str,
) -> None:
    if not fields:
        return
    safe_columns = max(1, int(columns))
    for row_start in range(0, len(fields), safe_columns):
        chunk = fields[row_start : row_start + safe_columns]
        row_columns = st.columns(len(chunk), gap="large")
        for index, field in enumerate(chunk):
            with row_columns[index]:
                st.text_input(
                    field["label"],
                    value=field["value"],
                    disabled=True,
                    help=field["help"],
                    key=f"{key_prefix}_{row_start}_{index}",
                )


def _render_payload_area(
    label: str,
    payload: object,
    *,
    help_text: str,
    key: str,
    height: int = 220,
) -> None:
    st.text_area(
        label,
        value=_format_payload(payload),
        disabled=True,
        height=height,
        help=help_text,
        key=key,
    )


def _render_run_summary(
    polled: UiRunPollResponse | None,
    *,
    key_prefix: str,
    empty_title: str,
    empty_detail: str,
    summary_label: str,
) -> None:
    if polled is None:
        _render_empty_state(empty_title, empty_detail)
        return
    record = polled.record
    _render_readonly_fields(
        [
            {
                "label": "Run status",
                "value": str(getattr(record, "status", "") or "")
                .replace("_", " ")
                .title(),
                "help": _tip(
                    "Current lifecycle state for the selected background job.",
                    "Succeeded means the worker finished without an error.",
                ),
            },
            {
                "label": "Artifacts saved",
                "value": f"{len(getattr(record, 'artifact_paths', []) or [])} file(s)",
                "help": _tip(
                    "How many output files this run has registered so far.",
                    "Use this count to confirm whether the run produced saved artifacts.",
                ),
            },
        ],
        columns=2,
        key_prefix=f"{key_prefix}_summary_fields",
    )
    _render_payload_area(
        summary_label,
        getattr(record, "result_summary", {}) or {},
        help_text=_tip(
            "Structured summary returned by the workflow after it completed or progressed.",
            "This is the quickest place to inspect the latest result without opening raw logs.",
        ),
        key=f"{key_prefix}_summary_payload",
        height=260,
    )


def _render_run_details(
    polled: UiRunPollResponse | None,
    *,
    key_prefix: str,
    empty_title: str,
    empty_detail: str,
) -> None:
    if polled is None:
        _render_empty_state(empty_title, empty_detail)
        return
    record = polled.record
    _render_readonly_fields(
        [
            {
                "label": "Run ID",
                "value": str(getattr(record, "run_id", "") or ""),
                "help": _tip(
                    "Stable identifier for the selected background run.",
                    "Use this ID when matching the page state with Run Center.",
                ),
            },
            {
                "label": "Workflow",
                "value": str(
                    getattr(record, "display_name", "")
                    or getattr(record, "run_type", "")
                    or ""
                ),
                "help": _tip(
                    "Human-readable workflow name for the selected run.",
                    "This tells you which background tool produced the results shown here.",
                ),
            },
            {
                "label": "Started at",
                "value": str(getattr(record, "started_at_utc", "") or ""),
                "help": _tip(
                    "UTC timestamp when the background worker started execution.",
                    "If this is blank, the run is still queued.",
                ),
            },
            {
                "label": "Finished at",
                "value": str(getattr(record, "finished_at_utc", "") or ""),
                "help": _tip(
                    "UTC timestamp when the background worker finished.",
                    "Blank means the run is still active or has not written a terminal state yet.",
                ),
            },
        ],
        columns=1,
        key_prefix=f"{key_prefix}_detail_fields",
    )
    artifact_paths = getattr(record, "artifact_paths", []) or []
    if artifact_paths:
        _render_payload_area(
            "Saved file paths",
            artifact_paths,
            help_text=_tip(
                "Exact files registered by the run as saved artifacts.",
                "Open these paths when you want the generated evidence or exports.",
            ),
            key=f"{key_prefix}_artifact_paths",
            height=150,
        )
    output_chunk = getattr(polled, "output_chunk", None)
    if output_chunk is not None:
        st.text_area(
            "Latest worker output",
            value=str(getattr(output_chunk, "text", "") or "[worker] no output yet"),
            disabled=True,
            height=180,
            help=_tip(
                "Latest captured console output from the background worker.",
                "Use this to understand what the worker is doing right now.",
            ),
            key=f"{key_prefix}_worker_output",
        )
    _render_payload_area(
        "Technical details",
        record.__dict__,
        help_text=_tip(
            "Raw run metadata stored in the run registry.",
            "Use this if you need the full structured record behind the current page state.",
        ),
        key=f"{key_prefix}_technical_details",
        height=220,
    )


def _load_saved_publishers(settings: object) -> tuple[list[dict[str, str]], str | None]:
    from .requests import build_publisher_choice_options

    try:
        response = load_publisher_profiles_snapshot(
            PublisherProfilesSnapshotLoadRequest(
                schema_version="1.0",
                snapshot_path=str(
                    getattr(settings, "publisher_profiles_path", "") or ""
                ),
            ),
            _ctx("publisher_profiles_snapshot"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:
        return [], str(exc)
    return build_publisher_choice_options(list(response.publishers)), None


def _load_browser_defaults() -> tuple[object | None, list[str], str | None]:
    from .requests import build_saved_delivery_email_options

    try:
        browser_settings = load_browser_download_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            _ctx("browser_download_settings"),
        )
    except UI_SURFACE_EXCEPTIONS as exc:
        return None, [], str(exc)
    return browser_settings, build_saved_delivery_email_options(browser_settings), None


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
