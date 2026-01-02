from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import yaml

from src.contracts.categories import (
    CategoryDefinition,
    CategoryMappingLoadRequest,
    CategoryMappingLoadResponse,
    CategoryMappings,
    UncategorizedTagsEntry,
    UncategorizedTagsUpdateRequest,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.category_mapping_service")

DEFAULT_MAPPING_PATH = Path(__file__).resolve().parents[1] / "config" / "category-mappings.yaml"


def _clean_tags(tags: List[str]) -> List[str]:
    cleaned = []
    seen = set()
    for t in tags or []:
        t_s = str(t).strip()
        if not t_s:
            continue
        norm = _norm_tag(t_s)
        if norm in seen:
            continue
        seen.add(norm)
        cleaned.append(t_s)
    return cleaned


def _norm_tag(tag: str) -> str:
    return tag.strip().lower().replace(" ", "_")


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise AppError(
            code="category_mapping_missing",
            message=f"Category mapping file not found: {path}",
            retryable=False,
            severity="error",
            context={"path": str(path)},
        )
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise AppError(
            code="category_mapping_invalid_yaml",
            message=f"Category mapping YAML invalid: {path}",
            cause=exc,
            retryable=False,
            severity="error",
            context={"path": str(path)},
        ) from exc


def load_mappings(request: CategoryMappingLoadRequest, ctx: RunContext) -> CategoryMappingLoadResponse:
    path = Path(request.path or DEFAULT_MAPPING_PATH)
    logger.info(log_event(
        ctx,
        role="service",
        event="category_mapping_load_start",
        module=logger.name,
        fields={"path": str(path)},
    ))
    data = _load_yaml(path)
    categories_raw = data.get("categories") or []
    categories: List[CategoryDefinition] = []
    for item in categories_raw:
        if not isinstance(item, dict):
            continue
        tags = _clean_tags(item.get("tags") or [])
        categories.append(CategoryDefinition(
            id=str(item.get("id") or "").strip(),
            label=str(item.get("label") or "").strip(),
            description=str(item.get("description") or "").strip(),
            tags=tags,
        ))
    uncategorized_raw = data.get("uncategorized") or []
    uncategorized: List[UncategorizedTagsEntry] = []
    for item in uncategorized_raw:
        if not isinstance(item, dict):
            continue
        uncategorized.append(UncategorizedTagsEntry(
            title=str(item.get("title") or "").strip(),
            tags=_clean_tags(item.get("tags") or []),
        ))
    mappings = CategoryMappings(
        schema_version=str(data.get("schema_version", "1.0")),
        categories=categories,
        uncategorized=uncategorized,
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="category_mapping_load_complete",
        module=logger.name,
        fields={
            "path": str(path),
            "categories": len(categories),
            "uncategorized": len(uncategorized),
        },
    ))
    return CategoryMappingLoadResponse(schema_version="1.0", mappings=mappings)


def update_uncategorized_tags(request: UncategorizedTagsUpdateRequest, ctx: RunContext) -> None:
    path = Path(request.path or DEFAULT_MAPPING_PATH)
    logger.info(log_event(
        ctx,
        role="service",
        event="category_uncategorized_update_start",
        module=logger.name,
        fields={"path": str(path), "title": request.report_title, "tag_count": len(request.tags)},
    ))
    data = _load_yaml(path)
    categories = data.get("categories") or []
    known_tags = {_norm_tag(t) for item in categories for t in (item.get("tags") or [])}

    # Remove already-mapped tags from existing uncategorized entries.
    uncategorized_raw = data.get("uncategorized") or []
    cleaned_uncategorized = []
    for entry in uncategorized_raw:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        tags = []
        seen = set()
        for t in entry.get("tags") or []:
            t_s = str(t).strip()
            norm = _norm_tag(t_s)
            if not t_s or norm in known_tags or norm in seen:
                continue
            seen.add(norm)
            tags.append(t_s)
        if tags:
            cleaned_uncategorized.append({"title": title, "tags": tags})

    # Add new unmapped tags for this report.
    new_tags = []
    seen_new = set()
    for t in request.tags or []:
        t_s = str(t).strip()
        norm = _norm_tag(t_s)
        if not t_s or norm in known_tags or norm in seen_new:
            continue
        seen_new.add(norm)
        new_tags.append(t_s)

    if new_tags:
        merged = False
        for entry in cleaned_uncategorized:
            if entry.get("title") == request.report_title:
                entry["tags"].extend([tag for tag in new_tags if _norm_tag(tag) not in {_norm_tag(t) for t in entry["tags"]}])
                merged = True
                break
        if not merged:
            cleaned_uncategorized.append({"title": request.report_title, "tags": new_tags})

    if cleaned_uncategorized:
        data["uncategorized"] = cleaned_uncategorized
    else:
        data.pop("uncategorized", None)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=False, default_flow_style=False),
        encoding="utf-8",
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="category_uncategorized_update_complete",
        module=logger.name,
        fields={"path": str(path), "records": len(cleaned_uncategorized)},
    ))
