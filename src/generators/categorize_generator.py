from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List

from src.contracts.categories import (
    CategoryAssignment,
    CategoryDefinition,
    CategoryMappingLoadResponse,
)
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.categorize_generator")


def categorize_taxonomy(
    taxonomy: List[str],
    mappings: CategoryMappingLoadResponse,
    ctx: RunContext,
) -> CategoryAssignment:
    logger.info(log_event(
        ctx,
        role="generator",
        event="categorize_start",
        module=logger.name,
        fields={"taxonomy_count": len(taxonomy), "categories": len(mappings.mappings.categories)},
    ))
    tag_to_category: Dict[str, str] = {}
    cat_id_to_def: Dict[str, CategoryDefinition] = {}
    for cat in mappings.mappings.categories:
        cat_id_to_def[cat.id] = cat
        for t in cat.tags:
            norm = _norm_tag(t)
            if norm:
                tag_to_category[norm] = cat.id

    scores: Dict[str, int] = defaultdict(int)
    unmapped: List[str] = []
    unmapped_norm = set()
    for raw_tag in taxonomy or []:
        tag = (raw_tag or "").strip()
        if not tag:
            continue
        norm = _norm_tag(tag)
        cat_id = tag_to_category.get(norm)
        if cat_id:
            scores[cat_id] += 1
        else:
            if norm not in unmapped_norm:
                unmapped_norm.add(norm)
                unmapped.append(tag)

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top_ids = [cat_id for cat_id, _ in ranked[:3]]
    labels = [_category_label(cat_id, cat_id_to_def) for cat_id in top_ids]

    assignment = CategoryAssignment(
        schema_version="1.0",
        categories=top_ids,
        category_labels=labels,
        unmapped_tags=unmapped,
    )
    logger.info(log_event(
        ctx,
        role="generator",
        event="categorize_complete",
        module=logger.name,
        fields={
            "assigned": assignment.categories,
            "unmapped": assignment.unmapped_tags,
        },
    ))
    return assignment


def _norm_tag(tag: str) -> str:
    return tag.strip().lower().replace(" ", "_")


def _category_label(cat_id: str, defs: Dict[str, CategoryDefinition]) -> str:
    cat = defs.get(cat_id)
    if not cat:
        return cat_id
    return cat.label or cat.id
