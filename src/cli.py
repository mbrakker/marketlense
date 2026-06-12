from __future__ import annotations

# ruff: noqa: F401

# Compatibility facade for the CLI. Command implementations live in src._cli.*
# so the public entrypoint remains src.cli and python -m src.cli.

import logging
import os
import json
from dataclasses import asdict
from datetime import date
from typing import Any, cast

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from src.utils.errors import AppError
from src.contracts.acquisition_audit import AcquisitionAuditBatchRequest
from src.contracts.costs import CostReportRequest, CostReportingRequest
from src.contracts.browser_download import ReportDownloadOrchestratorRequest
from src.contracts.browser_download import BrowserDeveloperDiagnosticsRequest
from src.contracts.browser_download import BrowserDownloadSessionReusePolicy
from src.contracts.browser_download import BrowserRoutePrivateApiPromotionRequest
from src.contracts.categories import RecategorizeRequest
from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisOrchestratorRequest,
    CrossReportAnalysisRequest,
    CrossReportProjectedDataReadRequest,
    PublicationMode,
)
from src.contracts.cover_images import CoverImageOrchestratorRequest
from src.contracts.drive import DriveOAuthAuthorizeRequest
from src.contracts.files import ReadTextRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.publisher_inventory import PublisherInventoryDiscoveryRequest
from src.contracts.publisher_profiles import PublisherSyncRequest
from src.contracts.semantic_ids import RunId
from src.contracts.tracing import TraceBuildRequest
from src.contracts.ui_run_control import (
    UiRunRecord,
    UiRunRecordGetRequest,
    UiRunRecordWriteRequest,
    UiRunWorkerRequest,
)
from src.contracts.ui_run_replay import (
    UiRunReplayCaptureRequest,
    UiRunReplayRequest,
)
from src.orchestrators.report_download_orchestrator import run_report_download
from src.orchestrators.acquisition_audit_orchestrator import run_acquisition_audit
from src.orchestrators.cost_reporting_orchestrator import run_cost_reporting
from src.orchestrators.ingest_orchestrator import run_ingest
from src.orchestrators.candidate_extraction_orchestrator import run_candidate_extraction
from src.orchestrators.cover_image_orchestrator import run_cover_image_generation
from src.orchestrators.cross_report_analysis_orchestrator import (
    run_cross_report_analysis as run_cross_report_analysis_orchestrator,
)
from src.orchestrators.publisher_inventory_orchestrator import (
    run_publisher_inventory_discovery,
)
from src.orchestrators.publisher_sync_orchestrator import run_publisher_sync
from src.orchestrators.publish_orchestrator import run_publish
from src.orchestrators.recategorize_orchestrator import run_recategorize
from src.orchestrators.ui_run_execution_orchestrator import (
    PROMPT_TREE_ROOT,
    SOURCE_TREE_ROOT,
    execute_ui_run,
)
from src.orchestrators.ui_run_replay_orchestrator import replay_ui_run
from src.orchestrators.wp_category_update_orchestrator import run_update_wp_categories
from src.generators.trace_generator import build_trace_summary
from src.services.config_service import (
    build_ingest_settings,
    load_browser_download_settings,
    load_publisher_inventory_settings,
    load_settings,
    load_publish_settings,
)
from src.services.browser_report_download_service import (
    default_browser_doctor_verification_url,
    promote_private_api_evidence_to_browser_playbook,
    run_browser_developer_diagnostics,
)
from src.services.drive_service import authorize_oauth_user
from src.services.file_service import read_text
from src.services.logging_service import setup_logging
from src.services.run_registry_service import (
    default_ui_run_registry_path,
    get_ui_run_record,
    write_ui_run_record,
)
from src.services.ui_run_replay_service import write_ui_run_replay_manifest
from src.utils.gui_utils import (
    extract_log_date_from_filename,
    parse_structured_log_line,
)
from src.utils.logging import child_context, log_event, new_run_context


from src._cli.app import cli_app, cli, console, logger, main
from src._cli.common import _default_log_path, _utc_now
from src._cli.cross_report import (
    _CROSS_REPORT_PUBLICATION_MODES,
    _build_cross_report_cli_request,
    _cross_report_cli_request_id,
    _cross_report_publish_mode,
    _normalize_cross_report_cli_date,
    _optional_int_cli_value,
    _split_cli_filter_values,
    generate_cross_report_analysis_cli,
)
from src._cli.private_api import (
    _int_list_payload,
    _load_private_api_promotion_request,
    _required_int_payload,
    _string_list_payload,
    promote_private_api_playbook,
)
from src._cli.trace import _load_structured_log_events, _trace_depths, trace_run
from src._cli.ui_runs import (
    _load_ui_run_worker_request,
    _update_ui_run_record,
    replay_run,
    ui_run_worker,
)
from src._cli.pipeline import (
    cost_report,
    extract_candidates,
    generate_covers,
    ingest,
    publish_wp,
    recategorize,
    update_wp_categories,
)
from src._cli.browser import browser_doctor, download_report
from src._cli.publisher import audit_acquisition_paths, discover_publisher_inventory
from src._cli.admin import drive_oauth_login, sync_publishers

if __name__ == "__main__":
    main()
