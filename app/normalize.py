# app/normalize.py
from __future__ import annotations
from typing import Any

from .models import ReportPayload, Quote, Figure

def _s(x: Any) -> str:
    if x is None: return ""
    return x if isinstance(x, str) else str(x)

def normalize_report_payload(data: ReportPayload) -> ReportPayload:
    """
    Coerces the ReportPayload into the expected schema so downstream code and Jinja never crash.
    Ensures:
      - tldr/commentary/source are strings
      - insights is a list of exactly 5 strings (truncate/pad)
      - quote and figure have required keys as strings
    Returns a normalized ReportPayload.
    """
    # Normalize string fields
    tldr = _s(data.tldr)
    commentary = _s(data.commentary)
    source = _s(data.source)

    # Normalize insights → exactly 5 strings
    insights = data.insights or []
    if len(insights) < 5:
        insights = insights + [""] * (5 - len(insights))
    insights = insights[:5]
    # Coerce each insight to string
    insights = [_s(insight) for insight in insights]

    # Normalize quote
    quote = Quote(
        text=_s(data.quote.text),
        author=_s(data.quote.author)
    )

    # Normalize figure
    figure = Figure(
        title=_s(data.figure.title),
        evidence=_s(data.figure.evidence)
    )

    # Normalize optional fields
    _figure_gallery = data._figure_gallery or []
    _figure_top = _s(data._figure_top)
    _figure_image = _s(data._figure_image)

    # If a top figure path wasn't set but a selected figure image exists,
    # use it as the top figure so templates show it.
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
