from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

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
    _coerce_quotes,
    _coerce_topic_briefs,
    _extract_fieldwork_dates,
    _extract_focus_year,
    _is_visual_candidate_slide,
    _pick_first_text,
    _s,
    _split_summary_bullets,
    _unwrap_doc_map,
)

logger = logging.getLogger("market_lense.render_service")
PUBLIC_EDITORIAL_CONTRACT_VERSION = "public-report-editorial-v1"
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
    if figure_assets:
        for index, raw_asset in enumerate(figure_assets, start=1):
            asset = _coerce_dict(raw_asset)
            image_path = _s(asset.get("image_path"))
            if not image_path:
                continue
            is_primary = bool(asset.get("is_primary")) or index == 1
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
                        caption=_pick_first_text(
                            asset.get("display_caption"),
                            "Representative figure from the source report.",
                        ),
                    ),
                    "caption": _pick_first_text(
                        asset.get("display_caption"),
                        "Representative figure from the source report.",
                    ),
                    "page": int(asset.get("page") or -1)
                    if isinstance(asset.get("page"), int)
                    else -1,
                    "kind": _s(asset.get("kind")),
                    "candidate_id": _s(asset.get("candidate_id")),
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
    primary_figure = _pick_first_text(
        data.get("_figure_top"), data.get("_figure_image")
    )
    figure_gallery = [
        _s(item) for item in _coerce_list(data.get("_figure_gallery")) if _s(item)
    ]
    seen: set[str] = set()
    ordered_paths: list[str] = []
    for path in [primary_figure, *figure_gallery]:
        if path and path not in seen:
            ordered_paths.append(path)
            seen.add(path)
    fallback_caption = ""
    legacy_figure = _coerce_dict(data.get("figure"))
    fallback_caption = _pick_first_text(
        legacy_figure.get("title"),
        legacy_figure.get("evidence"),
    )
    for index, image_path in enumerate(ordered_paths, start=1):
        slides.append(
            {
                **_build_media(
                    relative_path=image_path,
                    out_dir=out_dir,
                    alt=(
                        f"Selected figure from {report_title}"
                        if index == 1
                        else f"Additional figure {index} from {report_title}"
                    ),
                    default_width=1600,
                    default_height=900,
                    sizes="(max-width: 800px) 100vw, 980px",
                    caption=(
                        fallback_caption
                        if index == 1 and fallback_caption
                        else f"Additional figure {index}"
                    ),
                ),
                "caption": (
                    fallback_caption
                    if index == 1 and fallback_caption
                    else f"Additional figure {index}"
                ),
                "page": -1,
                "kind": "image",
                "candidate_id": "",
                "is_primary": index == 1,
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
    report_title = _pick_first_text(data.get("title"), doc_map.get("title"))
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
    tldr_text = _pick_first_text(summary.get("tldr"), data.get("tldr"))
    not_available = bool(
        source_status.get("not_available")
        if "not_available" in source_status
        else data.get("_text_not_available")
    )
    if not tldr_text and not_available:
        tldr_text = "Not available from text."
    executive_summary = _pick_first_text(
        summary.get("executive_summary"), data.get("commentary")
    )
    source_url = _s(data.get("source"))
    canonical_url = _pick_first_text(data.get("canonical_url"), source_url)
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
        "editorial_contract_version": PUBLIC_EDITORIAL_CONTRACT_VERSION,
        "publisher": publisher,
        "region": region,
        "focus_year": focus_year,
        "fieldwork_dates": fieldwork_dates,
        "source_url": source_url,
        "canonical_url": canonical_url,
        "source_download_href": _s(data.get("_source_download_href")),
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
        "signal_cards": _build_signal_cards(
            topics=topics, topic_briefs=topic_briefs, tags=snapshot_tags
        ),
        "editorial_cards": editorial_cards,
        "chapters": chapters,
        "insights": insights,
        "quotes": quotes,
        "commentary": _s(data.get("commentary")),
        "expert_comment": _s(artifacts.get("expert_comment")),
        "linkedin_post": _s(artifacts.get("linkedin_post")),
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
                _s(artifacts.get("expert_comment"))
                or _s(artifacts.get("linkedin_post"))
                or expert_status["status"] == "abstained"
                or linkedin_status["status"] == "abstained"
            ),
            "has_editorial": any(card["items"] for card in editorial_cards),
            "has_chapters": bool(chapters),
            "has_source_download": bool(_s(data.get("_source_download_href"))),
            "has_signal_cards": bool(
                _build_signal_cards(
                    topics=topics, topic_briefs=topic_briefs, tags=snapshot_tags
                )
            ),
            "has_advisory": bool(
                advisory["decision"]["available"]
                or advisory["recommendations"]
                or advisory["risks"]
                or advisory["metric_spine"]
                or advisory["claim_support"]
            ),
        },
        "seo": {
            "description": _pick_first_text(
                tldr_text, executive_summary, f"Digest for {report_title}"
            )[:180],
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


def _build_seo_title(report_title: str, focus_year: str, publisher: str) -> str:
    short_title = report_title[:72] + ("..." if len(report_title) > 72 else "")
    base_title = short_title
    if focus_year:
        base_title = f"{base_title} {focus_year}"
    publisher_short = publisher[:40] + ("..." if len(publisher) > 40 else "")
    publisher_segment = f" | {publisher_short}" if publisher_short else ""
    return f"{base_title}{publisher_segment} | MarketBearing"


__all__ = [
    "_build_figure_slides",
    "_build_render_view",
    "_build_seo_title",
]
