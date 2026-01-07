from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


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
    ingest_lock_path: str = field(metadata={"doc": "Filesystem path for the ingest single-run lock file."})
    temperature: float = field(metadata={"doc": "Sampling temperature for report generation."})
    ingest_lock_ttl_seconds: float = field(default=7200.0, metadata={"doc": "Seconds before a stale ingest lock is cleared; <=0 disables stale eviction."})
    openai_seed: Optional[int] = field(default=None, metadata={"doc": "Optional seed for report generation."})
    pdf_text_max_pages: int = field(default=5, metadata={"doc": "Max pages to extract for prompt context."})
    pdf_text_max_chars: int = field(default=80_000, metadata={"doc": "Max extracted characters for prompt context."})
    rank_model: str = field(default="", metadata={"doc": "OpenAI model ID for candidate ranking (optional override)."})
    rank_temperature: float = field(default=1.0, metadata={"doc": "Sampling temperature for candidate ranking."})
    rank_seed: Optional[int] = field(default=None, metadata={"doc": "Optional seed for candidate ranking."})
    openai_timeout_seconds: float = field(default=600.0, metadata={"doc": "Timeout in seconds for OpenAI report generation calls."})
    rank_timeout_seconds: float = field(default=600.0, metadata={"doc": "Timeout in seconds for OpenAI ranking calls."})
    contents_max_pages: int = field(default=8, metadata={"doc": "Max pages to scan from the start for contents/index detection."})
    contents_min_headings: int = field(default=3, metadata={"doc": "Minimum heading-like entries required to confirm contents/index page."})
    contents_keywords: List[str] = field(
        default_factory=lambda: ["table of contents", "contents", "index"],
        metadata={"doc": "Case-insensitive keywords that indicate a contents/index page."},
    )
    contents_preview_dpi: int = field(default=144, metadata={"doc": "Render DPI for contents/index page preview images."})
