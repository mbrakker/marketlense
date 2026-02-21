from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.contracts.docpacks import DocPackPathMap


@dataclass(frozen=True)
class IngestSettings:
    schema_version: str = field(metadata={"doc": "Settings schema version."})
    google_sa_path: str = field(
        metadata={"doc": "Filesystem path to the Google service account JSON."}
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
    ingest_lock_ttl_seconds: float = field(
        default=7200.0,
        metadata={
            "doc": "Seconds before a stale ingest lock is cleared; <=0 disables stale eviction."
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
            "doc": "Maximum number of final ranked candidates to include in HTML figure gallery."
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
    crop_refine_temperature: float = field(
        default=0.0,
        metadata={"doc": "Sampling temperature for crop refinement model calls."},
    )
    crop_refine_timeout_seconds: float = field(
        default=600.0,
        metadata={"doc": "Timeout in seconds for crop refinement model calls."},
    )
    openai_timeout_seconds: float = field(
        default=600.0,
        metadata={"doc": "Timeout in seconds for OpenAI report generation calls."},
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
    analysis_mode: str = field(
        default="vector_store", metadata={"doc": "Analysis mode to use (vector_store)."}
    )
    use_vector_store: bool = field(
        default=True,
        metadata={
            "doc": "Always true; vector_store is the only supported analysis path."
        },
    )
    vector_store_keep: bool = field(
        default=True,
        metadata={"doc": "Whether to keep the vector store cache after runs."},
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
    cover_cache_enabled: bool = field(
        default=True,
        metadata={
            "doc": "Whether to skip cover generation when cached output is up-to-date."
        },
    )
    cost_ledger_path: str = field(
        default="./out/cost-ledger.jsonl",
        metadata={"doc": "Filesystem path for cost ledger JSONL output."},
    )
    cost_daily_path: str = field(
        default="./out/cost-daily.json",
        metadata={"doc": "Filesystem path for daily cost rollup JSON."},
    )
    model_pricing: dict = field(
        default_factory=dict,
        metadata={
            "doc": "Per-model pricing table; keys are model IDs with per-1k token pricing."
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
    quality_baseline_path: str = field(
        default="./docs/quality/baseline_2026-02-21.json",
        metadata={
            "doc": "Path to non-regression quality baseline snapshot used by CI checks."
        },
    )


@dataclass(frozen=True)
class IngestOutcome:
    schema_version: str = field(metadata={"doc": "Outcome schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    name: str = field(metadata={"doc": "Drive file name."})
    md5: Optional[str] = field(
        metadata={"doc": "MD5 checksum of the cached PDF, if available."}
    )
    html_path: Optional[str] = field(
        metadata={"doc": "Rendered HTML path, if produced."}
    )
    status: str = field(metadata={"doc": "Outcome status: processed|skipped|error."})
    error: Optional[str] = field(
        default=None,
        metadata={"doc": "Error code/message when status=error or skipped."},
    )
    vector_store_id: Optional[str] = field(
        default=None, metadata={"doc": "Vector store ID used for this file, if any."}
    )
    vector_store_status: Optional[str] = field(
        default=None, metadata={"doc": "Vector store status after processing, if any."}
    )
    indexed_at_utc: Optional[str] = field(
        default=None,
        metadata={
            "doc": "UTC timestamp when vector store indexing completed, if known."
        },
    )
    openai_file_id: Optional[str] = field(
        default=None,
        metadata={"doc": "OpenAI file ID uploaded to the vector store, if any."},
    )
    evidence_packs: Optional[DocPackPathMap] = field(
        default=None,
        metadata={
            "doc": "Mapping of evidence-pack names to stored artifact paths, if generated."
        },
    )
    vector_store_last_error: Optional[str] = field(
        default=None, metadata={"doc": "Last vector store error, if any."}
    )
    text_validation_status: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Extractable text validation status: pass|fail, if evaluated."
        },
    )
    text_validation_reason: Optional[str] = field(
        default=None,
        metadata={"doc": "Extractable text validation failure reason, if any."},
    )
    text_validation_pages: Optional[List[int]] = field(
        default=None,
        metadata={"doc": "Page numbers sampled for extractable text validation."},
    )
    doc_map_summary: Optional[Dict[str, object]] = field(
        default=None,
        metadata={
            "doc": "DocMap validation summary when doc_map is empty, if available."
        },
    )
