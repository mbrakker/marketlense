from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from src.contracts.config import AppSettings
from src.contracts.ingest import IngestSettings
from src.utils.coercion import stripped_string_value as _s
from src.utils.errors import AppError
from src.utils.json_utils import dump_json_object as _dump_json
from src.utils.numeric_display import preserve_unique_source_displays
from src.utils.public_metric_display import normalize_public_metric_display
from src.utils.text_normalization import normalize_text

METRIC_FIELDS = (
    "label",
    "value",
    "unit",
    "trend",
    "timeframe",
    "geography",
    "segment",
    "sample_size",
    "confidence",
)
INSIGHT_TEXT_FIELDS = (
    "coverage_role",
    "so_what",
    "now_what",
    "report_type_lens",
)
INSIGHT_SCORE_FIELDS = (
    "score",
    "decision_relevance_score",
    "metric_strength_score",
    "novelty_score",
)
MIN_FINAL_ARTIFACT_INSIGHTS = 2
REQUIRED_REPORT_PAYLOAD_INSIGHTS = 5
COVERAGE_ROLE_VALUES = {
    "market_context",
    "behavior_shift",
    "strategic_risk",
    "operating_implication",
    "investment_signal",
    "proof_point",
    "counter_signal",
}
REPORT_TYPE_LENS_VALUES = {
    "market_size",
    "consumer_behavior",
    "technology_shift",
    "channel_strategy",
    "brand_strategy",
    "investment_outlook",
    "risk_regulation",
    "operations",
    "creative_culture",
}
REPORT_TYPE_LENS_TO_COVERAGE_ROLE = {
    "market_size": "market_context",
    "consumer_behavior": "behavior_shift",
    "technology_shift": "market_context",
    "channel_strategy": "operating_implication",
    "brand_strategy": "market_context",
    "investment_outlook": "investment_signal",
    "risk_regulation": "strategic_risk",
    "operations": "operating_implication",
    "creative_culture": "market_context",
}
COVERAGE_ROLE_TO_REPORT_TYPE_LENS = {
    "market_context": "market_size",
    "behavior_shift": "consumer_behavior",
    "strategic_risk": "risk_regulation",
    "operating_implication": "operations",
    "investment_signal": "investment_outlook",
    "proof_point": "market_size",
    "counter_signal": "risk_regulation",
}
INLINE_REFERENCE_TOKEN_RE = r"[A-Z]{1,4}-\d{1,4}"
INLINE_REFERENCE_GROUP_RE = re.compile(
    rf"[\(\[]\s*{INLINE_REFERENCE_TOKEN_RE}(?:\s*[/,;|]\s*{INLINE_REFERENCE_TOKEN_RE})*\s*[\)\]]"
)
EVIDENCE_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
QUOTE_ALIAS_RE = re.compile(r"^quote[-_]?(\d+)$", re.IGNORECASE)
PUBLIC_EDITORIAL_SCAFFOLD_RE = re.compile(
    r"\b(?:answer|scale|implication|delivery and workflow|evidence note|caveat)\s*:\s*",
    re.IGNORECASE,
)
_LABELLED_METRIC_VALUE_RE = re.compile(
    r"\b(?P<label>[A-Za-z][A-Za-z0-9&/ -]{0,72}?)\s+"
    r"(?:grew|increased|rose|reached)\s+(?P<value>[+-]?\d+(?:[,.]\d+)?\s*%)",
    re.IGNORECASE,
)
_PARALLEL_LABELLED_METRICS_RE = re.compile(
    r"\b(?P<labels>[A-Za-z][A-Za-z0-9&/ ,;-]{0,96}?)\s+"
    r"(?:grew|increased|rose|reached)\s+"
    r"(?P<values>[+-]?\d+(?:[,.]\d+)?\s*%"
    r"(?:\s*(?:,|and)\s*[+-]?\d+(?:[,.]\d+)?\s*%)+)",
    re.IGNORECASE,
)
_PARALLEL_PERCENT_VALUE_RE = re.compile(r"[+-]?\d+(?:[,.]\d+)?\s*%")
_SOURCE_RANGE_DISPLAY_RE = re.compile(
    r"(?P<display>"
    r"(?P<start>[+-]?(?:[$€£¥]\s*)?\d+(?:[,.]\d+)?(?:\s*%)?)"
    r"(?P<between>(?:\s+[A-Za-z][A-Za-z/-]*){1,8}\s+)"
    r"to\s+(?P<end>[+-]?(?:[$€£¥]\s*)?\d+(?:[,.]\d+)?(?:\s*%)?)"
    r"(?P<tail>(?:\s+(?:by|in|during)\s+(?:[A-Za-z]+\s+)?\d{4}(?:E)?)?)"
    r")",
    re.IGNORECASE,
)


def artifact_base_variables(
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> Dict[str, str]:
    return {
        "doc_map_json": _dump_json(doc_map or {}),
        "evidence_json": _dump_json(evidence_packs or {}),
    }


def normalize_artifact_editorial_plan(value: Any) -> Dict[str, Any]:
    """Validate the report-level thematic decision used by public artifacts."""
    data = value if isinstance(value, dict) else {}
    report_thesis = _s(data.get("report_thesis")).strip()
    raw_themes = data.get("themes")
    if not report_thesis or not isinstance(raw_themes, list) or len(raw_themes) < 2:
        raise AppError(
            code="editorial_plan_invalid",
            message="Editorial plan requires a report thesis and at least two themes",
            retryable=False,
        )
    if len(raw_themes) > 7:
        raise AppError(
            code="editorial_plan_invalid",
            message="Editorial plan must contain no more than seven themes",
            retryable=False,
        )
    themes: List[Dict[str, Any]] = []
    seen_themes: set[str] = set()
    seen_priorities: set[int] = set()
    for raw_theme in raw_themes:
        if not isinstance(raw_theme, dict):
            raise AppError(
                code="editorial_plan_invalid",
                message="Editorial plan themes must be objects",
                retryable=False,
            )
        theme = _s(raw_theme.get("theme")).strip()
        priority = raw_theme.get("priority")
        raw_evidence_ids = raw_theme.get("evidence_ids")
        if (
            not theme
            or not isinstance(priority, int)
            or priority <= 0
            or not isinstance(raw_evidence_ids, list)
        ):
            raise AppError(
                code="editorial_plan_invalid",
                message=(
                    "Editorial plan themes require text, positive priority, "
                    "and evidence IDs"
                ),
                retryable=False,
            )
        theme_key = normalize_text(theme)
        evidence_ids = list(
            dict.fromkeys(
                _s(evidence_id).strip()
                for evidence_id in raw_evidence_ids
                if _s(evidence_id).strip()
            )
        )
        if not evidence_ids or theme_key in seen_themes or priority in seen_priorities:
            raise AppError(
                code="editorial_plan_invalid",
                message=(
                    "Editorial plan themes must have unique priorities and evidence IDs"
                ),
                retryable=False,
            )
        seen_themes.add(theme_key)
        seen_priorities.add(priority)
        themes.append(
            {"theme": theme, "priority": priority, "evidence_ids": evidence_ids}
        )
    return {
        "report_thesis": report_thesis,
        "themes": sorted(themes, key=lambda item: item["priority"]),
    }


def stabilize_broad_artifact_editorial_plan(
    editorial_plan: Dict[str, Any],
    *,
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> Dict[str, Any]:
    """Keep a broad plan from concentrating its themes in one source area.

    This is deliberately a narrow deterministic guard on the existing single
    editorial plan. It activates only when linked findings provide distinct
    early, middle, and late section evidence that the plan has omitted.
    """
    plan = normalize_artifact_editorial_plan(editorial_plan)
    sections = _material_doc_map_sections(doc_map)
    findings_by_section = _section_linked_findings(evidence_packs, sections)
    if not _has_broad_section_coverage(sections, findings_by_section):
        return plan

    theme_sections = [
        _theme_section_id(theme, findings_by_section) for theme in plan["themes"]
    ]
    if not _plan_is_materially_clustered(theme_sections, sections):
        return plan

    kept, redundant = _split_distinct_plan_themes(plan["themes"], theme_sections)
    represented_sections = {section_id for _, section_id in kept if section_id}
    coverage_themes = _unrepresented_band_themes(
        sections=sections,
        findings_by_section=findings_by_section,
        represented_sections=represented_sections,
        existing_theme_names={normalize_text(theme["theme"]) for theme, _ in kept},
    )
    if not coverage_themes:
        return plan

    desired_count = len(plan["themes"])
    combined = [
        *[theme for theme, _ in kept],
        *coverage_themes,
        *[theme for theme, _ in redundant],
    ][:desired_count]
    if len(combined) != desired_count:
        return plan
    return {
        "report_thesis": plan["report_thesis"],
        "themes": [
            {**theme, "priority": index}
            for index, theme in enumerate(combined, start=1)
        ],
    }


def _material_doc_map_sections(doc_map: Dict[str, Any]) -> List[Dict[str, str]]:
    raw_sections = doc_map.get("sections") if isinstance(doc_map, dict) else []
    if not isinstance(raw_sections, list):
        return []
    sections: List[Dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, raw_section in enumerate(raw_sections):
        if not isinstance(raw_section, dict):
            continue
        section_id = _s(raw_section.get("id")).strip()
        title = _s(raw_section.get("title")).strip()
        summary = _s(raw_section.get("summary")).strip()
        key_points = raw_section.get("key_points")
        has_key_points = isinstance(key_points, list) and any(
            _s(point).strip() for point in key_points
        )
        normalized_id = normalize_text(section_id or title)
        if not title or not normalized_id or normalized_id in seen_ids:
            continue
        if not (summary or has_key_points):
            continue
        seen_ids.add(normalized_id)
        sections.append(
            {
                "id": normalized_id,
                "title": title,
                "order": str(index),
            }
        )
    return sections


def _section_linked_findings(
    evidence_packs: Dict[str, Any], sections: List[Dict[str, str]]
) -> Dict[str, List[str]]:
    valid_sections = {section["id"] for section in sections}
    findings_pack = (
        evidence_packs.get("findings") if isinstance(evidence_packs, dict) else {}
    )
    findings = findings_pack.get("findings") if isinstance(findings_pack, dict) else []
    if not isinstance(findings, list):
        return {}
    linked: Dict[str, List[str]] = {}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding_id = _s(finding.get("id")).strip()
        section_id = normalize_text(_s(finding.get("section_id")))
        finding_text = _s(finding.get("text")).strip()
        if not finding_id or not finding_text or section_id not in valid_sections:
            continue
        linked.setdefault(section_id, []).append(finding_id)
    return linked


def _has_broad_section_coverage(
    sections: List[Dict[str, str]], findings_by_section: Dict[str, List[str]]
) -> bool:
    if len(sections) < 6 or len(findings_by_section) < 4:
        return False
    bands = {
        _section_band(int(section["order"]), len(sections))
        for section in sections
        if section["id"] in findings_by_section
    }
    return bands == {0, 1, 2}


def _theme_section_id(
    theme: Dict[str, Any], findings_by_section: Dict[str, List[str]]
) -> str:
    evidence_ids = {
        normalize_text(evidence_id) for evidence_id in theme["evidence_ids"]
    }
    for section_id, finding_ids in findings_by_section.items():
        if evidence_ids.intersection(
            normalize_text(finding_id) for finding_id in finding_ids
        ):
            return section_id
    return ""


def _plan_is_materially_clustered(
    theme_sections: List[str], sections: List[Dict[str, str]]
) -> bool:
    mapped_sections = [section_id for section_id in theme_sections if section_id]
    if len(mapped_sections) < 4 or len(set(mapped_sections)) >= 3:
        return False
    section_orders = {section["id"]: int(section["order"]) for section in sections}
    mapped_bands = {
        _section_band(section_orders[section_id], len(sections))
        for section_id in mapped_sections
    }
    return len(mapped_bands) == 1


def _split_distinct_plan_themes(
    themes: List[Dict[str, Any]], theme_sections: List[str]
) -> tuple[List[tuple[Dict[str, Any], str]], List[tuple[Dict[str, Any], str]]]:
    kept: List[tuple[Dict[str, Any], str]] = []
    redundant: List[tuple[Dict[str, Any], str]] = []
    seen_sections: set[str] = set()
    for theme, section_id in zip(themes, theme_sections, strict=True):
        if section_id and section_id not in seen_sections:
            seen_sections.add(section_id)
            kept.append((theme, section_id))
        else:
            redundant.append((theme, section_id))
    return kept, redundant


def _unrepresented_band_themes(
    *,
    sections: List[Dict[str, str]],
    findings_by_section: Dict[str, List[str]],
    represented_sections: set[str],
    existing_theme_names: set[str],
) -> List[Dict[str, Any]]:
    represented_bands = {
        _section_band(int(section["order"]), len(sections))
        for section in sections
        if section["id"] in represented_sections
    }
    selected: List[Dict[str, Any]] = []
    for section in sections:
        section_id = section["id"]
        title_key = normalize_text(section["title"])
        band = _section_band(int(section["order"]), len(sections))
        if (
            section_id in represented_sections
            or section_id not in findings_by_section
            or band in represented_bands
            or not title_key
            or title_key in existing_theme_names
        ):
            continue
        selected.append(
            {
                "theme": section["title"],
                "priority": 0,
                "evidence_ids": [findings_by_section[section_id][0]],
            }
        )
        represented_bands.add(band)
        existing_theme_names.add(title_key)
    return selected


def _section_band(section_order: int, section_count: int) -> int:
    return min(2, (3 * section_order) // section_count)


def normalize_artifact_source_status(
    source_status: Optional[Dict[str, Any]],
    settings: AppSettings | IngestSettings,
    *,
    has_density: bool,
    vector_store_id: Optional[str] = None,
) -> Dict[str, Any]:
    status = source_status.copy() if isinstance(source_status, dict) else {}
    status.setdefault("schema_version", "1.0")
    status.setdefault("text_density", 0.0)
    status.setdefault(
        "density_threshold",
        float(getattr(settings, "pdf_text_min_density", 0.0)) if has_density else 0.0,
    )
    status.setdefault("pages_sampled", 0)
    status.setdefault("char_count", 0)
    status.setdefault("not_available", False)
    status.setdefault("reason", "")
    status.setdefault("evidence_present", True)
    if vector_store_id:
        status["density_threshold"] = 0.0
        status["not_available"] = False
        status["reason"] = ""
    return status


def artifact_vector_store_enabled(
    *, settings: AppSettings | IngestSettings, vector_store_id: Optional[str]
) -> bool:
    return bool(vector_store_id) and bool(
        getattr(settings, "artifacts_use_vector_store", False)
    )


def artifact_retrieval_mode(use_vector_store: bool) -> str:
    return "vector_store" if use_vector_store else "chat_json"


def normalize_artifact_summary(value: Any) -> Dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    claim_map = data.get("claim_evidence_map")
    return {
        "tldr": _s(data.get("tldr")),
        "card_tldr_compact": _s(data.get("card_tldr_compact")),
        "executive_summary": _strip_public_editorial_scaffold(
            strip_artifact_inline_reference_ids(_s(data.get("executive_summary")))
        ),
        "claim_evidence_map": _normalize_claims(claim_map),
    }


def preserve_public_source_displays(
    *,
    summary: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
    expert_comment: str,
    linkedin_post: str,
) -> tuple[str, str]:
    """Preserve unique, source-backed factual displays in public artifacts."""

    safe_summary = summary if isinstance(summary, dict) else {}
    summary_evidence = " ".join(
        _s(item.get("evidence"))
        for item in safe_summary.get("claim_evidence_map", [])
        if isinstance(item, dict) and _s(item.get("evidence")).strip()
    )
    for field_name in ("tldr", "card_tldr_compact", "executive_summary"):
        safe_summary[field_name] = _preserve_source_displays(
            _s(safe_summary.get(field_name)), summary_evidence
        )

    downstream_evidence: list[str] = []
    for insight in insights_final:
        if not isinstance(insight, dict):
            continue
        evidence = _s(insight.get("evidence"))
        for field_name in ("text", "so_what", "now_what"):
            if field_name in insight:
                insight[field_name] = _preserve_source_displays(
                    _s(insight.get(field_name)), evidence
                )
        metric = insight.get("metric")
        if isinstance(metric, dict):
            for field_name in ("value", "timeframe"):
                if field_name in metric:
                    metric[field_name] = _preserve_source_displays(
                        _s(metric.get(field_name)), evidence
                    )
        if _has_unsupported_material_number(_s(insight.get("text")), evidence, metric):
            # The evidence was bound from a canonical retained record. Replace
            # only a generated numeric claim that exceeds that record with its
            # exact source-backed statement before artifact retention.
            insight["text"] = evidence
        downstream_evidence.extend(
            value for value in (evidence, _s(insight.get("text"))) if value.strip()
        )
    combined_downstream_evidence = " ".join([summary_evidence, *downstream_evidence])
    return (
        _preserve_downstream_source_displays(
            expert_comment, combined_downstream_evidence
        ),
        _preserve_downstream_source_displays(
            linkedin_post, combined_downstream_evidence
        ),
    )


def _preserve_source_displays(text: str, evidence: str) -> str:
    return preserve_unique_source_displays(text, evidence)


def _has_unsupported_material_number(text: str, evidence: str, metric: object) -> bool:
    number_pattern = r"\d{1,3}(?:[,.]\d{3})+|\d+(?:[.,]\d+)?"
    evidence_numbers = {
        _normalise_numeric_display(match.group())
        for match in re.finditer(number_pattern, f"{evidence} {metric or ''}")
    }
    material_numbers = {
        _normalise_numeric_display(match.group())
        for match in re.finditer(number_pattern, text)
        if not re.fullmatch(
            r"(?:19|20)\d{2}", _normalise_numeric_display(match.group())
        )
    }
    return bool(material_numbers - evidence_numbers)


def _preserve_downstream_source_displays(text: str, evidence: str) -> str:
    return _preserve_source_range_displays(
        _preserve_parallel_labelled_metric_displays(
            _preserve_source_displays(text, evidence), evidence
        ),
        evidence,
    )


def _preserve_source_range_displays(text: str, evidence: str) -> str:
    """Restore a unique source range when prose drops its in-range display.

    This applies only where the public copy retains the exact start/end
    displays, while the retained evidence has one unambiguous intervening
    source display (such as a unit or source-relative timeframe). It never
    infers missing text or selects among competing source displays.
    """

    source_displays_by_pair: dict[tuple[str, str], set[str]] = {}
    for match in _SOURCE_RANGE_DISPLAY_RE.finditer(evidence):
        display = match.group("display")
        between = match.group("between")
        if not display or not between.strip():
            continue
        pair = (
            _normalise_numeric_display(match.group("start")),
            _normalise_numeric_display(match.group("end")),
        )
        if all(pair):
            source_displays_by_pair.setdefault(pair, set()).add(display)

    repaired = text
    for pair, displays in source_displays_by_pair.items():
        if len(displays) != 1:
            continue
        start, end = pair
        public_range = re.compile(
            rf"(?<![\d.]){re.escape(start)}\s+to\s+{re.escape(end)}(?![\d.])",
            re.IGNORECASE,
        )
        source_display = next(iter(displays))
        if len(public_range.findall(repaired)) == 1:
            repaired = public_range.sub(source_display, repaired, count=1)
    return repaired


def _normalise_numeric_display(value: str) -> str:
    return "".join(value.casefold().split())


def _preserve_parallel_labelled_metric_displays(text: str, evidence: str) -> str:
    """Restore ordered values only for uniquely matched source categories."""

    source_values_by_label: dict[str, set[str]] = {}
    for match in _LABELLED_METRIC_VALUE_RE.finditer(evidence):
        label = _normalise_metric_label(match.group("label"))
        value = match.group("value")
        if label and value:
            source_values_by_label.setdefault(label, set()).add(value)

    replacements: list[tuple[int, int, str]] = []
    for match in _PARALLEL_LABELLED_METRICS_RE.finditer(text):
        labels = _parallel_metric_labels(match.group("labels"))
        values = list(_PARALLEL_PERCENT_VALUE_RE.finditer(match.group("values")))
        if len(labels) < 2 or len(labels) != len(values):
            continue
        source_displays: list[str] = []
        for label in labels:
            source_display = _unique_source_value_for_label(
                label, source_values_by_label
            )
            if source_display is None:
                break
            source_displays.append(source_display)
        if len(source_displays) != len(labels):
            continue
        value_offset = match.start("values")
        for value_match, source_display in zip(values, source_displays, strict=True):
            if value_match.group() != source_display:
                replacements.append(
                    (
                        value_offset + value_match.start(),
                        value_offset + value_match.end(),
                        source_display,
                    )
                )

    repaired = text
    for start, end, source_display in reversed(replacements):
        repaired = repaired[:start] + source_display + repaired[end:]
    return repaired


def _parallel_metric_labels(value: str) -> list[str]:
    last_clause = re.split(r"[,;:]\s*", value)[-1]
    labels = [
        _normalise_metric_label(label)
        for label in re.split(r"\s+(?:and|&)\s+", last_clause, flags=re.IGNORECASE)
    ]
    return [label for label in labels if label]


def _normalise_metric_label(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").split())


def _unique_source_value_for_label(
    label: str, source_values_by_label: dict[str, set[str]]
) -> str | None:
    values = {
        value
        for source_label, displays in source_values_by_label.items()
        if source_label == label or source_label.endswith(f" {label}")
        for value in displays
    }
    return next(iter(values)) if len(values) == 1 else None


def _strip_public_editorial_scaffold(value: str) -> str:
    return PUBLIC_EDITORIAL_SCAFFOLD_RE.sub("", value).strip()


def normalize_artifact_insights(items: Any, *, prefix: str) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        metric_raw = _to_dict(item.get("metric"))
        metric = {key: _s(metric_raw.get(key, "")) for key in METRIC_FIELDS}
        metric["value"], metric["unit"] = normalize_public_metric_display(
            value=metric["value"], unit=metric["unit"]
        )
        pages_raw_obj = item.get("pages")
        pages_raw = pages_raw_obj if isinstance(pages_raw_obj, list) else []
        pages = [int(p) for p in pages_raw if isinstance(p, int)]
        evidence_id = _s(item.get("evidence_id"))
        insight: Dict[str, Any] = {
            "id": _s(item.get("id") or f"{prefix}_{idx + 1}"),
            "text": _s(item.get("text")),
            "evidence_id": evidence_id,
            "evidence": _s(item.get("evidence")),
            "evidence_spans": _normalize_evidence_spans(
                item.get("evidence_spans"), evidence_id=evidence_id
            ),
            "metric": metric,
            "pages": pages,
        }
        for field_name in INSIGHT_TEXT_FIELDS:
            value = _normalize_insight_text_field(field_name, item.get(field_name))
            if value:
                insight[field_name] = value
        for field_name in INSIGHT_SCORE_FIELDS:
            score_value = item.get(field_name)
            if isinstance(score_value, (int, float)):
                insight[field_name] = float(score_value)
        normalized.append(insight)
    return normalized


def select_artifact_insights(
    *,
    final_insights: List[Dict[str, Any]],
    candidate_insights: List[Dict[str, Any]],
    editorial_plan: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Keep theme coverage, then fill the report's required grounded insight slots."""
    plan = normalize_artifact_editorial_plan(editorial_plan)
    ranked = _ranked_unique_insights(final_insights, candidate_insights)
    required_count = max(REQUIRED_REPORT_PAYLOAD_INSIGHTS, len(plan["themes"]))
    selected: List[Dict[str, Any]] = []
    selected_keys: set[tuple[str, str]] = set()
    for theme in plan["themes"]:
        evidence_ids = {
            normalize_text(evidence_id) for evidence_id in theme["evidence_ids"]
        }
        matching = [
            item
            for item in ranked
            if normalize_text(_s(item[1].get("evidence_id"))) in evidence_ids
        ]
        if matching:
            _append_distinct_insight(
                selected, selected_keys, _best_ranked_insight(matching)[1]
            )
    for _, insight in ranked:
        if len(selected) >= required_count:
            break
        _append_distinct_insight(selected, selected_keys, insight)
    return selected


def build_expert_synthesis_context(
    *,
    editorial_plan: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the bounded, evidence-first input for Expert View synthesis."""
    plan = normalize_artifact_editorial_plan(editorial_plan)
    span_index = _build_evidence_span_index(
        doc_map=doc_map, evidence_packs=evidence_packs
    )
    themes: List[Dict[str, Any]] = []
    for theme in plan["themes"]:
        evidence = []
        for evidence_id in theme["evidence_ids"][:3]:
            spans = span_index.get(_s(evidence_id).casefold(), [])
            if not spans:
                continue
            span = spans[0]
            evidence.append(
                {
                    "evidence_id": _s(span.get("evidence_id")),
                    "source_pack": _s(span.get("source_pack")),
                    "text": _s(span.get("text")),
                }
            )
        themes.append(
            {
                "theme": theme["theme"],
                "priority": theme["priority"],
                "evidence": evidence,
            }
        )
    return {
        "schema_version": "1.0",
        "themes": themes,
        "insight_implications": _expert_insight_implications(insights_final),
        "limitations": _expert_context_items(
            evidence_packs.get("limitations"),
            item_key="limitations",
            text_keys=("description", "limitation", "text", "summary"),
        ),
        "counter_signals": _expert_counter_signals(insights_final, evidence_packs),
    }


def _expert_insight_implications(
    insights_final: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    implications: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for insight in insights_final:
        if not isinstance(insight, dict):
            continue
        implication = _s(insight.get("so_what")).strip()
        if not implication:
            continue
        evidence_id = _s(insight.get("evidence_id")).strip()
        key = (evidence_id.casefold(), normalize_text(implication))
        if key in seen:
            continue
        seen.add(key)
        implications.append({"evidence_id": evidence_id, "so_what": implication})
        if len(implications) == 7:
            break
    return implications


def _expert_counter_signals(
    insights_final: List[Dict[str, Any]], evidence_packs: Dict[str, Any]
) -> List[Dict[str, str]]:
    counter_signals: List[Dict[str, str]] = []
    for insight in insights_final:
        if not isinstance(insight, dict):
            continue
        if _s(insight.get("coverage_role")).strip() not in {
            "counter_signal",
            "strategic_risk",
        }:
            continue
        _append_expert_context_item(
            counter_signals,
            evidence_id=_s(insight.get("evidence_id")),
            text=_s(insight.get("text")),
        )
    return counter_signals[:7]


def _expert_context_items(
    pack: Any,
    *,
    item_key: str,
    text_keys: tuple[str, ...],
    existing: List[Dict[str, str]] | None = None,
) -> List[Dict[str, str]]:
    items = pack.get(item_key) if isinstance(pack, dict) else []
    if not isinstance(items, list):
        return []
    context_items: List[Dict[str, str]] = []
    seen = {
        (
            _s(item.get("evidence_id")).casefold(),
            normalize_text(_s(item.get("text"))),
        )
        for item in (existing or [])
        if isinstance(item, dict)
    }
    for item in items:
        if isinstance(item, str):
            text = item.strip()
            evidence_id = ""
        elif isinstance(item, dict):
            text = _pick_first_non_empty_text(*(item.get(key) for key in text_keys))
            evidence_id = _s(item.get("evidence_id") or item.get("id")).strip()
        else:
            continue
        if not text:
            continue
        key = (evidence_id.casefold(), normalize_text(text))
        if key in seen:
            continue
        seen.add(key)
        context_items.append({"evidence_id": evidence_id, "text": text})
        if len(context_items) == 7:
            break
    return context_items


def _append_expert_context_item(
    items: List[Dict[str, str]], *, evidence_id: str, text: str
) -> None:
    if not text.strip():
        return
    key = (evidence_id.casefold(), normalize_text(text))
    if any(
        key
        == (
            _s(item.get("evidence_id")).casefold(),
            normalize_text(_s(item.get("text"))),
        )
        for item in items
    ):
        return
    items.append({"evidence_id": evidence_id.strip(), "text": text.strip()})


def _ranked_unique_insights(
    final_insights: List[Dict[str, Any]], candidate_insights: List[Dict[str, Any]]
) -> List[tuple[int, Dict[str, Any]]]:
    ranked: List[tuple[int, Dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    for source_order, insight in enumerate([*final_insights, *candidate_insights]):
        if not isinstance(insight, dict) or not _s(insight.get("text")).strip():
            continue
        duplicate_key = _insight_duplicate_key(insight)
        if duplicate_key and duplicate_key in seen:
            continue
        if duplicate_key:
            seen.add(duplicate_key)
        ranked.append((source_order, dict(insight)))
    return ranked


def _best_ranked_insight(
    items: List[tuple[int, Dict[str, Any]]],
) -> tuple[int, Dict[str, Any]]:
    return min(items, key=_insight_rank_key)


def _insight_rank_key(item: tuple[int, Dict[str, Any]]) -> tuple[float, int]:
    source_order, insight = item
    score = insight.get("score")
    numeric_score = float(score) if isinstance(score, (int, float)) else 0.0
    return (-numeric_score, source_order)


def _append_distinct_insight(
    selected: List[Dict[str, Any]],
    selected_keys: set[tuple[str, str]],
    insight: Dict[str, Any],
) -> None:
    duplicate_key = _insight_duplicate_key(insight)
    if duplicate_key and duplicate_key in selected_keys:
        return
    if duplicate_key:
        selected_keys.add(duplicate_key)
    selected.append(insight)


def fallback_artifact_insights_from_findings(
    findings_pack: Any,
    *,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Build a bounded insight candidate set from addressable findings.

    It preserves the evidence-pack claim verbatim enough to retain deterministic
    grounding rather than inventing editorial copy. The final selector can use
    this set to complete missing DocMap-theme coverage when model candidates are
    clustered on one theme.
    """
    if not isinstance(findings_pack, dict) or limit <= 0:
        return []
    raw_findings = findings_pack.get("findings")
    if not isinstance(raw_findings, list):
        return []
    raw_candidates: List[Dict[str, Any]] = []
    seen_evidence_ids: set[str] = set()
    for finding in raw_findings:
        if not isinstance(finding, dict):
            continue
        evidence_id = _s(finding.get("id"))
        text = _s(finding.get("text"))
        evidence = _s(finding.get("evidence"))
        if not evidence_id or not text or not evidence:
            continue
        normalized_evidence_id = normalize_text(evidence_id)
        if normalized_evidence_id in seen_evidence_ids:
            continue
        seen_evidence_ids.add(normalized_evidence_id)
        raw_candidates.append(
            {
                "id": evidence_id,
                "text": text,
                "evidence_id": evidence_id,
                "evidence": evidence,
                "pages": finding.get("pages"),
            }
        )
        if len(raw_candidates) == limit:
            break
    return normalize_artifact_insights(raw_candidates, prefix="finding")


def _insight_duplicate_key(item: Dict[str, Any]) -> tuple[str, str] | None:
    text = normalize_text(_s(item.get("text")))
    if not text:
        return None
    return (text, normalize_text(_s(item.get("evidence_id"))))


def normalize_artifact_quotes(items: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            continue
        page_val = item.get("page")
        page = page_val if isinstance(page_val, int) else 0
        evidence_id = _s(item.get("evidence_id"))
        quote = {
            "text": _s(item.get("text")),
            "speaker": _s(item.get("speaker") or "Unknown"),
            "citation": _s(item.get("citation")),
            "page": page,
            "evidence_id": evidence_id,
            "evidence_spans": _normalize_evidence_spans(
                item.get("evidence_spans"), evidence_id=evidence_id
            ),
        }
        if item.get("is_paraphrase") is True or item.get("paraphrase") is True:
            quote["is_paraphrase"] = True
        for key in ("style", "mode", "label"):
            value = _s(item.get(key)).strip()
            if value:
                quote[key] = value
        normalized.append(quote)
    return normalized


def strip_artifact_inline_reference_ids(text: str) -> str:
    cleaned = INLINE_REFERENCE_GROUP_RE.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"([(\[])\s+", r"\1", cleaned)
    cleaned = re.sub(r"\s+([)\]])", r"\1", cleaned)
    return cleaned.strip(" ,;:-")


def strip_linkedin_inline_reference_ids(text: str) -> str:
    """Remove internal LinkedIn reference tokens without flattening paragraphs."""
    cleaned = INLINE_REFERENCE_GROUP_RE.sub("", text.replace("\r\n", "\n"))
    lines = []
    for line in cleaned.split("\n"):
        line = re.sub(r"[ \t]{2,}", " ", line)
        line = re.sub(r"[ \t]+([,.;:!?])", r"\1", line)
        line = re.sub(r"([(\[])\s+", r"\1", line)
        line = re.sub(r"\s+([)\]])", r"\1", line)
        lines.append(line.strip(" ,;:-"))
    return "\n".join(lines).strip("\n")


def normalize_artifact_topics(value: Any) -> List[str]:
    topics = value if isinstance(value, list) else []
    normalized: List[str] = []
    seen = set()
    for item in topics:
        text = _s(item).strip()
        if not text:
            continue
        text_key = text.casefold()
        if text_key in seen:
            continue
        seen.add(text_key)
        normalized.append(text)
    return normalized[:5]


def normalize_artifact_toc_entries(value: Any) -> List[Dict[str, Any]]:
    entries = value if isinstance(value, list) else []
    normalized: List[Dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for idx, item in enumerate(entries):
        if not isinstance(item, dict):
            continue
        section_id = _s(item.get("section_id")).strip()
        section_title = _s(item.get("section_title")).strip()
        display_title = _s(item.get("display_title")).strip()
        summary = _s(item.get("summary"))
        key_points_raw = item.get("key_points")
        key_points = []
        if isinstance(key_points_raw, list):
            key_points = [
                _s(point).strip() for point in key_points_raw if _s(point).strip()
            ]
        pages_raw = item.get("pages")
        pages = (
            [int(page) for page in pages_raw if isinstance(page, int)]
            if isinstance(pages_raw, list)
            else []
        )
        order_raw = item.get("order")
        order = int(order_raw) if isinstance(order_raw, int) else idx + 1
        dedupe_key = (
            section_id.casefold() if section_id else "",
            display_title.casefold() if display_title else section_title.casefold(),
        )
        if dedupe_key in seen_keys and any(dedupe_key):
            continue
        if any(dedupe_key):
            seen_keys.add(dedupe_key)
        normalized.append(
            {
                "section_id": section_id,
                "section_title": section_title,
                "display_title": display_title,
                "summary": summary,
                "key_points": key_points,
                "pages": pages,
                "order": order,
            }
        )
    return normalized


def normalize_artifact_evidence_ids(
    *,
    summary: Dict[str, Any],
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> Dict[str, int]:
    known_ids, alias_to_id = _collect_known_evidence_ids(
        doc_map=doc_map, evidence_packs=evidence_packs
    )
    normalized_count = 0
    unresolved_count = 0
    checked_count = 0

    def _normalize_item(item: Any) -> None:
        nonlocal normalized_count, unresolved_count, checked_count
        if not isinstance(item, dict):
            return
        original = _s(item.get("evidence_id")).strip()
        checked_count += 1
        normalized = _canonicalize_evidence_id(
            original, known_ids=known_ids, alias_to_id=alias_to_id
        )
        if normalized and normalized != original:
            normalized_count += 1
        if original and not normalized:
            # Preserve an unrecognized model-supplied ID so the validation
            # gate can reject and audit the hallucination instead of silently
            # converting it into an indistinguishable missing reference.
            unresolved_count += 1
            item["evidence_id"] = original
            return
        item["evidence_id"] = normalized

    claim_map = summary.get("claim_evidence_map")
    if isinstance(claim_map, list):
        for claim in claim_map:
            _normalize_item(claim)
    for item in insights_candidates:
        _normalize_item(item)
    for item in insights_final:
        _normalize_item(item)
    for item in quotes_final:
        _normalize_item(item)

    return {
        "known_reference_count": len(known_ids),
        "checked_count": checked_count,
        "normalized_count": normalized_count,
        "unresolved_count": unresolved_count,
    }


def bind_artifact_evidence_spans(
    *,
    summary: Dict[str, Any],
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> Dict[str, int]:
    span_index = _build_evidence_span_index(
        doc_map=doc_map, evidence_packs=evidence_packs
    )
    bound_count = 0
    unbound_count = 0
    pruned_claim_count = 0

    def _canonical_pages(spans: List[Dict[str, Any]]) -> List[int]:
        return list(
            dict.fromkeys(
                int(span["page"])
                for span in spans
                if isinstance(span.get("page"), int) and span["page"] > 0
            )
        )

    def _bind_item(
        item: Any,
        *,
        page_keys: tuple[str, ...],
        bind_canonical_evidence: bool = False,
    ) -> None:
        nonlocal bound_count, unbound_count
        if not isinstance(item, dict):
            return
        evidence_id = _s(item.get("evidence_id")).strip()
        if not evidence_id:
            item["evidence_spans"] = []
            return
        existing = _normalize_evidence_spans(
            item.get("evidence_spans"), evidence_id=evidence_id
        )
        derived = [dict(span) for span in span_index.get(evidence_id.casefold(), [])]
        # A resolvable evidence ID has an authoritative retained span.  Do not
        # let model-supplied page metadata override it: the generator may add
        # adjacent pages or retain stale spans while changing its copy.
        spans = derived or existing
        if derived:
            pages = _canonical_pages(derived)
            if "pages" in page_keys:
                item["pages"] = pages
            elif "page" in page_keys and pages:
                item["page"] = pages[0]
            if bind_canonical_evidence:
                canonical_evidence = " ".join(
                    dict.fromkeys(
                        _s(span.get("text")).strip()
                        for span in derived
                        if _s(span.get("text")).strip()
                    )
                )
                if canonical_evidence:
                    item["evidence"] = canonical_evidence
        if not spans:
            fallback_pages: List[int] = []
            for key in page_keys:
                raw_pages = item.get(key)
                if isinstance(raw_pages, list):
                    fallback_pages.extend(
                        int(page)
                        for page in raw_pages
                        if isinstance(page, int) and page > 0
                    )
                elif isinstance(raw_pages, int) and raw_pages > 0:
                    fallback_pages.append(raw_pages)
            deduped_pages = list(dict.fromkeys(fallback_pages))
            if deduped_pages:
                spans = [
                    {
                        "evidence_id": evidence_id,
                        "source_pack": "artifact",
                        "page": page,
                        "text": _pick_first_non_empty_text(
                            item.get("evidence"),
                            item.get("citation"),
                            item.get("text"),
                        ),
                    }
                    for page in deduped_pages
                ]
        item["evidence_spans"] = spans
        if spans:
            bound_count += 1
        else:
            unbound_count += 1

    claim_map = summary.get("claim_evidence_map")
    if isinstance(claim_map, list):
        bound_claims: List[Dict[str, Any]] = []
        for claim in claim_map:
            if not isinstance(claim, dict):
                continue
            evidence_id = _s(claim.get("evidence_id")).strip()
            claim["evidence_spans"] = []
            if not evidence_id:
                unbound_count += 1
                pruned_claim_count += 1
                continue
            existing = _normalize_evidence_spans(
                claim.get("evidence_spans"), evidence_id=evidence_id
            )
            derived = [
                dict(span) for span in span_index.get(evidence_id.casefold(), [])
            ]
            spans = derived or existing
            if derived:
                claim["pages"] = _canonical_pages(derived)
            if not spans:
                claim_pages = [
                    int(page)
                    for page in claim.get("pages") or []
                    if isinstance(page, int) and page > 0
                ]
                if claim_pages:
                    spans = [
                        {
                            "evidence_id": evidence_id,
                            "source_pack": "artifact",
                            "page": page,
                            "text": _pick_first_non_empty_text(
                                claim.get("evidence"), claim.get("claim")
                            ),
                        }
                        for page in list(dict.fromkeys(claim_pages))
                    ]
            claim["evidence_spans"] = spans
            if spans:
                bound_count += 1
                bound_claims.append(claim)
            else:
                unbound_count += 1
                pruned_claim_count += 1
        summary["claim_evidence_map"] = bound_claims

    for item in insights_candidates:
        _bind_item(item, page_keys=("pages",), bind_canonical_evidence=True)
    for item in insights_final:
        _bind_item(item, page_keys=("pages",), bind_canonical_evidence=True)
    for item in quotes_final:
        _bind_item(item, page_keys=("page",))

    return {
        "bound_count": bound_count,
        "unbound_count": unbound_count,
        "pruned_claim_count": pruned_claim_count,
        "indexed_reference_count": len(span_index),
    }


def normalize_expert_domain(categories: Optional[List[str]]) -> str:
    if not isinstance(categories, (list, tuple)):
        return "industry"
    normalized: List[str] = []
    seen: set[str] = set()
    for raw in categories:
        value = _s(raw).strip()
        if not value:
            continue
        value_key = value.casefold()
        if value_key in seen:
            continue
        seen.add(value_key)
        normalized.append(value)
        if len(normalized) == 3:
            break
    if not normalized:
        return "industry"
    return ", ".join(normalized)


def artifact_quote_candidates(evidence_packs: Dict[str, Any]) -> List[Any]:
    quote_candidates: list[Any] = []
    quote_pack = evidence_packs.get("quote_candidates")
    if isinstance(quote_pack, dict):
        quote_candidates = quote_pack.get("quote_candidates") or []
    elif isinstance(quote_pack, list):
        quote_candidates = quote_pack
    return quote_candidates


def _normalize_claims(items: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            continue
        pages_raw_obj = item.get("pages")
        pages_raw = pages_raw_obj if isinstance(pages_raw_obj, list) else []
        pages = [int(p) for p in pages_raw if isinstance(p, int)]
        evidence_id = _s(item.get("evidence_id"))
        normalized.append(
            {
                "claim": _s(item.get("claim")),
                "evidence_id": evidence_id,
                "evidence": _s(item.get("evidence")),
                "evidence_spans": _normalize_evidence_spans(
                    item.get("evidence_spans"), evidence_id=evidence_id
                ),
                "pages": pages,
            }
        )
    return normalized


def _normalize_insight_text_field(field_name: str, value: Any) -> str:
    text = _s(value).strip()
    if field_name == "coverage_role":
        if text in COVERAGE_ROLE_VALUES:
            return text
        # These strategy labels are optional.  Keep the supported cross-enum
        # translation, but do not retain an unsupported model label that the
        # artifact contract will reject later.
        return REPORT_TYPE_LENS_TO_COVERAGE_ROLE.get(text, "")
    if field_name == "report_type_lens":
        if text in REPORT_TYPE_LENS_VALUES:
            return text
        return COVERAGE_ROLE_TO_REPORT_TYPE_LENS.get(text, "")
    return text


def _collect_known_evidence_ids(
    *,
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> tuple[set[str], Dict[str, str]]:
    known_ids: set[str] = set()
    alias_to_id: Dict[str, str] = {}

    def _register(value: Any) -> None:
        evidence_id = _s(value).strip()
        if not evidence_id:
            return
        known_ids.add(evidence_id)
        alias_to_id.setdefault(evidence_id.lower(), evidence_id)

    if isinstance(evidence_packs, dict):
        for pack in evidence_packs.values():
            if not isinstance(pack, dict):
                continue
            for item_key in (
                "findings",
                "quote_candidates",
            ):
                items = pack.get(item_key)
                if not isinstance(items, list):
                    continue
                for idx, item in enumerate(items, start=1):
                    if isinstance(item, dict):
                        quote_id = _s(item.get("id")).strip()
                        _register(quote_id)
                        if item_key == "quote_candidates" and quote_id:
                            alias_to_id.setdefault(f"quote_{idx}", quote_id)
                            alias_to_id.setdefault(f"quote-{idx}", quote_id)
                            alias_to_id.setdefault(f"quote{idx}", quote_id)

    if isinstance(doc_map, dict):
        for section in doc_map.get("sections") or []:
            if isinstance(section, dict):
                _register(section.get("id"))

    for evidence_id in list(known_ids):
        match = re.match(r"^q(\d+)$", evidence_id, flags=re.IGNORECASE)
        if not match:
            continue
        quote_num = match.group(1)
        alias_to_id.setdefault(f"quote_{quote_num}", evidence_id)
        alias_to_id.setdefault(f"quote-{quote_num}", evidence_id)
        alias_to_id.setdefault(f"quote{quote_num}", evidence_id)

    return known_ids, alias_to_id


def _extract_evidence_id_candidates(raw_evidence_id: Any) -> List[str]:
    raw = _s(raw_evidence_id).strip()
    if not raw:
        return []

    candidates: List[str] = [raw]
    split_candidates = re.split(r"[,;|/]", raw)
    if len(split_candidates) > 1:
        candidates.extend(split_candidates)
    if raw.startswith("[") and raw.endswith("]"):
        candidates.extend(EVIDENCE_TOKEN_RE.findall(raw))
    if " " in raw:
        candidates.extend(EVIDENCE_TOKEN_RE.findall(raw))

    normalized: List[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        token = _s(candidate).strip()
        token = token.strip("\"'`")
        token = token.strip("[](){}")
        token = token.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _canonicalize_evidence_id(
    evidence_id: Any,
    *,
    known_ids: set[str],
    alias_to_id: Dict[str, str],
) -> str:
    raw = _s(evidence_id).strip()
    if not raw:
        return ""
    for candidate in _extract_evidence_id_candidates(raw):
        if not candidate:
            continue
        canonical = alias_to_id.get(candidate.lower())
        if canonical:
            return canonical
        quote_alias = QUOTE_ALIAS_RE.match(candidate)
        if quote_alias:
            alias_candidate = f"quote_{quote_alias.group(1)}"
            canonical = alias_to_id.get(alias_candidate)
            if canonical:
                return canonical
        if candidate in known_ids:
            return candidate
    return ""


def _normalize_evidence_spans(
    raw_spans: Any,
    *,
    evidence_id: str,
) -> List[Dict[str, Any]]:
    if not isinstance(raw_spans, list):
        return []
    normalized: List[Dict[str, Any]] = []
    seen: set[tuple[object, ...]] = set()
    for raw_span in raw_spans:
        if not isinstance(raw_span, dict):
            continue
        span_evidence_id = _s(raw_span.get("evidence_id") or evidence_id).strip()
        if not span_evidence_id:
            continue
        page = raw_span.get("page")
        start_offset = raw_span.get("start_offset")
        end_offset = raw_span.get("end_offset")
        normalized_span: Dict[str, Any] = {
            "evidence_id": span_evidence_id,
            "source_pack": _s(raw_span.get("source_pack")),
        }
        if isinstance(raw_span.get("section_id"), str) and _s(
            raw_span.get("section_id")
        ):
            normalized_span["section_id"] = _s(raw_span.get("section_id"))
        if isinstance(page, int) and page > 0:
            normalized_span["page"] = page
        if isinstance(start_offset, int) and start_offset >= 0:
            normalized_span["start_offset"] = start_offset
        if isinstance(end_offset, int) and end_offset >= 0:
            normalized_span["end_offset"] = end_offset
        text_value = _pick_first_non_empty_text(
            raw_span.get("text"),
            raw_span.get("evidence"),
            raw_span.get("citation"),
        )
        if text_value:
            normalized_span["text"] = text_value
        dedupe_key = (
            normalized_span.get("evidence_id"),
            normalized_span.get("source_pack"),
            normalized_span.get("section_id"),
            normalized_span.get("page"),
            normalized_span.get("start_offset"),
            normalized_span.get("end_offset"),
            normalized_span.get("text"),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(normalized_span)
    return normalized


def _build_evidence_span_index(
    *,
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    index: Dict[str, List[Dict[str, Any]]] = {}

    def _register(
        *,
        evidence_id: Any,
        source_pack: str,
        pages: List[int] | None = None,
        text: Any = "",
        section_id: Any = "",
        start_offset: Any = None,
        end_offset: Any = None,
    ) -> None:
        normalized_evidence_id = _s(evidence_id).strip()
        if not normalized_evidence_id:
            return
        normalized_text = _s(text).strip()
        normalized_section_id = _s(section_id).strip()
        normalized_pages = [
            page for page in (pages or []) if isinstance(page, int) and page > 0
        ]
        spans: List[Dict[str, Any]] = []
        if normalized_pages:
            for page in list(dict.fromkeys(normalized_pages)):
                span: Dict[str, Any] = {
                    "evidence_id": normalized_evidence_id,
                    "source_pack": source_pack,
                    "page": page,
                }
                if normalized_section_id:
                    span["section_id"] = normalized_section_id
                if normalized_text:
                    span["text"] = normalized_text
                if isinstance(start_offset, int) and start_offset >= 0:
                    span["start_offset"] = start_offset
                if isinstance(end_offset, int) and end_offset >= 0:
                    span["end_offset"] = end_offset
                spans.append(span)
        else:
            span = {
                "evidence_id": normalized_evidence_id,
                "source_pack": source_pack,
            }
            if normalized_section_id:
                span["section_id"] = normalized_section_id
            if normalized_text:
                span["text"] = normalized_text
            if isinstance(start_offset, int) and start_offset >= 0:
                span["start_offset"] = start_offset
            if isinstance(end_offset, int) and end_offset >= 0:
                span["end_offset"] = end_offset
            spans.append(span)
        bucket = index.setdefault(normalized_evidence_id.casefold(), [])
        for span in spans:
            if span not in bucket:
                bucket.append(span)

    if isinstance(evidence_packs, dict):
        findings_pack = evidence_packs.get("findings")
        if isinstance(findings_pack, dict):
            for item in findings_pack.get("findings") or []:
                if not isinstance(item, dict):
                    continue
                _register(
                    evidence_id=item.get("id"),
                    source_pack="findings",
                    pages=_coerce_span_pages(item),
                    text=_pick_first_non_empty_text(
                        item.get("evidence"), item.get("text"), item.get("statement")
                    ),
                )
        quotes_pack = evidence_packs.get("quote_candidates")
        if isinstance(quotes_pack, dict):
            for item in quotes_pack.get("quote_candidates") or []:
                if not isinstance(item, dict):
                    continue
                pages = []
                page_value = item.get("page")
                if isinstance(page_value, int) and page_value > 0:
                    pages = [page_value]
                _register(
                    evidence_id=item.get("id"),
                    source_pack="quote_candidates",
                    pages=pages,
                    text=item.get("text"),
                    start_offset=item.get("start_offset"),
                    end_offset=item.get("end_offset"),
                )
    if isinstance(doc_map, dict):
        for section in doc_map.get("sections") or []:
            if not isinstance(section, dict):
                continue
            _register(
                evidence_id=section.get("id"),
                source_pack="doc_map",
                pages=_coerce_span_pages(section),
                text=_pick_first_non_empty_text(
                    section.get("summary"), section.get("title"), section.get("heading")
                ),
                section_id=section.get("id"),
            )
    return index


def _coerce_span_pages(item: Dict[str, Any]) -> List[int]:
    pages: List[int] = []
    raw_pages = item.get("pages")
    if isinstance(raw_pages, list):
        pages.extend(
            int(page) for page in raw_pages if isinstance(page, int) and page > 0
        )
    raw_page = item.get("page")
    if isinstance(raw_page, int) and raw_page > 0:
        pages.append(int(raw_page))
    return list(dict.fromkeys(pages))


def _pick_first_non_empty_text(*values: Any) -> str:
    for value in values:
        text = _s(value).strip()
        if text:
            return text
    return ""


def _to_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}
