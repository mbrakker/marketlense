"""Deterministic landing-page qualification for already screened inventory candidates."""

from __future__ import annotations

# ruff: noqa: F401

from ._publisher_inventory_candidate_quality.classification import (
    _GENERIC_TITLE_TOKENS,
    _contains_report_style_title_marker,
    _looks_like_publication_detail_url,
    _looks_like_report_collection_root_url,
    _normalize_title,
    _resolve_candidate_title,
)
from ._publisher_inventory_candidate_quality.evaluation import (
    _qualify_observation,
    _build_recovery_recipe,
)
from ._publisher_inventory_candidate_quality.workflow import (
    logger,
    qualify_publisher_inventory_candidates,
)
