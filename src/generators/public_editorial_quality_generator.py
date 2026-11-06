"""Deterministic release validation for public editorial report fields.

The module deliberately has no external I/O and no model dependency.  It
returns actionable, evidence-linked findings that the existing targeted
regeneration orchestrator can route without rewriting passing artifacts.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup

from src.contracts.public_editorial_quality import (
    PublicEditorialQualityIssue,
    PublicEditorialQualityItem,
    PublicEditorialQualityMeasurement,
    PublicEditorialQualityReport,
)
from src.contracts.soft_copy_claim_provenance import (
    soft_copy_claim_provenance_from_payload,
)
from src.contracts.validation import ValidationIssue, ValidationReport
from src.generators.validation.verified_facts import (
    canonical_evidence_map,
    fact_for_evidence_id,
    metric_binding_mismatches,
    validated_verified_facts,
    verified_facts_mode,
)
from src.services.render_service import (
    _build_signal_cards,
    _coerce_limitation_items,
    _coerce_public_advisory,
    _coerce_public_chart_insight_cards,
    _coerce_public_topics_covered,
    _coerce_topic_briefs,
    _is_public_chart_insight_card,
    _sanitize_public_prose,
)
from src.utils.editorial_identity import insight_entity_id
from src.utils.errors import AppError
from src.utils.numeric_display import incomplete_source_numeric_displays
from src.utils.quantity import (
    Quantity,
    canonicalize_quantity,
    extract_quantities,
    quantities_match,
)
from src.utils.verified_facts import verified_advisory_evidence_ids

BLOCKING_RULE_IDS = {
    "public_editorial_quality.unsupported_numeric_claim",
    "public_editorial_quality.incomplete_numeric_expression",
    "public_editorial_quality.temporal_integrity",
    "public_editorial_quality.metric_label_relationship",
    "public_editorial_quality.metric_binding_mismatch",
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
    "public_editorial_quality.nonspecific_decision_implication",
}

# Deterministic public-release checks are limited to contract and rendering
# integrity.  Semantic factuality, interpretation, recommendation quality and
# editorial usefulness are adjudicated by the independent public-editorial
# model review at the orchestration boundary.  The older semantic detectors
# remain available to existing diagnostics/tests, but their findings must not
# become publication authority by themselves.
DETERMINISTIC_PUBLIC_EDITORIAL_RULE_IDS = frozenset(
    {
        "public_editorial_quality.internal_identifier",
        "public_editorial_quality.placeholder",
        "public_editorial_quality.malformed_extraction_fragment",
        "public_editorial_quality.text_corruption",
        "public_editorial_quality.literal_truncation",
        "public_editorial_quality.material_claim_evidence_missing",
        "public_editorial_quality.missing_asset",
        "public_editorial_quality.figure_linkage_missing",
        "public_editorial_quality.private_operational_reference",
        "public_editorial_quality.public_source_provenance_missing",
        "public_editorial_quality.metadata_identity",
    }
)

# These failures are source-fidelity release blockers, not weighted editorial
# quality deductions.  They deliberately cannot be waived: any one prevents
# publication even when every advisory quality measurement is excellent.
HARD_FAIL_CLASS_BY_RULE_ID = {
    "public_editorial_quality.unsupported_numeric_claim": "incorrect_numeric_value",
    "public_editorial_quality.incomplete_numeric_expression": (
        "malformed_or_truncated_public_claim"
    ),
    "public_editorial_quality.material_claim_evidence_missing": (
        "unsupported_factual_claim"
    ),
    "public_editorial_quality.literal_truncation": (
        "malformed_or_truncated_public_claim"
    ),
    "public_editorial_quality.malformed_extraction_fragment": (
        "malformed_or_truncated_public_claim"
    ),
    "public_editorial_quality.ocr_fragment": "malformed_or_truncated_public_claim",
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
# Broken extraction cells leave a tiny remnant beside one pipe (for example
# "platfor | ms" or "Revenue | 5").  A short segment that continues into a
# number ("Report | Q1 2026") is the renderer's own pipe-separated report
# title carrying an edition designator, not an extraction fragment.
_MALFORMED = re.compile(
    r"\ufffd|\b(?:\w{3,16}\s*\|\s*\w{1,2}(?!\s*\d)"
    r"|\w{1,2}(?!\s*\d)\s*\|\s*\w{3,16})\b|"
    r"(?:\w\s+){5,}\w"
)
_MOJIBAKE = re.compile(r"(?:Ã[\u0080-\u00bf]|Â[\u0080-\u00bf]|â€)")
_MECHANICAL_SCAFFOLD = re.compile(
    r"\b(?:answer|observation|implication|executive action|"
    r"executive takeaway|concrete finding|"
    r"immediate implication)\s*:",
    re.IGNORECASE,
)
_LITERAL_TRUNCATION = re.compile(r"(?:\.\.\.|…)(?![\"'”’])\s*$")
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
_TEMPORAL_QUALIFIER = re.compile(
    r"\b(?:Q[1-4]|H[12])(?:\s*(?:FY\s*)?20\d{2})?\b|"
    r"\b(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|"
    r"Oct|Nov|Dec)\.?\s+20\d{2}\b|"
    r"\b(?:FY\s*20\d{2}|fiscal\s+year\s+20\d{2})\b",
    re.IGNORECASE,
)
_FORECAST_MARKER = re.compile(
    r"\b(?:forecast(?:s|ed|ing)?|project(?:s|ed|ion|ions)?|"
    r"expect(?:s|ed|ation|ations)?|outlook)\b",
    re.IGNORECASE,
)
_RELATIONSHIP_VALUE = (
    r"(?:[$€£¥]\s*)?[+-]?(?:\d{1,3}:\d{2}|\d{1,3}(?:[,.]\d{3})+|\d+(?:[.,]\d+)?)"
    r"(?:\s*%|\s*(?:thousand|million|billion|trillion|mm|mn|mil|bn|bil|tn|tril|k|m|b|t|x))?"
)
_PERIOD_LABEL = (
    r"(?:Q[1-4]\s*(?:FY\s*)?(?:19|20)\d{2}E?|"
    r"(?:19|20)\d{2}E?\s*Q[1-4]|(?:19|20)\d{2}E?)"
)
_PERIOD_VALUE_PAIR = re.compile(
    rf"(?P<label>{_PERIOD_LABEL})\s*(?:[:=,]|\s)\s*"
    rf"(?P<value>{_RELATIONSHIP_VALUE})(?![A-Za-z0-9%])",
    re.IGNORECASE,
)
_VALUE_PERIOD_PAIR = re.compile(
    rf"(?P<value>{_RELATIONSHIP_VALUE})(?![A-Za-z0-9%])\s*"
    rf"(?:\(?\s*(?:in|for|at|during|by|of)?\s*)?"
    rf"(?P<label>{_PERIOD_LABEL})\b",
    re.IGNORECASE,
)
_CAPITALIZED_CATEGORY_VALUE_PAIR = re.compile(
    rf"\b(?P<label>[A-Z][A-Za-z0-9&/-]*(?:\s+(?:[A-Z][A-Za-z0-9&/-]*|and|&)){{0,4}})"
    rf"(?:[ \t]*(?::|is|has|accounts\s+for|at|reaches)[ \t]*|[ \t]+)"
    rf"(?P<value>{_RELATIONSHIP_VALUE})(?![A-Za-z0-9%])"
)
_COMMA_CATEGORY_VALUE_PAIR = re.compile(
    rf"\b(?P<label>[A-Z][A-Za-z0-9&/-]*(?:,\s*[A-Z][A-Za-z0-9&/-]*){{1,4}}"
    rf"(?:\s*,?\s*and\s+[A-Z][A-Za-z0-9&/-]*)?)"
    rf"\s+(?P<value>{_RELATIONSHIP_VALUE})(?![A-Za-z0-9%])"
)
_DELIMITED_SPACE_CATEGORY_VALUE_PAIR = re.compile(
    rf";\s*(?P<label>[A-Za-z][A-Za-z0-9&/-]*"
    rf"(?:\s+[A-Za-z][A-Za-z0-9&/-]*){{1,4}})"
    rf"[ \t]+(?P<value>{_RELATIONSHIP_VALUE})(?![A-Za-z0-9%])"
)
_DELIMITED_CATEGORY_VALUE_PAIR = re.compile(
    rf"(?:^|[;,\n])\s*(?P<label>[A-Za-z][A-Za-z0-9&/ -]{{0,48}}?)"
    rf"\s*(?::|=)\s*(?P<value>{_RELATIONSHIP_VALUE})(?![A-Za-z0-9%])"
)
_SUBJECT_VALUE_RELATIONSHIP = re.compile(
    rf"(?:^|[.;]\s*)(?P<subject>[A-Z][A-Za-z0-9&/-]*(?:\s+[A-Za-z0-9&/-]+){{0,4}}?)"
    rf"\s+(?:is|are|represents?)\s+(?P<value>{_RELATIONSHIP_VALUE})(?![A-Za-z0-9%])"
    rf"(?:\s+of\s+(?P<context>[^.;]+?))?(?=\s+(?:and|but)\b|[.;]|$)",
    re.IGNORECASE,
)
_SUBJECT_ACCOUNT_RELATIONSHIP = re.compile(
    rf"(?:^|[.;]\s*)(?P<prefix>[^.;]{{1,100}}?)\baccounts?\s+for\s+(?P<value>{_RELATIONSHIP_VALUE})(?![A-Za-z0-9%])"
    rf"(?:\s+of\s+(?P<context>[^.;]+?))?(?=[.;]|$)",
    re.IGNORECASE,
)
_MALFORMED_TEMPORAL_COMPARISON = re.compile(r"\b(?:in\s+to|between\s+and)\b", re.I)
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
    metadata_evidence: Mapping[str, object] | None = None,
) -> PublicEditorialQualityReport:
    """Evaluate public fields and rendered HTML using enabled deterministic rules."""
    safe_artifacts = artifacts if isinstance(artifacts, dict) else {}
    waivers = _normalized_waivers(disabled_rule_waivers)
    issues: list[PublicEditorialQualityIssue] = []
    if verified_facts_mode(safe_artifacts):
        safe_artifacts = dict(safe_artifacts)
        # A verified-facts snapshot is structural authority, not an editorial
        # quality issue that can be regenerated or waived.  Preserve the
        # original typed failure so the orchestration boundary can fail closed.
        verified_index = validated_verified_facts(safe_artifacts)
        safe_artifacts["_verified_fact_index"] = verified_index
        safe_artifacts["_verified_facts_mode"] = True

    for item in _public_text_items(safe_artifacts):
        issues.extend(_text_issues(report_id, item))
    issues.extend(_insight_issues(report_id, safe_artifacts))
    issues.extend(_key_figure_issues(report_id, safe_artifacts))
    issues.extend(_figure_issues(report_id, safe_artifacts))
    if html:
        issues.extend(_html_issues(report_id, html=html, html_path=html_path))
    issues.extend(
        _metadata_issues(report_id, safe_artifacts, metadata_evidence or {}, html=html)
    )

    # Source-fidelity and rendering failures are an explicit release policy and
    # are never eligible for a quality-rule waiver.  Semantic/editorial
    # judgments are deliberately omitted here; the independent LLM review
    # owns those decisions in the report-analysis orchestrator.
    filtered = [
        issue
        for issue in issues
        if issue.rule_id in DETERMINISTIC_PUBLIC_EDITORIAL_RULE_IDS
        and (issue.rule_id not in waivers or issue.hard_fail_class)
    ]
    filtered.sort(
        key=lambda item: (item.rule_id, item.affected_field, item.explanation)
    )
    hard_fail_count = sum(bool(issue.hard_fail_class) for issue in filtered)
    status = "fail" if any(issue.severity == "error" for issue in filtered) else "pass"
    return PublicEditorialQualityReport(
        report_id=str(report_id),
        status=status,
        issues=filtered,
        measurements=_measurements(safe_artifacts),
        items=enumerate_public_editorial_items(safe_artifacts),
        disabled_rule_waivers=waivers,
        publishable=status == "pass" and hard_fail_count == 0,
        hard_fail_count=hard_fail_count,
    )


def quality_report_payload(report: PublicEditorialQualityReport) -> dict[str, Any]:
    """Serialize explicitly so public text never enters operational log events."""
    return asdict(report)


def validation_issues_from_public_editorial_quality(
    report: PublicEditorialQualityReport,
) -> list[ValidationIssue]:
    """Adapt enabled blockers to the existing targeted-regeneration contract."""
    issues = [
        ValidationIssue(
            schema_version="1.0",
            message=f"[{issue.rule_id}] {issue.explanation}",
            severity=issue.severity,
            affected_section=issue.affected_field,
            rule_id=issue.rule_id,
            violation_type=issue.hard_fail_class,
            repair_target=issue.repair_target if issue.repair_eligible else "",
            entity_id=issue.public_item_id,
            evidence_ids=list(issue.evidence_ids),
        )
        for issue in report.issues
        if issue.severity == "error"
    ]
    # Persisted quality snapshots are an input to the release gate, not an
    # authority that may contradict their own aggregate disposition.  A
    # failed/non-publishable snapshot with warning-only detail must still
    # remain blocking until it is re-evaluated by the owning workflow.
    if (report.status != "pass" or not report.publishable) and not issues:
        issues.append(
            ValidationIssue(
                schema_version="1.0",
                message=(
                    "[public_editorial_quality.report_status_conflict] "
                    "The persisted public editorial quality report is not "
                    "publishable but contains no blocking issue."
                ),
                severity="error",
                affected_section="public_editorial_quality",
                rule_id="public_editorial_quality.report_status_conflict",
                repair_target="",
                entity_id="",
                evidence_ids=[],
            )
        )
    return issues


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
    verified_mode = bool(item.get("verified_facts_mode"))
    issues: list[PublicEditorialQualityIssue] = []
    if not text.strip():
        return issues
    if item.get("verified_facts_mode") and (
        not item.get("evidence_ids") or not str(item.get("evidence_text") or "").strip()
    ):
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.material_claim_evidence_missing",
                item,
                "verified public prose has no canonical fact binding",
            )
        )
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
    if not verified_mode and incomplete_source_numeric_displays(
        text, str(item.get("evidence_text") or "")
    ):
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
    if not verified_mode:
        temporal_explanation = _temporal_integrity_explanation(
            text, str(item.get("evidence_text") or "")
        )
        if temporal_explanation:
            issues.append(
                _issue(
                    report_id,
                    "public_editorial_quality.temporal_integrity",
                    item,
                    temporal_explanation,
                )
            )
        relationship_explanation = _metric_label_relationship_explanation(
            text,
            str(
                item.get("metric_relationship_evidence_text")
                or item.get("evidence_text")
                or ""
            ),
        )
        if relationship_explanation:
            issues.append(
                _issue(
                    report_id,
                    "public_editorial_quality.metric_label_relationship",
                    item,
                    relationship_explanation,
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
    if (
        not verified_mode
        and str(item.get("evidence_status") or "").casefold() in _LIMITED_EVIDENCE
        and _CERTAINTY.search(text)
    ):
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
        insight_id = insight_entity_id(insight) or str(index + 1)
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
        _annotate_verified_item(item, artifacts)
        fact = _fact_for_item(artifacts, item)
        if fact is not None:
            mismatches = metric_binding_mismatches(
                insight.get("metric"), fact.get("metric")
            )
            if mismatches:
                issues.append(
                    _issue(
                        report_id,
                        "public_editorial_quality.metric_binding_mismatch",
                        item,
                        "insight metric binding differs from its canonical verified "
                        "fact: " + ", ".join(mismatches),
                    )
                )
        item["metric_relationship_evidence_text"] = (
            item.get("evidence_text")
            if item.get("verified_facts_mode")
            else _preferred_metric_relationship_evidence(insight) or evidence
        )
        if text and (
            not evidence_id
            or not evidence
            or (
                item.get("verified_facts_mode")
                and _fact_for_item(artifacts, item) is None
            )
        ):
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
            and not item.get("verified_facts_mode")
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
        numbers = _material_numbers(text)
        for prior_index, prior_tokens, prior_numbers in seen:
            if _near_duplicate(tokens, numbers, prior_tokens, prior_numbers):
                prior_id = insight_entity_id(insights[prior_index]) or str(
                    prior_index + 1
                )
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


def _preferred_metric_relationship_evidence(insight: Mapping[str, Any]) -> str:
    """Prefer an authoritative findings statement for label/value binding checks."""
    statements: list[str] = []
    for raw_span in insight.get("evidence_spans") or []:
        if not isinstance(raw_span, Mapping):
            continue
        if str(raw_span.get("source_pack") or "").strip().casefold() != (
            "findings_statement"
        ):
            continue
        text = str(raw_span.get("text") or raw_span.get("evidence") or "").strip()
        if text and text not in statements:
            statements.append(text)
    return "\n".join(statements)


def _key_figure_issues(
    report_id: str, artifacts: dict[str, Any]
) -> list[PublicEditorialQualityIssue]:
    """Check public metric projections against their linked retained insight text."""

    evidence_text_by_id: dict[str, str] = {}
    for insight in _dict_items(artifacts.get("insights_final")):
        evidence_id = str(insight.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        evidence_text = str(insight.get("evidence") or "").strip()
        if evidence_text:
            evidence_text_by_id[evidence_id] = evidence_text

    issues: list[PublicEditorialQualityIssue] = []
    verified_mode = verified_facts_mode(artifacts)
    verified_index = _verified_fact_index(artifacts)
    missing_metric_copy_sources: set[tuple[str, str]] = set()

    def check_missing_metric_copy(
        *, section: str, index: int, metric: Mapping[str, Any]
    ) -> None:
        if not verified_mode or _sanitize_public_prose(
            metric.get("metric_public_copy")
        ):
            return
        evidence_id = str(metric.get("evidence_id") or "").strip()
        fact = fact_for_evidence_id(verified_index, evidence_id)
        if not evidence_id or fact is None:
            return
        metric_id = str(
            metric.get("metric_id")
            or metric.get("insight_id")
            or metric.get("figure_id")
            or metric.get("key_figure_id")
            or ""
        ).strip()
        source_key = (evidence_id, metric_id)
        if source_key in missing_metric_copy_sources:
            return
        missing_metric_copy_sources.add(source_key)
        matches = [
            insight
            for insight in _dict_items(artifacts.get("insights_final"))
            if metric_id
            and metric_id
            in {
                str(insight.get("id") or "").strip(),
                str(insight.get("insight_id") or "").strip(),
            }
        ]
        repair_target = "insights_bundle" if len(matches) == 1 else ""
        repair_field = (
            f"insights:{metric_id}.metric_public_copy" if len(matches) == 1 else ""
        )
        evidence_text = canonical_evidence_map(
            {str(fact.get("fact_id") or ""): fact}
        ).get(evidence_id, "")
        item = _item(
            artifact=section,
            field=f"{section}:{index}.metric_public_copy",
            text=_sanitize_public_prose(
                metric.get("label")
                or metric.get("metric")
                or metric.get("name")
                or metric.get("figure")
                or "verified metric"
            ),
            evidence_ids=[evidence_id],
            repair_target=repair_target,
            evidence_text=evidence_text,
            repair_field=repair_field,
        )
        _annotate_verified_item(item, artifacts)
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.material_claim_evidence_missing",
                item,
                "verified metric projection has no authoritative metric_public_copy",
            )
        )

    for index, figure in enumerate(_dict_items(artifacts.get("key_figures")), start=1):
        check_missing_metric_copy(section="key_figures", index=index, metric=figure)
        evidence_id = str(figure.get("evidence_id") or "").strip()
        evidence_text = evidence_text_by_id.get(evidence_id, "")
        fact = fact_for_evidence_id(_verified_fact_index(artifacts), evidence_id)
        if fact is not None:
            evidence_text = canonical_evidence_map(
                {str(fact.get("fact_id") or ""): fact}
            ).get(evidence_id, "")
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
                repair_target="key_figures",
                evidence_text=evidence_text,
            )
            _annotate_verified_item(item, artifacts)
            field_issues = _text_issues(report_id, item)
            if field_name in {"label", "figure"}:
                # Key-figure labels and displays are reader-facing metric
                # phrases, not sentence prose. Keep all factual and
                # evidence checks, but do not require a complete sentence.
                excluded_rule_ids = {
                    "public_editorial_quality.sentence_fragment",
                }
                if field_name == "figure":
                    excluded_rule_ids.add("public_editorial_quality.temporal_integrity")
                field_issues = [
                    issue
                    for issue in field_issues
                    if issue.rule_id not in excluded_rule_ids
                ]
            issues.extend(field_issues)
    for index, metric in enumerate(_dict_items(artifacts.get("metric_spine")), start=1):
        check_missing_metric_copy(section="metric_spine", index=index, metric=metric)
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
    issues = [
        issue
        for issue in _text_issues(report_id, item)
        if issue.rule_id != "public_editorial_quality.literal_truncation"
    ]
    if _MECHANICAL_SCAFFOLD.search(visible_text):
        issues.append(
            _issue(
                report_id,
                "public_editorial_quality.mechanical_editorial_scaffold",
                item,
                "renders mechanical editorial scaffolding",
            )
        )
    document = BeautifulSoup(html, "html.parser")
    for element in document(("head", "script", "style", "template")):
        element.decompose()
    if any(
        _LITERAL_TRUNCATION.search(node.get_text(" ", strip=True))
        for node in document.select(
            "p, li, h1, h2, h3, h4, h5, h6, blockquote, figcaption, "
            "div, section, article, main, body"
        )
    ):
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
    verified_mode = verified_facts_mode(artifacts)
    summary_evidence = _summary_evidence_items(summary)
    if verified_mode:
        summary_evidence = _verified_evidence_items(
            artifacts, [evidence_id for evidence_id, _ in summary_evidence]
        )
    for field_name in ("tldr", "card_tldr_compact", "executive_summary"):
        value = _sanitize_public_prose(summary.get(field_name))
        if value:
            claim_items = _retained_soft_copy_sentence_items(
                artifacts=artifacts,
                artifact="summary",
                field=field_name,
                text=value,
                evidence_items=summary_evidence,
            )
            if claim_items:
                for item in claim_items:
                    _annotate_verified_item(item, artifacts)
                    yield item
            elif summary_evidence and not verified_mode:
                item = _item(
                    "summary",
                    field_name,
                    value,
                    [evidence_id for evidence_id, _ in summary_evidence],
                    "summary",
                    evidence_text=" ".join(
                        evidence_text for _, evidence_text in summary_evidence
                    ),
                )
                _annotate_verified_item(item, artifacts)
                yield item
            else:
                item = _item("summary", field_name, value, [], "summary")
                _annotate_verified_item(item, artifacts)
                yield item

    downstream_evidence = _downstream_evidence_items(artifacts)
    if verified_mode:
        downstream_evidence = _verified_evidence_items(
            artifacts, [evidence_id for evidence_id, _ in downstream_evidence]
        )
    for field_name in ("expert_comment", "linkedin_post"):
        value = _sanitize_public_prose(artifacts.get(field_name))
        if value:
            claim_items = _retained_soft_copy_sentence_items(
                artifacts=artifacts,
                artifact=field_name,
                field=field_name,
                text=value,
                evidence_items=downstream_evidence,
            )
            if claim_items:
                for item in claim_items:
                    _annotate_verified_item(item, artifacts)
                    yield item
            elif downstream_evidence and not verified_mode:
                item = _item(
                    field_name,
                    field_name,
                    value,
                    [evidence_id for evidence_id, _ in downstream_evidence],
                    field_name,
                    evidence_text=" ".join(
                        evidence_text for _, evidence_text in downstream_evidence
                    ),
                )
                _annotate_verified_item(item, artifacts)
                yield item
            else:
                item = _item(field_name, field_name, value, [], field_name)
                _annotate_verified_item(item, artifacts)
                yield item


def public_editorial_semantic_review_items(
    artifacts: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return every public text item with its retained evidence context.

    This is a pure projection for the existing model boundary.  It keeps
    public copy out of ordinary quality logs while giving the semantic
    reviewer one stable item identity per public surface.  No semantic
    decision is made here.
    """

    if verified_facts_mode(artifacts):
        return _verified_public_semantic_review_items(artifacts)

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_text: set[str] = set()
    retained_evidence_text = _retained_public_evidence_text_by_id(artifacts)
    deduplicate_text = verified_facts_mode(artifacts)

    for item in _public_text_items(artifacts):
        _attach_retained_evidence_text(item, retained_evidence_text)
        item_id = str(item.get("public_item_id") or "").strip()
        normalized_text = " ".join(str(item.get("text") or "").split()).casefold()
        if (
            item_id
            and item_id not in seen
            and (
                not deduplicate_text
                or not normalized_text
                or normalized_text not in seen_text
            )
        ):
            seen.add(item_id)
            if normalized_text:
                seen_text.add(normalized_text)
            items.append(item)

    def add_item(item: dict[str, Any]) -> None:
        _attach_retained_evidence_text(item, retained_evidence_text)
        item_id = str(item.get("public_item_id") or "").strip()
        normalized_text = " ".join(str(item.get("text") or "").split()).casefold()
        if (
            item_id
            and item_id not in seen
            and (
                not deduplicate_text
                or not normalized_text
                or normalized_text not in seen_text
            )
        ):
            seen.add(item_id)
            if normalized_text:
                seen_text.add(normalized_text)
            items.append(item)

    for insight in _dict_items(artifacts.get("insights_final")):
        insight_id = insight_entity_id(insight)
        if not insight_id:
            continue
        evidence_ids = _public_evidence_ids(insight)
        evidence_text = str(
            insight.get("evidence") or insight.get("source_excerpt") or ""
        ).strip()
        for field_name in ("text", "so_what", "now_what"):
            value = _sanitize_public_prose(insight.get(field_name))
            if value:
                item = _item(
                    "insights_final",
                    f"insights:{insight_id}.{field_name}"
                    if field_name != "text"
                    else f"insights:{insight_id}",
                    value,
                    evidence_ids,
                    "insights_bundle",
                    evidence_text=evidence_text,
                )
                _annotate_verified_item(item, artifacts)
                add_item(item)

    for artifact_name, raw_figures in (
        ("key_figures", artifacts.get("key_figures")),
        ("metric_spine", artifacts.get("metric_spine")),
    ):
        for index, figure in enumerate(_dict_items(raw_figures), start=1):
            evidence_ids = _public_evidence_ids(figure)
            if verified_facts_mode(artifacts) and not any(
                fact_for_evidence_id(_verified_fact_index(artifacts), evidence_id)
                is not None
                for evidence_id in evidence_ids
            ):
                continue
            value = _sanitize_public_prose(figure.get("value") or figure.get("figure"))
            label = _sanitize_public_prose(
                figure.get("label") or figure.get("metric") or figure.get("name")
            )
            context_fields = (
                (
                    "context",
                    "cohort",
                    "denominator",
                    "segment",
                    "geography",
                    "timeframe",
                )
                if artifact_name == "key_figures"
                else ("segment", "geography", "timeframe")
            )
            context = ", ".join(
                str(figure.get(field_name) or "").strip()
                for field_name in context_fields
                if str(figure.get(field_name) or "").strip()
            )
            for field_name, text in (
                ("value", value),
                ("label", label),
                ("context", context),
            ):
                if not text:
                    continue
                item = _item(
                    artifact_name,
                    f"{artifact_name}:{index}.{field_name}",
                    text,
                    evidence_ids,
                    "insights_bundle",
                    evidence_text=str(
                        figure.get("evidence") or figure.get("source_excerpt") or ""
                    ).strip(),
                )
                _annotate_verified_item(item, artifacts)
                add_item(item)

    for index, quote in enumerate(_dict_items(artifacts.get("quotes_final")), start=1):
        value = _sanitize_public_prose(quote.get("text"))
        if value:
            item = _item(
                "quotes_final",
                f"quotes:{quote.get('id') or index}",
                value,
                _public_evidence_ids(quote),
                "quotes",
                evidence_text=str(
                    quote.get("evidence") or quote.get("source_excerpt") or ""
                ).strip(),
            )
            _annotate_verified_item(item, artifacts)
            add_item(item)

    for index, card in enumerate(
        _dict_items(artifacts.get("chart_insight_cards")), start=1
    ):
        if not _is_public_chart_insight_card(card):
            continue
        evidence_ids = _public_evidence_ids(card)
        if verified_facts_mode(artifacts) and not any(
            fact_for_evidence_id(_verified_fact_index(artifacts), evidence_id)
            is not None
            for evidence_id in evidence_ids
        ):
            continue
        evidence_text = str(
            card.get("evidence") or card.get("source_excerpt") or ""
        ).strip()
        limitation = _sanitize_public_prose(
            card.get("limitation")
            or card.get("avoid_reason")
            or card.get("avoid_reason_if_weak")
            or card.get("diagnostic")
        )
        for field_name in (
            "title",
            "caption",
            "public_takeaway",
            "so_what",
            "now_what",
        ):
            value = _sanitize_public_prose(card.get(field_name))
            if value:
                item = _item(
                    "chart_insight_cards",
                    f"chart_insight_cards:{index}.{field_name}",
                    value,
                    evidence_ids,
                    "insights_bundle",
                    evidence_text=evidence_text,
                )
                _annotate_verified_item(item, artifacts)
                add_item(item)
        if limitation:
            item = _item(
                "chart_insight_cards",
                f"chart_insight_cards:{index}.limitation",
                limitation,
                evidence_ids,
                "insights_bundle",
                evidence_text=evidence_text,
            )
            _annotate_verified_item(item, artifacts)
            add_item(item)

    verified_index = _verified_fact_index(artifacts)

    def has_verified_binding(evidence_ids: list[str]) -> bool:
        return not verified_facts_mode(artifacts) or any(
            fact_for_evidence_id(verified_index, evidence_id) is not None
            for evidence_id in evidence_ids
        )

    advisory = artifacts.get("executive_advisory")
    advisory_payload = advisory if isinstance(advisory, Mapping) else {}
    decision_brief = advisory_payload.get("decision_brief")
    decision_payload = decision_brief if isinstance(decision_brief, Mapping) else {}
    decision_evidence_ids = _surface_evidence_ids(decision_payload)
    if str(
        decision_payload.get("status") or ""
    ).strip().casefold() == "generated" and has_verified_binding(decision_evidence_ids):
        for field_name in (
            "strategic_context",
            "confidence_note",
        ):
            value = _sanitize_public_prose(decision_payload.get(field_name))
            if value:
                item = _item(
                    "executive_advisory",
                    f"decision_brief.{field_name}",
                    value,
                    decision_evidence_ids,
                    "executive_advisory",
                    evidence_text=str(
                        decision_payload.get("evidence")
                        or decision_payload.get("source_excerpt")
                        or ""
                    ).strip(),
                )
                _annotate_verified_item(item, artifacts)
                add_item(item)
        for field_name in ("decision_implications", "priority_moves", "watchouts"):
            for index, raw_value in enumerate(
                decision_payload.get(field_name) or [], start=1
            ):
                value = _sanitize_public_prose(raw_value)
                if not value:
                    continue
                item = _item(
                    "executive_advisory",
                    f"decision_brief.{field_name}:{index}",
                    value,
                    decision_evidence_ids,
                    "executive_advisory",
                )
                _annotate_verified_item(item, artifacts)
                add_item(item)

    for index, claim in enumerate(_dict_items(artifacts.get("claim_ledgers")), start=1):
        value = _sanitize_public_prose(claim.get("claim_text"))
        evidence_ids = _surface_evidence_ids(claim)
        if not value or not has_verified_binding(evidence_ids):
            continue
        item = _item(
            "claim_ledgers",
            f"claim:{index}",
            value,
            evidence_ids,
            "executive_advisory",
            evidence_text=str(
                claim.get("evidence") or claim.get("source_excerpt") or ""
            ).strip(),
        )
        _annotate_verified_item(item, artifacts)
        add_item(item)

    raw_topics = artifacts.get("toc_topics")
    topics = [
        str(value).strip()
        for value in (raw_topics if isinstance(raw_topics, list) else [])
        if str(value).strip()
    ]
    if not topics:
        topics = [
            str(item.get("title") or item.get("display_title") or "").strip()
            for item in _dict_items(artifacts.get("toc_entries"))
            if str(item.get("title") or item.get("display_title") or "").strip()
        ]
    topic_briefs = _coerce_topic_briefs(artifacts)
    raw_tags = artifacts.get("taxonomy")
    tags = raw_tags if isinstance(raw_tags, list) else []
    topic_evidence_by_title: dict[str, list[str]] = {}
    for raw_group in (
        artifacts.get("topics_covered"),
        artifacts.get("toc_topics_expanded"),
        artifacts.get("toc_entries"),
    ):
        for raw_item in _dict_items(raw_group):
            title = str(
                raw_item.get("topic")
                or raw_item.get("title")
                or raw_item.get("display_title")
                or ""
            ).strip()
            if title:
                evidence_ids = topic_evidence_by_title.setdefault(title.casefold(), [])
                for evidence_id in _surface_evidence_ids(raw_item):
                    if evidence_id not in evidence_ids:
                        evidence_ids.append(evidence_id)
    for index, signal in enumerate(
        _build_signal_cards(
            topics=topics,
            topic_briefs=topic_briefs,
            tags=tags,
            prefer_key_points=bool(artifacts.get("topics_covered")),
        ),
        start=1,
    ):
        text = _sanitize_public_prose(signal.get("signal") or signal.get("summary"))
        if not text:
            continue
        evidence_ids = topic_evidence_by_title.get(
            str(signal.get("title") or "").casefold(), []
        )
        if not has_verified_binding(evidence_ids):
            continue
        item = _item(
            "signal_cards",
            f"signal:{index}",
            text,
            evidence_ids,
            "insights_bundle",
        )
        _annotate_verified_item(item, artifacts)
        add_item(item)

    return items


def _verified_public_semantic_review_items(
    artifacts: dict[str, Any],
) -> list[dict[str, Any]]:
    """Project the verified review batch from the same rows the HTML uses.

    Verified review must see visible cards, not every intermediate artifact
    that happens to be retained.  Derived cards keep an internal source path
    for the planner; that path is never sent as public copy to the model.
    """

    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_text_by_id: dict[str, str] = {}
    retained_evidence_text = _retained_public_evidence_text_by_id(artifacts)

    def add(item: dict[str, Any]) -> None:
        item_id = str(item.get("public_item_id") or "").strip()
        text = str(item.get("text") or "").strip()
        if not item_id or not text:
            return
        _attach_retained_evidence_text(item, retained_evidence_text)
        normalized_text = " ".join(text.split()).casefold()
        if item_id in seen_ids:
            if seen_text_by_id.get(item_id) != normalized_text:
                raise AppError(
                    code="public_editorial_review_identity_conflict",
                    message=(
                        "Distinct visible public text resolved to the same stable "
                        "review identity."
                    ),
                    retryable=False,
                    context={
                        "public_item_id": item_id,
                        "reason": "duplicate_public_item_id_with_distinct_text",
                    },
                )
            return
        seen_ids.add(item_id)
        seen_text_by_id[item_id] = normalized_text
        _annotate_verified_item(item, artifacts)
        items.append(item)

    def display_text(*values: object) -> str:
        return " ".join(
            value
            for value in (_sanitize_public_prose(value) for value in values)
            if value
        )

    def unique_insight_source(
        identity: str, *, field: str = "text"
    ) -> tuple[str, str] | None:
        safe_identity = str(identity or "").strip()
        if not safe_identity:
            return None
        for root in ("insights_final", "insights_candidates"):
            matches = [
                insight
                for insight in _dict_items(artifacts.get(root))
                if safe_identity
                in {
                    str(insight.get("id") or "").strip(),
                    str(insight.get("insight_id") or "").strip(),
                }
            ]
            if len(matches) != 1:
                continue
            if not _has_scalar_path(matches[0], field):
                return None
            return "insights_bundle", f"insights:{safe_identity}.{field}"
        return None

    def unique_text_source(text: str) -> tuple[str, str] | None:
        normalized = " ".join(str(text or "").split()).casefold()
        if not normalized:
            return None
        matches: list[tuple[str, str]] = []
        for insight in _dict_items(artifacts.get("insights_final")):
            identity = insight_entity_id(insight)
            if not identity:
                continue
            for field in ("text", "so_what", "now_what"):
                value = " ".join(str(insight.get(field) or "").split()).casefold()
                if value and value == normalized:
                    matches.append(("insights_bundle", f"insights:{identity}.{field}"))
        if len(matches) == 1:
            return matches[0]
        return None

    def claim_source(claim: Mapping[str, Any]) -> tuple[str, str] | None:
        section = str(claim.get("artifact_section") or "").strip()
        canonical_id = str(
            claim.get("canonical_claim_id") or claim.get("claim_id") or ""
        ).strip()
        local_id = canonical_id.rsplit(":", 1)[-1] if canonical_id else ""
        if section == "metric_spine" and local_id:
            return unique_insight_source(local_id, field="metric_public_copy")
        if section == "insights_final" and local_id:
            return unique_insight_source(local_id, field="text")
        if section == "quotes_final" and local_id:
            matches = [
                quote
                for quote in _dict_items(artifacts.get("quotes_final"))
                if str(quote.get("id") or "").strip() == local_id
            ]
            if not matches and local_id.isdigit():
                index = int(local_id) - 1
                quotes = _dict_items(artifacts.get("quotes_final"))
                if 0 <= index < len(quotes):
                    matches = [quotes[index]]
            if len(matches) == 1 and _has_scalar_path(matches[0], "text"):
                quote_identity = str(matches[0].get("id") or local_id).strip()
                return "quotes", f"quotes:{quote_identity}.text"
        if section == "summary.claim_evidence_map" and local_id:
            summary_claims = (
                artifacts.get("summary", {}).get("claim_evidence_map")
                if isinstance(artifacts.get("summary"), Mapping)
                else []
            )
            if isinstance(summary_claims, list):
                if local_id.isdigit() and 0 < int(local_id) <= len(summary_claims):
                    return "summary", f"summary.claim_evidence_map:{local_id}.claim"
                if any(
                    isinstance(entry, Mapping)
                    and local_id
                    in {
                        str(entry.get("id") or "").strip(),
                        str(entry.get("claim_id") or "").strip(),
                    }
                    for entry in summary_claims
                ):
                    return "summary", f"summary.claim_evidence_map:{local_id}.claim"
        if section.startswith("executive_advisory."):
            return unique_text_source(str(claim.get("claim_text") or ""))
        return None

    def advisory_source(text: str, field: str) -> tuple[str, str] | None:
        direct = unique_text_source(text)
        if direct:
            return direct
        # Advisory fields are derived from insight implications.  Resolve
        # only the exact, unique source field; topic or evidence similarity is
        # insufficient to authorize a repair.
        source_field = {
            "decision_implications": "so_what",
            "priority_moves": "now_what",
            "watchouts": "text",
        }.get(field)
        if not source_field:
            return None
        matches: list[tuple[str, str]] = []
        normalized = " ".join(str(text or "").split()).casefold()
        for insight in _dict_items(artifacts.get("insights_final")):
            identity = insight_entity_id(insight)
            value = " ".join(str(insight.get(source_field) or "").split()).casefold()
            if identity and value and value == normalized:
                matches.append(
                    ("insights_bundle", f"insights:{identity}.{source_field}")
                )
        return matches[0] if len(matches) == 1 else None

    # Summary and downstream copy use the existing evidence-aware producer.
    # card_tldr_compact is intentionally excluded: verified HTML renders tldr,
    # not that intermediate compact presentation field.
    for item in _public_text_items(artifacts):
        if str(item.get("field") or "") == "card_tldr_compact":
            continue
        add(item)

    for insight in _dict_items(artifacts.get("insights_final")):
        identity = insight_entity_id(insight)
        if not identity:
            continue
        evidence_ids = _public_evidence_ids(insight)
        evidence_text = str(
            insight.get("evidence") or insight.get("source_excerpt") or ""
        ).strip()
        for field in ("text", "so_what", "now_what"):
            value = _sanitize_public_prose(insight.get(field))
            if not value:
                continue
            field_name = (
                f"insights:{identity}"
                if field == "text"
                else f"insights:{identity}.{field}"
            )
            add(
                _item(
                    "insights_final",
                    field_name,
                    value,
                    evidence_ids,
                    "insights_bundle",
                    evidence_text=evidence_text,
                )
            )

    summary = artifacts.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    for index, claim in enumerate(
        (summary.get("claim_evidence_map") or [])[:3], start=1
    ):
        if not isinstance(claim, Mapping):
            continue
        value = _sanitize_public_prose(claim.get("claim"))
        if not value:
            continue
        evidence_ids = _surface_evidence_ids(claim)
        if not any(
            fact_for_evidence_id(_verified_fact_index(artifacts), evidence_id)
            is not None
            for evidence_id in evidence_ids
        ):
            continue
        add(
            _item(
                "summary",
                f"summary.claim_evidence_map:{index}.claim",
                value,
                evidence_ids,
                "summary",
                evidence_text=str(
                    claim.get("evidence") or claim.get("source_excerpt") or ""
                ).strip(),
            )
        )

    for index, topic in enumerate(_coerce_public_topics_covered(artifacts), start=1):
        evidence_ids = list(topic.get("evidence_ids") or [])
        text = display_text(
            topic.get("topic"),
            topic.get("summary"),
            " ".join(str(value) for value in topic.get("subtopics") or []),
            topic.get("source_label"),
        )
        if not text:
            continue
        topic_id = str(topic.get("topic_id") or index).strip()
        add(
            _item(
                "topics_covered",
                f"topics_covered:{topic_id}",
                text,
                evidence_ids,
                "topics",
                repair_field=f"topics_covered:{topic_id}",
            )
        )

    public_advisory = _coerce_public_advisory(artifacts)
    for index, figure in enumerate(public_advisory.get("key_figures") or [], start=1):
        figure_id = str(figure.get("figure_id") or index).strip()
        source = unique_insight_source(
            str(figure.get("metric_id") or figure_id), field="metric_public_copy"
        )
        target, repair_field = source or ("", "")
        add(
            _item(
                "key_figures",
                f"key_figures:{figure_id}",
                str(figure.get("public_copy") or "").strip(),
                list(figure.get("evidence_ids") or []),
                target,
                repair_field=repair_field
                if target
                else f"key_figures:{figure_id}.figure",
            )
        )

    for index, metric in enumerate(public_advisory.get("metric_spine") or [], start=1):
        metric_id = str(metric.get("metric_id") or index).strip()
        source = unique_insight_source(metric_id, field="metric_public_copy")
        target, repair_field = source or ("", "")
        add(
            _item(
                "metric_spine",
                f"metric_spine:{metric_id}",
                str(metric.get("public_copy") or "").strip(),
                list(metric.get("evidence_ids") or []),
                target,
                repair_field=repair_field or f"metric_spine:{metric_id}.public_copy",
            )
        )

    for index, card in enumerate(
        _coerce_public_chart_insight_cards(artifacts), start=1
    ):
        card_id = str(card.get("candidate_id") or index).strip()
        source = unique_insight_source(str(card.get("insight_id") or ""))
        target, repair_field = source or ("", "")
        add(
            _item(
                "chart_insight_cards",
                f"chart_insight_cards:{card_id}",
                display_text(
                    card.get("title"),
                    card.get("insight"),
                    card.get("so_what"),
                    card.get("now_what"),
                    card.get("limitation"),
                ),
                _public_evidence_ids(card),
                target,
                repair_field=repair_field,
            )
        )

    # Match the renderer's advisory de-duplication: implications and moves
    # copied verbatim from findings are not rendered a second time.
    advisory = artifacts.get("executive_advisory")
    advisory = advisory if isinstance(advisory, Mapping) else {}
    decision = advisory.get("decision_brief")
    decision = decision if isinstance(decision, Mapping) else {}
    decision_evidence_ids = _surface_evidence_ids(decision)
    fact_index = _verified_fact_index(artifacts)
    decision_supported = str(
        decision.get("status") or ""
    ).strip().casefold() == "generated" and any(
        fact_for_evidence_id(fact_index, evidence_id) is not None
        for evidence_id in decision_evidence_ids
    )
    insight_so_what = {
        " ".join(str(insight.get("so_what") or "").split()).casefold()
        for insight in _dict_items(artifacts.get("insights_final"))
        if str(insight.get("so_what") or "").strip()
    }
    insight_now_what = {
        " ".join(str(insight.get("now_what") or "").split()).casefold()
        for insight in _dict_items(artifacts.get("insights_final"))
        if str(insight.get("now_what") or "").strip()
    }
    if decision_supported:
        for field in ("strategic_context", "confidence_note"):
            value = _sanitize_public_prose(decision.get(field))
            if value.casefold() in {
                "metric spine available",
                "evidence-linked insights available",
            }:
                value = ""
            if not value:
                continue
            item_evidence_ids = verified_advisory_evidence_ids(artifacts, field, value)
            if not item_evidence_ids:
                continue
            source = advisory_source(value, field)
            target, repair_field = source or ("", "")
            add(
                _item(
                    "executive_advisory",
                    f"decision_brief.{field}",
                    value,
                    item_evidence_ids,
                    target,
                    evidence_text=str(
                        decision.get("evidence") or decision.get("source_excerpt") or ""
                    ).strip(),
                    repair_field=repair_field,
                )
            )
        for field in ("decision_implications", "priority_moves", "watchouts"):
            for index, raw_value in enumerate(decision.get(field) or [], start=1):
                value = _sanitize_public_prose(raw_value)
                normalized = " ".join(value.split()).casefold()
                if (
                    not value
                    or (
                        field == "decision_implications"
                        and normalized in insight_so_what
                    )
                    or (field == "priority_moves" and normalized in insight_now_what)
                ):
                    continue
                item_evidence_ids = verified_advisory_evidence_ids(
                    artifacts, field, value
                )
                if not item_evidence_ids:
                    continue
                source = advisory_source(value, field)
                target, repair_field = source or ("", "")
                add(
                    _item(
                        "executive_advisory",
                        f"decision_brief.{field}:{index}",
                        value,
                        item_evidence_ids,
                        target,
                        repair_field=repair_field,
                    )
                )

    for index, claim in enumerate(public_advisory.get("claim_support") or [], start=1):
        source = claim_source(claim)
        target, repair_field = source or ("", "")
        add(
            _item(
                "claim_ledgers",
                f"claim:{index}",
                str(claim.get("claim") or "").strip(),
                list(claim.get("evidence_ids") or []),
                target,
                repair_field=repair_field,
            )
        )

    # Quotes are already a final public family; unlike derived cards, their
    # text is the authoritative producer output and routes to quotes_final.
    for index, quote in enumerate(
        _dict_items(artifacts.get("quotes_final"))[:6], start=1
    ):
        value = _sanitize_public_prose(quote.get("text"))
        if not value:
            continue
        quote_id = str(quote.get("id") or index).strip()
        add(
            _item(
                "quotes_final",
                f"quotes:{quote_id}",
                value,
                _public_evidence_ids(quote),
                "quotes",
                evidence_text=str(
                    quote.get("evidence") or quote.get("source_excerpt") or ""
                ).strip(),
                repair_field=f"quotes:{quote_id}.text",
            )
        )

    return items


def public_editorial_report_review_scope(
    artifacts: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    source_identity: str = "",
    verified_fact_digest: str = "",
    evidence_packs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the report-level context for the existing semantic review call.

    Item projections remain the authority for atomic source-fidelity checks.
    This companion projection gives the same call enough context to assess
    omissions, repetition, analytical depth, and report usefulness without
    repeating the complete fact snapshot or atomic public text on every item.
    The complete text remains in the top-level public-item batch.
    """

    safe_artifacts = artifacts if isinstance(artifacts, dict) else {}
    facts = _verified_fact_index(safe_artifacts)
    canary = (
        safe_artifacts.get("_cache", {}).get("visual_authority_canary")
        if isinstance(safe_artifacts.get("_cache"), Mapping)
        else None
    )
    first_fact = next(iter(facts.values()), {})
    resolved_source_identity = (
        str(source_identity or "").strip()
        or str(first_fact.get("source_identity") or "").strip()
    )
    resolved_digest = (
        str(verified_fact_digest or "").strip()
        or str(
            canary.get("verified_fact_digest") or canary.get("digest") or ""
            if isinstance(canary, Mapping)
            else ""
        ).strip()
    )

    evidence_context: dict[str, dict[str, Any]] = {}
    public_content: list[dict[str, Any]] = []
    surface_roles = {
        "summary": "summary_or_orientation",
        "insights_final": "primary_analysis",
        "expert_comment": "expert_synthesis",
        "linkedin_post": "distribution_copy",
    }
    reuse_guidance = (
        "The same bound fact may recur for orientation, distribution, or provenance; "
        "treat it as a distinctness failure only when the same substantive analysis "
        "is repeated as primary content without a new role or purpose."
    )
    for item in items:
        item_id = str(item.get("public_item_id") or "").strip()
        if not item_id:
            continue
        evidence_ids = _public_evidence_ids(item)
        evidence_text = str(item.get("evidence_text") or "").strip()
        for evidence_id in evidence_ids:
            entry = evidence_context.setdefault(
                evidence_id,
                {"evidence_id": evidence_id, "texts": []},
            )
            if evidence_text and evidence_text not in entry["texts"]:
                entry["texts"].append(evidence_text)
        public_content.append(
            {
                "item_id": item_id,
                "artifact": str(item.get("artifact") or ""),
                "field": str(item.get("field") or ""),
                "evidence_ids": evidence_ids,
                "surface_role": surface_roles.get(
                    str(item.get("artifact") or "").strip(),
                    "supporting_projection",
                ),
            }
        )

    editorial_plan = safe_artifacts.get("editorial_plan")
    render_evidence_packs: dict[str, Any] = {}
    if isinstance(evidence_packs, dict):
        render_evidence_packs = evidence_packs
    elif isinstance(safe_artifacts.get("evidence_packs"), dict):
        render_evidence_packs = safe_artifacts["evidence_packs"]
    rendered_limitations = _coerce_limitation_items(
        render_evidence_packs,
        verified_mode=verified_facts_mode(safe_artifacts),
        artifacts=safe_artifacts,
    )
    return {
        "authority": "canonical_verified_facts" if facts else "retained_evidence",
        "source_identity": resolved_source_identity,
        "source_pdf_sha256": str(first_fact.get("source_pdf_sha256") or "").strip(),
        "verified_fact_digest": resolved_digest,
        "verified_facts": {
            f"verified-fact:{fact_id}": deepcopy(fact)
            for fact_id, fact in facts.items()
        },
        "editorial_plan": deepcopy(editorial_plan)
        if isinstance(editorial_plan, (dict, list))
        else {},
        "evidence_context": list(evidence_context.values()),
        "public_content": public_content,
        "rendered_limitations": rendered_limitations,
        "reuse_guidance": reuse_guidance,
    }


def _retained_soft_copy_sentence_items(
    *,
    artifacts: dict[str, Any],
    artifact: str,
    field: str,
    text: str,
    evidence_items: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Expose sentence claims only when retained provenance proves each match."""

    try:
        claims = soft_copy_claim_provenance_from_payload(
            artifacts.get("soft_copy_claim_provenance")
        )
    except AppError:
        return []
    by_hash: dict[str, list[Any]] = {}
    for claim in claims:
        if claim.artifact_family == artifact:
            by_hash.setdefault(claim.text_hash, []).append(claim)
    sentences = [
        " ".join(sentence.split())
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if " ".join(sentence.split())
    ]
    matched = [
        by_hash.get(hashlib.sha256(sentence.encode("utf-8")).hexdigest(), [])
        for sentence in sentences
    ]
    if not sentences or any(len(items) != 1 for items in matched):
        return []
    evidence_by_id = dict(evidence_items)
    items: list[dict[str, Any]] = []
    for sentence, claim_items in zip(sentences, matched, strict=True):
        claim = claim_items[0]
        item = _item(
            artifact,
            field,
            sentence,
            list(claim.evidence_ids),
            artifact,
            evidence_text=" ".join(
                evidence_by_id[evidence_id]
                for evidence_id in claim.evidence_ids
                if evidence_id in evidence_by_id
            ),
        )
        item["public_item_id"] = claim.claim_id
        items.append(item)
    return items


def _public_inventory_text_items(artifacts: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Enumerate each public surface once while retaining all source bindings."""

    summary_value = artifacts.get("summary")
    summary: dict[str, Any] = summary_value if isinstance(summary_value, dict) else {}
    summary_evidence = _summary_evidence_items(summary)
    summary_ids = [evidence_id for evidence_id, _ in summary_evidence]
    summary_text = " ".join(text for _, text in summary_evidence)
    for field_name in ("tldr", "card_tldr_compact", "executive_summary"):
        value = _sanitize_public_prose(summary.get(field_name))
        if value:
            yield _item(
                "summary",
                field_name,
                value,
                summary_ids,
                "summary",
                evidence_text=summary_text,
            )
    downstream_evidence = _downstream_evidence_items(artifacts)
    downstream_ids = [evidence_id for evidence_id, _ in downstream_evidence]
    downstream_text = " ".join(text for _, text in downstream_evidence)
    for field_name in ("expert_comment", "linkedin_post"):
        value = _sanitize_public_prose(artifacts.get(field_name))
        if value:
            yield _item(
                field_name,
                field_name,
                value,
                downstream_ids,
                field_name,
                evidence_text=downstream_text,
            )


def _issue(
    report_id: str, rule_id: str, item: dict[str, Any], explanation: str
) -> PublicEditorialQualityIssue:
    evidence_ids = list(item.get("evidence_ids") or [])
    eligible = bool(
        item.get("repair_target") == "metadata"
        or (
            evidence_ids
            and str(item.get("evidence_text") or "").strip()
            and item.get("repair_target")
        )
    )
    return PublicEditorialQualityIssue(
        report_id=str(report_id),
        rule_id=rule_id,
        severity="error" if rule_id in BLOCKING_RULE_IDS else "warning",
        affected_artifact=str(item["artifact"]),
        affected_field=str(item.get("repair_field") or item["field"]),
        evidence_ids=evidence_ids,
        explanation=explanation,
        repair_eligible=eligible,
        repair_status="not_requested" if eligible else "abstained",
        repair_target=str(item.get("repair_target") or "") if eligible else "",
        public_item_id=str(item.get("public_item_id") or ""),
        hard_fail_class=_hard_fail_class(rule_id, explanation),
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
    repair_field: str = "",
) -> dict[str, Any]:
    return {
        "artifact": artifact,
        "field": field,
        "text": text,
        "evidence_ids": [value for value in evidence_ids if value],
        "repair_target": repair_target,
        "evidence_status": evidence_status,
        "evidence_text": evidence_text,
        "repair_field": repair_field,
        "public_item_id": _public_item_id(artifact, field),
    }


def _public_item_id(artifact: str, field: str) -> str:
    """Return a stable atomic identifier without retaining public copy."""
    normalized_artifact = str(artifact or "").strip() or "item"
    normalized_field = str(field or "").strip().replace(".", ":")
    if normalized_artifact == "insights_final" and normalized_field.startswith(
        "insights:"
    ):
        _, insight_id, *suffix = normalized_field.split(":")
        return f"insight:{insight_id}:{suffix[0] if suffix else 'text'}"
    return f"{normalized_artifact}:{normalized_field or 'text'}"


def _hard_fail_class(rule_id: str, explanation: str) -> str:
    if rule_id == "public_editorial_quality.temporal_integrity":
        return (
            "forecast_represented_as_observed"
            if "forecast marker" in explanation
            else "incorrect_timeframe"
        )
    if rule_id == "public_editorial_quality.metric_label_relationship":
        return (
            "incorrect_denominator_cohort_geography"
            if "cohort" in explanation or "denominator" in explanation
            else "incorrect_value_label_relationship"
        )
    return HARD_FAIL_CLASS_BY_RULE_ID.get(rule_id, "")


def enumerate_public_editorial_items(
    artifacts: dict[str, Any],
) -> list[PublicEditorialQualityItem]:
    """Enumerate public artifact surfaces without retaining their public text.

    The item list is intentionally independent of pass/fail findings so a
    source-fidelity auditor can account for every material public projection.
    """
    items: list[dict[str, Any]] = list(_public_inventory_text_items(artifacts))
    for insight in _dict_items(artifacts.get("insights_final")):
        insight_id = insight_entity_id(insight)
        if not insight_id:
            continue
        evidence_id = str(insight.get("evidence_id") or "").strip()
        for field_name in ("text", "so_what", "now_what"):
            if _sanitize_public_prose(insight.get(field_name)):
                items.append(
                    _item(
                        "insights_final",
                        f"insights:{insight_id}.{field_name}"
                        if field_name != "text"
                        else f"insights:{insight_id}",
                        _sanitize_public_prose(insight.get(field_name)),
                        [evidence_id] if evidence_id else [],
                        "insights_bundle",
                        evidence_text=str(insight.get("evidence") or ""),
                    )
                )
    for index, figure in enumerate(_dict_items(artifacts.get("key_figures")), start=1):
        evidence_id = str(figure.get("evidence_id") or "").strip()
        for field_name in ("label", "figure", "why_it_matters"):
            if _sanitize_public_prose(figure.get(field_name)):
                items.append(
                    _item(
                        "key_figures",
                        f"key_figures:{index}.{field_name}",
                        _sanitize_public_prose(figure.get(field_name)),
                        [evidence_id] if evidence_id else [],
                        "insights_bundle",
                    )
                )
    for index, quote in enumerate(_dict_items(artifacts.get("quotes_final")), start=1):
        if _sanitize_public_prose(quote.get("text")):
            items.append(
                _item(
                    "quotes_final",
                    f"quotes:{quote.get('id') or index}",
                    _sanitize_public_prose(quote.get("text")),
                    _string_list(quote.get("evidence_id")),
                    "quotes",
                )
            )
    for index, card in enumerate(
        _dict_items(artifacts.get("chart_insight_cards")), start=1
    ):
        for field_name in ("title", "caption", "public_takeaway"):
            if _sanitize_public_prose(card.get(field_name)):
                items.append(
                    _item(
                        "chart_insight_cards",
                        f"chart_insight_cards:{index}.{field_name}",
                        _sanitize_public_prose(card.get(field_name)),
                        _string_list(card.get("evidence_id")),
                        "insights_bundle",
                    )
                )
    metadata = artifacts.get("public_metadata")
    if isinstance(metadata, dict):
        for field_name in (
            "title",
            "publisher",
            "author",
            "edition",
            "publication_date",
        ):
            if str(metadata.get(field_name) or "").strip():
                items.append(
                    _item(
                        "public_metadata",
                        f"metadata.{field_name}",
                        str(metadata[field_name]).strip(),
                        [],
                        "metadata",
                    )
                )
    deduped = {item["public_item_id"]: item for item in items}
    return [
        PublicEditorialQualityItem(
            item_id=item_id,
            artifact=str(item["artifact"]),
            field_path=str(item["field"]),
            evidence_ids=list(item["evidence_ids"]),
            repair_target=str(item["repair_target"]),
        )
        for item_id, item in sorted(deduped.items())
    ]


def _metadata_issues(
    report_id: str,
    artifacts: dict[str, Any],
    metadata_evidence: Mapping[str, object],
    *,
    html: str = "",
) -> list[PublicEditorialQualityIssue]:
    """Fail closed when rendered metadata conflicts with retained identity evidence."""
    actual = dict(artifacts.get("public_metadata") or {})
    json_ld_actual: dict[str, str] = {}
    if html:
        document = BeautifulSoup(html, "html.parser")
        title_node = document.select_one("h1#report-title")
        if title_node:
            actual["title"] = title_node.get_text(" ", strip=True)
        for node in document.select(".meta-row .meta-pill"):
            label, separator, value = node.get_text(" ", strip=True).partition(":")
            if separator and label.casefold() in {
                "publisher",
                "author",
                "edition",
                "published",
            }:
                actual[
                    "publication_date"
                    if label.casefold() == "published"
                    else label.casefold()
                ] = value.strip()
        for node in document.select('script[type="application/ld+json"]'):
            try:
                payload = json.loads(node.get_text(strip=True))
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            for field_name in ("publisher", "author"):
                json_ld_value = payload.get(field_name)
                if isinstance(json_ld_value, dict):
                    name = str(json_ld_value.get("name") or "").strip()
                    if name:
                        json_ld_actual[field_name] = name
    if not actual:
        return []
    issues: list[PublicEditorialQualityIssue] = []
    for field_name, hard_fail_class in (
        ("title", "incorrect_report_identity"),
        ("publisher", "incorrect_publisher_author_attribution"),
        ("author", "incorrect_publisher_author_attribution"),
        ("edition", "incorrect_timeframe"),
        ("publication_date", "incorrect_timeframe"),
    ):
        expected = str(metadata_evidence.get(field_name) or "").strip()
        observed = str(actual.get(field_name) or "").strip()
        if not expected or not observed:
            continue
        generic_title = field_name == "title" and _is_generic_public_title(observed)
        if generic_title or _normalized_text(expected) != _normalized_text(observed):
            item = _item(
                "rendered_html" if html else "public_metadata",
                f"metadata.{field_name}",
                observed,
                [],
                "metadata",
            )
            issue = _issue(
                report_id,
                "public_editorial_quality.metadata_identity",
                item,
                "uses a generic title despite retained identity evidence"
                if generic_title
                else "does not match retained source identity evidence",
            )
            issues.append(
                PublicEditorialQualityIssue(
                    **{
                        **issue.__dict__,
                        "hard_fail_class": hard_fail_class,
                        "severity": "error",
                    }
                )
            )
    for field_name in ("publisher", "author"):
        expected = str(metadata_evidence.get(field_name) or "").strip()
        observed = json_ld_actual.get(field_name, "")
        if (
            not expected
            or not observed
            or _normalized_text(expected) == _normalized_text(observed)
        ):
            continue
        item = _item(
            "rendered_html",
            f"json_ld.{field_name}",
            observed,
            [],
            "metadata",
        )
        issue = _issue(
            report_id,
            "public_editorial_quality.metadata_identity",
            item,
            "JSON-LD does not match retained source identity evidence",
        )
        issues.append(
            PublicEditorialQualityIssue(
                **{
                    **issue.__dict__,
                    "hard_fail_class": "incorrect_publisher_author_attribution",
                    "severity": "error",
                }
            )
        )
    return issues


def _is_generic_public_title(value: str) -> bool:
    return _normalized_text(value) in {
        "powerpoint presentation",
        "presentation",
        "report",
        "untitled",
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


def _has_scalar_path(value: Mapping[str, Any], path: str) -> bool:
    current: Any = value
    for segment in str(path or "").split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return False
        current = current[segment]
    return not isinstance(current, (dict, list))


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return (
        [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, list)
        else []
    )


def _public_evidence_ids(item: Mapping[str, Any]) -> list[str]:
    """Return all retained evidence bindings in stable primary-first order."""

    values = [
        *_string_list(item.get("evidence_id")),
        *_string_list(item.get("evidence_ids")),
    ]
    return list(dict.fromkeys(value for value in values if value))


def _retained_public_evidence_text_by_id(
    artifacts: Mapping[str, Any],
) -> dict[str, str]:
    """Index source text already retained on public artifact projections.

    Derived public surfaces often retain only an evidence ID.  Resolve those
    IDs from final insight/summary/quote spans so the semantic reviewer sees
    the same source context without borrowing by topic or wording.
    """

    text_by_id: dict[str, list[str]] = {}

    def add(evidence_id: object, text: object) -> None:
        normalized_id = str(evidence_id or "").strip()
        normalized_text = " ".join(str(text or "").split()).strip()
        if not normalized_id or not normalized_text:
            return
        values = text_by_id.setdefault(normalized_id, [])
        if normalized_text not in values:
            values.append(normalized_text)

    def add_record(record: Mapping[str, Any]) -> None:
        for raw_span in record.get("evidence_spans") or []:
            if isinstance(raw_span, Mapping):
                add(raw_span.get("evidence_id"), raw_span.get("text"))
        record_text = record.get("evidence") or record.get("source_excerpt")
        for evidence_id in _public_evidence_ids(record):
            add(evidence_id, record_text)

    for insight in _dict_items(artifacts.get("insights_final")):
        add_record(insight)
    summary = artifacts.get("summary")
    if isinstance(summary, Mapping):
        for claim in summary.get("claim_evidence_map") or []:
            if isinstance(claim, Mapping):
                add_record(claim)
    for quote in _dict_items(artifacts.get("quotes_final")):
        add_record(quote)
    for card in _dict_items(artifacts.get("chart_insight_cards")):
        add_record(card)

    return {evidence_id: "; ".join(texts) for evidence_id, texts in text_by_id.items()}


def _attach_retained_evidence_text(
    item: dict[str, Any], evidence_text_by_id: Mapping[str, str]
) -> None:
    if str(item.get("evidence_text") or "").strip():
        return
    evidence_text = "; ".join(
        evidence_text_by_id[evidence_id]
        for evidence_id in _public_evidence_ids(item)
        if evidence_id in evidence_text_by_id
    )
    if evidence_text:
        item["evidence_text"] = evidence_text


def _surface_evidence_ids(item: Mapping[str, Any]) -> list[str]:
    """Collect the existing source bindings for a rendered advisory surface."""

    values = _public_evidence_ids(item)
    values.extend(
        str(value).strip()
        for value in _string_list(item.get("evidence_links"))
        if str(value).strip()
    )
    return list(dict.fromkeys(value for value in values if value))


def _summary_evidence_items(summary: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (
            str(item.get("evidence_id") or "").strip(),
            str(item.get("evidence") or item.get("claim") or "").strip(),
        )
        for item in _dict_items(summary.get("claim_evidence_map"))
        if str(item.get("evidence_id") or "").strip()
        and str(item.get("evidence") or item.get("claim") or "").strip()
    ]


def _downstream_evidence_items(artifacts: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (
            str(item.get("evidence_id") or "").strip(),
            str(item.get("evidence") or "").strip(),
        )
        for item in _dict_items(artifacts.get("insights_final"))
        if str(item.get("evidence_id") or "").strip()
        and str(item.get("evidence") or "").strip()
    ]


def _verified_fact_index(artifacts: object) -> dict[str, dict[str, Any]]:
    if not isinstance(artifacts, dict):
        return {}
    cached = artifacts.get("_verified_fact_index")
    if isinstance(cached, dict):
        return {
            str(key): value for key, value in cached.items() if isinstance(value, dict)
        }
    if not verified_facts_mode(artifacts):
        return {}
    try:
        return validated_verified_facts(artifacts)
    except AppError:
        return {}


def _verified_evidence_items(
    artifacts: object,
    evidence_ids: Iterable[str] | None = None,
) -> list[tuple[str, str]]:
    evidence_map = canonical_evidence_map(_verified_fact_index(artifacts))
    if evidence_ids is None:
        return list(evidence_map.items())
    return [
        (evidence_id, evidence_map[evidence_id])
        for evidence_id in dict.fromkeys(str(value).strip() for value in evidence_ids)
        if evidence_id in evidence_map
    ]


def _fact_for_item(
    artifacts: object, item: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    facts = _verified_fact_index(artifacts)
    matches = [
        fact_for_evidence_id(facts, evidence_id)
        for evidence_id in item.get("evidence_ids") or []
    ]
    matches = [fact for fact in matches if fact is not None]
    return matches[0] if len(matches) == 1 else None


def _annotate_verified_item(item: dict[str, Any], artifacts: object) -> None:
    if not verified_facts_mode(artifacts):
        return
    facts = _verified_fact_index(artifacts)
    item["verified_facts_mode"] = True
    # Preserve the canonical primary-first evidence order so prompt payloads
    # and their cache identities remain deterministic across runs.
    evidence_ids = _public_evidence_ids(item)
    canonical_texts = [
        canonical_evidence_map({fact_id: fact}).get(f"verified-fact:{fact_id}", "")
        for fact_id, fact in facts.items()
        if f"verified-fact:{fact_id}" in evidence_ids
    ]
    if canonical_texts:
        item["evidence_text"] = "; ".join(text for text in canonical_texts if text)
    bound_facts: dict[str, dict[str, Any]] = {}
    for evidence_id in evidence_ids:
        fact = fact_for_evidence_id(facts, evidence_id)
        if fact is None:
            continue
        fact_id = str(fact.get("fact_id") or "").strip()
        if fact_id:
            bound_facts[f"verified-fact:{fact_id}"] = deepcopy(dict(fact))
    if bound_facts:
        # Keep the complete canonical fact, including report-specific nested
        # metric fields, available to the independent semantic reviewer.
        item["verified_facts"] = bound_facts


def _temporal_integrity_explanation(text: str, evidence_text: str) -> str:
    """Identify only source-proven loss of a comparative time qualifier."""
    if _MALFORMED_TEMPORAL_COMPARISON.search(text):
        return "contains malformed comparative temporal wording"
    if not evidence_text:
        return ""

    claim_numbers = _material_numbers(text)
    if len(claim_numbers) < 2:
        return ""
    claim_qualifiers = _temporal_qualifiers(text)
    for source_sentence in _sentences(evidence_text):
        source_pairs = _number_temporal_qualifier_pairs(source_sentence)
        source_numbers = {number for number, _ in source_pairs}
        source_qualifiers = {
            qualifier for number, qualifier in source_pairs if number in claim_numbers
        }
        if len(source_numbers & claim_numbers) < 2 or len(source_qualifiers) < 2:
            continue
        if any(
            not _claim_retains_temporal_qualifier(qualifier, claim_qualifiers)
            for qualifier in source_qualifiers
        ):
            return "loses distinct source-proven comparative temporal qualifiers"
        if _FORECAST_MARKER.search(source_sentence) and not _FORECAST_MARKER.search(
            text
        ):
            return "loses the source-proven forecast marker for a period comparison"
    return ""


def _metric_label_relationship_explanation(text: str, evidence_text: str) -> str:
    """Reject a retained structured value when its source label changes."""
    if not evidence_text:
        return ""

    evidence_period_pairs = _period_value_pairs(evidence_text)
    claim_period_pairs = _period_value_pairs(text)
    for pair in claim_period_pairs:
        same_period_values = [
            value for period, value in evidence_period_pairs if period == pair[0]
        ]
        if any(
            _relationship_values_match(pair[1], value) is True
            for value in same_period_values
        ):
            continue
        other_period_values = [
            value for period, value in evidence_period_pairs if period != pair[0]
        ]
        if any(
            _relationship_values_match(pair[1], value) is True
            for value in other_period_values
        ):
            return "attaches a retained metric value to a different source period"

    evidence_category_pairs = _structured_category_value_pairs(evidence_text)
    ordered_table_relationships = _ordered_category_row_value_pairs(evidence_text)
    related_labels = tuple(
        sorted(
            {
                *(label for label, _value in evidence_category_pairs),
                *(
                    label
                    for region, category, _value in ordered_table_relationships
                    for label in (region, category)
                ),
            },
            key=lambda value: (-len(value), value.casefold()),
        )
    )
    validated_table_claims = {
        (region, category)
        for region, category, value in ordered_table_relationships
        if _has_relationship_value(
            value,
            _values_near_label(
                text,
                region,
                related_labels=related_labels,
                permitted_neighbor_labels=(category,),
            ),
        )
        and _has_relationship_value(
            value,
            _values_near_label(
                text,
                category,
                related_labels=related_labels,
                permitted_neighbor_labels=(region,),
            ),
        )
    }
    evidence_values_by_category: dict[str, set[str]] = {}
    if len(evidence_category_pairs) >= 2:
        for category, value in evidence_category_pairs:
            evidence_values_by_category.setdefault(category, set()).add(value)
        for category, values in evidence_values_by_category.items():
            if any(
                category in {region, column}
                for region, column in validated_table_claims
            ):
                continue
            for value in _values_near_label(
                text, category, related_labels=related_labels
            ):
                comparisons = [
                    _relationship_values_match(value, source_value)
                    for source_value in values
                ]
                if comparisons and all(result is False for result in comparisons):
                    if _combined_category_sum_matches(
                        text,
                        candidate_value=value,
                        values_by_category=evidence_values_by_category,
                    ):
                        continue
                    return (
                        "attaches a retained metric value to a different source "
                        "category"
                    )

    evidence_relationships = _subject_value_relationships(evidence_text)
    claim_relationships = _subject_value_relationships(text)
    values_by_relationship: dict[str, set[str]] = {}
    for relationship, value in evidence_relationships:
        values_by_relationship.setdefault(relationship, set()).add(value)
    evidence_values = {value for _relationship, value in evidence_relationships}
    for relationship, value in claim_relationships:
        # A value that occurs in retained evidence is not automatically valid:
        # it must remain bound to this exact subject and reported base.
        related_values = values_by_relationship.get(relationship, set())
        comparisons = [
            _relationship_values_match(value, source_value)
            for source_value in related_values
        ]
        if comparisons and all(result is False for result in comparisons):
            return (
                "attaches a retained metric value to a different source cohort "
                "or denominator"
            )
        if relationship not in values_by_relationship and _has_relationship_value(
            value, evidence_values
        ):
            subject = relationship.split(" | ", 1)[0]
            if any(
                source.startswith(f"{subject} | ") for source in values_by_relationship
            ):
                return (
                    "attaches a retained metric value to a different source denominator"
                )
    return ""


def _combined_category_sum_matches(
    text: str,
    *,
    candidate_value: str,
    values_by_category: Mapping[str, set[str]],
) -> bool:
    """Allow a rounded total only for explicitly joined source categories."""

    normalized = _normalized_relationship_search_text(text)
    label_matches: list[tuple[int, int, str]] = []
    for category in values_by_category:
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(category)}(?![A-Za-z0-9])", re.I
        )
        label_matches.extend(
            (match.start(), match.end(), category)
            for match in pattern.finditer(normalized)
        )
    label_matches.sort()
    category_mentions = Counter(label for _start, _end, label in label_matches)
    connector = re.compile(r"\s+(?:and|plus|along with|as well as|&)\s*", re.I)
    combined_predicate = re.compile(
        r"^\s*(?:(?:alone|together|combined|collectively|both|in total)\s+)?"
        r"(?:account(?:s|ed)? for|represent(?:s)?|make up|makes up|"
        r"contribute(?:s)?|comprise(?:s)?|total(?:s)?)\b",
        re.I,
    )
    for index, left in enumerate(label_matches):
        for right in label_matches[index + 1 :]:
            if left[2] == right[2]:
                continue
            if category_mentions != Counter({left[2]: 1, right[2]: 1}):
                continue
            if not connector.fullmatch(normalized[left[1] : right[0]]):
                continue
            if not combined_predicate.match(normalized[right[1] :]):
                continue
            left_values = values_by_category[left[2]]
            right_values = values_by_category[right[2]]
            if len(left_values) != 1 or len(right_values) != 1:
                continue
            left_quantities = extract_quantities(next(iter(left_values)))
            right_quantities = extract_quantities(next(iter(right_values)))
            claim_quantities = extract_quantities(candidate_value)
            if not (
                len(left_quantities)
                == len(right_quantities)
                == len(claim_quantities)
                == 1
            ):
                continue
            first, second, claim = (
                left_quantities[0],
                right_quantities[0],
                claim_quantities[0],
            )
            if (
                first.unit_family != "percent"
                or second.unit_family != "percent"
                or claim.unit_family != "percent"
            ):
                continue
            number = re.search(r"\d+(?:\.\d+)?", claim.raw)
            if not number:
                continue
            places = len(number.group(0).partition(".")[2])
            quantum = Decimal(1).scaleb(-places)
            try:
                total = Decimal(str(first.value)) + Decimal(str(second.value))
                rounded_total = total.quantize(quantum, rounding=ROUND_HALF_UP)
                claim_value = Decimal(str(claim.value)).quantize(quantum)
            except InvalidOperation:
                continue
            if rounded_total == claim_value:
                return True
    return False


def _ordered_category_row_value_pairs(text: str) -> set[tuple[str, str, str]]:
    """Bind compact table rows to explicit labels established by a prior row.

    Some retained evidence serializes the first row as labeled cells and later
    rows as positional values (for example ``APAC: X 1, Y 2; EMEA: 3, 4``).
    Infer only when the labeled row has unique columns and each compact row has
    exactly the same number of numeric cells. Ambiguous or incomplete rows do
    not create relationships.
    """

    column_labels: list[str] = []
    relationships: set[tuple[str, str, str]] = set()
    row_pattern = re.compile(
        r"^\s*(?P<region>[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,2})"
        r"\s*:\s*(?P<cells>.+?)\s*$"
    )
    for fragment in re.split(r"[;\n]|(?<=[.!?])\s+", text):
        row = row_pattern.match(fragment)
        if not row:
            continue
        region = _normalized_relationship_label(row.group("region"))
        cells = row.group("cells")
        explicit = [
            match
            for match in _CAPITALIZED_CATEGORY_VALUE_PAIR.finditer(cells)
            if not _is_year_value(_normalized_relationship_value(match.group("value")))
        ]
        if len(explicit) >= 2:
            labels = [
                _normalized_relationship_label(match.group("label"))
                for match in explicit
            ]
            if len(labels) == len(set(labels)):
                column_labels = labels
                relationships.update(
                    (
                        region,
                        label,
                        _normalized_relationship_value(match.group("value")),
                    )
                    for label, match in zip(labels, explicit, strict=True)
                )
            else:
                column_labels = []
            continue

        if not column_labels:
            continue
        values = [
            _normalized_relationship_value(match.group(0))
            for match in re.finditer(_RELATIONSHIP_VALUE, cells)
        ]
        if len(values) != len(column_labels) or any(_is_year_value(v) for v in values):
            continue
        relationships.update(
            (region, label, value)
            for label, value in zip(column_labels, values, strict=True)
        )
    return relationships


def _period_value_pairs(text: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for pattern in (_PERIOD_VALUE_PAIR, _VALUE_PERIOD_PAIR):
        for match in pattern.finditer(text):
            value = _normalized_relationship_value(match.group("value"))
            label = _normalized_relationship_label(match.group("label"))
            if value and label:
                pairs.add((label, value))
    return pairs


def _structured_category_value_pairs(text: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for pattern in (
        _COMMA_CATEGORY_VALUE_PAIR,
        _CAPITALIZED_CATEGORY_VALUE_PAIR,
        _DELIMITED_SPACE_CATEGORY_VALUE_PAIR,
        _DELIMITED_CATEGORY_VALUE_PAIR,
    ):
        for match in pattern.finditer(text):
            value = _normalized_relationship_value(match.group("value"))
            label = _normalized_category_value_label(match.group("label"))
            if (
                value
                and label
                and not _is_year_value(value)
                and not _is_demographic_age_threshold(
                    f"{match.group('label')} {match.group('value')}",
                    len(match.group("label")) + 1,
                    len(match.group(0)),
                )
                and "cagr" not in label.split()
            ):
                pairs.add((label, value))
    # A comma-separated category such as "Apparel, Shoes, and Accessories"
    # also matches the trailing token "Accessories" through the generic
    # capitalized parser. Keep the most specific label when both bindings carry
    # the same value so the short parser match cannot create a false swap.
    return {
        (label, value)
        for label, value in pairs
        if not any(
            label != other_label
            and value == other_value
            and (
                other_label.endswith(f" {label}") or other_label.startswith(f"{label} ")
            )
            for other_label, other_value in pairs
        )
    }


def _subject_value_relationships(text: str) -> set[tuple[str, str]]:
    """Return literal subject/base/value bindings from prose-style source facts.

    Table-like labels are handled separately above.  This intentionally covers
    the common retained-evidence form ``cohort ... accounts for N% of base``
    so a value cannot be reused merely because it appears in an adjacent cohort
    sentence.  The parser does not infer a missing subject or base.
    """

    pairs: set[tuple[str, str]] = set()
    for pattern in (_SUBJECT_VALUE_RELATIONSHIP, _SUBJECT_ACCOUNT_RELATIONSHIP):
        for match in pattern.finditer(text):
            subject_text = match.groupdict().get("subject") or _account_subject(
                match.group("prefix")
            )
            subject = _normalized_relationship_label(subject_text)
            context = _normalized_relationship_label(match.group("context") or "")
            value = _normalized_relationship_value(match.group("value"))
            if subject and context and value and not _is_year_value(value):
                pairs.add((f"{subject} | {context}", value))
    return pairs


def _account_subject(prefix: str) -> str:
    """Keep the named cohort before a preceding value clause, if present."""

    return re.split(r"\b(?:is|are|represents?)\b", prefix, maxsplit=1, flags=re.I)[
        0
    ].strip()


def _values_near_label(
    text: str,
    label: str,
    *,
    related_labels: Iterable[str] = (),
    permitted_neighbor_labels: Iterable[str] = (),
) -> set[str]:
    values: set[str] = set()
    normalized_text = _normalized_relationship_search_text(text)
    label_pattern = _relationship_label_pattern(label)
    other_labels = sorted(
        {
            value.strip()
            for value in related_labels
            if value.strip() and value.casefold() != label.casefold()
        },
        key=lambda value: (-len(value), value.casefold()),
    )
    other_label_patterns = [
        (
            related_label,
            _relationship_label_pattern(related_label),
        )
        for related_label in other_labels
    ]
    permitted_neighbors = {
        value.strip().casefold() for value in permitted_neighbor_labels if value.strip()
    }
    shared_value_prefix = re.compile(
        rf"(?P<value>{_RELATIONSHIP_VALUE})(?![A-Za-z0-9%])\s+in\s+",
        re.IGNORECASE,
    )
    category_list_separators = re.compile(
        r"[\s,&]*(?:(?:and|or)\b[\s,&]*)*", re.IGNORECASE
    )
    fragments = re.split(r";|\n|(?<=[.!?])\s+", normalized_text)
    for fragment in fragments:
        for label_match in label_pattern.finditer(fragment):
            if _is_compound_category_header(fragment, label_match.start()):
                continue
            prefix = fragment[: label_match.start()]
            attributed_preceding_value = re.search(
                rf"(?P<value>{_RELATIONSHIP_VALUE})(?![A-Za-z0-9%])"
                r"\s+(?:called|rated|described)\s+(?:as\s+)?"
                r"(?:(?:the|a|an)\s+)?(?:impact|effect|result|outcome)\s*$",
                prefix,
                re.IGNORECASE,
            )
            adjacent_preceding_value = re.search(
                rf"(?P<value>{_RELATIONSHIP_VALUE})(?![A-Za-z0-9%])\s*$",
                prefix,
            )
            preceding_category_value = (
                attributed_preceding_value or adjacent_preceding_value
            )
            if preceding_category_value and not attributed_preceding_value:
                preceding_context = prefix[: preceding_category_value.start()]
                has_category_separator = re.search(
                    r"(?:[,;:]|\b(?:and|or)\b)\s*$",
                    preceding_context,
                    re.IGNORECASE,
                )
                if not has_category_separator:
                    preceding_category_value = None
            if preceding_category_value:
                value = _normalized_relationship_value(
                    preceding_category_value.group("value")
                )
                if value and not _is_year_value(value):
                    values.add(value)
                continue

            preceding_value = re.search(
                rf"(?P<value>{_RELATIONSHIP_VALUE})(?![A-Za-z0-9%])\s+(?:in|for)\s+$",
                prefix,
                re.IGNORECASE,
            )
            if preceding_value:
                value = _normalized_relationship_value(preceding_value.group("value"))
                if value and not _is_year_value(value):
                    values.add(value)
                continue

            shared_value_found = False
            for prefix in reversed(
                list(shared_value_prefix.finditer(fragment[: label_match.start()]))
            ):
                intervening_text = fragment[prefix.end() : label_match.start()]
                matched_related_label = False
                for _related_label, pattern in other_label_patterns:
                    if pattern.search(intervening_text):
                        matched_related_label = True
                        intervening_text = pattern.sub(" ", intervening_text)
                if matched_related_label and category_list_separators.fullmatch(
                    intervening_text
                ):
                    value = _normalized_relationship_value(prefix.group("value"))
                    if value and not _is_year_value(value):
                        values.add(value)
                        shared_value_found = True
                        break
            if shared_value_found:
                continue

            next_category_start = min(
                (
                    match.start()
                    for related_label, pattern in other_label_patterns
                    if related_label.casefold() not in permitted_neighbors
                    if (match := pattern.search(fragment, label_match.end()))
                ),
                default=len(fragment),
            )
            window_end = min(label_match.end() + 80, next_category_start)
            window = fragment[label_match.end() : window_end]
            value_matches = re.finditer(
                rf"{_RELATIONSHIP_VALUE}(?![A-Za-z0-9%])", window, re.IGNORECASE
            )
            for value_match in value_matches:
                if _is_demographic_age_threshold(
                    window, value_match.start(), value_match.end()
                ):
                    continue
                value = _normalized_relationship_value(value_match.group(0))
                if value and not _is_year_value(value):
                    values.add(value)
                    break
    return values


def _is_demographic_age_threshold(text: str, start: int, end: int) -> bool:
    """Exclude age qualifiers from label-to-metric relationships."""
    before = text[max(0, start - 24) : end]
    after = text[end : end + 8]
    return bool(
        re.search(r"\baged\s+\d{1,3}\s*$", before, re.IGNORECASE)
        or re.search(
            r"\baged\s+\d{1,3}\s*[-\u2013]\s*\d{1,3}\s*$", before, re.IGNORECASE
        )
        or (
            re.search(r"\baged\s+\d{1,3}\s*$", before, re.IGNORECASE)
            and re.match(r"\s*(?:\+|[-\u2013]\s*\d{1,3})", after)
        )
    )


def _is_compound_category_header(text: str, label_start: int) -> bool:
    header_start = (
        max(
            text.rfind(".", 0, label_start),
            text.rfind(";", 0, label_start),
            text.rfind("\n", 0, label_start),
        )
        + 1
    )
    header_end_match = re.search(r"[:=]", text[label_start : label_start + 80])
    if not header_end_match:
        return False
    header = text[header_start : label_start + header_end_match.start()]
    return bool(re.search(r"\b(?:and|&)\b|&", header))


def _normalized_category_value_label(value: str) -> str:
    """Use the nearest blank-line-delimited row label, not its table heading."""
    nearest_label = re.split(r"\r?\n[ \t]*\r?\n", value)[-1]
    normalized = _normalized_relationship_label(nearest_label)
    # Delimited prose rows such as ``CTV accounts for 30.83%`` can be
    # captured with the verb phrase as part of the label. Strip that suffix so
    # combined-category checks compare the actual category names.
    return re.sub(
        r"\b(?:accounts?\s+for|is|are|was|were|has|had)\s*$", "", normalized
    ).strip()


def _normalized_relationship_label(value: str) -> str:
    normalized = value.casefold().replace("–", "-").replace(",", " ")
    normalized = re.sub(r"(?<=[a-z])\d+$", "", normalized)
    return " ".join(normalized.split())


def _normalized_relationship_value(value: str) -> str:
    return "".join(value.casefold().replace(",", "").split())


def _normalized_relationship_search_text(value: str) -> str:
    return value.casefold().replace("–", "-")


def _relationship_label_pattern(label: str) -> re.Pattern[str]:
    parts = [part for part in label.split() if part]
    pattern = r"(?:\s*,?\s+)".join(re.escape(part) for part in parts)
    return re.compile(rf"(?<![A-Za-z0-9]){pattern}(?![A-Za-z0-9])", re.IGNORECASE)


def _is_year_value(value: str) -> bool:
    return bool(re.fullmatch(r"(?:19|20)\d{2}e?", value))


def _material_numbers(text: str) -> set[str]:
    return {_quantity_identity(quantity) for quantity in _material_quantities(text)}


def _temporal_qualifiers(text: str) -> set[str]:
    return {
        " ".join(match.group(0).casefold().replace(".", "").split())
        for match in _TEMPORAL_QUALIFIER.finditer(text)
    }


def _number_temporal_qualifier_pairs(text: str) -> list[tuple[str, str]]:
    material_matches = [
        (quantity, _quantity_identity(quantity))
        for quantity in _material_quantities(text)
    ]
    pairs: list[tuple[str, str]] = []
    for index, (quantity, identity) in enumerate(material_matches):
        next_start = (
            material_matches[index + 1][0].start
            if index + 1 < len(material_matches)
            else len(text)
        )
        qualifier = _TEMPORAL_QUALIFIER.search(text[quantity.end : next_start])
        if qualifier:
            pairs.append(
                (
                    identity,
                    " ".join(qualifier.group(0).casefold().replace(".", "").split()),
                )
            )
    return pairs


def _claim_retains_temporal_qualifier(
    source_qualifier: str, claim_qualifiers: set[str]
) -> bool:
    if source_qualifier in claim_qualifiers:
        return True
    return bool(
        re.fullmatch(r"(?:q[1-4]|h[12])", source_qualifier)
        and any(
            qualifier.startswith(f"{source_qualifier} ")
            for qualifier in claim_qualifiers
        )
    )


def _sentences(text: str) -> list[str]:
    return [sentence for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence]


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


def _unsupported_numbers(text: str, evidence: str, metric: object) -> bool:
    evidence_text = " ".join([evidence, _metric_quantity_text(metric)])
    evidence_quantities = _material_quantities(evidence_text)
    return any(
        not any(quantities_match(claim, source) for source in evidence_quantities)
        for claim in _material_quantities(text)
    )


def _metric_quantity_text(value: object) -> str:
    if isinstance(value, Mapping):
        return " ".join(_metric_quantity_text(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_metric_quantity_text(item) for item in value)
    if isinstance(value, (str, int, float)):
        return str(value)
    return ""


def _material_quantities(text: str) -> list[Quantity]:
    return [
        quantity
        for quantity in extract_quantities(text)
        if not (
            quantity.unit_family == "unknown"
            and quantity.value.is_integer()
            and 1900 <= int(quantity.value) <= 2100
        )
    ]


def _quantity_identity(quantity: Quantity) -> str:
    canonical = canonicalize_quantity(quantity)
    return "|".join(
        str(value)
        for value in (
            canonical.value * canonical.scale,
            canonical.sign,
            canonical.comparator,
            canonical.unit_family,
            canonical.unit,
            canonical.currency,
            (canonical.low * canonical.scale) if canonical.low is not None else "",
            (canonical.high * canonical.scale) if canonical.high is not None else "",
        )
    )


def _relationship_values_match(left: str, right: str) -> bool | None:
    left_values = extract_quantities(left)
    right_values = extract_quantities(right)
    if len(left_values) != 1 or len(right_values) != 1:
        return None
    return quantities_match(left_values[0], right_values[0])


def _has_relationship_value(value: str, candidates: Iterable[str]) -> bool:
    return any(
        _relationship_values_match(value, candidate) is True for candidate in candidates
    )


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
    stripped = text.strip()
    if len(words) < 3:
        return not bool(re.search(r"[.!?;:]$", stripped))
    return not re.search(r"[.!?;:]$", stripped) and bool(
        re.search(r"\b(?:and|or|but|because|with|of|to)$", stripped, re.I)
    )


def _looks_ocr_shaped(text: str) -> bool:
    if "\ufffd" in text or "¦" in text or "||" in text:
        return True
    # OCR commonly substitutes a digit inside an otherwise lowercase word;
    # preserve legitimate mixed-case metric names such as ``Top2Box``.
    return bool(re.search(r"\b[a-z]{2,}\d[a-z]{2,}\b", text))


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
    "DETERMINISTIC_PUBLIC_EDITORIAL_RULE_IDS",
    "HARD_FAIL_CLASS_BY_RULE_ID",
    "enumerate_public_editorial_items",
    "evaluate_public_editorial_quality",
    "merge_public_editorial_quality_validation",
    "public_editorial_report_review_scope",
    "public_editorial_semantic_review_items",
    "public_html_quality_issues",
    "quality_report_payload",
    "validation_issues_from_public_editorial_quality",
]
