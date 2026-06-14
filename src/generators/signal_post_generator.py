from __future__ import annotations

import html
import logging

from src.contracts.cross_report_analysis import (
    CrossReportEvidenceReference,
    CrossReportProjectedDataReadResponse,
    CrossReportSourceReportCandidate,
    validate_cross_report_contract,
)
from src.contracts.run_context import RunContext
from src.contracts.signal_candidates import (
    SignalCandidate,
    SignalCandidateGroup,
    SignalCandidateReadResponse,
    SignalCandidateSourceRef,
    validate_signal_candidate_contract,
)
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPostGenerationRequest,
    SignalPublishProjection,
)
from src.utils.coercion import ordered_unique_strings as _unique_ordered
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.signal_post_generator")


def _normalized_filters(values: list[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text:
            normalized.add(text.casefold())
            slug = slugify(text)
            if slug:
                normalized.add(slug.casefold())
    return normalized


def _source_matches_request(
    source: CrossReportSourceReportCandidate,
    request: SignalPostGenerationRequest,
) -> bool:
    category_filters = _normalized_filters(request.category_filters)
    if category_filters:
        category_values = _normalized_filters(
            list(source.category_ids) + list(source.category_labels)
        )
        if not category_filters.intersection(category_values):
            return False

    tag_filters = _normalized_filters(request.tag_filters)
    if tag_filters:
        if not tag_filters.intersection(_normalized_filters(list(source.tags))):
            return False

    publisher_filters = _normalized_filters(request.publisher_filters)
    if publisher_filters:
        if not publisher_filters.intersection(
            _normalized_filters([source.publisher, source.publisher_id])
        ):
            return False

    return True


def _selected_sources(
    request: SignalPostGenerationRequest,
    projected_data: CrossReportProjectedDataReadResponse,
) -> list[CrossReportSourceReportCandidate]:
    candidates = [
        source
        for source in projected_data.source_candidates
        if source.projection_status == "projected"
        and source.evidence_count > 0
        and _source_matches_request(source, request)
    ]
    return sorted(
        candidates,
        key=lambda source: (
            -int(source.evidence_count),
            source.publisher.casefold(),
            source.report_id,
        ),
    )[: max(1, request.max_source_reports)]


def _selected_evidence(
    selected_sources: list[CrossReportSourceReportCandidate],
    projected_data: CrossReportProjectedDataReadResponse,
    request: SignalPostGenerationRequest,
) -> list[CrossReportEvidenceReference]:
    selected_report_ids = {source.report_id for source in selected_sources}
    evidence = [
        item
        for item in projected_data.evidence
        if item.report_id in selected_report_ids
        and str(item.evidence_id or "").strip()
        and str(item.text or "").strip()
    ]
    return sorted(
        evidence,
        key=lambda item: (item.report_id, item.evidence_id),
    )[: max(1, request.max_evidence_items)]


def _require_grounding(
    *,
    request: SignalPostGenerationRequest,
    selected_sources: list[CrossReportSourceReportCandidate],
    selected_evidence: list[CrossReportEvidenceReference],
    topic_ids: list[str],
) -> None:
    if (
        len({source.report_id for source in selected_sources})
        < request.minimum_source_reports
        or len(selected_evidence) < request.minimum_evidence_items
        or topic_ids == []
    ):
        raise AppError(
            code="signal_grounding_insufficient",
            message="Signal generation requires projected evidence, source reports, and topic/category relationships",
            retryable=False,
            severity="error",
            context={
                "request_id": request.request_id,
                "source_report_count": len(
                    {source.report_id for source in selected_sources}
                ),
                "evidence_count": len(selected_evidence),
                "topic_ids": topic_ids,
                "minimum_source_reports": request.minimum_source_reports,
                "minimum_evidence_items": request.minimum_evidence_items,
            },
        )


def _summary_html(evidence: list[CrossReportEvidenceReference]) -> str:
    first_text = html.escape(str(evidence[0].text or "").strip())
    return f"<p>{first_text}</p>"


def _page_refs_from_metadata(metadata: dict) -> list[int]:
    pages: list[int] = []
    for raw_page in metadata.get("pages") or []:
        try:
            page = int(raw_page)
        except (TypeError, ValueError):
            continue
        if page > 0 and page not in pages:
            pages.append(page)
    for key in ("page",):
        raw_page = metadata.get(key)
        try:
            page = int(raw_page) if raw_page is not None else 0
        except (TypeError, ValueError):
            page = 0
        if page > 0 and page not in pages:
            pages.append(page)
    return pages


def _citation_label(title: str, pages: list[int]) -> str:
    clean_title = str(title or "").strip()
    if pages:
        page_label = "page" if len(pages) == 1 else "pages"
        page_text = f"{page_label} {', '.join(str(page) for page in pages)}"
        return f"{clean_title}, {page_text}" if clean_title else page_text
    return clean_title


def _evidence_citation(item: CrossReportEvidenceReference) -> str:
    return _citation_label(item.title, _page_refs_from_metadata(item.source_metadata))


def _source_item_html(source: CrossReportSourceReportCandidate) -> str:
    label = f"{html.escape(source.publisher)}: {html.escape(source.title)}"
    source_url = str(source.source_url or "").strip()
    if source_url:
        return (
            "<li>"
            f'<a href="{html.escape(source_url)}" rel="noopener" target="_blank">'
            f"{label}</a>"
            "</li>"
        )
    return f"<li>{label}</li>"


def _body_html(
    *,
    projection_title: str,
    evidence: list[CrossReportEvidenceReference],
    sources: list[CrossReportSourceReportCandidate],
    uncertainty: str,
) -> str:
    evidence_items = "".join(
        "<li>"
        f"<strong>{html.escape(_evidence_citation(item))}</strong>: "
        f"{html.escape(item.text)}"
        "</li>"
        for item in evidence
    )
    source_items = "".join(_source_item_html(source) for source in sources)
    return (
        '<article class="ml-signal-post">'
        f"<h1>{html.escape(projection_title)}</h1>"
        "<h2>Grounded evidence</h2>"
        f"<ul>{evidence_items}</ul>"
        "<h2>Source reports</h2>"
        f"<ul>{source_items}</ul>"
        "<h2>Uncertainty</h2>"
        f"<p>{html.escape(uncertainty)}</p>"
        "</article>"
    )


def _body_html_from_candidates(
    *,
    projection_title: str,
    candidates: list[SignalCandidate],
    groups: list[SignalCandidateGroup],
    sources: list[CrossReportSourceReportCandidate],
    evidence: list[CrossReportEvidenceReference],
    uncertainty: str,
) -> str:
    del groups
    source_title_by_report_id = {source.report_id: source.title for source in sources}
    evidence_by_id = {item.evidence_id: item for item in evidence}
    candidate_items = "".join(
        "<li>"
        f"<strong>{html.escape(candidate.title)}</strong>: "
        f"{html.escape(candidate.summary)} "
        f"<span>({html.escape(candidate.support_level)})</span>"
        "</li>"
        for candidate in candidates
    )
    citation_items = "".join(
        "<li>"
        f"{html.escape(_stored_source_ref_citation(ref, source_title_by_report_id, evidence_by_id))}"
        "</li>"
        for candidate in candidates
        for ref in candidate.source_refs
    )
    source_items = "".join(_source_item_html(source) for source in sources)
    return (
        '<article class="ml-signal-post">'
        f"<h1>{html.escape(projection_title)}</h1>"
        "<h2>Stored Signal candidates</h2>"
        f"<ul>{candidate_items}</ul>"
        "<h2>Grounding citations</h2>"
        f"<ul>{citation_items}</ul>"
        "<h2>Source reports</h2>"
        f"<ul>{source_items}</ul>"
        "<h2>Uncertainty</h2>"
        f"<p>{html.escape(uncertainty)}</p>"
        "</article>"
    )


def _stored_source_ref_citation(
    ref: SignalCandidateSourceRef,
    source_title_by_report_id: dict[str, str],
    evidence_by_id: dict[str, CrossReportEvidenceReference],
) -> str:
    evidence = evidence_by_id.get(ref.evidence_id)
    if evidence is not None:
        return _evidence_citation(evidence)
    pages = list(ref.page_refs) or _page_refs_from_metadata(ref.source_metadata)
    return _citation_label(
        source_title_by_report_id.get(ref.report_id, "Source report"), pages
    )


def _approved_candidates(
    candidate_data: SignalCandidateReadResponse | None,
) -> list[SignalCandidate]:
    if candidate_data is None:
        return []
    validate_signal_candidate_contract(candidate_data)
    return [
        candidate
        for candidate in candidate_data.candidates
        if candidate.validation_status == "approved"
        and candidate.evidence_ids
        and candidate.source_report_ids
    ]


def _candidate_groups(
    candidate_data: SignalCandidateReadResponse | None,
    candidates: list[SignalCandidate],
) -> list[SignalCandidateGroup]:
    if candidate_data is None:
        return []
    wanted = {candidate.group_id for candidate in candidates}
    return [group for group in candidate_data.groups if group.group_id in wanted]


def _projection_from_candidates(
    *,
    request: SignalPostGenerationRequest,
    projected_data: CrossReportProjectedDataReadResponse,
    candidates: list[SignalCandidate],
    groups: list[SignalCandidateGroup],
) -> SignalPublishProjection:
    source_report_ids = _unique_ordered(
        [
            report_id
            for candidate in candidates
            for report_id in candidate.source_report_ids
        ]
    )
    source_by_report_id = {
        source.report_id: source for source in projected_data.source_candidates
    }
    selected_sources = [
        source_by_report_id[report_id]
        for report_id in source_report_ids
        if report_id in source_by_report_id
        and source_by_report_id[report_id].projection_status == "projected"
        and source_by_report_id[report_id].evidence_count > 0
        and _source_matches_request(source_by_report_id[report_id], request)
    ]
    evidence_ids = _unique_ordered(
        [
            evidence_id
            for candidate in candidates
            for evidence_id in candidate.evidence_ids
        ]
    )
    topic_ids = _unique_ordered(
        [
            category_id
            for source in selected_sources
            for category_id in source.category_ids
        ]
    )
    topic_labels = _unique_ordered(
        [
            category_label
            for source in selected_sources
            for category_label in source.category_labels
        ]
    )
    _require_grounding(
        request=request,
        selected_sources=selected_sources,
        selected_evidence=[
            item
            for item in projected_data.evidence
            if item.evidence_id in set(evidence_ids)
        ],
        topic_ids=topic_ids,
    )
    selected_evidence = [
        item
        for item in projected_data.evidence
        if item.evidence_id in set(evidence_ids)
    ]
    title_topic = (
        " ".join(str(request.topic or "").strip().split()) or candidates[0].title
    )
    title = f"{title_topic} signal"
    slug = f"{slugify(title_topic)}-signal"
    tag_labels = _unique_ordered(
        [tag for source in selected_sources for tag in source.tags]
    )
    publisher_labels = _unique_ordered(
        [source.publisher for source in selected_sources]
    )
    caveats = _unique_ordered(
        [caveat for candidate in candidates for caveat in candidate.caveats]
    )
    uncertainty = (
        "Stored Signal candidates: "
        + "; ".join(caveats)
        + ". Review source coverage before treating this as market-wide."
    )
    body_html = _body_html_from_candidates(
        projection_title=title,
        candidates=candidates,
        groups=groups,
        sources=selected_sources,
        evidence=selected_evidence,
        uncertainty=uncertainty,
    )
    summary = html.escape(candidates[0].summary)
    return SignalPublishProjection(
        schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
        title=title,
        slug=slug,
        summary_html=f"<p>{summary}</p>",
        body_html=body_html,
        evidence_ids=evidence_ids,
        source_report_ids=source_report_ids,
        topic_ids=topic_ids,
        confidence=max(candidate.confidence for candidate in candidates),
        uncertainty=uncertainty,
        validation_status="approved",
        file_id=f"signal:{slug}",
        html_text=f"<html><body>{body_html}</body></html>",
        topic_labels=topic_labels,
        tag_labels=tag_labels,
        publisher_labels=publisher_labels,
        target_route=request.target_route,
    )


def build_signal_publish_projection(
    request: SignalPostGenerationRequest,
    projected_data: CrossReportProjectedDataReadResponse,
    ctx: RunContext,
    *,
    candidate_data: SignalCandidateReadResponse | None = None,
) -> SignalPublishProjection:
    validate_cross_report_contract(projected_data)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="signal_publish_projection_start",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "topic": request.topic,
                "source_candidate_count": len(projected_data.source_candidates),
                "evidence_count": len(projected_data.evidence),
            },
        )
    )
    stored_candidates = _approved_candidates(candidate_data)
    if stored_candidates:
        projection = _projection_from_candidates(
            request=request,
            projected_data=projected_data,
            candidates=stored_candidates[: max(1, request.max_source_reports)],
            groups=_candidate_groups(candidate_data, stored_candidates),
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="signal_publish_projection_complete",
                module=logger.name,
                fields={
                    "request_id": request.request_id,
                    "slug": projection.slug,
                    "source_report_ids": projection.source_report_ids,
                    "evidence_ids": projection.evidence_ids,
                    "topic_ids": projection.topic_ids,
                    "validation_status": projection.validation_status,
                    "candidate_reuse": True,
                },
            )
        )
        return projection
    selected_sources = _selected_sources(request, projected_data)
    selected_evidence = _selected_evidence(selected_sources, projected_data, request)
    topic_ids = _unique_ordered(
        [
            category_id
            for source in selected_sources
            for category_id in source.category_ids
        ]
    )
    topic_labels = _unique_ordered(
        [
            category_label
            for source in selected_sources
            for category_label in source.category_labels
        ]
    )
    _require_grounding(
        request=request,
        selected_sources=selected_sources,
        selected_evidence=selected_evidence,
        topic_ids=topic_ids,
    )
    tag_labels = _unique_ordered(
        [tag for source in selected_sources for tag in source.tags]
    )
    publisher_labels = _unique_ordered(
        [source.publisher for source in selected_sources]
    )
    evidence_ids = [item.evidence_id for item in selected_evidence]
    source_report_ids = _unique_ordered(
        [source.report_id for source in selected_sources]
    )
    title_topic = " ".join(str(request.topic or "").strip().split()) or topic_labels[0]
    title = f"{title_topic} signal"
    slug = f"{slugify(title_topic)}-signal"
    publisher_count = len({publisher.casefold() for publisher in publisher_labels})
    confidence = min(
        0.95, round(0.55 + (len(evidence_ids) * 0.05) + (publisher_count * 0.08), 2)
    )
    uncertainty = (
        "Approved projected evidence from "
        f"{len(source_report_ids)} source reports and {publisher_count} publishers; "
        "review source coverage before treating this as market-wide."
    )
    body_html = _body_html(
        projection_title=title,
        evidence=selected_evidence,
        sources=selected_sources,
        uncertainty=uncertainty,
    )
    projection = SignalPublishProjection(
        schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
        title=title,
        slug=slug,
        summary_html=_summary_html(selected_evidence),
        body_html=body_html,
        evidence_ids=evidence_ids,
        source_report_ids=source_report_ids,
        topic_ids=topic_ids,
        confidence=confidence,
        uncertainty=uncertainty,
        validation_status="approved",
        file_id=f"signal:{slug}",
        html_text=f"<html><body>{body_html}</body></html>",
        topic_labels=topic_labels,
        tag_labels=tag_labels,
        publisher_labels=publisher_labels,
        target_route=request.target_route,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="signal_publish_projection_complete",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "slug": projection.slug,
                "source_report_ids": projection.source_report_ids,
                "evidence_ids": projection.evidence_ids,
                "topic_ids": projection.topic_ids,
                "validation_status": projection.validation_status,
            },
        )
    )
    return projection
