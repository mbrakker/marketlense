from __future__ import annotations

import logging
from typing import List

from src.contracts.categories import WordPressCategoryUpdateOutcome
from src.contracts.categories import CategoryMappingLoadResponse
from src.contracts.wordpress import (
    WordPressCategoryEnsureRequest,
    WordPressCategoryTerm,
    WordPressPostUpdateRequest,
)
from src.contracts.run_context import RunContext
from src.services.wordpress_service import ensure_categories, update_post_categories
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.wp_category_generator")


def update_post_categories_for_record(
    *,
    file_id: str,
    post_id: int,
    categories: List[str],
    base_url: str,
    auth_header: str,
    post_type: str,
    mappings: CategoryMappingLoadResponse,
    ctx: RunContext,
) -> WordPressCategoryUpdateOutcome:
    logger.info(log_event(
        ctx,
        role="generator",
        event="wp_category_update_start",
        module=logger.name,
        fields={"file_id": file_id, "post_id": post_id, "categories": categories},
    ))
    if not categories:
        logger.info(log_event(
            ctx,
            role="generator",
            event="wp_category_update_skipped",
            module=logger.name,
            fields={"file_id": file_id, "reason": "no_categories"},
        ))
        return WordPressCategoryUpdateOutcome(
            schema_version="1.0",
            file_id=file_id,
            post_id=post_id,
            categories=[],
            status="skipped",
            error="no_categories",
        )

    id_to_label = {cat.id: cat.label or cat.id for cat in mappings.mappings.categories}
    terms = [
        WordPressCategoryTerm(schema_version="1.0", slug=cat_id, name=id_to_label.get(cat_id, cat_id))
        for cat_id in categories
    ]
    ensure_resp = ensure_categories(
        WordPressCategoryEnsureRequest(
            schema_version="1.0",
            base_url=base_url,
            auth_header=auth_header,
            categories=terms,
        ),
        ctx,
    )
    category_ids = [
        ensure_resp.slug_to_id[term.slug]
        for term in terms
        if term.slug in ensure_resp.slug_to_id
    ]
    if not category_ids:
        return WordPressCategoryUpdateOutcome(
            schema_version="1.0",
            file_id=file_id,
            post_id=post_id,
            categories=[],
            status="skipped",
            error="no_category_ids",
        )
    update_resp = update_post_categories(
        WordPressPostUpdateRequest(
            schema_version="1.0",
            base_url=base_url,
            auth_header=auth_header,
            post_id=post_id,
            categories=category_ids,
            post_type=post_type,
        ),
        ctx,
    )
    logger.info(log_event(
        ctx,
        role="generator",
        event="wp_category_update_complete",
        module=logger.name,
        fields={"file_id": file_id, "post_id": post_id, "categories": category_ids},
    ))
    return WordPressCategoryUpdateOutcome(
        schema_version="1.0",
        file_id=file_id,
        post_id=update_resp.post_id,
        categories=categories,
        status="updated",
    )
