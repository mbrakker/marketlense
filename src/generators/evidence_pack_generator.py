from __future__ import annotations

import json
import logging
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
from hashlib import sha256
from typing import Dict, Optional, Tuple

from src.contracts.analysis_family import AnalysisFamilyStatus
from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIFileSearchResult
from src.contracts.prompt_family_materialization import (
    PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
    PromptFamilyMaterializationRequest,
    PromptFamilyReuseRequest,
)
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.semantic_ids import ReportId
from src.contracts.structured_output import StructuredOutputExecutionRequest
from src.generators.analysis_pack_cache import (
    CachedPackAdaptResult,
    load_cached_pack,
)
from src.generators.analysis_store_adapter import (
    resolve_pack_path as resolve_analysis_pack_path,
)
from src.generators.analysis_store_adapter import (
    store_pack as store_analysis_pack,
)
from src.generators.claim_validation_generator import (
    _evidence_fidelity_candidates,
    _has_printed_page_label,
    _source_index,
    exclude_untrusted_evidence,
    validate_evidence_fidelity,
)
from src.generators.evidence_packs.base import EvidencePackStrategy
from src.generators.evidence_packs.doc_map_strategy import (
    normalize_payload as normalize_doc_map_payload,
)
from src.generators.evidence_packs.doc_map_strategy import (
    summarize_completeness as summarize_doc_map_completeness,
)
from src.generators.evidence_packs.doc_map_strategy import (
    summarize_payload as summarize_doc_map,
)
from src.generators.evidence_packs.registry import (
    DEFAULT_PACK_REGISTRY,
    PACK_STRATEGIES,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.public_editorial_quality_generator import (
    _metric_label_relationship_explanation,
)
from src.generators.structured_output_execution import (
    invoke_structured_output_model,
    recovery_prompt_bundle,
)
from src.generators.structured_output_execution import (
    shared_retrieval_context_json as serialize_shared_retrieval_context,
)
from src.generators.validation.relationships import period_time_pairs
from src.generators.validation.semantic import run_semantic_validation
from src.services import file_service, prompt_service, report_analysis_store_service
from src.services.prompt_family_materialization_service import (
    materialize_prompt_family,
    read_reusable_prompt_family,
)
from src.services.schema_validator_service import (
    provider_output_schema,
    validate_schema,
)
from src.services.structured_output_service import execute_structured_output
from src.utils.analysis_family import serialize_family_status
from src.utils.cache_utils import sha256_json
from src.utils.coercion import coerce_int
from src.utils.errors import AppError
from src.utils.json_recovery import parse_json_from_text, strip_json_fence
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.model_client_contract import require_injected_model_client
from src.utils.quantity import Quantity, extract_quantities, quantities_match
from src.utils.structured_output import StructuredOutputFailure

logger = logging.getLogger("market_lense.evidence_pack_generator")

_OPTIONAL_EVIDENCE_PACKS = {
    "scope",
    "methods",
    "findings",
    "limitations",
    "quote_candidates",
}

_MAX_FINDINGS_RETRIEVAL_TARGETS = 8
_MAX_FINDINGS_FALLBACK_TARGETS = 2
_MAX_FINDINGS_TARGET_KEY_POINTS = 3
_MAX_FINDINGS_TARGET_SOURCE_PAGES = 12
_MAX_FINDINGS_TARGET_SOURCE_PAGE_CHARS = 5000
_MAX_FINDINGS_TARGET_SOURCE_CHARS = 32000
_FINDINGS_TARGET_METADATA_TITLE = re.compile(
    r"\b(?:about the research|research methodology|survey methodology|"
    r"methodology|respondent profiles?|survey scope|foreword|authors?|"
    r"acknowledg(?:e)?ments?|references|contents|"
    r"about the author|who should read(?: this report)?|"
    r"about this report)\b",
    re.IGNORECASE,
)
_FINDINGS_TARGET_OVERVIEW_TITLE = re.compile(
    r"\b(?:executive summary|introduction|drivers? shaping|"
    r"retrospective and .* outlook|outlook overview|report overview|"
    r"key takeaways)\b",
    re.IGNORECASE,
)
_FINDINGS_TARGET_COMPARISON = re.compile(
    r"\b(?:versus|vs\.?|compared with|compared to|while|whereas|"
    r"higher|lower|outpac(?:e|es|ed|ing)|differ(?:s|ed|ence|ences)?)\b",
    re.IGNORECASE,
)
_FINDINGS_TARGET_RESULT = re.compile(
    r"\b(?:grew|growth|increas(?:e|es|ed|ing)|rose|rising|declin(?:e|es|ed|ing)|"
    r"decreas(?:e|es|ed|ing)|fell|falling|drop(?:s|ped|ping)?|down|up|"
    r"accounts? for|positions?|positioned|positioning|represents?|reached|"
    r"reaches|forecast|project(?:s|ed|ion))\b",
    re.IGNORECASE,
)
_FINDINGS_TARGET_NEGATIVE_DIRECTION = re.compile(
    r"\b(?:declin(?:e|es|ed|ing)|decreas(?:e|s|ed|ing)|fell|falling|"
    r"drop(?:s|ped|ping)?|down|lost|loss)\b",
    re.IGNORECASE,
)
_FINDINGS_TARGET_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "between",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "that",
        "this",
        "to",
        "was",
        "were",
        "while",
        "with",
    }
)
_FINDINGS_TARGET_NUMBER = re.compile(
    r"(?<![\w\d])[+\-−]?\s*"
    r"(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"\s*(?P<unit>%|percent(?:age points?)?|pp|[kmbtn]|"
    r"thousand|million|billion|trillion|[eE])?(?![\w&])",
    re.IGNORECASE,
)
_FINDINGS_TARGET_QUALIFIERS = (
    ("approximate", ("approximately", "approx.", "around", "about", "roughly", "~")),
    ("at_least", ("at least", "more than", "over")),
    ("at_most", ("at most", "less than", "under")),
)
_FINDINGS_TARGET_YEAR_RANGE = re.compile(
    r"\b(?P<start>(?:19|20)\d{2})\s*[-–—−\uFFFD]\s*"
    r"(?P<end>(?:19|20)\d{2})\b"
)


def _findings_target_number_markers(value: str) -> set[str]:
    markers: set[str] = set()
    normalized = re.sub(
        r"\b(?:fig(?:ure)?|chart|table)\s*[A-Z]?\s*\d+\b",
        " ",
        value,
        flags=re.IGNORECASE,
    ).replace("−", "-")
    for match in _FINDINGS_TARGET_NUMBER.finditer(normalized):
        raw = match.group(0).strip().replace(",", "")
        sign = "-" if raw.startswith("-") else ""
        number = match.group("number").replace(",", "")
        unit = str(match.group("unit") or "").strip().casefold()
        unit = {
            "percent": "%",
            "percentage point": "pp",
            "percentage points": "pp",
            "thousand": "k",
            "million": "m",
            "billion": "b",
            "trillion": "t",
        }.get(unit, unit)
        markers.add(f"{sign}{number}{unit}")
    return markers


def _findings_target_number_occurrences(
    value: str, *, include_years: bool = False
) -> list[str]:
    normalized = _FINDINGS_TARGET_YEAR_RANGE.sub(
        r"\g<start> to \g<end>", value.replace("−", "-")
    )
    occurrences: list[str] = []
    for match in _FINDINGS_TARGET_NUMBER.finditer(normalized):
        number = match.group("number").replace(",", "")
        unit = str(match.group("unit") or "").strip().casefold()
        unit = {
            "percent": "%",
            "percentage point": "pp",
            "percentage points": "pp",
            "thousand": "k",
            "million": "m",
            "billion": "b",
            "trillion": "t",
        }.get(unit, unit)
        is_year = unit in {"", "e"} and number.isdigit() and 1900 <= int(number) <= 2100
        if is_year and not include_years:
            continue
        preceding_text = normalized[max(0, match.start() - 100) : match.start()]
        preceding_text = re.split(r"[;.!?\n]", preceding_text)[-1]
        is_negative = match.group(0).strip().startswith("-") or (
            not match.group(0).strip().startswith("+")
            and bool(_FINDINGS_TARGET_NEGATIVE_DIRECTION.search(preceding_text))
        )
        occurrences.append(f"{'-' if is_negative else ''}{number}{unit}")
    return occurrences


def _findings_target_score(value: str, title: str = "") -> float:
    number_count = len(set(_findings_target_number_occurrences(value)))
    comparison_score = min(len(_FINDINGS_TARGET_COMPARISON.findall(value)), 2) * 1.5
    result_score = min(len(_FINDINGS_TARGET_RESULT.findall(value)), 2) * 0.5
    content_words = {
        word
        for word in re.findall(r"[a-z]{3,}", f"{title} {value}".casefold())
        if word not in _FINDINGS_TARGET_STOP_WORDS
    }
    information_score = min(len(content_words), 12) * 0.08
    score = (
        1.0
        + min(number_count, 12) * 1.25
        + comparison_score
        + result_score
        + information_score
    )
    return score * (0.5 if _FINDINGS_TARGET_OVERVIEW_TITLE.search(title) else 1.0)


def _findings_target_key_points(target: dict[str, object]) -> list[str]:
    def normalize_year_ranges(points: list[str]) -> list[str]:
        return [
            _FINDINGS_TARGET_YEAR_RANGE.sub(r"\g<start> to \g<end>", point)
            for point in points
        ]

    raw_points = target.get("key_points")
    if isinstance(raw_points, list):
        points = [str(point).strip() for point in raw_points if str(point).strip()]
        if points:
            return normalize_year_ranges(points)
    point = str(target.get("key_point") or "").strip()
    return normalize_year_ranges([point]) if point else []


def _findings_target_pages(target: dict[str, object]) -> list[int]:
    raw_pages = target.get("pages")
    if not isinstance(raw_pages, list):
        return []
    return [
        page
        for page in raw_pages
        if isinstance(page, int) and not isinstance(page, bool) and page > 0
    ]


def _findings_target_key_point_score(value: str, title: str = "") -> float:
    return _findings_target_score(value, title)


def _findings_retrieval_targets(doc_map: dict) -> list[dict[str, object]]:
    """Select bounded substantive sections as retrieval targets, never evidence."""

    raw_sections = doc_map.get("sections")
    if not isinstance(raw_sections, list):
        return []
    ranked: list[tuple[float, int, dict[str, object]]] = []
    for index, raw_section in enumerate(raw_sections):
        if not isinstance(raw_section, dict):
            continue
        section_id = str(raw_section.get("id") or "").strip()
        title = str(raw_section.get("title") or "").strip()
        if not section_id or not title or _FINDINGS_TARGET_METADATA_TITLE.search(title):
            continue
        pages = (
            [
                page
                for page in raw_section.get("pages", [])
                if isinstance(page, int) and not isinstance(page, bool) and page > 0
            ]
            if isinstance(raw_section.get("pages"), list)
            else []
        )
        raw_points = raw_section.get("key_points")
        key_points = (
            [str(point).strip() for point in raw_points if str(point).strip()]
            if isinstance(raw_points, list)
            else []
        )
        summary = str(raw_section.get("summary") or "").strip()
        if not key_points and not summary:
            continue
        target_key_points = key_points or [summary]
        priority_key_points = sorted(
            enumerate(target_key_points),
            key=lambda item: (
                -_findings_target_key_point_score(item[1], title),
                item[0],
            ),
        )
        selected_key_points = [target_key_points[0]]
        for _point_index, point in priority_key_points:
            if point in selected_key_points:
                continue
            selected_key_points.append(point)
            if len(selected_key_points) >= _MAX_FINDINGS_TARGET_KEY_POINTS:
                break
        point_scores = sorted(
            _findings_target_score(point, title) for point in selected_key_points
        )
        score = point_scores[len(point_scores) // 2]
        ranked.append(
            (
                score,
                index,
                {
                    "id": section_id,
                    "title": title,
                    "pages": pages,
                    "key_point": selected_key_points[0],
                    "key_points": selected_key_points,
                },
            )
        )
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [
        target for _score, _index, target in ranked[:_MAX_FINDINGS_RETRIEVAL_TARGETS]
    ]


def _findings_target_source_pages(
    targets: list[dict[str, object]], source_spans: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Return bounded PDF page text for missed DocMap targets, never DocMap proof."""

    page_spans: dict[int, list[tuple[str, str]]] = {}
    for span in source_spans:
        if not isinstance(span, dict):
            continue
        page = span.get("page")
        text = str(span.get("text") or "").strip()
        if isinstance(page, int) and not isinstance(page, bool) and page > 0 and text:
            span_id = str(span.get("id") or "").strip()
            page_spans.setdefault(page, []).append((span_id, text))

    selected: list[dict[str, object]] = []
    seen_pages: set[int] = set()
    total_chars = 0
    for target in targets:
        candidate_pages = _findings_target_physical_source_pages(target, page_spans)
        expected_numbers = {
            marker
            for key_point in _findings_target_key_points(target)
            for marker in _findings_target_number_markers(key_point)
            if not (
                marker.rstrip("e").isdigit() and 1900 <= int(marker.rstrip("e")) <= 2100
            )
        }
        if expected_numbers:
            complete_relationship_pages = [
                page
                for page in candidate_pages
                if expected_numbers.issubset(
                    _findings_target_number_markers(
                        "\n".join(text for _span_id, text in page_spans[page])
                    )
                )
            ]
            if complete_relationship_pages:
                candidate_pages = complete_relationship_pages
        for page in candidate_pages:
            if (
                not isinstance(page, int)
                or isinstance(page, bool)
                or page <= 0
                or page in seen_pages
                or page not in page_spans
                or len(selected) >= _MAX_FINDINGS_TARGET_SOURCE_PAGES
                or total_chars >= _MAX_FINDINGS_TARGET_SOURCE_CHARS
            ):
                continue
            remaining_chars = _MAX_FINDINGS_TARGET_SOURCE_CHARS - total_chars
            page_content = "\n".join(text for _span_id, text in page_spans[page])
            excerpt_limit = min(_MAX_FINDINGS_TARGET_SOURCE_PAGE_CHARS, remaining_chars)
            excerpt_start = _findings_relevant_excerpt_start(
                page_content, target, excerpt_limit
            )
            excerpt = page_content[excerpt_start : excerpt_start + excerpt_limit]
            if not excerpt:
                continue
            excerpt_end = excerpt_start + len(excerpt)
            span_ids: list[str] = []
            span_offset = 0
            for span_id, text in page_spans[page]:
                span_end = span_offset + len(text)
                if span_offset < excerpt_end and span_end > excerpt_start and span_id:
                    span_ids.append(span_id)
                span_offset = span_end + 1
            selected.append(
                {"page": page, "text": excerpt, "source_span_ids": span_ids}
            )
            seen_pages.add(page)
            total_chars += len(excerpt)
    return selected


def _findings_target_physical_source_pages(
    target: dict[str, object], page_spans: dict[int, list[tuple[str, str]]]
) -> list[int]:
    """Resolve printed DocMap labels to physical pages, then rank relevant text."""

    printed_labels = _findings_target_pages(target)
    mapped_labels: dict[int, int] = {}
    for printed_label in printed_labels:
        matches = [
            physical_page
            for physical_page, spans in page_spans.items()
            if _has_printed_page_label(
                "\n".join(text for _span_id, text in spans), printed_label
            )
        ]
        if len(matches) == 1:
            mapped_labels[printed_label] = matches[0]
    offsets = Counter(
        physical_page - printed_label
        for printed_label, physical_page in mapped_labels.items()
    )
    if offsets:
        offset, count = offsets.most_common(1)[0]
        next_count = offsets.most_common(2)[1][1] if len(offsets) > 1 else 0
        if count >= 2 and count > next_count:
            for printed_label in printed_labels:
                if printed_label in mapped_labels:
                    continue
                inferred_physical_page = printed_label + offset
                if inferred_physical_page in page_spans:
                    mapped_labels[printed_label] = inferred_physical_page

    matched_pages = [
        mapped_labels[printed_label]
        for printed_label in printed_labels
        if printed_label in mapped_labels
    ]
    if matched_pages:
        resolved_pages = list(dict.fromkeys(matched_pages))
        ranked_pages = _rank_findings_target_source_pages(
            target, page_spans, resolved_pages
        )
        return ranked_pages[: min(3, len(ranked_pages))] or resolved_pages[:2]

    # Extraction may omit a printed footer. In that case, use DocMap wording and
    # numeric markers to find a small physical-page candidate set. These pages
    # remain retrieval context; evidence-fidelity validation still decides support.
    return _rank_findings_target_source_pages(target, page_spans, list(page_spans))[:2]


def _rank_findings_target_source_pages(
    target: dict[str, object],
    page_spans: dict[int, list[tuple[str, str]]],
    candidate_pages: list[int],
) -> list[int]:
    key_points = _findings_target_key_points(target)
    query_words = _findings_target_content_words(target)
    expected_numbers = {
        marker
        for point in key_points
        for marker in _findings_target_number_markers(point)
        if not (
            marker.rstrip("e").isdigit() and 1900 <= int(marker.rstrip("e")) <= 2100
        )
    }
    if not query_words and not expected_numbers:
        return []

    ranked_pages: list[tuple[int, int, int]] = []
    for physical_page in candidate_pages:
        spans = page_spans.get(physical_page, [])
        if not spans:
            continue
        page_content = "\n".join(text for _span_id, text in spans)
        page_words = set(re.findall(r"[a-z]{3,}", page_content.casefold()))
        word_overlap = len(query_words & page_words)
        page_numbers = _findings_target_number_markers(page_content)
        number_overlap = len(expected_numbers & page_numbers)
        has_complete_numbers = bool(expected_numbers) and expected_numbers.issubset(
            page_numbers
        )
        if word_overlap < 2 and not (has_complete_numbers and word_overlap >= 1):
            continue
        score = word_overlap + 3 * number_overlap + (4 if has_complete_numbers else 0)
        ranked_pages.append((score, word_overlap, physical_page))
    ranked_pages.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [page for _score, _overlap, page in ranked_pages]


def _findings_target_content_words(target: dict[str, object]) -> set[str]:
    return {
        word
        for word in re.findall(
            r"[a-z]{3,}",
            " ".join(
                [str(target.get("title") or ""), *_findings_target_key_points(target)]
            ).casefold(),
        )
        if word not in _FINDINGS_TARGET_STOP_WORDS
    }


def _findings_relevant_excerpt_start(
    page_text: str, target: dict[str, object], excerpt_limit: int
) -> int:
    if len(page_text) <= excerpt_limit:
        return 0
    key_points = _findings_target_key_points(target)
    query_words = _findings_target_content_words(target)
    expected_numbers = (
        set().union(*(_findings_target_number_markers(point) for point in key_points))
        if key_points
        else set()
    )
    step = max(1, excerpt_limit // 4)
    starts = list(range(0, max(1, len(page_text) - excerpt_limit + 1), step))
    starts.append(max(0, len(page_text) - excerpt_limit))
    normalized_page = page_text.casefold()
    best_start = 0
    best_score = -1
    for start in dict.fromkeys(starts):
        excerpt = normalized_page[start : start + excerpt_limit]
        score = sum(word in excerpt for word in query_words)
        excerpt_numbers = _findings_target_number_markers(excerpt)
        score += 2 * len(expected_numbers & excerpt_numbers)
        if score > best_score:
            best_start = start
            best_score = score
    return best_start


def _findings_section_matches_target(
    finding: dict[str, object],
    target: dict[str, object],
    targets: Optional[list[dict[str, object]]] = None,
) -> bool:
    finding_id = str(finding.get("section_id") or "").strip()
    target_id = str(target.get("id") or "").strip()
    if finding_id:
        return finding_id == target_id
    finding_title = str(finding.get("section_title") or "").strip().casefold()
    target_title = str(target.get("title") or "").strip().casefold()
    if not finding_title or finding_title != target_title:
        return False
    same_title_targets = [
        item
        for item in (targets or [target])
        if str(item.get("title") or "").strip().casefold() == target_title
    ]
    if len(same_title_targets) < 2:
        return True
    finding_pages = set(_findings_target_pages(finding))
    target_pages = set(_findings_target_pages(target))
    return bool(finding_pages.intersection(target_pages))


def _findings_is_subset_of_fallback(
    finding: dict[str, object], fallback_finding: dict[str, object]
) -> bool:
    """Drop a primary item only when a supported fallback preserves its facts."""

    finding_section_id = str(finding.get("section_id") or "").strip()
    fallback_section_id = str(fallback_finding.get("section_id") or "").strip()
    if finding_section_id and fallback_section_id:
        same_section = finding_section_id == fallback_section_id
    else:
        same_section = bool(
            str(finding.get("section_title") or "").strip().casefold()
            == str(fallback_finding.get("section_title") or "").strip().casefold()
            and set(_findings_target_pages(finding))
            & set(_findings_target_pages(fallback_finding))
        )
    if not same_section:
        return False

    for key in ("text", "evidence"):
        primary_text = str(finding.get(key) or "")
        fallback_text = str(fallback_finding.get(key) or "")
        primary_words = set(
            re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)?", primary_text.casefold())
        )
        fallback_words = set(
            re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)?", fallback_text.casefold())
        )
        if not primary_words or not primary_words.issubset(fallback_words):
            return False
        if Counter(_findings_target_number_occurrences(primary_text)) - Counter(
            _findings_target_number_occurrences(fallback_text)
        ):
            return False
        if Counter(
            _findings_target_number_occurrences(primary_text, include_years=True)
        ) - Counter(
            _findings_target_number_occurrences(fallback_text, include_years=True)
        ):
            return False
        if _metric_label_relationship_explanation(primary_text, fallback_text):
            return False
    return set(_findings_target_pages(finding)).issubset(
        set(_findings_target_pages(fallback_finding))
    )


def _findings_target_point_covered(
    key_point: str, findings: list[dict[str, object]]
) -> bool:
    clauses = [clause.strip() for clause in re.split(r";", key_point) if clause.strip()]
    expected_years = {
        marker
        for marker in _findings_target_number_occurrences(key_point, include_years=True)
        if marker.rstrip("e").isdigit() and 1900 <= int(marker.rstrip("e")) <= 2100
    }
    return bool(clauses) and all(
        _findings_target_clause_covered(clause, findings, expected_years)
        for clause in clauses
    )


def _findings_target_numeric_occurrences(
    value: str,
) -> list[tuple[str, Quantity]]:
    markers = _findings_target_number_occurrences(value)
    quantities = [
        quantity
        for quantity in extract_quantities(value)
        if not (
            quantity.value.is_integer()
            and 1900 <= int(quantity.value) <= 2100
            and quantity.unit_family == "unknown"
        )
    ]
    if len(markers) != len(quantities):
        return []
    return [
        (
            marker,
            replace(
                quantity,
                value=abs(quantity.value) * (-1 if marker.startswith("-") else 1),
            ),
        )
        for marker, quantity in zip(markers, quantities, strict=True)
    ]


def _findings_target_numeric_values_covered(target_text: str, actual_text: str) -> bool:
    expected_markers = _findings_target_number_occurrences(target_text)
    if not expected_markers:
        return True
    actual_markers = _findings_target_number_occurrences(actual_text)
    if not (Counter(expected_markers) - Counter(actual_markers)):
        return True

    expected = _findings_target_numeric_occurrences(target_text)
    actual = _findings_target_numeric_occurrences(actual_text)
    if len(expected) != len(expected_markers) or len(actual) != len(actual_markers):
        return False
    remaining = list(actual)
    for expected_marker, expected_quantity in expected:
        match_index = next(
            (
                index
                for index, (actual_marker, actual_quantity) in enumerate(remaining)
                if expected_marker.startswith("-") == actual_marker.startswith("-")
                and quantities_match(expected_quantity, actual_quantity)
            ),
            None,
        )
        if match_index is None:
            return False
        remaining.pop(match_index)
    return True


def _findings_target_clause_covered(
    key_point: str,
    findings: list[dict[str, object]],
    required_years: set[str],
) -> bool:
    expected_numbers = Counter(_findings_target_number_occurrences(key_point))
    key_point_words = {
        word
        for word in re.findall(r"[a-z]{3,}", key_point.casefold())
        if word not in _FINDINGS_TARGET_STOP_WORDS
    }
    for finding in findings:
        claim = str(finding.get("text") or "")
        evidence = str(finding.get("evidence") or "")
        if not _findings_target_numeric_values_covered(key_point, claim):
            continue
        if not _findings_target_numeric_values_covered(key_point, evidence):
            continue
        claim_markers = set(
            _findings_target_number_occurrences(claim, include_years=True)
        )
        evidence_markers = set(
            _findings_target_number_occurrences(evidence, include_years=True)
        )
        if required_years - claim_markers or required_years - evidence_markers:
            continue
        if key_point_words and len(expected_numbers) == 0:
            finding_words = set(
                re.findall(r"[a-z]{3,}", f"{claim} {evidence}".casefold())
            )
            if len(key_point_words & finding_words) < min(2, len(key_point_words)):
                continue
        if any(
            any(variant in key_point.casefold() for variant in variants)
            and not any(variant in claim.casefold() for variant in variants)
            for _name, variants in _FINDINGS_TARGET_QUALIFIERS
        ):
            continue
        if _metric_label_relationship_explanation(key_point, claim):
            continue
        if _metric_label_relationship_explanation(claim, evidence):
            continue
        return True
    return False


def _findings_target_is_covered(
    target: dict[str, object],
    findings: list[dict[str, object]],
    grounded_finding_ids: set[str],
    targets: Optional[list[dict[str, object]]] = None,
) -> bool:
    matched = [
        finding
        for finding in findings
        if _findings_section_matches_target(finding, target, targets)
        and str(finding.get("id") or "").strip() in grounded_finding_ids
    ]
    if not matched:
        return False
    if not any(_findings_target_pages(finding) for finding in matched):
        return False
    return all(
        _findings_target_point_covered(key_point, matched)
        for key_point in _findings_target_key_points(target)
    )


def _attach_verified_finding_pages(
    findings: list[dict[str, object]], fidelity
) -> set[str]:
    """Bind supported findings to physical pages found in their source evidence."""

    findings_by_id = {
        str(finding.get("id") or "").strip(): finding
        for finding in findings
        if str(finding.get("id") or "").strip()
    }
    supported_ids: set[str] = set()
    for result in fidelity.results:
        claim_id = str(result.candidate.claim_id)
        if result.status != "supported" or not claim_id.startswith(
            "evidence:findings:"
        ):
            continue
        finding_id = claim_id.removeprefix("evidence:findings:")
        finding = findings_by_id.get(finding_id)
        if finding is None:
            continue
        pages = sorted(
            {
                int(reference.page)
                for reference in result.candidate.evidence_references
                if isinstance(getattr(reference, "page", None), int)
                and not isinstance(reference.page, bool)
                and reference.page > 0
            }
        )
        if pages:
            finding["pages"] = pages
            supported_ids.add(finding_id)
    return supported_ids


def _missing_findings_retrieval_targets(
    targets: list[dict[str, object]],
    findings: list[dict[str, object]],
    grounded_finding_ids: set[str],
) -> list[dict[str, object]]:
    """Return at most two missed high-priority targets for one fallback."""

    missing = []
    for target in targets:
        if _findings_target_is_covered(target, findings, grounded_finding_ids, targets):
            continue
        missing.append(target)
    return missing[:_MAX_FINDINGS_FALLBACK_TARGETS]


def _normalize_m_and_a_deal_quantities(text: str) -> str:
    """Keep M&A from being parsed as a magnitude in numeric deal findings."""

    return re.sub(
        r"\b(\d+(?:\.\d+)?)\s+M\s*&\s*A\s+(deals?)\b",
        r"\1 \2 in M&A",
        text,
        flags=re.IGNORECASE,
    )


def _normalize_targeted_finding_text(text: str) -> str:
    return _normalize_m_and_a_deal_quantities(text)


def _findings_prompt_user_variables(
    doc_map: dict, source_text: str = ""
) -> Dict[str, str]:
    sections: list[dict[str, object]] = []
    raw_sections = doc_map.get("sections")
    if isinstance(raw_sections, list):
        for raw_section in raw_sections:
            if not isinstance(raw_section, dict):
                continue
            section_id = str(raw_section.get("id") or "").strip()
            section_title = str(raw_section.get("title") or "").strip()
            if not section_id or not section_title:
                continue
            key_points = raw_section.get("key_points")
            pages = raw_section.get("pages")
            sections.append(
                {
                    "id": section_id,
                    "title": section_title,
                    "summary": str(raw_section.get("summary") or "").strip(),
                    "key_points": [
                        str(point).strip() for point in key_points if str(point).strip()
                    ]
                    if isinstance(key_points, list)
                    else [],
                    "pages": [
                        page
                        for page in pages
                        if isinstance(page, int) and not isinstance(page, bool)
                    ]
                    if isinstance(pages, list)
                    else [],
                }
            )
    source_temporal_relationships = [
        {"period": period, "value": value}
        for period, value in sorted(period_time_pairs(source_text))
    ]
    return {
        "doc_map_sections_json": json.dumps(sections, ensure_ascii=False),
        "source_temporal_relationships_json": json.dumps(
            source_temporal_relationships, ensure_ascii=False
        ),
        "findings_target_source_pages_json": "",
        "findings_targeted_fallback_instruction": "",
    }


def _pack_parallel_workers(settings: AppSettings, step_count: int) -> int:
    configured = coerce_int(
        getattr(settings, "evidence_pack_parallel_workers", 3), 3, min_value=1
    )
    return max(1, min(configured, step_count))


def _resolve_pack_steps(settings: AppSettings) -> list[EvidencePackStrategy]:
    raw_registry = getattr(settings, "evidence_pack_registry", None)
    registry: list[str] = []
    if isinstance(raw_registry, list):
        for value in raw_registry:
            token = str(value).strip()
            if token and token in PACK_STRATEGIES and token not in registry:
                registry.append(token)
    if not registry:
        registry = list(DEFAULT_PACK_REGISTRY)
    if "doc_map" not in registry:
        registry = ["doc_map", *registry]
    elif registry[0] != "doc_map":
        registry = ["doc_map"] + [item for item in registry if item != "doc_map"]
    return [PACK_STRATEGIES[pack_name] for pack_name in registry]


def _prompt_namespace_for_strategy(strategy: EvidencePackStrategy) -> str:
    return f"report_vs/{strategy.prompt_namespace_suffix}"


def _prompt_family_processing_version(pack_name: str) -> str:
    if pack_name in {"findings", "quote_candidates"}:
        return "report_generation_checkpoint_v3"
    return "report_generation_checkpoint_v2"


def _attach_pack_family_status(pack_name: str, payload: dict) -> dict:
    enriched = dict(payload)
    enriched["family_status"] = serialize_family_status(
        _build_pack_family_status(pack_name, enriched)
    )
    return enriched


def _build_pack_family_status(
    pack_name: str,
    payload: dict,
) -> AnalysisFamilyStatus:
    confidence_score = _pack_confidence_score(pack_name, payload)
    not_found_reason = str(payload.get("not_found_reason") or "").strip()
    if not_found_reason:
        status = "abstained"
        reason = not_found_reason
    elif confidence_score <= 0.0:
        status = "abstained"
        reason = "insufficient_pack_content"
    else:
        status = "generated"
        reason = ""
    policy_action = _pack_policy_action(pack_name, status)
    return AnalysisFamilyStatus(
        schema_version="1.0",
        family=pack_name,
        source="evidence_pack",
        status=status,
        confidence_score=confidence_score,
        policy_action=policy_action,
        reason=reason,
    )


def _pack_policy_action(pack_name: str, status: str) -> str:
    if status != "abstained":
        return "keep"
    if pack_name == "doc_map":
        return "regenerate"
    if pack_name in _OPTIONAL_EVIDENCE_PACKS:
        return "abstain"
    return "regenerate"


def _pack_confidence_score(pack_name: str, payload: dict) -> float:
    if str(payload.get("not_found_reason") or "").strip():
        return 0.0
    if pack_name == "doc_map":
        return _doc_map_confidence_score(payload)
    if pack_name in {"scope", "methods"}:
        return _scalar_or_list_pack_confidence(payload, root_key=pack_name)
    if pack_name in {
        "findings",
        "limitations",
        "quote_candidates",
    }:
        return _scalar_or_list_pack_confidence(payload, root_key=pack_name)
    return 0.0


def _doc_map_confidence_score(payload: dict) -> float:
    summary = _summarize_doc_map(payload)
    if not summary["has_content"]:
        return 0.0
    raw_sections = payload.get("sections")
    sections = raw_sections if isinstance(raw_sections, list) else []
    title_present = bool(str(payload.get("title") or "").strip())
    doc_id_present = bool(str(payload.get("doc_id") or "").strip())
    sections_with_summary = 0
    for entry in sections:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("summary") or "").strip():
            sections_with_summary += 1
    score = 0.0
    if title_present:
        score += 0.2
    if doc_id_present:
        score += 0.15
    if sections:
        score += 0.35
        score += 0.3 * (sections_with_summary / max(1, len(sections)))
    return max(0.0, min(1.0, round(score, 3)))


def _scalar_or_list_pack_confidence(payload: dict, *, root_key: str) -> float:
    value = payload.get(root_key)
    if isinstance(value, list):
        if not value:
            return 0.0
        substantive = 0
        for item in value:
            if isinstance(item, str) and item.strip():
                substantive += 1
                continue
            if isinstance(item, dict) and any(
                str(v or "").strip() for v in item.values()
            ):
                substantive += 1
        ratio = substantive / max(1, len(value))
        return max(0.0, min(1.0, round(0.4 + (0.5 * ratio), 3)))
    if isinstance(value, dict):
        substantive = any(str(v or "").strip() for v in value.values())
        return 0.9 if substantive else 0.0
    if isinstance(value, str):
        return 0.9 if value.strip() else 0.0
    return 0.0


def _strip_json_fence(text: str) -> str:
    return strip_json_fence(text)


def _parse_json_payload_from_text(text: str) -> Optional[object]:
    parsed, _strategy = parse_json_from_text(text, accepted_types=(dict, list))
    return parsed


def generate_evidence_packs(
    report_id: str,
    report_name: str,
    vector_store_id: str,
    settings: AppSettings,
    ctx: Optional[RunContext] = None,
    md5: Optional[str] = None,
    vector_store_content_hash: Optional[str] = None,
    publisher_name: str = "",
    source_url: str = "",
    source_text: str = "",
    source_spans: Optional[list[dict[str, object]]] = None,
    *,
    openai_client=None,
    prompt_client=prompt_service,
    analysis_store=report_analysis_store_service,
    prompt_family_reuse_reader=read_reusable_prompt_family,
    prompt_family_materializer=materialize_prompt_family,
    retrieval_results_observer=None,
    findings_retrieval_results_observer=None,
) -> Dict[str, dict]:
    ctx = ctx or new_run_context(task_id=f"evidence_pack:{report_id}")
    source_identity_id = str(ctx.source_identity_id or "").strip()
    openai_client = require_injected_model_client(
        openai_client,
        scope="evidence_pack_generator",
    )
    validated_source_spans = source_spans or (
        [{"id": "source:document", "text": source_text}] if source_text.strip() else []
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="evidence_pack_start",
            module=logger.name,
            fields={"report_id": report_id, "vector_store_id": vector_store_id},
        )
    )
    strategies = _resolve_pack_steps(settings)
    results: Dict[str, dict] = {}
    pack_contexts: dict[str, RunContext] = {}
    deferred_materializations: dict[
        str, tuple[PromptFamilyMaterializationRequest, RunContext, bool]
    ] = {}
    parallel_workers = _pack_parallel_workers(settings, max(0, len(strategies) - 1))
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="evidence_pack_parallel_config",
            module=logger.name,
            fields={
                "report_id": report_id,
                "parallel_workers": parallel_workers,
                "parallel_step_count": max(0, len(strategies) - 1),
                "pack_registry": [strategy.pack_name for strategy in strategies],
            },
        )
    )

    doc_strategy = strategies[0]
    step_name = doc_strategy.pack_name
    step_ctx = child_context(ctx, task_id=f"{ctx.task_id}:{step_name}")
    pack_contexts[step_name] = step_ctx
    retrieval_results: list = []
    retrieval_observed = False

    def observe_doc_map_results(found_results) -> None:
        nonlocal retrieval_observed, retrieval_results
        retrieval_observed = True
        retrieval_results = list(found_results or [])
        if retrieval_results_observer is not None:
            retrieval_results_observer(retrieval_results)

    shares_retrieval = any(
        strategy.pack_name in {"scope", "methods", "limitations"}
        for strategy in strategies[1:]
    )
    try:
        results[step_name] = _generate_pack(
            report_id=report_id,
            report_name=report_name,
            vector_store_id=vector_store_id,
            settings=settings,
            ctx=step_ctx,
            md5=md5,
            vector_store_content_hash=vector_store_content_hash,
            publisher_name=publisher_name,
            source_url=source_url,
            openai_client=openai_client,
            prompt_client=prompt_client,
            prompt_family_reuse_reader=prompt_family_reuse_reader,
            deferred_materializations=deferred_materializations,
            strategy=doc_strategy,
            retrieval_results_observer=observe_doc_map_results,
            require_retrieval_results=shares_retrieval,
        )
    finally:
        if not retrieval_observed:
            observe_doc_map_results([])
    completeness = _summarize_doc_map_completeness(results[step_name])
    if completeness["warn"]:
        logger.warning(
            log_event(
                step_ctx,
                role="generator",
                event="doc_map_completeness_warning",
                module=logger.name,
                fields={
                    "report_id": report_id,
                    "vector_store_id": vector_store_id,
                    "sections_count": completeness["sections_count"],
                    "sections_with_summary": completeness["sections_with_summary"],
                    "sections_missing_summary": completeness[
                        "sections_missing_summary"
                    ],
                    "summary_coverage_ratio": completeness["summary_coverage_ratio"],
                    "sections_with_key_points": completeness[
                        "sections_with_key_points"
                    ],
                    "key_points_coverage_ratio": completeness[
                        "key_points_coverage_ratio"
                    ],
                },
            )
        )
    summary = _summarize_doc_map(results[step_name])
    if not summary["has_content"]:
        reason = (
            summary["not_found_reason"] or summary["quality_reason"] or "no_content"
        )
        logger.info(
            log_event(
                step_ctx,
                role="generator",
                event="doc_map_validation_failed",
                module=logger.name,
                fields={
                    "report_id": report_id,
                    "vector_store_id": vector_store_id,
                    "sections_count": summary["sections_count"],
                    "substantive_sections": summary["substantive_sections"],
                    "topic_terms_count": summary["topic_terms_count"],
                    "quality_reason": summary["quality_reason"],
                    "title_present": summary["title_present"],
                    "doc_id_present": summary["doc_id_present"],
                    "summary_present": summary["summary_present"],
                    "not_found_reason": summary["not_found_reason"],
                },
            )
        )
        raise AppError(
            code="doc_map_empty",
            message=f"doc_map_empty:{reason}",
            retryable=False,
            context=summary,
        )

    parallel_strategies = strategies[1:]
    findings_prompt_user_variables: Dict[str, str] = {}
    findings_retrieval_targets: list[dict[str, object]] = []
    if any(strategy.pack_name == "findings" for strategy in parallel_strategies):
        findings_prompt_user_variables = _findings_prompt_user_variables(
            results["doc_map"], source_text
        )
        findings_retrieval_targets = _findings_retrieval_targets(results["doc_map"])
        logger.info(
            log_event(
                step_ctx,
                role="generator",
                event="findings_doc_map_context_prepared",
                module=logger.name,
                fields={
                    "report_id": report_id,
                    "sections_count": len(
                        json.loads(
                            findings_prompt_user_variables["doc_map_sections_json"]
                        )
                    ),
                },
            )
        )
    parallel_results: Dict[str, dict] = {}
    if parallel_strategies and parallel_workers > 1:
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            futures = {}
            for strategy in parallel_strategies:
                step_name = strategy.pack_name
                step_ctx = child_context(ctx, task_id=f"{ctx.task_id}:{step_name}")
                pack_contexts[step_name] = step_ctx
                future = executor.submit(
                    _generate_pack,
                    report_id=report_id,
                    report_name=report_name,
                    vector_store_id=vector_store_id,
                    settings=settings,
                    ctx=step_ctx,
                    md5=md5,
                    vector_store_content_hash=vector_store_content_hash,
                    publisher_name=publisher_name,
                    source_url=source_url,
                    openai_client=openai_client,
                    prompt_client=prompt_client,
                    prompt_family_reuse_reader=prompt_family_reuse_reader,
                    deferred_materializations=deferred_materializations,
                    strategy=strategy,
                    shared_retrieval_context_json=(
                        serialize_shared_retrieval_context(retrieval_results)
                        if strategy.pack_name in {"scope", "methods", "limitations"}
                        else ""
                    ),
                    prompt_user_variables=(
                        findings_prompt_user_variables
                        if strategy.pack_name == "findings"
                        else {}
                    ),
                    source_spans=(
                        validated_source_spans
                        if strategy.pack_name == "findings"
                        else None
                    ),
                    findings_retrieval_results_observer=(
                        findings_retrieval_results_observer
                        if strategy.pack_name == "findings"
                        else None
                    ),
                    findings_retrieval_targets=(
                        findings_retrieval_targets
                        if strategy.pack_name == "findings"
                        else None
                    ),
                )
                futures[future] = step_name
            first_error: Optional[Tuple[str, Exception]] = None
            for future in as_completed(futures):
                current_step = futures[future]
                try:
                    parallel_results[current_step] = future.result()
                except Exception as exc:  # pragma: no cover - defensive fallback
                    if first_error is None:
                        first_error = (current_step, exc)
                    logger.info(
                        log_event(
                            ctx,
                            role="generator",
                            event="evidence_pack_parallel_step_failed",
                            module=logger.name,
                            fields={
                                "report_id": report_id,
                                "pack": current_step,
                                "error": str(exc),
                            },
                        )
                    )
            if first_error is not None:
                for future in futures:
                    future.cancel()
                failed_step, first_exc = first_error
                if isinstance(first_exc, AppError):
                    raise first_exc
                raise AppError(
                    code="evidence_pack_step_failed",
                    message=f"Evidence pack step failed: {failed_step}",
                    cause=first_exc,
                    retryable=True,
                    context={"report_id": report_id, "pack": failed_step},
                ) from first_exc
    else:
        for strategy in parallel_strategies:
            step_name = strategy.pack_name
            step_ctx = child_context(ctx, task_id=f"{ctx.task_id}:{step_name}")
            pack_contexts[step_name] = step_ctx
            parallel_results[step_name] = _generate_pack(
                report_id=report_id,
                report_name=report_name,
                vector_store_id=vector_store_id,
                settings=settings,
                ctx=step_ctx,
                md5=md5,
                vector_store_content_hash=vector_store_content_hash,
                publisher_name=publisher_name,
                source_url=source_url,
                openai_client=openai_client,
                prompt_client=prompt_client,
                prompt_family_reuse_reader=prompt_family_reuse_reader,
                deferred_materializations=deferred_materializations,
                strategy=strategy,
                shared_retrieval_context_json=(
                    serialize_shared_retrieval_context(retrieval_results)
                    if strategy.pack_name in {"scope", "methods", "limitations"}
                    else ""
                ),
                prompt_user_variables=(
                    findings_prompt_user_variables
                    if strategy.pack_name == "findings"
                    else {}
                ),
                source_spans=(
                    validated_source_spans if strategy.pack_name == "findings" else None
                ),
                findings_retrieval_results_observer=(
                    findings_retrieval_results_observer
                    if strategy.pack_name == "findings"
                    else None
                ),
                findings_retrieval_targets=(
                    findings_retrieval_targets
                    if strategy.pack_name == "findings"
                    else None
                ),
            )
    for strategy in parallel_strategies:
        results[strategy.pack_name] = parallel_results[strategy.pack_name]
    if validated_source_spans:
        initial_fidelity = validate_evidence_fidelity(
            results, source_spans=validated_source_spans
        )
        candidate_texts = {
            candidate_input.candidate.claim_id: candidate_input.text
            for candidate_input in _evidence_fidelity_candidates(
                results, _source_index(validated_source_spans)
            )
        }

        def semantic_batch_fallback(candidates, sources):
            if not candidates or not sources:
                return {}
            outcome = run_semantic_validation(
                insights=[
                    {
                        "id": candidate.claim_id,
                        "text": candidate_texts.get(candidate.claim_id, ""),
                        "metric": {},
                        "evidence_id": candidate.claim_id,
                    }
                    for candidate in candidates
                ],
                quotes=[],
                evidence_texts=sources,
                settings=settings,
                prompt_client=prompt_client,
                openai_client=openai_client,
                ctx=child_context(ctx, task_id=f"{ctx.task_id}:evidence_fidelity"),
                publisher_name=publisher_name,
                report_name=report_name,
                source_url=source_url,
                report_id=report_id,
                source_id=source_identity_id,
            )
            batch_results = {}
            for candidate in candidates:
                support = outcome.metric_support.get(candidate.claim_id)
                if support is not None:
                    batch_results[candidate.claim_id] = (
                        bool(support.supported),
                        support.reason,
                        outcome.execution_identity,
                    )
            return batch_results

        fidelity = (
            validate_evidence_fidelity(
                results,
                source_spans=validated_source_spans,
                semantic_batch_validator=semantic_batch_fallback,
            )
            if initial_fidelity.unresolved_factual_count
            else initial_fidelity
        )
        findings_pack = results.get("findings")
        if isinstance(findings_pack, dict) and isinstance(
            findings_pack.get("findings"), list
        ):
            findings = [
                finding
                for finding in findings_pack["findings"]
                if isinstance(finding, dict)
            ]
            _attach_verified_finding_pages(findings, fidelity)
            findings_pack["findings"] = findings
        results = exclude_untrusted_evidence(results, fidelity)
        for pack_name in ("findings", "quote_candidates"):
            if pack_name in results:
                results[pack_name] = _attach_pack_family_status(
                    pack_name, results[pack_name]
                )
        results["evidence_fidelity"] = asdict(fidelity)

    # Store and materialize only the authoritative post-fidelity outputs. These
    # are the same payloads returned to report-analysis and artifact generation.
    for pack_name, payload in results.items():
        _store_pack(
            analysis_store=analysis_store,
            output_dir=settings.output_dir,
            report_id=report_id,
            pack_name=pack_name,
            payload=payload,
            ctx=pack_contexts.get(pack_name, ctx),
            report_name=report_name,
        )
    for pack_name, (
        request,
        materialization_ctx,
        always_materialize,
    ) in deferred_materializations.items():
        if always_materialize or results[pack_name] != request.output_payload:
            prompt_family_materializer(
                replace(request, output_payload=results[pack_name]),
                materialization_ctx,
            )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="evidence_pack_complete",
            module=logger.name,
            fields={"report_id": report_id, "packs": list(results.keys())},
        )
    )
    return results


def _generate_pack(
    *,
    report_id: str,
    report_name: str,
    vector_store_id: str,
    settings: AppSettings,
    ctx: RunContext,
    md5: Optional[str],
    vector_store_content_hash: Optional[str],
    publisher_name: str,
    source_url: str,
    openai_client,
    prompt_client,
    prompt_family_reuse_reader,
    deferred_materializations,
    strategy: EvidencePackStrategy,
    prompt_user_variables: Optional[Dict[str, str]] = None,
    source_spans: Optional[list[dict[str, object]]] = None,
    findings_retrieval_results_observer=None,
    findings_retrieval_targets: Optional[list[dict[str, object]]] = None,
    shared_retrieval_context_json: str = "",
    retrieval_results_observer=None,
    require_retrieval_results: bool = False,
) -> dict:
    source_identity_id = str(ctx.source_identity_id or "").strip()
    pack_name = strategy.pack_name
    prompt_namespace = _prompt_namespace_for_strategy(strategy)
    schema_name = strategy.schema_name
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="evidence_pack_step_start",
            module=logger.name,
            fields={
                "report_id": report_id,
                "pack": pack_name,
                "prompt_namespace": prompt_namespace,
            },
        )
    )

    def prepare_pack_prompt(
        retrieval_context_json: str,
        user_variables_override: Optional[Dict[str, str]] = None,
    ):
        user_variables = dict(
            user_variables_override
            if user_variables_override is not None
            else prompt_user_variables or {}
        )
        if pack_name in {"scope", "methods", "limitations"}:
            user_variables["shared_retrieval_context_json"] = retrieval_context_json
        return prepare_prompt_bundle(
            namespace=prompt_namespace,
            settings=settings,
            ctx=ctx,
            prompt_client=prompt_client,
            system_variables={},
            user_variables=user_variables,
            default_model=settings.openai_model,
            retrieval_mode=("chat_json" if retrieval_context_json else "vector_store"),
        )

    prompt_bundle = prepare_pack_prompt(shared_retrieval_context_json)
    if (
        shared_retrieval_context_json
        and prompt_bundle.execution_policy.policy.retrieval_mode == "file_search"
    ):
        # An explicit operator File Search policy remains authoritative.
        shared_retrieval_context_json = ""
        prompt_bundle = prepare_pack_prompt(shared_retrieval_context_json)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="evidence_pack_prompt_rendered",
            module=logger.name,
            fields={
                "pack": pack_name,
                "namespace": prompt_namespace,
                "system_path": prompt_bundle.prompt_set.system.path,
                "user_path": prompt_bundle.prompt_set.user.path,
                "prompt_system_sha256": prompt_bundle.prompt_set.system.sha256,
                "prompt_user_sha256": prompt_bundle.prompt_set.user.sha256,
                "resolved_model": prompt_bundle.resolved_model,
                "temperature": prompt_bundle.effective_temperature,
                "execution_policy_hash": prompt_bundle.execution_policy.policy_hash,
            },
        )
    )
    vector_provenance_verified = bool(str(vector_store_content_hash or "").strip())
    relevant_input_hash = (
        sha256_json(
            {
                "report_id": report_id,
                "report_name": report_name,
                "pack_name": pack_name,
                "schema_name": schema_name,
                "vector_store_id": vector_store_id,
                "vector_store_content_hash": vector_store_content_hash,
                "prompt_user_variables": prompt_user_variables or {},
                "shared_retrieval_context_json": shared_retrieval_context_json,
            }
        )
        if vector_provenance_verified
        else ""
    )
    configuration_policy_hash = sha256_json(
        {
            "execution_policy_hash": prompt_bundle.execution_policy.policy_hash,
            "execution_policy": asdict(prompt_bundle.execution_policy.policy),
            "routing_policy": asdict(prompt_bundle.routing_decision),
        }
    )

    def defer_family_materialization(
        payload: dict,
        *,
        relevant_hash: str,
        always_materialize: bool,
    ) -> None:
        if not source_identity_id or not vector_provenance_verified:
            return
        deferred_materializations[pack_name] = (
            PromptFamilyMaterializationRequest(
                schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
                db_path=settings.reports_db,
                output_dir=settings.output_dir,
                report_id=report_id,
                report_slug=report_name,
                source_id=source_identity_id,
                family_id=prompt_namespace,
                family_schema_version="1.0",
                processing_version=_prompt_family_processing_version(pack_name),
                output_payload=payload,
                system_prompt_hash=prompt_bundle.prompt_set.system.sha256,
                user_prompt_hash=prompt_bundle.prompt_set.user.sha256,
                prompt_content_hash=prompt_bundle.prompt_content_hash,
                prompt_dependency_manifest=asdict(prompt_bundle.dependency_manifest),
                execution_identity=prompt_bundle.execution_identity.execution_identity,
                execution_identity_manifest=asdict(prompt_bundle.execution_identity),
                prompt_policy_version=prompt_bundle.prompt_content_hash,
                model_name=prompt_bundle.resolved_model,
                model_provider=str(prompt_bundle.execution_policy.policy.provider),
                model_policy_namespace="report_vs",
                routing_policy_version=prompt_bundle.execution_policy.policy_hash,
                relevant_input_hash=relevant_hash,
                configuration_policy_hash=configuration_policy_hash,
                validator_version=f"{schema_name}:1.0",
                validation_status="pass",
            ),
            ctx,
            always_materialize,
        )

    def normalize_and_validate_reused(payload: object) -> dict:
        normalized = strategy.normalize_payload(payload, report_id, report_name).payload
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0", payload=normalized, schema_name=schema_name
            ),
            ctx,
        )
        return _attach_pack_family_status(pack_name, normalized)

    reused_findings_for_target_recovery: Optional[dict] = None
    # Missing canonical identity disables retained-family reuse; never
    # substitute the source MD5 for this identity.
    if (
        source_identity_id
        and vector_provenance_verified
        and not (pack_name == "doc_map" and require_retrieval_results)
    ):
        reuse = prompt_family_reuse_reader(
            PromptFamilyReuseRequest(
                schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
                db_path=settings.reports_db,
                output_dir=settings.output_dir,
                report_id=report_id,
                report_slug=report_name,
                source_id=source_identity_id,
                family_id=prompt_namespace,
                family_schema_version="1.0",
                processing_version=_prompt_family_processing_version(pack_name),
                prompt_content_hash=prompt_bundle.prompt_content_hash,
                execution_identity=prompt_bundle.execution_identity.execution_identity,
                model_provider=str(prompt_bundle.execution_policy.policy.provider),
                model_name=prompt_bundle.resolved_model,
                model_policy_namespace="report_vs",
                routing_policy_version=prompt_bundle.execution_policy.policy_hash,
                validator_version=f"{schema_name}:1.0",
                relevant_input_hash=relevant_input_hash,
                configuration_policy_hash=configuration_policy_hash,
            ),
            ctx,
        )
        if reuse.reusable:
            reused_payload = normalize_and_validate_reused(reuse.output_payload)
            if pack_name == "findings" and source_spans and findings_retrieval_targets:
                reused_findings = [
                    item
                    for item in reused_payload.get("findings", [])
                    if isinstance(item, dict)
                ]
                reused_fidelity = validate_evidence_fidelity(
                    {"findings": {"findings": reused_findings}},
                    source_spans=source_spans,
                )
                reused_grounded_ids = _attach_verified_finding_pages(
                    reused_findings, reused_fidelity
                )
                reused_payload["findings"] = reused_findings
                cached_gaps = _missing_findings_retrieval_targets(
                    findings_retrieval_targets,
                    reused_findings,
                    reused_grounded_ids,
                )
                if cached_gaps:
                    reused_findings_for_target_recovery = reused_payload
                    logger.info(
                        log_event(
                            ctx,
                            role="generator",
                            event="findings_cached_pack_target_gap",
                            module=logger.name,
                            fields={
                                "report_id": report_id,
                                "target_count": len(cached_gaps),
                                "finding_count": len(reused_findings),
                                "grounded_finding_count": len(reused_grounded_ids),
                            },
                        )
                    )
                else:
                    defer_family_materialization(
                        reused_payload,
                        relevant_hash=relevant_input_hash,
                        always_materialize=False,
                    )
                    logger.info(
                        log_event(
                            ctx,
                            role="generator",
                            event="evidence_pack_prompt_family_reused",
                            module=logger.name,
                            fields={
                                "family_id": prompt_namespace,
                                "artifact_id": reuse.artifact_id,
                            },
                        )
                    )
                    return reused_payload
            else:
                defer_family_materialization(
                    reused_payload,
                    relevant_hash=relevant_input_hash,
                    always_materialize=False,
                )
                logger.info(
                    log_event(
                        ctx,
                        role="generator",
                        event="evidence_pack_prompt_family_reused",
                        module=logger.name,
                        fields={
                            "family_id": prompt_namespace,
                            "artifact_id": reuse.artifact_id,
                        },
                    )
                )
                return reused_payload
    cache_meta = None
    cache_key = ""
    # The former pack-level cache lacks lineage, output-hash, and vector-content
    # proof. It is deliberately not consulted after E9; the independently
    # materialized family above is the sole pre-call reuse authority.
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="model_resolved",
            module=logger.name,
            fields={
                "namespace": prompt_namespace,
                "resolved_model": prompt_bundle.resolved_model,
                "default_model": settings.openai_model,
            },
        )
    )
    not_found_reason = ""
    output_schema = provider_output_schema(schema_name)

    recovery_attempted = False
    doc_map_retrieval_results: list[OpenAIFileSearchResult] = []

    def call_model(
        mode: str,
        original_response: str,
        schema_errors: str,
        *,
        bundle_override=None,
        context_override: Optional[RunContext] = None,
        stage_override: Optional[str] = None,
    ):
        nonlocal recovery_attempted, doc_map_retrieval_results
        call_ctx = context_override or ctx
        if mode not in {
            "primary",
            "targeted_fallback",
            "targeted_fallback_source_pages",
        }:
            recovery_attempted = True
        doc_map_context_json = (
            serialize_shared_retrieval_context(doc_map_retrieval_results)
            if pack_name == "doc_map"
            else ""
        )
        effective_retrieval_context = (
            shared_retrieval_context_json or doc_map_context_json
        )
        request_vector_store_id: str | None = vector_store_id
        if pack_name == "findings" and mode == "targeted_fallback_source_pages":
            request_vector_store_id = None
        if effective_retrieval_context and (
            pack_name in {"scope", "methods", "limitations"}
            or (pack_name == "doc_map" and mode != "primary")
        ):
            request_vector_store_id = None
        bundle = bundle_override or prompt_bundle
        if mode != "primary" and bundle_override is None:
            bundle = recovery_prompt_bundle(
                mode=mode,
                artifact_family=pack_name,
                schema_errors=schema_errors,
                original_response=original_response,
                output_schema=output_schema,
                source_evidence={
                    "report_name": report_name,
                    "vector_store_id": vector_store_id,
                    "pack_name": pack_name,
                    **(prompt_user_variables or {}),
                    **(
                        {"shared_retrieval_context_json": effective_retrieval_context}
                        if effective_retrieval_context
                        else {}
                    ),
                },
                settings=settings,
                ctx=call_ctx,
                prompt_client=prompt_client,
                vector_store_id=request_vector_store_id,
            )
        resp = invoke_structured_output_model(
            openai_client=openai_client,
            prompt_bundle=bundle,
            settings=settings,
            ctx=call_ctx,
            vector_store_id=request_vector_store_id,
            report_id=report_id,
            artifact_family=pack_name,
            stage=stage_override or f"evidence_pack_{mode}",
            publisher_name=publisher_name,
            report_name=report_name,
            source_url=source_url,
            output_schema=output_schema,
            output_schema_identity=f"{pack_name}_v1",
            repair_attempt={"primary": 0, "model_repair": 1, "regeneration": 2}.get(
                mode, 0
            ),
            include_file_search_results=(
                (pack_name == "doc_map" and mode == "primary")
                or (
                    pack_name == "findings"
                    and findings_retrieval_results_observer is not None
                )
            ),
            vector_store_content_hash=(vector_store_content_hash or ""),
            cache_file_search_results=(pack_name == "doc_map" and mode == "primary"),
        )
        if pack_name == "doc_map" and mode == "primary":
            doc_map_retrieval_results = list(
                getattr(resp, "file_search_results", None) or []
            )
            if retrieval_results_observer is not None:
                retrieval_results_observer(doc_map_retrieval_results)
        if pack_name == "findings" and findings_retrieval_results_observer is not None:
            found_results = list(getattr(resp, "file_search_results", None) or [])
            findings_retrieval_results_observer(found_results, mode)
            logger.info(
                log_event(
                    call_ctx,
                    role="generator",
                    event="findings_retrieval_results_observed",
                    module=logger.name,
                    fields={
                        "report_id": report_id,
                        "retrieval_stage": mode,
                        "query_count": len(
                            {
                                query
                                for result in found_results
                                for query in result.queries
                                if str(query).strip()
                            }
                        ),
                        "result_count": len(found_results),
                    },
                )
            )
        logger.info(
            log_event(
                call_ctx,
                role="generator",
                event="evidence_pack_response_received",
                module=logger.name,
                fields={
                    "report_id": report_id,
                    "pack": pack_name,
                    "namespace": bundle.dependency_manifest.namespace,
                    "model": str(resp.model or bundle.resolved_model or ""),
                    "request_id": resp.request_id or "",
                    "input_tokens": resp.input_tokens,
                    "output_tokens": resp.output_tokens,
                    "tool_calls": resp.tool_calls,
                    "has_json": isinstance(resp.parsed_json, (dict, list)),
                    "response_chars": len(str(resp.text or "")),
                    "response_sha256": sha256(
                        str(resp.text or "").encode("utf-8")
                    ).hexdigest(),
                },
            )
        )
        return resp

    def normalize_payload(payload: object) -> dict:
        if pack_name == "doc_map" and not isinstance(payload, dict):
            raise AppError(
                code="schema_type_mismatch",
                message="doc_map payload must be a JSON object",
                retryable=False,
            )
        normalized = strategy.normalize_payload(payload, report_id, report_name).payload
        # A limitations pack with an explicitly empty list has a deterministic
        # meaning: no limitation was found.  Canonicalize that documented
        # optional-pack abstention before the shared bounded recovery service
        # decides whether another model call is necessary.
        if (
            pack_name == "limitations"
            and not normalized.get("limitations")
            and not str(normalized.get("not_found_reason") or "").strip()
        ):
            normalized = dict(normalized)
            normalized["not_found_reason"] = "limitations_not_found"
        return normalized

    execution_request = StructuredOutputExecutionRequest(
        schema_version="1.0",
        report_id=report_id,
        artifact_family=pack_name,
        schema_name=schema_name,
        model=prompt_bundle.resolved_model,
        workflow="report_analysis",
        prompt_family=prompt_bundle.routing_decision.namespace,
        allow_abstention=pack_name in _OPTIONAL_EVIDENCE_PACKS,
        terminal_failure_code=(
            "doc_map_invalid_json"
            if pack_name == "doc_map"
            else "evidence_pack_invalid_json"
        ),
    )

    if reused_findings_for_target_recovery is not None:
        result_payload = reused_findings_for_target_recovery
        primary_attempts = 0
    else:
        recovery = execute_structured_output(
            execution_request,
            ctx,
            call_model=call_model,
            normalize_payload=normalize_payload,
            validate_payload=lambda payload: validate_schema(
                SchemaValidateRequest(
                    schema_version="1.0", payload=payload, schema_name=schema_name
                ),
                ctx,
            ),
            is_substantive=lambda payload: (
                _pack_confidence_score(pack_name, payload) > 0.0
            ),
            model_pricing=settings.model_pricing,
            is_formal_abstention=lambda payload: bool(
                isinstance(payload, dict)
                and str(payload.get("not_found_reason") or "").strip()
            ),
        )
        result_payload = recovery.payload
        primary_attempts = recovery.attempts
    fallback_attempts = 0
    if pack_name == "findings" and source_spans:
        findings = [
            item
            for item in result_payload.get("findings", [])
            if isinstance(item, dict)
        ]
        targets = findings_retrieval_targets or []
        if targets:
            initial_fidelity = validate_evidence_fidelity(
                {"findings": {"findings": findings}}, source_spans=source_spans
            )
            grounded_finding_ids = _attach_verified_finding_pages(
                findings, initial_fidelity
            )
            result_payload["findings"] = findings
            missing_targets = _missing_findings_retrieval_targets(
                targets, findings, grounded_finding_ids
            )
            if missing_targets:
                logger.info(
                    log_event(
                        ctx,
                        role="generator",
                        event="findings_targeted_fallback_started",
                        module=logger.name,
                        fields={
                            "report_id": report_id,
                            "missing_section_ids": [
                                str(target.get("id") or "")
                                for target in missing_targets
                            ],
                            "target_count": len(missing_targets),
                            "initial_finding_count": len(findings),
                            "grounded_finding_count": len(grounded_finding_ids),
                            "initial_validation_statuses": {
                                status: sum(
                                    result.status == status
                                    for result in initial_fidelity.results
                                )
                                for status in sorted(
                                    {
                                        result.status
                                        for result in initial_fidelity.results
                                    }
                                )
                            },
                            "source_reference_count": sum(
                                len(result.candidate.evidence_references)
                                for result in initial_fidelity.results
                            ),
                        },
                    )
                )
                fallback_ctx = child_context(
                    ctx, task_id=f"{ctx.task_id}:targeted_fallback"
                )
                fallback_variables = dict(prompt_user_variables or {})
                fallback_target_ids = {
                    str(target.get("id") or "") for target in missing_targets
                }
                fallback_variables["doc_map_sections_json"] = json.dumps(
                    [
                        {
                            "id": str(target.get("id") or ""),
                            "title": str(target.get("title") or ""),
                            "summary": "",
                            "key_points": _findings_target_key_points(target),
                            "pages": _findings_target_pages(target),
                        }
                        for target in missing_targets
                        if str(target.get("id") or "") in fallback_target_ids
                    ],
                    ensure_ascii=False,
                )
                fallback_variables["findings_targeted_fallback_instruction"] = (
                    "Bounded recovery: the DocMap sections below guide retrieval "
                    "but are not evidence. Use only the independently extracted "
                    "source-page excerpts below as evidence, and cite their physical "
                    "page numbers. Return only findings needed to complete the listed "
                    "target key points. Preserve each subject, period, denominator, "
                    "and numeric relationship; omit unsupported parts. Keep paired "
                    "measures for one subject or cohort in the same finding. For a "
                    "two-year YoY range, write 'year over year between [start year] "
                    "and [end year]' instead of copying the dash. For a numeric M&A "
                    "deal count, phrase the count before the acronym, such as "
                    "'5.2 deals in M&A'. Do not expand into unrelated findings."
                )
                fallback_source_pages = _findings_target_source_pages(
                    missing_targets, source_spans
                )
                fallback_variables["findings_target_source_pages_json"] = json.dumps(
                    fallback_source_pages, ensure_ascii=False
                )
                fallback_bundle = prepare_pack_prompt("", fallback_variables)

                def call_targeted_fallback(
                    _mode: str, _original_response: str, _schema_errors: str
                ):
                    return call_model(
                        (
                            "targeted_fallback_source_pages"
                            if fallback_source_pages
                            else "targeted_fallback"
                        ),
                        "",
                        "",
                        bundle_override=fallback_bundle,
                        context_override=fallback_ctx,
                        stage_override="evidence_pack_targeted_fallback",
                    )

                fallback_attempts = 1
                try:
                    fallback = execute_structured_output(
                        replace(execution_request, allow_model_recovery=False),
                        fallback_ctx,
                        call_model=call_targeted_fallback,
                        normalize_payload=normalize_payload,
                        validate_payload=lambda payload: validate_schema(
                            SchemaValidateRequest(
                                schema_version="1.0",
                                payload=payload,
                                schema_name=schema_name,
                            ),
                            fallback_ctx,
                        ),
                        is_substantive=lambda payload: (
                            _pack_confidence_score(pack_name, payload) > 0.0
                        ),
                        model_pricing=settings.model_pricing,
                        is_formal_abstention=lambda payload: bool(
                            isinstance(payload, dict)
                            and str(payload.get("not_found_reason") or "").strip()
                        ),
                    )
                except StructuredOutputFailure as exc:
                    logger.warning(
                        log_event(
                            fallback_ctx,
                            role="generator",
                            event="findings_targeted_fallback_rejected",
                            module=logger.name,
                            fields={
                                "report_id": report_id,
                                "error_code": exc.code,
                                "error_class": exc.context.get("error_class", ""),
                                "target_count": len(missing_targets),
                            },
                        )
                    )
                else:
                    fallback_attempts = fallback.attempts
                    target_ids = {
                        str(target.get("id") or ""): target
                        for target in missing_targets
                    }
                    fallback_findings: list[dict[str, object]] = []
                    existing_ids = {
                        str(item.get("id") or "").strip()
                        for item in findings
                        if str(item.get("id") or "").strip()
                    }
                    seen_signatures = {
                        (
                            str(item.get("section_id") or "").casefold(),
                            str(item.get("text") or "").casefold(),
                            str(item.get("evidence") or "").casefold(),
                        )
                        for item in findings
                    }
                    for raw_item in fallback.payload.get("findings", []):
                        if not isinstance(raw_item, dict):
                            continue
                        matched_target = next(
                            (
                                target
                                for target in missing_targets
                                if _findings_section_matches_target(
                                    raw_item, target, missing_targets
                                )
                            ),
                            None,
                        )
                        if matched_target is None:
                            continue
                        item = dict(raw_item)
                        if not str(item.get("section_id") or "").strip():
                            item["section_id"] = matched_target["id"]
                        if not str(item.get("section_title") or "").strip():
                            item["section_title"] = matched_target["title"]
                        if str(item.get("section_id") or "").strip() not in target_ids:
                            continue
                        item["text"] = _normalize_targeted_finding_text(
                            str(item.get("text") or "")
                        )
                        signature = (
                            str(item.get("section_id") or "").casefold(),
                            str(item.get("text") or "").casefold(),
                            str(item.get("evidence") or "").casefold(),
                        )
                        if signature in seen_signatures:
                            continue
                        item_id = str(item.get("id") or "").strip()
                        if not item_id or item_id in existing_ids:
                            base_id = item_id or str(
                                item.get("section_id") or "finding"
                            )
                            suffix = 1
                            item_id = f"{base_id}-targeted-{suffix}"
                            while item_id in existing_ids:
                                suffix += 1
                                item_id = f"{base_id}-targeted-{suffix}"
                            item["id"] = item_id
                        existing_ids.add(item_id)
                        seen_signatures.add(signature)
                        fallback_findings.append(item)
                    supported_fallback_findings: list[dict[str, object]] = []
                    if fallback_findings:
                        fallback_fidelity = validate_evidence_fidelity(
                            {"findings": {"findings": fallback_findings}},
                            source_spans=source_spans,
                        )
                        directly_supported_fallback_ids = (
                            _attach_verified_finding_pages(
                                fallback_findings, fallback_fidelity
                            )
                        )
                        supported_fallback_findings = [
                            item
                            for item in fallback_findings
                            if str(item.get("id") or "").strip()
                            in directly_supported_fallback_ids
                        ]
                        merged_findings = [
                            item
                            for item in findings
                            if not any(
                                str(fallback_item.get("id") or "").strip()
                                in directly_supported_fallback_ids
                                and _findings_is_subset_of_fallback(item, fallback_item)
                                for fallback_item in supported_fallback_findings
                            )
                        ]
                        merged_ids = {
                            str(item.get("id") or "").strip()
                            for item in merged_findings
                            if str(item.get("id") or "").strip()
                        }
                        merged_signatures = {
                            (
                                str(item.get("section_id") or "").casefold(),
                                str(item.get("text") or "").casefold(),
                                str(item.get("evidence") or "").casefold(),
                            )
                            for item in merged_findings
                        }
                        for item in supported_fallback_findings:
                            signature = (
                                str(item.get("section_id") or "").casefold(),
                                str(item.get("text") or "").casefold(),
                                str(item.get("evidence") or "").casefold(),
                            )
                            if signature in merged_signatures:
                                continue
                            item = dict(item)
                            item_id = str(item.get("id") or "").strip()
                            if item_id in merged_ids:
                                suffix = 1
                                base_id = item_id
                                item_id = f"{base_id}-targeted-{suffix}"
                                while item_id in existing_ids or item_id in merged_ids:
                                    suffix += 1
                                    item_id = f"{base_id}-targeted-{suffix}"
                                item["id"] = item_id
                            existing_ids.add(item_id)
                            merged_ids.add(item_id)
                            merged_signatures.add(signature)
                            merged_findings.append(item)
                        if merged_findings != findings:
                            merged = dict(result_payload)
                            merged["findings"] = merged_findings
                            merged["not_found_reason"] = ""
                            result_payload = merged
                    logger.info(
                        log_event(
                            fallback_ctx,
                            role="generator",
                            event="findings_targeted_fallback_complete",
                            module=logger.name,
                            fields={
                                "report_id": report_id,
                                "attempts": fallback.attempts,
                                "target_count": len(missing_targets),
                                "returned_findings": len(fallback_findings),
                                "supported_findings": len(supported_fallback_findings),
                                "merged_findings": max(
                                    0,
                                    len(result_payload.get("findings", []))
                                    - len(findings),
                                ),
                            },
                        )
                    )
    not_found_reason = str(result_payload.get("not_found_reason") or "")
    attempts_used = primary_attempts + fallback_attempts
    max_attempts = 3 + (1 if fallback_attempts else 0)
    result_payload = _attach_pack_family_status(pack_name, result_payload)
    if cache_meta and isinstance(result_payload, dict):
        result_payload = dict(result_payload)
        result_payload["_cache"] = {**cache_meta, "key": cache_key}
    defer_family_materialization(
        result_payload,
        relevant_hash=("" if recovery_attempted else relevant_input_hash),
        always_materialize=True,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="evidence_pack_step_complete",
            module=logger.name,
            fields={
                "report_id": report_id,
                "pack": pack_name,
                "not_found_reason": not_found_reason,
                "attempts": attempts_used,
                "max_attempts": max_attempts,
            },
        )
    )
    return result_payload


def _empty_payload(pack_name: str, reason: str) -> dict:
    return PACK_STRATEGIES[pack_name].empty_payload(reason)


def _normalize_evidence_pack_payload(payload: object, pack_name: str) -> dict:
    if pack_name == "doc_map":
        raise AppError(
            code="invalid_pack_strategy",
            message="doc_map uses _normalize_doc_map_payload",
            retryable=False,
        )
    return PACK_STRATEGIES[pack_name].normalize_payload(payload, "", "").payload


def _normalize_doc_map_payload(
    payload: dict, report_id: str, report_name: str = ""
) -> Tuple[dict, dict]:
    normalized = normalize_doc_map_payload(payload, report_id, report_name)
    return normalized.payload, normalized.metadata


def _summarize_doc_map(payload: dict) -> dict:
    return summarize_doc_map(payload)


def _summarize_doc_map_completeness(payload: dict) -> dict:
    return summarize_doc_map_completeness(payload)


def _resolve_pack_path(
    output_dir: str,
    report_id: str,
    pack_name: str,
    report_name: str,
    analysis_store,
    ctx: RunContext,
) -> str:
    return resolve_analysis_pack_path(
        analysis_store=analysis_store,
        request=AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=ReportId(report_id),
            pack_name=pack_name,
            report_slug=report_name,
        ),
        ctx=ctx,
    )


def _store_pack(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    pack_name: str,
    payload: dict,
    ctx: RunContext,
    report_name: str,
) -> str:
    return store_analysis_pack(
        analysis_store=analysis_store,
        request=AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=ReportId(report_id),
            pack_name=pack_name,
            payload=payload,
            report_slug=report_name,
        ),
        ctx=ctx,
    )


def _load_cached_pack(
    *,
    output_dir: str,
    report_id: str,
    pack_name: str,
    report_name: str,
    cache_key: str,
    ctx: RunContext,
    analysis_store,
) -> Optional[dict]:
    def _log_read_failed(exc: AppError, path: str) -> None:
        del path
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="evidence_pack_cache_read_failed",
                module=logger.name,
                fields={
                    "report_id": report_id,
                    "pack": pack_name,
                    "error": exc.message,
                },
            )
        )

    def _adapt_payload(
        payload: Dict[str, object], path: str
    ) -> CachedPackAdaptResult[dict]:
        strategy = PACK_STRATEGIES[pack_name]
        normalized_payload = dict(
            strategy.normalize_payload(payload, report_id, report_name).payload
        )
        normalized_payload = _attach_pack_family_status(pack_name, normalized_payload)
        try:
            validate_schema(
                SchemaValidateRequest(
                    schema_version="1.0",
                    payload=normalized_payload,
                    schema_name=strategy.schema_name,
                ),
                ctx,
            )
        except AppError as exc:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="evidence_pack_cache_invalid",
                    module=logger.name,
                    fields={
                        "report_id": report_id,
                        "pack": pack_name,
                        "path": path,
                        "code": exc.code,
                        "message": exc.message,
                    },
                )
            )
            return CachedPackAdaptResult(
                schema_version="1.0",
                status="schema_invalid",
                value=None,
            )
        not_found_reason = str(normalized_payload.get("not_found_reason") or "").strip()
        if not_found_reason:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="evidence_pack_cache_rejected",
                    module=logger.name,
                    fields={
                        "report_id": report_id,
                        "pack": pack_name,
                        "reason": not_found_reason,
                    },
                )
            )
            return CachedPackAdaptResult(
                schema_version="1.0",
                status="cache_rejected",
                value=None,
            )
        if pack_name == "doc_map":
            summary = _summarize_doc_map(normalized_payload)
            if not summary["has_content"]:
                logger.info(
                    log_event(
                        ctx,
                        role="generator",
                        event="evidence_pack_cache_rejected",
                        module=logger.name,
                        fields={
                            "report_id": report_id,
                            "pack": pack_name,
                            "reason": summary["quality_reason"] or "doc_map_no_content",
                            "substantive_sections": summary["substantive_sections"],
                            "topic_terms_count": summary["topic_terms_count"],
                        },
                    )
                )
                return CachedPackAdaptResult(
                    schema_version="1.0",
                    status="cache_rejected",
                    value=None,
                )
        return CachedPackAdaptResult(
            schema_version="1.0",
            status="hit",
            value=normalized_payload,
        )

    result = load_cached_pack(
        cache_key=cache_key,
        ctx=ctx,
        resolve_path=lambda: _resolve_pack_path(
            output_dir, report_id, pack_name, report_name, analysis_store, ctx
        ),
        read_text=file_service.read_text,
        on_read_failed=_log_read_failed,
        adapt_payload=_adapt_payload,
    )
    if result.status == "key_mismatch":
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="evidence_pack_cache_miss",
                module=logger.name,
                fields={"report_id": report_id, "pack": pack_name},
            )
        )
    return result.value if result.status == "hit" else None
