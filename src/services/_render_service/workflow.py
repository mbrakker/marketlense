from __future__ import annotations

import logging
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.contracts.files import WriteBytesRequest
from src.contracts.report_assets import RenderRequest, RenderResponse
from src.contracts.run_context import RunContext
from src.services import file_service
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.slugify import slugify

from .normalization import (
    _build_tag_acronym_map,
)
from .view import (
    _build_render_view,
    _build_seo_title,
)

logger = logging.getLogger("market_lense.render_service")
TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"
JINJA_ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)
_MONTH_PATTERN = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{4}\b",
    re.IGNORECASE,
)
_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
_ISO_DATE_PATTERN = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


def render_report(request: RenderRequest, ctx: RunContext) -> RenderResponse:
    tag_acronym_map = _build_tag_acronym_map(request.tag_acronyms)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="render_html_start",
            module=logger.name,
            fields={
                "doc_name": request.doc_name,
                "file_id": request.file_id,
                "tag_acronyms_count": len(tag_acronym_map),
            },
        )
    )
    view = _build_render_view(request, tag_acronym_map)
    view["seo"]["title"] = _build_seo_title(
        view["report_title"],
        view["focus_year"],
        view["publisher"],
    )
    json_ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": view["report_title"],
        "description": view["seo"]["description"],
        "author": {"@type": "Organization", "name": view["publisher"]}
        if view["publisher"]
        else None,
        "publisher": {"@type": "Organization", "name": view["publisher"]}
        if view["publisher"]
        else None,
        "mainEntityOfPage": view["canonical_url"] if view["canonical_url"] else None,
        "image": [view["seo"]["primary_image"]] if view["seo"]["primary_image"] else [],
        "articleSection": view["topics"],
        "keywords": view["json_ld_keywords"],
    }
    html = JINJA_ENV.get_template("report.html.j2").render(
        data=request.data,
        view=view,
        doc_name=request.doc_name,
        title=f"{view['report_title']} - Digest",
        report_title=view["report_title"],
        preview_png=request.preview_png,
        tag_acronym_map=tag_acronym_map,
        json_ld=json_ld,
    )
    report_name = slugify(request.doc_name)
    out_dir = Path(request.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{report_name}.html"
    try:
        file_service.write_bytes(
            WriteBytesRequest(
                schema_version="1.0",
                path=str(out_path),
                content=html.encode("utf-8"),
            ),
            ctx,
        )
    except AppError as exc:
        raise AppError(
            code="render_html_write_failed",
            message="Failed to write rendered HTML report",
            cause=exc,
            retryable=False,
            context={"out_path": str(out_path)},
        ) from exc
    html_path = str(out_path)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="render_html_complete",
            module=logger.name,
            fields={"html_path": html_path},
        )
    )
    return RenderResponse(schema_version="1.0", html_path=html_path)


__all__ = [
    "render_report",
]
