from __future__ import annotations
import re
import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.services._render_service.normalization import (
    _build_tag_acronym_map,
    _s,
    _coerce_dict,
    _coerce_list,
    _coerce_positive_int,
    _pick_first_text,
    _split_summary_bullets,
    _sentence_excerpt,
    _build_core_signal,
    _extract_focus_year,
    _extract_fieldwork_dates,
    _REPORT_VALUE_DIMENSION_LABELS,
    _build_report_quality_score,
    _resolve_asset_path,
    _detect_asset_dimensions,
    _build_srcset,
    _build_media,
    _unwrap_doc_map,
    _build_report_identity_items,
    _coerce_claim_map,
    _coerce_insights,
    _coerce_quotes,
    _display_quote_author,
    _coerce_evidence_spans,
    _build_citation_micro_line,
    _public_citation_label,
    _coerce_topic_briefs,
    _coerce_chapters,
    _build_signal_cards,
    _is_visual_candidate_slide,
    _coerce_methodology,
    _coerce_coverage,
    _coerce_findings,
    _coerce_limitations,
    _coerce_contacts,
    _coerce_family_status,
)

from src.services._render_service.view import (
    _build_figure_slides,
    _build_render_view,
    _build_seo_title,
)

from src.services._render_service.workflow import (
    render_report,
)

logger = logging.getLogger("market_lense.render_service")
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
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

__all__ = [
    "_build_tag_acronym_map",
    "_s",
    "_coerce_dict",
    "_coerce_list",
    "_coerce_positive_int",
    "_pick_first_text",
    "_split_summary_bullets",
    "_sentence_excerpt",
    "_build_core_signal",
    "_extract_focus_year",
    "_extract_fieldwork_dates",
    "_REPORT_VALUE_DIMENSION_LABELS",
    "_build_report_quality_score",
    "_resolve_asset_path",
    "_detect_asset_dimensions",
    "_build_srcset",
    "_build_media",
    "_unwrap_doc_map",
    "_build_report_identity_items",
    "_coerce_claim_map",
    "_coerce_insights",
    "_coerce_quotes",
    "_display_quote_author",
    "_coerce_evidence_spans",
    "_build_citation_micro_line",
    "_public_citation_label",
    "_coerce_topic_briefs",
    "_coerce_chapters",
    "_build_signal_cards",
    "_is_visual_candidate_slide",
    "_coerce_methodology",
    "_coerce_coverage",
    "_coerce_findings",
    "_coerce_limitations",
    "_coerce_contacts",
    "_coerce_family_status",
    "_build_figure_slides",
    "_build_render_view",
    "_build_seo_title",
    "render_report",
]
