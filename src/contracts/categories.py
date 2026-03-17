from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.config import AppSettings


@dataclass(frozen=True)
class CategoryClassificationConfig:
    schema_version: str = field(
        default="1.1",
        metadata={"doc": "Category-classification config schema version."},
    )
    max_categories: int = field(
        default=2,
        metadata={"doc": "Maximum number of portal categories to assign."},
    )
    min_primary_score: float = field(
        default=2.2,
        metadata={"doc": "Minimum score required for a primary category."},
    )
    min_secondary_score: float = field(
        default=1.6,
        metadata={"doc": "Minimum score required for a secondary category."},
    )
    secondary_score_ratio: float = field(
        default=0.7,
        metadata={
            "doc": "Minimum ratio between secondary and primary category score."
        },
    )
    secondary_rescue_score_ratio: float = field(
        default=0.55,
        metadata={
            "doc": "Lower secondary-to-primary score ratio allowed when evidence-backed rescue is satisfied."
        },
    )
    secondary_rescue_min_strong_matches: int = field(
        default=2,
        metadata={
            "doc": "Minimum distinct strong matches required for evidence-backed secondary rescue."
        },
    )
    secondary_rescue_min_evidence_tags: int = field(
        default=2,
        metadata={
            "doc": "Minimum distinct evidence-backed tags required for secondary rescue."
        },
    )
    secondary_rescue_min_evidence_sections: int = field(
        default=2,
        metadata={
            "doc": "Minimum distinct supporting sections required for secondary rescue."
        },
    )
    core_tag_weight: float = field(
        default=2.2,
        metadata={"doc": "Weight applied to category core tags."},
    )
    supporting_tag_weight: float = field(
        default=1.2,
        metadata={"doc": "Weight applied to category supporting tags."},
    )
    legacy_tag_weight: float = field(
        default=1.0,
        metadata={"doc": "Weight applied to legacy category tags."},
    )
    generic_tag_weight: float = field(
        default=0.3,
        metadata={"doc": "Weight applied to generic cross-cutting tags."},
    )
    negative_tag_weight: float = field(
        default=-2.0,
        metadata={"doc": "Penalty applied to explicit negative tags."},
    )
    repeated_match_bonus: float = field(
        default=0.25,
        metadata={"doc": "Bonus applied for multiple distinct strong matches."},
    )
    global_generic_tags: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Cross-cutting tags that should be downweighted globally."
        },
    )


@dataclass(frozen=True)
class CategoryDefinition:
    id: str = field(metadata={"doc": "Canonical category identifier (snake_case)."})
    label: str = field(metadata={"doc": "Human-readable category label."})
    description: str = field(metadata={"doc": "Category description."})
    definition: str = field(
        default="",
        metadata={
            "doc": "Context-first classifier definition describing the category's true central subject."
        },
    )
    include_when: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Evidence-based guidance for when a report should fit this category."
        },
    )
    exclude_when: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Evidence-based guidance for when a report should not fit this category."
        },
    )
    tags: List[str] = field(
        default_factory=list,
        metadata={"doc": "Legacy tags/keywords that map to this category."}
    )
    core_tags: List[str] = field(
        default_factory=list,
        metadata={"doc": "High-signal tags that strongly indicate this category."},
    )
    supporting_tags: List[str] = field(
        default_factory=list,
        metadata={"doc": "Supporting tags that indicate this category."},
    )
    secondary_supporting_tags: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Supporting tags that are especially relevant when this category is a valid secondary theme."
        },
    )
    descriptor_tags: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Broad descriptor tags that may be extracted for report metadata but must not influence portal-category scoring."
        },
    )
    generic_tags: List[str] = field(
        default_factory=list,
        metadata={"doc": "Broad tags that weakly indicate this category."},
    )
    negative_tags: List[str] = field(
        default_factory=list,
        metadata={"doc": "Tags that should penalize this category when present."},
    )
    must_have_one_of: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "When set, at least one of these tags must match before the category can be rescued as secondary."
        },
    )
    priority: int = field(
        default=0,
        metadata={"doc": "Tie-break priority; higher values win ties."},
    )
    portal_exposed: bool = field(
        default=True,
        metadata={"doc": "Whether this category can be returned to portal surfaces."},
    )
    schema_version: str = field(
        default="1.2", metadata={"doc": "Category definition schema version."}
    )


@dataclass(frozen=True)
class UncategorizedTagsEntry:
    title: str = field(metadata={"doc": "Report title for uncategorized tags."})
    tags: List[str] = field(
        metadata={"doc": "List of tags that were not mapped for this report."}
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Uncategorized-tags entry schema version."}
    )


@dataclass(frozen=True)
class TaxonomyInferenceRule:
    name: str = field(metadata={"doc": "Stable name for the taxonomy inference rule."})
    target_category_id: str = field(
        default="",
        metadata={
            "doc": "Category whose scoring this inference rule is intended to strengthen."
        },
    )
    trigger_tags: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Extracted tags whose evidence can trigger this inference rule."
        },
    )
    inferred_tag: str = field(
        default="",
        metadata={"doc": "Tag to inject when the rule matches."},
    )
    inferred_tier: str = field(
        default="secondary",
        metadata={"doc": "Tier assigned to the inferred tag: primary or secondary."},
    )
    context_keywords_any: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Normalized context words/phrases; at least one must appear in evidence when provided."
        },
    )
    remove_tags: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Tags to remove from primary/secondary outputs when this rule fires."
        },
    )
    schema_version: str = field(
        default="1.1", metadata={"doc": "Taxonomy inference-rule schema version."}
    )


@dataclass(frozen=True)
class CategoryMappings:
    schema_version: str = field(metadata={"doc": "Category mappings schema version."})
    categories: List[CategoryDefinition] = field(
        metadata={"doc": "List of category definitions."}
    )
    classification: CategoryClassificationConfig = field(
        default_factory=CategoryClassificationConfig,
        metadata={"doc": "Scoring and threshold rules for category assignment."},
    )
    inference_rules: List[TaxonomyInferenceRule] = field(
        default_factory=list,
        metadata={"doc": "Config-driven taxonomy post-processing inference rules."},
    )
    uncategorized: List[UncategorizedTagsEntry] = field(
        default_factory=list, metadata={"doc": "Unmapped tag records."}
    )


@dataclass(frozen=True)
class CategoryMappingLoadRequest:
    schema_version: str = field(
        metadata={"doc": "Category mapping load request schema version."}
    )
    path: str = field(
        metadata={"doc": "Filesystem path to the category mappings YAML."}
    )
    reload_if_changed: bool = field(
        default=False,
        metadata={"doc": "Reload mapping file if the on-disk copy changed."},
    )
    force_reload: bool = field(
        default=False, metadata={"doc": "Bypass cache and reload mappings from disk."}
    )


@dataclass(frozen=True)
class CategoryMappingLoadResponse:
    schema_version: str = field(
        metadata={"doc": "Category mapping load response schema version."}
    )
    mappings: CategoryMappings = field(metadata={"doc": "Loaded category mappings."})


@dataclass(frozen=True)
class UncategorizedTagsUpdateRequest:
    schema_version: str = field(
        metadata={"doc": "Uncategorized tag update request schema version."}
    )
    path: str = field(
        metadata={"doc": "Filesystem path to the category mappings YAML."}
    )
    report_title: str = field(
        metadata={"doc": "Report title for the uncategorized record."}
    )
    tags: List[str] = field(
        metadata={"doc": "Tags that were not mapped for this report."}
    )


@dataclass(frozen=True)
class UncategorizedTagsFlushRequest:
    schema_version: str = field(
        metadata={"doc": "Uncategorized tag flush request schema version."}
    )
    path: str = field(
        metadata={"doc": "Filesystem path to the category mappings YAML."}
    )


@dataclass(frozen=True)
class CategoryScoreDetail:
    category_id: str = field(metadata={"doc": "Canonical category identifier."})
    label: str = field(metadata={"doc": "Human-readable category label."})
    score: float = field(metadata={"doc": "Final weighted score for the category."})
    matched_tags: List[str] = field(
        default_factory=list,
        metadata={"doc": "Matched taxonomy tags that contributed to the score."},
    )
    strong_match_count: int = field(
        default=0,
        metadata={"doc": "Count of distinct non-generic positive matches."},
    )
    generic_match_count: int = field(
        default=0,
        metadata={"doc": "Count of distinct generic matches."},
    )
    evidence_tag_count: int = field(
        default=0,
        metadata={"doc": "Count of distinct strong matched tags that carry evidence support."},
    )
    evidence_section_count: int = field(
        default=0,
        metadata={"doc": "Count of distinct report sections supporting matched tags."},
    )
    secondary_tier_match_count: int = field(
        default=0,
        metadata={"doc": "Count of matched tags that the extractor labeled as secondary."},
    )
    must_have_match_count: int = field(
        default=0,
        metadata={"doc": "Count of matched must-have rescue tags."},
    )
    secondary_rescue_eligible: bool = field(
        default=False,
        metadata={"doc": "Whether this category qualifies for evidence-backed secondary rescue."},
    )
    eligible: bool = field(
        default=False,
        metadata={"doc": "Whether the category cleared assignment thresholds."},
    )
    skip_reason: str = field(
        default="",
        metadata={"doc": "Reason the category was not eligible, if any."},
    )
    schema_version: str = field(
        default="1.1", metadata={"doc": "Category score detail schema version."}
    )


@dataclass(frozen=True)
class CategoryAssignment:
    schema_version: str = field(metadata={"doc": "Category assignment schema version."})
    categories: List[str] = field(
        metadata={"doc": "Assigned portal category IDs after category selection."}
    )
    category_labels: List[str] = field(
        metadata={"doc": "Human-readable category labels aligned with categories."}
    )
    unmapped_tags: List[str] = field(
        metadata={"doc": "Tags that did not map to any category."}
    )
    score_details: List[CategoryScoreDetail] = field(
        default_factory=list,
        metadata={"doc": "Ranked category scoring details for audit/debug flows."},
    )


@dataclass(frozen=True)
class RecategorizeOutcome:
    schema_version: str = field(
        metadata={"doc": "Recategorization outcome schema version."}
    )
    file_id: str = field(metadata={"doc": "Drive file ID."})
    title: str = field(metadata={"doc": "Report title."})
    categories: List[str] = field(metadata={"doc": "Assigned category IDs."})
    unmapped_tags: List[str] = field(metadata={"doc": "Tags that remained unmapped."})
    status: str = field(metadata={"doc": "Outcome status: updated|skipped|error."})
    error: Optional[str] = field(
        default=None, metadata={"doc": "Error message if status=error."}
    )


@dataclass(frozen=True)
class RecategorizeRequest:
    schema_version: str = field(
        metadata={"doc": "Recategorization request schema version."}
    )
    db_path: str = field(metadata={"doc": "Reports metadata SQLite path."})
    category_mapping_path: str = field(
        metadata={"doc": "Filesystem path to category mappings YAML."}
    )
    settings: AppSettings = field(
        metadata={
            "doc": "Resolved application settings used for context-first category fitting."
        }
    )


@dataclass(frozen=True)
class WordPressCategoryUpdateOutcome:
    schema_version: str = field(
        metadata={"doc": "WordPress category update outcome schema version."}
    )
    file_id: str = field(metadata={"doc": "Drive file ID."})
    status: str = field(metadata={"doc": "Outcome status: updated|skipped|error."})
    categories: List[str] = field(
        default_factory=list, metadata={"doc": "Category IDs pushed to WordPress."}
    )
    post_id: Optional[int] = field(
        default=None, metadata={"doc": "WordPress post ID if known."}
    )
    error: Optional[str] = field(
        default=None, metadata={"doc": "Error message if status=error."}
    )
