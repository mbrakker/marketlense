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
    validate_signal_candidate_contract,
)
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPostGenerationRequest,
    SignalPublishProjection,
)
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.signal_post_generator")


def _unique_ordered(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value or "").strip()
        key = value.casefold()
        if value == "" or key in seen:
            continue
        seen.add(key)
        ordered.append(value)
    return ordered


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


def _body_html(
    *,
    projection_title: str,
    evidence: list[CrossReportEvidenceReference],
    sources: list[CrossReportSourceReportCandidate],
    uncertainty: str,
) -> str:
    evidence_items = "".join(
        "<li>"
        f"<strong>{html.escape(item.evidence_id)}</strong>: "
        f"{html.escape(item.text)} "
        f"<span>({html.escape(item.publisher)} / {html.escape(item.title)})</span>"
        "</li>"
        for item in evidence
    )
    source_items = "".join(
        "<li>" f"{html.escape(source.publisher)}: {html.escape(source.title)}" "</li>"
        for source in sources
    )
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
    uncertainty: str,
) -> str:
    group_by_id = {group.group_id: group for group in groups}
    candidate_items = "".join(
        "<li>"
        f"<strong>{html.escape(candidate.candidate_id)}</strong>: "
        f"{html.escape(candidate.summary)} "
        f"<span>({html.escape(candidate.support_level)} / "
        f"{html.escape(candidate.group_id)})</span>"
        "</li>"
        for candidate in candidates
    )
    group_items = "".join(
        "<li>"
        f"<strong>{html.escape(group.group_id)}</strong>: "
        f"{html.escape(group.summary)}"
        "</li>"
        for group in group_by_id.values()
    )
    source_items = "".join(
        "<li>" f"{html.escape(source.publisher)}: {html.escape(source.title)}" "</li>"
        for source in sources
    )
    return (
        '<article class="ml-signal-post">'
        f"<h1>{html.escape(projection_title)}</h1>"
        "<h2>Stored Signal candidates</h2>"
        f"<ul>{candidate_items}</ul>"
        "<h2>Signal groups</h2>"
        f"<ul>{group_items}</ul>"
        "<h2>Source reports</h2>"
        f"<ul>{source_items}</ul>"
        "<h2>Uncertainty</h2>"
        f"<p>{html.escape(uncertainty)}</p>"
        "</article>"
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
