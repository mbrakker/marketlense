from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

import yaml

from src.contracts.categories import (
    CategoryDefinition,
    CategoryMappingLoadRequest,
    CategoryMappingLoadResponse,
    CategoryMappings,
    UncategorizedTagsEntry,
    UncategorizedTagsFlushRequest,
    UncategorizedTagsUpdateRequest,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.category_mapping_service")

DEFAULT_MAPPING_PATH = Path(__file__).resolve().parents[1] / "config" / "category-mappings.yaml"


@dataclass
class _CategoryMappingCacheEntry:
    path: Path
    modified_time: float
    data: dict
    mappings: CategoryMappings
    dirty_uncategorized: bool = False


_CATEGORY_CACHE: Dict[Path, _CategoryMappingCacheEntry] = {}


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


def load_mappings(request: CategoryMappingLoadRequest, ctx: RunContext) -> CategoryMappingLoadResponse:
    path = Path(request.path or DEFAULT_MAPPING_PATH).resolve()
    logger.info(log_event(
        ctx,
        role="service",
        event="category_mapping_load_start",
        module=logger.name,
        fields={"path": str(path)},
    ))
    entry, source = _get_or_load_entry(
        path,
        reload_if_changed=request.reload_if_changed,
        force_reload=request.force_reload,
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="category_mapping_load_complete",
        module=logger.name,
        fields={
            "path": str(path),
            "categories": len(entry.mappings.categories),
            "uncategorized": len(entry.mappings.uncategorized),
            "cached": source != "reloaded",
            "source": source,
        },
    ))
    return CategoryMappingLoadResponse(schema_version="1.0", mappings=entry.mappings)


def update_uncategorized_tags(request: UncategorizedTagsUpdateRequest, ctx: RunContext) -> None:
    path = Path(request.path or DEFAULT_MAPPING_PATH).resolve()
    logger.info(log_event(
        ctx,
        role="service",
        event="category_uncategorized_update_start",
        module=logger.name,
        fields={"path": str(path), "title": request.report_title, "tag_count": len(request.tags)},
    ))
    entry, source = _get_or_load_entry(
        path,
        reload_if_changed=True,
        force_reload=False,
    )
    merged_uncategorized = _merge_uncategorized(
        entry.data.get("uncategorized") or [],
        entry.data.get("categories") or [],
        request.report_title,
        request.tags,
    )
    if merged_uncategorized == (entry.data.get("uncategorized") or []):
        logger.info(log_event(
            ctx,
            role="service",
            event="category_uncategorized_update_noop",
            module=logger.name,
            fields={"path": str(path), "title": request.report_title, "source": source},
        ))
        return

    entry.data["uncategorized"] = merged_uncategorized
    entry.mappings = CategoryMappings(
        schema_version=entry.data.get("schema_version", "1.0"),
        categories=entry.mappings.categories,
        uncategorized=[
            UncategorizedTagsEntry(title=item["title"], tags=item["tags"])
            for item in merged_uncategorized
        ],
    )
    entry.dirty_uncategorized = True
    _CATEGORY_CACHE[path] = entry
    logger.info(log_event(
        ctx,
        role="service",
        event="category_uncategorized_update_complete",
        module=logger.name,
        fields={
            "path": str(path),
            "records": len(merged_uncategorized),
            "dirty": entry.dirty_uncategorized,
        },
    ))


def flush_uncategorized_tags(request: UncategorizedTagsFlushRequest, ctx: RunContext) -> None:
    path = Path(request.path or DEFAULT_MAPPING_PATH).resolve()
    entry = _CATEGORY_CACHE.get(path)
    logger.info(log_event(
        ctx,
        role="service",
        event="category_uncategorized_flush_start",
        module=logger.name,
        fields={
            "path": str(path),
            "cached": entry is not None,
            "dirty": entry.dirty_uncategorized if entry else False,
        },
    ))
    if not entry or not entry.dirty_uncategorized:
        logger.info(log_event(
            ctx,
            role="service",
            event="category_uncategorized_flush_skipped",
            module=logger.name,
            fields={"path": str(path), "reason": "no_pending_changes"},
        ))
        return

    serialized = {
        "schema_version": entry.data.get("schema_version", "1.0"),
        "categories": entry.data.get("categories") or [],
        "uncategorized": entry.data.get("uncategorized") or [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(serialized, sort_keys=False, allow_unicode=False, default_flow_style=False),
        encoding="utf-8",
    )
    entry.modified_time = _get_mtime(path)
    entry.dirty_uncategorized = False
    _CATEGORY_CACHE[path] = entry
    logger.info(log_event(
        ctx,
        role="service",
        event="category_uncategorized_flush_complete",
        module=logger.name,
        fields={
            "path": str(path),
            "records": len(serialized.get("uncategorized") or []),
        },
    ))


def _merge_uncategorized(
    existing_uncategorized: List[dict],
    categories: List[dict],
    report_title: str,
    tags: List[str],
) -> List[dict]:
    known_tags = {_norm_tag(t) for item in categories for t in (item.get("tags") or [])}

    cleaned_uncategorized = []
    for entry in existing_uncategorized:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        tags_cleaned = []
        seen = set()
        for t in entry.get("tags") or []:
            t_s = str(t).strip()
            norm = _norm_tag(t_s)
            if not t_s or norm in known_tags or norm in seen:
                continue
            seen.add(norm)
            tags_cleaned.append(t_s)
        if tags_cleaned:
            cleaned_uncategorized.append({"title": title, "tags": tags_cleaned})

    new_tags = []
    seen_new = set()
    for t in tags or []:
        t_s = str(t).strip()
        norm = _norm_tag(t_s)
        if not t_s or norm in known_tags or norm in seen_new:
            continue
        seen_new.add(norm)
        new_tags.append(t_s)

    if new_tags:
        merged = False
        for entry in cleaned_uncategorized:
            if entry.get("title") == report_title:
                existing_norms = {_norm_tag(t) for t in entry["tags"]}
                entry["tags"].extend([tag for tag in new_tags if _norm_tag(tag) not in existing_norms])
                merged = True
                break
        if not merged:
            cleaned_uncategorized.append({"title": report_title, "tags": new_tags})

    return cleaned_uncategorized


def _get_mtime(path: Path) -> float:
    return path.stat().st_mtime


def _is_cache_valid(entry: _CategoryMappingCacheEntry) -> bool:
    try:
        return entry.modified_time == entry.path.stat().st_mtime
    except FileNotFoundError:
        return False


def _sanitize_mapping_data(raw: dict) -> dict:
    categories_raw = raw.get("categories") or []
    categories: List[dict] = []
    for item in categories_raw:
        if not isinstance(item, dict):
            continue
        tags = _clean_tags(item.get("tags") or [])
        categories.append({
            "id": str(item.get("id") or "").strip(),
            "label": str(item.get("label") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "tags": tags,
        })
    known_tags: Set[str] = {_norm_tag(t) for item in categories for t in item["tags"]}
    uncategorized_raw = raw.get("uncategorized") or []
    uncategorized: List[dict] = []
    for item in uncategorized_raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        tags_cleaned = []
        seen = set()
        for t in item.get("tags") or []:
            t_s = str(t).strip()
            norm = _norm_tag(t_s)
            if not t_s or norm in known_tags or norm in seen:
                continue
            seen.add(norm)
            tags_cleaned.append(t_s)
        if tags_cleaned:
            uncategorized.append({"title": title, "tags": tags_cleaned})
    return {
        "schema_version": str(raw.get("schema_version", "1.0")),
        "categories": categories,
        "uncategorized": uncategorized,
    }


def _build_mappings(data: dict) -> CategoryMappings:
    categories = [
        CategoryDefinition(
            id=item.get("id", ""),
            label=item.get("label", ""),
            description=item.get("description", ""),
            tags=item.get("tags", []),
        )
        for item in data.get("categories") or []
    ]
    uncategorized = [
        UncategorizedTagsEntry(title=item.get("title", ""), tags=item.get("tags", []))
        for item in data.get("uncategorized") or []
    ]
    return CategoryMappings(
        schema_version=str(data.get("schema_version", "1.0")),
        categories=categories,
        uncategorized=uncategorized,
    )


def _get_or_load_entry(
    path: Path,
    *,
    reload_if_changed: bool,
    force_reload: bool,
) -> Tuple[_CategoryMappingCacheEntry, str]:
    cache_entry = _CATEGORY_CACHE.get(path)
    if cache_entry:
        if cache_entry.dirty_uncategorized:
            return cache_entry, "cache_dirty"
        if not force_reload:
            if not reload_if_changed:
                return cache_entry, "cache"
            if _is_cache_valid(cache_entry):
                return cache_entry, "cache_validated"
    data = _load_yaml(path)
    sanitized = _sanitize_mapping_data(data)
    entry = _CategoryMappingCacheEntry(
        path=path,
        modified_time=_get_mtime(path),
        data=sanitized,
        mappings=_build_mappings(sanitized),
    )
    _CATEGORY_CACHE[path] = entry
    return entry, "reloaded"


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
