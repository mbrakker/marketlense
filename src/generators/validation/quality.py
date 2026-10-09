from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, List

from src.contracts.soft_copy_claim_provenance import (
    soft_copy_claim_provenance_from_payload,
)
from src.contracts.validation import ValidationIssue
from src.generators.validation.models import ValidationRuntime
from src.utils.coercion import string_value as _s
from src.utils.errors import AppError

RULE_ID = "artifact_quality"

_BANNED_PATTERNS = (
    ("rapidly evolving landscape", re.compile(r"\brapidly evolving landscape\b", re.I)),
    ("game changer", re.compile(r"\bgame[- ]changer\b", re.I)),
    ("unlock", re.compile(r"\bunlock(?:s|ed|ing)?\b", re.I)),
    ("delve", re.compile(r"\bdelve(?:s|d|ing)?\b", re.I)),
    ("robust", re.compile(r"\brobust\b", re.I)),
    ("seamless", re.compile(r"\bseamless(?:ly)?\b", re.I)),
    ("crucial", re.compile(r"\bcrucial\b", re.I)),
    ("important to note", re.compile(r"\bit is important to note\b", re.I)),
    ("report highlights", re.compile(r"\bthis report highlights\b", re.I)),
)

_TECHNICAL_ALLOWLIST = (
    re.compile(r"\bfinancial leverage\b", re.I),
    re.compile(r"\boperating leverage\b", re.I),
    re.compile(r"\bdebt leverage\b", re.I),
    re.compile(r"\brobust (standard errors|regression|statistics|methodology)\b", re.I),
)

_GENERIC_COPY_SIGNAL = re.compile(
    r"(\d|%|\$|\b(revenue|margin|growth|demand|adoption|retention|cost|risk|"
    r"enterprise|merchant|consumer|retailer|publisher|operator|brand|market|"
    r"channel|payments|wallet|ai|cloud|supply|pricing)\b|[A-Z]{2,})",
    re.I,
)
_QUANTITATIVE_SIGNAL = re.compile(
    r"(?:[$€£]\s*\d[\d,.]*(?:\s?(?:[KMB]|million|billion|trillion))?\b|"
    r"\b\d[\d,.]*\s?(?:%|percent(?:age)?|GB|TB|MB|hours?|minutes?|"
    r"days?|weeks?|months?|years?|points?|basis points?|downloads?|users?)\b|"
    r"\b\d[\d,.]*\s+(?:thousand|million|billion|trillion)\b)",
    re.IGNORECASE,
)
_QUANTITATIVE_METRIC_CONTEXT = re.compile(
    r"\b(?:revenue|sales|download(?:s|ed|ing)?|installs?|sessions?|traffic|referrals?|"
    r"conversions?|retention|churn|spending|spend|costs?|prices?|margins?|"
    r"profits?|orders?|transactions?|market share|time spent|engagement|GDP)\b",
    re.IGNORECASE,
)
_QUALITATIVE_ACTOR = re.compile(
    r"\b(?:advertisers?|audiences?|brands?|buyers?|companies?|consumers?|"
    r"corporates?|creators?|developers?|households?|investors?|marketers?|"
    r"merchants?|operators?|publishers?|retailers?|users?)\b",
    re.IGNORECASE,
)
_QUALITATIVE_RELATION = re.compile(
    r"\b(?:account for|adopt|choose|constrain|decline|depend|divert|drive|"
    r"exceed|fall|generate|grow|increase|lead to|lose|outpace|prefer|push|"
    r"reduce|redirect|reshape|shift|substitute|switch|trade off|value|weigh|"
    r"while|whereas|rather than|instead of|more likely|less likely)\b",
    re.IGNORECASE,
)


def run_artifact_quality_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    artifacts = (
        runtime.request.artifacts if isinstance(runtime.request.artifacts, dict) else {}
    )
    for path, text, has_structured_category in _artifact_copy_fields(artifacts):
        normalized = " ".join(text.split())
        if not normalized:
            continue
        for label, pattern in _BANNED_PATTERNS:
            if not pattern.search(normalized):
                continue
            if _is_allowed_technical_usage(normalized, label):
                continue
            issues.append(
                ValidationIssue(
                    schema_version="1.0",
                    message=f"Generated copy uses banned generic pattern: {label}",
                    severity="warning",
                    affected_section=path,
                    rule_id=RULE_ID,
                    repair_target="artifact_copy",
                    entity_id=path,
                )
            )
        first_sentence = _first_sentence(normalized)
        if not first_sentence or has_structured_category:
            continue
        if path.startswith("summary."):
            if _has_concrete_signal(first_sentence):
                continue
            stronger_evidence_id = _stronger_retained_insight_evidence_id(artifacts)
            if not stronger_evidence_id:
                continue
            claim_id = _summary_opening_claim_id(
                artifacts=artifacts,
                path=path,
                sentence=first_sentence,
            )
            issues.append(
                ValidationIssue(
                    schema_version="1.0",
                    message=(
                        "Summary opening is broader than a retained source-supported "
                        "finding."
                    ),
                    severity="warning",
                    affected_section=path,
                    rule_id=RULE_ID,
                    repair_target="artifact_copy",
                    entity_id=claim_id or path,
                    evidence_ids=[stronger_evidence_id],
                )
            )
            continue
        if not _has_generic_copy_signal(first_sentence):
            issues.append(
                ValidationIssue(
                    schema_version="1.0",
                    message=(
                        "Generated copy opens without a concrete metric or specific "
                        "qualitative relationship."
                    ),
                    severity="warning",
                    affected_section=path,
                    rule_id=RULE_ID,
                    repair_target="artifact_copy",
                    entity_id=path,
                )
            )
    return issues


def _stronger_retained_insight_evidence_id(artifacts: dict) -> str:
    """Return the first specific, evidence-linked selected insight, if any."""

    insights = artifacts.get("insights_final")
    if not isinstance(insights, list):
        return ""
    for insight in insights:
        if not isinstance(insight, dict):
            continue
        evidence_id = _s(insight.get("evidence_id")).strip()
        evidence = _s(insight.get("evidence")).strip()
        first_sentence = _first_sentence(_s(insight.get("text")).strip())
        if (
            evidence_id
            and evidence
            and first_sentence
            and _has_concrete_signal(first_sentence)
        ):
            return evidence_id
    return ""


def _summary_opening_claim_id(*, artifacts: dict, path: str, sentence: str) -> str:
    """Attribute a summary opening warning only to one exact retained claim."""

    if path not in {
        "summary.tldr",
        "summary.card_tldr_compact",
        "summary.executive_summary",
    }:
        return ""
    try:
        claims = soft_copy_claim_provenance_from_payload(
            artifacts.get("soft_copy_claim_provenance")
        )
    except (AppError, TypeError, ValueError):
        return ""
    text_hash = hashlib.sha256(" ".join(sentence.split()).encode("utf-8")).hexdigest()
    matches = [
        claim
        for claim in claims
        if claim.artifact_family == "summary" and claim.text_hash == text_hash
    ]
    return matches[0].claim_id if len(matches) == 1 else ""


def _artifact_copy_fields(artifacts: dict) -> Iterable[tuple[str, str, bool]]:
    for key in ("expert_comment", "linkedin_post"):
        text = _s(artifacts.get(key)).strip()
        if text:
            yield key, text, False
    summary = artifacts.get("summary")
    if isinstance(summary, dict):
        for key in ("tldr", "card_tldr_compact", "executive_summary"):
            text = _s(summary.get(key)).strip()
            if text:
                yield f"summary.{key}", text, False
    yield from _copy_from_list(
        artifacts.get("insights_final"), "insights_final", ("text",)
    )
    yield from _topic_copy_fields(
        artifacts.get("topics_covered"),
        "topics_covered",
        ("why_it_matters",),
    )
    yield from _copy_from_list(
        artifacts.get("key_figures"),
        "key_figures",
        ("why_it_matters", "caveat"),
    )
    yield from _copy_from_list(
        artifacts.get("chart_insight_cards"),
        "chart_insight_cards",
        ("takeaway", "business_implication", "avoid_reason_if_weak"),
    )
    for index, item in enumerate(artifacts.get("chart_insight_cards") or []):
        if not isinstance(item, dict):
            continue
        caption = _s(item.get("caption")).strip()
        if caption:
            # Chart captions are display labels, not sentence prose. Other
            # editorial-quality checks still apply to their retained text.
            yield f"chart_insight_cards[{index}].caption", caption, True


def _copy_from_list(
    value: Any, section: str, keys: tuple[str, ...]
) -> Iterable[tuple[str, str, bool]]:
    if not isinstance(value, list):
        return
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        for key in keys:
            text = _s(item.get(key)).strip()
            if text:
                yield f"{section}[{index}].{key}", text, False


def _topic_copy_fields(
    value: Any, section: str, keys: tuple[str, ...]
) -> Iterable[tuple[str, str, bool]]:
    if not isinstance(value, list):
        return
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        has_structured_category = bool(_s(item.get("topic")).strip())
        for key in keys:
            text = _s(item.get(key)).strip()
            if text:
                yield f"{section}[{index}].{key}", text, has_structured_category


def _is_allowed_technical_usage(text: str, label: str) -> bool:
    if label not in {"leverage", "robust"}:
        return False
    return any(pattern.search(text) for pattern in _TECHNICAL_ALLOWLIST)


def _first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“'])", text, maxsplit=1)
    return parts[0].strip()


def _has_concrete_signal(sentence: str) -> bool:
    if any(pattern.search(sentence) for pattern in _TECHNICAL_ALLOWLIST):
        return True
    if _QUANTITATIVE_SIGNAL.search(sentence) and _QUANTITATIVE_METRIC_CONTEXT.search(
        sentence
    ):
        return True
    return bool(
        _QUALITATIVE_ACTOR.search(sentence)
        and _QUALITATIVE_RELATION.search(sentence)
    )


def _has_generic_copy_signal(sentence: str) -> bool:
    """Preserve broad-copy checks outside summary leads."""

    if re.match(r"^(this report|the report|it)\b", sentence, flags=re.I):
        return False
    return bool(_GENERIC_COPY_SIGNAL.search(sentence))
