from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.config import AppSettings
from src.contracts.ingest import IngestSettings
from src.contracts.semantic_ids import ReportId, SemanticIdContract


@dataclass(frozen=True)
class TaxonomyExtractRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Taxonomy extraction request schema version."}
    )
    report_id: ReportId = field(
        metadata={"doc": "Report identifier used for logging and storage."}
    )
    report_title: str = field(
        metadata={"doc": "Human-friendly report title for prompt context."}
    )
    vector_store_id: str = field(
        metadata={"doc": "Vector store identifier to query for taxonomy extraction."}
    )
    settings: AppSettings | IngestSettings = field(
        metadata={"doc": "Resolved application settings for model configuration."}
    )
    prompt_namespace: str = field(
        default="report_vs/taxonomy",
        metadata={"doc": "Prompt namespace for taxonomy extraction."},
    )
    md5: Optional[str] = field(
        default=None,
        metadata={"doc": "Report source MD5 used for taxonomy cache keys."},
    )
    report_slug: Optional[str] = field(
        default=None,
        metadata={"doc": "Report slug used to resolve taxonomy cache path."},
    )
    publisher_name: str = field(
        default="",
        metadata={"doc": "Publisher context recorded with downstream LLM usage."},
    )
    source_url: str = field(
        default="",
        metadata={"doc": "Source/report URL context recorded with downstream LLM usage."},
    )


@dataclass(frozen=True)
class TaxonomyTagEvidence:
    tag: str = field(
        metadata={"doc": "Extracted taxonomy tag supported by this evidence item."}
    )
    tier: str = field(
        default="primary",
        metadata={"doc": "Tag tier: primary or secondary."},
    )
    section_label: str = field(
        default="",
        metadata={"doc": "Section or chapter label that supports the tag."},
    )
    evidence: str = field(
        default="",
        metadata={"doc": "Short evidence snippet or justification for the tag."},
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Taxonomy tag-evidence schema version."}
    )


@dataclass(frozen=True)
class TaxonomyExtractResponse:
    schema_version: str = field(
        metadata={"doc": "Taxonomy extraction response schema version."}
    )
    taxonomy: List[str] = field(
        metadata={"doc": "Extracted taxonomy tags for the report."}
    )
    region: str = field(metadata={"doc": "Primary region/market focus for the report."})
    time_period: str = field(
        metadata={"doc": "Primary time period covered by the report."}
    )
    primary_tags: List[str] = field(
        default_factory=list,
        metadata={"doc": "Most central report tags that define the primary subject."},
    )
    secondary_tags: List[str] = field(
        default_factory=list,
        metadata={"doc": "Secondary report tags that are material but not dominant."},
    )
    tag_evidence: List[TaxonomyTagEvidence] = field(
        default_factory=list,
        metadata={
            "doc": "Per-tag evidence items used to support tiered categorization."
        },
    )
    not_found_reason: Optional[str] = field(
        default=None, metadata={"doc": "Reason for fallback output, if any."}
    )
