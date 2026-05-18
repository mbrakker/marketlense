from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image
from src.contracts.files import WriteBytesRequest
from src.contracts.report_assets import RenderRequest, RenderResponse
from src.contracts.run_context import RunContext
from src.services import file_service
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.slugify import slugify

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


def _build_tag_acronym_map(acronyms: list[str]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for raw in acronyms:
        token = str(raw).strip()
        if not token:
            continue
        mapped[token.lower()] = token
    return mapped


def _s(value: object) -> str:
    return str(value or "").strip()


def _coerce_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _coerce_positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _pick_first_text(*values: object) -> str:
    for value in values:
        candidate = _s(value)
        if candidate:
            return candidate
    return ""


def _split_summary_bullets(text: str, *, max_items: int = 5) -> list[str]:
    normalized = _s(text)
    if not normalized:
        return []
    if "\n" in normalized:
        parts = [part.strip(" -*\t") for part in normalized.splitlines()]
    elif ";" in normalized:
        parts = [part.strip(" -*\t") for part in normalized.split(";")]
    else:
        parts = [
            part.strip(" -*\t") for part in _SENTENCE_SPLIT_PATTERN.split(normalized)
        ]
    bullets = [part for part in parts if part]
    if len(bullets) <= 1 and len(normalized) > 140:
        words = normalized.split()
        chunked: list[str] = []
        chunk: list[str] = []
        for word in words:
            chunk.append(word)
            if len(" ".join(chunk)) >= 120:
                chunked.append(" ".join(chunk).strip())
                chunk = []
        if chunk:
            chunked.append(" ".join(chunk).strip())
        bullets = [part for part in chunked if part]
    return bullets[:max_items]


def _extract_focus_year(*values: object) -> str:
    for value in values:
        candidate = _s(value)
        if not candidate:
            continue
        match = _YEAR_PATTERN.search(candidate)
        if match:
            return match.group(1)
    return ""


def _extract_fieldwork_dates(*values: object) -> str:
    for value in values:
        candidate = _s(value)
        if not candidate:
            continue
        if "fieldwork" in candidate.lower():
            fieldwork_index = candidate.lower().find("fieldwork")
            return candidate[fieldwork_index:].strip(" ()")
        months = _MONTH_PATTERN.findall(candidate)
        if len(months) >= 2:
            return f"{months[0]} to {months[-1]}"
        if len(months) == 1:
            return months[0]
        iso_dates = _ISO_DATE_PATTERN.findall(candidate)
        if len(iso_dates) >= 2:
            return f"{iso_dates[0]} to {iso_dates[-1]}"
        if len(iso_dates) == 1:
            return iso_dates[0]
    return ""


def _resolve_asset_path(out_dir: Path, relative_path: str) -> Path | None:
    candidate = _s(relative_path)
    if not candidate:
        return None
    path = Path(candidate)
    if path.is_absolute():
        return path
    return out_dir / path


def _detect_asset_dimensions(
    asset_path: Path | None, default_width: int, default_height: int
) -> tuple[int, int]:
    if asset_path is None or not asset_path.exists():
        return default_width, default_height
    try:
        with Image.open(asset_path) as image:
            return int(image.width), int(image.height)
    except OSError:
        return default_width, default_height


def _build_srcset(asset_path: Path | None, relative_path: str) -> str:
    if asset_path is None:
        return ""
    candidates = []
    relative = _s(relative_path)
    if relative:
        candidates.append(f"{relative} 1x")
    suffix = asset_path.suffix
    stem = asset_path.stem
    for variant_suffix, descriptor in (
        ("@2x", "2x"),
        ("-2x", "2x"),
        ("_2x", "2x"),
        ("-1280w", "1280w"),
        ("-1600w", "1600w"),
        ("-1920w", "1920w"),
    ):
        variant_path = asset_path.with_name(f"{stem}{variant_suffix}{suffix}")
        if not variant_path.exists():
            continue
        if asset_path.is_absolute():
            rel_variant = (
                str(variant_path.relative_to(asset_path.parent.parent))
                if len(variant_path.parents) > 1
                else variant_path.name
            )
        else:
            rel_variant = variant_path.name
        if relative:
            rel_variant = str(Path(relative).with_name(variant_path.name)).replace(
                "\\", "/"
            )
        candidates.append(f"{rel_variant} {descriptor}")
    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return ", ".join(unique)


def _build_media(
    *,
    relative_path: str,
    out_dir: Path,
    alt: str,
    default_width: int,
    default_height: int,
    sizes: str,
    caption: str = "",
) -> dict[str, Any]:
    src = _s(relative_path)
    asset_path = _resolve_asset_path(out_dir, src)
    width, height = _detect_asset_dimensions(asset_path, default_width, default_height)
    srcset = _build_srcset(asset_path, src)
    return {
        "src": src,
        "alt": alt,
        "caption": _s(caption),
        "width": width,
        "height": height,
        "sizes": sizes if srcset else "",
        "srcset": srcset,
    }


def _unwrap_doc_map(raw_doc_map: object) -> dict[str, Any]:
    candidate = _coerce_dict(raw_doc_map)
    for key in ("doc_map", "docmap", "docMap"):
        wrapped = candidate.get(key)
        if isinstance(wrapped, dict):
            return wrapped
    return candidate


def _build_report_identity_items(
    *,
    report_title: str,
    publisher: str,
    focus_year: str,
    report_author: str,
) -> list[str]:
    items: list[str] = []
    if report_title:
        items.append(f"Title: {report_title}")
    if publisher:
        items.append(f"Publisher: {publisher}")
    if focus_year:
        items.append(f"Year: {focus_year}")
    if report_author:
        items.append(f"Author: {report_author}")
    return items


def _coerce_claim_map(summary: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw_item in _coerce_list(summary.get("claim_evidence_map")):
        item = _coerce_dict(raw_item)
        claim = _s(item.get("claim"))
        if not claim:
            continue
        evidence_id = _s(item.get("evidence_id"))
        citation_line = _build_citation_micro_line(
            evidence_id=evidence_id,
            citation="",
            evidence_spans=item.get("evidence_spans"),
            pages=item.get("pages"),
        )
        items.append(
            {
                "claim": claim,
                "evidence_id": evidence_id,
                "evidence": _s(item.get("evidence")),
                "citation_line": citation_line,
            }
        )
    return items


def _coerce_insights(raw_insights: object) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []
    for raw_item in _coerce_list(raw_insights):
        item = _coerce_dict(raw_item)
        if item:
            text = _s(item.get("text"))
        else:
            text = _s(raw_item)
        if not text:
            continue
        insights.append(
            {
                "text": text,
                "citation_line": _build_citation_micro_line(
                    evidence_id=_s(item.get("evidence_id")),
                    citation="",
                    evidence_spans=item.get("evidence_spans"),
                    pages=item.get("pages"),
                ),
            }
        )
    return insights


def _coerce_quotes(
    raw_quotes: object, data: dict[str, Any], publisher: str
) -> list[dict[str, str]]:
    quotes: list[dict[str, str]] = []
    for raw_item in _coerce_list(raw_quotes):
        item = _coerce_dict(raw_item)
        text = _pick_first_text(
            item.get("text"), raw_item if isinstance(raw_item, str) else ""
        )
        if not text:
            continue
        quotes.append(
            {
                "text": text,
                "author": _display_quote_author(
                    _pick_first_text(item.get("speaker"), item.get("author")),
                    publisher,
                ),
                "citation": _s(item.get("citation")),
                "citation_line": _build_citation_micro_line(
                    evidence_id=_s(item.get("evidence_id")),
                    citation=_s(item.get("citation")),
                    evidence_spans=item.get("evidence_spans"),
                    pages=[item.get("page")]
                    if isinstance(item.get("page"), int)
                    else [],
                ),
            }
        )
    if quotes:
        return quotes
    legacy_quote = _coerce_dict(data.get("quote"))
    if _s(legacy_quote.get("text")):
        return [
            {
                "text": _s(legacy_quote.get("text")),
                "author": _display_quote_author(
                    _pick_first_text(legacy_quote.get("author"), "Unknown"),
                    publisher,
                ),
                "citation": "",
                "citation_line": "",
            }
        ]
    return []


def _display_quote_author(author: str, publisher: str) -> str:
    normalized_author = _s(author)
    if normalized_author and normalized_author.casefold() != "unknown":
        return normalized_author
    normalized_publisher = _s(publisher)
    if normalized_publisher:
        return f"{normalized_publisher} expert team"
    return "Expert team"


def _coerce_evidence_spans(raw_spans: object) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    seen: set[tuple[object, ...]] = set()
    for raw_span in _coerce_list(raw_spans):
        span = _coerce_dict(raw_span)
        evidence_id = _s(span.get("evidence_id"))
        source_pack = _s(span.get("source_pack"))
        if not evidence_id:
            continue
        page = _coerce_positive_int(span.get("page"))
        dedupe_key = (
            evidence_id,
            source_pack,
            _s(span.get("section_id")),
            page,
            span.get("start_offset"),
            span.get("end_offset"),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized: dict[str, Any] = {
            "evidence_id": evidence_id,
            "source_pack": source_pack,
        }
        if page is not None:
            normalized["page"] = page
        if _s(span.get("section_id")):
            normalized["section_id"] = _s(span.get("section_id"))
        spans.append(normalized)
    return spans


def _build_citation_micro_line(
    *,
    evidence_id: str,
    citation: str,
    evidence_spans: object,
    pages: object,
) -> str:
    parts: list[str] = []
    if evidence_id:
        parts.append(evidence_id)
    span_pages = [
        page
        for page in (
            _coerce_positive_int(span.get("page"))
            for span in _coerce_evidence_spans(evidence_spans)
        )
        if page is not None
    ]
    explicit_pages = [
        page
        for page in (_coerce_positive_int(page) for page in _coerce_list(pages))
        if page is not None
    ]
    all_pages = list(dict.fromkeys([*span_pages, *explicit_pages]))
    if all_pages:
        page_label = "report page" if len(all_pages) == 1 else "report pages"
        parts.append(f"{page_label} {', '.join(str(page) for page in all_pages)}")
    normalized_citation = _s(citation)
    if normalized_citation:
        parts.append(normalized_citation)
    return " · ".join(part for part in parts if part)


def _coerce_topic_briefs(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    expanded = _coerce_list(artifacts.get("toc_topics_expanded"))
    briefs: list[dict[str, Any]] = []
    source_items = expanded or _coerce_list(artifacts.get("toc_entries"))
    for raw_item in source_items:
        item = _coerce_dict(raw_item)
        title = _pick_first_text(
            item.get("topic"),
            item.get("display_title"),
            item.get("section_title"),
            item.get("title"),
        )
        if not title:
            continue
        briefs.append(
            {
                "title": title,
                "summary": _s(item.get("summary")),
                "key_points": [
                    _s(point)
                    for point in _coerce_list(item.get("key_points"))
                    if _s(point)
                ],
            }
        )
    return briefs


def _coerce_chapters(
    artifacts: dict[str, Any], doc_map: dict[str, Any]
) -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    for raw_item in _coerce_list(artifacts.get("toc_entries")):
        item = _coerce_dict(raw_item)
        title = _pick_first_text(item.get("display_title"), item.get("section_title"))
        if not title:
            continue
        toc_pages = [
            str(page).strip() for page in _coerce_list(item.get("pages")) if _s(page)
        ]
        chapters.append(
            {
                "order": int(item.get("order") or len(chapters) + 1),
                "title": title,
                "summary": _s(item.get("summary")),
                "pages": toc_pages,
            }
        )
    if chapters:
        return chapters
    for index, raw_section in enumerate(_coerce_list(doc_map.get("sections")), start=1):
        section = _coerce_dict(raw_section)
        title = _pick_first_text(
            section.get("title"), section.get("heading"), section.get("name")
        )
        if not title:
            continue
        pages: list[str] = []
        if _s(section.get("page")):
            pages.append(_s(section.get("page")))
        for page in _coerce_list(section.get("pages")):
            if _s(page):
                pages.append(_s(page))
        chapters.append(
            {
                "order": index,
                "title": title,
                "summary": _s(section.get("summary")),
                "pages": pages,
            }
        )
    return chapters


def _coerce_methodology(
    doc_map: dict[str, Any], evidence_packs: dict[str, Any]
) -> list[str]:
    methods_pack = _coerce_dict(evidence_packs.get("methods"))
    methods: list[str] = []
    for raw_item in _coerce_list(methods_pack.get("methods")):
        item = _coerce_dict(raw_item)
        description = _pick_first_text(item.get("description"), item.get("name"))
        if description:
            methods.append(description)
    doc_map_methodology = _s(doc_map.get("methodology"))
    if doc_map_methodology and doc_map_methodology not in methods:
        methods.insert(0, doc_map_methodology)
    return methods


def _coerce_coverage(
    doc_map: dict[str, Any], evidence_packs: dict[str, Any]
) -> list[str]:
    coverage: list[str] = []
    scope = _coerce_dict(_coerce_dict(evidence_packs.get("scope")).get("scope"))
    jurisdictions = [
        value
        for value in (_s(item) for item in _coerce_list(scope.get("jurisdictions")))
        if value
    ]
    if jurisdictions:
        coverage.append(f"Jurisdictions: {', '.join(jurisdictions)}")
    sources = []
    for raw_source in _coerce_list(scope.get("sources")):
        source = _coerce_dict(raw_source)
        title = _pick_first_text(
            source.get("title"), source.get("id"), source.get("type")
        )
        if title:
            sources.append(title)
    if sources:
        coverage.append(f"Sources in scope: {', '.join(sources[:3])}")
    content_types = [
        value
        for value in (_s(item) for item in _coerce_list(scope.get("contentTypes")))
        if value
    ]
    if content_types:
        coverage.append(f"Content types: {', '.join(content_types[:4])}")
    if _s(scope.get("samplingRate")):
        coverage.append(f"Sampling rate: {_s(scope.get('samplingRate'))}")
    if _s(scope.get("retentionDays")):
        coverage.append(f"Retention: {_s(scope.get('retentionDays'))} days")
    for key in ("summary", "subtitle", "about_publisher"):
        value = _s(doc_map.get(key))
        if value and value not in coverage:
            coverage.append(value)
    for raw_stat in _coerce_list(doc_map.get("key_stats")):
        stat = _s(raw_stat)
        if stat and stat not in coverage:
            coverage.append(stat)
    return coverage[:6]


def _coerce_findings(evidence_packs: dict[str, Any]) -> list[str]:
    findings_pack = _coerce_dict(evidence_packs.get("findings"))
    findings: list[str] = []
    for raw_item in _coerce_list(findings_pack.get("findings")):
        item = _coerce_dict(raw_item)
        statement = _pick_first_text(
            item.get("statement"),
            item.get("title"),
            item.get("description"),
        )
        if statement:
            findings.append(statement)
    return findings[:5]


def _coerce_limitations(evidence_packs: dict[str, Any]) -> list[str]:
    limitations_pack = _coerce_dict(evidence_packs.get("limitations"))
    limitations: list[str] = []
    for raw_item in _coerce_list(limitations_pack.get("limitations")):
        item = _coerce_dict(raw_item)
        message = _pick_first_text(
            item.get("message"),
            item.get("description"),
            item.get("mitigation"),
        )
        if message:
            limitations.append(message)
    return limitations[:5]


def _coerce_contacts(
    doc_map: dict[str, Any], evidence_packs: dict[str, Any]
) -> list[str]:
    contacts: list[str] = []
    for collection_key in ("contributors", "authors"):
        for raw_item in _coerce_list(doc_map.get(collection_key)):
            item = _coerce_dict(raw_item)
            line_parts = [
                _pick_first_text(
                    item.get("name"), item.get("author"), item.get("full_name")
                ),
                _pick_first_text(item.get("role"), item.get("affiliation")),
                _pick_first_text(item.get("email"), item.get("contact")),
            ]
            line = " — ".join(part for part in line_parts if part)
            if line and line not in contacts:
                contacts.append(line)
    publisher = _coerce_dict(doc_map.get("publisher"))
    organization = _pick_first_text(
        publisher.get("organization"),
        publisher.get("name"),
    )
    if organization and organization not in contacts:
        contacts.append(organization)
    scope = _coerce_dict(_coerce_dict(evidence_packs.get("scope")).get("scope"))
    owner = _coerce_dict(scope.get("owner"))
    if owner:
        owner_line = " — ".join(
            part
            for part in (
                _s(owner.get("name")),
                _s(owner.get("role")),
            )
            if part
        )
        if owner_line and owner_line not in contacts:
            contacts.append(owner_line)
    return contacts[:5]


def _coerce_family_status(artifacts: dict[str, Any], family: str) -> dict[str, str]:
    family_status = _coerce_dict(artifacts.get("family_status"))
    status = _coerce_dict(family_status.get(family))
    return {
        "status": _s(status.get("status")),
        "reason": _s(status.get("reason")),
    }


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
        else data.get("insights")
    )
    quotes = _coerce_quotes(artifacts.get("quotes_final"), data, publisher)
    figure_section_enabled = bool(data.get("_figure_section_enabled", True))
    figure_slides = (
        _build_figure_slides(data, out_dir, report_title)
        if figure_section_enabled
        else []
    )
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
        "fallback_reason": _s(source_status.get("reason")),
        "not_available": not_available,
        "report_identity_items": _build_report_identity_items(
            report_title=report_title,
            publisher=publisher,
            focus_year=focus_year,
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
            "claim_map": _coerce_claim_map(summary),
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
            "categories": _coerce_list(data.get("categories_display"))
            or _coerce_list(data.get("categories")),
            "tags": _coerce_list(data.get("taxonomy")),
        },
        "topics": topics,
        "topic_briefs": _coerce_topic_briefs(artifacts),
        "editorial_cards": editorial_cards,
        "chapters": chapters,
        "insights": insights,
        "quotes": quotes,
        "commentary": _s(data.get("commentary")),
        "expert_comment": _s(artifacts.get("expert_comment")),
        "linkedin_post": _s(artifacts.get("linkedin_post")),
        "figures": {
            "slides": figure_slides,
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
            "has_topic_briefs": bool(_coerce_topic_briefs(artifacts)),
            "has_figures": bool(figure_slides),
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
    return f"{base_title}{' | ' + publisher_short if publisher_short else ''} | Market Lense"


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
        file_id=request.file_id,
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
