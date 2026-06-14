from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from src.generators.artifact_normalization import (
    normalize_artifact_toc_entries,
)
from src.utils.coercion import string_value as _s

logger = logging.getLogger("market_lense.artifact_generator")

TOPIC_TOKEN_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
TOPIC_BRIEF_MAX_KEY_POINTS = 4
TOPIC_SECTION_MATCH_MIN_SCORE = 35
TOPIC_SECTION_REASSIGN_MARGIN = 8
TOPIC_BRIEF_MAPPING_VERSION = "3"
TOC_STRUCTURE_VERSION = "1"
TOC_EXCLUDED_TITLE_MARKERS = (
    "about the author",
    "about the authors",
    "about us",
    "appendix",
    "appendices",
    "bibliography",
    "contact",
    "contact us",
    "disclaimer",
    "glossary",
    "legal notice",
    "panel discussion",
    "q&a",
    "q & a",
    "questions",
    "references",
    "thank you",
    "thanks",
)


def _normalize_topic_lookup_text(value: Any) -> str:
    text = _s(value).strip().lower()
    if not text:
        return ""
    collapsed = re.sub(r"[^a-z0-9]+", " ", text)
    collapsed = re.sub(r"\bgen\s*ai\b", "generative ai", collapsed)
    return re.sub(r"\s+", " ", collapsed).strip()


def _normalize_topic_token(token: str) -> str:
    clean = _normalize_topic_lookup_text(token)
    if not clean:
        return ""
    if clean.endswith("ies") and len(clean) > 4:
        return f"{clean[:-3]}y"
    if clean.endswith("s") and len(clean) > 3 and not clean.endswith("ss"):
        return clean[:-1]
    return clean


def _topic_tokens(value: Any) -> List[str]:
    normalized = _normalize_topic_lookup_text(value)
    if not normalized:
        return []
    tokens: List[str] = []
    for raw_token in normalized.split(" "):
        token = _normalize_topic_token(raw_token)
        if not token or token in TOPIC_TOKEN_STOPWORDS or token in tokens:
            continue
        tokens.append(token)
    return tokens


def _coerce_topic_key_points(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    points: List[str] = []
    for item in value:
        if isinstance(item, dict):
            text = _s(
                item.get("text")
                or item.get("point")
                or item.get("summary")
                or item.get("value")
            ).strip()
        else:
            text = _s(item).strip()
        if text and text not in points:
            points.append(text)
    return points


def _coerce_topic_pages(value: Any) -> List[int]:
    if not isinstance(value, list):
        return []
    pages: List[int] = []
    for page in value:
        if isinstance(page, int):
            pages.append(page)
    return pages


def _unwrap_doc_map(doc_map: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(doc_map, dict):
        return {}
    candidate = doc_map
    for key in ("doc_map", "docmap", "docMap"):
        wrapped = doc_map.get(key)
        if isinstance(wrapped, dict):
            candidate = wrapped
            break
    return candidate


def _toc_entry_exclusion_reason(title: str) -> str:
    title_norm = _normalize_topic_lookup_text(title)
    if not title_norm:
        return "empty_title"
    for marker in TOC_EXCLUDED_TITLE_MARKERS:
        if marker in title_norm:
            return marker
    return ""


def _toc_display_title(title: str) -> str:
    clean_title = _s(title).strip()
    if not clean_title:
        return ""
    if ":" in clean_title:
        prefix = clean_title.split(":", 1)[0].strip()
        if prefix and len(prefix) <= 60:
            return prefix
    return clean_title


def _dedupe_toc_display_titles(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not entries:
        return []
    counts: Dict[str, int] = {}
    for entry in entries:
        label = _s(entry.get("display_title")).strip()
        if not label:
            continue
        key = label.casefold()
        counts[key] = counts.get(key, 0) + 1
    normalized: List[Dict[str, Any]] = []
    fallback_counts: Dict[str, int] = {}
    for entry in entries:
        updated = dict(entry)
        display_title = _s(updated.get("display_title")).strip()
        section_title = _s(updated.get("section_title")).strip()
        if not display_title:
            display_title = section_title
        key = display_title.casefold()
        if counts.get(key, 0) > 1:
            display_title = section_title
        display_key = display_title.casefold()
        fallback_counts[display_key] = fallback_counts.get(display_key, 0) + 1
        if fallback_counts[display_key] > 1:
            display_title = f"{display_title} ({updated.get('order')})"
        updated["display_title"] = display_title
        normalized.append(updated)
    return normalized


def build_toc_entries(*, doc_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidate = _unwrap_doc_map(doc_map)
    sections_raw = candidate.get("sections")
    if not isinstance(sections_raw, list):
        return []
    entries: List[Dict[str, Any]] = []
    for idx, raw_section in enumerate(sections_raw):
        if not isinstance(raw_section, dict):
            continue
        section_title = _s(
            raw_section.get("title")
            or raw_section.get("heading")
            or raw_section.get("name")
        ).strip()
        if _toc_entry_exclusion_reason(section_title):
            continue
        summary = _s(raw_section.get("summary")).strip()
        key_points = _coerce_topic_key_points(raw_section.get("key_points"))
        if not section_title and not summary and not key_points:
            continue
        section_id = _s(raw_section.get("id")).strip() or f"section-{idx + 1}"
        entries.append(
            {
                "section_id": section_id,
                "section_title": section_title,
                "display_title": _toc_display_title(section_title),
                "summary": summary,
                "key_points": key_points[:TOPIC_BRIEF_MAX_KEY_POINTS],
                "pages": _coerce_topic_pages(raw_section.get("pages")),
                "order": len(entries) + 1,
            }
        )
    return _dedupe_toc_display_titles(entries)


def build_legacy_topic_briefs(
    *, toc_entries: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    briefs: List[Dict[str, Any]] = []
    for entry in normalize_artifact_toc_entries(toc_entries):
        topic = _s(entry.get("display_title")).strip()
        if not topic:
            continue
        briefs.append(
            {
                "topic": topic,
                "summary": _s(entry.get("summary")),
                "key_points": _coerce_topic_key_points(entry.get("key_points")),
                "section_id": _s(entry.get("section_id")).strip(),
                "section_title": _s(entry.get("section_title")).strip(),
                "pages": _coerce_topic_pages(entry.get("pages")),
            }
        )
    return briefs


def build_toc_artifacts(*, doc_map: Dict[str, Any]) -> Dict[str, Any]:
    toc_entries = build_toc_entries(doc_map=doc_map)
    return {
        "toc_entries": toc_entries,
        "toc_topics": [
            _s(entry.get("display_title")).strip()
            for entry in toc_entries
            if _s(entry.get("display_title")).strip()
        ],
        "toc_topics_expanded": build_legacy_topic_briefs(toc_entries=toc_entries),
    }


def _doc_map_sections_for_topics(doc_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidate = _unwrap_doc_map(doc_map)
    sections_raw = candidate.get("sections")
    if not isinstance(sections_raw, list):
        return []
    sections: List[Dict[str, Any]] = []
    for idx, raw_section in enumerate(sections_raw):
        if not isinstance(raw_section, dict):
            continue
        title = _s(
            raw_section.get("title")
            or raw_section.get("heading")
            or raw_section.get("name")
        ).strip()
        section_id = _s(raw_section.get("id")).strip()
        summary = _s(raw_section.get("summary")).strip()
        key_points = _coerce_topic_key_points(raw_section.get("key_points"))
        pages = _coerce_topic_pages(raw_section.get("pages"))
        context_text = " ".join(
            part for part in [title, summary, *key_points] if _s(part).strip()
        )
        sections.append(
            {
                "section_id": section_id,
                "title": title,
                "summary": summary,
                "key_points": key_points,
                "pages": pages,
                "title_norm": _normalize_topic_lookup_text(title),
                "id_norm": _normalize_topic_lookup_text(section_id),
                "title_tokens": _topic_tokens(title),
                "context_norm": _normalize_topic_lookup_text(context_text),
                "context_tokens": _topic_tokens(context_text),
                "index": idx,
            }
        )
    return sections


def _topic_token_overlap_score(
    topic_tokens: List[str], section_tokens: List[str]
) -> int:
    topic_tokens_set = set(topic_tokens)
    section_tokens_set = set(section_tokens)
    if not topic_tokens_set or not section_tokens_set:
        return 0
    overlap = len(topic_tokens_set & section_tokens_set)
    coverage = overlap / max(1, len(topic_tokens_set))
    return int(round(coverage * 45))


def _topic_match_score(
    *,
    topic_norm: str,
    topic_tokens: List[str],
    section: Dict[str, Any],
) -> int:
    score = 0
    title_norm = _s(section.get("title_norm")).strip()
    id_norm = _s(section.get("id_norm")).strip()
    context_norm = _s(section.get("context_norm")).strip()
    if topic_norm and (topic_norm == title_norm or topic_norm == id_norm):
        score += 120
    elif topic_norm and (
        (topic_norm in title_norm and title_norm)
        or (title_norm in topic_norm and topic_norm)
        or (topic_norm in id_norm and id_norm)
    ):
        score += 80
    elif topic_norm and (
        (topic_norm in context_norm and context_norm)
        or (context_norm in topic_norm and topic_norm)
    ):
        score += 55

    score += _topic_token_overlap_score(topic_tokens, section.get("title_tokens") or [])
    score += _topic_token_overlap_score(
        topic_tokens, section.get("context_tokens") or []
    )
    return score


def _best_topic_section_match(
    *,
    topic: str,
    sections: List[Dict[str, Any]],
) -> tuple[Optional[Dict[str, Any]], int]:
    if not sections:
        return None, 0
    topic_norm = _normalize_topic_lookup_text(topic)
    tokens = _topic_tokens(topic)
    best_section: Optional[Dict[str, Any]] = None
    best_score = -1
    for section in sections:
        score = _topic_match_score(
            topic_norm=topic_norm,
            topic_tokens=tokens,
            section=section,
        )
        if score > best_score:
            best_score = score
            best_section = section
    return best_section, max(best_score, 0)


def _select_topic_section(
    *,
    topic: str,
    sections: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    section, score = _best_topic_section_match(topic=topic, sections=sections)
    if score < TOPIC_SECTION_MATCH_MIN_SCORE:
        return None
    return section


def _text_matches_topic(text: str, topic: str) -> bool:
    text_norm = _normalize_topic_lookup_text(text)
    topic_norm = _normalize_topic_lookup_text(topic)
    if not text_norm or not topic_norm:
        return False
    if topic_norm in text_norm:
        return True
    topic_tokens = set(_topic_tokens(topic))
    text_tokens = set(_topic_tokens(text))
    if not topic_tokens or not text_tokens:
        return False
    overlap = len(topic_tokens & text_tokens)
    required = max(1, min(2, len(topic_tokens)))
    return overlap >= required


def _dedupe_non_empty_text(values: List[str], *, limit: int) -> List[str]:
    deduped: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = _s(value).strip()
        if not text:
            continue
        key = _normalize_topic_lookup_text(text)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
        if len(deduped) >= limit:
            break
    return deduped


def _topic_brief_from_claims(
    topic: str, summary: Dict[str, Any]
) -> tuple[str, List[str]]:
    claim_map = summary.get("claim_evidence_map")
    if not isinstance(claim_map, list):
        return "", []
    matching_claims: List[str] = []
    claim_points: List[str] = []
    for claim in claim_map:
        if not isinstance(claim, dict):
            continue
        claim_text = _s(claim.get("claim")).strip()
        evidence_text = _s(claim.get("evidence")).strip()
        if not _text_matches_topic(f"{claim_text} {evidence_text}", topic):
            continue
        if claim_text:
            matching_claims.append(claim_text)
        if evidence_text:
            claim_points.append(evidence_text)
    summary_text = matching_claims[0] if matching_claims else ""
    points = _dedupe_non_empty_text(claim_points, limit=TOPIC_BRIEF_MAX_KEY_POINTS)
    return summary_text, points


def _topic_points_from_insights(
    topic: str, insights_final: List[Dict[str, Any]]
) -> List[str]:
    if not isinstance(insights_final, list):
        return []
    matched: List[str] = []
    for insight in insights_final:
        if not isinstance(insight, dict):
            continue
        insight_text = _s(insight.get("text")).strip()
        if insight_text and _text_matches_topic(insight_text, topic):
            matched.append(insight_text)
    return _dedupe_non_empty_text(matched, limit=TOPIC_BRIEF_MAX_KEY_POINTS)


def _resolve_attached_topic_section(
    *,
    topic_brief: Dict[str, Any],
    sections: List[Dict[str, Any]],
) -> tuple[Optional[Dict[str, Any]], str]:
    if not sections:
        return None, ""
    section_id = _s(topic_brief.get("section_id")).strip()
    section_title = _s(topic_brief.get("section_title")).strip()
    by_id = {
        _s(section.get("section_id")).strip(): section
        for section in sections
        if _s(section.get("section_id")).strip()
    }
    by_title = {
        _s(section.get("title_norm")).strip(): section
        for section in sections
        if _s(section.get("title_norm")).strip()
    }
    section_from_id = by_id.get(section_id) if section_id else None
    title_norm = _normalize_topic_lookup_text(section_title)
    section_from_title = by_title.get(title_norm) if title_norm else None
    if section_from_id and section_from_title and section_from_id != section_from_title:
        return None, "identity_mismatch"
    if section_from_id:
        return section_from_id, "id"
    if section_from_title:
        return section_from_title, "title"
    if section_id or section_title:
        return None, "unknown"
    return None, ""


def audit_topic_brief_mappings(
    *,
    topic_briefs: List[Dict[str, Any]],
    doc_map: Dict[str, Any],
) -> List[Dict[str, Any]]:
    sections = _doc_map_sections_for_topics(doc_map)
    diagnostics: List[Dict[str, Any]] = []
    for index, item in enumerate(topic_briefs):
        if not isinstance(item, dict):
            continue
        topic = _s(item.get("topic")).strip()
        if not topic:
            continue
        attached_section, attached_source = _resolve_attached_topic_section(
            topic_brief=item,
            sections=sections,
        )
        best_section, best_score = _best_topic_section_match(
            topic=topic,
            sections=sections,
        )
        current_score = 0
        if attached_section is not None:
            current_score = _topic_match_score(
                topic_norm=_normalize_topic_lookup_text(topic),
                topic_tokens=_topic_tokens(topic),
                section=attached_section,
            )
        status = "ok"
        if attached_source == "identity_mismatch":
            status = "identity_mismatch"
        elif attached_source == "unknown":
            status = "unknown_section"
        elif (
            attached_section is not None
            and current_score < TOPIC_SECTION_MATCH_MIN_SCORE
        ):
            status = "low_confidence"
        elif (
            attached_section is not None
            and best_section is not None
            and _s(best_section.get("section_id")).strip()
            != _s(attached_section.get("section_id")).strip()
            and best_score >= TOPIC_SECTION_MATCH_MIN_SCORE
            and best_score >= current_score + TOPIC_SECTION_REASSIGN_MARGIN
        ):
            status = "stale_match"
        diagnostics.append(
            {
                "topic_index": index,
                "topic": topic,
                "attached_section_id": _s(item.get("section_id")).strip(),
                "attached_section_title": _s(item.get("section_title")).strip(),
                "resolved_section_id": _s(attached_section.get("section_id")).strip()
                if attached_section
                else "",
                "resolved_section_title": _s(attached_section.get("title")).strip()
                if attached_section
                else "",
                "current_score": current_score,
                "best_section_id": _s(best_section.get("section_id")).strip()
                if best_section
                else "",
                "best_section_title": _s(best_section.get("title")).strip()
                if best_section
                else "",
                "best_score": best_score,
                "status": status,
                "min_score": TOPIC_SECTION_MATCH_MIN_SCORE,
            }
        )
    return diagnostics


def audit_toc_artifacts(
    *,
    artifacts: Dict[str, Any],
    doc_map: Dict[str, Any],
) -> List[Dict[str, Any]]:
    diagnostics: List[Dict[str, Any]] = []
    expected_bundle = build_toc_artifacts(doc_map=doc_map)
    expected_entries = normalize_artifact_toc_entries(
        expected_bundle.get("toc_entries")
    )
    expected_by_id = {
        _s(entry.get("section_id")).strip(): entry for entry in expected_entries
    }
    expected_ids = [entry["section_id"] for entry in expected_entries]

    raw_toc_entries = artifacts.get("toc_entries")
    actual_entries_raw: list[Any] = (
        raw_toc_entries if isinstance(raw_toc_entries, list) else []
    )
    actual_entries = normalize_artifact_toc_entries(actual_entries_raw)
    actual_ids = [_s(entry.get("section_id")).strip() for entry in actual_entries]
    duplicate_ids: set[str] = set()
    seen_ids: set[str] = set()
    for raw_entry in actual_entries_raw:
        if not isinstance(raw_entry, dict):
            continue
        section_id = _s(raw_entry.get("section_id")).strip()
        if not section_id:
            continue
        if section_id in seen_ids:
            duplicate_ids.add(section_id)
        seen_ids.add(section_id)

    if expected_entries and not actual_entries:
        diagnostics.append(
            {
                "status": "missing_entries",
                "section_id": "",
                "section_title": "",
                "affected_section": "toc_entries",
            }
        )
    for section_id in expected_ids:
        if section_id not in actual_ids:
            expected_entry = expected_by_id.get(section_id) or {}
            diagnostics.append(
                {
                    "status": "missing_section",
                    "section_id": section_id,
                    "section_title": _s(expected_entry.get("section_title")).strip(),
                    "affected_section": f"toc_entries:{section_id}",
                }
            )
    for section_id in duplicate_ids:
        expected_entry = expected_by_id.get(section_id) or {}
        diagnostics.append(
            {
                "status": "duplicate_section",
                "section_id": section_id,
                "section_title": _s(expected_entry.get("section_title")).strip(),
                "affected_section": f"toc_entries:{section_id}",
            }
        )
    for entry in actual_entries:
        section_id = _s(entry.get("section_id")).strip()
        if section_id not in expected_by_id:
            diagnostics.append(
                {
                    "status": "unknown_section",
                    "section_id": section_id,
                    "section_title": _s(entry.get("section_title")).strip(),
                    "affected_section": f"toc_entries:{section_id or 'unknown'}",
                }
            )
            continue
        expected_entry = expected_by_id[section_id]
        if (
            _s(entry.get("section_title")).strip()
            != _s(expected_entry.get("section_title")).strip()
        ):
            diagnostics.append(
                {
                    "status": "section_title_mismatch",
                    "section_id": section_id,
                    "section_title": _s(expected_entry.get("section_title")).strip(),
                    "affected_section": f"toc_entries:{section_id}",
                }
            )
        if not _s(entry.get("display_title")).strip():
            diagnostics.append(
                {
                    "status": "empty_display_title",
                    "section_id": section_id,
                    "section_title": _s(expected_entry.get("section_title")).strip(),
                    "affected_section": f"toc_entries:{section_id}",
                }
            )
        for field_name in ("summary", "key_points", "pages"):
            if entry.get(field_name) != expected_entry.get(field_name):
                diagnostics.append(
                    {
                        "status": f"stale_{field_name}",
                        "section_id": section_id,
                        "section_title": _s(
                            expected_entry.get("section_title")
                        ).strip(),
                        "affected_section": f"toc_entries:{section_id}",
                    }
                )
    ordered_ids = [
        section_id for section_id in actual_ids if section_id in expected_by_id
    ]
    if ordered_ids and ordered_ids != expected_ids[: len(ordered_ids)]:
        diagnostics.append(
            {
                "status": "out_of_order",
                "section_id": "",
                "section_title": "",
                "affected_section": "toc_entries",
            }
        )

    expected_topics = expected_bundle.get("toc_topics") or []
    raw_toc_topics = artifacts.get("toc_topics")
    actual_topics: list[Any] = (
        raw_toc_topics if isinstance(raw_toc_topics, list) else []
    )
    if actual_topics != expected_topics:
        diagnostics.append(
            {
                "status": "legacy_topics_stale",
                "section_id": "",
                "section_title": "",
                "affected_section": "toc_topics",
            }
        )

    expected_briefs = expected_bundle.get("toc_topics_expanded") or []
    raw_toc_briefs = artifacts.get("toc_topics_expanded")
    actual_briefs: list[Any] = (
        raw_toc_briefs if isinstance(raw_toc_briefs, list) else []
    )
    if len(actual_briefs) != len(expected_briefs):
        diagnostics.append(
            {
                "status": "legacy_briefs_count_mismatch",
                "section_id": "",
                "section_title": "",
                "affected_section": "toc_topics_expanded",
            }
        )
    else:
        for expected_brief, actual_brief in zip(expected_briefs, actual_briefs):
            if not isinstance(actual_brief, dict):
                diagnostics.append(
                    {
                        "status": "legacy_brief_invalid",
                        "section_id": _s(expected_brief.get("section_id")).strip(),
                        "section_title": _s(
                            expected_brief.get("section_title")
                        ).strip(),
                        "affected_section": (
                            f"toc_topics_expanded:{_s(expected_brief.get('section_id')).strip()}"
                        ),
                    }
                )
                continue
            for field_name in (
                "topic",
                "summary",
                "key_points",
                "section_id",
                "section_title",
                "pages",
            ):
                if actual_brief.get(field_name) != expected_brief.get(field_name):
                    diagnostics.append(
                        {
                            "status": f"legacy_brief_{field_name}_mismatch",
                            "section_id": _s(expected_brief.get("section_id")).strip(),
                            "section_title": _s(
                                expected_brief.get("section_title")
                            ).strip(),
                            "affected_section": (
                                f"toc_topics_expanded:{_s(expected_brief.get('section_id')).strip()}"
                            ),
                        }
                    )
                    break
    return diagnostics


def build_topic_briefs(
    *,
    toc_topics: List[str],
    doc_map: Dict[str, Any],
    summary: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not toc_topics:
        return []
    sections = _doc_map_sections_for_topics(doc_map)
    expanded: List[Dict[str, Any]] = []
    for raw_topic in toc_topics:
        topic = _s(raw_topic).strip()
        if not topic:
            continue
        section = _select_topic_section(topic=topic, sections=sections)
        section_summary = _s(section.get("summary")).strip() if section else ""
        raw_section_points = section.get("key_points") if section else []
        section_points: list[Any] = (
            raw_section_points if isinstance(raw_section_points, list) else []
        )
        key_points = _dedupe_non_empty_text(
            [_s(point) for point in section_points], limit=TOPIC_BRIEF_MAX_KEY_POINTS
        )
        summary_text = section_summary

        claim_summary, claim_points = _topic_brief_from_claims(topic, summary)
        if not summary_text:
            summary_text = claim_summary
        key_points = _dedupe_non_empty_text(
            key_points + claim_points, limit=TOPIC_BRIEF_MAX_KEY_POINTS
        )

        insight_points = _topic_points_from_insights(topic, insights_final)
        if not summary_text and insight_points:
            summary_text = insight_points[0]
        key_points = _dedupe_non_empty_text(
            key_points + insight_points, limit=TOPIC_BRIEF_MAX_KEY_POINTS
        )

        if not summary_text and key_points:
            summary_text = key_points[0]

        expanded.append(
            {
                "topic": topic,
                "summary": summary_text,
                "key_points": key_points,
                "section_id": _s(section.get("section_id")).strip() if section else "",
                "section_title": _s(section.get("title")).strip() if section else "",
                "pages": section.get("pages") if section else [],
            }
        )
    return expanded
