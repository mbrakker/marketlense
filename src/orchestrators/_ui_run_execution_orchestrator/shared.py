from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

import hashlib
import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any, TypeAlias, cast

from src.contracts.acquisition_audit import AcquisitionAuditBatchRequest
from src.contracts.browser_download import ReportDownloadOrchestratorRequest
from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisOrchestratorRequest,
    CrossReportAnalysisRequest,
    CrossReportProjectedDataReadRequest,
    PublicationMode,
)
from src.contracts.cover_images import CoverImageOrchestratorRequest
from src.contracts.publisher_inventory import PublisherInventoryDiscoveryRequest
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidateExtractionRequest,
)
from src.contracts.ui_run_control import UiRunWorkerRequest
from src.contracts.ui_run_payloads import (
    PAYLOAD_SCHEMA_VERSION,
    AcquisitionAuditUiRunPayload,
    CandidateExtractionUiRunPayload,
    CoverImagesUiRunPayload,
    CrossReportAnalysisUiRunPayload,
    IngestUiRunPayload,
    PublishUiRunPayload,
    PublisherDiscoveryUiRunPayload,
    ReportDownloadUiRunPayload,
    SignalCandidateExtractionUiRunPayload,
    SignalPostUiRunPayload,
    UiRunReplayUiRunPayload,
)
from src.contracts.ui_run_replay import UiRunExecutionResponse, UiRunReplayRequest
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPostGenerationRequest,
    SignalPostWorkflowRequest,
)
from src.orchestrators.acquisition_audit_orchestrator import run_acquisition_audit
from src.orchestrators.candidate_extraction_orchestrator import run_candidate_extraction
from src.orchestrators.cover_image_orchestrator import run_cover_image_generation
from src.orchestrators.cross_report_analysis_orchestrator import (
    run_cross_report_analysis,
)
from src.orchestrators.ingest_orchestrator import run_ingest
from src.orchestrators.publish_orchestrator import run_publish
from src.orchestrators.publisher_inventory_orchestrator import (
    run_publisher_inventory_discovery,
)
from src.orchestrators.report_download_orchestrator import run_report_download
from src.orchestrators.signal_candidate_orchestrator import (
    run_signal_candidate_extraction,
)
from src.orchestrators.signal_post_orchestrator import run_signal_post_workflow
from src.services.config_service import (
    build_ingest_settings,
    load_browser_download_settings,
    load_publisher_inventory_settings,
    load_publish_settings,
    load_settings,
)
from src.services.run_registry_service import default_ui_run_registry_path
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.ui_run_execution_orchestrator")

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_TREE_ROOT = REPO_ROOT / "src"
PROMPT_TREE_ROOT = REPO_ROOT / "src" / "prompts"
SENSITIVE_KEY_TOKENS = ("api_key", "token", "password", "secret", "email")
PUBLICATION_MODES = {
    "generate_only",
    "validate_only",
    "publish_dry_run",
    "publish_live",
}
UiRunPayload: TypeAlias = (
    IngestUiRunPayload
    | CandidateExtractionUiRunPayload
    | CoverImagesUiRunPayload
    | PublishUiRunPayload
    | PublisherDiscoveryUiRunPayload
    | ReportDownloadUiRunPayload
    | AcquisitionAuditUiRunPayload
    | CrossReportAnalysisUiRunPayload
    | SignalCandidateExtractionUiRunPayload
    | SignalPostUiRunPayload
    | UiRunReplayUiRunPayload
)

__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
