from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.contracts.ingest import IngestSettings


@dataclass(frozen=True)
class ConfigLoadRequest:
    schema_version: str = field(metadata={"doc": "Config request schema version."})
    path: str = field(metadata={"doc": "Absolute or workspace-relative path to the YAML config file."})


@dataclass(frozen=True)
class AppSettings:
    schema_version: str = field(metadata={"doc": "Settings schema version."})
    google_sa_path: str = field(metadata={"doc": "Filesystem path to the Google service account JSON."})
    gdrive_folder_id: str = field(metadata={"doc": "Google Drive folder ID containing source PDFs."})
    openai_api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    openai_model: str = field(metadata={"doc": "OpenAI model ID for report generation."})
    batch_limit: int = field(metadata={"doc": "Max PDFs to process per ingest run."})
    output_dir: str = field(metadata={"doc": "Output directory for rendered HTML and assets."})
    cache_dir: str = field(metadata={"doc": "Cache directory for downloaded PDFs."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    reports_db: str = field(metadata={"doc": "SQLite path for report metadata."})
    category_mapping_path: str = field(metadata={"doc": "Filesystem path to category mappings YAML."})
    cover_style_path: str = field(metadata={"doc": "Filesystem path to cover style YAML."})
    ingest_lock_path: str = field(metadata={"doc": "Filesystem path for the ingest single-run lock file."})
    temperature: float = field(metadata={"doc": "Sampling temperature for report generation."})
    ingest_worker_limit: int = field(default=2, metadata={"doc": "Max concurrent per-file ingest workers; 1 disables parallelism."})
    report_worker_limit: int = field(default=2, metadata={"doc": "Max concurrent per-file report subtasks; 1 disables within-file parallelism."})
    drive_supports_all_drives: bool = field(default=True, metadata={"doc": "Whether to set supportsAllDrives for Drive list calls."})
    drive_include_items_from_all_drives: bool = field(default=True, metadata={"doc": "Whether to includeItemsFromAllDrives for Drive list calls."})
    drive_id: Optional[str] = field(default=None, metadata={"doc": "Optional shared Drive ID for corpora=drive scoping."})
    drive_list_mode: str = field(default="metadata", metadata={"doc": "Drive list mode: full or metadata."})
    openai_models: Dict[str, str] = field(default_factory=dict, metadata={"doc": "Per-namespace OpenAI model overrides keyed by namespace/prefix."})
    ingest_lock_ttl_seconds: float = field(default=7200.0, metadata={"doc": "Seconds before a stale ingest lock is cleared; <=0 disables stale eviction."})
    openai_seed: Optional[int] = field(default=None, metadata={"doc": "Optional seed for report generation."})
    pdf_text_max_pages: int = field(default=5, metadata={"doc": "Max pages to extract for prompt context."})
    pdf_text_max_chars: int = field(default=80_000, metadata={"doc": "Max extracted characters for prompt context."})
    pdf_text_min_density: float = field(default=250.0, metadata={"doc": "Minimum characters per page considered usable text."})
    pdf_text_sample_pages: int = field(default=3, metadata={"doc": "Number of pages to sample when validating extractable text."})
    debug_candidate_gallery: bool = field(default=False, metadata={"doc": "Whether to render the full candidate gallery crop set."})
    rank_model: str = field(default="", metadata={"doc": "OpenAI model ID for candidate ranking (optional override)."})
    rank_temperature: float = field(default=1.0, metadata={"doc": "Sampling temperature for candidate ranking."})
    rank_seed: Optional[int] = field(default=None, metadata={"doc": "Optional seed for candidate ranking."})
    rank_max_candidates: int = field(default=40, metadata={"doc": "Max candidates to send to the ranker after heuristics."})
    openai_timeout_seconds: float = field(default=600.0, metadata={"doc": "Timeout in seconds for OpenAI report generation calls."})
    rank_timeout_seconds: float = field(default=600.0, metadata={"doc": "Timeout in seconds for OpenAI ranking calls."})
    contents_max_pages: int = field(default=8, metadata={"doc": "Max pages to scan from the start for contents/index detection."})
    contents_min_headings: int = field(default=3, metadata={"doc": "Minimum heading-like entries required to confirm contents/index page."})
    contents_keywords: List[str] = field(
        default_factory=lambda: ["table of contents", "contents", "index"],
        metadata={"doc": "Case-insensitive keywords that indicate a contents/index page."},
    )
    contents_preview_enabled: bool = field(default=True, metadata={"doc": "Whether to render contents/index preview images."})
    contents_preview_dpi: int = field(default=144, metadata={"doc": "Render DPI for contents/index page preview images."})
    evidence_pack_parallel_workers: int = field(default=3, metadata={"doc": "Max parallel evidence-pack generation workers per report; 1 disables pack-level parallelism."})
    evidence_pack_global_max_in_flight: int = field(default=2, metadata={"doc": "Global process-wide cap for concurrent evidence-pack model calls."})
    evidence_pack_global_min_interval_ms: int = field(default=250, metadata={"doc": "Global minimum interval in milliseconds between evidence-pack model call starts."})
    analysis_mode: str = field(default="vector_store", metadata={"doc": "Analysis mode to use: vector_store (default)."})
    use_vector_store: bool = field(default=True, metadata={"doc": "Always true; vector_store is the only supported analysis path."})
    vector_store_keep: bool = field(default=True, metadata={"doc": "Whether to keep the vector store cache after runs."})
    mirror_legacy_packs: bool = field(default=True, metadata={"doc": "Whether to mirror analysis packs to the legacy output layout."})
    cover_cache_enabled: bool = field(default=True, metadata={"doc": "Whether to skip cover generation when cached output is up-to-date."})
    cost_ledger_path: str = field(default="./out/cost-ledger.jsonl", metadata={"doc": "Filesystem path for the cost ledger JSONL output."})
    cost_daily_path: str = field(default="./out/cost-daily.json", metadata={"doc": "Filesystem path for daily cost rollups JSON."})
    model_pricing: dict = field(default_factory=dict, metadata={"doc": "Per-model pricing table; keys are model IDs with per-1k token pricing."})
    analysis_compare: bool = field(default=False, metadata={"doc": "Legacy compare toggle (ignored; vector_store only)."})
    validation_data_gap_policy: str = field(default="warn", metadata={"doc": "Policy for data gaps: warn|fail controls validation severity when text evidence is missing."})


@dataclass(frozen=True)
class IngestSettingsBuildRequest:
    schema_version: str = field(metadata={"doc": "Ingest settings build request schema version."})
    app_settings: AppSettings = field(metadata={"doc": "App-level settings used to build ingest settings."})
