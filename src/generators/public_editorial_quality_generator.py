"""Deterministic release validation for public editorial report fields.

The module deliberately has no external I/O and no model dependency.  It
returns actionable, evidence-linked findings that the existing targeted
regeneration orchestrator can route without rewriting passing artifacts.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup

from src.contracts.public_editorial_quality import (
    PublicEditorialQualityIssue,
    PublicEditorialQualityMeasurement,
    PublicEditorialQualityReport,
)
from src.contracts.validation import ValidationIssue, ValidationReport
from src.services.render_service import _sanitize_public_prose
from src.utils.numeric_display import incomplete_source_numeric_displays

BLOCKING_RULE_IDS = {
    "public_editorial_quality.unsupported_numeric_claim",
    "public_editorial_quality.incomplete_numeric_expression",
    "public_editorial_quality.material_claim_evidence_missing",
    "public_editorial_quality.internal_identifier",
    "public_editorial_quality.placeholder",
    "public_editorial_quality.malformed_extraction_fragment",
    "public_editorial_quality.missing_asset",
    "public_editorial_quality.duplicate_insight",
    "public_editorial_quality.sentence_fragment",
    "public_editorial_quality.ocr_fragment",
    "public_editorial_quality.text_corruption",
    "public_editorial_quality.generic_figure_label",
    "public_editorial_quality.fallback_boilerplate",
    "public_editorial_quality.unsupported_certainty",
    "public_editorial_quality.nonspecific_decision_implication",
    "public_editorial_quality.figure_linkage_missing",
    "public_editorial_quality.private_operational_reference",
    "public_editorial_quality.mechanical_editorial_scaffold",
    "public_editorial_quality.literal_truncation",
    "public_editorial_quality.public_source_provenance_missing",
}

ADVISORY_RULE_IDS = {
    "public_editorial_quality.insight_role_diversity",
    "public_editorial_quality.repeated_syntax",
    "public_editorial_quality.excessive_verbosity",
    "public_editorial_quality.chart_insight_linkage",
    "public_editorial_quality.source_note_completeness",
    "public_editorial_quality.action_specificity",
}

_INTERNAL_IDENTIFIER = re.compile(
    r"(?:drive\s*file\s*id|file[_\s-]?id|source_artifact_id|"
    r"canonical[_\s-]?(?:id|path)|(?:^|\s)(?:ic|insight|finding|figure)[_-]?\d{1,5}\b)",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(
    r"\{\{[^}]+\}\}|\[\[(?:[^\]]+)\]\]|\b(?:todo|tbd|lorem ipsum|insert [a-z]+)\b",
    re.IGNORECASE,
)
_MALFORMED = re.compile(
    r"\ufffd|\b(?:\w{3,16}\s*\|\s*\w{1,2}|\w{1,2}\s*\|\s*\w{3,16})\b|"
    r"(?:\w\s+){5,}\w"
)
_MOJIBAKE = re.compile(r"(?:Ã[\u0080-\u00bf]|Â[\u0080-\u00bf]|â€)")
_MECHANICAL_SCAFFOLD = re.compile(
    r"\b(?:answer|observation|implication|executive action|"
    r"executive takeaway|concrete finding|"
    r"immediate implication)\s*:",
    re.IGNORECASE,
)
_LITERAL_TRUNCATION = re.compile(r"(?:\.\.\.|…)(?![\"'”’])")
_PRIVATE_OPERATIONAL_REFERENCE = re.compile(
    r"(?:https?://(?:drive\.google\.com|localhost|127\.0\.0\.1)\S*|"
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|(?:^|[\"'])/(?:out|cache|state)/))",
    re.IGNORECASE,
)
_SOURCE_SECTION = re.compile(
    r"<section\b[^>]*\bid=[\"']source[\"'][^>]*>", re.IGNORECASE
)
_PUBLIC_SOURCE_LINK = re.compile(
    r"<a\b[^>]*\bhref=[\"']https?://[^\"']+[\"'][^>]*>\s*Open original source\s*</a>",
    re.IGNORECASE,
)
_SOURCE_PROVENANCE_UNAVAILABLE = re.compile(
    r"Source URL:\s*Not available",
    re.IGNORECASE,
)
_GENERIC_FIGURE = re.compile(r"^(?:figure|chart|exhibit)\s*(?:\d+|[ivxlcdm]+)?$", re.I)
_NUMBER = re.compile(
    r"(?<![A-Za-z])(?:\d{1,3}(?:[,.]\d{3})+|\d+(?:[.,]\d+)?)(?:\s*%|\s*(?:million|billion|m|bn|x))?",
    re.I,
)
_CERTAINTY = re.compile(
    r"\b(?:will|certain(?:ly)?|guarantee[sd]?|proves?|always|undeniably)\b", re.I
)
_LIMITED_EVIDENCE = {"limited", "weak", "abstained", "unsupported", "not_supported"}
_FALLBACK_SENTENCES = {
    "decision relevance source backed finding",
    "review this source backed finding before committing the related decision",
}
_GENERIC_ACTIONS = {
    "review the finding",
    "consider this finding",
    "monitor this trend",
    "take action",
    "act on this insight",
}
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
    "will",
}


def evaluate_public_editorial_quality(
    *,
    report_id: str,
    artifacts: dict[str, Any],
    html: str = "",
    html_path: str = "",
    disabled_rule_waivers: dict[str, str] | None = None,
) -> PublicEditorialQualityReport:
    """Evaluate public fields and rendered HTML using enabled deterministic rules."""
    safe_artifacts = artifacts if isinstance(artifacts, dict) else {}
    waivers = _normalized_waivers(disabled_rule_waivers)
    issues: list[PublicEditorialQualityIssue] = []

    for item in _public_text_items(safe_artifacts):
        issues.extend(_text_issues(report_id, item))
    issues.extend(_insight_issues(report_id, safe_artifacts))
    issues.extend(_key_figure_issues(report_id, safe_artifacts))
    issues.extend(_figure_issues(report_id, safe_artifacts))
    if html:
        issues.extend(_html_issues(report_id, html=html, html_path=html_path))

    filtered = [issue for issue in issues if issue.rule_id not in waivers]
    filtered.sort(
        key=lambda item: (item.rule_id, item.affected_field, item.explanation)
    )
    return PublicEditorialQualityReport(
        report_id=str(report_id),
        status="fail"
        if any(issue.severity == "error" for issue in filtered)
        else "pass",
        issues=filtered,
        measurements=_measurements(safe_artifacts),
        disabled_rule_waivers=waivers,
    )


def quality_report_payload(report: PublicEditorialQualityReport) -> dict[str, Any]:
    """Serialize explicitly so public text never enters operational log events."""
    return asdict(report)


def validation_issues_from_public_editorial_quality(
    report: PublicEditorialQualityReport,
) -> list[ValidationIssue]:
    """Adapt enabled blockers to the existing targeted-regeneration contract."""
    return [
        ValidationIssue(
            schema_version="1.0",
            message=f"[{issue.rule_id}] {issue.explanation}",
            severity=issue.severity,
            affected_section=issue.affected_field,
            rule_id=issue.rule_id,
            repair_target=issue.repair_target if issue.repair_eligible else "",
            entity_id="",
        )
        for issue in report.issues
        if issue.severity == "error"
    ]


def merge_public_editorial_quality_validation(
    validation: ValidationReport,
    quality: PublicEditorialQualityReport,
) -> ValidationReport:
    added = validation_issues_from_public_editorial_quality(quality)
    issues = list(validation.issues) + added
    severity = (
        "error"
        if any(item.severity == "error" for item in issues)
        else validation.severity
    )
    return ValidationReport(
        schema_version=validation.schema_version,
        status="fail" if severity == "error" else "pass",
        issues=issues,
        severity=severity,
        source_path=validation.source_path,
    )


def public_html_quality_issues(*, html: str, html_path: str) -> dict[str, list[str]]:
    """Compatibility summary of objective rendered defects for existing callers."""
    report = evaluate_public_editorial_quality(
        report_id="public-html", artifacts={}, html=html, html_path=html_path
    )
    mapping = {
        "placeholders": "public_editorial_quality.placeholder",
        "raw_fragments": "public_editorial_quality.malformed_extraction_fragment",
        "broken_assets": "public_editorial_quality.missing_asset",
    }
    return {
        key: [issue.affected_field for issue in report.issues if issue.rule_id == rule]
        for key, rule in mapping.items()
    }


def _text_issues(
    report_id: str, item: dict[str, Any]
) -> list[PublicEditorialQualityIssue]:
    text = item["text"]
    field = item["field"]
    target = item["repair_target"]
    issues: list[PublicEditorialQualityIssue] = []
    if not text.strip():
        return issues
    for rule_id, pattern, description in (
        (
            "public_editorial_quality.internal_identifier",
            _INTERNAL_IDENTIFIER,
            "contains an internal identifier",
        ),
        (
            "public_editorial_quality.placeholder",
            _PLACEHOLDER,
            "contains an unresolved placeholder",
        ),
        (
            "public_editorial_quality.malformed_extraction_fragment",
            _MALFORMED,
            "contains a malformed extraction fragment",
        ),
        (
            "public_editorial_quality.text_corruption",
            _MOJIBAKE,
            "contains a common UTF-8 mojibake sequence",
        ),
        (
            "public_editorial_quality.mechanical_editorial_scaffold",
            _MECHANICAL_SCAFFOLD,
            "contains mechanical editorial scaffolding",
        ),
        (
            "public_editorial_quality.literal_truncation",
            _LITERAL_TRUNCATION,
            "contains a literal truncation ellipsis",
        ),
    ):
        if pattern.search(text):
            issues.append(_issue(report_id, rule_id, item, description))
    if _looks_ocr_shaped(text):
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.ocr_fragment",
                item,
                "contains an OCR-shaped fragment",
            )
        )
    if _looks_fragmentary(text):
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.sentence_fragment",
                item,
                "is a sentence fragment rather than complete public prose",
            )
        )
    if _normalized_text(text) in _FALLBACK_SENTENCES:
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.fallback_boilerplate",
                item,
                "matches prohibited generic fallback boilerplate",
            )
        )
    if incomplete_source_numeric_displays(text, str(item.get("evidence_text") or "")):
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.incomplete_numeric_expression",
                item,
                (
                    "contains a numeric display truncated before a retained "
                    "source decimal digit"
                ),
            )
        )
    if field.endswith((".so_what", ".now_what")) and _is_nonspecific_action(text):
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.nonspecific_decision_implication",
                item,
                "does not identify a report-specific decision or action",
            )
        )
    if str(
        item.get("evidence_status") or ""
    ).casefold() in _LIMITED_EVIDENCE and _CERTAINTY.search(text):
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.unsupported_certainty",
                item,
                "uses certainty language despite limited evidence status",
            )
        )
    _ = target
    return issues


def _insight_issues(
    report_id: str, artifacts: dict[str, Any]
) -> list[PublicEditorialQualityIssue]:
    insights = _dict_items(artifacts.get("insights_final"))
    issues: list[PublicEditorialQualityIssue] = []
    seen: list[tuple[int, set[str], set[str]]] = []
    for index, insight in enumerate(insights):
        insight_id = str(insight.get("id") or index + 1)
        text = _sanitize_public_prose(insight.get("text"))
        evidence_id = str(insight.get("evidence_id") or "").strip()
        evidence = str(insight.get("evidence") or "").strip()
        item = _item(
            artifact="insights_final",
            field=f"insights:{insight_id}",
            text=text,
            evidence_ids=[evidence_id] if evidence_id else [],
            repair_target="insights_bundle",
            evidence_status=_evidence_status(insight),
            evidence_text=evidence,
        )
        if text and (not evidence_id or not evidence):
            issues.append(
                _issue(
                    report_id,
                    "public_editorial_quality.material_claim_evidence_missing",
                    item,
                    "material insight has no retained evidence ID and source text",
                )
            )
        issues.extend(_text_issues(report_id, item))
        if (
            text
            and evidence
            and _unsupported_numbers(text, evidence, insight.get("metric"))
        ):
            issues.append(
                _issue(
                    report_id,
                    "public_editorial_quality.unsupported_numeric_claim",
                    item,
                    "material numeric claim is absent from linked retained evidence",
                )
            )
        tokens = _content_tokens(text)
        numbers = {_normalized_number(value) for value in _NUMBER.findall(text)}
        for prior_index, prior_tokens, prior_numbers in seen:
            if _near_duplicate(tokens, numbers, prior_tokens, prior_numbers):
                prior_id = str(insights[prior_index].get("id") or prior_index + 1)
                fields = f"insights:{insight_id}~insights:{prior_id}"
                duplicate_item = dict(item)
                duplicate_item["field"] = fields
                issues.append(
                    _issue(
                        report_id,
                        "public_editorial_quality.duplicate_insight",
                        duplicate_item,
                        "duplicates a prior insight by normalized claim content",
                    )
                )
                break
        if text:
            seen.append((index, tokens, numbers))
        for field_name in ("so_what", "now_what"):
            if field_name in insight:
                value = _sanitize_public_prose(insight.get(field_name))
                implication = dict(item)
                implication["field"] = f"insights:{insight_id}.{field_name}"
                implication["text"] = value
                if not value:
                    issues.append(
                        _issue(
                            report_id,
                            "public_editorial_quality.nonspecific_decision_implication",
                            implication,
                            "required public decision implication is empty",
                        )
                    )
                else:
                    issues.extend(_text_issues(report_id, implication))
    return issues


def _key_figure_issues(
    report_id: str, artifacts: dict[str, Any]
) -> list[PublicEditorialQualityIssue]:
    """Check public metric projections against their linked retained insight text."""

    evidence_text_by_id: dict[str, str] = {}
    for insight in _dict_items(artifacts.get("insights_final")):
        evidence_id = str(insight.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        evidence_text = " ".join(
            value
            for value in (
                str(insight.get("evidence") or "").strip(),
                str(insight.get("text") or "").strip(),
            )
            if value
        )
        if evidence_text:
            evidence_text_by_id[evidence_id] = evidence_text

    issues: list[PublicEditorialQualityIssue] = []
    for index, figure in enumerate(_dict_items(artifacts.get("key_figures")), start=1):
        evidence_id = str(figure.get("evidence_id") or "").strip()
        evidence_text = evidence_text_by_id.get(evidence_id, "")
        if not evidence_id or not evidence_text:
            continue
        for field_name in ("label", "figure", "why_it_matters"):
            value = _sanitize_public_prose(figure.get(field_name))
            if not value:
                continue
            item = _item(
                artifact="key_figures",
                field=f"key_figures:{index}.{field_name}",
                text=value,
                evidence_ids=[evidence_id],
                repair_target="insights_bundle",
                evidence_text=evidence_text,
            )
            field_issues = _text_issues(report_id, item)
            if field_name == "figure":
                # A key-figure display can be a standalone number/unit rather
                # than reader-facing sentence prose. Keep numeric-grounding
                # checks, but do not require that display to be a sentence.
                field_issues = [
                    issue
                    for issue in field_issues
                    if issue.rule_id
                    != "public_editorial_quality.sentence_fragment"
                ]
            issues.extend(field_issues)
    return issues


def _figure_issues(
    report_id: str, artifacts: dict[str, Any]
) -> list[PublicEditorialQualityIssue]:
    issues: list[PublicEditorialQualityIssue] = []
    for index, figure in enumerate(_dict_items(artifacts.get("chart_insight_cards"))):
        if figure.get("crop_qa_accepted") is not True:
            # The renderer omits cards that are not explicit accepted-crop
            # projections, including text-only insights. They are not public
            # figure cards and must not create a contradictory repair demand.
            continue
        title = str(figure.get("title") or figure.get("chart_title") or "").strip()
        caption = str(
            figure.get("caption") or figure.get("retained_caption") or ""
        ).strip()
        if title and caption and _GENERIC_FIGURE.fullmatch(title):
            item = _item(
                artifact="chart_insight_cards",
                field=f"chart_insight_cards:{index + 1}.title",
                text=title,
                evidence_ids=_string_list(figure.get("evidence_id")),
                repair_target="insights_bundle",
                evidence_text=caption,
            )
            issues.append(
                _issue(
                    report_id,
                    "public_editorial_quality.generic_figure_label",
                    item,
                    (
                        "uses a generic figure label despite a retained "
                        "descriptive caption"
                    ),
                )
            )
        if str(figure.get("status") or "").strip().lower() not in {
            "weak",
            "weak_evidence",
            "limited",
            "abstained",
        }:
            required = (
                "candidate_id",
                "evidence_id",
                "source_page",
                "insight_id",
                "caption",
            )
            missing = [
                key for key in required if not str(figure.get(key) or "").strip()
            ]
            if missing:
                item = _item(
                    artifact="chart_insight_cards",
                    field=f"chart_insight_cards:{index + 1}",
                    text=caption or title,
                    evidence_ids=_string_list(figure.get("evidence_id")),
                    repair_target="insights_bundle",
                    evidence_text=caption,
                )
                issues.append(
                    _issue(
                        report_id,
                        "public_editorial_quality.figure_linkage_missing",
                        item,
                        "public chart card is missing retained linkage fields: "
                        + ", ".join(missing),
                    )
                )
    return issues


def _html_issues(
    report_id: str, *, html: str, html_path: str
) -> list[PublicEditorialQualityIssue]:
    visible_text = _visible_html_text(html)
    item = _item("rendered_html", "html", visible_text, [], "", evidence_text="")
    issues = _text_issues(report_id, item)
    if _MECHANICAL_SCAFFOLD.search(visible_text):
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.mechanical_editorial_scaffold",
                item,
                "renders mechanical editorial scaffolding",
            )
        )
    if _LITERAL_TRUNCATION.search(visible_text):
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.literal_truncation",
                item,
                "renders a literal truncation ellipsis",
            )
        )
    if _PRIVATE_OPERATIONAL_REFERENCE.search(html):
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.private_operational_reference",
                item,
                "renders a private or operational URL/path",
            )
        )
    if (
        _SOURCE_SECTION.search(html)
        and not _PUBLIC_SOURCE_LINK.search(html)
        and not _SOURCE_PROVENANCE_UNAVAILABLE.search(visible_text)
    ):
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.public_source_provenance_missing",
                item,
                "renders a source section without a public original-source link",
            )
        )
    if _visible_report_id(report_id, visible_text):
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.internal_identifier",
                item,
                "renders the internal report identifier as reader-facing copy",
            )
        )
    for source in _broken_local_images(html=html, html_path=html_path):
        broken = dict(item)
        broken["field"] = source
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.missing_asset",
                broken,
                "references a missing local rendered asset",
            )
        )
    return issues


def _public_text_items(artifacts: dict[str, Any]) -> Iterable[dict[str, Any]]:
    summary_value = artifacts.get("summary")
    summary: dict[str, Any] = summary_value if isinstance(summary_value, dict) else {}
    summary_evidence = _summary_evidence_ids(summary)
    for field_name in ("tldr", "executive_summary"):
        value = _sanitize_public_prose(summary.get(field_name))
        if value:
            yield _item(
                "summary",
                field_name,
                value,
                summary_evidence,
                "summary",
                evidence_text=" ".join(_summary_evidence_texts(summary)),
            )
    for field_name in ("expert_comment", "linkedin_post"):
        value = _sanitize_public_prose(artifacts.get(field_name))
        if value:
            yield _item(field_name, field_name, value, [], field_name, evidence_text="")


def _issue(
    report_id: str, rule_id: str, item: dict[str, Any], explanation: str
) -> PublicEditorialQualityIssue:
    evidence_ids = list(item.get("evidence_ids") or [])
    eligible = bool(
        evidence_ids
        and str(item.get("evidence_text") or "").strip()
        and item.get("repair_target")
    )
    return PublicEditorialQualityIssue(
        report_id=str(report_id),
        rule_id=rule_id,
        severity="error" if rule_id in BLOCKING_RULE_IDS else "warning",
        affected_artifact=str(item["artifact"]),
        affected_field=str(item["field"]),
        evidence_ids=evidence_ids,
        explanation=explanation,
        repair_eligible=eligible,
        repair_status="not_requested" if eligible else "abstained",
        repair_target=str(item.get("repair_target") or "") if eligible else "",
    )


def _measurements(artifacts: dict[str, Any]) -> list[PublicEditorialQualityMeasurement]:
    insights = _dict_items(artifacts.get("insights_final"))
    count = len(insights)
    roles = {str(item.get("coverage_role") or "").strip() for item in insights} - {""}
    texts = [
        str(item.get("text") or "").strip()
        for item in insights
        if str(item.get("text") or "").strip()
    ]
    templates = [" ".join(sorted(_content_tokens(text))[:4]) for text in texts]
    repeated_template_count = sum(
        value - 1 for value in Counter(templates).values() if value > 1
    )
    chart_cards = _dict_items(artifacts.get("chart_insight_cards"))
    public_chart_cards = [
        item
        for item in chart_cards
        if str(item.get("status") or "").strip().lower()
        not in {"weak", "weak_evidence", "limited", "abstained"}
        and item.get("crop_qa_accepted") is True
    ]
    card_to_insight = sum(
        1 for item in public_chart_cards if str(item.get("insight_id") or "").strip()
    )
    figure_to_evidence = sum(
        1
        for item in public_chart_cards
        if str(item.get("candidate_id") or "").strip()
        and str(item.get("evidence_id") or "").strip()
        and str(item.get("source_page") or "").strip()
    )
    figure_to_insight = sum(
        1
        for item in public_chart_cards
        if str(item.get("candidate_id") or "").strip()
        and str(item.get("insight_id") or "").strip()
    )
    source_linked = sum(
        1 for item in insights if str(item.get("evidence_id") or "").strip()
    )
    specific_actions = sum(
        1 for item in insights if _is_specific_action(str(item.get("now_what") or ""))
    )
    average_words = (
        round(sum(len(text.split()) for text in texts) / len(texts), 2)
        if texts
        else 0.0
    )
    values = (
        (
            "public_editorial_quality.insight_role_diversity",
            float(len(roles)),
            "distinct_roles",
            "Distinct assigned insight roles.",
        ),
        (
            "public_editorial_quality.repeated_syntax",
            float(repeated_template_count),
            "repeated_openings",
            "Repeated normalized insight openings.",
        ),
        (
            "public_editorial_quality.excessive_verbosity",
            average_words,
            "average_words_per_insight",
            "Average insight length; investigate only when it is unusually high.",
        ),
        (
            "public_editorial_quality.card_to_insight_linkage",
            _ratio(card_to_insight, len(public_chart_cards)),
            "share",
            "Public chart cards with a retained insight ID.",
        ),
        (
            "public_editorial_quality.figure_to_evidence_linkage",
            _ratio(figure_to_evidence, len(public_chart_cards)),
            "share",
            "Public chart cards with accepted candidate, source page, and evidence ID.",
        ),
        (
            "public_editorial_quality.figure_to_insight_linkage",
            _ratio(figure_to_insight, len(public_chart_cards)),
            "share",
            "Public chart cards with an accepted candidate and retained insight ID.",
        ),
        (
            "public_editorial_quality.source_note_completeness",
            _ratio(source_linked, count),
            "share",
            "Insights with explicit source evidence IDs.",
        ),
        (
            "public_editorial_quality.action_specificity",
            _ratio(specific_actions, count),
            "share",
            "Insights with a specific decision action.",
        ),
    )
    return [
        PublicEditorialQualityMeasurement(
            rule_id=rule, value=value, unit=unit, explanation=explanation
        )
        for rule, value, unit, explanation in values
    ]


def _item(
    artifact: str,
    field: str,
    text: str,
    evidence_ids: list[str],
    repair_target: str,
    *,
    evidence_status: str = "",
    evidence_text: str = "",
) -> dict[str, Any]:
    return {
        "artifact": artifact,
        "field": field,
        "text": text,
        "evidence_ids": [value for value in evidence_ids if value],
        "repair_target": repair_target,
        "evidence_status": evidence_status,
        "evidence_text": evidence_text,
    }


def _normalized_waivers(value: dict[str, str] | None) -> dict[str, str]:
    return {
        str(rule).strip(): str(reason).strip()
        for rule, reason in (value or {}).items()
        if str(rule).strip() and str(reason).strip()
    }


def _dict_items(value: object) -> list[dict[str, Any]]:
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return (
        [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, list)
        else []
    )


def _summary_evidence_ids(summary: dict[str, Any]) -> list[str]:
    return [
        str(item.get("evidence_id") or "").strip()
        for item in _dict_items(summary.get("claim_evidence_map"))
        if str(item.get("evidence_id") or "").strip()
    ]


def _summary_evidence_texts(summary: dict[str, Any]) -> list[str]:
    return [
        str(item.get("claim") or "").strip()
        for item in _dict_items(summary.get("claim_evidence_map"))
        if str(item.get("claim") or "").strip()
    ]


def _evidence_status(item: dict[str, Any]) -> str:
    return (
        str(
            item.get("evidence_status")
            or item.get("confidence")
            or item.get("status")
            or ""
        )
        .strip()
        .casefold()
    )


def _normalized_text(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if token not in _STOP_WORDS and len(token) > 1
    }


def _normalized_number(value: str) -> str:
    match = re.search(r"\d{1,3}(?:[,.]\d{3})+|\d+(?:[.,]\d+)?", value)
    return re.sub(r"[,.]", "", match.group(0)) if match else ""


def _unsupported_numbers(text: str, evidence: str, metric: object) -> bool:
    evidence_text = " ".join([evidence, str(metric or "")])
    evidence_numbers = {
        _normalized_number(value) for value in _NUMBER.findall(evidence_text)
    }
    material_numbers = {
        normalized
        for value in _NUMBER.findall(text)
        if (normalized := _normalized_number(value))
        and not (len(normalized) == 4 and 1900 <= int(normalized) <= 2100)
    }
    return bool(material_numbers - evidence_numbers)


def _near_duplicate(
    tokens: set[str], numbers: set[str], prior_tokens: set[str], prior_numbers: set[str]
) -> bool:
    if not tokens or not prior_tokens:
        return False
    intersection = len(tokens & prior_tokens)
    union = len(tokens | prior_tokens)
    jaccard = intersection / union if union else 0.0
    same_material_numbers = bool(numbers) and numbers == prior_numbers
    return jaccard >= 0.78 or (
        same_material_numbers and jaccard >= 0.52 and len(tokens) >= 3
    )


def _looks_fragmentary(text: str) -> bool:
    words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", text)
    if len(words) < 3:
        return True
    stripped = text.strip()
    return not re.search(r"[.!?;:]$", stripped) and bool(
        re.search(r"\b(?:and|or|but|because|with|of|to)$", stripped, re.I)
    )


def _looks_ocr_shaped(text: str) -> bool:
    if "\ufffd" in text or "¦" in text or "||" in text:
        return True
    return bool(re.search(r"\b[A-Za-z]{2,}\d[A-Za-z]{2,}\b", text))


def _is_nonspecific_action(text: str) -> bool:
    return _normalized_text(text) in _GENERIC_ACTIONS or len(_content_tokens(text)) < 3


def _is_specific_action(text: str) -> bool:
    return bool(text.strip()) and not _is_nonspecific_action(text)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _broken_local_images(*, html: str, html_path: str) -> list[str]:
    if not html_path:
        return []
    html_dir = Path(html_path).resolve().parent
    sources = re.findall(r"<img\b[^>]*?\bsrc=[\"'](?P<src>[^\"']+)[\"']", html, re.I)
    return [
        source
        for source in sources
        if source
        and not source.startswith(("https://", "http://", "data:"))
        and not (html_dir / source).resolve().is_file()
    ]


def _visible_html_text(html: str) -> str:
    document = BeautifulSoup(html, "html.parser")
    for element in document(("head", "script", "style", "template")):
        element.decompose()
    return document.get_text(" ")


def _visible_report_id(report_id: str, text: str) -> bool:
    token = str(report_id or "").strip().casefold()
    return bool(token and token.endswith(("-pdf", ".pdf")) and token in text.casefold())


__all__ = [
    "ADVISORY_RULE_IDS",
    "BLOCKING_RULE_IDS",
    "evaluate_public_editorial_quality",
    "merge_public_editorial_quality_validation",
    "public_html_quality_issues",
    "quality_report_payload",
    "validation_issues_from_public_editorial_quality",
]
