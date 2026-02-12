from __future__ import annotations

import logging
from typing import Any, List

from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.utils.logging import log_event
from src.services.schema_validator_service import validate_schema

logger = logging.getLogger("market_lense.normalize_generator")


def normalize_report(payload: ReportPayload, ctx: RunContext) -> ReportPayload:
    logger.info(log_event(
        ctx,
        role="generator",
        event="normalize_report_start",
        module=logger.name,
        fields={"payload": payload.to_dict()},
    ))
    normalized = _normalize_report_payload(payload)
    logger.info(log_event(
        ctx,
        role="generator",
        event="normalize_report_complete",
        module=logger.name,
        fields={"payload": normalized.to_dict()},
    ))
    return normalized


def validate_with_schema(payload: dict, schema_name: str, ctx: RunContext) -> None:
    """Validate an arbitrary payload against a named schema."""
    validate_schema(
        SchemaValidateRequest(schema_version="1.0", payload=payload, schema_name=schema_name),
        ctx,
    )


def _s(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _normalize_report_payload(data: ReportPayload) -> ReportPayload:
    tldr = _s(data.tldr)
    title = _s(data.title).strip()
    commentary = _s(data.commentary)
    source = _s(data.source)
    publisher = _s(data.publisher).strip()
    region = _s(data.region).strip()
    time_period = _s(data.time_period).strip()
    taxonomy_raw = data.taxonomy or []
    taxonomy = []
    seen = set()
    for item in taxonomy_raw:
        item_s = _s(item).strip()
        if not item_s:
            continue
        key = item_s.lower()
        if key in seen:
            continue
        seen.add(key)
        taxonomy.append(item_s)
    categories_raw = data.categories or []
    categories = []
    seen_categories = set()
    for item in categories_raw:
        item_s = _s(item).strip()
        if not item_s:
            continue
        key = item_s.lower()
        if key in seen_categories:
            continue
        seen_categories.add(key)
        categories.append(item_s)

    insights: List[str] = data.insights or []
    if len(insights) < 5:
        insights = insights + [""] * (5 - len(insights))
    insights = insights[:5]
    insights = [_s(insight) for insight in insights]

    quote = Quote(
        text=_s(data.quote.text),
        author=_s(data.quote.author),
    )

    figure = Figure(
        title=_s(data.figure.title),
        evidence=_s(data.figure.evidence),
    )

    contents_page_number = data.contents_page_number if isinstance(data.contents_page_number, int) and data.contents_page_number >= 0 else 0
    contents_heading = _s(data.contents_heading)

    _figure_gallery = data._figure_gallery or []
    _figure_top = _s(data._figure_top)
    _figure_image = _s(data._figure_image)
    _contents_image = _s(data._contents_image)

    if not _figure_top and _figure_image:
        _figure_top = _figure_image

    return ReportPayload(
        tldr=tldr,
        title=title,
        insights=insights,
        quote=quote,
        figure=figure,
        publisher=publisher,
        taxonomy=taxonomy,
        categories=categories,
        region=region,
        time_period=time_period,
        commentary=commentary,
        source=source,
        _figure_image=_figure_image,
        _figure_gallery=_figure_gallery,
        _figure_top=_figure_top,
        contents_page_number=contents_page_number,
        contents_heading=contents_heading,
        _contents_image=_contents_image,
    )
