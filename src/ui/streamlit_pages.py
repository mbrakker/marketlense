"""Compatibility facade for Streamlit page helpers and legacy imports.

Workflow-owned page implementations now live in `src.ui.app_pages`, while shared
read-model/runtime helpers live under `src.ui._streamlit_pages`. This module
keeps older imports stable.
"""

from __future__ import annotations

import streamlit as st

from src.ui._streamlit_pages.read_models import (
    _DASHBOARD_CACHE_INVALIDATION_REASON_KEY,
    _DASHBOARD_READ_MODEL_CACHE_KEY,
    CANDIDATE_STEPS,
    INGEST_STEPS,
    _discover_log_files,
    _invalidate_dashboard_read_models,
    _load_dashboard_read_model,
    _load_directory_count_rows,
    _load_ledger_entries,
    _load_log_events,
    _load_ops_dashboard_snapshot,
    _load_processed_rows,
    _load_published_rows,
    _load_report_rows,
    _lock_snapshot,
    _read_json,
    _recent_validation_files,
    _selected_report_index,
    _selected_ui_run,
)
from src.ui._streamlit_pages.runtime import (
    _try_load_publish_settings,
    _try_load_settings,
    _try_read_app_config,
    _try_write_app_config,
)
from src.ui._streamlit_pages.structured_config import (
    _render_structured_config_form_legacy,
)
from src.ui._streamlit_pages.structured_config import (
    render_structured_config_form as _render_structured_config_form,
)
from src.ui.app_pages.content_qa import (
    render_analysis_evidence as _render_analysis_and_evidence,
)
from src.ui.app_pages.content_qa import (
    render_report_command_center as _render_report_command_center,
)
from src.ui.app_pages.content_qa import (
    render_validation_center as _render_validation_center,
)
from src.ui.app_pages.core_operations import (
    _render_category_manager,
    _render_publishing_control,
)
from src.ui.app_pages.core_operations import (
    render_candidate_extraction as _render_candidate_extraction,
)
from src.ui.app_pages.core_operations import (
    render_cover_images as _render_cover_images,
)
from src.ui.app_pages.core_operations import (
    render_ingest_control as _render_ingest_control,
)
from src.ui.app_pages.observability import (
    render_cost_usage as _render_cost_and_usage,
)
from src.ui.app_pages.observability import (
    render_developer_tools as _render_developer_tools,
)
from src.ui.app_pages.observability import (
    render_logs_events as _render_logs_and_terminal,
)
from src.ui.app_pages.observability import (
    render_system_storage as _render_system_and_storage,
)
from src.ui.app_pages.overview import (
    render_cockpit_overview as _render_cockpit_overview,
)
from src.ui.app_pages.overview import (
    render_run_center as _render_run_center,
)
from src.ui.app_pages.strategy_outputs import (
    render_strategy_outputs as _render_strategy_outputs,
)
from src.ui.common import (
    UI_SURFACE_EXCEPTIONS,
    _append_terminal,
    _as_utc,
    _chip_html,
    _ctx,
    _inject_theme,
    _page_shell,
    _render_empty_state,
    _render_stepper,
    _render_terminal_panel,
    _tip,
)
from src.ui.settings_page import (
    render_settings_and_prompts as _render_settings_and_prompts,
)

__all__ = [
    "st",
    "UI_SURFACE_EXCEPTIONS",
    "_append_terminal",
    "_as_utc",
    "_chip_html",
    "_ctx",
    "_inject_theme",
    "_page_shell",
    "_render_empty_state",
    "_render_stepper",
    "_render_terminal_panel",
    "_tip",
    "_DASHBOARD_CACHE_INVALIDATION_REASON_KEY",
    "_DASHBOARD_READ_MODEL_CACHE_KEY",
    "CANDIDATE_STEPS",
    "INGEST_STEPS",
    "_discover_log_files",
    "_invalidate_dashboard_read_models",
    "_load_dashboard_read_model",
    "_load_directory_count_rows",
    "_load_ledger_entries",
    "_load_log_events",
    "_load_ops_dashboard_snapshot",
    "_load_processed_rows",
    "_load_published_rows",
    "_load_report_rows",
    "_lock_snapshot",
    "_read_json",
    "_recent_validation_files",
    "_selected_report_index",
    "_selected_ui_run",
    "_try_load_publish_settings",
    "_try_load_settings",
    "_try_read_app_config",
    "_try_write_app_config",
    "_render_analysis_and_evidence",
    "_render_candidate_extraction",
    "_render_category_manager",
    "_render_cockpit_overview",
    "_render_cost_and_usage",
    "_render_cover_images",
    "_render_developer_tools",
    "_render_ingest_control",
    "_render_logs_and_terminal",
    "_render_publishing_control",
    "_render_report_command_center",
    "_render_run_center",
    "_render_settings_and_prompts",
    "_render_strategy_outputs",
    "_render_structured_config_form",
    "_render_structured_config_form_legacy",
    "_render_system_and_storage",
    "_render_validation_center",
    "main",
]


def main() -> None:
    from src import streamlit_app

    streamlit_app.main()


if __name__ == "__main__":
    main()
