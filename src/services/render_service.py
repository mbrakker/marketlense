from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from src.contracts.report_assets import RenderRequest, RenderResponse
from src.contracts.run_context import RunContext
from src.utils.logging import log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.render_service")


def render_report(request: RenderRequest, ctx: RunContext) -> RenderResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="render_html_start",
        module=logger.name,
        fields={"doc_name": request.doc_name, "file_id": request.file_id},
    ))
    templates_dir = (Path(__file__).resolve().parents[2] / "templates")
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    report_title = str(request.data.get("title") or request.doc_name)
    html = env.get_template("report.html.j2").render(
        data=request.data,
        doc_name=request.doc_name,
        file_id=request.file_id,
        title=f"{report_title} - Digest",
        report_title=report_title,
        preview_png=request.preview_png,
    )
    report_name = slugify(request.doc_name)
    out_path = Path(request.out_dir) / f"{report_name}.html"
    out_path.write_text(html, encoding="utf-8")
    html_path = str(out_path)
    logger.info(log_event(
        ctx,
        role="service",
        event="render_html_complete",
        module=logger.name,
        fields={"html_path": html_path},
    ))
    return RenderResponse(schema_version="1.0", html_path=html_path)
