from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

from src.utils.coercion import stripped_string_value as _s
from src.utils.public_metric_display import normalize_public_metric_display
from src.utils.verified_facts import (
    VERIFIED_FACT_EVIDENCE_PREFIX,
    verified_advisory_evidence_ids,
    verified_facts_mode,
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
    r"(?:\s*[\[(](?!(?:q\d{1,3}|h[12]|day[-_]?\d{1,5})\b)(?:[a-z]{1,4}|finding|insight|claim)[_-]?\d{1,5}[\])]|"
    r"\b(?!(?:q\d{1,3}|h[12]|day[-_]?\d{1,5})\b)(?:[a-z]{1,4}|finding|insight|claim)[_-]?\d{1,5}\b)",
    re.IGNORECASE,
)
_PROVIDER_FILE_CITATION = re.compile(
    r"\ue200filecite(?:\ue202turn\d*file\d+)+\ue201", re.IGNORECASE
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
    r"should|may|might|must|do|does|did|has|have|had|changes?|creates?|"
    r"drives?|enables?|supports?|reduces?|improves?|accelerates?|informs?|"
    r"guides?|requires?|shows?|signals?|shifts?|increases?|decreases?|grows?|"
    r"falls?|remains?|becomes?|continues?|reflects?|indicates?|helps?|makes?|"
    r"puts?|leaves?|reveals?)\b)|"
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


_NON_PUBLIC_CHART_CARD_STATUSES = frozenset(
    {
        "weak",
        "weak_evidence",
        "limited",
        "abstained",
        "text_only",
        "not_applicable",
        "omitted",
        "unavailable",
    }
)


def _verified_bound_evidence_ids(artifacts: dict[str, Any]) -> set[str]:
    if not verified_facts_mode(artifacts):
        return set()
    fact_values = _coerce_list(artifacts.get("verified_facts"))
    return {
        f"{VERIFIED_FACT_EVIDENCE_PREFIX}{_s(_coerce_dict(item).get('fact_id'))}"
        for item in fact_values
        if _s(_coerce_dict(item).get("fact_id"))
    }


def _public_evidence_ids(item: object, *, verified_mode: bool = False) -> list[str]:
    """Return the retained primary-first bindings for one public row."""

    payload = _coerce_dict(item)
    primary = _s(payload.get("evidence_id"))
    if not verified_mode:
        return [primary] if primary else []
    values: list[str] = [primary] if primary else []
    for value in _coerce_list(payload.get("evidence_ids")):
        normalized = _s(value)
        if normalized:
            values.append(normalized)
    return list(dict.fromkeys(values))


def _is_public_chart_insight_card(item: object) -> bool:
    """Match the renderer's accepted chart-card projection predicate."""

    card = _coerce_dict(item)
    status = _s(card.get("status")).casefold()
    return (
        status not in _NON_PUBLIC_CHART_CARD_STATUSES
        and card.get("crop_qa_accepted") is True
        and bool(_s(card.get("candidate_id")))
        and bool(_s(card.get("evidence_id")))
        and bool(_s(card.get("source_page")))
        and bool(_s(card.get("insight_id")))
        and bool(
            _pick_first_text(
                _sanitize_public_prose(card.get("caption")),
                _sanitize_public_prose(card.get("retained_caption")),
            )
        )
        and bool(_sanitize_public_prose(card.get("public_takeaway")))
    )


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
    sanitized = _PROVIDER_FILE_CITATION.sub("", text)
    sanitized = re.sub(
        r"\s{2,}", " ", _INLINE_INTERNAL_REFERENCE.sub("", sanitized)
    ).strip()
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
    candidates: list[dict[str, str]] = []
    for index, insight in enumerate(insights):
        if not isinstance(insight, dict):
            continue
        text = _s(insight.get("text"))
        if not text:
            continue
        for sentence in _complete_sentences(text):
            body = sentence.strip()
            if body:
                candidates.append(
                    {
                        "body": body,
                        "insight_id": _s(insight.get("id")) or f"insight-{index + 1}",
                        "evidence_id": _s(insight.get("evidence_id")),
                    }
                )

    # Summary prose is a fallback only. A selected retained insight is the
    # canonical unit for both the displayed heading and the supporting body.
    if not candidates:
        for source_id, source_text in (
            ("summary-tldr", _s(tldr_text)),
            ("summary-executive", _s(executive_summary)),
        ):
            for sentence in _complete_sentences(source_text):
                body = sentence.strip()
                if body:
                    candidates.append(
                        {
                            "body": body,
                            "insight_id": source_id,
                            "evidence_id": "",
                        }
                    )

    selected = next(
        (
            candidate
            for candidate in candidates
            if not _CORE_SIGNAL_ANNOTATION.search(candidate["body"])
        ),
        candidates[0] if candidates else {},
    )
    body = _s(selected.get("body"))
    heading = _core_signal_heading(body) if body else ""
    return {
        "heading": heading or body,
        "body": body,
        "insight_id": _s(selected.get("insight_id")),
        "evidence_id": _s(selected.get("evidence_id")),
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
    edition: str,
    published_date: str,
    data_period: str,
    fieldwork_dates: str,
    region: str,
    report_author: str,
) -> list[str]:
    items: list[str] = []
    if report_title:
        items.append(f"Title: {report_title}")
    if publisher:
        items.append(f"Publisher: {publisher}")
    if edition:
        items.append(f"Edition: {edition}")
    if published_date:
        items.append(f"Published: {published_date}")
    if data_period:
        items.append(f"Data period: {data_period}")
    if fieldwork_dates:
        items.append(f"Fieldwork: {fieldwork_dates}")
    if region:
        items.append(f"Region: {region}")
    if report_author:
        items.append(f"Author: {report_author}")
    return items


def _coerce_claim_map(
    summary: dict[str, Any],
    *,
    report_title: str,
    verified_evidence_ids: set[str] | None = None,
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw_item in _coerce_list(summary.get("claim_evidence_map")):
        item = _coerce_dict(raw_item)
        claim = _s(item.get("claim"))
        if not claim:
            continue
        evidence_id = _s(item.get("evidence_id"))
        if verified_evidence_ids is not None:
            evidence_ids = list(
                dict.fromkeys(
                    value
                    for value in (
                        evidence_id,
                        *[
                            _s(value)
                            for value in _coerce_list(item.get("evidence_ids"))
                        ],
                    )
                    if value
                )
            )
            if not set(evidence_ids).intersection(verified_evidence_ids):
                continue
            evidence_id = next(
                (
                    candidate_id
                    for candidate_id in evidence_ids
                    if candidate_id in verified_evidence_ids
                ),
                "",
            )
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
) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    verified_mode = verified_facts_mode(artifacts)
    allowed_evidence_ids = _verified_bound_evidence_ids(artifacts)
    for raw_item in _coerce_list(artifacts.get("metric_spine")):
        item = _coerce_dict(raw_item)
        evidence_ids = _public_evidence_ids(item, verified_mode=verified_mode)
        evidence_id = evidence_ids[0] if evidence_ids else ""
        if verified_mode and (
            not evidence_ids or not set(evidence_ids).issubset(allowed_evidence_ids)
        ):
            continue
        public_copy = _sanitize_public_prose(item.get("metric_public_copy"))
        if verified_mode and not public_copy:
            # A verified metric may remain in the audit spine, but it is not a
            # reader-facing claim until its final editorial sentence has been
            # independently reviewed.
            continue
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
                _s(item.get("subject")),
                _s(item.get("segment")),
                _s(item.get("cohort")),
                _s(item.get("denominator")),
                _s(item.get("geography")),
                _s(item.get("timeframe")),
                _s(item.get("observation_status")),
                _s(item.get("forecast_status")),
            )
            if part
        )
        metrics.append(
            {
                "metric_id": _s(item.get("metric_id")),
                "label": label,
                "value": metric_value,
                "public_copy": public_copy,
                "context": context,
                "evidence_id": evidence_id,
                "evidence_ids": evidence_ids,
                "confidence_label": _public_label_from_token(item.get("confidence"))
                or "Source-backed",
            }
        )
        if len(metrics) >= limit:
            break
    return metrics


def _coerce_public_claim_support(
    artifacts: dict[str, Any], *, limit: int = 4
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    verified_mode = verified_facts_mode(artifacts)
    allowed_evidence_ids = _verified_bound_evidence_ids(artifacts)
    for raw_item in _coerce_list(artifacts.get("claim_ledgers")):
        item = _coerce_dict(raw_item)
        evidence_ids = {
            _s(value) for value in _coerce_list(item.get("evidence_ids")) if _s(value)
        }
        if verified_mode and not evidence_ids.intersection(allowed_evidence_ids):
            continue
        claim_text = _sanitize_public_prose(item.get("claim_text"))
        if not claim_text:
            continue
        support_type = _public_label_from_token(item.get("support_type"))
        confidence = _public_label_from_token(item.get("confidence"))
        risk = _public_label_from_token(item.get("risk"))
        labels = [label for label in (support_type, confidence, risk) if label]
        canonical_claim_id = _s(item.get("canonical_claim_id")) or _s(
            item.get("claim_id")
        )
        if _s(item.get("artifact_section")) == "metric_spine":
            metric_id = canonical_claim_id.rsplit(":", 1)[-1]
            source_matches = [
                insight
                for insight in _coerce_list(artifacts.get("insights_final"))
                if isinstance(insight, dict)
                and _s(insight.get("id") or insight.get("insight_id")) == metric_id
            ]
            source_copy = (
                _sanitize_public_prose(source_matches[0].get("metric_public_copy"))
                if len(source_matches) == 1
                else ""
            )
            if not source_copy:
                spine_matches = [
                    metric
                    for metric in _coerce_list(artifacts.get("metric_spine"))
                    if isinstance(metric, dict)
                    and _s(metric.get("metric_id")) == metric_id
                    and _s(metric.get("evidence_id")) in evidence_ids
                ]
                source_copy = (
                    _sanitize_public_prose(spine_matches[0].get("metric_public_copy"))
                    if len(spine_matches) == 1
                    else ""
                )
            if source_copy:
                claim_text = source_copy
            elif verified_mode:
                # Do not expose the universal ledger's diagnostic field
                # serialization when the authoritative final copy is absent.
                continue
        claims.append(
            {
                "canonical_claim_id": canonical_claim_id,
                "claim_id": canonical_claim_id,
                "artifact_section": _s(item.get("artifact_section")),
                "claim": claim_text,
                "support_label": " · ".join(labels) if labels else "Source-backed",
                "evidence_ids": sorted(evidence_ids),
            }
        )
        if len(claims) >= limit:
            break
    return claims


def _coerce_public_advisory(artifacts: dict[str, Any]) -> dict[str, Any]:
    advisory = _coerce_dict(artifacts.get("executive_advisory"))
    decision_brief = _coerce_dict(advisory.get("decision_brief"))
    status = _s(decision_brief.get("status")).casefold()
    verified_mode = verified_facts_mode(artifacts)
    allowed_evidence_ids = _verified_bound_evidence_ids(artifacts)
    decision_evidence_ids = {
        _s(value)
        for value in _coerce_list(decision_brief.get("evidence_links"))
        if _s(value)
    }
    decision_supported = not verified_mode or bool(
        decision_evidence_ids.intersection(allowed_evidence_ids)
    )
    confidence_note = _sanitize_public_prose(decision_brief.get("confidence_note"))
    if confidence_note.casefold() in {
        "metric spine available",
        "evidence-linked insights available",
    }:
        confidence_note = ""
    if (
        verified_mode
        and confidence_note
        and not verified_advisory_evidence_ids(
            artifacts, "confidence_note", confidence_note
        )
    ):
        confidence_note = ""

    def advisory_texts(field: str, value: object) -> list[str]:
        texts = _coerce_text_items(value, limit=4)
        if not verified_mode:
            return texts
        return [
            text
            for text in texts
            if verified_advisory_evidence_ids(artifacts, field, text)
        ]

    strategic_context = _sanitize_public_prose(decision_brief.get("strategic_context"))
    if (
        verified_mode
        and strategic_context
        and not verified_advisory_evidence_ids(
            artifacts, "strategic_context", strategic_context
        )
    ):
        strategic_context = ""
    decision = {
        "available": status == "generated" and decision_supported,
        "strategic_context": strategic_context if decision_supported else "",
        "decision_implications": (
            advisory_texts(
                "decision_implications", decision_brief.get("decision_implications")
            )
            if decision_supported
            else []
        ),
        "priority_moves": (
            advisory_texts("priority_moves", decision_brief.get("priority_moves"))
            if decision_supported
            else []
        ),
        "watchouts": (
            advisory_texts("watchouts", decision_brief.get("watchouts"))
            if decision_supported
            else []
        ),
        "confidence_note": confidence_note if decision_supported else "",
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
    key_figures = _coerce_public_key_figures(artifacts)
    metric_spine = _coerce_public_metric_spine(artifacts)
    claim_support = _coerce_public_claim_support(artifacts)
    key_figures, metric_spine, claim_support = _deduplicate_public_metric_surfaces(
        key_figures=key_figures,
        metric_spine=metric_spine,
        claim_support=claim_support,
        verified_mode=verified_mode,
    )
    return {
        "decision": decision,
        "recommendations": recommendations,
        "risks": risks,
        "metric_spine": metric_spine,
        "claim_support": claim_support,
        "key_figures": key_figures,
    }


def _deduplicate_public_metric_surfaces(
    *,
    key_figures: list[dict[str, Any]],
    metric_spine: list[dict[str, Any]],
    claim_support: list[dict[str, Any]],
    verified_mode: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep one exact public placement for a verified metric sentence.

    The metric spine is the canonical reader-facing placement.  Key figures
    and the claim ledger remain authoritative retained structures, but an
    identical sentence with the same evidence binding is not shown or sent to
    the semantic reviewer a second time.  No semantic similarity is used.
    """

    if not verified_mode:
        return key_figures, metric_spine, claim_support

    def identity(
        item: dict[str, Any], text_key: str
    ) -> tuple[str, tuple[str, ...]] | None:
        text = " ".join(_s(item.get(text_key)).split()).casefold()
        evidence_ids = tuple(
            sorted(
                {
                    _s(value)
                    for value in _coerce_list(item.get("evidence_ids"))
                    if _s(value)
                }
            )
        )
        if not text or not evidence_ids:
            return None
        return text, evidence_ids

    seen: set[tuple[str, tuple[str, ...]]] = set()
    retained_metric_spine: list[dict[str, Any]] = []
    for item in metric_spine:
        key = identity(item, "public_copy")
        if key is not None:
            seen.add(key)
        retained_metric_spine.append(item)

    retained_key_figures: list[dict[str, Any]] = []
    for item in key_figures:
        key = identity(item, "public_copy")
        if key is not None and key in seen:
            continue
        if key is not None:
            seen.add(key)
        retained_key_figures.append(item)

    retained_claim_support: list[dict[str, Any]] = []
    for item in claim_support:
        key = identity(item, "claim")
        if key is not None and key in seen:
            continue
        if key is not None:
            seen.add(key)
        retained_claim_support.append(item)

    return retained_key_figures, retained_metric_spine, retained_claim_support


def _coerce_public_topics_covered(
    artifacts: dict[str, Any],
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    topics: list[dict[str, Any]] = []
    verified_mode = verified_facts_mode(artifacts)
    allowed_evidence_ids = _verified_bound_evidence_ids(artifacts)
    raw_topics = (
        _coerce_list(artifacts.get("topics_covered"))
        or _coerce_list(artifacts.get("toc_topics_expanded"))
        or _coerce_list(artifacts.get("toc_entries"))
    )
    for index, raw_item in enumerate(raw_topics, start=1):
        item = _coerce_dict(raw_item)
        evidence_ids = {
            _s(value)
            for value in (
                [_s(item.get("evidence_id"))] + _coerce_list(item.get("evidence_ids"))
            )
            if _s(value)
        }
        if verified_mode and not evidence_ids.intersection(allowed_evidence_ids):
            continue
        title = _sanitize_public_prose(
            _pick_first_text(
                item.get("topic"),
                item.get("title"),
                item.get("display_title"),
                raw_item if isinstance(raw_item, str) else "",
            )
        )
        if not title:
            continue
        toc_only = _s(item.get("status")).casefold() == "toc_only"
        pages = [
            str(page).strip() for page in _coerce_list(item.get("pages")) if _s(page)
        ]
        topics.append(
            {
                "topic_id": _s(item.get("id"))
                or _s(item.get("topic_id"))
                or str(index),
                "topic": title,
                "summary": (
                    "Covered by the source report."
                    if toc_only
                    else _sanitize_public_prose(
                        _pick_first_text(
                            item.get("why_it_matters"),
                            item.get("summary"),
                            "Covered by the source report.",
                        )
                    )
                ),
                "subtopics": (
                    []
                    if toc_only
                    else [
                        _sanitize_public_prose(point)
                        for point in _coerce_list(item.get("subtopics"))
                        if _sanitize_public_prose(point)
                    ][:4]
                ),
                "source_label": f"Pages {', '.join(pages)}" if pages else "",
                "evidence_ids": sorted(evidence_ids),
            }
        )
        if len(topics) >= limit:
            break
    return topics


def _coerce_public_key_figures(
    artifacts: dict[str, Any],
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    verified_mode = verified_facts_mode(artifacts)
    allowed_evidence_ids = _verified_bound_evidence_ids(artifacts)
    raw_figures = _coerce_list(artifacts.get("key_figures")) or _coerce_list(
        artifacts.get("metric_spine")
    )
    for raw_item in raw_figures:
        item = _coerce_dict(raw_item)
        evidence_ids = _public_evidence_ids(item, verified_mode=verified_mode)
        evidence_id = evidence_ids[0] if evidence_ids else ""
        if verified_mode and (
            not evidence_ids or not set(evidence_ids).issubset(allowed_evidence_ids)
        ):
            continue
        public_copy = _sanitize_public_prose(item.get("metric_public_copy"))
        if verified_mode and not public_copy:
            continue
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
                "public_copy": public_copy,
                "label": label,
                "context": ", ".join(
                    dict.fromkeys(
                        part
                        for part in (
                            _s(item.get("context")),
                            _s(item.get("subject")),
                            _s(item.get("cohort")),
                            _s(item.get("denominator")),
                            _s(item.get("segment")),
                            _s(item.get("geography")),
                            _s(item.get("timeframe")),
                            _s(item.get("observation_status")),
                            _s(item.get("forecast_status")),
                        )
                        if part
                    )
                ),
                "figure_id": _s(item.get("figure_id"))
                or _s(item.get("key_figure_id"))
                or _s(item.get("id")),
                "metric_id": _s(item.get("metric_id")) or _s(item.get("insight_id")),
                "evidence_id": evidence_id,
                "evidence_ids": evidence_ids,
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
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    verified_mode = verified_facts_mode(artifacts)
    allowed_evidence_ids = _verified_bound_evidence_ids(artifacts)
    for raw_item in _coerce_list(artifacts.get("chart_insight_cards")):
        item = _coerce_dict(raw_item)
        if not _is_public_chart_insight_card(item):
            continue
        candidate_id = _s(item.get("candidate_id"))
        evidence_ids = _public_evidence_ids(item, verified_mode=verified_mode)
        evidence_id = evidence_ids[0] if evidence_ids else ""
        if verified_mode and (
            not evidence_ids or not set(evidence_ids).issubset(allowed_evidence_ids)
        ):
            continue
        source_page = _s(item.get("source_page"))
        insight_id = _s(item.get("insight_id"))
        caption = _pick_first_text(
            _sanitize_public_prose(item.get("caption")),
            _sanitize_public_prose(item.get("retained_caption")),
        )
        takeaway = _sanitize_public_prose(item.get("public_takeaway"))
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
            _sanitize_public_prose(item.get("title")),
            _sanitize_public_prose(item.get("chart_title")),
            caption,
            takeaway,
        )
        limitation = _pick_first_text(
            _sanitize_public_prose(item.get("limitation")),
            _sanitize_public_prose(item.get("avoid_reason")),
            _sanitize_public_prose(item.get("avoid_reason_if_weak")),
            _sanitize_public_prose(item.get("diagnostic")),
        )
        if not title:
            continue
        card: dict[str, Any] = {
            "candidate_id": candidate_id,
            "insight_id": insight_id,
            "evidence_id": evidence_id,
            "title": title,
            "insight": takeaway,
            "so_what": _sanitize_public_prose(item.get("so_what")),
            "now_what": _sanitize_public_prose(item.get("now_what")),
            "status_label": "Chart-backed",
            "limitation": limitation,
        }
        if verified_mode:
            card["evidence_ids"] = evidence_ids
        cards.append(card)
        if len(cards) >= limit:
            break
    return cards


def _coerce_insights(
    raw_insights: object, *, report_title: str
) -> list[dict[str, Any]]:
    insights: list[dict[str, Any]] = []
    for raw_item in _coerce_list(raw_insights):
        item = _coerce_dict(raw_item)
        text = (
            _sanitize_public_prose(item.get("text"))
            if item
            else _sanitize_public_prose(raw_item)
        )
        if not text:
            continue
        spans = _coerce_evidence_spans(item.get("evidence_spans"))
        section_ids = list(
            dict.fromkeys(
                value
                for value in (
                    _s(item.get("section_id")),
                    *[_s(span.get("section_id")) for span in spans],
                )
                if value
            )
        )
        insights.append(
            {
                "id": _s(item.get("id")),
                "text": text,
                "so_what": _sanitize_public_prose(item.get("so_what")),
                "now_what": _sanitize_public_prose(item.get("now_what")),
                "evidence_id": _s(item.get("evidence_id")),
                "section_ids": section_ids,
                "coverage_role": _s(item.get("coverage_role")),
                "report_type_lens": _s(item.get("report_type_lens")),
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
    raw_quotes: object,
    data: dict[str, Any],
    publisher: str,
    *,
    report_title: str,
    allow_legacy_fallback: bool = True,
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
    if not allow_legacy_fallback:
        return []
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
        internal_tokens = re.finditer(
            r"(?:quote|finding|insight|figure|claim)[_-][a-z0-9_-]+",
            normalized_author,
            re.IGNORECASE,
        )
        if not any(
            not _public_citation_label(match.group(0)) for match in internal_tokens
        ):
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
    if lowered.startswith(VERIFIED_FACT_EVIDENCE_PREFIX):
        return ""
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
    if re.search(
        r"(?<![a-z0-9])(?:quote|finding|insight|figure|claim)[_-][a-z0-9_-]+",
        lowered,
    ):
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
    coverage_by_title: dict[str, dict[str, Any]] = {}
    for raw_coverage in _coerce_list(artifacts.get("topics_covered")):
        coverage_item = _coerce_dict(raw_coverage)
        coverage_title = _pick_first_text(
            coverage_item.get("topic"), coverage_item.get("title")
        )
        if coverage_title:
            coverage_by_title[
                unicodedata.normalize("NFC", coverage_title).casefold()
            ] = coverage_item
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
        coverage = coverage_by_title.get(
            unicodedata.normalize("NFC", title).casefold(), {}
        )
        coverage_status = _s(coverage.get("status")).casefold()
        toc_only = coverage_status == "toc_only"
        if coverage_status:
            summary = "" if toc_only else _s(coverage.get("why_it_matters"))
            key_points_source = (
                [] if toc_only else _coerce_list(coverage.get("subtopics"))
            )
        else:
            summary = _s(item.get("summary"))
            key_points_source = _coerce_list(item.get("key_points"))
        briefs.append(
            {
                "section_id": _s(item.get("section_id") or item.get("id")),
                "title": title,
                "summary": summary,
                "key_points": [_s(point) for point in key_points_source if _s(point)],
            }
        )
    return briefs


def _coerce_chapters(
    artifacts: dict[str, Any],
    doc_map: dict[str, Any],
    *,
    verified_mode: bool = False,
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
                "summary": "" if verified_mode else _s(item.get("summary")),
                "pages": toc_pages,
            }
        )
    if chapters:
        return chapters
    if verified_mode:
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
    insights: list[dict[str, Any]] | None = None,
    prefer_key_points: bool = False,
) -> list[dict[str, Any]]:
    brief_title_matches: dict[str, list[dict[str, Any]]] = {}
    brief_section_matches: dict[str, list[dict[str, Any]]] = {}
    for item in topic_briefs:
        title = _s(item.get("title"))
        if title:
            title_key = unicodedata.normalize("NFC", title).casefold()
            brief_title_matches.setdefault(title_key, []).append(item)
        section_id = _s(item.get("section_id")).strip()
        if section_id:
            brief_section_matches.setdefault(section_id, []).append(item)
    briefs_by_title = {
        key: matches[0]
        for key, matches in brief_title_matches.items()
        if len(matches) == 1
    }
    briefs_by_section = {
        key: matches[0]
        for key, matches in brief_section_matches.items()
        if len(matches) == 1
    }
    has_structured_insights = any(
        _s(item.get("evidence_id"))
        or _s(item.get("so_what"))
        or _s(item.get("now_what"))
        or _coerce_list(item.get("section_ids"))
        for item in insights or []
    )
    if insights and has_structured_insights:
        role_labels = {
            "market_context": "Market context",
            "behavior_shift": "Behavior shift",
            "strategic_risk": "Strategic risk",
            "operating_implication": "Operating implication",
            "investment_signal": "Investment signal",
            "proof_point": "Proof point",
            "counter_signal": "Counter-signal",
        }
        cards: list[dict[str, Any]] = []
        for insight in insights:
            signal = _sanitize_public_prose(insight.get("text"))
            if not signal:
                continue
            brief: dict[str, Any] = {}
            for section_id in _coerce_list(insight.get("section_ids")):
                candidate_brief = briefs_by_section.get(_s(section_id).strip())
                if candidate_brief:
                    brief = candidate_brief
                    break
            role = _s(insight.get("coverage_role"))
            title = _pick_first_text(
                brief.get("title"),
                role_labels.get(role, ""),
                _core_signal_heading(signal),
                signal,
            )
            cards.append(
                {
                    "title": title,
                    "signal": signal,
                    "so_what": _sanitize_public_prose(insight.get("so_what")),
                    "now_what": _sanitize_public_prose(insight.get("now_what")),
                    "source_label": _sanitize_public_prose(
                        insight.get("citation_line")
                    ),
                }
            )
            if len(cards) >= 6:
                break
        if cards:
            return cards

    cards = []
    source_labels = topics or [_s(tag) for tag in tags if _s(tag)]
    for label in source_labels[:6]:
        title_key = unicodedata.normalize("NFC", _s(label)).casefold()
        brief = briefs_by_title.get(title_key, {})
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


def _coerce_limitation_items(
    evidence_packs: dict[str, Any],
    *,
    verified_mode: bool = False,
    artifacts: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return the exact source-backed limitation rows used by the renderer."""

    limitations_pack = _coerce_dict(evidence_packs.get("limitations"))
    limitations: list[dict[str, Any]] = []
    planned_limitation_ids = {
        _s(evidence_id).strip().casefold()
        for evidence_id in _coerce_list(
            _coerce_dict((artifacts or {}).get("editorial_plan")).get(
                "material_limitation_evidence_ids"
            )
        )
        if _s(evidence_id).strip()
    }
    for raw_item in _coerce_list(limitations_pack.get("limitations")):
        item = _coerce_dict(raw_item)
        message = _pick_first_text(
            item.get("message"),
            item.get("description"),
            item.get("text"),
            item.get("summary"),
            item.get("mitigation"),
        )
        if message:
            evidence_ids = [
                _s(item.get("evidence_id")),
                *[_s(value) for value in _coerce_list(item.get("evidence_ids"))],
            ]
            limitations.append(
                {
                    "text": message,
                    "evidence_ids": list(
                        dict.fromkeys(value for value in evidence_ids if value)
                    ),
                }
            )
    if limitations and planned_limitation_ids:
        limitations = [
            item
            for item in limitations
            if {
                evidence_id.strip().casefold()
                for evidence_id in item.get("evidence_ids", [])
                if evidence_id.strip()
            }.intersection(planned_limitation_ids)
        ]
    if limitations or not verified_mode:
        return limitations[:5]
    verified_pack = _coerce_dict(evidence_packs.get("verified_facts"))
    raw_facts = _coerce_list(verified_pack.get("verified_facts"))
    if not raw_facts and isinstance(evidence_packs.get("verified_facts"), list):
        raw_facts = _coerce_list(evidence_packs.get("verified_facts"))
    selected_evidence_ids: set[str] = set()
    for raw_insight in _coerce_list((artifacts or {}).get("insights_final")):
        insight = _coerce_dict(raw_insight)
        selected_evidence_ids.update(
            value
            for value in [
                _s(insight.get("evidence_id")),
                *[_s(item) for item in _coerce_list(insight.get("evidence_ids"))],
            ]
            if value
        )
    fact_rows: list[dict[str, Any]] = []
    for raw_fact in raw_facts:
        fact = _coerce_dict(raw_fact)
        fact_id = _s(fact.get("fact_id"))
        evidence_id = f"{VERIFIED_FACT_EVIDENCE_PREFIX}{fact_id}" if fact_id else ""
        for raw_qualifier in _coerce_list(fact.get("qualifiers")):
            qualifier = _s(raw_qualifier)
            if qualifier and (
                not planned_limitation_ids
                or evidence_id.casefold() in planned_limitation_ids
            ):
                fact_rows.append(
                    {
                        "text": qualifier,
                        "evidence_ids": [evidence_id] if evidence_id else [],
                        "_selected": evidence_id in selected_evidence_ids,
                    }
                )
    fact_rows.sort(key=lambda row: not bool(row.pop("_selected", False)))
    seen_texts = {item["text"] for item in limitations}
    for row in fact_rows:
        if row["text"] in seen_texts:
            continue
        limitations.append(row)
        seen_texts.add(row["text"])
        if len(limitations) >= 5:
            break
    return limitations


def _coerce_limitations(
    evidence_packs: dict[str, Any],
    *,
    verified_mode: bool = False,
    artifacts: dict[str, Any] | None = None,
) -> list[str]:
    return [
        item["text"]
        for item in _coerce_limitation_items(
            evidence_packs,
            verified_mode=verified_mode,
            artifacts=artifacts,
        )
    ]


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
    "_is_public_chart_insight_card",
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
