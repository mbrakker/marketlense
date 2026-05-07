from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

@dataclass(frozen=True)
class PublisherInventoryRoutePolicySignal:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory route-policy signal schema version."}
    )
    route_kind: str = field(
        metadata={
            "doc": "Discovery route kind this policy signal describes, for example `http_parse` or `browser_render`."
        }
    )
    attempts: int = field(
        metadata={"doc": "Number of recorded discovery attempts for this route kind."}
    )
    successful_attempts: int = field(
        metadata={
            "doc": "Number of successful discovery attempts recorded for this route kind."
        }
    )
    review_required_attempts: int = field(
        metadata={
            "doc": "Number of attempts whose run quality required review for this route kind."
        }
    )
    success_rate: float = field(
        metadata={"doc": "Successful-attempt ratio for this route kind."}
    )
    confidence_score: float = field(
        metadata={"doc": "Confidence score for preferring this route kind."}
    )
    rank_score: float = field(
        metadata={
            "doc": "Planner ranking score derived from success rate, quality, recency, and review penalty."
        }
    )
    last_outcome: str = field(
        metadata={"doc": "Most recent run-quality outcome for this route kind."}
    )
    last_status: str = field(
        metadata={"doc": "Most recent discovery status for this route kind."}
    )
    last_quality_band: str = field(
        metadata={"doc": "Most recent quality band for this route kind."}
    )
    last_scenario_class: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Most recent scenario class associated with this route kind, if available."
        },
    )
    recent_outcomes: List[str] = field(
        default_factory=list,
        metadata={"doc": "Recent outcome labels observed for this route kind."},
    )


@dataclass(frozen=True)
class PublisherInventoryRoutePlanStep:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory route-plan step schema version."}
    )
    step_name: str = field(
        metadata={
            "doc": "Unique orchestrator step name used for the planned discovery attempt."
        }
    )
    route_kind_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Discovery route kind to request for this step when known: http_parse or browser_render."
        },
    )
    route_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Remembered route summary to reuse for this step when available."
        },
    )
    uses_memory_route: bool = field(
        default=False,
        metadata={"doc": "Whether this step reuses a remembered inventory route."},
    )
    fallback_on_retryable_error: bool = field(
        default=False,
        metadata={
            "doc": "Whether the orchestrator should continue to the next planned step only when this step fails with a retryable AppError."
        },
    )


@dataclass(frozen=True)
class PublisherInventoryRunQualitySummary:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory run-quality summary schema version."}
    )
    outcome: str = field(
        metadata={
            "doc": "Run-level quality outcome, for example accepted, no_report_assets, raw_only_delta_rejected, undercoverage_regression, or unreachable_delta_tolerated."
        }
    )
    status: str = field(
        metadata={
            "doc": "Final run status string aligned with discovery test-status semantics, for example passed, passed:no_report_assets, or failed:<error_code>."
        }
    )
    quality_band: str = field(
        metadata={
            "doc": "Deterministic quality band for route-planning and drift monitoring: high, medium, or low."
        }
    )
    route_kind: str = field(
        metadata={
            "doc": "Discovery route kind used for the run-quality summary: http_parse or browser_render."
        }
    )
    recommended_route_kind: str = field(
        metadata={
            "doc": "Route kind recommended for the next discovery run based on this run's quality evidence."
        }
    )
    used_memory_route: bool = field(
        metadata={
            "doc": "Whether the successful discovery attempt reused remembered route memory."
        }
    )
    page_count: int = field(
        metadata={"doc": "Number of inventory pages traversed during the run."}
    )
    raw_candidate_count: int = field(
        metadata={
            "doc": "Number of normalized raw inventory items produced before diff screening."
        }
    )
    current_report_count: int = field(
        metadata={
            "doc": "Number of normalized report items in the current snapshot candidate."
        }
    )
    previous_report_count: int = field(
        metadata={
            "doc": "Number of normalized report items in the previous snapshot when available, else zero."
        }
    )
    raw_new_report_count: int = field(
        metadata={
            "doc": "Number of raw diff items before screening and landing-page qualification."
        }
    )
    screened_new_report_count: int = field(
        metadata={
            "doc": "Number of diff items approved by the screening step before landing-page qualification."
        }
    )
    qualified_new_report_count: int = field(
        metadata={
            "doc": "Number of diff items approved after landing-page qualification."
        }
    )
    snapshot_changed: bool = field(
        metadata={
            "doc": "Whether the canonical publisher snapshot changed after all quality gates."
        }
    )
    requires_review: bool = field(
        metadata={
            "doc": "Whether the run should be treated as drift-prone and reviewed before trusting route reuse."
        }
    )
    recommended_route_reason: str = field(
        metadata={"doc": "Short explanation for the recommended route kind."}
    )
    summary: str = field(
        metadata={"doc": "Compact human-readable summary of the run quality verdict."}
    )
    candidate_provenance_counts: dict[str, int] = field(
        default_factory=dict,
        metadata={
            "doc": "Counts of candidate provenance markers contributing to the run, keyed by provenance label."
        },
    )
    scenario_class: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional preflight scenario classification that described the landing surface for the run, for example direct_detail_html, filtered_archive, or mixed_content_hub."
        },
    )


@dataclass(frozen=True)
class PublisherInventoryRouteTrace:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory structured route-trace schema version."}
    )
    followed_report_listing: bool = field(
        default=False,
        metadata={
            "doc": "Whether discovery followed a dedicated report-listing entry point before collecting candidates."
        },
    )
    applied_report_filter: bool = field(
        default=False,
        metadata={
            "doc": "Whether discovery applied an explicit report-only filter during traversal."
        },
    )
    selected_filters: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Deterministic labels for filters that were applied during traversal."
        },
    )
    selected_tab_labels: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Ordered tab labels traversed during discovery when the archive used tabbed content sections."
        },
    )
    pagination_mode: str = field(
        default="none",
        metadata={
            "doc": "Pagination mode observed during traversal: none, next_link, button_next, load_more, tabbed, or mixed."
        },
    )
    preferred_control_labels: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Deterministic control labels preferred by the remembered route for pagination or expansion."
        },
    )
    candidate_surface_guard: str = field(
        default="none",
        metadata={
            "doc": "Guard describing how remembered traversal avoided irrelevant surfaces: none, candidate_density, report_filter, or tab_guard."
        },
    )
    surface_class: str = field(
        default="unknown",
        metadata={
            "doc": "Deterministic traversal surface class aligned with scenario/source-surface taxonomy."
        },
    )
    scroll_surface: str = field(
        default="document",
        metadata={
            "doc": "Primary browser scroll surface used during archive traversal: document, nested_container, or virtualized_list."
        },
    )
    scroll_surface_candidate_growth: bool = field(
        default=False,
        metadata={
            "doc": "Whether bounded scroll-surface probing exposed additional or changed candidate anchors."
        },
    )
    virtualized_list_detected: bool = field(
        default=False,
        metadata={
            "doc": "Whether traversal detected virtualized-list signals on the scroll surface."
        },
    )


@dataclass(frozen=True)
class PublisherInventoryScenarioSummary:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory scenario-summary schema version."}
    )
    scenario_class: str = field(
        metadata={
            "doc": "Deterministic scenario class inferred before or during discovery: direct_pdf, direct_detail_html, filtered_archive, tabbed_archive, mixed_content_hub, js_hydrated_archive, challenge_prone, or unknown."
        }
    )
    source_surface_class: str = field(
        default="unknown",
        metadata={
            "doc": "Best-effort surface class aligned with candidate quality taxonomy."
        },
    )
    confidence: float = field(
        default=0.0,
        metadata={
            "doc": "Deterministic scenario confidence score in the range 0.0-1.0."
        },
    )
    direct_detail_eligible: bool = field(
        default=False,
        metadata={
            "doc": "Whether the scenario strongly supports a direct-detail short-circuit instead of archive traversal."
        },
    )
    browser_preferred: bool = field(
        default=False,
        metadata={
            "doc": "Whether browser traversal should be preferred for this scenario when route planning has a choice."
        },
    )
    notes: str = field(
        default="",
        metadata={
            "doc": "Short human-readable explanation for the chosen scenario class."
        },
    )


@dataclass(frozen=True)
class PublisherInventoryRecoveryRecipe:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory recovery-recipe schema version."}
    )
    verification_class: str = field(
        metadata={
            "doc": "Verification class that triggered the deferred recovery recipe."
        }
    )
    source_surface_class: str = field(
        metadata={"doc": "Surface class of the candidate the recipe applies to."}
    )
    recovery_action: str = field(
        metadata={
            "doc": "Deterministic deferred recovery action, for example browser_retry, headless_retry, http_recheck, or protected_document_probe."
        }
    )
    reason: str = field(
        metadata={
            "doc": "Short explanation of why deferred recovery is allowed for this candidate."
        }
    )


@dataclass(frozen=True)
class PublisherInventoryRecoveryRecord:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory recovery-cache record schema version."}
    )
    normalized_url: str = field(
        metadata={
            "doc": "Normalized publisher insights URL that owned the recovery attempt."
        }
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized candidate URL whose recovery history is cached."}
    )
    source_surface_class: str = field(
        metadata={"doc": "Surface class associated with the cached candidate."}
    )
    verification_class: str = field(
        metadata={
            "doc": "Latest landing-page verification class associated with the candidate."
        }
    )
    recovery_action: str = field(
        metadata={
            "doc": "Most recent deferred recovery action recorded for the candidate."
        }
    )
    last_outcome: str = field(
        metadata={
            "doc": "Outcome of the latest recovery attempt, for example scheduled, recovered, skipped, or failed."
        }
    )
    last_http_status: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Latest observed HTTP status code for the candidate when available."
        },
    )
    last_error_marker: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Latest normalized error marker recorded for the candidate when available."
        },
    )
    updated_at_utc: str = field(
        default="",
        metadata={
            "doc": "UTC timestamp when this recovery cache record was last updated."
        },
    )


@dataclass(frozen=True)
class PublisherInventoryRoutePlanRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory route-plan request schema version."}
    )
    normalized_url: str = field(
        metadata={"doc": "Normalized publisher insights URL used for route planning."}
    )
    force_browser: bool = field(
        metadata={
            "doc": "Whether discovery must prefer browser traversal regardless of HTTP availability."
        }
    )
    remembered_route_kind: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Previously successful remembered discovery route kind when available."
        },
    )
    remembered_route_summary: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Previously successful remembered discovery route summary when available."
        },
    )
    remembered_route_trace: Optional[PublisherInventoryRouteTrace] = field(
        default=None,
        metadata={
            "doc": "Previously successful remembered discovery route trace when available."
        },
    )
    remembered_scenario_summary: Optional[PublisherInventoryScenarioSummary] = field(
        default=None,
        metadata={"doc": "Previously persisted scenario summary when available."},
    )
    previous_run_quality_summary: Optional[PublisherInventoryRunQualitySummary] = field(
        default=None,
        metadata={
            "doc": "Previously persisted run-quality summary used to bias route ordering when no remembered route exists."
        },
    )
    route_policy: List[PublisherInventoryRoutePolicySignal] = field(
        default_factory=list,
        metadata={
            "doc": "Ranked discovery route-kind policy signals learned from publisher inventory history."
        },
    )
    enable_structured_route_reuse: bool = field(
        default=False,
        metadata={
            "doc": "Whether the planner may prioritize typed remembered route traces over legacy route summaries."
        },
    )


@dataclass(frozen=True)
class PublisherInventoryRoutePlanResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory route-plan response schema version."}
    )
    steps: List[PublisherInventoryRoutePlanStep] = field(
        metadata={"doc": "Ordered discovery attempts the orchestrator should execute."}
    )
    planning_reason: str = field(
        metadata={
            "doc": "Short human-readable explanation of why this route order was chosen."
        }
    )


@dataclass(frozen=True)
class PublisherInventoryCoverageValidationRequest:
    schema_version: str = field(
        metadata={
            "doc": "Publisher inventory coverage-validation request schema version."
        }
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name for logging and error context."}
    )
    normalized_url: str = field(
        metadata={
            "doc": "Normalized publisher insights URL used as the coverage-validation key."
        }
    )
    previous_snapshot_available: bool = field(
        metadata={
            "doc": "Whether a previous canonical snapshot exists for this publisher."
        }
    )
    previous_page_count: int = field(
        metadata={
            "doc": "Number of pages recorded in the previous canonical snapshot when available, else zero."
        }
    )
    previous_report_count: int = field(
        metadata={
            "doc": "Number of items recorded in the previous canonical snapshot when available, else zero."
        }
    )
    current_page_count: int = field(
        metadata={"doc": "Number of pages traversed in the current candidate snapshot."}
    )
    current_report_count: int = field(
        metadata={"doc": "Number of items in the current candidate snapshot."}
    )
    raw_new_report_count: int = field(
        metadata={
            "doc": "Number of raw diff items before screening and landing-page qualification."
        }
    )
    screened_new_report_count: int = field(
        metadata={
            "doc": "Number of diff items approved by the candidate-screening step."
        }
    )
    qualified_new_report_count: int = field(
        metadata={
            "doc": "Number of diff items approved after landing-page qualification."
        }
    )
    candidate_snapshot_changed: bool = field(
        metadata={
            "doc": "Whether the candidate snapshot hash differs from the previous canonical snapshot hash."
        }
    )
    quality_rejection_reasons: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Ordered landing-page quality rejection reasons used for systematic-unreachable detection."
        },
    )


@dataclass(frozen=True)
class PublisherInventoryCoverageValidationResponse:
    schema_version: str = field(
        metadata={
            "doc": "Publisher inventory coverage-validation response schema version."
        }
    )
    verdict: str = field(
        metadata={
            "doc": "Coverage-validation verdict: accepted, no_report_assets, raw_only_delta_rejected, undercoverage_regression, unreachable_delta_failure, or unreachable_delta_tolerated."
        }
    )
    reason: str = field(
        metadata={
            "doc": "Short human-readable reason explaining the coverage-validation verdict."
        }
    )
    snapshot_allowed: bool = field(
        metadata={
            "doc": "Whether the candidate snapshot is allowed to become canonical after coverage validation."
        }
    )
    no_report_assets_detected: bool = field(
        metadata={
            "doc": "Whether the run should be treated as an archive with no qualifying report assets."
        }
    )
    should_raise_error: bool = field(
        metadata={
            "doc": "Whether the orchestrator must fail the run based on this coverage verdict."
        }
    )
    error_code: Optional[str] = field(
        default=None,
        metadata={"doc": "Typed AppError code to raise when should_raise_error=true."},
    )
    error_message: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Typed AppError message to raise when should_raise_error=true."
        },
    )


@dataclass(frozen=True)
class PublisherInventoryRunQualityEvaluationRequest:
    schema_version: str = field(
        metadata={
            "doc": "Publisher inventory run-quality evaluation request schema version."
        }
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name for the completed discovery run."}
    )
    normalized_url: str = field(
        metadata={
            "doc": "Normalized publisher insights URL used as the run-quality key."
        }
    )
    route_kind: str = field(
        metadata={"doc": "Discovery route kind used successfully for the run."}
    )
    used_memory_route: bool = field(
        metadata={
            "doc": "Whether the successful discovery attempt reused remembered route memory."
        }
    )
    page_count: int = field(
        metadata={"doc": "Number of inventory pages traversed during the run."}
    )
    raw_candidate_count: int = field(
        metadata={
            "doc": "Number of normalized items in the current candidate snapshot before diff screening."
        }
    )
    current_report_count: int = field(
        metadata={
            "doc": "Number of normalized items in the canonical current snapshot candidate."
        }
    )
    previous_report_count: int = field(
        metadata={
            "doc": "Number of normalized items in the previous canonical snapshot when available, else zero."
        }
    )
    raw_new_report_count: int = field(
        metadata={
            "doc": "Number of raw diff items before screening and landing-page qualification."
        }
    )
    screened_new_report_count: int = field(
        metadata={
            "doc": "Number of diff items approved by the candidate-screening step."
        }
    )
    qualified_new_report_count: int = field(
        metadata={
            "doc": "Number of diff items approved after landing-page qualification."
        }
    )
    snapshot_changed: bool = field(
        metadata={
            "doc": "Whether the canonical snapshot changed after all quality gates."
        }
    )
    coverage_validation: PublisherInventoryCoverageValidationResponse = field(
        metadata={
            "doc": "Explicit coverage-validation verdict for the completed discovery run."
        }
    )
    candidate_provenance_counts: dict[str, int] = field(
        default_factory=dict,
        metadata={
            "doc": "Counts of candidate provenance markers contributing to the run, keyed by provenance label."
        },
    )

