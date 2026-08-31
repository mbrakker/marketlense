from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

from src.utils.coercion import stripped_string_value as _s
from src.utils.public_metric_display import normalize_public_metric_display

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
_FIELDWORK_DATE_RANGE_PATTERN = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{1,2},?\s+20\d{2}\s*(?:-|to|through|until)\s*"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{1,2},?\s+20\d{2}\b",
    re.IGNORECASE,
)
_FIELDWORK_ISO_RANGE_PATTERN = re.compile(
    r"\b20\d{2}-\d{2}-\d{2}\s*(?:-|to|through|until)\s*20\d{2}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
_SENTENCE_ABBREVIATION = re.compile(r"\b(?:U\.S|U\.K|e\.g|i\.e)\.", re.I)
_INLINE_INTERNAL_REFERENCE = re.compile(
    r"(?:\s*[\[(](?!(?:q[1-4]|h[12])\b)(?:[a-z]{1,4}|finding|insight|claim)[_-]?\d{1,5}[\])]|"
    r"\b(?!(?:q[1-4]|h[12])\b)(?:[a-z]{1,4}|finding|insight|claim)[_-]?\d{1,5}\b)",
    re.IGNORECASE,
)
_PUBLIC_TRUNCATION_MARKER = re.compile(r"(?:\.\.\.|…)")
_LINKEDIN_MARKDOWN_LINK = re.compile(r"\[([^\]\n]+)\]\([^\)\n]+\)")
_LINKEDIN_MARKDOWN_HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s+")
_LINKEDIN_LIST_MARKER = re.compile(r"(?m)^(\s*)(?:[-+*]|\d+[.)])\s+")
_LINKEDIN_PLACEHOLDER = re.compile(
    r"\[(?:placeholder|todo|tbd|not available|n/?a|unknown)\]", re.IGNORECASE
)
_MECHANICAL_PUBLIC_SCAFFOLD = re.compile(
    r"\b(?:answer|observation|implication|executive action|executive takeaway|"
    r"concrete finding|"
    r"immediate implication)\s*:",
    re.IGNORECASE,
)
_CORE_SIGNAL_CLAUSE_BOUNDARY = re.compile(
    r";|(?<!\d):(?!\d)|\s+(?:but|while)\s+|,\s+(?:and|but|while)\s+(?=(?:(?:it|they|"
    r"we|you|he|she|this|"
    r"that|these|those)\s+(?:is|are|was|were|be|been|being|can|could|will|"
    r"would|should|may|might|must|do|does|did|has|have|had|[a-z]+(?:s|ed))\b|"
    r"[a-z]+\s+(?:is|are|was|were|be|been|being|can|could|will|would|should|"
    r"may|might|must|do|does|did|has|have|had)\b))|"
    r"\s+and\s+(?=(?:is|are|was|were|be|been|being|can|could|will|would|"
    r"should|may|might|must|do|does|did|has|have|had|[a-z]+(?:s|ed))\b)|"
    r"\s+to\s+(?=(?:contextualize|enable|support|reduce|improve|accelerate|"
    r"inform|guide)\b)",
    re.IGNORECASE,
)


def _build_tag_acronym_map(acronyms: list[str]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for raw in acronyms:
        token = str(raw).strip()
        if not token:
            continue
        mapped[token.lower()] = token
    return mapped


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


def _sanitize_public_prose(value: object) -> str:
    """Return complete public prose without internal or placeholder text."""
    text = _s(value)
    if not text:
        return ""
    sanitized = re.sub(r"\s{2,}", " ", _INLINE_INTERNAL_REFERENCE.sub("", text)).strip()
    if _PUBLIC_TRUNCATION_MARKER.search(sanitized):
        return ""
    return _MECHANICAL_PUBLIC_SCAFFOLD.sub("", sanitized).strip()


def _sanitize_linkedin_post(value: object) -> str:
    """Return plain LinkedIn prose while retaining its paragraph structure."""
    text = _s(value)
    if not text:
        return ""
    sanitized = _INLINE_INTERNAL_REFERENCE.sub("", text.replace("\r\n", "\n"))
    sanitized = _LINKEDIN_PLACEHOLDER.sub("", sanitized)
    if _PUBLIC_TRUNCATION_MARKER.search(sanitized):
        return ""
    sanitized = _LINKEDIN_MARKDOWN_LINK.sub(r"\1", sanitized)
    sanitized = _LINKEDIN_MARKDOWN_HEADING.sub("", sanitized)
    sanitized = _LINKEDIN_LIST_MARKER.sub(r"\1", sanitized)
    sanitized = re.sub(r"[*_`]", "", sanitized)
    sanitized = _MECHANICAL_PUBLIC_SCAFFOLD.sub("", sanitized)
    return "\n".join(
        re.sub(r"[ \t]{2,}", " ", line).strip() for line in sanitized.split("\n")
    ).strip()


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


def _sentence_excerpt(text: str, *, max_chars: int) -> str:
    normalized = _s(text)
    if not normalized:
        return ""
    sentences = _complete_sentences(normalized)
    for raw_sentence in sentences:
        candidate = raw_sentence.strip()
        if candidate and len(candidate) <= max_chars:
            return candidate
    # A clipped fragment reads as a claim whose ending was withheld. Preserve a
    # complete source sentence or let the caller use its explicit unavailable
    # state; never emit a literal ellipsis.
    return ""


def _complete_sentences(text: str) -> list[str]:
    """Split public prose without treating common abbreviations as a full claim."""
    sentinel = "\ufff0"
    protected = _SENTENCE_ABBREVIATION.sub(
        lambda match: match.group(0).replace(".", sentinel), text
    )
    return [
        sentence.replace(sentinel, ".")
        for sentence in (_SENTENCE_SPLIT_PATTERN.split(protected) or [protected])
    ]


def _build_core_signal(
    *, tldr_text: str, executive_summary: str, insights: list[dict[str, str]]
) -> dict[str, str]:
    insight_texts = [
        _s(insight.get("text"))
        for insight in insights
        if isinstance(insight, dict) and _s(insight.get("text"))
    ]
    strategic_texts = [
        _s(insight.get("so_what"))
        for insight in insights
        if isinstance(insight, dict) and _s(insight.get("so_what"))
    ]
    source_texts = insight_texts + [_s(tldr_text), _s(executive_summary)]
    candidates = [
        sentence.strip()
        for source_text in source_texts
        for sentence in _complete_sentences(source_text)
        if sentence.strip()
    ]
    ranked_candidates = sorted(
        enumerate(candidates),
        key=lambda item: (-_core_signal_score(item[1]), item[0]),
    )
    heading = _pick_first_text(
        *(_core_signal_heading(candidate) for candidate in strategic_texts),
        *(_core_signal_heading(candidate) for candidate in source_texts),
    )
    body = _pick_first_text(
        *(
            _sentence_excerpt(candidate, max_chars=320)
            for _, candidate in ranked_candidates
        ),
    )
    return {
        "heading": heading or "Source-backed market signal",
        "body": body or "Source-supported signal unavailable for this report.",
    }


def _core_signal_heading(text: str) -> str:
    """Keep a complete strategic clause when a full source sentence is too long."""
    sentence = _sentence_excerpt(text, max_chars=80)
    if sentence:
        return sentence
    for raw_sentence in _complete_sentences(_s(text)):
        strategic_tail = re.search(
            r"(?:,|—)\s+(?:enabling|supporting|reducing|driving)\s+(.+?)[.?!]?$",
            raw_sentence,
            flags=re.IGNORECASE,
        )
        if strategic_tail:
            candidate = strategic_tail.group(1).strip().rstrip(".?! ") + "."
            if len(candidate) <= 80 and len(candidate.split()) >= 4:
                return candidate[0].upper() + candidate[1:]
        # A bare "and" is not a boundary unless it starts a predicate; this
        # preserves coordinated terms such as "between scale and momentum"
        # and "search and video".
        clause = _CORE_SIGNAL_CLAUSE_BOUNDARY.split(raw_sentence, maxsplit=1)[0]
        candidate = clause.rstrip(".,?! ") + "."
        if len(candidate) <= 80 and len(candidate.split()) >= 5:
            return candidate
    return ""


_CORE_SIGNAL_ANNOTATION = re.compile(
    r"\b(?:report|study|document|paper|survey)\b.*\b(?:documents?|presents?|"
    r"describes?|outlines?|examines?|covers?)\b",
    re.IGNORECASE,
)
_CORE_SIGNAL_MARKERS = re.compile(
    r"\b(?:adoption|accelerat(?:e|es|ed|ing)|barrier|constrain(?:t|ed|s)|"
    r"declin(?:e|es|ed|ing)|demand|driv(?:e|es|en|ing)|forecast|growth|"
    r"increas(?:e|es|ed|ing)|majority|market|monetiz(?:e|ation)|revenue|"
    r"shift|subscription|under\s+\d+|more\s+than)\b|%|\b\d[\d,.]*\b",
    re.IGNORECASE,
)


def _core_signal_score(text: str) -> int:
    """Prefer a substantive source sentence over a report-description sentence."""
    normalized = _s(text)
    if not normalized:
        return -10
    score = min(4, len(_CORE_SIGNAL_MARKERS.findall(normalized)))
    if 55 <= len(normalized) <= 185:
        score += 1
    if _CORE_SIGNAL_ANNOTATION.search(normalized):
        score -= 5
    return score


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
        marker = candidate.casefold().find("fieldwork")
        if marker < 0:
            continue
        # The date can precede or follow the marker, but only the nearby
        # clause is eligible. This prevents methodology or summary prose from
        # becoming public Fieldwork metadata.
        window = candidate[max(0, marker - 120) : marker + 320]
        match = _FIELDWORK_DATE_RANGE_PATTERN.search(window)
        if match:
            return match.group(0)
        match = _FIELDWORK_ISO_RANGE_PATTERN.search(window)
        if match:
            return match.group(0)
    return ""


_REPORT_VALUE_DIMENSION_LABELS = {
    "market_insight_depth": "Market insight depth",
    "evidence_specificity": "Evidence specificity",
    "decision_relevance": "Decision relevance",
    "recency_timeliness": "Recency timeliness",
    "source_authority_originality": "Source authority originality",
}


def _build_report_quality_score(data: dict[str, Any]) -> dict[str, Any]:
    raw_score = _coerce_dict(data.get("_report_value_score"))
    components: list[dict[str, Any]] = []
    raw_components = _coerce_list(raw_score.get("components"))
    for dimension, label in _REPORT_VALUE_DIMENSION_LABELS.items():
        raw_component = next(
            (
                _coerce_dict(item)
                for item in raw_components
                if _s(_coerce_dict(item).get("dimension")) == dimension
            ),
            {},
        )
        score_value = raw_component.get("score")
        score = float(score_value) if isinstance(score_value, (int, float)) else None
        components.append(
            {
                "dimension": dimension,
                "label": label,
                "score": score,
                "score_label": f"{score:.0f}" if score is not None else "N/A",
                "fill": max(0.0, min(100.0, score or 0.0)),
                "rationale": _s(raw_component.get("rationale")),
            }
        )
    overall = raw_score.get("overall_score")
    overall_score = float(overall) if isinstance(overall, (int, float)) else None
    return {
        "available": overall_score is not None,
        "overall_score": overall_score,
        "overall_label": f"{overall_score:.0f}"
        if overall_score is not None
        else "Pending",
        "value_band": _s(raw_score.get("value_band")),
        "rationale": _s(raw_score.get("rationale")),
        "components": components,
    }


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
    source_period: str,
    fieldwork_dates: str,
    region: str,
    report_author: str,
) -> list[str]:
    items: list[str] = []
    if report_title:
        items.append(f"Title: {report_title}")
    if publisher:
        items.append(f"Publisher: {publisher}")
    if source_period:
        items.append(f"Period: {source_period}")
    if fieldwork_dates:
        items.append(f"Fieldwork: {fieldwork_dates}")
    if region:
        items.append(f"Region: {region}")
    if report_author:
        items.append(f"Author: {report_author}")
    return items


def _coerce_claim_map(
    summary: dict[str, Any], *, report_title: str
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw_item in _coerce_list(summary.get("claim_evidence_map")):
        item = _coerce_dict(raw_item)
        claim = _s(item.get("claim"))
        if not claim:
            continue
        evidence_id = _s(item.get("evidence_id"))
        citation_line = _build_citation_micro_line(
            report_title=report_title,
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


def _public_label_from_token(value: object) -> str:
    label = _s(value)
    if not label:
        return ""
    normalized = label.replace("_", " ").replace("-", " ").strip()
    words = [word for word in normalized.split() if word]
    if not words:
        return ""
    lowered = " ".join(word.lower() for word in words)
    return lowered[:1].upper() + lowered[1:]


def _coerce_text_items(value: object, limit: int = 4) -> list[str]:
    items: list[str] = []
    for raw_item in _coerce_list(value):
        text = _sanitize_public_prose(raw_item)
        if text and text not in items:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def _coerce_advisory_items(
    advisory_section: object,
    *,
    text_keys: tuple[str, ...],
    limit: int = 4,
) -> list[dict[str, str]]:
    section = _coerce_dict(advisory_section)
    rows: list[dict[str, str]] = []
    for raw_item in _coerce_list(section.get("items")):
        item = _coerce_dict(raw_item)
        text = _sanitize_public_prose(
            _pick_first_text(*(item.get(key) for key in text_keys), raw_item)
        )
        if not text:
            continue
        rows.append(
            {
                "text": text,
                "support_label": "Source-backed",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _coerce_public_metric_spine(
    artifacts: dict[str, Any], *, limit: int = 4
) -> list[dict[str, str]]:
    metrics: list[dict[str, str]] = []
    for raw_item in _coerce_list(artifacts.get("metric_spine")):
        item = _coerce_dict(raw_item)
        label = _s(item.get("label"))
        value = _s(item.get("value"))
        unit = _s(item.get("unit"))
        if not label or not value:
            continue
        value, unit = normalize_public_metric_display(value=value, unit=unit)
        if not value:
            continue
        metric_value = (
            f"{value}{unit}"
            if unit in {"%", "pp"}
            else " ".join(part for part in (value, unit) if part)
        )
        context = ", ".join(
            part
            for part in (
                _s(item.get("segment")),
                _s(item.get("geography")),
                _s(item.get("timeframe")),
            )
            if part
        )
        metrics.append(
            {
                "label": label,
                "value": metric_value,
                "context": context,
                "confidence_label": _public_label_from_token(item.get("confidence"))
                or "Source-backed",
            }
        )
        if len(metrics) >= limit:
            break
    return metrics


def _coerce_public_claim_support(
    artifacts: dict[str, Any], *, limit: int = 4
) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []
    for raw_item in _coerce_list(artifacts.get("claim_ledgers")):
        item = _coerce_dict(raw_item)
        claim_text = _sanitize_public_prose(item.get("claim_text"))
        if not claim_text:
            continue
        support_type = _public_label_from_token(item.get("support_type"))
        confidence = _public_label_from_token(item.get("confidence"))
        risk = _public_label_from_token(item.get("risk"))
        labels = [label for label in (support_type, confidence, risk) if label]
        claims.append(
            {
                "claim": claim_text,
                "support_label": " · ".join(labels) if labels else "Source-backed",
            }
        )
        if len(claims) >= limit:
            break
    return claims


def _coerce_public_advisory(artifacts: dict[str, Any]) -> dict[str, Any]:
    advisory = _coerce_dict(artifacts.get("executive_advisory"))
    decision_brief = _coerce_dict(advisory.get("decision_brief"))
    status = _s(decision_brief.get("status")).casefold()
    decision = {
        "available": status == "generated",
        "strategic_context": _sanitize_public_prose(
            decision_brief.get("strategic_context")
        ),
        "decision_implications": _coerce_text_items(
            decision_brief.get("decision_implications"), limit=4
        ),
        "priority_moves": _coerce_text_items(
            decision_brief.get("priority_moves"), limit=4
        ),
        "watchouts": _coerce_text_items(decision_brief.get("watchouts"), limit=4),
        "confidence_note": _sanitize_public_prose(
            decision_brief.get("confidence_note")
        ),
    }
    recommendations = _coerce_advisory_items(
        advisory.get("recommendations"),
        text_keys=("recommendation", "text"),
        limit=4,
    )
    risks = _coerce_advisory_items(
        advisory.get("risks"),
        text_keys=("risk", "text"),
        limit=4,
    )
    return {
        "decision": decision,
        "recommendations": recommendations,
        "risks": risks,
        "metric_spine": _coerce_public_metric_spine(artifacts),
        "claim_support": _coerce_public_claim_support(artifacts),
    }


def _coerce_public_topics_covered(
    artifacts: dict[str, Any],
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    topics: list[dict[str, Any]] = []
    raw_topics = (
        _coerce_list(artifacts.get("topics_covered"))
        or _coerce_list(artifacts.get("toc_topics_expanded"))
        or _coerce_list(artifacts.get("toc_entries"))
    )
    for raw_item in raw_topics:
        item = _coerce_dict(raw_item)
        title = _pick_first_text(
            item.get("topic"),
            item.get("title"),
            item.get("display_title"),
            raw_item if isinstance(raw_item, str) else "",
        )
        if not title:
            continue
        pages = [
            str(page).strip() for page in _coerce_list(item.get("pages")) if _s(page)
        ]
        topics.append(
            {
                "topic": title,
                "summary": _pick_first_text(
                    item.get("why_it_matters"),
                    item.get("summary"),
                    "Covered by the source report.",
                ),
                "subtopics": [
                    _s(point)
                    for point in _coerce_list(item.get("subtopics"))
                    if _s(point)
                ][:4],
                "source_label": f"Pages {', '.join(pages)}" if pages else "",
            }
        )
        if len(topics) >= limit:
            break
    return topics


def _coerce_public_key_figures(
    artifacts: dict[str, Any],
    *,
    limit: int = 6,
) -> list[dict[str, str]]:
    figures: list[dict[str, str]] = []
    raw_figures = _coerce_list(artifacts.get("key_figures")) or _coerce_list(
        artifacts.get("metric_spine")
    )
    for raw_item in raw_figures:
        item = _coerce_dict(raw_item)
        value = _pick_first_text(item.get("value"), item.get("figure"))
        label = _pick_first_text(
            item.get("label"), item.get("metric"), item.get("name")
        )
        if not value or not label:
            continue
        unit = _s(item.get("unit"))
        value, unit = normalize_public_metric_display(value=value, unit=unit)
        if not value:
            continue
        if unit and unit.casefold() in value.casefold():
            display_value = value
        elif unit in {"%", "pp"}:
            display_value = f"{value}{unit}"
        else:
            display_value = " ".join(part for part in (value, unit) if part)
        figures.append(
            {
                "value": display_value,
                "label": label,
                "context": ", ".join(
                    part
                    for part in (
                        _s(item.get("context")),
                        _s(item.get("segment")),
                        _s(item.get("geography")),
                        _s(item.get("timeframe")),
                    )
                    if part
                ),
                "confidence_label": _public_label_from_token(item.get("confidence"))
                or "Source-backed",
            }
        )
        if len(figures) >= limit:
            break
    return figures


def _coerce_public_chart_insight_cards(
    artifacts: dict[str, Any],
    *,
    limit: int = 4,
) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for raw_item in _coerce_list(artifacts.get("chart_insight_cards")):
        item = _coerce_dict(raw_item)
        status = _s(item.get("status")).casefold()
        if status in {
            "weak",
            "weak_evidence",
            "limited",
            "abstained",
            "text_only",
            "not_applicable",
            "omitted",
            "unavailable",
        }:
            continue
        candidate_id = _s(item.get("candidate_id"))
        evidence_id = _s(item.get("evidence_id"))
        source_page = _s(item.get("source_page"))
        insight_id = _s(item.get("insight_id"))
        caption = _pick_first_text(item.get("caption"), item.get("retained_caption"))
        takeaway = _s(item.get("public_takeaway"))
        if not (
            item.get("crop_qa_accepted") is True
            and candidate_id
            and evidence_id
            and source_page
            and insight_id
            and caption
            and takeaway
        ):
            continue
        title = _pick_first_text(
            item.get("title"),
            item.get("chart_title"),
            caption,
            takeaway,
        )
        limitation = _pick_first_text(
            item.get("limitation"),
            item.get("avoid_reason"),
            item.get("avoid_reason_if_weak"),
            item.get("diagnostic"),
        )
        if not title:
            continue
        cards.append(
            {
                "title": title,
                "insight": takeaway,
                "so_what": _s(item.get("so_what")),
                "now_what": _s(item.get("now_what")),
                "status_label": "Chart-backed",
                "limitation": limitation,
            }
        )
        if len(cards) >= limit:
            break
    return cards


def _coerce_insights(
    raw_insights: object, *, report_title: str
) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []
    for raw_item in _coerce_list(raw_insights):
        item = _coerce_dict(raw_item)
        text = (
            _sanitize_public_prose(item.get("text"))
            if item
            else _sanitize_public_prose(raw_item)
        )
        if not text:
            continue
        insights.append(
            {
                "text": text,
                "so_what": _sanitize_public_prose(item.get("so_what")),
                "now_what": _sanitize_public_prose(item.get("now_what")),
                "citation_line": _build_citation_micro_line(
                    report_title=report_title,
                    evidence_id=_s(item.get("evidence_id")),
                    citation="",
                    evidence_spans=item.get("evidence_spans"),
                    pages=item.get("pages"),
                ),
            }
        )
    return insights


def _coerce_quotes(
    raw_quotes: object, data: dict[str, Any], publisher: str, *, report_title: str
) -> list[dict[str, str]]:
    quotes: list[dict[str, str]] = []
    for raw_item in _coerce_list(raw_quotes):
        item = _coerce_dict(raw_item)
        text = _sanitize_public_prose(
            _pick_first_text(
                item.get("text"), raw_item if isinstance(raw_item, str) else ""
            )
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
                "citation": "",
                "citation_line": _build_citation_micro_line(
                    report_title=report_title,
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
    legacy_text = _sanitize_public_prose(legacy_quote.get("text"))
    if legacy_text:
        return [
            {
                "text": legacy_text,
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
    report_title: str,
    evidence_id: str,
    citation: str,
    evidence_spans: object,
    pages: object,
) -> str:
    parts: list[str] = []
    normalized_evidence_id = _public_citation_label(_s(evidence_id))
    normalized_citation = _public_citation_label(_s(citation))
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
    source_label = _s(report_title)
    if normalized_evidence_id:
        parts.append(normalized_evidence_id)
    if all_pages:
        page_label = "page" if len(all_pages) == 1 else "pages"
        page_text = f"{page_label} {', '.join(str(page) for page in all_pages)}"
        if normalized_evidence_id:
            parts.append(f"report {page_text}")
        else:
            parts.append(f"{source_label}, {page_text}" if source_label else page_text)
    elif source_label and not normalized_evidence_id:
        parts.append(source_label)
    if normalized_citation:
        parts.append(normalized_citation)
    return " · ".join(part for part in parts if part)


def _public_citation_label(value: str) -> str:
    label = _s(value)
    if not label:
        return ""
    # Some model outputs wrap an otherwise internal evidence identifier in
    # quotes.  It is still an internal identifier and must not become public
    # merely because the wrapper prevents a full-string token match.
    comparison_label = label.strip("'\"")
    lowered = comparison_label.casefold()
    if lowered.startswith("local-"):
        return ""
    if "\\" in label or "/" in label:
        return ""
    if ":" in label and len(label) >= 2 and label[1] == ":":
        return ""
    if lowered.endswith((".json", ".jsonl", ".txt", ".sqlite", ".db")):
        return ""
    if lowered in {
        "context_category_fit",
        "quote_candidates",
        "report_context",
    }:
        return ""
    if re.match(r"(?:quote|finding|insight|figure|claim)[_-]", lowered):
        return ""
    if re.fullmatch(
        r"(?:[a-z]{1,4}[-_]?\d{1,5}|(?:quote|finding|insight|figure|claim)[_-][a-z0-9_-]+)",
        lowered,
    ):
        return ""
    if "internal" in lowered or "canonical" in lowered:
        return ""
    return label


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


def _build_signal_cards(
    *,
    topics: list[str],
    topic_briefs: list[dict[str, Any]],
    tags: list[Any],
    prefer_key_points: bool = False,
) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    briefs_by_title = {
        _s(item.get("title")).casefold(): item
        for item in topic_briefs
        if _s(item.get("title"))
    }
    source_labels = topics or [_s(tag) for tag in tags if _s(tag)]
    for label in source_labels[:6]:
        brief = briefs_by_title.get(_s(label).casefold(), {})
        summary = _s(brief.get("summary"))
        points = [
            _s(point) for point in _coerce_list(brief.get("key_points")) if _s(point)
        ]
        if prefer_key_points and points:
            summary = " ".join(points)
        elif summary and points:
            summary = f"{summary} {' '.join(points)}"
        if not summary:
            summary = points[0] if points else ""
        cards.append(
            {
                "title": label,
                "summary": summary
                or "Report-linked theme extracted from the source analysis.",
            }
        )
    return cards


def _is_visual_candidate_slide(slide: dict[str, Any]) -> bool:
    page = slide.get("page")
    if not isinstance(page, int) or page < 0:
        return False
    kind = _s(slide.get("kind")).casefold()
    if kind and kind not in {"chart", "table", "figure", "image", "graph"}:
        return False
    return bool(_s(slide.get("src")))


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


__all__ = [
    "_build_tag_acronym_map",
    "_s",
    "_coerce_dict",
    "_coerce_list",
    "_coerce_positive_int",
    "_pick_first_text",
    "_sanitize_linkedin_post",
    "_sanitize_public_prose",
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
    "_coerce_public_advisory",
    "_coerce_public_topics_covered",
    "_coerce_public_key_figures",
    "_coerce_public_chart_insight_cards",
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
]
