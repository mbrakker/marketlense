from __future__ import annotations

import logging
from typing import List, Optional

from src.contracts.categories import WordPressCategoryUpdateOutcome
from src.contracts.categories import CategoryMappingLoadResponse
from src.contracts.wordpress import (
    WordPressPostUpdateRequest,
    WordPressTaxonomyEnsureRequest,
    WordPressTaxonomyTerm,
)
from src.contracts.run_context import RunContext
from src.services import wordpress_service
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
    ssl_verify: bool = True,
    ca_bundle_path: Optional[str] = None,
    mappings: CategoryMappingLoadResponse,
    ctx: RunContext,
) -> WordPressCategoryUpdateOutcome:
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="wp_category_update_start",
            module=logger.name,
            fields={"file_id": file_id, "post_id": post_id, "categories": categories},
        )
    )
    if not categories:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="wp_category_update_skipped",
                module=logger.name,
                fields={"file_id": file_id, "reason": "no_categories"},
            )
        )
        return WordPressCategoryUpdateOutcome(
            schema_version="1.0",
            file_id=file_id,
            post_id=post_id,
            categories=[],
            status="skipped",
            error="no_categories",
        )

    id_to_category = {cat.id: cat for cat in mappings.mappings.categories}
    terms = [
        WordPressTaxonomyTerm(
            schema_version="1.1",
            slug=cat_id,
            name=(id_to_category[cat_id].label or cat_id)
            if cat_id in id_to_category
            else cat_id,
            description=id_to_category[cat_id].description
            if cat_id in id_to_category
            else "",
            definition=id_to_category[cat_id].definition
            if cat_id in id_to_category
            else "",
            include_when=list(id_to_category[cat_id].include_when)
            if cat_id in id_to_category
            else [],
            exclude_when=list(id_to_category[cat_id].exclude_when)
            if cat_id in id_to_category
            else [],
            semantics_version=id_to_category[cat_id].schema_version
            if cat_id in id_to_category
            else "",
        )
        for cat_id in categories
    ]
    ensure_resp = wordpress_service.ensure_taxonomy_terms(
        WordPressTaxonomyEnsureRequest(
            schema_version="1.0",
            base_url=base_url,
            auth_header=auth_header,
            taxonomy_rest_base="categories",
            terms=terms,
            ssl_verify=ssl_verify,
            ca_bundle_path=ca_bundle_path,
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
    update_resp = wordpress_service.update_post_categories(
        WordPressPostUpdateRequest(
            schema_version="1.0",
            base_url=base_url,
            auth_header=auth_header,
            post_id=post_id,
            categories=category_ids,
            ssl_verify=ssl_verify,
            ca_bundle_path=ca_bundle_path,
            post_type=post_type,
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="wp_category_update_complete",
            module=logger.name,
            fields={"file_id": file_id, "post_id": post_id, "categories": category_ids},
        )
    )
    return WordPressCategoryUpdateOutcome(
        schema_version="1.0",
        file_id=file_id,
        post_id=update_resp.post_id,
        categories=categories,
        status="updated",
    )
