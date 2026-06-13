from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.contracts.analysis_family import AnalysisFamilyStatus
from src.utils.analysis_family import (
    family_is_abstained,
    serialize_family_status,
)
from src.utils.text_normalization import normalize_for_lookup, normalize_text

logger = logging.getLogger("market_lense.artifact_generator")

_ARTIFACT_REGENERATE_FAMILIES = {"summary", "insights_bundle", "quotes"}
_ARTIFACT_CONFIDENCE_THRESHOLDS = {
    "summary": 0.72,
    "insights_bundle": 0.78,
    "quotes": 0.72,
    "expert_comment": 0.76,
    "linkedin_post": 0.72,
}


def apply_artifact_family_policy(
    *,
    summary: Dict[str, Any],
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    expert_comment: str,
    linkedin_post: str,
) -> tuple[
    Dict[str, Any],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    str,
    str,
    Dict[str, Dict[str, Any]],
]:
    summary_payload = dict(summary)
    insights_candidate_payload = list(insights_candidates)
    insights_final_payload = list(insights_final)
    quotes_payload = list(quotes_final)
    expert_payload = expert_comment
    linkedin_payload = linkedin_post

    family_status = build_artifact_family_status(
        summary=summary_payload,
        insights_candidates=insights_candidate_payload,
        insights_final=insights_final_payload,
        quotes_final=quotes_payload,
        expert_comment=expert_payload,
        linkedin_post=linkedin_payload,
    )
    if family_is_abstained({"family_status": family_status}, "summary"):
        summary_payload = {
            "tldr": "",
            "card_tldr_compact": "",
            "executive_summary": "",
            "claim_evidence_map": [],
        }
    if family_is_abstained({"family_status": family_status}, "insights_bundle"):
        insights_candidate_payload = []
        insights_final_payload = []
    if family_is_abstained({"family_status": family_status}, "quotes"):
        quotes_payload = []
    if family_is_abstained({"family_status": family_status}, "expert_comment"):
        expert_payload = ""
    if family_is_abstained({"family_status": family_status}, "linkedin_post"):
        linkedin_payload = ""
    return (
        summary_payload,
        insights_candidate_payload,
        insights_final_payload,
        quotes_payload,
        expert_payload,
        linkedin_payload,
        family_status,
    )


def build_artifact_family_status(
    *,
    summary: Dict[str, Any],
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    expert_comment: str,
    linkedin_post: str,
) -> Dict[str, Dict[str, Any]]:
    statuses = [
        _artifact_family_status(
            family="summary",
            confidence_score=_summary_confidence_score(summary),
            reason=_summary_confidence_reason(summary),
        ),
        _artifact_family_status(
            family="insights_bundle",
            confidence_score=_insights_confidence_score(
                insights_candidates=insights_candidates,
                insights_final=insights_final,
            ),
            reason=_insights_confidence_reason(
                insights_candidates=insights_candidates,
                insights_final=insights_final,
            ),
        ),
        _artifact_family_status(
            family="quotes",
            confidence_score=_quotes_confidence_score(quotes_final),
            reason=_quotes_confidence_reason(quotes_final),
        ),
        _artifact_family_status(
            family="expert_comment",
            confidence_score=_soft_text_confidence_score(
                text=expert_comment,
                summary=summary,
                insights_final=insights_final,
                quotes_final=quotes_final,
            ),
            reason=_soft_text_confidence_reason(
                text=expert_comment,
                supporting_artifacts_ready=bool(summary) and bool(insights_final),
            ),
        ),
        _artifact_family_status(
            family="linkedin_post",
            confidence_score=_soft_text_confidence_score(
                text=linkedin_post,
                summary=summary,
                insights_final=insights_final,
                quotes_final=quotes_final,
            ),
            reason=_soft_text_confidence_reason(
                text=linkedin_post,
                supporting_artifacts_ready=bool(summary) and bool(insights_final),
            ),
        ),
    ]
    return {status.family: serialize_family_status(status) for status in statuses}


def _artifact_family_status(
    *,
    family: str,
    confidence_score: float,
    reason: str,
) -> AnalysisFamilyStatus:
    threshold = _ARTIFACT_CONFIDENCE_THRESHOLDS[family]
    below_threshold = confidence_score < threshold
    if not below_threshold:
        status = "generated"
        policy_action = "keep"
        status_reason = ""
    elif family in _ARTIFACT_REGENERATE_FAMILIES:
        status = "abstained"
        policy_action = "regenerate"
        status_reason = reason or "insufficient_evidence_support"
    else:
        status = "abstained"
        policy_action = "abstain"
        status_reason = reason or "insufficient_evidence_support"
    return AnalysisFamilyStatus(
        schema_version="1.0",
        family=family,
        source="artifact",
        status=status,
        confidence_score=max(0.0, min(1.0, round(confidence_score, 3))),
        policy_action=policy_action,
        reason=status_reason,
    )


def _summary_confidence_score(summary: Dict[str, Any]) -> float:
    claim_map = summary.get("claim_evidence_map") if isinstance(summary, dict) else []
    score = 0.0
    if _s(summary.get("tldr")).strip():
        score += 0.28
    if _s(summary.get("executive_summary")).strip():
        score += 0.28
    if isinstance(claim_map, list) and claim_map:
        score += 0.08
        supported_claims = 0
        for claim in claim_map:
            if not isinstance(claim, dict):
                continue
            if _summary_claim_has_structured_support(claim):
                supported_claims += 1
        score += 0.36 * (supported_claims / max(1, len(claim_map)))
    return score


def _summary_claim_has_structured_support(claim: Dict[str, Any]) -> bool:
    return bool(claim.get("evidence_spans") or _s(claim.get("evidence_id")).strip())


def _summary_confidence_reason(summary: Dict[str, Any]) -> str:
    claim_map = summary.get("claim_evidence_map") if isinstance(summary, dict) else []
    if not _s(summary.get("tldr")).strip():
        return "summary_missing_tldr"
    if not _s(summary.get("executive_summary")).strip():
        return "summary_missing_executive_summary"
    if not isinstance(claim_map, list) or not claim_map:
        return "summary_missing_claim_evidence"
    if not any(
        isinstance(claim, dict)
        and (
            claim.get("evidence_spans")
            or _s(claim.get("evidence_id")).strip()
            or _s(claim.get("evidence")).strip()
        )
        for claim in claim_map
    ):
        return "summary_claim_evidence_unsupported"
    if any(
        isinstance(claim, dict)
        and _s(claim.get("claim")).strip()
        and not _summary_claim_has_structured_support(claim)
        for claim in claim_map
    ):
        return "summary_claim_span_missing"
    return ""


def _insights_confidence_score(
    *,
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
) -> float:
    score = 0.0
    nonempty_final = [
        item
        for item in insights_final
        if isinstance(item, dict) and _s(item.get("text")).strip()
    ]
    if nonempty_final:
        score += 0.28
        score += 0.32 * (min(len(nonempty_final), 5) / 5.0)
    evidence_supported = [
        item
        for item in nonempty_final
        if _s(item.get("evidence_id")).strip() or _s(item.get("evidence")).strip()
    ]
    if nonempty_final:
        score += 0.24 * (len(evidence_supported) / len(nonempty_final))
    if isinstance(insights_candidates, list) and insights_candidates:
        score += 0.16 * (min(len(insights_candidates), 5) / 5.0)
    return score


def _insights_confidence_reason(
    *,
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
) -> str:
    nonempty_final = [
        item
        for item in insights_final
        if isinstance(item, dict) and _s(item.get("text")).strip()
    ]
    if len(nonempty_final) < 5:
        return "insights_missing_required_count"
    if not any(
        _s(item.get("evidence_id")).strip() or _s(item.get("evidence")).strip()
        for item in nonempty_final
    ):
        return "insights_missing_evidence_support"
    if not insights_candidates:
        return "insights_candidates_empty"
    return ""


def _quotes_confidence_score(quotes_final: List[Dict[str, Any]]) -> float:
    if not quotes_final:
        return 0.0
    first_quote = quotes_final[0] if isinstance(quotes_final[0], dict) else {}
    score = 0.0
    if _s(first_quote.get("text")).strip():
        score += 0.45
    if _quote_has_verbatim_source(first_quote):
        score += 0.35
    if (
        _s(first_quote.get("speaker")).strip()
        or _s(first_quote.get("citation")).strip()
        or isinstance(first_quote.get("page"), int)
    ):
        score += 0.2
    return score


def _quotes_confidence_reason(quotes_final: List[Dict[str, Any]]) -> str:
    if not quotes_final:
        return "quotes_missing"
    first_quote = quotes_final[0] if isinstance(quotes_final[0], dict) else {}
    if not _s(first_quote.get("text")).strip():
        return "quotes_missing_text"
    if not _quote_has_verbatim_source(first_quote):
        return "quotes_missing_verbatim_source"
    return ""


def _quote_has_verbatim_source(quote: Dict[str, Any]) -> bool:
    text = _s(quote.get("text")).strip()
    if not text:
        return False
    if _quote_is_marked_paraphrase(quote):
        return False
    spans = quote.get("evidence_spans")
    if isinstance(spans, list):
        for span in spans:
            if not isinstance(span, dict):
                continue
            source_pack = _s(span.get("source_pack")).strip().casefold()
            if source_pack == "quote_candidates":
                return True
            span_text = _s(span.get("text")).strip()
            if span_text and _normalized_contains(span_text, text):
                return True
    source_pack = _s(quote.get("source_pack")).strip().casefold()
    return source_pack == "quote_candidates"


def _quote_is_marked_paraphrase(quote: Dict[str, Any]) -> bool:
    if quote.get("is_paraphrase") is True or quote.get("paraphrase") is True:
        return True
    flags = [quote.get("style"), quote.get("mode"), quote.get("label")]
    return any("paraphrase" in normalize_text(_s(flag)) for flag in flags)


def _normalized_contains(container: str, needle: str) -> bool:
    container_norm = normalize_for_lookup(container)
    needle_norm = normalize_for_lookup(needle)
    if not container_norm or not needle_norm:
        return False
    return needle_norm in container_norm


def _soft_text_confidence_score(
    *,
    text: str,
    summary: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
) -> float:
    if not _s(text).strip():
        return 0.0
    score = 0.45
    if _s(summary.get("executive_summary")).strip():
        score += 0.2
    if insights_final:
        score += 0.2
    if quotes_final:
        score += 0.15
    return score


def _soft_text_confidence_reason(*, text: str, supporting_artifacts_ready: bool) -> str:
    if not _s(text).strip():
        return "generated_text_missing"
    if not supporting_artifacts_ready:
        return "supporting_artifacts_weak"
    return ""


def _s(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)
