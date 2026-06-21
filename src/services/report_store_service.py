from __future__ import annotations

"""Canonical report-store service boundary.

The public report-store API stays singular here, while semantic families live in
`src.services._report_store_service`.
"""

from src.services._report_store_service.download_routes import (
    get_publisher_download_route,
    mark_publisher_private_api_candidate_promoted,
    record_publisher_private_api_candidate_observation,
    record_publisher_download_route,
)
from src.services._report_store_service.inventory import (
    get_publisher_inventory_recovery_cache_record,
    get_publisher_inventory_state,
    record_publisher_inventory_recovery_cache_record,
    record_publisher_inventory_run_quality,
    record_publisher_inventory_state,
    record_publisher_inventory_test_status,
)
from src.services._report_store_service.metadata import (
    check_report_db_access,
    get_metadata,
    list_metadata,
    upsert_metadata,
)
from src.services._report_store_service.publishers import (
    list_publishers,
    replace_publishers,
    update_publisher_google_folder,
)
from src.services._report_store_service.sources import (
    get_report_download_drive_folder,
    list_report_source_quality_history,
    list_public_publisher_report_value_aggregates,
    record_discovered_report_source,
    record_report_value_score,
    record_report_source,
)

__all__ = [
    "check_report_db_access",
    "get_metadata",
    "get_publisher_download_route",
    "get_publisher_inventory_recovery_cache_record",
    "get_publisher_inventory_state",
    "get_report_download_drive_folder",
    "list_metadata",
    "list_report_source_quality_history",
    "list_public_publisher_report_value_aggregates",
    "list_publishers",
    "mark_publisher_private_api_candidate_promoted",
    "record_discovered_report_source",
    "record_publisher_private_api_candidate_observation",
    "record_report_value_score",
    "record_publisher_download_route",
    "record_publisher_inventory_recovery_cache_record",
    "record_publisher_inventory_run_quality",
    "record_publisher_inventory_state",
    "record_publisher_inventory_test_status",
    "record_report_source",
    "replace_publishers",
    "update_publisher_google_folder",
    "upsert_metadata",
]
