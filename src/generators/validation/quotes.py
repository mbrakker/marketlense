from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from src.contracts.validation import ValidationIssue

from .evidence import (
    lexical_overlap,
    quote_is_paraphrase,
    quote_label,
    quote_near_verbatim,
    retrieve_evidence_windows,
)
from .models import EvidenceWindow, SemanticSupport, ValidationRuntime
from .shared import (
    QUOTE_MIN_PARAPHRASE_OVERLAP,
    QUOTE_MIN_VERBATIM_SEMANTIC_OVERLAP,
    RETRIEVE_TOP_K,
    format_confidence,
    issue,
    s,
)

RULE_ID = "quotes"


def run_quote_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    return validate_quotes(
        quotes=runtime.prepared.quotes,
        evidence_texts=runtime.prepared.evidence_texts,
        semantic_support=runtime.semantic_outcome.quote_support,
        evidence_windows=runtime.prepared.evidence_windows,
    )


def validate_quotes(
    quotes: Sequence[dict],
    evidence_texts: Sequence[str],
    semantic_support: Optional[Dict[str, SemanticSupport]] = None,
    evidence_windows: Optional[Sequence[EvidenceWindow]] = None,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not quotes:
        return issues
    windows = list(evidence_windows or [])
    for idx, quote in enumerate(quotes):
        if not isinstance(quote, dict):
            continue
        text = s(quote.get("text"))
        if not text:
            continue
        label = quote_label(quote, idx)
        quote_paraphrase = quote_is_paraphrase(quote)
        semantic_entry = (semantic_support or {}).get(label)
        semantic_confidence = semantic_entry.confidence if semantic_entry else 0.0
        retrieved = retrieve_evidence_windows(text, windows, top_k=RETRIEVE_TOP_K)
        candidate_evidence = list(evidence_texts) + [window.text for window in retrieved]
        verbatim_match = any(
            quote_near_verbatim(text, evidence) for evidence in candidate_evidence
        )
        best_overlap = 0.0
        if candidate_evidence:
            best_overlap = max(
                lexical_overlap(text, evidence) for evidence in candidate_evidence
            )
        if verbatim_match:
            continue
        semantic_supported = bool(semantic_entry and semantic_entry.supported)
        if quote_paraphrase:
            if semantic_supported or best_overlap >= QUOTE_MIN_PARAPHRASE_OVERLAP:
                issues.append(
                    issue(
                        rule_id=RULE_ID,
                        message=(
                            "Quote paraphrased but semantically supported "
                            f"(confidence={format_confidence(semantic_confidence)}): {text[:120]}"
                        ),
                        severity="info",
                        section=f"quotes:{label}",
                    )
                )
                continue
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=f"Quote paraphrase not supported by evidence: {text[:120]}",
                    severity="warning",
                    section=f"quotes:{label}",
                )
            )
            continue
        if semantic_supported and best_overlap >= QUOTE_MIN_VERBATIM_SEMANTIC_OVERLAP:
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=(
                        "Quote semantically supported with lexical overlap "
                        f"(confidence={format_confidence(semantic_confidence)}): {text[:120]}"
                    ),
                    severity="info",
                    section=f"quotes:{label}",
                )
            )
        else:
            reason = (
                f" ({semantic_entry.reason})"
                if semantic_entry and semantic_entry.reason
                else ""
            )
            severity = (
                "error"
                if not semantic_entry or semantic_confidence >= 0.6
                else "warning"
            )
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=f"Quote not verbatim in evidence{reason}: {text[:120]}",
                    severity=severity,
                    section=f"quotes:{label}",
                )
            )
    return issues

