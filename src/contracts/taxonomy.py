from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.config import AppSettings


@dataclass(frozen=True)
class TaxonomyExtractRequest:
    schema_version: str = field(metadata={"doc": "Taxonomy extraction request schema version."})
    report_id: str = field(metadata={"doc": "Report identifier used for logging and storage."})
    report_title: str = field(metadata={"doc": "Human-friendly report title for prompt context."})
    vector_store_id: str = field(metadata={"doc": "Vector store identifier to query for taxonomy extraction."})
    settings: AppSettings = field(metadata={"doc": "Resolved application settings for model configuration."})
    prompt_namespace: str = field(default="report_vs/taxonomy", metadata={"doc": "Prompt namespace for taxonomy extraction."})
    md5: Optional[str] = field(default=None, metadata={"doc": "Report source MD5 used for taxonomy cache keys."})
    report_slug: Optional[str] = field(default=None, metadata={"doc": "Report slug used to resolve taxonomy cache path."})


@dataclass(frozen=True)
class TaxonomyExtractResponse:
    schema_version: str = field(metadata={"doc": "Taxonomy extraction response schema version."})
    taxonomy: List[str] = field(metadata={"doc": "Extracted taxonomy tags for the report."})
    region: str = field(metadata={"doc": "Primary region/market focus for the report."})
    time_period: str = field(metadata={"doc": "Primary time period covered by the report."})
    not_found_reason: Optional[str] = field(default=None, metadata={"doc": "Reason for fallback output, if any."})
