# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.contracts.regeneration import (
    FailureFingerprint,
    RepairDelta,
    RepairSeverityChange,
    repair_strategy_fingerprint,
)

from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)

from src.contracts.soft_copy_claim_provenance import (
    soft_copy_claim_provenance_to_payload,
)

from src.contracts.validation import ValidationReport

from src.generators.soft_copy_claim_provenance import build_soft_copy_claim_provenance

from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
    _normalize_regeneration_issue,
)

from src.orchestrators._report_analysis_orchestrator.validation import (
    _load_candidate_claim_validation_for_promotion,
    _run_validation_regeneration_loop,
    _store_promoted_candidate_claim_validation,
)

from src.services import file_service, report_analysis_store_service

from src.utils.cache_utils import sha256_json

from ._shared import *  # noqa: F401,F403

__all__ = [
    "test_load_retained_claim_candidate_binds_to_promoted_artifacts",
    "test_store_promoted_retained_claim_candidate_to_report_scoped_pack",
    "test_long_validation_candidate_pack_stores_and_loads_after_path_compaction",
    "test_promote_retained_claim_candidate_rejects_artifact_mismatch",
    "test_build_regeneration_plan_skips_info_and_orders_errors_first",
    "test_build_regeneration_plan_maps_public_artifact_copy_to_its_family",
    "test_build_regeneration_plan_keeps_hard_repair_claim_scoped",
    "test_hard_soft_copy_repair_keeps_coupled_grounding_warnings_in_plan",
    "test_mobile_numbers_failure_targets_exact_insight_so_what_leaf",
    "test_persisting_insight_metric_failures_preempt_linkedin_and_skip_noop_copy",
    "test_repair_memory_does_not_upgrade_unknown_severity_to_hard_error",
    "test_multi_insight_retry_does_not_offer_single_item_safe_removal",
    "test_summary_claim_map_grounding_is_limited_to_the_failed_item",
    "test_indexed_summary_claim_issue_resolves_only_the_failed_item",
    "test_indexed_summary_claim_support_failure_gets_exact_repair_path",
    "test_validation_loop_preflights_empty_summary_package_to_safe_removal",
    "test_insight_repair_authorizes_same_claim_grounding_warning_fields",
    "test_summary_repair_keeps_same_claim_grounding_context_only",
    "test_summary_repair_maps_duplicate_claim_surfaces_together",
    "test_run_report_analysis_rejects_unsupported_repair_target",
    "test_run_report_analysis_snapshot_preserves_internal_payload_metadata",
]


__all__ = [name for name in globals() if not name.startswith("__")]
