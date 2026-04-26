from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import yaml

from src.contracts.categories import (
    CategoryClassificationConfig,
    CategoryDefinition,
    CategoryMappingLoadRequest,
    CategoryMappingLoadResponse,
    CategoryMappings,
    TaxonomyInferenceRule,
    UncategorizedTagsEntry,
    UncategorizedTagsFlushRequest,
    UncategorizedTagsUpdateRequest,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.tag_utils import normalize_slug_tag

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
_CATEGORY_LOCK = threading.Lock()


def _clean_tags(tags: List[str]) -> List[str]:
    cleaned = []
    seen = set()
    for t in tags or []:
        t_s = str(t).strip()
        if not t_s:
            continue
        norm = normalize_slug_tag(t_s)
        if norm in seen:
            continue
        seen.add(norm)
        cleaned.append(norm)
    return cleaned


def _clean_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if not isinstance(value, (int, float, str, bytes, bytearray)):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return float(value)
    if not isinstance(value, (int, float, str, bytes, bytearray)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return default


def _category_positive_tags(item: dict) -> List[str]:
    positive: List[str] = []
    for key in (
        "core_tags",
        "supporting_tags",
        "secondary_supporting_tags",
        "descriptor_tags",
        "generic_tags",
        "tags",
    ):
        positive.extend(item.get(key) or [])
    return positive


def _sanitize_classification(raw: dict) -> dict:
    classification_raw = raw.get("classification")
    classification_map = (
        classification_raw if isinstance(classification_raw, dict) else {}
    )
    return {
        "schema_version": str(classification_map.get("schema_version", "1.1")),
        "max_categories": max(1, _clean_int(classification_map.get("max_categories"), 2)),
        "min_primary_score": _clean_float(
            classification_map.get("min_primary_score"), 2.2
        ),
        "min_secondary_score": _clean_float(
            classification_map.get("min_secondary_score"), 1.6
        ),
        "secondary_score_ratio": _clean_float(
            classification_map.get("secondary_score_ratio"), 0.7
        ),
        "secondary_rescue_score_ratio": _clean_float(
            classification_map.get("secondary_rescue_score_ratio"), 0.55
        ),
        "secondary_rescue_min_strong_matches": max(
            1,
            _clean_int(
                classification_map.get("secondary_rescue_min_strong_matches"),
                2,
            ),
        ),
        "secondary_rescue_min_evidence_tags": max(
            1,
            _clean_int(
                classification_map.get("secondary_rescue_min_evidence_tags"),
                2,
            ),
        ),
        "secondary_rescue_min_evidence_sections": max(
            1,
            _clean_int(
                classification_map.get("secondary_rescue_min_evidence_sections"),
                2,
            ),
        ),
        "core_tag_weight": _clean_float(
            classification_map.get("core_tag_weight"), 2.2
        ),
        "supporting_tag_weight": _clean_float(
            classification_map.get("supporting_tag_weight"), 1.2
        ),
        "legacy_tag_weight": _clean_float(
            classification_map.get("legacy_tag_weight"), 1.0
        ),
        "generic_tag_weight": _clean_float(
            classification_map.get("generic_tag_weight"), 0.3
        ),
        "negative_tag_weight": _clean_float(
            classification_map.get("negative_tag_weight"), -2.0
        ),
        "repeated_match_bonus": _clean_float(
            classification_map.get("repeated_match_bonus"), 0.25
        ),
        "global_generic_tags": _clean_tags(
            classification_map.get("global_generic_tags") or []
        ),
    }


def _sanitize_inference_rules(raw: dict) -> List[dict]:
    rules_raw = raw.get("inference_rules") or []
    if not isinstance(rules_raw, list):
        return []
    rules: List[dict] = []
    for item in rules_raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        target_category_id = str(item.get("target_category_id") or "").strip()
        inferred_tag = str(item.get("inferred_tag") or "").strip()
        trigger_tags = _clean_tags(item.get("trigger_tags") or [])
        if not name or not inferred_tag or not trigger_tags:
            continue
        inferred_tier = str(item.get("inferred_tier") or "secondary").strip().lower()
        if inferred_tier not in {"primary", "secondary"}:
            inferred_tier = "secondary"
        rules.append(
            {
                "name": name,
                "target_category_id": target_category_id,
                "trigger_tags": trigger_tags,
                "inferred_tag": inferred_tag,
                "inferred_tier": inferred_tier,
                "context_keywords_any": _clean_tags(
                    item.get("context_keywords_any") or []
                ),
                "remove_tags": _clean_tags(item.get("remove_tags") or []),
                "schema_version": str(item.get("schema_version", "1.1")),
            }
        )
    return rules


def load_mappings(request: CategoryMappingLoadRequest, ctx: RunContext) -> CategoryMappingLoadResponse:
    path = Path(request.path or DEFAULT_MAPPING_PATH).resolve()
    logger.info(log_event(
        ctx,
        role="service",
        event="category_mapping_load_start",
        module=logger.name,
        fields={"path": str(path)},
    ))
    with _CATEGORY_LOCK:
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
            "max_categories": entry.mappings.classification.max_categories,
            "cached": source != "reloaded",
            "source": source,
        },
    ))
    return CategoryMappingLoadResponse(schema_version="1.1", mappings=entry.mappings)


def update_uncategorized_tags(request: UncategorizedTagsUpdateRequest, ctx: RunContext) -> None:
    path = Path(request.path or DEFAULT_MAPPING_PATH).resolve()
    logger.info(log_event(
        ctx,
        role="service",
        event="category_uncategorized_update_start",
        module=logger.name,
        fields={"path": str(path), "title": request.report_title, "tag_count": len(request.tags)},
    ))
    with _CATEGORY_LOCK:
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
            classification=entry.mappings.classification,
            inference_rules=entry.mappings.inference_rules,
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
    cached_entry = _CATEGORY_CACHE.get(path)
    logger.info(log_event(
        ctx,
        role="service",
        event="category_uncategorized_flush_start",
        module=logger.name,
        fields={
            "path": str(path),
            "cached": path in _CATEGORY_CACHE,
            "dirty": cached_entry.dirty_uncategorized if cached_entry else False,
        },
    ))
    with _CATEGORY_LOCK:
        entry = _CATEGORY_CACHE.get(path)
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
            "classification": entry.data.get("classification") or {},
            "categories": entry.data.get("categories") or [],
            "inference_rules": entry.data.get("inference_rules") or [],
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
    known_tags = {
        normalize_slug_tag(tag)
        for item in categories
        for tag in _category_positive_tags(item)
        if normalize_slug_tag(tag)
    }

    cleaned_uncategorized: List[dict[str, Any]] = []
    for entry in existing_uncategorized:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        tags_cleaned = []
        seen = set()
        for t in entry.get("tags") or []:
            t_s = str(t).strip()
            norm = normalize_slug_tag(t_s)
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
        norm = normalize_slug_tag(t_s)
        if not t_s or norm in known_tags or norm in seen_new:
            continue
        seen_new.add(norm)
        new_tags.append(t_s)

    if new_tags:
        merged = False
        for entry in cleaned_uncategorized:
            if entry.get("title") == report_title:
                existing_tags = [
                    str(tag).strip()
                    for tag in entry.get("tags", [])
                    if str(tag).strip()
                ]
                existing_norms = {
                    normalize_slug_tag(tag)
                    for tag in existing_tags
                    if normalize_slug_tag(tag)
                }
                existing_tags.extend(
                    [
                        tag
                        for tag in new_tags
                        if normalize_slug_tag(tag) not in existing_norms
                    ]
                )
                entry["tags"] = existing_tags
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
    classification = _sanitize_classification(raw)
    inference_rules = _sanitize_inference_rules(raw)
    categories_raw = raw.get("categories") or []
    categories: List[dict] = []
    for item in categories_raw:
        if not isinstance(item, dict):
            continue
        tags = _clean_tags(item.get("tags") or [])
        core_tags = _clean_tags(item.get("core_tags") or [])
        supporting_tags = _clean_tags(item.get("supporting_tags") or [])
        secondary_supporting_tags = _clean_tags(
            item.get("secondary_supporting_tags") or []
        )
        descriptor_tags = _clean_tags(item.get("descriptor_tags") or [])
        generic_tags = _clean_tags(item.get("generic_tags") or [])
        negative_tags = _clean_tags(item.get("negative_tags") or [])
        must_have_one_of = _clean_tags(item.get("must_have_one_of") or [])
        categories.append({
            "id": str(item.get("id") or "").strip(),
            "label": str(item.get("label") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "definition": str(
                item.get("definition") or item.get("description") or ""
            ).strip(),
            "include_when": [
                str(value).strip()
                for value in (item.get("include_when") or [])
                if str(value).strip()
            ],
            "exclude_when": [
                str(value).strip()
                for value in (item.get("exclude_when") or [])
                if str(value).strip()
            ],
            "tags": tags,
            "core_tags": core_tags,
            "supporting_tags": supporting_tags,
            "secondary_supporting_tags": secondary_supporting_tags,
            "descriptor_tags": descriptor_tags,
            "generic_tags": generic_tags,
            "negative_tags": negative_tags,
            "must_have_one_of": must_have_one_of,
            "priority": _clean_int(item.get("priority"), 0),
            "portal_exposed": _clean_bool(item.get("portal_exposed"), True),
        })
    known_tags: Set[str] = {
        normalize_slug_tag(tag)
        for item in categories
        for tag in _category_positive_tags(item)
        if normalize_slug_tag(tag)
    }
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
            norm = normalize_slug_tag(t_s)
            if not t_s or norm in known_tags or norm in seen:
                continue
            seen.add(norm)
            tags_cleaned.append(t_s)
        if tags_cleaned:
            uncategorized.append({"title": title, "tags": tags_cleaned})
    return {
        "schema_version": str(raw.get("schema_version", "1.2")),
        "classification": classification,
        "categories": categories,
        "inference_rules": inference_rules,
        "uncategorized": uncategorized,
    }


def _validate_context_profiles(data: dict, path: Path) -> None:
    incomplete_fields: list[str] = []
    for item in data.get("categories") or []:
        if not isinstance(item, dict):
            continue
        if not _clean_bool(item.get("portal_exposed"), True):
            continue
        category_id = str(item.get("id") or "").strip() or "<missing-id>"
        if not str(item.get("label") or "").strip():
            incomplete_fields.append(f"{category_id}.label")
        if not str(item.get("description") or "").strip():
            incomplete_fields.append(f"{category_id}.description")
        if not str(item.get("definition") or "").strip():
            incomplete_fields.append(f"{category_id}.definition")
        if not (item.get("include_when") or []):
            incomplete_fields.append(f"{category_id}.include_when")
        if not (item.get("exclude_when") or []):
            incomplete_fields.append(f"{category_id}.exclude_when")
    if incomplete_fields:
        raise AppError(
            code="category_mapping_context_profile_incomplete",
            message=f"Context-first category profiles are incomplete: {path}",
            retryable=False,
            severity="error",
            context={
                "path": str(path),
                "incomplete_fields": incomplete_fields,
            },
        )


def _build_mappings(data: dict) -> CategoryMappings:
    categories = [
        CategoryDefinition(
            id=item.get("id", ""),
            label=item.get("label", ""),
            description=item.get("description", ""),
            definition=item.get("definition", ""),
            include_when=item.get("include_when", []),
            exclude_when=item.get("exclude_when", []),
            tags=item.get("tags", []),
            core_tags=item.get("core_tags", []),
            supporting_tags=item.get("supporting_tags", []),
            secondary_supporting_tags=item.get("secondary_supporting_tags", []),
            descriptor_tags=item.get("descriptor_tags", []),
            generic_tags=item.get("generic_tags", []),
            negative_tags=item.get("negative_tags", []),
            must_have_one_of=item.get("must_have_one_of", []),
            priority=_clean_int(item.get("priority"), 0),
            portal_exposed=_clean_bool(item.get("portal_exposed"), True),
        )
        for item in data.get("categories") or []
    ]
    uncategorized = [
        UncategorizedTagsEntry(title=item.get("title", ""), tags=item.get("tags", []))
        for item in data.get("uncategorized") or []
    ]
    inference_rules = [
        TaxonomyInferenceRule(
            name=item.get("name", ""),
            target_category_id=item.get("target_category_id", ""),
            trigger_tags=item.get("trigger_tags", []),
            inferred_tag=item.get("inferred_tag", ""),
            inferred_tier=item.get("inferred_tier", "secondary"),
            context_keywords_any=item.get("context_keywords_any", []),
            remove_tags=item.get("remove_tags", []),
            schema_version=item.get("schema_version", "1.1"),
        )
        for item in data.get("inference_rules") or []
    ]
    return CategoryMappings(
        schema_version=str(data.get("schema_version", "1.2")),
        categories=categories,
        classification=CategoryClassificationConfig(
            schema_version=str(
                (data.get("classification") or {}).get("schema_version", "1.1")
            ),
            max_categories=max(
                1,
                _clean_int((data.get("classification") or {}).get("max_categories"), 2),
            ),
            min_primary_score=_clean_float(
                (data.get("classification") or {}).get("min_primary_score"), 2.2
            ),
            min_secondary_score=_clean_float(
                (data.get("classification") or {}).get("min_secondary_score"), 1.6
            ),
            secondary_score_ratio=_clean_float(
                (data.get("classification") or {}).get("secondary_score_ratio"), 0.7
            ),
            secondary_rescue_score_ratio=_clean_float(
                (data.get("classification") or {}).get(
                    "secondary_rescue_score_ratio"
                ),
                0.55,
            ),
            secondary_rescue_min_strong_matches=max(
                1,
                _clean_int(
                    (data.get("classification") or {}).get(
                        "secondary_rescue_min_strong_matches"
                    ),
                    2,
                ),
            ),
            secondary_rescue_min_evidence_tags=max(
                1,
                _clean_int(
                    (data.get("classification") or {}).get(
                        "secondary_rescue_min_evidence_tags"
                    ),
                    2,
                ),
            ),
            secondary_rescue_min_evidence_sections=max(
                1,
                _clean_int(
                    (data.get("classification") or {}).get(
                        "secondary_rescue_min_evidence_sections"
                    ),
                    2,
                ),
            ),
            core_tag_weight=_clean_float(
                (data.get("classification") or {}).get("core_tag_weight"), 2.2
            ),
            supporting_tag_weight=_clean_float(
                (data.get("classification") or {}).get("supporting_tag_weight"), 1.2
            ),
            legacy_tag_weight=_clean_float(
                (data.get("classification") or {}).get("legacy_tag_weight"), 1.0
            ),
            generic_tag_weight=_clean_float(
                (data.get("classification") or {}).get("generic_tag_weight"), 0.3
            ),
            negative_tag_weight=_clean_float(
                (data.get("classification") or {}).get("negative_tag_weight"), -2.0
            ),
            repeated_match_bonus=_clean_float(
                (data.get("classification") or {}).get("repeated_match_bonus"), 0.25
            ),
            global_generic_tags=_clean_tags(
                (data.get("classification") or {}).get("global_generic_tags") or []
            ),
        ),
        inference_rules=inference_rules,
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
    _validate_context_profiles(sanitized, path)
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
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise AppError(
            code="category_mapping_invalid_yaml",
            message=f"Category mapping YAML invalid: {path}",
            cause=exc,
            retryable=False,
            severity="error",
            context={"path": str(path)},
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="category_mapping_invalid_yaml",
            message=f"Category mapping YAML must be a mapping: {path}",
            retryable=False,
            severity="error",
            context={"path": str(path)},
        )
    return payload
