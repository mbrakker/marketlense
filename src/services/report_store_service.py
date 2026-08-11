"""Canonical report-store service boundary.

The public report-store API stays singular here, while semantic families live in
`src.services._report_store_service`.
"""

from __future__ import annotations

from src.services._report_store_service.artifact_lineage import (
    audit_artifact_lineage,
    backfill_artifact_lineage,
    check_artifact_reuse,
    get_artifact_lineage_for_storage,
    invalidate_artifacts,
    record_artifact_lineage,
    trace_artifact_lineage,
)
from src.services._report_store_service.corpus_rehabilitation import (
    approve_corpus_rehabilitation_campaign,
    create_corpus_rehabilitation_campaign,
    read_corpus_rehabilitation_campaign,
    read_corpus_rehabilitation_plan,
    update_corpus_rehabilitation_campaign_item,
)
from src.services._report_store_service.download_routes import (
    evaluate_acquisition_route_suppression,
    get_publisher_download_route,
    list_acquisition_resource_aggregates,
    mark_publisher_private_api_candidate_promoted,
    record_acquisition_attempt_resource,
    record_publisher_download_route,
    record_publisher_private_api_candidate_observation,
)
from src.services._report_store_service.execution_plan import (
    build_current_report_execution_compatibility,
    build_minimal_execution_plan,
    read_validated_report_artifacts,
    record_minimal_execution_plan,
    record_minimal_execution_plan_result,
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
    get_report_publication_metadata,
    get_report_source_identity,
    list_metadata,
    record_source_identity_observation,
    resolve_report_source_identity,
    upsert_metadata,
    upsert_source_publication_metadata,
)
from src.services._report_store_service.publishers import (
    list_publishers,
    replace_publishers,
    update_publisher_google_folder,
)
from src.services._report_store_service.route_economics import (
    read_acquisition_route_economics,
)
from src.services._report_store_service.sources import (
    get_report_download_drive_folder,
    link_report_to_source,
    list_public_publisher_report_value_aggregates,
    list_report_source_quality_history,
    record_discovered_report_source,
    record_report_source,
    record_report_value_score,
)
from src.services._report_store_service.validation_run_manifest import (
    audit_validation_run_manifest,
    create_validation_run_manifest,
    record_validation_run_manifest_stage,
    resolve_validation_run_manifest_attempt,
)

__all__ = [
    "check_report_db_access",
    "create_validation_run_manifest",
    "build_current_report_execution_compatibility",
    "build_minimal_execution_plan",
    "audit_artifact_lineage",
    "audit_validation_run_manifest",
    "backfill_artifact_lineage",
    "check_artifact_reuse",
    "get_metadata",
    "get_report_publication_metadata",
    "get_report_source_identity",
    "get_artifact_lineage_for_storage",
    "invalidate_artifacts",
    "get_publisher_download_route",
    "evaluate_acquisition_route_suppression",
    "list_acquisition_resource_aggregates",
    "get_publisher_inventory_recovery_cache_record",
    "get_publisher_inventory_state",
    "get_report_download_drive_folder",
    "link_report_to_source",
    "list_metadata",
    "list_report_source_quality_history",
    "list_public_publisher_report_value_aggregates",
    "list_publishers",
    "mark_publisher_private_api_candidate_promoted",
    "record_discovered_report_source",
    "record_artifact_lineage",
    "record_minimal_execution_plan",
    "record_minimal_execution_plan_result",
    "read_validated_report_artifacts",
    "record_publisher_private_api_candidate_observation",
    "record_acquisition_attempt_resource",
    "record_validation_run_manifest_stage",
    "resolve_validation_run_manifest_attempt",
    "read_acquisition_route_economics",
    "read_corpus_rehabilitation_plan",
    "create_corpus_rehabilitation_campaign",
    "approve_corpus_rehabilitation_campaign",
    "read_corpus_rehabilitation_campaign",
    "update_corpus_rehabilitation_campaign_item",
    "record_report_value_score",
    "record_publisher_download_route",
    "record_publisher_inventory_recovery_cache_record",
    "record_publisher_inventory_run_quality",
    "record_publisher_inventory_state",
    "record_publisher_inventory_test_status",
    "record_report_source",
    "record_source_identity_observation",
    "replace_publishers",
    "resolve_report_source_identity",
    "update_publisher_google_folder",
    "trace_artifact_lineage",
    "upsert_metadata",
    "upsert_source_publication_metadata",
]
