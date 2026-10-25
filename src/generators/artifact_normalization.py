from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from typing import Any, Dict, List, Optional

from src.contracts.config import AppSettings
from src.contracts.ingest import IngestSettings
from src.contracts.soft_copy_claim_provenance import (
    align_soft_copy_claim_bindings_to_sentences,
    soft_copy_material_sentences,
    soft_copy_public_text,
)
from src.utils.cache_utils import sha256_json
from src.utils.coercion import stripped_string_value as _s
from src.utils.errors import AppError
from src.utils.json_utils import dump_json_object as _dump_json
from src.utils.numeric_display import preserve_unique_source_displays
from src.utils.public_metric_display import normalize_public_metric_display
from src.utils.quantity import Quantity, extract_quantities, quantities_match
from src.utils.text_normalization import normalize_for_lookup, normalize_text
from src.utils.verified_facts import PROTECTED_METRIC_FIELDS

EDITORIAL_PLAN_TRANSFORM_VERSION = "normalize_and_stabilize_editorial_plan:1.0"
ARTIFACT_INSIGHT_SELECTION_VERSION = "evidence_backed_shortlisting:15"
VERIFIED_FACT_CONTEXT_VERSION = "verified_fact_context:1.0"

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
METRIC_BINDING_FIELDS = (
    "subject",
    "cohort",
    "denominator",
    "observation_status",
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
TEMPORAL_ONLY_METRIC_RE = re.compile(
    r"^(?:(?:by|in|from|through|until|as\s+of)\s+)?"
    r"(?:(?:the\s+)?(?:start|beginning|end)\s+of\s+)?\d{4}e?$",
    re.IGNORECASE,
)
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
    known_evidence_ids, _ = _collect_known_evidence_ids(
        doc_map=doc_map or {}, evidence_packs=evidence_packs or {}
    )
    return {
        "doc_map_json": _dump_json(doc_map or {}),
        "evidence_json": _dump_json(evidence_packs or {}),
        "canonical_evidence_ids_json": _dump_json(
            sorted(known_evidence_ids, key=str.casefold)
        ),
    }


def build_verified_fact_doc_map(doc_map: Dict[str, Any]) -> Dict[str, Any]:
    """Retain only structural navigation context after visual fact admission.

    Section titles and stable ordering are layout inputs.  DocMap summaries,
    key points, pages, and report-level descriptive fields remain discovery
    material and must not reach downstream factual prompts in verified mode.
    """

    source = doc_map if isinstance(doc_map, dict) else {}
    sections = source.get("sections")
    structural_sections: list[dict[str, Any]] = []
    if isinstance(sections, list):
        for index, raw_section in enumerate(sections):
            if not isinstance(raw_section, dict):
                continue
            section_id = _s(raw_section.get("id")).strip()
            title = _s(
                raw_section.get("title")
                or raw_section.get("heading")
                or raw_section.get("name")
            ).strip()
            if not section_id and not title:
                continue
            item: dict[str, Any] = {
                "id": section_id or f"section-{index + 1}",
                "title": title,
            }
            order = raw_section.get("order")
            if isinstance(order, int) and not isinstance(order, bool):
                item["order"] = order
            structural_sections.append(item)
    result: dict[str, Any] = {
        "schema_version": VERIFIED_FACT_CONTEXT_VERSION,
        "sections": structural_sections,
    }
    for key in ("doc_id", "document_id", "title"):
        value = _s(source.get(key)).strip()
        if value:
            result[key] = value
    return result


def remap_editorial_plan_to_verified_facts(
    editorial_plan: Dict[str, Any],
    verified_facts: List[Dict[str, Any]],
    *,
    source_findings: Any = None,
    coverage_diagnostics: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Keep planning themes while replacing discovery IDs with fact IDs.

    Section references are navigation hints from discovery.  They are resolved
    only through the original finding-to-section links of admitted facts; a
    section name alone is never treated as a factual binding.
    """

    plan = normalize_artifact_editorial_plan(editorial_plan)
    facts = [
        fact
        for fact in verified_facts
        if isinstance(fact, dict) and _s(fact.get("fact_id")).strip()
    ]
    fact_evidence_ids = [
        f"verified-fact:{_s(fact.get('fact_id')).strip()}" for fact in facts
    ]
    if not fact_evidence_ids:
        raise AppError(
            code="verified_facts_missing",
            message=(
                "Verified-mode editorial planning requires at least one verified fact"
            ),
            retryable=False,
        )
    aliases: dict[str, set[str]] = {}
    fact_discovery_ids: dict[str, set[str]] = {}
    for fact, evidence_id in zip(facts, fact_evidence_ids, strict=True):
        identifiers = {_s(fact.get("fact_id")).strip(), evidence_id}
        discovery_identifiers: set[str] = set()
        provenance = fact.get("provenance")
        if isinstance(provenance, dict):
            discovery_candidate_id = _s(
                provenance.get("discovery_candidate_id")
            ).strip()
            identifiers.add(discovery_candidate_id)
            if discovery_candidate_id:
                discovery_identifiers.add(discovery_candidate_id)
            raw_evidence_ids = provenance.get("discovery_evidence_ids")
            if isinstance(raw_evidence_ids, list):
                discovery_identifiers.update(
                    _s(value).strip() for value in raw_evidence_ids if _s(value).strip()
                )
                identifiers.update(discovery_identifiers)
        for identifier in identifiers:
            if identifier:
                for alias in {
                    identifier.casefold(),
                    _fallback_evidence_key(identifier),
                }:
                    if alias:
                        aliases.setdefault(alias, set()).add(evidence_id)
        fact_discovery_ids[evidence_id] = discovery_identifiers

    finding_sections = _finding_section_ids(source_findings)

    section_fact_targets: dict[str, list[str]] = {}
    for evidence_id in fact_evidence_ids:
        for discovery_id in fact_discovery_ids.get(evidence_id, set()):
            sections = finding_sections.get(_fallback_evidence_key(discovery_id), set())
            if len(sections) != 1:
                continue
            section_id = next(iter(sections))
            targets = section_fact_targets.setdefault(section_id, [])
            if evidence_id not in targets:
                targets.append(evidence_id)

    themes: list[dict[str, Any]] = []
    unmapped_themes: list[str] = []
    for theme in plan["themes"]:
        mapped: list[str] = []
        for raw_evidence_id in theme["evidence_ids"]:
            raw_key = raw_evidence_id.casefold()
            direct_targets = aliases.get(raw_key) or aliases.get(
                _fallback_evidence_key(raw_evidence_id), set()
            )
            if direct_targets:
                if len(direct_targets) == 1:
                    target = next(iter(direct_targets))
                    if target not in mapped:
                        mapped.append(target)
                continue
            for target in section_fact_targets.get(normalize_text(raw_evidence_id), []):
                if target not in mapped:
                    mapped.append(target)
        if not mapped:
            unmapped_themes.append(theme["theme"])
            continue
        themes.append({**theme, "evidence_ids": mapped})

    central_priority = min(theme["priority"] for theme in plan["themes"])
    lost_central_themes = [
        theme["theme"]
        for theme in plan["themes"]
        if theme["theme"] in unmapped_themes and theme["priority"] == central_priority
    ]
    if coverage_diagnostics is not None:
        coverage_diagnostics.clear()
        coverage_diagnostics.update(
            {
                "planned_themes": [theme["theme"] for theme in plan["themes"]],
                "planned_theme_bindings": deepcopy(plan["themes"]),
                "supported_themes": [theme["theme"] for theme in themes],
                "supported_theme_bindings": deepcopy(themes),
                "lost_themes": list(unmapped_themes),
                "lost_central_themes": list(lost_central_themes),
                "planned_theme_count": len(plan["themes"]),
                "supported_theme_count": len(themes),
                "lost_theme_count": len(unmapped_themes),
            }
        )
    if lost_central_themes:
        raise AppError(
            code="verified_fact_editorial_coverage_insufficient",
            message=(
                "Verified-fact editorial coverage lost the central planned theme: "
                + ", ".join(lost_central_themes)
            ),
            retryable=False,
            context={
                "verified_fact_count": len(fact_evidence_ids),
                "mapped_theme_count": len(themes),
                "unmapped_themes": unmapped_themes,
                "lost_central_themes": lost_central_themes,
            },
        )
    if len(themes) < MIN_FINAL_ARTIFACT_INSIGHTS:
        raise AppError(
            code="verified_fact_editorial_coverage_insufficient",
            message=(
                "Verified-fact editorial coverage requires at least "
                f"{MIN_FINAL_ARTIFACT_INSIGHTS} themes with unambiguous fact bindings"
            ),
            retryable=False,
            context={
                "verified_fact_count": len(fact_evidence_ids),
                "mapped_theme_count": len(themes),
                "unmapped_themes": unmapped_themes,
            },
        )
    return {"report_thesis": plan["report_thesis"], "themes": themes}


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
    claims = _normalize_claims(claim_map)
    compact = _s(data.get("card_tldr_compact"))
    if not _is_complete_short_sentence(compact, limit=18):
        compact = next(
            (
                _s(claim.get("claim")).strip()
                for claim in claims
                if _is_complete_short_sentence(_s(claim.get("claim")), limit=18)
            ),
            compact,
        )
    return {
        "tldr": _s(data.get("tldr")),
        "card_tldr_compact": compact,
        "executive_summary": _strip_public_editorial_scaffold(
            strip_artifact_inline_reference_ids(_s(data.get("executive_summary")))
        ),
        "claim_evidence_map": claims,
    }


def _is_complete_short_sentence(value: str, *, limit: int) -> bool:
    text = " ".join(value.split())
    return (
        bool(text)
        and len(text.split()) <= limit
        and not text.endswith(("...", "\u2026"))
        and text.endswith((".", "?", "!"))
    )


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
            timeframe = _s(metric.get("timeframe")).strip()
            if timeframe and not _source_text_contains_field(timeframe, evidence):
                # A candidate may carry a period copied from a neighbouring
                # finding.  The bound evidence is authoritative at this
                # boundary; keep the supported metric but remove only the
                # unsupported temporal qualifier before it reaches the spine
                # and public copy families.
                metric["timeframe"] = ""
        text_has_unsupported_number = _has_unsupported_material_number(
            _s(insight.get("text")), evidence
        )
        metric_has_unsupported_number = isinstance(metric, dict) and (
            _has_unsupported_material_number(_s(metric.get("value")), evidence)
        )
        if text_has_unsupported_number:
            # The evidence was bound from a canonical retained record. Replace
            # only a generated numeric claim that exceeds that record with its
            # exact source-backed statement before artifact retention.
            insight["text"] = evidence
        if isinstance(metric, dict) and (
            not _s(metric.get("value")).strip() or metric_has_unsupported_number
        ):
            _clear_unproven_metric_metadata(metric)
        if evidence.strip():
            downstream_evidence.append(evidence)
    combined_downstream_evidence = " ".join([summary_evidence, *downstream_evidence])
    return (
        _preserve_downstream_source_displays(
            expert_comment, combined_downstream_evidence
        ),
        _preserve_downstream_source_displays(
            linkedin_post, combined_downstream_evidence
        ),
    )


def preserve_soft_copy_binding_source_displays(
    *,
    summary: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
    soft_copy_claim_bindings: Dict[str, List[Dict[str, Any]]],
) -> None:
    """Apply the final public display correction to declared binding text too.

    The correction remains deterministic and does not choose evidence: it only
    carries a binding's already-validated classification and evidence IDs onto
    the exact sentence that will be retained.  The provenance builder then
    derives its ID, hash, and source spans from that corrected sentence.
    """

    summary_evidence = " ".join(
        _s(item.get("evidence"))
        for item in summary.get("claim_evidence_map", [])
        if isinstance(item, dict) and _s(item.get("evidence")).strip()
    )
    downstream_evidence = [summary_evidence]
    for insight in insights_final:
        if isinstance(insight, dict) and _s(insight.get("evidence")).strip():
            downstream_evidence.append(_s(insight.get("evidence")))
    combined_downstream_evidence = " ".join(downstream_evidence)

    for binding in soft_copy_claim_bindings.get("summary", []):
        if isinstance(binding, dict):
            binding["claim"] = _preserve_source_displays(
                _s(binding.get("claim")), summary_evidence
            )
    for family in ("expert_comment", "linkedin_post"):
        for binding in soft_copy_claim_bindings.get(family, []):
            if isinstance(binding, dict):
                binding["claim"] = _preserve_downstream_source_displays(
                    _s(binding.get("claim")), combined_downstream_evidence
                )


def retain_bound_optional_soft_copy_sentences(
    *,
    artifact_family: str,
    public_text: str,
    claim_bindings: object,
) -> str:
    """Fail closed by omitting unbound optional public-copy sentences.

    This finalization fallback operates only on Expert Comment and LinkedIn.
    It keeps the model's already-declared semantic binding intact and never
    infers classification or evidence for an omitted sentence.
    """

    if artifact_family not in {"expert_comment", "linkedin_post"}:
        return public_text
    sentences = soft_copy_material_sentences(public_text)
    if not sentences:
        return public_text
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family=artifact_family,
        public_output=public_text,
        claim_bindings=claim_bindings,
    )
    covered = {
        " ".join(str(binding.get("claim") or "").split())
        for binding in aligned
        if isinstance(binding, dict)
    }
    retained = [sentence for sentence in sentences if sentence in covered]
    if not retained or len(retained) == len(sentences):
        return public_text
    return " ".join(retained)


def carry_soft_copy_binding_semantics_to_final_sentences(
    *,
    artifact_family: str,
    original_public_text: object,
    final_public_text: object,
    original_claim_bindings: object,
) -> list[dict[str, Any]]:
    """Carry declared semantics across a deterministic same-grid correction.

    This never resolves an unknown or ambiguous binding. It applies only when
    the original public grid is completely and uniquely covered and the final
    correction retains the same sentence count and order.
    """

    original_text = soft_copy_public_text(artifact_family, original_public_text)
    final_text = soft_copy_public_text(artifact_family, final_public_text)
    original_sentences = soft_copy_material_sentences(original_text)
    final_sentences = soft_copy_material_sentences(final_text)
    if not original_sentences or len(original_sentences) != len(final_sentences):
        return []
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family=artifact_family,
        public_output=original_public_text,
        claim_bindings=original_claim_bindings,
    )
    binding_by_sentence = {
        " ".join(str(binding.get("claim") or "").split()): binding
        for binding in aligned
        if isinstance(binding, dict)
    }
    if any(sentence not in binding_by_sentence for sentence in original_sentences):
        return []
    return [
        {**binding_by_sentence[original], "claim": final}
        for original, final in zip(original_sentences, final_sentences, strict=True)
    ]


def source_backed_summary_claim_bindings(
    summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Derive fallback-summary bindings from direct or descriptive evidence."""

    bindings: List[Dict[str, Any]] = []
    for claim in summary.get("claim_evidence_map", []):
        if not isinstance(claim, dict) or not _claim_has_safe_summary_evidence(claim):
            continue
        claim_text = _s(claim.get("claim")).strip()
        evidence_ids = list(
            dict.fromkeys(
                evidence_id
                for evidence_id in [
                    _s(claim.get("evidence_id")).strip(),
                    *[
                        _s(span.get("evidence_id")).strip()
                        for span in claim.get("evidence_spans") or []
                        if isinstance(span, dict) and _span_is_safe_summary_source(span)
                    ],
                ]
                if evidence_id
            )
        )
        if claim_text:
            bindings.append(
                {
                    "claim": claim_text,
                    "classification": "factual",
                    "evidence_ids": evidence_ids,
                }
            )
    return bindings


def _preserve_source_displays(text: str, evidence: str) -> str:
    return preserve_unique_source_displays(text, evidence)


def _source_text_contains_field(value: str, evidence: str) -> bool:
    """Return whether a protected display is explicitly present in evidence."""

    normalized_value = normalize_for_lookup(value)
    normalized_evidence = normalize_for_lookup(evidence)
    if not normalized_value:
        return True
    if normalized_value in normalized_evidence:
        return True
    value_tokens = set(re.findall(r"[a-z0-9%]+", normalized_value))
    evidence_tokens = set(re.findall(r"[a-z0-9%]+", normalized_evidence))
    value_tokens.difference_update(
        {
            "a",
            "an",
            "and",
            "as",
            "at",
            "by",
            "for",
            "in",
            "of",
            "on",
            "the",
            "to",
            "with",
        }
    )
    return bool(value_tokens) and all(
        token in evidence_tokens or _timeframe_token_is_present(token, evidence_tokens)
        for token in value_tokens
    )


def _timeframe_token_is_present(token: str, evidence_tokens: set[str]) -> bool:
    """Allow a conservative inflectional match without inferring a period."""

    if any(character.isdigit() for character in token):
        return False
    stem_length = max(4, len(token) - 3)
    stem = token[:stem_length]
    return any(
        len(candidate) >= stem_length and candidate[:stem_length] == stem
        for candidate in evidence_tokens
    )


def _has_unsupported_material_number(text: str, evidence: str) -> bool:
    number_pattern = r"\d{1,3}(?:[,.]\d{3})+|\d+(?:[.,]\d+)?"
    evidence_numbers = {
        _normalise_numeric_display(match.group())
        for match in re.finditer(number_pattern, evidence)
    }
    material_numbers = {
        _normalise_numeric_display(match.group())
        for match in re.finditer(number_pattern, text)
        if not re.fullmatch(
            r"(?:19|20)\d{2}", _normalise_numeric_display(match.group())
        )
    }
    return bool(material_numbers - evidence_numbers)


def _clear_unproven_metric_metadata(metric: Dict[str, Any]) -> None:
    """Remove metric context when its value is absent or not source-backed."""

    for field_name in (*METRIC_FIELDS, *METRIC_BINDING_FIELDS):
        if field_name in metric:
            metric[field_name] = ""


def constrain_summary_to_source_backed_claims(
    summary: Dict[str, Any],
    *,
    require_direct_fallback: bool = False,
) -> bool:
    """Fail closed to direct claim copy when a strong claim has weak evidence."""

    claims = summary.get("claim_evidence_map") if isinstance(summary, dict) else None
    if not isinstance(claims, list):
        return False
    valid_claims = [claim for claim in claims if isinstance(claim, dict)]
    weak_strong_claims = [
        claim for claim in valid_claims if _claim_is_strong_and_weakly_bound(claim)
    ]
    if not weak_strong_claims and not require_direct_fallback:
        return False
    direct_claims = [
        claim
        for claim in valid_claims
        if _claim_has_direct_evidence(claim) and _s(claim.get("claim")).strip()
    ]
    if not direct_claims:
        return False
    descriptive_claims = [
        claim
        for claim in valid_claims
        if not _claim_has_direct_evidence(claim)
        and _claim_has_descriptive_doc_map_evidence(claim)
    ]
    fallback_claims = [*direct_claims, *descriptive_claims]
    fallback_claims = [
        claim for claim in fallback_claims if _s(claim.get("claim")).strip()
    ]
    direct_public_claims = [_s(claim.get("claim")).strip() for claim in direct_claims]
    public_claims = [_s(claim.get("claim")).strip() for claim in fallback_claims]
    public_claims = [claim for claim in public_claims if claim]
    if not public_claims:
        return False
    compact_claim = next(
        (
            claim
            for claim in direct_public_claims
            if _is_complete_short_sentence(claim, limit=18)
        ),
        None,
    )
    if compact_claim is None:
        raise AppError(
            code="card_tldr_compact_invalid",
            message=(
                "summary.card_tldr_compact must be a complete sentence of 1 to 18 words"
            ),
            retryable=False,
            context={
                "field": "summary.card_tldr_compact",
                "word_count": len(" ".join(direct_public_claims[0].split()).split()),
            },
        )
    summary["claim_evidence_map"] = fallback_claims
    summary["tldr"] = public_claims[0]
    summary["card_tldr_compact"] = compact_claim
    summary["executive_summary"] = " ".join(public_claims[:3])
    return True


def summary_has_unbound_material_sentences(
    *, summary: Dict[str, Any], claim_bindings: object
) -> bool:
    """Return whether final Summary prose exceeds its declared semantics."""

    text = soft_copy_public_text("summary", summary)
    if not text:
        return False
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="summary",
        public_output=summary,
        claim_bindings=claim_bindings,
    )
    covered = {
        " ".join(str(binding.get("claim") or "").split())
        for binding in aligned
        if isinstance(binding, dict)
    }
    return any(
        sentence not in covered for sentence in soft_copy_material_sentences(text)
    )


def _claim_is_strong_and_weakly_bound(claim: Dict[str, Any]) -> bool:
    claim_text = _s(claim.get("claim")).strip()
    if not claim_text or not _strong_claim_text(claim_text):
        return False
    spans = [
        span for span in claim.get("evidence_spans") or [] if isinstance(span, dict)
    ]
    return bool(spans) and not any(_span_is_direct(span) for span in spans)


def _claim_has_direct_evidence(claim: Dict[str, Any]) -> bool:
    return any(
        _span_is_direct(span)
        for span in claim.get("evidence_spans") or []
        if isinstance(span, dict)
    )


def _claim_has_descriptive_doc_map_evidence(claim: Dict[str, Any]) -> bool:
    claim_text = _s(claim.get("claim")).strip()
    spans = [
        span for span in claim.get("evidence_spans") or [] if isinstance(span, dict)
    ]
    return bool(
        claim_text
        and not _strong_claim_text(claim_text)
        and spans
        and any(
            _s(span.get("source_pack")).strip() == "doc_map"
            and _s(span.get("text")).strip()
            for span in spans
        )
    )


def _claim_has_safe_summary_evidence(claim: Dict[str, Any]) -> bool:
    return _claim_has_direct_evidence(claim) or _claim_has_descriptive_doc_map_evidence(
        claim
    )


def _span_is_safe_summary_source(span: Dict[str, Any]) -> bool:
    return _span_is_direct(span) or (
        _s(span.get("source_pack")).strip() in {"doc_map", "verified_facts"}
        and bool(_s(span.get("text")).strip())
    )


def _span_is_direct(span: Dict[str, Any]) -> bool:
    return _s(span.get("source_pack")).strip() in {
        "findings",
        "quote_candidates",
    }


def _strong_claim_text(text: str) -> bool:
    return bool(
        re.search(
            r"(?:\d+(?:[\.,]\d+)?\s*(?:%|percent|percentage|bps|points|x|times|million|billion|trillion|k|m|bn)\b|[$€£]\s*\d|\b(?:proves?|guarantees?|must|will|always|never|only|highest|lowest|largest|smallest|dominates?|requires?|increas(?:e|es|ed|ing)|rose|grew|declin(?:e|es|ed|ing)|fell|drop(?:s|ped|ping)?|reduc(?:e|es|ed|ing)|boost(?:s|ed|ing)?|dr(?:ive|ives|iven|iving)|caus(?:e|es|ed|ing)|result(?:s|ed|ing)?|lead(?:s|ing)?\s+to|improv(?:e|es|ed|ing)|worsen(?:s|ed|ing)|predict(?:s|ed|ing)|forecast(?:s|ed|ing))\b)",
            text,
            re.IGNORECASE,
        )
    )


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


def normalize_artifact_insights(
    items: Any, *, prefix: str, verified_mode: bool = False
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        metric_raw = _to_dict(item.get("metric"))
        metric: Dict[str, Any] = {
            key: _s(metric_raw.get(key, "")) for key in METRIC_FIELDS
        }
        metric.update(
            {
                key: _s(metric_raw.get(key, ""))
                for key in (*METRIC_BINDING_FIELDS, "forecast_status")
                if key in metric_raw or verified_mode
            }
        )
        if verified_mode:
            metric["value"] = _s(metric_raw.get("value", ""))
            metric["unit"] = _s(metric_raw.get("unit", ""))
            observations = metric_raw.get("observations")
            if isinstance(observations, list):
                metric["observations"] = deepcopy(observations)
        else:
            metric["value"], metric["unit"] = normalize_public_metric_display(
                value=metric["value"], unit=metric["unit"]
            )
        if not verified_mode and TEMPORAL_ONLY_METRIC_RE.fullmatch(
            metric["value"].strip()
        ):
            _clear_unproven_metric_metadata(metric)
        pages_raw_obj = item.get("pages")
        pages_raw = pages_raw_obj if isinstance(pages_raw_obj, list) else []
        pages = [int(p) for p in pages_raw if isinstance(p, int)]
        evidence_id = _s(item.get("evidence_id"))
        evidence_ids = _ordered_item_evidence_ids(item)
        insight: Dict[str, Any] = {
            "id": _s(item.get("id") or f"{prefix}_{idx + 1}"),
            "text": _normalize_public_numeric_signs(_s(item.get("text"))),
            "evidence_id": evidence_id,
            "evidence": _normalize_public_numeric_signs(_s(item.get("evidence"))),
            "evidence_spans": _normalize_evidence_spans(
                item.get("evidence_spans"), evidence_id=evidence_id
            ),
            "metric": metric,
            "pages": pages,
        }
        if isinstance(item.get("evidence_ids"), list) and evidence_ids:
            insight["evidence_ids"] = evidence_ids
        timeframe = _s(metric.get("timeframe")).strip()
        binding_evidence = " ".join(
            [
                insight["evidence"],
                *[
                    _s(span.get("text") or span.get("evidence"))
                    for span in insight["evidence_spans"]
                    if isinstance(span, dict)
                ],
            ]
        )
        if (
            not verified_mode
            and timeframe
            and not _source_text_contains_field(timeframe, binding_evidence)
        ):
            metric["timeframe"] = ""
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
    require_final_candidate_lineage: bool = False,
    preserve_all: bool = False,
    verified_mode: bool = False,
    source_findings: Any = None,
    max_count: int | None = None,
) -> List[Dict[str, Any]]:
    """Lead with the strongest evidence-bound insight and retain theme coverage.

    ``require_final_candidate_lineage`` is used only at the final-insight
    admission boundary.  Candidate-stage selection remains able to admit
    evidence-bound alternatives from the findings fallback pool.

    When a final insight shares a stable ID with a chosen candidate, the
    candidate is the evidence-anchored source of the protected factual fields
    (metric value/unit/timeframe/geography/cohort/denominator/observation
    status and its evidence binding).  The final stage may rewrite editorial
    wording, but any factual drift it introduces is deterministically
    reverted to the retained candidate values instead of mutating the fact.
    """
    plan = normalize_artifact_editorial_plan(editorial_plan)
    conflicting_candidate_ids = _candidate_factual_conflict_ids(candidate_insights)
    candidate_facts = _candidate_factual_fields(
        candidate_insights,
        preserve_unknown_metric_fields=verified_mode,
    )
    unresolved_candidate_ids = set(_candidate_insight_groups(candidate_insights)) - set(
        candidate_facts
    )
    final_lineage_ids = set(candidate_facts)
    available_evidence_ids = {
        evidence_id
        for fact in candidate_facts.values()
        for evidence_id in _ordered_item_evidence_ids(fact)
    }
    anchored_finals = [
        _restore_candidate_factual_fields(
            item,
            candidate_facts,
            preserve_unknown_metric_fields=verified_mode,
            allowed_evidence_ids=available_evidence_ids,
        )
        if isinstance(item, dict)
        else item
        for item in final_insights
        if not (
            isinstance(item, dict)
            and _s(item.get("id")).strip()
            in conflicting_candidate_ids.union(unresolved_candidate_ids)
        )
        and (
            not require_final_candidate_lineage
            or (
                isinstance(item, dict)
                and _s(item.get("id")).strip() in final_lineage_ids
            )
        )
    ]
    ranked = _ranked_unique_insights(
        anchored_finals,
        [] if require_final_candidate_lineage and verified_mode else candidate_insights,
    )
    required_count = max(REQUIRED_REPORT_PAYLOAD_INSIGHTS, len(plan["themes"]))
    selected: List[Dict[str, Any]] = []
    selected_keys: set[str] = set()
    theme_bindings = editorial_plan_theme_bindings(
        plan,
        source_findings=source_findings,
    )
    selection_limit = (
        max_count if isinstance(max_count, int) and max_count > 0 else None
    )
    # A high-scored final claim may still lack its source binding; allow only
    # evidence-bound candidates to bypass the editorial plan's coverage order.
    grounded_ranked = [
        item for item in ranked if _s(item[1].get("evidence_id")).strip()
    ]
    if grounded_ranked:
        _append_distinct_insight(
            selected, selected_keys, _best_ranked_insight(grounded_ranked)[1]
        )
    for binding in theme_bindings:
        if selection_limit is not None and len(selected) >= selection_limit:
            break
        evidence_ids = set(binding["coverage_keys"])
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
        if selection_limit is not None and len(selected) >= selection_limit:
            break
        if (
            selection_limit is None
            and not preserve_all
            and len(selected) >= required_count
        ):
            break
        _append_distinct_insight(selected, selected_keys, insight)
    return selected


def validate_final_insight_candidate_lineage(
    *,
    final_insights: List[Dict[str, Any]],
    candidate_insights: List[Dict[str, Any]],
) -> None:
    """Reject final identities that cannot resolve to one bound candidate.

    Final-stage selection may fill missing slots from eligible candidates, but
    an emitted final identity must first be validated.  Raising the existing
    application error lets structured-output recovery record the invalid ID
    instead of silently dropping it and retaining a different proposition.
    """

    candidate_facts = _candidate_factual_fields(candidate_insights)
    final_ids: list[str] = []
    duplicate_ids: set[str] = set()
    seen_ids: set[str] = set()
    missing_id = False
    for insight in final_insights:
        if not isinstance(insight, dict):
            continue
        insight_id = _s(insight.get("id")).strip()
        if not insight_id:
            missing_id = True
            continue
        if insight_id in seen_ids:
            duplicate_ids.add(insight_id)
            continue
        seen_ids.add(insight_id)
        final_ids.append(insight_id)

    invalid_ids = sorted(
        {insight_id for insight_id in final_ids if insight_id not in candidate_facts}
    )
    if not invalid_ids and not duplicate_ids and not missing_id:
        return
    context: Dict[str, Any] = {}
    if invalid_ids:
        context["invalid_insight_ids"] = invalid_ids
    if duplicate_ids:
        context["duplicate_insight_ids"] = sorted(duplicate_ids)
    if missing_id:
        context["missing_insight_id"] = True
    raise AppError(
        code="artifact_final_insight_lineage_invalid",
        message=(
            "Final insight identities must resolve to unique, evidence-bound candidates"
        ),
        retryable=False,
        context=context,
    )


def final_insight_editorial_coverage(
    *,
    final_insights: List[Dict[str, Any]],
    candidate_insights: List[Dict[str, Any]],
    editorial_plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Report which planned themes are represented by final candidate facts."""

    candidate_facts = _candidate_factual_fields(candidate_insights)
    selected_evidence_keys: set[str] = set()
    for insight in final_insights:
        if not isinstance(insight, dict):
            continue
        candidate_fact = candidate_facts.get(_s(insight.get("id")).strip())
        evidence_ids = (
            _ordered_item_evidence_ids(candidate_fact)
            if candidate_fact is not None
            else _ordered_item_evidence_ids(insight)
        )
        selected_evidence_keys.update(
            _fallback_evidence_key(evidence_id) for evidence_id in evidence_ids
        )

    theme_bindings = editorial_plan_theme_bindings(editorial_plan)
    theme_coverage: List[Dict[str, Any]] = []
    for binding in theme_bindings:
        coverage_keys = set(binding["coverage_keys"])
        theme_coverage.append(
            {
                "theme": binding["theme"],
                "priority": binding["priority"],
                "selected": bool(coverage_keys & selected_evidence_keys),
                "evidence_keys": sorted(coverage_keys),
            }
        )
    priorities = [
        item["priority"]
        for item in theme_coverage
        if isinstance(item.get("priority"), int)
    ]
    central_priority = min(priorities) if priorities else None
    omitted_themes = [item["theme"] for item in theme_coverage if not item["selected"]]
    omitted_central_themes = [
        item["theme"]
        for item in theme_coverage
        if not item["selected"] and item["priority"] == central_priority
    ]
    return {
        "planned_theme_count": len(theme_coverage),
        "selected_theme_count": sum(1 for item in theme_coverage if item["selected"]),
        "selected_themes": [
            item["theme"] for item in theme_coverage if item["selected"]
        ],
        "omitted_themes": omitted_themes,
        "omitted_central_themes": omitted_central_themes,
        "selected_evidence_keys": sorted(selected_evidence_keys),
        "theme_coverage": theme_coverage,
    }


def validate_final_insight_editorial_coverage(
    *,
    final_insights: List[Dict[str, Any]],
    candidate_insights: List[Dict[str, Any]],
    editorial_plan: Dict[str, Any],
    coverage_diagnostics: Dict[str, Any] | None = None,
) -> None:
    """Fail closed when a supported central theme is silently omitted."""

    coverage = final_insight_editorial_coverage(
        final_insights=final_insights,
        candidate_insights=candidate_insights,
        editorial_plan=editorial_plan,
    )
    if coverage_diagnostics is not None:
        coverage_diagnostics.clear()
        coverage_diagnostics.update(coverage)
    if not coverage["omitted_central_themes"]:
        return
    raise AppError(
        code="artifact_final_insight_coverage_invalid",
        message=("Final insight selection omitted a supported central editorial theme"),
        retryable=False,
        context={"omitted_central_themes": coverage["omitted_central_themes"]},
    )


def eligible_final_insight_candidates(
    candidate_insights: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return one authoritative, source-bound candidate for each stable ID."""

    candidate_facts = _candidate_factual_fields(candidate_insights)
    eligible: List[Dict[str, Any]] = []
    for insight_id, group in _candidate_insight_groups(candidate_insights).items():
        if insight_id not in candidate_facts:
            continue
        reliable = [
            insight for insight in group if _s(insight.get("evidence_id")).strip()
        ]
        if reliable:
            eligible.append(
                _restore_candidate_factual_fields(
                    min(reliable, key=_insight_quality_key), candidate_facts
                )
            )
    return eligible


def restore_artifact_insight_factual_fields(
    insight: Dict[str, Any], candidate_insights: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Restore a final insight from the authoritative candidate fact index."""

    candidate_facts = _candidate_factual_fields(candidate_insights)
    return _restore_candidate_factual_fields(
        insight,
        candidate_facts,
        allowed_evidence_ids={
            evidence_id
            for fact in candidate_facts.values()
            for evidence_id in _ordered_item_evidence_ids(fact)
        },
    )


def _candidate_factual_fields(
    candidate_insights: List[Dict[str, Any]],
    *,
    preserve_unknown_metric_fields: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Index the retained factual payload of each stable-ID candidate."""

    best_candidates: Dict[str, Dict[str, Any]] = {}
    for insight_id, group in _candidate_insight_groups(candidate_insights).items():
        reliable = [
            insight for insight in group if _s(insight.get("evidence_id")).strip()
        ]
        if not reliable or _candidate_group_has_factual_conflict(reliable):
            continue
        best_candidates[insight_id] = min(reliable, key=_insight_quality_key)

    facts: Dict[str, Dict[str, Any]] = {}
    for insight_id, insight in best_candidates.items():
        fact: Dict[str, Any] = {}
        if "metric" in insight:
            fact["metric"] = _complete_protected_metric_binding(
                insight.get("metric"),
                preserve_unknown_fields=preserve_unknown_metric_fields,
            )
        evidence_ids = _ordered_item_evidence_ids(insight)
        if isinstance(insight.get("evidence_ids"), list):
            fact["evidence_ids"] = evidence_ids
        for field_name in ("evidence_id", "evidence", "pages", "evidence_spans"):
            if field_name not in insight:
                continue
            value = insight.get(field_name)
            if field_name in {"evidence_id", "evidence"}:
                fact[field_name] = _s(value).strip()
            else:
                fact[field_name] = deepcopy(value) if value else []
        facts[insight_id] = fact
    return facts


def _ordered_item_evidence_ids(item: Any) -> List[str]:
    """Return a primary-first, duplicate-free evidence binding list."""

    if not isinstance(item, dict):
        return []
    values: List[str] = []
    primary = _s(item.get("evidence_id")).strip()
    if primary:
        values.append(primary)
    raw_ids = item.get("evidence_ids")
    if isinstance(raw_ids, list):
        values.extend(_s(value).strip() for value in raw_ids)
    return list(dict.fromkeys(value for value in values if value))


def _candidate_insight_groups(
    candidate_insights: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for insight in candidate_insights:
        if not isinstance(insight, dict):
            continue
        insight_id = _s(insight.get("id")).strip()
        if insight_id:
            groups.setdefault(insight_id, []).append(insight)
    return groups


def _candidate_factual_conflict_ids(
    candidate_insights: List[Dict[str, Any]],
) -> set[str]:
    return {
        insight_id
        for insight_id, group in _candidate_insight_groups(candidate_insights).items()
        if _candidate_group_has_factual_conflict(
            [insight for insight in group if _s(insight.get("evidence_id")).strip()]
        )
    }


def _candidate_group_has_factual_conflict(
    candidates: List[Dict[str, Any]],
) -> bool:
    evidence_ids = {
        normalize_for_lookup(candidate.get("evidence_id"))
        for candidate in candidates
        if normalize_for_lookup(candidate.get("evidence_id"))
    }
    if len(evidence_ids) > 1:
        return True
    for field_name in PROTECTED_METRIC_FIELDS:
        values = {
            normalize_for_lookup(
                (candidate.get("metric") or {}).get(field_name)
                if isinstance(candidate.get("metric"), dict)
                else ""
            )
            for candidate in candidates
        }
        values.discard("")
        if len(values) > 1:
            return True
    source_identities = {
        normalize_for_lookup(
            candidate.get("source_identity") or candidate.get("source_id")
        )
        for candidate in candidates
        if normalize_for_lookup(
            candidate.get("source_identity") or candidate.get("source_id")
        )
    }
    if len(source_identities) > 1:
        return True
    for index, candidate in enumerate(candidates):
        for other in candidates[index + 1 :]:
            if _candidate_provenance_has_conflict(candidate, other):
                return True
    return False


def _candidate_provenance_has_conflict(
    candidate: Dict[str, Any], other: Dict[str, Any]
) -> bool:
    """Reject incompatible physical bindings for one stable candidate ID.

    A canonical evidence ID can legitimately be represented by the same
    excerpt on several pages, or by overlapping source spans.  It cannot,
    however, identify two unrelated page/span excerpts and still be resolved
    by editorial score.
    """
    candidate_pages, candidate_spans, candidate_texts = _candidate_provenance(candidate)
    other_pages, other_spans, other_texts = _candidate_provenance(other)
    if _candidates_have_concrete_physical_spans(candidate_spans, other_spans):
        return not _candidate_spans_are_compatible(candidate_spans, other_spans)
    shared_texts = candidate_texts.intersection(other_texts)
    if shared_texts and not candidate_spans and not other_spans:
        if not candidate_pages and not other_pages:
            return False
        if candidate_pages.intersection(other_pages):
            return False
    if _candidate_spans_are_compatible(candidate_spans, other_spans):
        return False

    pages_overlap = bool(candidate_pages.intersection(other_pages))
    candidate_has_physical_binding = bool(candidate_pages or candidate_spans)
    other_has_physical_binding = bool(other_pages or other_spans)
    if candidate_has_physical_binding and other_has_physical_binding:
        if pages_overlap:
            return bool(candidate_texts and other_texts)
        return True
    return bool(candidate_texts and other_texts)


def _candidate_provenance(
    insight: Dict[str, Any],
) -> tuple[set[int], List[Dict[str, Any]], set[str]]:
    pages = {
        page
        for page in insight.get("pages") or []
        if isinstance(page, int) and page > 0
    }
    spans = [
        span for span in (insight.get("evidence_spans") or []) if isinstance(span, dict)
    ]
    texts = {
        normalized
        for value in [insight.get("evidence")]
        + [span.get("text") or span.get("evidence") for span in spans]
        if (normalized := normalize_for_lookup(value))
    }
    for span in spans:
        page = span.get("page")
        if isinstance(page, int) and page > 0:
            pages.add(page)
    return pages, spans, texts


def _candidates_have_concrete_physical_spans(
    candidate_spans: List[Dict[str, Any]],
    other_spans: List[Dict[str, Any]],
) -> bool:
    def has_concrete_span(spans: List[Dict[str, Any]]) -> bool:
        return any(
            any(
                isinstance(span.get(field_name), int)
                and not isinstance(span.get(field_name), bool)
                for field_name in (
                    "page",
                    "start_offset",
                    "end_offset",
                    "start",
                    "end",
                    "char_start",
                    "char_end",
                    "line_start",
                    "line_end",
                )
            )
            for span in spans
        )

    return has_concrete_span(candidate_spans) and has_concrete_span(other_spans)


def _candidate_spans_are_compatible(
    candidate_spans: List[Dict[str, Any]],
    other_spans: List[Dict[str, Any]],
) -> bool:
    for candidate_span in candidate_spans:
        for other_span in other_spans:
            if (
                not _compatible_span_source(
                    candidate_span.get("source_pack"),
                    other_span.get("source_pack"),
                )
                or not _compatible_span_source(
                    candidate_span.get("section_id"),
                    other_span.get("section_id"),
                )
                or not _compatible_span_source(
                    candidate_span.get("source_identity"),
                    other_span.get("source_identity"),
                )
                or not _compatible_span_source(
                    candidate_span.get("source_id"),
                    other_span.get("source_id"),
                )
                or not _compatible_span_source(
                    candidate_span.get("evidence_id"),
                    other_span.get("evidence_id"),
                )
            ):
                continue
            candidate_text = normalize_for_lookup(
                candidate_span.get("text") or candidate_span.get("evidence")
            )
            other_text = normalize_for_lookup(
                other_span.get("text") or other_span.get("evidence")
            )
            candidate_page = candidate_span.get("page")
            other_page = other_span.get("page")
            if (
                isinstance(candidate_page, int)
                and not isinstance(candidate_page, bool)
                and isinstance(other_page, int)
                and not isinstance(other_page, bool)
            ):
                if candidate_page != other_page:
                    continue
                if _span_offsets_overlap(candidate_span, other_span):
                    return True
                if _span_offsets_are_concrete(candidate_span, other_span):
                    continue
            if candidate_text and other_text:
                if candidate_text == other_text:
                    return True
                continue
            if _span_locations_match(candidate_span, other_span):
                return True
    return False


def _span_offsets_are_concrete(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    return _span_offset_pair(left) is not None and _span_offset_pair(right) is not None


def _span_offset_pair(span: Dict[str, Any]) -> tuple[int, int] | None:
    for start_name, end_name in (
        ("start_offset", "end_offset"),
        ("char_start", "char_end"),
        ("start", "end"),
        ("line_start", "line_end"),
    ):
        start = span.get(start_name)
        end = span.get(end_name)
        if (
            isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
        ):
            return start, end
    return None


def _compatible_span_source(left: Any, right: Any) -> bool:
    left_value = normalize_for_lookup(left)
    right_value = normalize_for_lookup(right)
    return not left_value or not right_value or left_value == right_value


def _span_offsets_overlap(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    if not isinstance(left.get("page"), int) or not isinstance(right.get("page"), int):
        return False
    left_offsets = _span_offset_pair(left)
    right_offsets = _span_offset_pair(right)
    if left_offsets is None or right_offsets is None:
        return False
    left_start, left_end = left_offsets
    right_start, right_end = right_offsets
    return max(left_start, right_start) <= min(left_end, right_end)


def _span_locations_match(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    fields = ("source_pack", "section_id", "page", "start_offset", "end_offset")
    values = [
        normalize_for_lookup(left.get(field_name))
        if field_name in {"source_pack", "section_id"}
        else left.get(field_name)
        for field_name in fields
    ]
    other_values = [
        normalize_for_lookup(right.get(field_name))
        if field_name in {"source_pack", "section_id"}
        else right.get(field_name)
        for field_name in fields
    ]
    return values == other_values and any(value is not None for value in values)


def _complete_protected_metric_binding(
    metric: Any, *, preserve_unknown_fields: bool = False
) -> Dict[str, Any]:
    metric = metric if isinstance(metric, dict) else {}
    binding: Dict[str, Any] = deepcopy(metric) if preserve_unknown_fields else {}
    for field_name in PROTECTED_METRIC_FIELDS:
        if field_name == "observations":
            observations = metric.get(field_name)
            binding[field_name] = (
                deepcopy(observations) if isinstance(observations, list) else []
            )
        else:
            binding[field_name] = deepcopy(metric.get(field_name, ""))
    return binding


def _restore_candidate_factual_fields(
    insight: Dict[str, Any],
    candidate_facts: Dict[str, Dict[str, Any]],
    *,
    preserve_unknown_metric_fields: bool = False,
    allowed_evidence_ids: set[str] | None = None,
) -> Dict[str, Any]:
    """Deterministically revert final-stage factual drift to the candidate."""

    insight_id = _s(insight.get("id")).strip()
    candidate = candidate_facts.get(insight_id)
    if candidate is None:
        return insight
    restored = dict(insight)
    candidate_metric = candidate.get("metric")
    if isinstance(candidate_metric, dict):
        restored["metric"] = _complete_protected_metric_binding(
            candidate_metric,
            preserve_unknown_fields=preserve_unknown_metric_fields,
        )
    elif "metric" in restored:
        restored["metric"] = _complete_protected_metric_binding(
            None,
            preserve_unknown_fields=preserve_unknown_metric_fields,
        )
    for field_name in ("evidence_id", "evidence", "pages", "evidence_spans"):
        if field_name not in candidate and field_name not in restored:
            continue
        if field_name in {"evidence_id", "evidence"}:
            restored[field_name] = _s(candidate.get(field_name)).strip()
        else:
            restored[field_name] = deepcopy(candidate.get(field_name) or [])
    candidate_evidence_ids = _ordered_item_evidence_ids(candidate)
    if isinstance(insight.get("evidence_ids"), list):
        final_evidence_ids = _ordered_item_evidence_ids(insight)
        allowed = allowed_evidence_ids
        if allowed is None:
            allowed = set(candidate_evidence_ids)
        allowed_lookup = {normalize_for_lookup(value) for value in allowed}
        if (
            final_evidence_ids
            and candidate_evidence_ids
            and normalize_for_lookup(candidate_evidence_ids[0])
            == normalize_for_lookup(final_evidence_ids[0])
            and all(
                normalize_for_lookup(value) in allowed_lookup
                for value in final_evidence_ids
            )
        ):
            restored["evidence_ids"] = final_evidence_ids
        elif len(candidate_evidence_ids) > 1:
            restored["evidence_ids"] = candidate_evidence_ids
        else:
            restored.pop("evidence_ids", None)
    elif len(candidate_evidence_ids) > 1:
        restored["evidence_ids"] = candidate_evidence_ids
    return restored


def build_expert_synthesis_context(
    *,
    editorial_plan: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> Dict[str, Any]:
    """Build bounded direct-source input for Expert View synthesis."""
    plan = normalize_artifact_editorial_plan(editorial_plan)
    # DocMap selects retrieval targets; it cannot substantiate factual claims.
    span_index = _build_evidence_span_index(doc_map={}, evidence_packs=evidence_packs)
    source_findings = _expert_source_findings(evidence_packs)
    implications = _expert_insight_implications(
        insights_final,
        evidence_span_index=span_index,
        source_findings=source_findings,
    )
    implication_source_ids = {
        evidence_id.casefold()
        for item in implications
        if item.get("source_finding")
        for evidence_id in _ordered_item_evidence_ids(item)
    }
    themes: List[Dict[str, Any]] = []
    for theme in plan["themes"]:
        evidence = []
        for evidence_id in theme["evidence_ids"][:3]:
            spans = span_index.get(_s(evidence_id).casefold(), [])
            if not spans:
                continue
            span = spans[0]
            item: Dict[str, Any] = {
                "evidence_id": _s(span.get("evidence_id")),
                "source_pack": _s(span.get("source_pack")),
                "text": _s(span.get("text")),
            }
            source_page = span.get("page")
            if isinstance(source_page, int) and source_page > 0:
                item["page"] = source_page
            evidence_id = _s(span.get("evidence_id")).casefold()
            source_finding = source_findings.get(evidence_id, "")
            if source_finding and evidence_id not in implication_source_ids:
                item["source_finding"] = source_finding
            evidence.append(item)
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
        "insight_implications": implications,
        "limitations": _expert_context_items(
            evidence_packs.get("limitations"),
            item_key="limitations",
            text_keys=("description", "limitation", "text", "summary"),
        ),
        "counter_signals": _expert_counter_signals(insights_final, evidence_packs),
    }


def _expert_insight_implications(
    insights_final: List[Dict[str, Any]],
    *,
    evidence_span_index: Dict[str, List[Dict[str, Any]]],
    source_findings: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Keep insight claims adjacent to their independently retained source span."""

    metric_context_fields = (
        "label",
        "value",
        "unit",
        "subject",
        "cohort",
        "denominator",
        "timeframe",
        "geography",
        "segment",
        "sample_size",
        "observation_status",
        "forecast_status",
        "observations",
    )
    required_metric_fields = (
        "label",
        "value",
        "unit",
        "subject",
        "cohort",
        "denominator",
        "timeframe",
    )
    implications: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for insight in insights_final:
        if not isinstance(insight, dict):
            continue
        implication = _s(insight.get("so_what")).strip()
        if not implication:
            continue
        evidence_ids = _ordered_item_evidence_ids(insight)
        evidence_id = evidence_ids[0] if evidence_ids else ""
        supporting_evidence: list[dict[str, Any]] = []
        for bound_evidence_id in evidence_ids:
            source_finding = source_findings.get(bound_evidence_id.casefold(), "")
            source_span = next(
                (
                    span
                    for span in evidence_span_index.get(
                        bound_evidence_id.casefold(), []
                    )
                    if _s(span.get("text")).strip()
                    and _s(span.get("evidence_id")).casefold()
                    == bound_evidence_id.casefold()
                ),
                None,
            )
            if not source_finding and source_span is None:
                continue
            support: dict[str, Any] = {"evidence_id": bound_evidence_id}
            if source_finding:
                support["source_finding"] = source_finding
            if source_span is not None:
                support["source_excerpt"] = _s(source_span.get("text"))
                source_page = source_span.get("page")
                if isinstance(source_page, int) and source_page > 0:
                    support["source_page"] = source_page
            supporting_evidence.append(support)
        primary_support = next(
            (
                support
                for support in supporting_evidence
                if _s(support.get("evidence_id")).casefold() == evidence_id.casefold()
            ),
            {},
        )
        key = (
            ",".join(value.casefold() for value in evidence_ids),
            normalize_text(implication),
            normalize_text(_s(primary_support.get("source_finding"))),
        )
        if key in seen:
            continue
        seen.add(key)
        item: Dict[str, Any] = {"evidence_id": evidence_id}
        if len(evidence_ids) > 1:
            item["evidence_ids"] = evidence_ids
        if implication:
            item["so_what"] = implication
        if primary_support:
            item.update(
                {
                    key: primary_support[key]
                    for key in ("source_finding", "source_excerpt")
                    if key in primary_support
                }
            )
            if "source_page" in primary_support:
                item["source_page"] = primary_support["source_page"]
            metric = insight.get("metric")
            if isinstance(metric, dict):
                structured_metric: Dict[str, Any] = {}
                for field_name in metric_context_fields:
                    value = metric.get(field_name)
                    if field_name == "observations":
                        if isinstance(value, list) and value:
                            structured_metric[field_name] = deepcopy(value)
                    elif _s(value).strip():
                        structured_metric[field_name] = _s(value).strip()
                if all(
                    field_name in structured_metric
                    for field_name in required_metric_fields
                ):
                    item["metric"] = structured_metric
        if len(supporting_evidence) > 1:
            item["supporting_evidence"] = supporting_evidence
        implications.append(item)
        if len(implications) == 7:
            break
    return implications


def _expert_source_findings(evidence_packs: Dict[str, Any]) -> Dict[str, str]:
    """Index only unique findings-pack statements by their retained evidence ID."""

    findings_pack = evidence_packs.get("findings")
    findings = findings_pack.get("findings") if isinstance(findings_pack, dict) else []
    if not isinstance(findings, list):
        return {}
    by_id: Dict[str, set[str]] = {}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        evidence_id = _s(finding.get("id")).strip().casefold()
        text = _s(finding.get("text")).strip()
        if evidence_id and text:
            by_id.setdefault(evidence_id, set()).add(text)
    return {
        evidence_id: next(iter(texts))
        for evidence_id, texts in by_id.items()
        if len(texts) == 1
    }


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
    # A final-stage record owns its public wording.  Resolve stable-ID matches
    # before ranking so a higher-scored candidate cannot replace that wording.
    final_by_id: dict[str, tuple[int, Dict[str, Any]]] = {}
    final_without_id: list[tuple[int, Dict[str, Any]]] = []
    for source_order, item in enumerate(final_insights):
        if not isinstance(item, dict) or not _s(item.get("text")).strip():
            continue
        insight = dict(item)
        insight_id = _s(insight.get("id")).strip()
        if insight_id:
            final_by_id.setdefault(insight_id, (source_order, insight))
        else:
            final_without_id.append((source_order, insight))

    candidate_by_id: dict[str, tuple[int, Dict[str, Any]]] = {}
    candidate_alternatives_by_id: dict[str, list[tuple[int, Dict[str, Any]]]] = {}
    candidate_without_id: list[tuple[int, Dict[str, Any]]] = []
    candidate_offset = len(final_insights)
    candidate_groups: dict[str, list[tuple[int, Dict[str, Any]]]] = {}
    for index, item in enumerate(candidate_insights):
        if not isinstance(item, dict) or not _s(item.get("text")).strip():
            continue
        insight = dict(item)
        insight_id = _s(insight.get("id")).strip()
        source_order = candidate_offset + index
        if not insight_id:
            candidate_without_id.append((source_order, insight))
            continue
        candidate_groups.setdefault(insight_id, []).append((source_order, insight))

    for insight_id, group in candidate_groups.items():
        reliable = [item for item in group if _s(item[1].get("evidence_id")).strip()]
        if not reliable or _candidate_group_has_factual_conflict(
            [insight for _, insight in reliable]
        ):
            continue
        if insight_id in final_by_id:
            candidate_alternatives_by_id[insight_id] = sorted(
                reliable, key=_insight_rank_key
            )
        else:
            candidate_by_id[insight_id] = min(reliable, key=_insight_rank_key)

    ambiguous_final_texts = _resolve_duplicate_final_wording(
        final_by_id=final_by_id,
        final_without_id=final_without_id,
        candidate_alternatives_by_id=candidate_alternatives_by_id,
    )

    ordered_items = [
        *final_by_id.values(),
        *final_without_id,
        *candidate_by_id.values(),
        *candidate_without_id,
    ]
    ordered_items.sort(key=_insight_rank_key)
    ambiguous_public_texts = _ambiguous_public_duplicate_keys(ordered_items)
    ranked: List[tuple[int, Dict[str, Any]]] = []
    for source_order, insight in ordered_items:
        if not _s(insight.get("evidence_id")).strip():
            continue
        duplicate_key = _insight_duplicate_key(insight)
        if (
            duplicate_key in ambiguous_final_texts
            or duplicate_key in ambiguous_public_texts
        ):
            continue
        if any(
            _insights_semantically_equivalent(insight, retained)
            for _, retained in ranked
        ):
            continue
        ranked.append((source_order, dict(insight)))
    return ranked


def _ambiguous_public_duplicate_keys(
    items: list[tuple[int, Dict[str, Any]]],
) -> set[str]:
    """Return public-prose keys whose retained facts cannot be merged safely."""

    grouped: dict[str, list[Dict[str, Any]]] = {}
    for _source_order, insight in items:
        duplicate_key = _insight_duplicate_key(insight)
        if duplicate_key:
            grouped.setdefault(duplicate_key, []).append(insight)
    return {
        duplicate_key
        for duplicate_key, members in grouped.items()
        if len(members) > 1
        and len({_insight_metric_signature(member) for member in members}) > 1
    }


def _resolve_duplicate_final_wording(
    *,
    final_by_id: dict[str, tuple[int, Dict[str, Any]]],
    final_without_id: list[tuple[int, Dict[str, Any]]],
    candidate_alternatives_by_id: dict[str, list[tuple[int, Dict[str, Any]]]],
) -> set[str]:
    """Repair or abstain on duplicate final prose with different facts.

    A candidate alternative is usable only for its matching stable ID and only
    when every member of an ambiguous wording group has a distinct, bound
    alternative.  Otherwise the whole group is omitted instead of choosing one
    metric binding or publishing duplicate prose.
    """

    grouped: dict[str, list[tuple[int, Dict[str, Any]]]] = {}
    for item in [*final_by_id.values(), *final_without_id]:
        duplicate_key = _insight_duplicate_key(item[1])
        if duplicate_key:
            grouped.setdefault(duplicate_key, []).append(item)
    occupied_keys = set(grouped)
    ambiguous: set[str] = set()

    for duplicate_key, members in grouped.items():
        if len(members) < 2:
            continue
        if len({_insight_metric_signature(insight) for _, insight in members}) <= 1:
            continue

        replacements: list[tuple[str, Dict[str, Any]]] = []
        replacement_keys: set[str] = set()
        for _source_order, insight in members:
            insight_id = _s(insight.get("id")).strip()
            final_evidence_id = normalize_for_lookup(insight.get("evidence_id"))
            alternative = next(
                (
                    candidate
                    for _, candidate in candidate_alternatives_by_id.get(insight_id, [])
                    if _insight_duplicate_key(candidate)
                    and _insight_duplicate_key(candidate) != duplicate_key
                    and normalize_for_lookup(candidate.get("evidence_id"))
                    == final_evidence_id
                    and _insight_metric_signature(candidate)
                    == _insight_metric_signature(insight)
                ),
                None,
            )
            alternative_key = (
                _insight_duplicate_key(alternative) if alternative is not None else None
            )
            if (
                not insight_id
                or alternative is None
                or not alternative_key
                or alternative_key in replacement_keys
                or alternative_key in occupied_keys - {duplicate_key}
            ):
                replacements = []
                break
            replacement_keys.add(alternative_key)
            replacements.append((insight_id, alternative))

        if len(replacements) != len(members):
            ambiguous.add(duplicate_key)
            continue

        for _source_order, insight in members:
            insight_id = _s(insight.get("id")).strip()
            alternative = next(
                candidate
                for candidate_id, candidate in replacements
                if candidate_id == insight_id
            )
            replaced = dict(insight)
            replaced["text"] = _s(alternative.get("text")).strip()
            final_by_id[insight_id] = (_source_order, replaced)

    return ambiguous


def _best_ranked_insight(
    items: List[tuple[int, Dict[str, Any]]],
) -> tuple[int, Dict[str, Any]]:
    return min(items, key=_insight_rank_key)


def _insight_rank_key(item: tuple[int, Dict[str, Any]]) -> tuple[float, ...]:
    source_order, insight = item
    return (*_insight_quality_key(insight), source_order)


def _insight_quality_key(insight: Dict[str, Any]) -> tuple[float, ...]:
    """Return a deterministic quality tuple using only retained signals."""

    metric = insight.get("metric")
    metric = metric if isinstance(metric, dict) else {}
    evidence_id = _s(insight.get("evidence_id")).strip()
    evidence = _s(insight.get("evidence")).strip()
    pages = [
        page
        for page in insight.get("pages", [])
        if isinstance(page, int) and not isinstance(page, bool) and page > 0
    ]
    spans = insight.get("evidence_spans")
    page_bound_spans = (
        [
            span
            for span in spans
            if isinstance(span, dict)
            and isinstance(span.get("page"), int)
            and span["page"] > 0
            and _s(span.get("text")).strip()
        ]
        if isinstance(spans, list)
        else []
    )
    metric_label = _s(metric.get("label")).strip()
    metric_value = _s(metric.get("value")).strip()
    binding_count = sum(
        bool(_s(metric.get(field_name)).strip()) for field_name in METRIC_BINDING_FIELDS
    )
    relevance = _numeric_score(insight.get("decision_relevance_score"))
    metric_strength = _numeric_score(insight.get("metric_strength_score"))
    novelty = _numeric_score(insight.get("novelty_score"))
    score = _numeric_score(insight.get("score"))
    evidence_strength = (
        bool(evidence_id) * 4
        + bool(evidence) * 2
        + bool(pages) * 2
        + min(len(page_bound_spans), 2) * 2
        + bool(metric_label and metric_value) * 2
        + min(binding_count, len(METRIC_BINDING_FIELDS))
    )
    return (
        -float(evidence_strength),
        -relevance,
        -metric_strength,
        -novelty,
        -score,
    )


def _numeric_score(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _insight_metric_signature(insight: Dict[str, Any]) -> tuple[tuple[str, str], ...]:
    metric = insight.get("metric")
    if not isinstance(metric, dict):
        return ()
    return tuple(
        (field_name, normalize_for_lookup(metric.get(field_name)))
        for field_name in PROTECTED_METRIC_FIELDS
        if normalize_for_lookup(metric.get(field_name))
    )


def _insights_semantically_equivalent(
    left: Dict[str, Any], right: Dict[str, Any]
) -> bool:
    """Collapse only an explicitly identical public proposition and binding."""

    left_metric = _insight_metric_signature(left)
    right_metric = _insight_metric_signature(right)
    if left_metric != right_metric:
        return False
    left_proposition = normalize_for_lookup(left.get("text"))
    right_proposition = normalize_for_lookup(right.get("text"))
    # Evidence excerpts are source support, not propositions.  They are never
    # used to collapse differently worded claims.
    return bool(left_proposition and left_proposition == right_proposition)


def _append_distinct_insight(
    selected: List[Dict[str, Any]],
    selected_keys: set[str],
    insight: Dict[str, Any],
) -> None:
    duplicate_key = _insight_duplicate_key(insight)
    if duplicate_key and duplicate_key in selected_keys:
        return
    if any(
        _insights_semantically_equivalent(insight, retained) for retained in selected
    ):
        return
    if duplicate_key:
        selected_keys.add(duplicate_key)
    selected.append(insight)


def _fallback_evidence_key(value: Any) -> str:
    return normalize_text(value).removeprefix("evidence:findings:")


def _finding_section_ids(source_findings: Any) -> dict[str, set[str]]:
    """Index original finding IDs by their unambiguous source section."""

    raw_findings = (
        source_findings.get("findings")
        if isinstance(source_findings, dict)
        else source_findings
    )
    if isinstance(raw_findings, dict):
        raw_findings = raw_findings.get("findings")
    finding_sections: dict[str, set[str]] = {}
    if not isinstance(raw_findings, list):
        return finding_sections
    for finding in raw_findings:
        if not isinstance(finding, dict):
            continue
        finding_key = _fallback_evidence_key(finding.get("id"))
        if not finding_key:
            continue
        finding_sections.setdefault(finding_key, set())
        section_id = normalize_text(finding.get("section_id"))
        if section_id:
            finding_sections[finding_key].add(section_id)
    return finding_sections


def editorial_plan_theme_bindings(
    editorial_plan: Dict[str, Any] | None,
    *,
    source_findings: Any = None,
    eligible_finding_ids: set[str] | None = None,
) -> List[Dict[str, Any]]:
    """Resolve each plan theme to direct or unambiguous finding identities.

    The result is deliberately a small shared mapping contract used by both
    fallback selection and candidate coverage checks.  Section names remain
    navigation hints: they cover a candidate only through a finding that is
    explicitly linked to that section.
    """

    if not isinstance(editorial_plan, dict):
        return []
    finding_sections = _finding_section_ids(source_findings)
    finding_ids = set(finding_sections)
    bindings: List[Dict[str, Any]] = []
    for theme in editorial_plan.get("themes") or []:
        if not isinstance(theme, dict):
            continue
        reference_keys = {
            _fallback_evidence_key(evidence_id)
            for evidence_id in theme.get("evidence_ids") or []
            if _fallback_evidence_key(evidence_id)
        }
        direct_finding_ids = reference_keys & finding_ids
        section_finding_ids = {
            finding_id
            for finding_id, sections in finding_sections.items()
            if len(sections) == 1 and next(iter(sections)) in reference_keys
        }
        if eligible_finding_ids is not None:
            direct_finding_ids &= eligible_finding_ids
            section_finding_ids &= eligible_finding_ids
        coverage_keys = (
            (direct_finding_ids | section_finding_ids)
            if source_findings is not None
            else reference_keys
        )
        bindings.append(
            {
                "theme": _s(theme.get("theme")).strip(),
                "priority": theme.get("priority"),
                "reference_keys": reference_keys,
                "direct_finding_ids": direct_finding_ids,
                "section_finding_ids": section_finding_ids,
                "coverage_keys": coverage_keys,
            }
        )
    return bindings


def supported_fidelity_evidence_ids(evidence_fidelity: Any) -> set[str] | None:
    """Return canonical finding IDs that passed the existing fidelity gate."""

    results = (
        evidence_fidelity.get("results")
        if isinstance(evidence_fidelity, dict)
        else None
    )
    if not isinstance(results, list):
        return None
    return {
        claim_id.removeprefix("evidence:findings:").casefold()
        for result in results
        if isinstance(result, dict) and result.get("status") == "supported"
        for candidate in [result.get("candidate")]
        if isinstance(candidate, dict)
        for claim_id in [_s(candidate.get("claim_id")).strip()]
        if claim_id.startswith("evidence:findings:")
    }


def fallback_artifact_insights_from_findings(
    findings_pack: Any,
    *,
    limit: int = 5,
    editorial_plan: Dict[str, Any] | None = None,
    evidence_fidelity: Any = None,
    covered_evidence_ids: List[str] | None = None,
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
    fidelity_results = (
        evidence_fidelity.get("results")
        if isinstance(evidence_fidelity, dict)
        else findings_pack.get("evidence_fidelity", {}).get("results")
        if isinstance(findings_pack.get("evidence_fidelity"), dict)
        else None
    )
    fidelity_ids = supported_fidelity_evidence_ids(
        {"results": fidelity_results} if isinstance(fidelity_results, list) else None
    )
    finding_section_ids = _finding_section_ids(findings_pack)
    finding_sections = {
        finding_id: next(iter(sections)) if len(sections) == 1 else ""
        for finding_id, sections in finding_section_ids.items()
    }
    for finding in raw_findings:
        if not isinstance(finding, dict):
            continue
        finding_id = _fallback_evidence_key(finding.get("id"))
        if not finding_id:
            continue
        section_id = normalize_text(finding.get("section_id"))
        if finding_id not in finding_sections:
            finding_sections[finding_id] = section_id
        elif finding_sections[finding_id] != section_id:
            finding_sections[finding_id] = ""

    theme_priority: dict[str, int] = {}
    theme_evidence_ids: list[tuple[int, set[str], set[str], set[str]]] = []
    for binding in editorial_plan_theme_bindings(
        editorial_plan,
        source_findings=findings_pack,
        eligible_finding_ids=fidelity_ids,
    ):
        priority = binding["priority"]
        if not isinstance(priority, int):
            continue
        reference_keys = set(binding["reference_keys"])
        direct_keys = set(binding["direct_finding_ids"])
        section_candidate_ids = set(binding["section_finding_ids"])
        if reference_keys:
            theme_evidence_ids.append(
                (priority, reference_keys, direct_keys, section_candidate_ids)
            )
        for finding_id in direct_keys | section_candidate_ids:
            theme_priority[finding_id] = min(
                theme_priority.get(finding_id, priority),
                priority,
            )
    seen_evidence_ids: set[str] = set()
    ranked_findings: list[tuple[tuple[float, ...], int, str, str, Dict[str, Any]]] = []
    for source_order, finding in enumerate(raw_findings):
        if not isinstance(finding, dict):
            continue
        evidence_id = _s(finding.get("id"))
        text = _s(finding.get("text"))
        evidence = _s(finding.get("evidence"))
        pages = (
            [
                page
                for page in finding.get("pages", [])
                if isinstance(page, int) and not isinstance(page, bool) and page > 0
            ]
            if isinstance(finding.get("pages"), list)
            else []
        )
        if not evidence_id or not text or not evidence:
            continue
        if not pages:
            continue
        if fidelity_ids is not None and evidence_id.casefold() not in fidelity_ids:
            continue
        normalized_evidence_id = normalize_text(evidence_id)
        if normalized_evidence_id in seen_evidence_ids:
            continue
        seen_evidence_ids.add(normalized_evidence_id)
        confidence = normalize_text(finding.get("confidence"))
        confidence_rank = {"high": 3.0, "medium": 2.0, "low": 1.0}.get(confidence, 0.0)
        source_score = _numeric_score(finding.get("score"))
        theme_rank = theme_priority.get(normalized_evidence_id, 10_000)
        ranked_findings.append(
            (
                (
                    -confidence_rank,
                    -source_score,
                    float(theme_rank),
                    float(source_order),
                ),
                source_order,
                normalized_evidence_id,
                finding_sections.get(normalized_evidence_id, ""),
                {
                    "id": _s(finding.get("verified_fact_id")) or evidence_id,
                    "text": text,
                    "evidence_id": evidence_id,
                    "evidence": evidence,
                    "pages": pages,
                },
            )
        )
    ranked_findings.sort(key=lambda item: (item[0], item[1], item[4]["id"].casefold()))
    covered_keys = {
        _fallback_evidence_key(evidence_id)
        for evidence_id in covered_evidence_ids or []
        if _fallback_evidence_key(evidence_id)
    }
    selected_ranked: list[tuple[tuple[float, ...], int, str, str, Dict[str, Any]]] = []
    selected_ids: set[str] = set()
    selected_sections: dict[str, int] = {}
    for _, _, direct_ids, section_candidate_ids in sorted(theme_evidence_ids):
        if direct_ids & covered_keys or section_candidate_ids & covered_keys:
            continue
        theme_candidates = [
            item
            for item in ranked_findings
            if (
                item[2] in direct_ids
                if direct_ids
                else item[2] in section_candidate_ids
            )
            and item[2] not in selected_ids
            and item[2] not in covered_keys
        ]
        if not theme_candidates:
            continue
        chosen = min(theme_candidates, key=lambda item: (item[0], item[1]))
        selected_ranked.append(chosen)
        selected_ids.add(chosen[2])
        if chosen[3]:
            selected_sections[chosen[3]] = selected_sections.get(chosen[3], 0) + 1
        if len(selected_ranked) >= limit:
            break

    # Give each still-unrepresented source section one strong eligible finding
    # before the ranked fill.  Section metadata is used only as an existing
    # coverage signal; fidelity and finding quality remain the eligibility gate.
    for section_id in dict.fromkeys(item[3] for item in ranked_findings if item[3]):
        if len(selected_ranked) >= limit or section_id in selected_sections:
            continue
        section_candidates = [
            item
            for item in ranked_findings
            if item[3] == section_id
            and item[2] not in selected_ids
            and item[2] not in covered_keys
        ]
        if not section_candidates:
            continue
        chosen = min(section_candidates, key=lambda item: (item[0], item[1]))
        selected_ranked.append(chosen)
        selected_ids.add(chosen[2])
        selected_sections[section_id] = 1

    if len(selected_ranked) < limit:
        remaining = list(ranked_findings)
        while len(selected_ranked) < limit:
            available = [
                item
                for item in remaining
                if item[2] not in selected_ids and item[2] not in covered_keys
            ]
            if not available:
                break
            coverage_counts = {
                item[3] or "__unsectioned__": selected_sections.get(item[3], 0)
                for item in available
            }
            minimum_count = min(coverage_counts.values())
            balanced = [
                item
                for item in available
                if coverage_counts[item[3] or "__unsectioned__"] == minimum_count
            ]
            chosen = min(balanced, key=lambda item: (item[0], item[1]))
            selected_ranked.append(chosen)
            selected_ids.add(chosen[2])
            if chosen[3]:
                selected_sections[chosen[3]] = selected_sections.get(chosen[3], 0) + 1
    raw_candidates = [item[4] for item in selected_ranked]
    return normalize_artifact_insights(raw_candidates, prefix="finding")


def fallback_artifact_insights_from_evidence(
    findings_pack: Any,
    quote_candidates_pack: Any,
    *,
    limit: int = 5,
    editorial_plan: Dict[str, Any] | None = None,
    evidence_fidelity: Any = None,
    covered_evidence_ids: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """Build replacement candidates from fidelity-approved findings and quotes.

    Callers must pass the evidence packs after fidelity exclusion. Quotes are
    only used to fill a short findings pool, keeping replacement copy tied to
    an existing evidence identifier and a PDF-validated source excerpt.
    """
    if limit <= 0:
        return []
    candidates = fallback_artifact_insights_from_findings(
        findings_pack,
        limit=limit,
        editorial_plan=editorial_plan,
        evidence_fidelity=evidence_fidelity,
        covered_evidence_ids=covered_evidence_ids,
    )
    seen_evidence_ids = {
        normalize_text(_s(item.get("evidence_id")))
        for item in candidates
        if isinstance(item, dict)
    }
    raw_quotes = (
        quote_candidates_pack.get("quote_candidates")
        if isinstance(quote_candidates_pack, dict)
        else []
    )
    if not isinstance(raw_quotes, list):
        return candidates
    for quote in raw_quotes:
        if len(candidates) >= limit:
            break
        if not isinstance(quote, dict):
            continue
        evidence_id = _s(quote.get("id") or quote.get("evidence_id")).strip()
        text = _s(quote.get("text")).strip()
        normalized_id = normalize_text(evidence_id)
        if not evidence_id or not text or normalized_id in seen_evidence_ids:
            continue
        page = quote.get("page")
        candidates.append(
            {
                "id": evidence_id,
                "text": text,
                "evidence_id": evidence_id,
                "evidence": text,
                "pages": [page] if isinstance(page, int) and page > 0 else [],
            }
        )
        seen_evidence_ids.add(normalized_id)
    return normalize_artifact_insights(candidates, prefix="evidence")


def _insight_duplicate_key(item: Dict[str, Any]) -> str | None:
    text = normalize_text(_s(item.get("text")))
    return text or None


def canonical_artifact_quote_id(item: Any, *, occurrence_index: int = 0) -> str:
    """Return the stable source-slot identity for a normalized quote item."""
    if not isinstance(item, dict):
        return ""
    page_val = item.get("page")
    page = page_val if isinstance(page_val, int) else 0
    evidence_id = _s(item.get("evidence_id"))
    if type(occurrence_index) is not int or occurrence_index < 0:
        occurrence_index = 0
    return sha256_json(
        {
            "evidence_id": evidence_id,
            "page": page,
            "occurrence_index": occurrence_index,
        }
    )


def normalize_artifact_quotes(items: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    occurrence_counts: dict[tuple[str, int], int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        page_val = item.get("page")
        page = page_val if isinstance(page_val, int) else 0
        evidence_id = _s(item.get("evidence_id"))
        text = _s(item.get("text")).strip()
        evidence_spans = _normalize_evidence_spans(
            item.get("evidence_spans"), evidence_id=evidence_id
        )
        occurrence_key = (evidence_id, page)
        occurrence_index = occurrence_counts.get(occurrence_key, 0)
        occurrence_counts[occurrence_key] = occurrence_index + 1
        quote = {
            "id": canonical_artifact_quote_id(item, occurrence_index=occurrence_index),
            "text": text,
            "speaker": _s(item.get("speaker") or "Unknown"),
            "citation": _s(item.get("citation")),
            "page": page,
            "evidence_id": evidence_id,
            "evidence_spans": evidence_spans,
        }
        if item.get("is_paraphrase") is True or item.get("paraphrase") is True:
            quote["is_paraphrase"] = True
        for key in ("style", "mode", "label"):
            value = _s(item.get(key)).strip()
            if value:
                quote[key] = value
        normalized.append(quote)
    return normalized


def discard_location_only_quotes(items: Any) -> List[Dict[str, Any]]:
    """Keep quote records that name retained evidence, never page hints alone."""
    if not isinstance(items, list):
        return []
    sanitized: List[Dict[str, Any]] = []
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        evidence_id = _s(raw_item.get("evidence_id")).strip()
        if re.fullmatch(r"source:page:\d+", evidence_id, flags=re.IGNORECASE):
            continue
        item = dict(raw_item)
        spans = item.get("evidence_spans")
        if isinstance(spans, list):
            item["evidence_spans"] = [
                span
                for span in spans
                if not (
                    isinstance(span, dict)
                    and re.fullmatch(
                        r"source:page:\d+",
                        _s(span.get("evidence_id")).strip(),
                        flags=re.IGNORECASE,
                    )
                )
            ]
        sanitized.append(item)
    return sanitized


def discard_location_only_insights(items: Any) -> List[Dict[str, Any]]:
    """Keep insight records grounded in retained evidence, never page hints alone."""
    if not isinstance(items, list):
        return []
    sanitized: List[Dict[str, Any]] = []
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        evidence_id = _s(raw_item.get("evidence_id")).strip()
        if re.fullmatch(r"source:page:\d+", evidence_id, flags=re.IGNORECASE):
            continue
        item = dict(raw_item)
        spans = item.get("evidence_spans")
        if isinstance(spans, list):
            item["evidence_spans"] = [
                span
                for span in spans
                if not (
                    isinstance(span, dict)
                    and re.fullmatch(
                        r"source:page:\d+",
                        _s(span.get("evidence_id")).strip(),
                        flags=re.IGNORECASE,
                    )
                )
            ]
        sanitized.append(item)
    return sanitized


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
        text_key = unicodedata.normalize("NFC", text).casefold()
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
            unicodedata.normalize("NFC", section_id).casefold() if section_id else "",
            unicodedata.normalize(
                "NFC", display_title if display_title else section_title
            ).casefold(),
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
    editorial_plan: Dict[str, Any] | None = None,
    soft_copy_claim_provenance: Dict[str, Any] | None = None,
    context_anchors: Dict[str, str] | None = None,
) -> Dict[str, int]:
    known_ids, alias_to_id = _collect_known_evidence_ids(
        doc_map=doc_map, evidence_packs=evidence_packs
    )
    # The soft-copy context also exposes the insight and metric-spine anchors
    # whose rows each carry one retained evidence ID.  A model that cites such
    # an anchor is binding to that row's own retained evidence, so resolve the
    # anchor to it exactly as other retained aliases are resolved.  Retained
    # alias spellings always win over a context anchor.
    for anchor_alias, anchor_target in (context_anchors or {}).items():
        anchor_key = _s(anchor_alias).strip().lower()
        if (
            anchor_key
            and _s(anchor_target).strip() in known_ids
            and anchor_key not in alias_to_id
        ):
            alias_to_id[anchor_key] = _s(anchor_target).strip()
    normalized_count = 0
    unresolved_count = 0
    checked_count = 0

    def _normalize_reference(item: Any, *, preserve_missing: bool = False) -> None:
        nonlocal normalized_count, unresolved_count, checked_count
        if not isinstance(item, dict):
            return
        if preserve_missing and "evidence_id" not in item:
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

    def _normalize_item(item: Any) -> None:
        _normalize_reference(item)
        if not isinstance(item, dict):
            return
        if isinstance(item.get("evidence_ids"), list):
            normalized_ids = _normalize_evidence_ids(item.get("evidence_ids"))
            primary_evidence_id = _s(item.get("evidence_id")).strip()
            item["evidence_ids"] = list(
                dict.fromkeys(
                    [primary_evidence_id, *normalized_ids]
                    if primary_evidence_id
                    else normalized_ids
                )
            )
        parent_evidence_id = _s(item.get("evidence_id")).strip()
        spans = item.get("evidence_spans")
        if isinstance(spans, list):
            for span in spans:
                _normalize_span(span, parent_evidence_id=parent_evidence_id)

    def _normalize_span(span: Any, *, parent_evidence_id: str = "") -> None:
        nonlocal normalized_count, unresolved_count
        if not isinstance(span, dict) or "evidence_id" not in span:
            return
        original = _s(span.get("evidence_id")).strip()
        _normalize_reference(span, preserve_missing=True)
        # A source-page label is location provenance, not an independent
        # evidence identity.  When the containing artifact has already
        # resolved one retained evidence ID, preserve the page/source metadata
        # while binding that location to its proven canonical parent.
        if (
            parent_evidence_id in known_ids
            and span.get("evidence_id") == original
            and re.fullmatch(r"source:page:\d+", original, flags=re.IGNORECASE)
        ):
            span["evidence_id"] = parent_evidence_id
            normalized_count += 1
            unresolved_count -= 1

    def _normalize_evidence_ids(evidence_ids: Any) -> List[str]:
        if not isinstance(evidence_ids, list):
            return []
        normalized_ids: List[str] = []
        for evidence_id in evidence_ids:
            reference = {"evidence_id": evidence_id}
            _normalize_reference(reference)
            normalized_ids.append(_s(reference.get("evidence_id")).strip())
        return normalized_ids

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
    if isinstance(editorial_plan, dict):
        themes = editorial_plan.get("themes")
        if isinstance(themes, list):
            for theme in themes:
                if not isinstance(theme, dict):
                    continue
                evidence_ids = theme.get("evidence_ids")
                if not isinstance(evidence_ids, list):
                    continue
                theme["evidence_ids"] = _normalize_evidence_ids(evidence_ids)
    if isinstance(soft_copy_claim_provenance, dict):
        claims = soft_copy_claim_provenance.get("claims")
        if isinstance(claims, list):
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                evidence_ids = claim.get("evidence_ids")
                if isinstance(evidence_ids, list):
                    claim["evidence_ids"] = _normalize_evidence_ids(evidence_ids)
                canonical_evidence_ids = {
                    _s(evidence_id).strip()
                    for evidence_id in claim.get("evidence_ids") or []
                    if _s(evidence_id).strip() in known_ids
                }
                parent_evidence_id = (
                    next(iter(canonical_evidence_ids))
                    if len(canonical_evidence_ids) == 1
                    else ""
                )
                source_spans = claim.get("source_spans")
                if isinstance(source_spans, list):
                    for span in source_spans:
                        _normalize_span(span, parent_evidence_id=parent_evidence_id)

    return {
        "known_reference_count": len(known_ids),
        "checked_count": checked_count,
        "normalized_count": normalized_count,
        "unresolved_count": unresolved_count,
    }


def soft_copy_context_evidence_anchors(
    *,
    insights_final: Any,
    metric_spine: Any,
) -> Dict[str, str]:
    """Map context-exposed insight/metric anchors to their retained evidence ID.

    The summary, expert-comment, and LinkedIn prompts receive the final
    insights and the derived metric spine as supporting context.  Each row
    carries exactly one retained ``evidence_id`` beside its public identifier,
    so citing the row identifier is a resolvable alias for that retained
    evidence, not a new evidence system.  Anchors without a retained evidence
    ID are skipped so unknown references still fail validation.
    """

    anchors: Dict[str, str] = {}

    def _register(alias: Any, target: Any) -> None:
        alias_key = _s(alias).strip()
        target_id = _s(target).strip()
        if alias_key and target_id:
            anchors.setdefault(alias_key, target_id)

    for insight in insights_final if isinstance(insights_final, list) else []:
        if isinstance(insight, dict):
            _register(insight.get("id"), insight.get("evidence_id"))
    for metric in metric_spine if isinstance(metric_spine, list) else []:
        if isinstance(metric, dict):
            _register(metric.get("metric_id"), metric.get("evidence_id"))
    return anchors


def bind_artifact_evidence_spans(
    *,
    summary: Dict[str, Any],
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> Dict[str, int]:
    _rebind_numeric_summary_claims_to_unique_findings(
        summary=summary,
        doc_map=doc_map,
        evidence_packs=evidence_packs,
    )
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
        evidence_ids = _ordered_item_evidence_ids(item)
        evidence_id = evidence_ids[0] if evidence_ids else ""
        if not evidence_id:
            item["evidence_spans"] = []
            return
        existing = _normalize_evidence_spans(
            item.get("evidence_spans"), evidence_id=evidence_id
        )
        derived: List[Dict[str, Any]] = []
        for bound_evidence_id in evidence_ids:
            derived.extend(
                dict(span) for span in span_index.get(bound_evidence_id.casefold(), [])
            )
        derived = _normalize_evidence_spans(derived, evidence_id=evidence_id)
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
                source_bound = [
                    span
                    for span in derived
                    if span.get("source_pack")
                    in {"findings", "findings_statement", "quote_candidates"}
                ]
                canonical_spans = source_bound or derived
                canonical_evidence = " ".join(
                    dict.fromkeys(
                        _s(span.get("text")).strip()
                        for span in canonical_spans
                        if _s(span.get("text")).strip()
                    )
                )
                if source_bound and canonical_evidence:
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


_SUMMARY_CLAIM_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "was",
    "were",
    "while",
    "with",
    "year",
    "yoy",
}


def _rebind_numeric_summary_claims_to_unique_findings(
    *,
    summary: Dict[str, Any],
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> None:
    """Replace broad section references only when one direct finding fits.

    The check is deliberately exacting: the source must be a page-backed
    retained finding, every claimed quantity must match, and every meaningful
    claim token must occur in its text. Ambiguous matches keep their current
    reference for the regular grounding gate to assess.
    """

    sections = doc_map.get("sections") if isinstance(doc_map, dict) else None
    doc_map_ids = {
        _s(section.get("id")).strip()
        for section in sections or []
        if isinstance(section, dict) and _s(section.get("id")).strip()
    }
    claims = summary.get("claim_evidence_map")
    pack = evidence_packs.get("findings") if isinstance(evidence_packs, dict) else None
    findings = pack.get("findings") if isinstance(pack, dict) else None
    if (
        not doc_map_ids
        or not isinstance(claims, list)
        or not isinstance(findings, list)
    ):
        return

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        if _s(claim.get("evidence_id")).strip() not in doc_map_ids:
            continue
        claim_text = _s(claim.get("claim")).strip()
        claim_quantities = extract_quantities(claim_text)
        claim_tokens = _summary_claim_content_tokens(claim_text)
        if not claim_quantities or not claim_tokens:
            continue

        matching_ids: set[str] = set()
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            finding_id = _s(finding.get("id") or finding.get("evidence_id")).strip()
            finding_pages = _coerce_span_pages(finding)
            finding_text = " ".join(
                _s(finding.get(field_name)).strip()
                for field_name in ("text", "evidence", "statement")
                if _s(finding.get(field_name)).strip()
            )
            if not finding_id or not finding_pages or not finding_text:
                continue
            if not claim_tokens.issubset(_summary_claim_content_tokens(finding_text)):
                continue
            if not _summary_claim_quantities_match(claim_quantities, finding_text):
                continue
            matching_ids.add(finding_id)

        if len(matching_ids) == 1:
            claim["evidence_id"] = next(iter(matching_ids))


def _summary_claim_content_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z]+", normalize_for_lookup(text))
        if token not in _SUMMARY_CLAIM_STOP_WORDS
    }


def _summary_claim_quantities_match(
    claim_quantities: list[Quantity], evidence_text: str
) -> bool:
    evidence_quantities = extract_quantities(evidence_text)
    return all(
        any(
            not (
                claim.comparator in {"eq", "approx"}
                and evidence.comparator in {"gt", "gte", "lt", "lte"}
            )
            and quantities_match(claim, evidence)
            for evidence in evidence_quantities
        )
        for claim in claim_quantities
    )


def artifact_evidence_span_index(
    *, doc_map: Dict[str, Any], evidence_packs: Dict[str, Any]
) -> Dict[str, List[Dict[str, Any]]]:
    """Expose canonical evidence spans for retained private provenance."""

    return _build_evidence_span_index(
        doc_map=doc_map,
        evidence_packs=evidence_packs,
    )


def page_bound_direct_evidence_packs(
    evidence_packs: Dict[str, Any],
) -> Dict[str, Any]:
    """Keep only findings and quotes with canonical direct source pages."""

    direct_packs = {
        name: evidence_packs[name]
        for name in ("findings", "quote_candidates")
        if isinstance(evidence_packs.get(name), dict)
    }
    span_index = artifact_evidence_span_index(doc_map={}, evidence_packs=direct_packs)
    eligible_ids = {
        evidence_id
        for evidence_id, spans in span_index.items()
        if any(
            span.get("source_pack") in {"findings", "quote_candidates"}
            and isinstance(span.get("page"), int)
            and span["page"] > 0
            and _s(span.get("text")).strip()
            for span in spans
        )
    }
    filtered: Dict[str, Any] = {}
    for name, root_key in (
        ("findings", "findings"),
        ("quote_candidates", "quote_candidates"),
    ):
        payload = direct_packs.get(name)
        entries = payload.get(root_key) if isinstance(payload, dict) else None
        if isinstance(payload, dict) and isinstance(entries, list):
            filtered[name] = {
                **payload,
                root_key: [
                    entry
                    for entry in entries
                    if isinstance(entry, dict)
                    and _s(entry.get("id") or entry.get("evidence_id"))
                    .strip()
                    .casefold()
                    in eligible_ids
                ],
            }
    return filtered


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


def fallback_artifact_quotes_from_candidates(
    quote_candidates_pack: Any, *, limit: int = 3
) -> List[Dict[str, Any]]:
    """Reuse retained verbatim quote candidates when quote selection abstains."""
    if limit <= 0:
        return []
    candidates = (
        quote_candidates_pack.get("quote_candidates")
        if isinstance(quote_candidates_pack, dict)
        else quote_candidates_pack
        if isinstance(quote_candidates_pack, list)
        else []
    )
    if not isinstance(candidates, list):
        return []
    fallback: list[dict[str, Any]] = []
    for candidate in candidates:
        if len(fallback) >= limit or not isinstance(candidate, dict):
            continue
        evidence_id = _s(candidate.get("id") or candidate.get("evidence_id")).strip()
        text = _s(candidate.get("text")).strip()
        if not evidence_id or not text:
            continue
        page = candidate.get("page")
        fallback.append(
            {
                "text": text,
                "speaker": "Unknown",
                "citation": _s(candidate.get("source")).strip(),
                "page": page if isinstance(page, int) and page > 0 else 0,
                "evidence_id": evidence_id,
            }
        )
    return normalize_artifact_quotes(fallback)


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
                "claim": _normalize_public_numeric_signs(_s(item.get("claim"))),
                "evidence_id": evidence_id,
                "evidence": _normalize_public_numeric_signs(_s(item.get("evidence"))),
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


_DOUBLE_NUMERIC_SIGN_RE = re.compile(r"([\u2212-])\s*[\u2212-](?=\s*\d)")


def _normalize_public_numeric_signs(text: str) -> str:
    """Collapse OCR/model double signs without changing a valid range."""

    return _DOUBLE_NUMERIC_SIGN_RE.sub(r"\1", text)


def _collect_known_evidence_ids(
    *,
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> tuple[set[str], Dict[str, str]]:
    known_ids: set[str] = set()
    alias_candidates: dict[str, set[str]] = {}
    indexed_ids: list[tuple[str, int, str]] = []

    def _register(value: Any) -> None:
        evidence_id = _s(value).strip()
        if not evidence_id:
            return
        known_ids.add(evidence_id)

    def _add_alias(alias: str, evidence_id: str) -> None:
        alias_candidates.setdefault(alias.lower(), set()).add(evidence_id)

    def _register_separator_aliases(evidence_id: str) -> None:
        _add_alias(evidence_id, evidence_id)
        # Extraction families have historically used both separators.  Register
        # only the equivalent spelling of a retained canonical ID, so this
        # remains a lookup proof rather than a permissive rewrite of unknown
        # model references.
        _add_alias(evidence_id.replace("-", "_"), evidence_id)
        _add_alias(evidence_id.replace("_", "-"), evidence_id)

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
                            indexed_ids.append(("quote", idx, quote_id))
                        if item_key == "findings" and quote_id:
                            # Some retained reports use opaque finding IDs
                            # (for example ``f1`` or ``methodology-1``), while
                            # prompts present their ordered evidence as
                            # ``Finding 1``.  Mirror the established quote
                            # index aliases, but resolve only to this retained
                            # finding's canonical ID.
                            indexed_ids.append(("finding", idx, quote_id))

    if isinstance(doc_map, dict):
        for section in doc_map.get("sections") or []:
            if isinstance(section, dict):
                _register(section.get("id"))

    for evidence_id in known_ids:
        _register_separator_aliases(evidence_id)
    for kind, index, evidence_id in indexed_ids:
        for separator in ("_", "-", "", " "):
            _add_alias(f"{kind}{separator}{index}", evidence_id)

    canonical_ids_by_lower = {evidence_id.lower() for evidence_id in known_ids}
    numeric_ids: dict[tuple[str, int], list[str]] = {}
    for evidence_id in known_ids:
        numeric_suffix = re.fullmatch(r"(.+?)(\d+)", evidence_id)
        if not numeric_suffix:
            continue
        prefix, numeric_index = numeric_suffix.groups()
        normalized_prefix = prefix.rstrip("-_ ").lower()
        if normalized_prefix:
            numeric_ids.setdefault((normalized_prefix, int(numeric_index)), []).append(
                evidence_id
            )
    for (prefix, index), evidence_ids in numeric_ids.items():
        # Only one retained canonical ID may prove a compact/unpadded form.
        # Distinct canonical spellings remain distinct, even if their numeric
        # suffix and separator-normalized prefixes otherwise match.
        if len(evidence_ids) != 1:
            continue
        evidence_id = evidence_ids[0]
        for separator in ("", "-", "_", " "):
            alias = f"{prefix}{separator}{index}"
            if alias not in canonical_ids_by_lower:
                _add_alias(alias, evidence_id)

    for evidence_id in list(known_ids):
        match = re.match(r"^q(\d+)$", evidence_id, flags=re.IGNORECASE)
        if not match:
            continue
        quote_num = match.group(1)
        _add_alias(f"quote_{quote_num}", evidence_id)
        _add_alias(f"quote-{quote_num}", evidence_id)
        _add_alias(f"quote{quote_num}", evidence_id)

    return (
        known_ids,
        {
            alias: next(iter(candidates))
            for alias, candidates in alias_candidates.items()
            if len(candidates) == 1
        },
    )


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
    # Model prompts display evidence in a namespaced provenance form (for
    # example ``evidence:quote_candidates:quote_001``).  Retain that form for
    # audit, but offer its terminal identifier as a candidate only when the
    # canonical lookup below proves it exists.  This deliberately does not
    # turn arbitrary source/page strings into evidence.
    if ":" in raw:
        candidates.append(raw.rsplit(":", 1)[-1])

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
        # An explicit retained ID is authoritative even when a separator
        # alias for a different retained ID would otherwise collide.
        if candidate in known_ids:
            return candidate
        canonical = alias_to_id.get(candidate.lower())
        if canonical:
            return canonical
        quote_alias = QUOTE_ALIAS_RE.match(candidate)
        if quote_alias:
            alias_candidate = f"quote_{int(quote_alias.group(1))}"
            canonical = alias_to_id.get(alias_candidate)
            if canonical:
                return canonical
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
            fidelity = evidence_packs.get("evidence_fidelity")
            supported_findings: dict[str, tuple[str, set[int]]] = {}
            ambiguous_findings: set[str] = set()
            fidelity_results = (
                fidelity.get("results") if isinstance(fidelity, dict) else None
            )
            for result in (
                fidelity_results if isinstance(fidelity_results, list) else []
            ):
                if not isinstance(result, dict) or result.get("status") != "supported":
                    continue
                candidate = result.get("candidate")
                if not isinstance(candidate, dict):
                    continue
                claim_id = _s(candidate.get("claim_id"))
                prefix = "evidence:findings:"
                if not claim_id.startswith(prefix):
                    continue
                validated_finding_id = claim_id.removeprefix(prefix)
                statement = _s(candidate.get("text")).strip()
                references = candidate.get("evidence_references")
                source_pages: set[int] = set()
                if isinstance(references, list):
                    for reference in references:
                        if (
                            not isinstance(reference, dict)
                            or reference.get("source_pack") != "source_pdf"
                        ):
                            continue
                        page = reference.get("page")
                        if isinstance(page, int) and page > 0:
                            source_pages.add(page)
                if not validated_finding_id or not statement or not source_pages:
                    continue
                binding = (statement, source_pages)
                if (
                    validated_finding_id in supported_findings
                    and supported_findings[validated_finding_id] != binding
                ):
                    supported_findings.pop(validated_finding_id, None)
                    ambiguous_findings.add(validated_finding_id)
                elif validated_finding_id not in ambiguous_findings:
                    supported_findings[validated_finding_id] = binding
            family_status = findings_pack.get("family_status")
            findings_validated = (
                isinstance(family_status, dict)
                and family_status.get("status") == "generated"
                and family_status.get("policy_action") == "keep"
            )
            family_source = (
                _s(family_status.get("source")).strip()
                if isinstance(family_status, dict)
                else ""
            )
            finding_source_pack = (
                "verified_facts" if family_source == "verified_facts" else "findings"
            )
            for item in findings_pack.get("findings") or []:
                if not isinstance(item, dict):
                    continue
                finding_id = _s(item.get("id") or item.get("evidence_id")).strip()
                pages = _coerce_span_pages(item)
                excerpt = _pick_first_non_empty_text(
                    item.get("evidence"), item.get("excerpt")
                )
                if not finding_id or not excerpt:
                    # A generated finding sentence without its retained source
                    # excerpt is not evidence for a downstream artifact.
                    continue
                _register(
                    evidence_id=finding_id,
                    source_pack=finding_source_pack,
                    pages=pages,
                    text=excerpt,
                )
                statement = _pick_first_non_empty_text(
                    item.get("text"), item.get("statement")
                )
                validated_statement, validated_pages = supported_findings.get(
                    _s(finding_id), ("", set())
                )
                if (
                    findings_validated
                    and statement
                    and statement == validated_statement
                    and pages
                    and set(pages).issubset(validated_pages)
                ):
                    _register(
                        evidence_id=finding_id,
                        source_pack=(
                            "verified_facts"
                            if finding_source_pack == "verified_facts"
                            else "findings_statement"
                        ),
                        pages=pages,
                        text=statement,
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
            key_points = section.get("key_points")
            direct_key_points = (
                [_s(point).strip() for point in key_points if _s(point).strip()]
                if isinstance(key_points, list)
                else []
            )
            _register(
                evidence_id=section.get("id"),
                source_pack="doc_map",
                pages=_coerce_span_pages(section),
                text=" ".join(
                    dict.fromkeys(
                        value
                        for value in (
                            _s(section.get("summary")).strip(),
                            *direct_key_points,
                        )
                        if value
                    )
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
