from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.contracts.report_assets import RenderRequest

from .normalization import (
    _build_core_signal,
    _build_media,
    _build_report_identity_items,
    _build_report_quality_score,
    _build_signal_cards,
    _coerce_chapters,
    _coerce_claim_map,
    _coerce_contacts,
    _coerce_coverage,
    _coerce_dict,
    _coerce_family_status,
    _coerce_findings,
    _coerce_insights,
    _coerce_limitations,
    _coerce_list,
    _coerce_methodology,
    _coerce_public_advisory,
    _coerce_public_chart_insight_cards,
    _coerce_public_key_figures,
    _coerce_public_topics_covered,
    _coerce_quotes,
    _coerce_topic_briefs,
    _extract_fieldwork_dates,
    _extract_focus_year,
    _is_visual_candidate_slide,
    _pick_first_text,
    _s,
    _sanitize_public_prose,
    _split_summary_bullets,
    _unwrap_doc_map,
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


def _build_figure_slides(
    data: dict[str, Any], out_dir: Path, report_title: str
) -> list[dict[str, Any]]:
    figure_assets = _coerce_list(data.get("_figure_assets"))
    slides: list[dict[str, Any]] = []
    cards_by_candidate = {
        _s(candidate_card.get("candidate_id")): candidate_card
        for raw_card in _coerce_list(
            _coerce_dict(data.get("artifacts")).get("chart_insight_cards")
        )
        if (candidate_card := _coerce_dict(raw_card))
        and _s(candidate_card.get("status")).casefold()
        not in {
            "abstained",
            "limited",
            "not_applicable",
            "omitted",
            "text_only",
            "unavailable",
            "weak",
            "weak_evidence",
        }
        and candidate_card.get("crop_qa_accepted") is True
        and _s(candidate_card.get("candidate_id"))
        and _s(candidate_card.get("evidence_id"))
        and _s(candidate_card.get("insight_id"))
        and _s(candidate_card.get("caption"))
        and _s(candidate_card.get("public_takeaway"))
        and candidate_card.get("source_page") is not None
    }
    for raw_asset in figure_assets:
        asset = _coerce_dict(raw_asset)
        candidate_id = _s(asset.get("candidate_id"))
        card = cards_by_candidate.get(candidate_id)
        image_path = _s(asset.get("image_path"))
        page = asset.get("page")
        if (
            asset.get("crop_qa_accepted") is not True
            or not image_path
            or card is None
            or page is None
            or str(page) != str(card.get("source_page"))
        ):
            continue
        index = len(slides) + 1
        is_primary = not slides
        caption = _s(card.get("caption"))
        slides.append(
            {
                **_build_media(
                    relative_path=image_path,
                    out_dir=out_dir,
                    alt=(
                        f"Selected figure from {report_title}"
                        if is_primary
                        else f"Additional figure {index} from {report_title}"
                    ),
                    default_width=1600,
                    default_height=900,
                    sizes="(max-width: 800px) 100vw, 980px",
                    caption=caption,
                ),
                "caption": caption,
                "page": int(page),
                "kind": _s(asset.get("kind")),
                "candidate_id": candidate_id,
                "is_primary": is_primary,
                "thumb": _build_media(
                    relative_path=image_path,
                    out_dir=out_dir,
                    alt=f"Figure thumbnail {index}",
                    default_width=320,
                    default_height=180,
                    sizes="84px",
                ),
            }
        )
    return slides


def _build_render_view(
    request: RenderRequest, tag_acronym_map: dict[str, str]
) -> dict[str, Any]:
    data = request.data
    out_dir = Path(request.out_dir)
    artifacts = _coerce_dict(data.get("artifacts"))
    summary = _coerce_dict(artifacts.get("summary"))
    source_status = _coerce_dict(artifacts.get("source_status"))
    evidence_packs = _coerce_dict(data.get("evidence_packs"))
    doc_map = _unwrap_doc_map(evidence_packs.get("doc_map"))
    report_title = _normalize_public_title(
        _pick_first_text(data.get("title"), doc_map.get("title"))
    )
    publisher = _pick_first_text(
        data.get("publisher"),
        doc_map.get("publisher"),
        _coerce_dict(doc_map.get("publisher")).get("name"),
    )
    report_author = _s(data.get("report_identity_author"))
    region = _s(data.get("region"))
    time_period = _s(data.get("time_period"))
    focus_year = _extract_focus_year(
        time_period, doc_map.get("year"), doc_map.get("publicationDate"), report_title
    )
    methodology_items = _coerce_methodology(doc_map, evidence_packs)
    fieldwork_dates = _extract_fieldwork_dates(
        time_period,
        *methodology_items,
        _s(summary.get("executive_summary")),
        _s(doc_map.get("methodology")),
    )
    tldr_text = _sanitize_public_prose(
        _pick_first_text(summary.get("tldr"), data.get("tldr"))
    )
    not_available = bool(
        source_status.get("not_available")
        if "not_available" in source_status
        else data.get("_text_not_available")
    )
    if not tldr_text and not_available:
        tldr_text = "Not available from text."
    executive_summary = _sanitize_public_prose(
        _pick_first_text(summary.get("executive_summary"), data.get("commentary"))
    )
    source_url = _public_http_url(data.get("source"))
    source_download_href = _public_http_url(data.get("_source_download_href"))
    canonical_url = _marketlense_article_url(
        data.get("wordpress_url"),
        data.get("canonical_url"),
        source_url=source_url,
    )
    topics = [
        _s(item) for item in _coerce_list(artifacts.get("toc_topics")) if _s(item)
    ]
    if not topics:
        for chapter in _coerce_chapters(artifacts, doc_map):
            if chapter["title"]:
                topics.append(chapter["title"])
    insights = _coerce_insights(
        artifacts.get("insights_final")
        if _coerce_list(artifacts.get("insights_final"))
        else data.get("insights"),
        report_title=report_title,
    )
    quotes = _coerce_quotes(
        artifacts.get("quotes_final"),
        data,
        publisher,
        report_title=report_title,
    )
    topic_briefs = _coerce_topic_briefs(artifacts)
    snapshot_categories = _coerce_list(data.get("categories_display")) or _coerce_list(
        data.get("categories")
    )
    snapshot_tags = _coerce_list(data.get("taxonomy"))
    figure_section_enabled = bool(data.get("_figure_section_enabled", True))
    figure_slides = (
        _build_figure_slides(data, out_dir, report_title)
        if figure_section_enabled
        else []
    )
    visual_candidate_slides = [
        slide for slide in figure_slides if _is_visual_candidate_slide(slide)
    ]
    hero_image = None
    hero_src = _pick_first_text(
        request.preview_png, figure_slides[0]["src"] if figure_slides else ""
    )
    if hero_src:
        hero_image = _build_media(
            relative_path=hero_src,
            out_dir=out_dir,
            alt=f"Report preview visual for {report_title}",
            default_width=1400,
            default_height=1980,
            sizes="(max-width: 800px) 100vw, 38vw",
            caption="Preview panel for the source report.",
        )
    summary_status = _coerce_family_status(artifacts, "summary")
    insights_status = _coerce_family_status(artifacts, "insights_bundle")
    quotes_status = _coerce_family_status(artifacts, "quotes")
    expert_status = _coerce_family_status(artifacts, "expert_comment")
    linkedin_status = _coerce_family_status(artifacts, "linkedin_post")
    report_quality_score = _build_report_quality_score(data)
    advisory = _coerce_public_advisory(artifacts)
    topics_covered = _coerce_public_topics_covered(artifacts)
    key_figures = _coerce_public_key_figures(artifacts)
    chart_insight_cards = _coerce_public_chart_insight_cards(artifacts)
    signal_cards = _build_signal_cards(
        topics=topics,
        topic_briefs=topic_briefs,
        tags=snapshot_tags,
        prefer_key_points=bool(topics_covered),
    )
    core_signal = _build_core_signal(
        tldr_text=tldr_text,
        executive_summary=executive_summary,
        insights=insights,
    )
    editorial_cards = [
        {
            "label": "Methodology",
            "items": methodology_items,
            "empty": "No methodology details were extracted.",
        },
        {
            "label": "Coverage",
            "items": _coerce_coverage(doc_map, evidence_packs),
            "empty": "No coverage notes were extracted.",
        },
        {
            "label": "Findings",
            "items": _coerce_findings(evidence_packs),
            "empty": "No structured findings were extracted.",
        },
        {
            "label": "Limitations",
            "items": _coerce_limitations(evidence_packs),
            "empty": "No explicit limitations were extracted.",
        },
        {
            "label": "Contacts",
            "items": _coerce_contacts(doc_map, evidence_packs),
            "empty": "No contact details were extracted.",
        },
    ]
    chapters = _coerce_chapters(artifacts, doc_map)
    return {
        "report_title": report_title,
        "publisher": publisher,
        "region": region,
        "focus_year": focus_year,
        "fieldwork_dates": fieldwork_dates,
        "source_url": source_url,
        "canonical_url": canonical_url,
        "source_download_href": source_download_href,
        "fallback_reason": _s(source_status.get("reason")),
        "not_available": not_available,
        "core_signal": core_signal,
        "quality_score": report_quality_score,
        "report_identity_items": _build_report_identity_items(
            report_title=report_title,
            publisher=publisher,
            focus_year=focus_year,
            fieldwork_dates=fieldwork_dates,
            region=region,
            report_author=report_author,
        ),
        "hero_meta": [
            item
            for item in (
                f"{len(insights)} insight{'s' if len(insights) != 1 else ''}"
                if insights
                else "",
                f"{len(quotes)} quote{'s' if len(quotes) != 1 else ''}"
                if quotes
                else "",
                f"{len(topics)} topic{'s' if len(topics) != 1 else ''}"
                if topics
                else "",
                "Source linked" if canonical_url else "",
            )
            if item
        ],
        "hero_image": hero_image,
        "summary": {
            "tldr_text": tldr_text,
            "tldr_bullets": _split_summary_bullets(tldr_text, max_items=4),
            "executive_summary": executive_summary,
            "executive_bullets": _split_summary_bullets(executive_summary, max_items=6),
            "claim_map": _coerce_claim_map(summary, report_title=report_title),
        },
        "advisory": advisory,
        "public_intelligence": {
            "topics_covered": topics_covered,
            "key_figures": key_figures,
            "chart_insight_cards": chart_insight_cards,
        },
        "snapshot": {
            "facts": [
                item
                for item in (
                    {"label": "Report focus year", "value": focus_year}
                    if focus_year
                    else None,
                    {"label": "Fieldwork", "value": fieldwork_dates}
                    if fieldwork_dates
                    else None,
                    {"label": "Geography", "value": region} if region else None,
                    {"label": "Publisher", "value": publisher} if publisher else None,
                )
                if item
            ],
            "categories": snapshot_categories,
            "tags": snapshot_tags,
        },
        "topics": topics,
        "topic_briefs": topic_briefs,
        "signal_cards": signal_cards,
        "editorial_cards": editorial_cards,
        "chapters": chapters,
        "insights": insights,
        "quotes": quotes,
        "commentary": _sanitize_public_prose(data.get("commentary")),
        "expert_comment": _sanitize_public_prose(artifacts.get("expert_comment")),
        "linkedin_post": _sanitize_public_prose(artifacts.get("linkedin_post")),
        "figures": {
            "slides": figure_slides,
            "visual_candidates": visual_candidate_slides,
            "lightbox_width": figure_slides[0]["width"] if figure_slides else 1600,
            "lightbox_height": figure_slides[0]["height"] if figure_slides else 900,
        },
        "statuses": {
            "summary": summary_status,
            "insights": insights_status,
            "quotes": quotes_status,
            "expert": expert_status,
            "linkedin": linkedin_status,
        },
        "display": {
            "has_metadata": bool(
                _coerce_list(data.get("categories_display"))
                or _coerce_list(data.get("categories"))
                or _coerce_list(data.get("taxonomy"))
            ),
            "has_topics": bool(topics),
            "has_topic_briefs": bool(topic_briefs),
            "has_figures": bool(visual_candidate_slides),
            "has_insights": bool(insights),
            "has_quotes": bool(quotes),
            "has_appendix": bool(
                _sanitize_public_prose(artifacts.get("expert_comment"))
                or _sanitize_public_prose(artifacts.get("linkedin_post"))
                or expert_status["status"] == "abstained"
                or linkedin_status["status"] == "abstained"
            ),
            "has_editorial": any(card["items"] for card in editorial_cards),
            "has_chapters": bool(chapters),
            "has_source_download": bool(source_download_href),
            "has_signal_cards": bool(signal_cards),
            "has_advisory": bool(
                advisory["decision"]["available"]
                or advisory["metric_spine"]
                or advisory["claim_support"]
            ),
            "has_public_intelligence": bool(
                topics_covered or key_figures or chart_insight_cards
            ),
        },
        "seo": {
            "description": _seo_description(
                _pick_first_text(
                    tldr_text, executive_summary, f"Digest for {report_title}."
                ),
                fallback=f"Digest for {report_title}.",
            ),
            "title": "",
            "robots": _s(data.get("robots"))
            or (
                "index,follow"
                if (
                    (tldr_text and tldr_text.lower() != "not available from text.")
                    or insights
                    or quotes
                    or executive_summary
                )
                and not not_available
                else "noindex,nofollow"
            ),
            "primary_image": hero_image["src"] if hero_image else "",
        },
        "json_ld_keywords": _coerce_list(data.get("taxonomy"))
        or _coerce_list(data.get("categories_display"))
        or _coerce_list(data.get("categories")),
        "tag_acronym_map": tag_acronym_map,
    }


def _marketlense_article_url(*candidates: object, source_url: str) -> str:
    source_key = source_url.rstrip("/").casefold()
    for candidate in candidates:
        value = _public_http_url(candidate)
        if not value:
            continue
        normalized = value.rstrip("/").casefold()
        if normalized == source_key or normalized.endswith(".pdf"):
            continue
        return value
    return ""


def _public_http_url(value: object) -> str:
    """Return a safe public HTTP(S) URL, rejecting local and credentialed values."""
    candidate = _s(value)
    if not candidate:
        return ""
    parsed = urlsplit(candidate)
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.hostname.casefold()
        in {"drive.google.com", "localhost", "127.0.0.1", "::1"}
    ):
        return ""
    return candidate


def _normalize_public_title(value: str, *, max_length: int = 110) -> str:
    title = _s(value).replace("…", "").replace("...", "")
    title = re.sub(r"\.pdf$", "", title, flags=re.IGNORECASE)
    if "_" in title:
        title = re.sub(r"[_]+", " ", title)
    title = re.sub(r"\b(20\d{2})(?:\s*[-|:]?\s*)\1\b", r"\1", title)
    title = re.sub(r"\s+", " ", title).strip(" -|:.")
    if len(title) <= max_length:
        return title
    primary_title = re.split(r"\s*(?::|[–—])\s+", title, maxsplit=1)[0]
    return primary_title.strip(" -|:.") or title


def _seo_description(value: str, *, fallback: str, max_length: int = 180) -> str:
    text = " ".join(_s(value).split())
    if not text:
        return fallback
    if len(text) <= max_length:
        return text if re.search(r"[.!?;:]$", text) else f"{text}."
    boundary = max(
        (index for index, char in enumerate(text[: max_length + 1]) if char in ".!?;:"),
        default=-1,
    )
    if boundary >= 0:
        return text[: boundary + 1].strip()
    return fallback


def _build_seo_title(report_title: str, focus_year: str, publisher: str) -> str:
    base_title = _normalize_public_title(report_title, max_length=72)
    if focus_year and focus_year not in base_title:
        base_title = f"{base_title} {focus_year}"
    publisher_short = _normalize_public_title(publisher, max_length=40)
    publisher_segment = f" | {publisher_short}" if publisher_short else ""
    return f"{base_title}{publisher_segment} | MarketBearing"


__all__ = [
    "_build_figure_slides",
    "_build_render_view",
    "_build_seo_title",
    "_marketlense_article_url",
    "_normalize_public_title",
    "_seo_description",
]
