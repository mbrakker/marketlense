from __future__ import annotations

"""Models helpers for publication orchestration."""

from dataclasses import dataclass, field
from typing import List, Optional, TypedDict

from src.contracts.publish import (
    PublishHtmlSnapshot,
    PublishResolvedTerms,
)
from src.contracts.publish_readiness import PublishReadinessArtifact
from src.contracts.state import (
    StateGetResponse,
)
from src.contracts.wordpress import (
    WordPressPostLookupBatchItem,
    WordPressTaxonomyTerm,
)
from src.utils.errors import AppError

_PUBLISH_IDEMPOTENCY_SCOPE = "publish_orchestrator.publish_html"

_CROSS_REPORT_PUBLISH_IDEMPOTENCY_SCOPE = "publish_orchestrator.cross_report_package"


@dataclass(frozen=True)
class _PublishEntityRoute:
    entity_type: str
    canonical_route_intent: str
    post_type: str
    front_end_section: str
    template: str


_PUBLISH_ENTITY_ROUTES = {
    "report": _PublishEntityRoute(
        entity_type="report",
        canonical_route_intent="wordpress:ml_report",
        post_type="ml_report",
        front_end_section="reports",
        template="single-ml_report",
    ),
    "briefing": _PublishEntityRoute(
        entity_type="briefing",
        canonical_route_intent="wordpress:ml_briefing",
        post_type="ml_briefing",
        front_end_section="briefings",
        template="single-ml_briefing",
    ),
    "signal": _PublishEntityRoute(
        entity_type="signal",
        canonical_route_intent="wordpress:ml_signal",
        post_type="ml_signal",
        front_end_section="signals",
        template="single-ml_signal",
    ),
}

_PUBLISH_ROUTES_BY_INTENT = {
    route.canonical_route_intent: route for route in _PUBLISH_ENTITY_ROUTES.values()
}

_CROSS_REPORT_WORDPRESS_POST_TYPES = {
    route.canonical_route_intent: route.post_type
    for route in _PUBLISH_ENTITY_ROUTES.values()
}


@dataclass(frozen=True)
class _PublishCandidate:
    html_path: str
    file_id: Optional[str]
    html_snapshot: Optional[PublishHtmlSnapshot]
    entity_route: _PublishEntityRoute | None
    entity_error: AppError | None


@dataclass(frozen=True)
class _PublishPreflightEntry:
    candidate: _PublishCandidate
    state_row: StateGetResponse | None
    validation_status: str
    validation_issues: List[str] = field(default_factory=list)
    publish_readiness: PublishReadinessArtifact | None = None
    existing_post_lookup: WordPressPostLookupBatchItem | None = None
    resolved_terms: PublishResolvedTerms | None = None


@dataclass(frozen=True)
class _CrossReportWordPressClassification:
    post_type: str
    slug: str
    category_terms: list[WordPressTaxonomyTerm]
    tag_slugs: list[str]
    taxonomy_terms: dict[str, list[WordPressTaxonomyTerm]]


class _CrossReportResultFields(TypedDict):
    target_post_type: str
    target_slug: str
    category_slugs: list[str]
    tag_slugs: list[str]
    taxonomy_term_slugs: dict[str, list[str]]
