from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from src.contracts.report_models import ReportPayload
from src.contracts.validation import ValidationIssue
from src.utils.quantity import extract_quantities, should_ground_quantity

from .evidence import retrieve_evidence_windows, split_sentences
from .models import EvidenceWindow, ValidationRuntime
from .quantities import (
    collect_allowed_quantities,
    quantity_supported,
    unsupported_quantity_severity,
)
from .shared import RETRIEVE_TOP_K, issue, s, section_policy

RULE_ID = "numbers"


def run_number_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    return validate_new_numbers(
        artifacts=runtime.request.artifacts,
        insights=runtime.prepared.insights,
        report=runtime.request.report,
        evidence_texts=runtime.prepared.evidence_texts,
        evidence_windows=runtime.prepared.evidence_windows,
    )


def validate_new_numbers(
    artifacts: dict,
    insights: Sequence[dict],
    report: ReportPayload,
    evidence_texts: Sequence[str],
    evidence_windows: Optional[Sequence[EvidenceWindow]] = None,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    allowed_quantities = collect_allowed_quantities(
        insights, report, artifacts, evidence_texts
    )
    windows = list(evidence_windows or [])
    summary = artifacts.get("summary") if isinstance(artifacts, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    section_texts: List[Tuple[str, str]] = [
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
    seen: set[Tuple[str, str, str]] = set()
    for text, section in section_texts:
        if not text:
            continue
        policy = section_policy(section)
        for sentence in split_sentences(text):
            sentence_quantities = extract_quantities(sentence)
            if not sentence_quantities:
                continue
            retrieved = retrieve_evidence_windows(sentence, windows, top_k=RETRIEVE_TOP_K)
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
                severity = unsupported_quantity_severity(
                    policy=policy,
                    quantity=quantity,
                    sentence=sentence,
                )
                key = (section, quantity.raw or str(quantity.value), severity)
                if key in seen:
                    continue
                seen.add(key)
                issues.append(
                    issue(
                        rule_id=RULE_ID,
                        message=f"Number {quantity.value} not present in report or evidence",
                        severity=severity,
                        section=section,
                    )
                )
    return issues
