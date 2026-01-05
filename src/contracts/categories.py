from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class CategoryDefinition:
    id: str = field(metadata={"doc": "Canonical category identifier (snake_case)."})
    label: str = field(metadata={"doc": "Human-readable category label."})
    description: str = field(metadata={"doc": "Category description."})
    tags: List[str] = field(metadata={"doc": "Tags/keywords that map to this category."})


@dataclass(frozen=True)
class UncategorizedTagsEntry:
    title: str = field(metadata={"doc": "Report title for uncategorized tags."})
    tags: List[str] = field(metadata={"doc": "List of tags that were not mapped for this report."})


@dataclass(frozen=True)
class CategoryMappings:
    schema_version: str = field(metadata={"doc": "Category mappings schema version."})
    categories: List[CategoryDefinition] = field(metadata={"doc": "List of category definitions."})
    uncategorized: List[UncategorizedTagsEntry] = field(default_factory=list, metadata={"doc": "Unmapped tag records."})


@dataclass(frozen=True)
class CategoryMappingLoadRequest:
    schema_version: str = field(metadata={"doc": "Category mapping load request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the category mappings YAML."})
    reload_if_changed: bool = field(default=False, metadata={"doc": "Reload mapping file if the on-disk copy changed."})
    force_reload: bool = field(default=False, metadata={"doc": "Bypass cache and reload mappings from disk."})


@dataclass(frozen=True)
class CategoryMappingLoadResponse:
    schema_version: str = field(metadata={"doc": "Category mapping load response schema version."})
    mappings: CategoryMappings = field(metadata={"doc": "Loaded category mappings."})


@dataclass(frozen=True)
class UncategorizedTagsUpdateRequest:
    schema_version: str = field(metadata={"doc": "Uncategorized tag update request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the category mappings YAML."})
    report_title: str = field(metadata={"doc": "Report title for the uncategorized record."})
    tags: List[str] = field(metadata={"doc": "Tags that were not mapped for this report."})


@dataclass(frozen=True)
class UncategorizedTagsFlushRequest:
    schema_version: str = field(metadata={"doc": "Uncategorized tag flush request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the category mappings YAML."})


@dataclass(frozen=True)
class CategoryAssignment:
    schema_version: str = field(metadata={"doc": "Category assignment schema version."})
    categories: List[str] = field(metadata={"doc": "Top category IDs (max 3)."})
    category_labels: List[str] = field(metadata={"doc": "Human-readable category labels aligned with categories."})
    unmapped_tags: List[str] = field(metadata={"doc": "Tags that did not map to any category."})


@dataclass(frozen=True)
class RecategorizeOutcome:
    schema_version: str = field(metadata={"doc": "Recategorization outcome schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    title: str = field(metadata={"doc": "Report title."})
    categories: List[str] = field(metadata={"doc": "Assigned category IDs."})
    unmapped_tags: List[str] = field(metadata={"doc": "Tags that remained unmapped."})
    status: str = field(metadata={"doc": "Outcome status: updated|skipped|error."})
    error: Optional[str] = field(default=None, metadata={"doc": "Error message if status=error."})


@dataclass(frozen=True)
class RecategorizeRequest:
    schema_version: str = field(metadata={"doc": "Recategorization request schema version."})
    db_path: str = field(metadata={"doc": "Reports metadata SQLite path."})
    category_mapping_path: str = field(metadata={"doc": "Filesystem path to category mappings YAML."})


@dataclass(frozen=True)
class WordPressCategoryUpdateOutcome:
    schema_version: str = field(metadata={"doc": "WordPress category update outcome schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    status: str = field(metadata={"doc": "Outcome status: updated|skipped|error."})
    categories: List[str] = field(default_factory=list, metadata={"doc": "Category IDs pushed to WordPress."})
    post_id: Optional[int] = field(default=None, metadata={"doc": "WordPress post ID if known."})
    error: Optional[str] = field(default=None, metadata={"doc": "Error message if status=error."})
