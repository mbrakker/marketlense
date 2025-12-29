from __future__ import annotations

import logging
from typing import Any

from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.normalize import NormalizeRequest, NormalizeResponse
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.normalize_service")


def normalize_report(request: NormalizeRequest, ctx: RunContext) -> NormalizeResponse:
    log_event(
        logger,
        ctx,
        role="service",
        event="normalize_report_start",
        fields={},
    )
    payload = _normalize_report_payload(request.payload)
    log_event(
        logger,
        ctx,
        role="service",
        event="normalize_report_complete",
        fields={},
    )
    return NormalizeResponse(schema_version="1.0", payload=payload)


def _s(x: Any) -> str:
    if x is None:
        return ""
    return x if isinstance(x, str) else str(x)


def _normalize_report_payload(data: ReportPayload) -> ReportPayload:
    tldr = _s(data.tldr)
    commentary = _s(data.commentary)
    source = _s(data.source)

    insights = data.insights or []
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

    _figure_gallery = data._figure_gallery or []
    _figure_top = _s(data._figure_top)
    _figure_image = _s(data._figure_image)

    if not _figure_top and _figure_image:
        _figure_top = _figure_image

    return ReportPayload(
        tldr=tldr,
        insights=insights,
        quote=quote,
        figure=figure,
        commentary=commentary,
        source=source,
        _openai_file_id=_s(data._openai_file_id),
        _figure_image=_figure_image,
        _figure_gallery=_figure_gallery,
        _figure_top=_figure_top,
    )
