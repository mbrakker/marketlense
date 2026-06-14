from __future__ import annotations

import logging
from typing import Callable

from src.contracts.cross_report_analysis import (
    CrossReportProjectedDataReadRequest,
    CrossReportProjectedDataReadResponse,
)
from src.contracts.run_context import RunContext
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidateExtractionOutcome,
    SignalCandidateExtractionRequest,
    SignalCandidateStoreRequest,
    SignalCandidateStoreResponse,
    validate_signal_candidate_contract,
)
from src.generators.cross_report_analysis_input_generator import (
    assemble_cross_report_analysis_inputs,
    group_cross_report_evidence_agreement,
    score_cross_report_signals,
    select_cross_report_source_reports,
    select_cross_report_theme,
)
from src.generators.signal_candidate_generator import build_signal_candidate_batch
from src.services import analytics_store_service
from src.utils.clock import utc_now_iso as _utc_now
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.signal_candidate_orchestrator")


def _log_transition(
    ctx: RunContext,
    transitions: list[str],
    transition: str,
) -> None:
    transitions.append(transition)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="signal_candidate_extraction_transition",
            module=logger.name,
            fields={"transition": transition},
        )
    )


def run_signal_candidate_extraction(
    request: SignalCandidateExtractionRequest,
    ctx: RunContext,
    *,
    read_projected_data_fn: Callable[
        [CrossReportProjectedDataReadRequest, RunContext],
        CrossReportProjectedDataReadResponse,
    ] = analytics_store_service.read_cross_report_projected_data,
    upsert_signal_candidates_fn: Callable[
        [SignalCandidateStoreRequest, RunContext],
        SignalCandidateStoreResponse,
    ] = analytics_store_service.upsert_signal_candidates,
) -> SignalCandidateExtractionOutcome:
    validate_signal_candidate_contract(request)
    transitions: list[str] = []
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="signal_candidate_extraction_start",
            module=logger.name,
            fields={
                "extraction_request_id": request.extraction_request_id,
                "db_path": request.db_path,
                "projected_data_db_path": request.projected_data_request.db_path,
                "max_evidence_items": request.max_evidence_items,
                "max_signals": request.max_signals,
            },
        )
    )
    _log_transition(ctx, transitions, "started")

    projected_data = read_projected_data_fn(request.projected_data_request, ctx)
    _log_transition(ctx, transitions, "projected_data_read")
    source_selection = select_cross_report_source_reports(
        request.analysis_request,
        projected_data,
        ctx,
    )
    _log_transition(ctx, transitions, "source_selected")
    theme_selection = select_cross_report_theme(
        request.analysis_request,
        source_selection,
        ctx,
    )
    _log_transition(ctx, transitions, "theme_selected")
    evidence_inputs = assemble_cross_report_analysis_inputs(
        request.analysis_request,
        source_selection,
        projected_data,
        ctx,
        max_evidence_items=request.max_evidence_items,
    )
    _log_transition(ctx, transitions, "evidence_assembled")
    signal_result = score_cross_report_signals(
        request.analysis_request,
        evidence_inputs,
        theme_selection,
        ctx,
        max_signals=request.max_signals,
    )
    _log_transition(ctx, transitions, "signals_scored")
    agreement_result = group_cross_report_evidence_agreement(
        request.analysis_request,
        evidence_inputs,
        signal_result,
        ctx,
    )
    _log_transition(ctx, transitions, "agreement_grouped")
    generated_at_utc = request.generated_at_utc.strip() or _utc_now()
    batch = build_signal_candidate_batch(
        request.analysis_request,
        evidence_inputs,
        signal_result,
        agreement_result,
        ctx,
        generated_at_utc=generated_at_utc,
    )
    _log_transition(ctx, transitions, "candidates_built")
    store_request = SignalCandidateStoreRequest(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        db_path=request.db_path,
        extraction_request_id=request.extraction_request_id,
        candidates=batch.candidates,
        groups=batch.groups,
    )
    stored_response = upsert_signal_candidates_fn(store_request, ctx)
    _log_transition(ctx, transitions, "candidates_stored")
    outcome = SignalCandidateExtractionOutcome(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        extraction_request_id=request.extraction_request_id,
        status="stored",
        batch=batch,
        stored_response=stored_response,
        candidate_count=len(batch.candidates),
        group_count=len(batch.groups),
        state_transitions=[*transitions, "completed"],
    )
    validate_signal_candidate_contract(outcome)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="signal_candidate_extraction_complete",
            module=logger.name,
            fields={
                "extraction_request_id": outcome.extraction_request_id,
                "status": outcome.status,
                "candidate_count": outcome.candidate_count,
                "group_count": outcome.group_count,
                "candidate_ids": [
                    candidate.candidate_id for candidate in outcome.batch.candidates
                ],
                "group_ids": [group.group_id for group in outcome.batch.groups],
            },
        )
    )
    return outcome
