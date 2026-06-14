from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from src.contracts.cross_report_analysis import (
    CrossReportAnalysisRequest,
    CrossReportEvidenceAgreementGroup,
    CrossReportEvidenceAgreementResult,
    CrossReportEvidenceInputResult,
    CrossReportEvidenceReference,
    CrossReportSignalScore,
    validate_cross_report_contract,
)
from src.contracts.run_context import RunContext
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidate,
    SignalCandidateBatch,
    SignalCandidateGroup,
    SignalCandidateSourceRef,
    SignalCandidateSupportLevel,
    SignalCandidateType,
    validate_signal_candidate_contract,
)
from src.utils.coercion import ordered_unique_strings as _unique_ordered
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.signal_candidate_generator")


def _page_refs(metadata: dict[str, Any]) -> list[int]:
    pages = metadata.get("pages")
    if isinstance(pages, list):
        return [
            int(value)
            for value in pages
            if isinstance(value, int) or str(value).strip().isdigit()
        ]
    page = metadata.get("page")
    if isinstance(page, int):
        return [page]
    if str(page or "").strip().isdigit():
        return [int(str(page).strip())]
    return []


def _source_ref(evidence: CrossReportEvidenceReference) -> SignalCandidateSourceRef:
    return SignalCandidateSourceRef(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        report_id=evidence.report_id,
        evidence_id=evidence.evidence_id,
        source_table=evidence.source_table,
        entity_uid=evidence.entity_uid,
        content_class=str(evidence.content_class),
        page_refs=_page_refs(evidence.source_metadata),
        source_metadata=dict(evidence.source_metadata),
    )


def _support_level(
    group: CrossReportEvidenceAgreementGroup,
) -> SignalCandidateSupportLevel:
    if group.agreement_type == "convergent":
        return "multi_report_convergent"
    if group.agreement_type == "divergent":
        return "multi_report_divergent"
    if len(group.source_report_ids) <= 1:
        return "single_report"
    return "weak_coverage"


def _candidate_type(group: CrossReportEvidenceAgreementGroup) -> SignalCandidateType:
    if group.agreement_type == "divergent":
        return "contradiction_signal"
    if group.agreement_type == "thin_coverage":
        return "weak_signal"
    return "market_signal"


def _caveats(group: CrossReportEvidenceAgreementGroup) -> list[str]:
    caveats = _unique_ordered(list(group.uncertainty_reasons))
    if group.agreement_type == "convergent":
        caveats.append("coverage_limited_to_selected_projected_reports")
    elif group.agreement_type == "divergent":
        caveats.append("divergent_source_coverage")
    else:
        caveats.append("weak_or_single_report_coverage")
    return _unique_ordered(caveats)


def _summary(label: str, evidence: list[CrossReportEvidenceReference]) -> str:
    first = evidence[0].text.strip()
    if len(first) > 240:
        first = first[:237].rstrip() + "..."
    return f"{label}: {first}"


def _confidence(
    *,
    signal: CrossReportSignalScore,
    support_level: SignalCandidateSupportLevel,
    evidence_count: int,
    source_count: int,
) -> float:
    base = min(0.95, 0.45 + min(signal.total_score, 5.0) * 0.08)
    base += min(evidence_count, 4) * 0.03
    base += min(source_count, 3) * 0.03
    if support_level == "multi_report_divergent":
        base -= 0.08
    if support_level in {"single_report", "weak_coverage"}:
        base -= 0.12
    return max(0.1, min(0.95, round(base, 2)))


def _group_by_signal_id(
    agreement_result: CrossReportEvidenceAgreementResult,
) -> dict[str, CrossReportEvidenceAgreementGroup]:
    grouped: dict[str, CrossReportEvidenceAgreementGroup] = {}
    for group in agreement_result.evidence_groups:
        for signal_id in group.signal_ids:
            grouped[signal_id] = group
    return grouped


def _raw_context(
    *,
    request: CrossReportAnalysisRequest,
    signal: CrossReportSignalScore,
    group: CrossReportEvidenceAgreementGroup,
    evidence: list[CrossReportEvidenceReference],
    raw_metric_policy: str,
) -> dict[str, Any]:
    return {
        "request": {
            "request_id": request.request_id,
            "topic": request.topic,
            "category_filters": list(request.category_filters),
            "tag_filters": list(request.tag_filters),
        },
        "signal_score": asdict(signal),
        "agreement_group": asdict(group),
        "evidence": [asdict(item) for item in evidence],
        "raw_metric_policy": raw_metric_policy,
    }


def _candidate_from_signal(
    *,
    request: CrossReportAnalysisRequest,
    selected_theme_id: str,
    signal: CrossReportSignalScore,
    group: CrossReportEvidenceAgreementGroup,
    evidence_by_id: dict[str, CrossReportEvidenceReference],
    raw_metric_policy: str,
    generated_at_utc: str,
) -> SignalCandidate:
    group_evidence = [
        evidence_by_id[evidence_id]
        for evidence_id in signal.evidence_ids
        if evidence_id in evidence_by_id
    ]
    if not group_evidence:
        raise AppError(
            code="signal_candidate_unsupported",
            message="Signal candidate requires source-backed evidence.",
            retryable=False,
            severity="error",
            context={
                "signal_id": signal.signal_id,
                "evidence_ids": list(signal.evidence_ids),
            },
        )
    support_level = _support_level(group)
    source_report_ids = _unique_ordered([item.report_id for item in group_evidence])
    candidate = SignalCandidate(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        candidate_id=f"signal-candidate:{selected_theme_id}:{signal.signal_id}",
        candidate_type=_candidate_type(group),
        title=signal.label,
        summary=_summary(signal.label, group_evidence),
        confidence=_confidence(
            signal=signal,
            support_level=support_level,
            evidence_count=len(group_evidence),
            source_count=len(source_report_ids),
        ),
        strength=signal.total_score,
        support_level=support_level,
        caveats=_caveats(group),
        source_report_ids=source_report_ids,
        evidence_ids=[item.evidence_id for item in group_evidence],
        source_refs=[_source_ref(item) for item in group_evidence],
        raw_source_context=_raw_context(
            request=request,
            signal=signal,
            group=group,
            evidence=group_evidence,
            raw_metric_policy=raw_metric_policy,
        ),
        validation_status="approved",
        validation_notes=["source_backed", f"support_level:{support_level}"],
        group_id=f"signal-group:{group.group_id}",
        extraction_request_id=request.request_id,
        generated_at_utc=generated_at_utc,
    )
    validate_signal_candidate_contract(candidate)
    return candidate


def _group_from_candidates(
    *,
    group: CrossReportEvidenceAgreementGroup,
    candidates: list[SignalCandidate],
    generated_at_utc: str,
) -> SignalCandidateGroup:
    if not candidates:
        raise AppError(
            code="signal_candidate_group_empty",
            message="Signal candidate group requires at least one candidate.",
            retryable=False,
            severity="error",
            context={"group_id": group.group_id},
        )
    source_report_ids = _unique_ordered(
        [
            report_id
            for candidate in candidates
            for report_id in candidate.source_report_ids
        ]
    )
    evidence_ids = _unique_ordered(
        [
            evidence_id
            for candidate in candidates
            for evidence_id in candidate.evidence_ids
        ]
    )
    caveats = _unique_ordered(
        [caveat for candidate in candidates for caveat in candidate.caveats]
    )
    support_level = candidates[0].support_level
    candidate_ids = [candidate.candidate_id for candidate in candidates]
    signal_group = SignalCandidateGroup(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        group_id=f"signal-group:{group.group_id}",
        stable_key=f"{group.group_id}:{','.join(candidate_ids)}",
        title=group.label,
        summary=candidates[0].summary,
        support_level=support_level,
        candidate_ids=candidate_ids,
        source_report_ids=source_report_ids,
        evidence_ids=evidence_ids,
        caveats=caveats,
        raw_group_context={
            "agreement_type": group.agreement_type,
            "uncertainty_reasons": list(group.uncertainty_reasons),
            "raw_metric_policy": "raw_metrics_preserved_without_normalization",
        },
        validation_status="approved",
        extraction_request_id=candidates[0].extraction_request_id,
        generated_at_utc=generated_at_utc,
    )
    validate_signal_candidate_contract(signal_group)
    return signal_group


def build_signal_candidate_batch(
    request: CrossReportAnalysisRequest,
    evidence_inputs: CrossReportEvidenceInputResult,
    signal_result,
    agreement_result: CrossReportEvidenceAgreementResult,
    ctx: RunContext,
    *,
    generated_at_utc: str,
) -> SignalCandidateBatch:
    validate_cross_report_contract(request)
    validate_cross_report_contract(evidence_inputs)
    validate_cross_report_contract(signal_result)
    validate_cross_report_contract(agreement_result)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="signal_candidate_batch_build_start",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "signal_count": len(signal_result.signal_scores),
                "evidence_count": len(evidence_inputs.evidence),
                "agreement_group_count": len(agreement_result.evidence_groups),
            },
        )
    )
    evidence_by_id = {item.evidence_id: item for item in evidence_inputs.evidence}
    group_by_signal_id = _group_by_signal_id(agreement_result)
    candidates: list[SignalCandidate] = []
    for signal in signal_result.signal_scores:
        group = group_by_signal_id.get(signal.signal_id)
        if group is None:
            raise AppError(
                code="signal_candidate_group_missing",
                message="Signal candidate requires an evidence agreement group.",
                retryable=False,
                severity="error",
                context={"signal_id": signal.signal_id},
            )
        candidates.append(
            _candidate_from_signal(
                request=request,
                selected_theme_id=signal_result.selected_theme.theme_id,
                signal=signal,
                group=group,
                evidence_by_id=evidence_by_id,
                raw_metric_policy=signal_result.raw_metric_policy,
                generated_at_utc=generated_at_utc,
            )
        )

    candidates_by_group: dict[str, list[SignalCandidate]] = {}
    for candidate in candidates:
        candidates_by_group.setdefault(candidate.group_id, []).append(candidate)
    groups = [
        _group_from_candidates(
            group=group,
            candidates=sorted(
                candidates_by_group.get(f"signal-group:{group.group_id}", []),
                key=lambda candidate: candidate.candidate_id,
            ),
            generated_at_utc=generated_at_utc,
        )
        for group in agreement_result.evidence_groups
        if f"signal-group:{group.group_id}" in candidates_by_group
    ]
    batch = SignalCandidateBatch(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        extraction_request_id=request.request_id,
        generated_at_utc=generated_at_utc,
        candidates=sorted(candidates, key=lambda candidate: candidate.candidate_id),
        groups=sorted(groups, key=lambda group: group.group_id),
    )
    validate_signal_candidate_contract(batch)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="signal_candidate_batch_build_complete",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "candidate_count": len(batch.candidates),
                "group_count": len(batch.groups),
                "candidate_ids": [
                    candidate.candidate_id for candidate in batch.candidates
                ],
                "group_ids": [group.group_id for group in batch.groups],
            },
        )
    )
    return batch
