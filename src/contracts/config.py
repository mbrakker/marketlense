from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ConfigLoadRequest:
    schema_version: str = field(metadata={"doc": "Config request schema version."})
    path: str = field(
        metadata={"doc": "Absolute or workspace-relative path to the YAML config file."}
    )


@dataclass(frozen=True)
class OpenAICredentialResolveRequest:
    schema_version: str = field(
        metadata={"doc": "OpenAI credential resolution request schema version."}
    )


@dataclass(frozen=True)
class OpenAICredentialResolveResponse:
    schema_version: str = field(
        metadata={"doc": "OpenAI credential resolution response schema version."}
    )
    api_key: str = field(metadata={"doc": "Resolved OpenAI API key secret."})
    source: str = field(
        metadata={"doc": "Sanitized configuration source used for resolution."}
    )


@dataclass(frozen=True)
class AppSettings:
    schema_version: str = field(metadata={"doc": "Settings schema version."})
    google_sa_path: str = field(
        metadata={
            "doc": "Filesystem path to the Google service account JSON when drive_auth_mode=service_account."
        }
    )
    gdrive_folder_id: str = field(
        metadata={"doc": "Google Drive folder ID containing source PDFs."}
    )
    openai_api_key: str = field(
        metadata={"doc": "OpenAI API key (secret, loaded from env)."}
    )
    openai_model: str = field(
        metadata={"doc": "OpenAI model ID for report generation."}
    )
    batch_limit: int = field(metadata={"doc": "Max PDFs to process per ingest run."})
    output_dir: str = field(
        metadata={"doc": "Output directory for rendered HTML and assets."}
    )
    cache_dir: str = field(metadata={"doc": "Cache directory for downloaded PDFs."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    reports_db: str = field(metadata={"doc": "SQLite path for report metadata."})
    publisher_profiles_path: str = field(
        metadata={
            "doc": "Filesystem path to the publisher snapshot JSON sourced from Notion."
        }
    )
    category_mapping_path: str = field(
        metadata={"doc": "Filesystem path to category mappings YAML."}
    )
    cover_style_path: str = field(
        metadata={"doc": "Filesystem path to cover style YAML."}
    )
    ingest_lock_path: str = field(
        metadata={"doc": "Filesystem path for the ingest single-run lock file."}
    )
    temperature: float = field(
        metadata={"doc": "Sampling temperature for report generation."}
    )
    drive_auth_mode: str = field(
        default="service_account",
        metadata={"doc": "Drive auth mode: service_account or oauth_user."},
    )
    google_oauth_client_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional OAuth desktop client JSON path when drive_auth_mode=oauth_user."
        },
    )
    google_oauth_token_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional OAuth authorized-user token JSON path when drive_auth_mode=oauth_user."
        },
    )
    taxonomy_temperature: float = field(
        default=1.0,
        metadata={"doc": "Sampling temperature for taxonomy extraction calls."},
    )
    ingest_worker_limit: int = field(
        default=2,
        metadata={
            "doc": "Max concurrent per-file ingest workers; 1 disables parallelism."
        },
    )
    report_worker_limit: int = field(
        default=2,
        metadata={
            "doc": "Max concurrent per-file report subtasks; 1 disables within-file parallelism."
        },
    )
    drive_supports_all_drives: bool = field(
        default=True,
        metadata={"doc": "Whether to set supportsAllDrives for Drive list calls."},
    )
    drive_include_items_from_all_drives: bool = field(
        default=True,
        metadata={"doc": "Whether to includeItemsFromAllDrives for Drive list calls."},
    )
    drive_id: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional shared Drive ID for corpora=drive scoping."},
    )
    drive_list_mode: str = field(
        default="metadata", metadata={"doc": "Drive list mode: full or metadata."}
    )
    openai_models: Dict[str, str] = field(
        default_factory=dict,
        metadata={
            "doc": "Per-namespace OpenAI model overrides keyed by namespace/prefix."
        },
    )
    llm_routing: Dict[str, Dict[str, object]] = field(
        default_factory=dict,
        metadata={
            "doc": "Per-namespace quality, token, compaction, and provider-fallback routing policies."
        },
    )
    llm_execution_policies: Dict[str, Dict[str, object]] = field(
        default_factory=dict,
        metadata={
            "doc": "Versioned namespace-aware execution controls for model calls."
        },
    )
    ingest_lock_ttl_seconds: float = field(
        default=7200.0,
        metadata={
            "doc": "Seconds before a stale ingest lock is cleared; <=0 disables stale eviction."
        },
    )
    source_quarantine_enabled: bool = field(
        default=True,
        metadata={
            "doc": (
                "Whether invalid source PDFs are quarantined before extraction "
                "or model work."
            )
        },
    )
    admission_min_text_chars: int = field(
        default=500,
        metadata={
            "doc": (
                "Minimum bounded native-text sample required before evidence generation."
            )
        },
    )
    admission_max_pages: int | None = field(
        default=250,
        metadata={
            "doc": (
                "Maximum readable source page count admitted for one report; "
                "null disables the limit."
            )
        },
    )
    admission_max_source_bytes: int | None = field(
        default=104_857_600,
        metadata={
            "doc": (
                "Maximum retained source byte size admitted for one report; "
                "null disables the limit."
            )
        },
    )
    admission_required_evidence_families: tuple[str, ...] = field(
        default=("doc_map",),
        metadata={
            "doc": (
                "Minimum configured evidence families that must have deterministic "
                "potential before admission."
            )
        },
    )
    openai_seed: Optional[int] = field(
        default=None, metadata={"doc": "Optional seed for report generation."}
    )
    pdf_text_max_pages: int = field(
        default=5, metadata={"doc": "Max pages to extract for prompt context."}
    )
    pdf_text_max_chars: int = field(
        default=80_000, metadata={"doc": "Max extracted characters for prompt context."}
    )
    pdf_text_min_density: float = field(
        default=250.0,
        metadata={"doc": "Minimum characters per page considered usable text."},
    )
    pdf_text_sample_pages: int = field(
        default=3,
        metadata={"doc": "Number of pages to sample when validating extractable text."},
    )
    pdf_text_native_confidence_threshold: float = field(
        default=0.55,
        metadata={
            "doc": "Minimum aggregated native-text confidence required to avoid OCR fallback."
        },
    )
    pdf_text_native_page_confidence_threshold: float = field(
        default=0.35,
        metadata={
            "doc": "Minimum per-page native-text confidence used to flag weak sampled pages."
        },
    )
    pdf_text_ocr_enabled: bool = field(
        default=False,
        metadata={
            "doc": "Whether OCR fallback should run when extractable text validation fails."
        },
    )
    pdf_text_ocr_policy: str = field(
        default="native_first_selective",
        metadata={"doc": "OCR fallback policy: native_first_selective or always."},
    )
    pdf_text_ocr_model: str = field(
        default="gpt-5.6-luna",
        metadata={"doc": "OpenAI model ID used for OCR fallback."},
    )
    pdf_text_ocr_timeout_seconds: float = field(
        default=600.0,
        metadata={"doc": "Timeout in seconds for the OCR fallback request."},
    )
    pdf_text_ocr_prompt_namespace: str = field(
        default="pdf_text/ocr_fallback",
        metadata={"doc": "Prompt namespace used for OCR fallback rendering."},
    )
    pdf_text_ocr_cache_enabled: bool = field(
        default=True,
        metadata={
            "doc": "Whether OCR fallback responses and rendered PDFs are cached by md5/prompt hash."
        },
    )
    pdf_text_ocr_chunk_page_count: int = field(
        default=8,
        metadata={
            "doc": "Maximum number of PDF pages submitted per OCR chunk request."
        },
    )
    rank_model: str = field(
        default="",
        metadata={"doc": "OpenAI model ID for candidate ranking (optional override)."},
    )
    rank_temperature: float = field(
        default=1.0, metadata={"doc": "Sampling temperature for candidate ranking."}
    )
    rank_seed: Optional[int] = field(
        default=None, metadata={"doc": "Optional seed for candidate ranking."}
    )
    rank_max_candidates: int = field(
        default=40,
        metadata={"doc": "Max candidates to send to the ranker after heuristics."},
    )
    rank_selected_max: int = field(
        default=5,
        metadata={
            "doc": "Maximum number of final ranked candidates to keep per kind (table and chart) for the HTML figure gallery."
        },
    )
    rank_min_overall_score: int = field(
        default=78,
        metadata={
            "doc": "Minimum overall rank score required for a candidate to pass threshold gate."
        },
    )
    rank_min_quality_score: int = field(
        default=75,
        metadata={
            "doc": "Minimum quality score required for a candidate to pass threshold gate."
        },
    )
    rank_min_insight_score: int = field(
        default=75,
        metadata={
            "doc": "Minimum insightfulness score required for a candidate to pass threshold gate."
        },
    )
    rank_min_data_score: int = field(
        default=70,
        metadata={
            "doc": "Minimum data-density score required for a candidate to pass threshold gate."
        },
    )
    candidate_page_gate_enabled: bool = field(
        default=True,
        metadata={"doc": "Whether candidate extraction uses scored page gating."},
    )
    candidate_page_gate_min_score: float = field(
        default=0.2,
        metadata={"doc": "Minimum scored page value required for direct extraction."},
    )
    candidate_page_gate_min_recall_pages: int = field(
        default=12,
        metadata={"doc": "Minimum candidate-extraction pages retained for recall."},
    )
    candidate_page_gate_min_recall_page_fraction: float = field(
        default=0.65,
        metadata={
            "doc": "Minimum requested-page fraction retained for candidate recall."
        },
    )
    crop_refine_enabled: bool = field(
        default=True,
        metadata={
            "doc": "Whether GPT-assisted crop refinement is enabled for ambiguous candidates."
        },
    )
    crop_refine_mode: str = field(
        default="adaptive",
        metadata={"doc": "Crop refinement mode: adaptive|always|off."},
    )
    crop_refine_page_dpi: int = field(
        default=110,
        metadata={
            "doc": "DPI used when rendering page context images for crop refinement."
        },
    )
    final_crop_dpi: int = field(
        default=216,
        metadata={
            "doc": (
                "DPI used when rendering final selected table/chart PNG crops for HTML."
            )
        },
    )
    crop_qa_escalation_enabled: bool = field(
        default=False,
        metadata={
            "doc": "Whether bounded model-backed QA may review borderline final crops."
        },
    )
    crop_qa_escalation_min_score: float = field(
        default=72.0,
        metadata={"doc": "Inclusive QA-score floor for crop escalation."},
    )
    crop_qa_escalation_max_score: float = field(
        default=82.0,
        metadata={"doc": "Inclusive QA-score ceiling for crop escalation."},
    )
    crop_qa_escalation_max_calls: int = field(
        default=2,
        metadata={"doc": "Maximum model-backed crop QA calls per report."},
    )
    crop_qa_escalation_max_repairs: int = field(
        default=1,
        metadata={"doc": "Maximum crop repair recommendations per report."},
    )
    crop_refine_temperature: float = field(
        default=0.0,
        metadata={"doc": "Sampling temperature for crop refinement model calls."},
    )
    crop_refine_timeout_seconds: float = field(
        default=600.0,
        metadata={"doc": "Timeout in seconds for crop refinement model calls."},
    )
    figure_caption_enabled: bool = field(
        default=False,
        metadata={
            "doc": "Whether multimodal per-image figure caption generation is enabled."
        },
    )
    figure_caption_temperature: float = field(
        default=0.2,
        metadata={"doc": "Sampling temperature for figure caption generation."},
    )
    figure_caption_timeout_seconds: float = field(
        default=600.0,
        metadata={"doc": "Timeout in seconds for figure caption model calls."},
    )
    figure_caption_prompt_namespace: str = field(
        default="report_vs/figure_caption",
        metadata={
            "doc": "Prompt namespace used for per-image figure caption generation."
        },
    )
    figure_caption_max_chars: int = field(
        default=500,
        metadata={
            "doc": "Maximum caption length, in characters including spaces, after normalization."
        },
    )
    openai_timeout_seconds: float = field(
        default=600.0,
        metadata={"doc": "Timeout in seconds for OpenAI report generation calls."},
    )
    llm_retry_retries: int = field(
        default=0,
        metadata={
            "doc": "Legacy compatibility value; LLM service retries are disabled."
        },
    )
    llm_retry_base_delay_seconds: float = field(
        default=0.0,
        metadata={
            "doc": "Legacy compatibility value; service retry delay is disabled."
        },
    )
    llm_retry_backoff_step_seconds: float = field(
        default=0.0,
        metadata={
            "doc": "Legacy compatibility value; service retry backoff is disabled."
        },
    )
    llm_retry_jitter_seconds: float = field(
        default=0.0,
        metadata={
            "doc": "Legacy compatibility value; service retry jitter is disabled."
        },
    )
    llm_circuit_breaker_failure_threshold: int = field(
        default=3,
        metadata={
            "doc": "Consecutive retryable LLM failures required to open the circuit breaker."
        },
    )
    llm_circuit_breaker_recovery_seconds: float = field(
        default=30.0,
        metadata={
            "doc": "Cooldown in seconds before the LLM circuit breaker allows a probe call."
        },
    )
    rank_timeout_seconds: float = field(
        default=600.0, metadata={"doc": "Timeout in seconds for OpenAI ranking calls."}
    )
    contents_max_pages: int = field(
        default=8,
        metadata={
            "doc": "Max pages to scan from the start for contents/index detection."
        },
    )
    contents_min_headings: int = field(
        default=3,
        metadata={
            "doc": "Minimum heading-like entries required to confirm contents/index page."
        },
    )
    contents_keywords: List[str] = field(
        default_factory=lambda: ["table of contents", "contents", "index"],
        metadata={
            "doc": "Case-insensitive keywords that indicate a contents/index page."
        },
    )
    contents_preview_enabled: bool = field(
        default=True,
        metadata={"doc": "Whether to render contents/index preview images."},
    )
    contents_preview_dpi: int = field(
        default=144,
        metadata={"doc": "Render DPI for contents/index page preview images."},
    )
    evidence_pack_parallel_workers: int = field(
        default=3,
        metadata={
            "doc": "Max parallel evidence-pack generation workers per report; 1 disables pack-level parallelism."
        },
    )
    evidence_pack_global_max_in_flight: int = field(
        default=2,
        metadata={
            "doc": "Global process-wide cap for concurrent evidence-pack model calls."
        },
    )
    evidence_pack_global_min_interval_ms: int = field(
        default=250,
        metadata={
            "doc": "Global minimum interval in milliseconds between evidence-pack model call starts."
        },
    )
    evidence_pack_doc_map_max_attempts: int = field(
        default=3,
        metadata={
            "doc": "Maximum attempts for doc_map generation before halting the pipeline."
        },
    )
    evidence_pack_doc_map_retry_delay_ms: int = field(
        default=500,
        metadata={"doc": "Delay in milliseconds between doc_map retry attempts."},
    )
    evidence_pack_registry: List[str] = field(
        default_factory=lambda: [
            "doc_map",
            "scope",
            "methods",
            "findings",
            "limitations",
            "quote_candidates",
        ],
        metadata={
            "doc": "Ordered evidence-pack registry. `doc_map` should remain first as a hard gate."
        },
    )
    evidence_pack_enable_new_variety_packs: bool = field(
        default=False,
        metadata={
            "doc": "Feature flag enabling additional evidence-pack families (key_metrics, risk_register, recommendations, contradictions)."
        },
    )
    artifact_parallel_workers: int = field(
        default=4,
        metadata={
            "doc": "Max parallel artifact generation workers per report for independent artifact steps; 1 disables step-level parallelism."
        },
    )
    artifact_global_max_in_flight: int = field(
        default=2,
        metadata={
            "doc": "Global process-wide cap for concurrent artifact model calls."
        },
    )
    artifact_global_min_interval_ms: int = field(
        default=250,
        metadata={
            "doc": "Global minimum interval in milliseconds between artifact model call starts."
        },
    )
    vector_store_keep: bool = field(
        default=True,
        metadata={"doc": "Whether to keep the vector store cache after runs."},
    )
    vector_store_retention_days: int = field(
        default=30,
        metadata={
            "doc": "Days to retain kept vector stores before retention cleanup; <=0 disables expiry cleanup."
        },
    )
    artifacts_use_vector_store: bool = field(
        default=False,
        metadata={
            "doc": "Whether artifact generation model calls should use vector store retrieval."
        },
    )
    validation_grounding_use_vector_store: bool = field(
        default=False,
        metadata={
            "doc": "Whether validation grounding model calls should use vector store retrieval."
        },
    )
    strict_schema_validation: bool = field(
        default=True,
        metadata={
            "doc": "Whether strict schema validation should be enforced for generated analysis packs."
        },
    )
    cost_ledger_path: str = field(
        default="./out/cost-ledger.jsonl",
        metadata={"doc": "Filesystem path for the cost ledger JSONL output."},
    )
    cost_daily_path: str = field(
        default="./out/cost-daily.json",
        metadata={"doc": "Filesystem path for daily cost rollups JSON."},
    )
    usage_db_path: str = field(
        default="./state/llm_usage.sqlite",
        metadata={"doc": "Canonical SQLite path for durable LLM usage events."},
    )
    run_budget_max_spend_usd: float | None = field(
        default=None,
        metadata={
            "doc": "Maximum forecasted spend in USD for one report-generation run."
        },
    )
    run_budget_max_pdfs: int | None = field(
        default=None,
        metadata={"doc": "Maximum PDFs processed by one report-generation run."},
    )
    run_budget_max_retries: int | None = field(
        default=None,
        metadata={"doc": "Maximum expensive retries for one report-generation run."},
    )
    run_budget_max_runtime_seconds: int | None = field(
        default=None,
        metadata={"doc": "Maximum elapsed report-generation runtime in seconds."},
    )
    run_budget_enabled_effect_kinds: tuple[str, ...] = field(
        default=(),
        metadata={
            "doc": "Enabled report-generation effect categories; empty means all."
        },
    )
    run_budget_limit_decision: str = field(
        default="stop",
        metadata={"doc": "Decision used when a report-generation ceiling is met."},
    )
    model_pricing: dict = field(
        default_factory=dict,
        metadata={
            "doc": "Per-model pricing table; keys are model IDs with per-1k token pricing."
        },
    )
    signal_store_db: str = field(
        default="",
        metadata={
            "doc": "SQLite path for reusable grounded Signal candidates and groups."
        },
    )
    html_tag_acronyms: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Acronyms preserved in uppercase when formatting HTML metadata chips (e.g., AI, ROI)."
        },
    )
    validation_data_gap_policy: str = field(
        default="warn",
        metadata={
            "doc": "Policy for data gaps: warn|fail controls validation severity when text evidence is missing."
        },
    )
    validation_regeneration_max_attempts: int = field(
        default=3,
        metadata={
            "doc": "Maximum validation-driven regeneration attempts after the initial validation failure."
        },
    )
    public_editorial_quality_disabled_rule_waivers: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "doc": "Explicit release-waiver reasons keyed by disabled public editorial quality rule ID."
        },
    )
    cross_report_analysis_enabled: bool = field(
        default=False,
        metadata={"doc": "Whether cross-report analysis generation is enabled."},
    )
    cross_report_analysis_max_source_reports: int = field(
        default=6,
        metadata={
            "doc": "Maximum projected reports selected for cross-report synthesis."
        },
    )
    cross_report_analysis_max_evidence_items: int = field(
        default=48,
        metadata={
            "doc": "Maximum projected evidence items included in synthesis input."
        },
    )
    cross_report_analysis_max_prompt_chars: int = field(
        default=60000,
        metadata={
            "doc": "Maximum rendered prompt/input characters before model calls."
        },
    )
    cross_report_analysis_prompt_namespace: str = field(
        default="cross_report_analysis/synthesis",
        metadata={"doc": "Prompt namespace used for cross-report synthesis."},
    )
    cross_report_analysis_model: str = field(
        default="gpt-5.6-luna",
        metadata={"doc": "Model identifier used for cross-report synthesis."},
    )
    cross_report_analysis_temperature: float = field(
        default=1.0,
        metadata={"doc": "Sampling temperature for cross-report synthesis."},
    )
    cross_report_analysis_timeout_seconds: float = field(
        default=600.0,
        metadata={"doc": "Timeout in seconds for cross-report synthesis model calls."},
    )
    cross_report_analysis_cache_enabled: bool = field(
        default=True,
        metadata={
            "doc": "Whether unchanged cross-report synthesis inputs may reuse cache."
        },
    )
    cross_report_analysis_auto_theme_enabled: bool = field(
        default=True,
        metadata={"doc": "Whether automatic deterministic theme choice is enabled."},
    )
    cross_report_analysis_theme_rotation_window_days: int = field(
        default=30,
        metadata={
            "doc": "Days of recent artifacts considered by theme variety policy."
        },
    )
    cross_report_analysis_min_theme_source_publishers: int = field(
        default=2,
        metadata={
            "doc": "Minimum distinct publishers required for publishable themes."
        },
    )
    cross_report_analysis_publish_enabled: bool = field(
        default=False,
        metadata={"doc": "Whether live cross-report publication is allowed."},
    )
    cross_report_analysis_publish_requires_validation_pass: bool = field(
        default=True,
        metadata={
            "doc": "Whether publication requires deterministic validation to pass."
        },
    )
    cross_report_analysis_signal_score_weights: dict = field(
        default_factory=lambda: {
            "contradiction": 0.5,
            "diversity": 1.0,
            "recency": 1.0,
            "recurrence": 1.0,
            "support": 1.0,
            "taxonomy_fit": 1.0,
        },
        metadata={
            "doc": "Deterministic cross-report signal score weights loaded from YAML."
        },
    )


@dataclass(frozen=True)
class IngestSettingsBuildRequest:
    schema_version: str = field(
        metadata={"doc": "Ingest settings build request schema version."}
    )
    app_settings: AppSettings = field(
        metadata={"doc": "App-level settings used to build ingest settings."}
    )


@dataclass(frozen=True)
class AppConfigReadRequest:
    schema_version: str = field(
        metadata={"doc": "App config read request schema version."}
    )
    path: str = field(
        metadata={
            "doc": "Absolute or workspace-relative config path; empty uses default app.yaml."
        }
    )


@dataclass(frozen=True)
class AppConfigReadResponse:
    schema_version: str = field(
        metadata={"doc": "App config read response schema version."}
    )
    path: str = field(metadata={"doc": "Resolved config path that was read."})
    content: str = field(metadata={"doc": "Raw YAML content."})
    payload: dict[str, Any] = field(metadata={"doc": "Decoded YAML mapping payload."})
    size_bytes: int = field(metadata={"doc": "File size in bytes."})
    modified_utc: Optional[float] = field(
        default=None, metadata={"doc": "Last-modified time in epoch seconds."}
    )


@dataclass(frozen=True)
class AppConfigWriteRequest:
    schema_version: str = field(
        metadata={"doc": "App config write request schema version."}
    )
    path: str = field(
        metadata={
            "doc": "Absolute or workspace-relative config path; empty uses default app.yaml."
        }
    )
    content: str = field(metadata={"doc": "Raw YAML content to validate and write."})
    make_backup: bool = field(
        default=True,
        metadata={"doc": "Whether to write a timestamped backup before overwriting."},
    )


@dataclass(frozen=True)
class AppConfigWriteResponse:
    schema_version: str = field(
        metadata={"doc": "App config write response schema version."}
    )
    path: str = field(metadata={"doc": "Resolved config path that was written."})
    bytes_written: int = field(metadata={"doc": "Number of bytes written to disk."})
    modified_utc: Optional[float] = field(
        default=None, metadata={"doc": "Last-modified time in epoch seconds."}
    )
    top_level_keys: list[str] = field(
        default_factory=list,
        metadata={"doc": "Top-level YAML keys discovered during validation."},
    )
    backup_path: Optional[str] = field(
        default=None, metadata={"doc": "Backup file path when backup was created."}
    )
