"""Cross-report publish HTML assembly.

This module owns presentation assembly separately from synthesis and validation so
the cross-report generator can keep model adaptation, contract checks, and HTML
layout concerns independent.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

from src.contracts.cross_report_analysis import (
    CrossReportEvidenceAgreementResult,
    CrossReportGeneratedAnalysisResult,
)
from src.contracts.publish import PublishEntityMetadata
from src.utils.html_utils import publish_entity_metadata_script

_CROSS_REPORT_DOCUMENT_CSS = """
body {
  margin: 0;
  color: #162339;
  background: linear-gradient(180deg, #eef2f8 0%, #f0f4fb 100%);
  font-family: "Iowan Old Style", "Baskerville", "Times New Roman", serif;
  line-height: 1.62;
}
.ml-ingest-report-content * {
  box-sizing: border-box;
}
.ml-ingest-report-content a {
  color: #0d3b66;
}
.ml-ingest-report-content .page-shell {
  max-width: 1180px;
  margin: 24px auto 58px;
  padding: 0 20px;
}
.ml-ingest-report-content .report {
  background: #ffffff;
  border: 1px solid #cdd9ea;
  border-radius: 18px;
  box-shadow: 0 18px 44px rgba(11, 31, 56, 0.12);
  overflow: visible;
}
.ml-ingest-report-content .hero {
  border-bottom: 1px solid #d6e0ed;
  background: linear-gradient(130deg, #f7fbff 0%, #ebf2ff 52%, #f7efe3 100%);
}
.ml-ingest-report-content .hero-split {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 22px;
  padding: 28px 30px 22px;
}
.ml-ingest-report-content .eyebrow,
.ml-ingest-report-content .panel-kicker,
.ml-ingest-report-content .meta-label,
.ml-ingest-report-content .fact-label {
  color: #2c4f77;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-size: 0.76rem;
  font-family: "Trebuchet MS", "Segoe UI", Tahoma, sans-serif;
  font-weight: 700;
}
.ml-ingest-report-content h1 {
  margin: 0 0 0.62rem;
  font-size: clamp(1.85rem, 3.2vw, 2.7rem);
  line-height: 1.1;
}
.ml-ingest-report-content h2 {
  margin: 0 0 0.72rem;
  font-size: 1.48rem;
  line-height: 1.18;
  font-family: "Avenir Next", "Segoe UI", Tahoma, sans-serif;
}
.ml-ingest-report-content h3 {
  margin: 0 0 7px;
  font-size: 1rem;
  line-height: 1.35;
  font-family: "Trebuchet MS", "Segoe UI", Tahoma, sans-serif;
}
.ml-ingest-report-content .report-identity,
.ml-ingest-report-content .hero-subtitle,
.ml-ingest-report-content .muted,
.ml-ingest-report-content .citation-micro {
  color: #4f6078;
}
.ml-ingest-report-content .hero-subtitle {
  margin: 0 0 1rem;
  font-size: 1.02rem;
}
.ml-ingest-report-content .hero-subtitle-line {
  display: block;
  margin: 0 0 2px;
}
.ml-ingest-report-content .hero-subtitle-label {
  font-weight: 700;
}
.ml-ingest-report-content .hero-meta,
.ml-ingest-report-content .chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.ml-ingest-report-content .hero-meta li,
.ml-ingest-report-content .chip {
  border: 1px solid #bfd1e8;
  border-radius: 999px;
  padding: 5px 11px;
  font-size: 0.78rem;
  color: #20456d;
  background: rgba(255, 255, 255, 0.7);
  font-family: "Avenir Next", "Segoe UI", Tahoma, sans-serif;
}
.ml-ingest-report-content .hero-brief {
  border: 1px solid #bfd1e8;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.72);
  padding: 18px;
  box-shadow: 0 10px 26px rgba(13, 59, 102, 0.10);
}
.ml-ingest-report-content .hero-brief strong {
  display: block;
  margin-bottom: 7px;
  font-family: "Avenir Next", "Segoe UI", Tahoma, sans-serif;
}
.ml-ingest-report-content .sticky-nav {
  position: sticky;
  top: 0;
  z-index: 90;
  border-bottom: 1px solid #d6e0ed;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(12px);
}
.ml-ingest-report-content .reading-progress {
  height: 3px;
  background: rgba(13, 59, 102, 0.1);
}
.ml-ingest-report-content .reading-progress span {
  display: block;
  width: 34%;
  height: 100%;
  background: linear-gradient(90deg, #0d3b66 0%, #f4b942 100%);
}
.ml-ingest-report-content .section-nav {
  padding: 10px 24px;
}
.ml-ingest-report-content .nav-scroll {
  overflow-x: auto;
  padding: 4px 0;
}
.ml-ingest-report-content .nav-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: nowrap;
  gap: 7px;
  min-width: max-content;
}
.ml-ingest-report-content .nav-list a {
  display: inline-block;
  border: 1px solid #c4d6ea;
  background: rgba(255, 255, 255, 0.86);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 0.88rem;
  color: #1c446f;
  text-decoration: none;
  font-family: "Avenir Next", "Segoe UI", Tahoma, sans-serif;
  font-weight: 600;
}
.ml-ingest-report-content .content {
  padding: 24px 30px 30px;
}
.ml-ingest-report-content .panel {
  position: relative;
  border: 1px solid #d6e0ed;
  border-radius: 16px;
  background: #fff;
  padding: 20px 20px 18px;
  margin: 0 0 16px;
}
.ml-ingest-report-content .panel::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  border-top-left-radius: 15px;
  border-bottom-left-radius: 15px;
  background: #b2c7de;
}
.ml-ingest-report-content .panel[data-tone="summary"]::before {
  background: linear-gradient(180deg, #0d3b66 0%, #3877b3 100%);
}
.ml-ingest-report-content .panel[data-tone="insights"]::before {
  background: linear-gradient(180deg, #1a6f4f 0%, #38a169 100%);
}
.ml-ingest-report-content .panel[data-tone="quotes"]::before {
  background: linear-gradient(180deg, #915019 0%, #d18a44 100%);
}
.ml-ingest-report-content .panel-header {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-end;
  margin-bottom: 16px;
}
.ml-ingest-report-content .summary-copy {
  margin: 0;
  font-size: 1.03rem;
}
.ml-ingest-report-content .fact-grid,
.ml-ingest-report-content .editorial-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 10px;
}
.ml-ingest-report-content .fact-card,
.ml-ingest-report-content .editorial-card,
.ml-ingest-report-content .insight-card {
  border: 1px solid #d4e1f1;
  border-radius: 8px;
  background: linear-gradient(180deg, #f8fbff 0%, #f1f7ff 100%);
  padding: 14px;
}
.ml-ingest-report-content .fact-value {
  margin: 4px 0 0;
}
.ml-ingest-report-content .insight-grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 12px;
}
.ml-ingest-report-content .insight-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.ml-ingest-report-content .insight-index {
  flex: 0 0 auto;
  min-width: 30px;
  height: 30px;
  border-radius: 50%;
  background: #0d3b66;
  color: #fff;
  text-align: center;
  line-height: 30px;
  font-family: "Trebuchet MS", "Segoe UI", Tahoma, sans-serif;
  font-size: 0.82rem;
  font-weight: 700;
}
.ml-ingest-report-content .prose-block {
  display: grid;
  gap: 11px;
  margin: 0;
}
.ml-ingest-report-content .prose-paragraph,
.ml-ingest-report-content .insight-text {
  margin: 0;
}
.ml-ingest-report-content .citation-micro {
  margin-top: 8px;
  font-size: 0.82rem;
  font-family: "Avenir Next", "Segoe UI", Tahoma, sans-serif;
}
.ml-ingest-report-content .resource-list {
  margin: 0;
  padding-left: 18px;
}
.ml-ingest-report-content .resource-list li {
  margin-bottom: 6px;
}
.ml-ingest-report-content code {
  background: #edf3f9;
  border-radius: 6px;
  padding: 0.12rem 0.32rem;
  font-family: "Consolas", "SFMono-Regular", monospace;
  font-size: 0.92em;
}
.ml-ingest-report-content .footer {
  border-top: 1px solid #d6e0ed;
  color: #4f6078;
  padding: 18px 24px 22px;
  font-size: 0.92rem;
}
@media (max-width: 860px) {
  .ml-ingest-report-content .hero-split {
    grid-template-columns: 1fr;
  }
  .ml-ingest-report-content .content {
    padding: 18px 14px 28px;
  }
}
"""

_INTERNAL_EVIDENCE_REF_RE = re.compile(
    r"\b[A-Za-z0-9_-]+:(?:claim|finding|quote):[A-Za-z0-9_.-]+\b"
)


def build_cross_report_html_document(
    *,
    generated: CrossReportGeneratedAnalysisResult,
    agreement_result: CrossReportEvidenceAgreementResult,
    source_metadata: list[dict[str, Any]],
    machine_metadata: dict[str, Any],
    file_id: str,
    publish_entity_metadata: PublishEntityMetadata,
) -> tuple[str, str]:
    body = "\n".join(
        [
            '<div class="ml-ingest-report-content">',
            '<div class="page-shell">',
            '<article class="report ml-cross-report-analysis">',
            _hero_html(generated, source_metadata),
            _nav_html(generated),
            '<main class="content" id="cross-report-content">',
            _summary_html(generated, source_metadata),
            _analysis_sections_html(generated),
            _source_map_html(source_metadata),
            _agreement_html(agreement_result, generated),
            _evidence_html(generated),
            _raw_metric_html(generated),
            _metadata_script(machine_metadata),
            f"<p hidden>Drive fileId: {_html_text(file_id)}</p>",
            "</main>",
            (
                '<footer class="footer">Generated by Market Lense. '
                f"File ID: <code>{_html_text(file_id)}</code>.</footer>"
            ),
            "</article>",
            "</div>",
            "</div>",
        ]
    )
    document = (
        "<!doctype html><html><head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta name="description" content="{_html_text(generated.executive_summary[:180])}">'
        f"{publish_entity_metadata_script(publish_entity_metadata)}"
        f"<title>{_html_text(generated.title)}</title>"
        f"<style>{_CROSS_REPORT_DOCUMENT_CSS}</style>"
        "</head><body>"
        f"{body}"
        "</body></html>"
    )
    return body, document


def _html_text(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _metadata_script(metadata: dict[str, Any]) -> str:
    metadata_json = json.dumps(
        metadata,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return (
        '<script type="application/json" '
        'data-market-lense-cross-report-metadata="true">'
        f"{html.escape(metadata_json, quote=False)}</script>"
    )


def _public_reference_text(
    value: Any,
    *,
    evidence_references: dict[str, str] | None = None,
    raw_metric_references: dict[str, str] | None = None,
) -> str:
    text = str(value or "")
    replacements = {
        **(evidence_references or {}),
        **(raw_metric_references or {}),
    }
    for source_id in sorted(replacements, key=len, reverse=True):
        label = str(replacements.get(source_id) or "").strip() or "source evidence"
        text = re.sub(
            rf"(?<![\w:-]){re.escape(source_id)}(?![\w:-])",
            label,
            text,
        )
    return _INTERNAL_EVIDENCE_REF_RE.sub("source evidence", text)


def _prose_html(
    value: Any,
    *,
    evidence_references: dict[str, str] | None = None,
    raw_metric_references: dict[str, str] | None = None,
) -> str:
    text = _public_reference_text(
        value,
        evidence_references=evidence_references,
        raw_metric_references=raw_metric_references,
    )
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return '<p class="muted">Not available from supplied evidence.</p>'
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    paragraphs = lines if len(lines) > 1 else [text]
    return "".join(
        f'<p class="prose-paragraph">{_html_text(paragraph)}</p>'
        for paragraph in paragraphs
    )


def _coerce_pages(metadata: dict[str, Any]) -> list[int]:
    pages: list[int] = []
    for raw_page in metadata.get("pages") or []:
        try:
            page = int(raw_page)
        except (TypeError, ValueError):
            continue
        if page > 0 and page not in pages:
            pages.append(page)
    try:
        page = int(metadata.get("page"))
    except (TypeError, ValueError):
        page = 0
    if page > 0 and page not in pages:
        pages.append(page)
    return pages


def _grounding_reference(title: str, metadata: dict[str, Any]) -> str:
    pages = _coerce_pages(metadata)
    title_text = str(title or "").strip()
    if pages:
        page_label = "page" if len(pages) == 1 else "pages"
        page_text = f"{page_label} {', '.join(str(page) for page in pages)}"
        return f"{title_text}, {page_text}" if title_text else page_text
    return title_text


def _evidence_reference_map(
    generated: CrossReportGeneratedAnalysisResult,
) -> dict[str, str]:
    return {
        evidence.evidence_id: _grounding_reference(
            evidence.title,
            dict(evidence.source_metadata or {}),
        )
        for evidence in generated.evidence
    }


def _raw_metric_reference_map(
    generated: CrossReportGeneratedAnalysisResult,
) -> dict[str, str]:
    return {
        metric.metric_id: _grounding_reference(
            next(
                (
                    source.title
                    for source in generated.selected_sources
                    if source.report_id == metric.report_id
                ),
                metric.report_id,
            ),
            dict(metric.source_metadata or {}),
        )
        for metric in generated.raw_metrics
    }


def _citation_line(
    *,
    evidence_ids: list[str],
    raw_metric_ids: list[str] | None = None,
    evidence_references: dict[str, str] | None = None,
    raw_metric_references: dict[str, str] | None = None,
) -> str:
    parts: list[str] = []
    evidence_labels = _unique_ordered(
        [
            (evidence_references or {}).get(evidence_id, "")
            for evidence_id in evidence_ids
        ]
    )
    if evidence_labels:
        parts.append("Evidence: " + "; ".join(evidence_labels))
    if raw_metric_ids:
        metric_labels = _unique_ordered(
            [
                (raw_metric_references or {}).get(metric_id, "")
                for metric_id in raw_metric_ids
            ]
        )
        if metric_labels:
            parts.append("Raw metrics: " + "; ".join(metric_labels))
    return " | ".join(parts)


def _unique_ordered(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value or "").strip()
        if not value or value.casefold() in seen:
            continue
        seen.add(value.casefold())
        ordered.append(value)
    return ordered


def _chip_list_html(values: list[str]) -> str:
    chips = "".join(
        f'<li class="chip">{_html_text(value)}</li>'
        for value in _unique_ordered(values)
    )
    if not chips:
        return '<p class="muted">No taxonomy tags supplied.</p>'
    return f'<ul class="chip-list">{chips}</ul>'


def _publisher_count(source_metadata: list[dict[str, Any]]) -> int:
    return len(
        {
            str(item.get("publisher") or "").strip().casefold()
            for item in source_metadata
            if str(item.get("publisher") or "").strip()
        }
    )


def _hero_html(
    generated: CrossReportGeneratedAnalysisResult,
    source_metadata: list[dict[str, Any]],
) -> str:
    evidence_references = _evidence_reference_map(generated)
    raw_metric_references = _raw_metric_reference_map(generated)
    publisher_count = _publisher_count(source_metadata)
    source_count = len(source_metadata)
    evidence_count = len(generated.evidence)
    raw_metric_count = len(generated.raw_metrics)
    theme_label = generated.selected_theme.label or generated.selected_theme.theme_id
    categories = _unique_ordered(
        [
            category
            for source in generated.selected_sources
            for category in source.category_labels
        ]
    )
    tags = _unique_ordered(
        [tag for source in generated.selected_sources for tag in source.tags]
    )
    hero_meta = "".join(
        f"<li>{_html_text(item)}</li>"
        for item in (
            f"{source_count} source reports",
            f"{publisher_count} publishers",
            f"{evidence_count} evidence references",
            f"{raw_metric_count} raw metrics",
        )
    )
    taxonomy = _chip_list_html([*categories, *tags])
    return "\n".join(
        [
            '<header class="hero">',
            '<div class="hero-split">',
            '<div class="hero-copy">',
            '<p class="eyebrow">Market Lense cross-report intelligence</p>',
            f"<h1>{_html_text(generated.title)}</h1>",
            f'<p class="report-identity">Theme: {_html_text(theme_label)}</p>',
            '<p class="hero-subtitle">',
            (
                '<span class="hero-subtitle-line">'
                '<span class="hero-subtitle-label">Analysis type:</span> '
                "Cross-report evidence synthesis</span>"
            ),
            (
                '<span class="hero-subtitle-line">'
                '<span class="hero-subtitle-label">Coverage:</span> '
                f"{_html_text(source_count)} reports from "
                f"{_html_text(publisher_count)} publishers</span>"
            ),
            "</p>",
            f'<ul class="hero-meta">{hero_meta}</ul>',
            "</div>",
            '<aside class="hero-brief" aria-label="Executive brief">',
            "<strong>Executive synthesis</strong>",
            (
                '<div class="prose-block">'
                f"{_prose_html(generated.executive_summary, evidence_references=evidence_references, raw_metric_references=raw_metric_references)}"
                "</div>"
            ),
            '<div style="margin-top: 14px">',
            '<span class="meta-label">Topic signals</span>',
            taxonomy,
            "</div>",
            "</aside>",
            "</div>",
            "</header>",
        ]
    )


def _nav_html(generated: CrossReportGeneratedAnalysisResult) -> str:
    metric_link = (
        '<li><a href="#section-metrics" data-section-link>Metrics</a></li>'
        if generated.raw_metrics
        else ""
    )
    return "\n".join(
        [
            '<div class="sticky-nav">',
            '<div class="reading-progress" aria-hidden="true"><span></span></div>',
            '<nav class="section-nav" aria-label="Cross-report sections">',
            '<div class="nav-scroll">',
            '<ul class="nav-list">',
            '<li><a href="#section-summary" data-section-link>Executive synthesis</a></li>',
            '<li><a href="#section-insights" data-section-link>Strategic read-through</a></li>',
            '<li><a href="#section-sources" data-section-link>Sources</a></li>',
            '<li><a href="#section-uncertainty" data-section-link>Uncertainty</a></li>',
            '<li><a href="#section-evidence" data-section-link>Evidence</a></li>',
            metric_link,
            "</ul>",
            "</div>",
            "</nav>",
            "</div>",
        ]
    )


def _summary_html(
    generated: CrossReportGeneratedAnalysisResult,
    source_metadata: list[dict[str, Any]],
) -> str:
    evidence_references = _evidence_reference_map(generated)
    raw_metric_references = _raw_metric_reference_map(generated)
    facts = [
        ("Selected reports", str(len(source_metadata))),
        ("Distinct publishers", str(_publisher_count(source_metadata))),
        ("Evidence references", str(len(generated.evidence))),
        ("Raw metric appendix", str(len(generated.raw_metrics))),
    ]
    fact_cards = "".join(
        (
            '<article class="fact-card">'
            f'<span class="fact-label">{_html_text(label)}</span>'
            f'<p class="fact-value">{_html_text(value)}</p>'
            "</article>"
        )
        for label, value in facts
    )
    return "\n".join(
        [
            (
                '<section class="panel" id="section-summary" data-tone="summary" '
                'aria-label="Executive synthesis">'
            ),
            '<div class="panel-header"><div>',
            '<p class="panel-kicker">Lead takeaway</p>',
            "<h2>Executive synthesis</h2>",
            "</div></div>",
            (
                '<div class="summary-copy prose-block">'
                f"{_prose_html(generated.executive_summary, evidence_references=evidence_references, raw_metric_references=raw_metric_references)}"
                "</div>"
            ),
            f'<div class="fact-grid" style="margin-top: 18px">{fact_cards}</div>',
            "</section>",
        ]
    )


def _analysis_sections_html(generated: CrossReportGeneratedAnalysisResult) -> str:
    cards: list[str] = []
    evidence_references = _evidence_reference_map(generated)
    raw_metric_references = _raw_metric_reference_map(generated)
    for index, section in enumerate(generated.sections, start=1):
        citation = _citation_line(
            evidence_ids=section.evidence_ids,
            raw_metric_ids=section.raw_metric_ids,
            evidence_references=evidence_references,
            raw_metric_references=raw_metric_references,
        )
        citation_html = (
            f'<div class="citation-micro">{_html_text(citation)}</div>'
            if citation
            else ""
        )
        cards.append(
            "\n".join(
                [
                    (
                        '<li class="insight-card" '
                        'data-cross-report-section="true" '
                        f'id="{_html_text(section.section_id)}">'
                    ),
                    '<div class="insight-head">',
                    f'<span class="insight-index">{index}</span>',
                    "<div>",
                    f"<h3>{_html_text(section.heading)}</h3>",
                    (
                        '<div class="insight-text prose-block">'
                        f"{_prose_html(section.body, evidence_references=evidence_references, raw_metric_references=raw_metric_references)}"
                        "</div>"
                    ),
                    citation_html,
                    "</div>",
                    "</div>",
                    "</li>",
                ]
            )
        )
    return "\n".join(
        [
            (
                '<section class="panel" id="section-insights" data-tone="insights" '
                'aria-label="Strategic read-through">'
            ),
            '<div class="panel-header"><div>',
            '<p class="panel-kicker">Consulting-grade synthesis</p>',
            "<h2>Strategic read-through</h2>",
            "</div></div>",
            f'<ol class="insight-grid">{"".join(cards)}</ol>',
            "</section>",
        ]
    )


def _source_map_html(source_metadata: list[dict[str, Any]]) -> str:
    cards: list[str] = []
    for item in source_metadata:
        source_url = str(item.get("source_url") or "").strip()
        title = _html_text(item["title"])
        title_html = (
            f'<h3><a href="{_html_text(source_url)}" rel="noopener" target="_blank">{title}</a></h3>'
            if source_url
            else f"<h3>{title}</h3>"
        )
        cards.append(
            "\n".join(
                [
                    (
                        '<article class="editorial-card" '
                        f'data-report-id="{_html_text(item["report_id"])}">'
                    ),
                    title_html,
                    (
                        '<p class="fact-value">'
                        f"{_html_text(item['publisher'])} | "
                        f"{_html_text(item['report_date'])}</p>"
                    ),
                    (
                        '<div class="citation-micro">'
                        f"Rank {_html_text(item['rank'])} | "
                        f"evidence items: {_html_text(item['evidence_count'])}</div>"
                    ),
                    "</article>",
                ]
            )
        )
    return "\n".join(
        [
            '<section class="panel" id="section-sources" aria-label="Source report map">',
            '<div class="panel-header"><div>',
            '<p class="panel-kicker">Consulting-style source appendix</p>',
            "<h2>Source report map</h2>",
            "</div></div>",
            f'<div class="editorial-grid">{"".join(cards)}</div>',
            "</section>",
        ]
    )


def _evidence_html(generated: CrossReportGeneratedAnalysisResult) -> str:
    items = [
        "<li>"
        f"<strong>{_html_text(evidence.publisher)}</strong>, "
        f"{_html_text(_grounding_reference(evidence.title, dict(evidence.source_metadata or {})))}: "
        f"{_html_text(evidence.text)}"
        "</li>"
        for evidence in generated.evidence
    ]
    return "\n".join(
        [
            '<section class="panel" id="section-evidence" aria-label="Evidence references">',
            '<div class="panel-header"><div>',
            '<p class="panel-kicker">Audit trail</p>',
            "<h2>Evidence references</h2>",
            "</div></div>",
            f'<ol class="resource-list">{"".join(items)}</ol>',
            "</section>",
        ]
    )


def _raw_metric_html(generated: CrossReportGeneratedAnalysisResult) -> str:
    metric_references = _raw_metric_reference_map(generated)
    items = [
        "<li>"
        f"<strong>{_html_text(metric.publisher)}</strong>: "
        f"{_html_text(metric.label)} = {_html_text(metric.raw_value)} "
        f"{_html_text(metric.unit)}"
        f"{' (' + _html_text(metric_references[metric.metric_id]) + ')' if metric_references.get(metric.metric_id) else ''}"
        "</li>"
        for metric in generated.raw_metrics
    ]
    item_html = (
        f'<ul class="resource-list">{"".join(items)}</ul>'
        if items
        else '<p class="muted">No source-specific raw metrics were supplied.</p>'
    )
    return "\n".join(
        [
            '<section class="panel" id="section-metrics" aria-label="Raw metric appendix">',
            '<div class="panel-header"><div>',
            '<p class="panel-kicker">Source-bound metrics</p>',
            "<h2>Raw metric appendix</h2>",
            "</div></div>",
            item_html,
            "</section>",
        ]
    )


def _agreement_html(
    agreement_result: CrossReportEvidenceAgreementResult,
    generated: CrossReportGeneratedAnalysisResult,
) -> str:
    evidence_lookup = _evidence_reference_map(generated)
    items = [
        "<li>"
        f"<strong>{_html_text(group.agreement_type)}</strong>: "
        f"{_html_text(group.label)}"
        f" | evidence: {_html_text('; '.join(_unique_ordered([evidence_lookup.get(evidence_id, '') for evidence_id in group.evidence_ids])))}"
        f" | notes: {_html_text(', '.join(group.uncertainty_reasons))}"
        "</li>"
        for group in agreement_result.evidence_groups
    ]
    item_html = (
        f'<ul class="resource-list">{"".join(items)}</ul>'
        if items
        else '<p class="muted">No uncertainty groups were supplied.</p>'
    )
    return "\n".join(
        [
            (
                '<section class="panel" id="section-uncertainty" data-tone="quotes" '
                'aria-label="Uncertainty and divergence notes">'
            ),
            '<div class="panel-header"><div>',
            '<p class="panel-kicker">Caveats and disagreement</p>',
            "<h2>Uncertainty and divergence notes</h2>",
            "</div></div>",
            item_html,
            "</section>",
        ]
    )
