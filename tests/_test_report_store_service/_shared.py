# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_report_store_service.py"
)

import os

import pytest

import sqlite3

import tempfile

import time

import unittest

from dataclasses import replace

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadNetworkEvent,
    BrowserDownloadRouteStep,
    DownloadTerminalEvidence,
)

from src.contracts.report_store import (
    PublisherInventoryRecoveryCacheGetRequest,
    PublisherInventoryRecoveryCacheRecordRequest,
    PublishersListRequest,
    PublisherDownloadRouteGetRequest,
    PublisherDownloadRouteRecordRequest,
    PublisherInventoryRunQualityRecordRequest,
    PublisherInventoryStateGetRequest,
    PublisherInventoryStateRecordRequest,
    PublisherInventoryTestStatusRecordRequest,
    PublisherGoogleFolderUpdateRequest,
    PublishersReplaceRequest,
    ReportDownloadDriveFolderLookupRequest,
    ReportMetadataDbAccessRequest,
    ReportSourceDiscoveryRecordRequest,
    ReportSourceIdentityResolveRequest,
    ReportSourceLinkRequest,
    ReportSourceQualityHistoryRequest,
    ReportMetadataGetRequest,
    ReportSourceRecordRequest,
    ReportValueScoreComponent,
    ReportValueScoreRecordRequest,
    ReportValueScoreResponse,
    ReportMetadataUpsertRequest,
)

from src.contracts.publisher_inventory import (
    PublisherInventoryRecoveryRecord,
    PublisherInventoryRouteTrace,
    PublisherInventoryRunQualitySummary,
    PublisherInventoryScenarioSummary,
)

from src.contracts.publisher_profiles import PublisherProfileRecord

from src.services.report_store_service import (
    check_report_db_access,
    get_report_download_drive_folder,
    get_metadata,
    get_publisher_inventory_recovery_cache_record,
    list_report_source_quality_history,
    record_discovered_report_source,
    resolve_report_source_identity,
    link_report_to_source,
    record_report_value_score,
    get_publisher_download_route,
    get_publisher_inventory_state,
    list_publishers,
    record_publisher_inventory_recovery_cache_record,
    record_publisher_inventory_run_quality,
    record_publisher_inventory_test_status,
    record_report_source,
    record_publisher_download_route,
    record_publisher_inventory_state,
    replace_publishers,
    update_publisher_google_folder,
    upsert_metadata,
)

from src.utils.errors import AppError

from src.utils.logging import new_run_context

if __name__ == "__main__":
    unittest.main()


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
        "_SplitPath",
    }
]
