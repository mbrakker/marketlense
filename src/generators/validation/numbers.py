from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from typing import List, Optional, Sequence, Tuple

from src.contracts.report_models import ReportPayload
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_from_payload,
    soft_copy_material_sentences,
)
from src.contracts.validation import ValidationIssue
from src.utils.errors import AppError
from src.utils.quantity import extract_quantities, should_ground_quantity

from .evidence import retrieve_evidence_windows, split_sentences
from .models import EvidenceWindow, ValidationRuntime
from .quantities import (
    collect_allowed_quantities,
    quantity_supported,
    unsupported_quantity_severity,
)
from .relationships import period_time_pairs, unsupported_period_time_pairs
from .shared import RETRIEVE_TOP_K, issue, s, section_policy

RULE_ID = "numbers"


def run_number_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    return validate_new_numbers(
        artifacts=runtime.request.artifacts,
        insights=runtime.prepared.insights,
        report=runtime.request.report,
        evidence_texts=runtime.prepared.evidence_texts,
        evidence_windows=runtime.prepared.evidence_windows,
        source_text=runtime.prepared.pdf_text,
    )


def validate_new_numbers(
    artifacts: dict,
    insights: Sequence[dict],
    report: ReportPayload,
    evidence_texts: Sequence[str],
    evidence_windows: Optional[Sequence[EvidenceWindow]] = None,
    source_text: str = "",
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    allowed_quantities = collect_allowed_quantities(
        insights, report, artifacts, evidence_texts
    )
    windows = list(evidence_windows or [])
    soft_copy_claims = _soft_copy_claims_by_sentence(artifacts)
    summary = artifacts.get("summary") if isinstance(artifacts, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    section_texts: List[Tuple[str, str]] = [
        (s(summary.get("tldr")), "summary.tldr"),
        (s(summary.get("card_tldr_compact")), "summary.card_tldr_compact"),
        (
            s(artifacts.get("expert_comment") if isinstance(artifacts, dict) else ""),
            "expert_comment",
        ),
        (
            s(artifacts.get("linkedin_post") if isinstance(artifacts, dict) else ""),
            "linkedin_post",
        ),
        (s(summary.get("executive_summary")), "summary.executive_summary"),
    ]
    insight_items = (
        list(insights)
        if insights
        else (
            artifacts.get("insights_final", []) if isinstance(artifacts, dict) else []
        )
    )
    linked_insight_evidence: dict[str, str] = {}
    for index, insight in enumerate(insight_items):
        if not isinstance(insight, dict):
            continue
        insight_id = s(insight.get("id") or str(index + 1))
        for field_name in ("text", "so_what", "now_what"):
            section = f"insights:{insight_id}.{field_name}"
            section_texts.append((s(insight.get(field_name)), section))
            linked_insight_evidence[section] = s(insight.get("evidence"))
    figures = artifacts.get("key_figures") if isinstance(artifacts, dict) else []
    for index, figure in enumerate(
        figures if isinstance(figures, list) else [], start=1
    ):
        if not isinstance(figure, dict):
            continue
        for field_name in ("label", "figure", "why_it_matters"):
            section_texts.append(
                (s(figure.get(field_name)), f"key_figures:{index}.{field_name}")
            )
    seen: set[Tuple[str, str, str]] = set()
    for text, section in section_texts:
        if not text:
            continue
        policy = section_policy(section)
        sentences = (
            soft_copy_material_sentences(text)
            if section in {"expert_comment", "linkedin_post"}
            else split_sentences(text)
        )
        for sentence in sentences:
            sentence_quantities = extract_quantities(sentence)
            if not sentence_quantities:
                continue
            retrieved = retrieve_evidence_windows(
                sentence, windows, top_k=RETRIEVE_TOP_K
            )
            local_evidence_quantities = list(allowed_quantities)
            for window in retrieved:
                local_evidence_quantities.extend(window.quantities)
            for quantity in sentence_quantities:
                if not should_ground_quantity(
                    quantity,
                    sentence,
                    section_policy=policy,
                    strict_section=policy == "strict",
                ):
                    continue
                if quantity_supported(
                    quantity, local_evidence_quantities, numeric_only=True
                ):
                    continue
                if _rank_group_label_in_linked_evidence(
                    quantity=quantity,
                    sentence=sentence,
                    evidence=linked_insight_evidence.get(section, ""),
                ):
                    continue
                severity = unsupported_quantity_severity(
                    policy=policy,
                    quantity=quantity,
                    sentence=sentence,
                )
                key = (section, quantity.raw or str(quantity.value), severity)
                if key in seen:
                    continue
                seen.add(key)
                claim = soft_copy_claims.get((section, _normalized_text_hash(sentence)))
                issues.append(
                    replace(
                        issue(
                            rule_id=RULE_ID,
                            message=f"Number {quantity.value} not present in report or evidence",
                            severity=severity,
                            section=section,
                            entity_id=claim.claim_id if claim else "",
                        ),
                        evidence_ids=list(claim.evidence_ids) if claim else [],
                    )
                )
        unsupported_pairs = unsupported_period_time_pairs(text, source_text)
        source_pairs = period_time_pairs(source_text)
        source_values_by_period = {period: value for period, value in source_pairs}
        for period, value in sorted(unsupported_pairs):
            key = (section, f"{period}:{value}", "error")
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=(
                        "Ordered source evidence does not pair "
                        f"{value} with {period}; retained source pairs {period} "
                        f"with {source_values_by_period.get(period, '')}"
                    ),
                    severity="error",
                    section=section,
                )
            )
    return issues


_RANK_GROUP_LABEL = re.compile(
    r"\btop\s+\d+\s+\w+\b|\b\w+\s+ranked\s+\d+\s*[-–]\s*\d+\b",
    re.IGNORECASE,
)


def _rank_group_label_in_linked_evidence(
    *, quantity, sentence: str, evidence: str
) -> bool:
    """Ground a cohort label by its exact phrase, not a nearby metric value."""

    if not evidence:
        return False
    normalized_evidence = " ".join(re.findall(r"\w+", evidence.casefold()))
    return any(
        match.start() <= quantity.start
        and quantity.end <= match.end()
        and " ".join(re.findall(r"\w+", match.group().casefold()))
        in normalized_evidence
        for match in _RANK_GROUP_LABEL.finditer(sentence)
    )


def _soft_copy_claims_by_sentence(
    artifacts: object,
) -> dict[tuple[str, str], SoftCopyClaimProvenance]:
    """Keep a soft-copy validator failure claim-scoped for E13 regeneration."""
    if not isinstance(artifacts, dict):
        return {}
    try:
        claims = soft_copy_claim_provenance_from_payload(
            artifacts.get("soft_copy_claim_provenance")
        )
    except (AppError, TypeError, ValueError):
        return {}
    mapped: dict[tuple[str, str], SoftCopyClaimProvenance] = {}
    ambiguous: set[tuple[str, str]] = set()
    for claim in claims:
        if claim.artifact_family not in {"expert_comment", "linkedin_post"}:
            continue
        key = (claim.artifact_family, claim.text_hash)
        if key in mapped:
            ambiguous.add(key)
        else:
            mapped[key] = claim
    return {key: claim for key, claim in mapped.items() if key not in ambiguous}


def _normalized_text_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()
