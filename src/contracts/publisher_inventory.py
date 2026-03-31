from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class PublisherInventoryPage:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory page schema version."}
    )
    page_number: int = field(
        metadata={"doc": "One-based inventory page number visited during discovery."}
    )
    page_url: str = field(
        metadata={"doc": "Absolute URL of the visited inventory page."}
    )


@dataclass(frozen=True)
class PublisherInventoryRawCandidate:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory raw candidate schema version."}
    )
    url: str = field(
        metadata={"doc": "Raw absolute or relative URL extracted from the source page."}
    )
    title: str = field(
        metadata={"doc": "Raw candidate title text extracted from the source page."}
    )
    source_page_url: str = field(
        metadata={"doc": "Absolute URL of the inventory page where this candidate was found."}
    )
    discovered_on_page_number: int = field(
        metadata={"doc": "One-based inventory page number where this candidate was found."}
    )
    pdf_url: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional raw PDF URL associated with this candidate."},
    )
    published_at_text: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional raw published-date text extracted for this candidate."},
    )


@dataclass(frozen=True)
class PublisherInventoryItem:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory item schema version."}
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized canonical report URL used as the diff identity."}
    )
    title: str = field(metadata={"doc": "Normalized report title."})
    discovered_on_page_number: int = field(
        metadata={"doc": "One-based inventory page number where the item was first found."}
    )
    pdf_url: Optional[str] = field(
        default=None,
        metadata={"doc": "Normalized PDF URL when the report link points directly to a PDF or one is known."},
    )
    published_at_text: Optional[str] = field(
        default=None,
        metadata={"doc": "Normalized published-date text when available."},
    )


@dataclass(frozen=True)
class PublisherInventorySnapshot:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory snapshot schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name resolved from the reports database."}
    )
    insights_url: str = field(
        metadata={"doc": "Original publisher insights URL used for discovery."}
    )
    normalized_insights_url: str = field(
        metadata={"doc": "Normalized publisher insights URL used as the memory key."}
    )
    discovered_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the snapshot was produced."}
    )
    route_kind: str = field(
        metadata={"doc": "Discovery route kind used for this snapshot: http_parse or browser_render."}
    )
    route_summary: str = field(
        metadata={"doc": "Summary of the successful discovery route for reuse on later runs."}
    )
    final_page_url: str = field(
        metadata={"doc": "Final page URL observed at the end of the discovery run."}
    )
    pages: List[PublisherInventoryPage] = field(
        metadata={"doc": "Inventory pages traversed to build this snapshot."}
    )
    items: List[PublisherInventoryItem] = field(
        metadata={"doc": "Normalized report inventory across all traversed pages."}
    )


@dataclass(frozen=True)
class PublisherInventoryDiffItem:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory diff item schema version."}
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized canonical report URL that is new in the current snapshot."}
    )
    title: str = field(metadata={"doc": "Normalized title for the new report."})
    discovered_on_page_number: int = field(
        metadata={"doc": "One-based inventory page number where the new report link was found."}
    )


@dataclass(frozen=True)
class PublisherInventorySettings:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory discovery settings schema version."}
    )
    openrouter_api_key: str = field(
        metadata={"doc": "OpenRouter API key used when browser-render fallback is required."}
    )
    model: str = field(
        metadata={"doc": "Model ID used by the browser-render fallback flow."}
    )
    temperature: float = field(
        metadata={"doc": "Sampling temperature for browser-render discovery."}
    )
    timeout_seconds: float = field(
        metadata={"doc": "Per-model timeout in seconds for browser-render discovery."}
    )
    max_steps: int = field(
        metadata={"doc": "Maximum browser-use agent steps per discovery run."}
    )
    output_dir: str = field(
        metadata={"doc": "Root directory used for temporary browser discovery output."}
    )
    reports_db: str = field(
        metadata={"doc": "SQLite reports DB path used for publisher lookups and snapshot indexing."}
    )
    google_sa_path: str = field(
        metadata={"doc": "Filesystem path to the Google service account JSON used for Drive access when drive_auth_mode=service_account."}
    )
    prompt_namespace: str = field(
        metadata={"doc": "Prompt namespace used for browser-render inventory discovery."}
    )
    pagination_max_pages: int = field(
        metadata={"doc": "Hard upper bound on inventory pages traversed in one discovery run."}
    )
    http_timeout_seconds: float = field(
        metadata={"doc": "HTTP timeout in seconds for direct HTML fetch discovery."}
    )
    drive_auth_mode: str = field(
        default="service_account",
        metadata={"doc": "Drive auth mode: service_account or oauth_user."},
    )
    google_oauth_client_path: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional OAuth desktop client JSON path when drive_auth_mode=oauth_user."},
    )
    google_oauth_token_path: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional OAuth authorized-user token JSON path when drive_auth_mode=oauth_user."},
    )
    openrouter_http_referer: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional HTTP-Referer header sent to OpenRouter."},
    )
    headed: bool = field(
        default=False,
        metadata={"doc": "Whether browser-render discovery should run in a visible browser."},
    )
    force_browser: bool = field(
        default=False,
        metadata={"doc": "Whether discovery must use the browser-render route instead of direct HTTP parsing."},
    )
    retry_retries: int = field(
        default=1,
        metadata={"doc": "Retry count for orchestrated inventory discovery attempts."},
    )
    retry_base_delay_seconds: float = field(
        default=1.0,
        metadata={"doc": "Base delay before the first inventory discovery retry."},
    )
    retry_backoff_step_seconds: float = field(
        default=1.0,
        metadata={"doc": "Linear backoff step added per inventory discovery retry."},
    )
    retry_jitter_seconds: float = field(
        default=0.25,
        metadata={"doc": "Maximum jitter added to inventory discovery retry delays."},
    )
    openai_api_key: str = field(
        default="",
        metadata={"doc": "OpenAI API key used for candidate screening before report_sources persistence when candidate_screening_enabled=true."},
    )
    openai_models: dict[str, str] = field(
        default_factory=dict,
        metadata={"doc": "Optional per-namespace OpenAI model overrides used by publisher-inventory candidate screening."},
    )
    openai_seed: Optional[int] = field(
        default=None,
        metadata={"doc": "Optional OpenAI seed used for publisher-inventory candidate screening."},
    )
    candidate_screening_enabled: bool = field(
        default=True,
        metadata={"doc": "Whether new diff candidates should be screened by OpenAI before insertion into report_sources."},
    )
    candidate_screening_model: str = field(
        default="gpt-5-nano",
        metadata={"doc": "Base OpenAI model used for candidate screening before report_sources persistence."},
    )
    candidate_screening_temperature: float = field(
        default=1.0,
        metadata={"doc": "Sampling temperature for publisher-inventory candidate screening."},
    )
    candidate_screening_timeout_seconds: float = field(
        default=120.0,
        metadata={"doc": "Timeout in seconds for publisher-inventory candidate screening calls."},
    )
    candidate_screening_batch_size: int = field(
        default=20,
        metadata={"doc": "Maximum number of candidates sent to a single publisher-inventory screening LLM call."},
    )
    candidate_screening_prompt_namespace: str = field(
        default="publisher_inventory/meaningful_candidate_screen",
        metadata={"doc": "Prompt namespace used to screen new publisher-inventory diff candidates before queueing them for download."},
    )
    candidate_quality_check_enabled: bool = field(
        default=True,
        metadata={"doc": "Whether landing-page quality checks should run after LLM screening and before report_sources persistence."},
    )
    candidate_quality_check_timeout_seconds: float = field(
        default=15.0,
        metadata={"doc": "Per-candidate HTTP timeout in seconds for landing-page quality checks before report_sources persistence."},
    )
    candidate_quality_check_max_workers: int = field(
        default=6,
        metadata={"doc": "Maximum parallel landing-page fetch workers used by the candidate quality-check service."},
    )
    cost_ledger_path: str = field(
        default="./out/cost-ledger.jsonl",
        metadata={"doc": "Filesystem path for OpenAI cost ledger entries produced by candidate screening."},
    )
    cost_daily_path: str = field(
        default="./out/cost-daily.json",
        metadata={"doc": "Filesystem path for daily OpenAI cost rollups produced by candidate screening."},
    )
    model_pricing: dict = field(
        default_factory=dict,
        metadata={"doc": "Per-model pricing table used for candidate-screening cost estimation."},
    )
    llm_retry_retries: int = field(
        default=1,
        metadata={"doc": "Maximum retry count for individual candidate-screening LLM calls."},
    )
    llm_retry_base_delay_seconds: float = field(
        default=1.0,
        metadata={"doc": "Base delay in seconds before the first candidate-screening LLM retry."},
    )
    llm_retry_backoff_step_seconds: float = field(
        default=1.0,
        metadata={"doc": "Additional linear backoff delay added per candidate-screening LLM retry attempt."},
    )
    llm_retry_jitter_seconds: float = field(
        default=0.25,
        metadata={"doc": "Maximum jitter in seconds added to each candidate-screening LLM retry delay."},
    )
    llm_circuit_breaker_failure_threshold: int = field(
        default=3,
        metadata={"doc": "Consecutive retryable candidate-screening LLM failures required to open the circuit breaker."},
    )
    llm_circuit_breaker_recovery_seconds: float = field(
        default=30.0,
        metadata={"doc": "Cooldown in seconds before the candidate-screening LLM circuit breaker allows a probe call."},
    )


@dataclass(frozen=True)
class PublisherInventoryCandidateScreeningItem:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory candidate-screening item schema version."}
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized candidate URL under review for future download persistence."}
    )
    title: str = field(metadata={"doc": "Normalized candidate title under review."})
    discovered_on_page_number: int = field(
        metadata={"doc": "One-based inventory page number where the candidate was found."}
    )
    source_page_url: str = field(
        metadata={"doc": "Inventory page URL where the candidate was found."}
    )


@dataclass(frozen=True)
class PublisherInventoryCandidateScreeningDecision:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory candidate-screening decision schema version."}
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized candidate URL that was screened."}
    )
    accepted: bool = field(
        metadata={"doc": "Whether the candidate is a meaningful report-like asset that should be queued for future download."}
    )
    reason: str = field(
        metadata={"doc": "Short human-readable reason explaining the screening decision."}
    )


@dataclass(frozen=True)
class PublisherInventoryCandidateScreeningRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory candidate-screening request schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name resolved from the reports database."}
    )
    insights_url: str = field(
        metadata={"doc": "Publisher insights URL whose new diff items are being screened."}
    )
    candidates: List[PublisherInventoryCandidateScreeningItem] = field(
        metadata={"doc": "New diff candidates to evaluate before persistence into report_sources."}
    )
    settings: PublisherInventorySettings = field(
        metadata={"doc": "Loaded publisher inventory discovery settings including candidate-screening configuration."}
    )


@dataclass(frozen=True)
class PublisherInventoryCandidateScreeningResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory candidate-screening response schema version."}
    )
    approved_items: List[PublisherInventoryCandidateScreeningItem] = field(
        metadata={"doc": "Candidates accepted for future download persistence."}
    )
    rejected_items: List[PublisherInventoryCandidateScreeningItem] = field(
        metadata={"doc": "Candidates rejected by the LLM screening step."}
    )
    decisions: List[PublisherInventoryCandidateScreeningDecision] = field(
        metadata={"doc": "Full screening decision set returned for all reviewed candidates."}
    )
    model: str = field(
        metadata={"doc": "Resolved OpenAI model ID used for candidate screening."}
    )
    request_id: Optional[str] = field(
        default=None,
        metadata={"doc": "Provider request identifier for the screening call, if available."},
    )
    raw_response: str = field(
        default="",
        metadata={"doc": "Raw model response text returned by the candidate-screening call."},
    )


@dataclass(frozen=True)
class PublisherInventoryLandingPageInspectionItem:
    schema_version: str = field(
        metadata={"doc": "Landing-page inspection item schema version."}
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized candidate URL whose destination page should be inspected."}
    )
    title: str = field(
        metadata={"doc": "Current normalized candidate title carried into landing-page inspection."}
    )
    discovered_on_page_number: int = field(
        metadata={"doc": "One-based inventory page number where the candidate was found."}
    )
    source_page_url: str = field(
        metadata={"doc": "Inventory page URL where the candidate was found."}
    )


@dataclass(frozen=True)
class PublisherInventoryLandingPageInspectionRequest:
    schema_version: str = field(
        metadata={"doc": "Landing-page inspection request schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name for logging and inspection context."}
    )
    items: List[PublisherInventoryLandingPageInspectionItem] = field(
        metadata={"doc": "Candidate landing pages that should be fetched and inspected."}
    )
    timeout_seconds: float = field(
        metadata={"doc": "Per-request HTTP timeout in seconds used for landing-page inspection fetches."}
    )
    max_workers: int = field(
        metadata={"doc": "Maximum concurrent fetch workers used for landing-page inspection."}
    )


@dataclass(frozen=True)
class PublisherInventoryLandingPageObservation:
    schema_version: str = field(
        metadata={"doc": "Landing-page observation schema version."}
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized candidate URL that was inspected."}
    )
    source_title: str = field(
        metadata={"doc": "Candidate title before landing-page qualification."}
    )
    final_url: str = field(
        metadata={"doc": "Final URL after redirects during landing-page inspection."}
    )
    final_title: str = field(
        metadata={"doc": "HTML <title> text extracted from the landing page when available."}
    )
    h1_title: str = field(
        metadata={"doc": "First H1 text extracted from the landing page when available."}
    )
    og_title: str = field(
        metadata={"doc": "Open Graph title extracted from the landing page when available."}
    )
    http_status_code: Optional[int] = field(
        default=None,
        metadata={"doc": "HTTP status code observed for the landing page when available."},
    )
    content_type: str = field(
        default="",
        metadata={"doc": "Observed response Content-Type header for the landing page fetch."},
    )
    fetch_error: str = field(
        default="",
        metadata={"doc": "Short fetch error message when the landing page could not be retrieved successfully."},
    )
    is_pdf: bool = field(
        default=False,
        metadata={"doc": "Whether the inspected target resolved to a direct PDF/document asset."},
    )
    has_asset_type_term: bool = field(
        default=False,
        metadata={"doc": "Whether the landing page URL/title/content contains report-like asset type terms."},
    )
    has_download_language: bool = field(
        default=False,
        metadata={"doc": "Whether the landing page includes strong download/access/get-report language."},
    )
    has_gated_form: bool = field(
        default=False,
        metadata={"doc": "Whether the landing page includes a form likely used to access the asset."},
    )
    has_document_structure: bool = field(
        default=False,
        metadata={"doc": "Whether the landing page exposes report-like document structure such as contents, methodology, or findings."},
    )
    has_price_or_purchase: bool = field(
        default=False,
        metadata={"doc": "Whether the landing page exposes report product signals such as price, buy, or add-to-cart."},
    )
    has_print_language: bool = field(
        default=False,
        metadata={"doc": "Whether the landing page includes print/printable/read-report language consistent with a document asset."},
    )
    has_editorial_url_pattern: bool = field(
        default=False,
        metadata={"doc": "Whether the landing page URL matches common blog/news/article/editorial path patterns."},
    )
    has_editorial_markers: bool = field(
        default=False,
        metadata={"doc": "Whether the landing page content exposes blog/article/news style markers."},
    )
    has_related_posts: bool = field(
        default=False,
        metadata={"doc": "Whether the landing page prominently exposes related-post/article recommendations."},
    )
    has_newsletter_cta: bool = field(
        default=False,
        metadata={"doc": "Whether the landing page prominently exposes newsletter signup CTAs."},
    )
    has_contact_sales_cta: bool = field(
        default=False,
        metadata={"doc": "Whether the landing page prominently exposes contact-sales or demo-booking CTAs."},
    )
    has_dead_page_marker: bool = field(
        default=False,
        metadata={"doc": "Whether the landing page looks missing, 404, or otherwise dead."},
    )


@dataclass(frozen=True)
class PublisherInventoryLandingPageInspectionResponse:
    schema_version: str = field(
        metadata={"doc": "Landing-page inspection response schema version."}
    )
    observations: List[PublisherInventoryLandingPageObservation] = field(
        metadata={"doc": "Landing-page observations returned for the inspected candidate set."}
    )


@dataclass(frozen=True)
class PublisherInventoryQualifiedCandidateItem:
    schema_version: str = field(
        metadata={"doc": "Qualified candidate item schema version."}
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized candidate URL approved or rejected by the landing-page quality check."}
    )
    title: str = field(
        metadata={"doc": "Resolved report-like title used after landing-page qualification."}
    )
    discovered_on_page_number: int = field(
        metadata={"doc": "One-based inventory page number where the candidate was found."}
    )
    source_page_url: str = field(
        metadata={"doc": "Inventory page URL where the candidate was found."}
    )


@dataclass(frozen=True)
class PublisherInventoryCandidateQualityDecision:
    schema_version: str = field(
        metadata={"doc": "Candidate landing-page quality decision schema version."}
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized candidate URL evaluated by the landing-page quality check."}
    )
    accepted: bool = field(
        metadata={"doc": "Whether the landing page qualifies as a report-like asset worth queueing for download."}
    )
    reason: str = field(
        metadata={"doc": "Short human-readable reason explaining the landing-page quality decision."}
    )
    resolved_title: str = field(
        metadata={"doc": "Best resolved title chosen from the candidate and landing-page metadata."}
    )


@dataclass(frozen=True)
class PublisherInventoryCandidateQualityRequest:
    schema_version: str = field(
        metadata={"doc": "Candidate landing-page quality-check request schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name resolved from the reports database."}
    )
    insights_url: str = field(
        metadata={"doc": "Publisher insights URL whose already-screened candidates are being qualified."}
    )
    candidates: List[PublisherInventoryCandidateScreeningItem] = field(
        metadata={"doc": "Candidates already accepted by the LLM screening stage and pending final landing-page quality qualification."}
    )
    settings: PublisherInventorySettings = field(
        metadata={"doc": "Loaded publisher inventory discovery settings including quality-check configuration."}
    )


@dataclass(frozen=True)
class PublisherInventoryCandidateQualityResponse:
    schema_version: str = field(
        metadata={"doc": "Candidate landing-page quality-check response schema version."}
    )
    approved_items: List[PublisherInventoryQualifiedCandidateItem] = field(
        metadata={"doc": "Candidates accepted for report_sources persistence after landing-page qualification."}
    )
    rejected_items: List[PublisherInventoryQualifiedCandidateItem] = field(
        metadata={"doc": "Candidates rejected by the landing-page quality check."}
    )
    decisions: List[PublisherInventoryCandidateQualityDecision] = field(
        metadata={"doc": "Full landing-page quality decision set returned for all reviewed candidates."}
    )


@dataclass(frozen=True)
class PublisherInventoryDiscoveryRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory discovery request schema version."}
    )
    insights_url: str = field(
        metadata={"doc": "Publisher insights URL to crawl and diff."}
    )
    reports_db: str = field(
        metadata={"doc": "SQLite reports DB path used for publisher lookup and state persistence."}
    )
    settings: PublisherInventorySettings = field(
        metadata={"doc": "Loaded publisher inventory discovery settings."}
    )


@dataclass(frozen=True)
class PublisherInventoryDiscoveryResult:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory discovery result schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name resolved from the reports DB."}
    )
    insights_url: str = field(
        metadata={"doc": "Original publisher insights URL provided by the caller."}
    )
    normalized_insights_url: str = field(
        metadata={"doc": "Normalized publisher insights URL used as the memory key."}
    )
    new_report_urls: List[PublisherInventoryDiffItem] = field(
        metadata={"doc": "List of report URLs that are new versus the previous snapshot."}
    )
    current_report_count: int = field(
        metadata={"doc": "Number of normalized reports in the current snapshot."}
    )
    previous_report_count: int = field(
        metadata={"doc": "Number of normalized reports in the previous snapshot."}
    )
    used_memory_route: bool = field(
        metadata={"doc": "Whether a remembered route hint was used on the successful run."}
    )
    snapshot_changed: bool = field(
        metadata={"doc": "Whether the normalized current snapshot differed from the previous snapshot."}
    )

@dataclass(frozen=True)
class PublisherInventoryServiceRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory service request schema version."}
    )
    insights_url: str = field(
        metadata={"doc": "Publisher insights URL to crawl for report inventory."}
    )
    settings: PublisherInventorySettings = field(
        metadata={"doc": "Loaded publisher inventory discovery settings."}
    )
    route_hint: Optional[str] = field(
        default=None,
        metadata={"doc": "Previously successful route summary used to bias browser-render discovery."},
    )
    route_kind_hint: Optional[str] = field(
        default=None,
        metadata={"doc": "Previously successful route kind when known: http_parse or browser_render."},
    )
@dataclass(frozen=True)
class PublisherInventoryServiceResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory service response schema version."}
    )
    source_url: str = field(
        metadata={"doc": "Original publisher insights URL provided by the caller."}
    )
    normalized_url: str = field(
        metadata={"doc": "Normalized publisher insights URL used as the memory key."}
    )
    route_kind: str = field(
        metadata={"doc": "Discovery route kind used successfully: http_parse or browser_render."}
    )
    route_summary: str = field(
        metadata={"doc": "Summary of the successful discovery route for reuse on later runs."}
    )
    final_page_url: str = field(
        metadata={"doc": "Final page URL observed at the end of the discovery run."}
    )
    used_route_hint: bool = field(
        metadata={"doc": "Whether the discovery run used a remembered route hint."}
    )
    pages: List[PublisherInventoryPage] = field(
        metadata={"doc": "Inventory pages traversed during this run."}
    )
    candidates: List[PublisherInventoryRawCandidate] = field(
        metadata={"doc": "Raw report candidates extracted across all traversed pages."}
    )


@dataclass(frozen=True)
class PublisherInventoryBuildRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory build request schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name resolved from the reports DB."}
    )
    insights_url: str = field(
        metadata={"doc": "Original publisher insights URL provided by the caller."}
    )
    normalized_insights_url: str = field(
        metadata={"doc": "Normalized publisher insights URL used as the memory key."}
    )
    discovered_at_utc: str = field(
        metadata={"doc": "UTC timestamp for the current discovery run."}
    )
    route_kind: str = field(
        metadata={"doc": "Discovery route kind used successfully for this run."}
    )
    route_summary: str = field(
        metadata={"doc": "Summary of the successful discovery route."}
    )
    final_page_url: str = field(
        metadata={"doc": "Final page URL observed at the end of the discovery run."}
    )
    pages: List[PublisherInventoryPage] = field(
        metadata={"doc": "Inventory pages traversed during the discovery run."}
    )
    candidates: List[PublisherInventoryRawCandidate] = field(
        metadata={"doc": "Raw candidates extracted during the discovery run."}
    )
    previous_snapshot: Optional[PublisherInventorySnapshot] = field(
        default=None,
        metadata={"doc": "Previous snapshot used to compute the diff when available."},
    )


@dataclass(frozen=True)
class PublisherInventoryBuildResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory build response schema version."}
    )
    snapshot: PublisherInventorySnapshot = field(
        metadata={"doc": "Normalized current snapshot for this discovery run."}
    )
    new_items: List[PublisherInventoryDiffItem] = field(
        metadata={"doc": "New report URLs discovered versus the previous snapshot."}
    )
    current_report_count: int = field(
        metadata={"doc": "Number of normalized reports in the current snapshot."}
    )
    previous_report_count: int = field(
        metadata={"doc": "Number of normalized reports in the previous snapshot."}
    )
    snapshot_sha256: str = field(
        metadata={"doc": "SHA-256 hash of the normalized snapshot JSON payload."}
    )
    snapshot_json: str = field(
        metadata={"doc": "Deterministic JSON serialization of the normalized snapshot."}
    )
