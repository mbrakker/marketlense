from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.run_context import RunContext
from src.contracts.signal_candidates import (
    SignalCandidateExtractionOutcome,
    SignalCandidateExtractionRequest,
)
from src.services import report_analysis_store_service
from src.utils.errors import AppError


def _signal_candidate_dependency_not_wired(
    request: SignalCandidateExtractionRequest,
    ctx: RunContext,
) -> SignalCandidateExtractionOutcome:
    raise AppError(
        code="report_signal_dependency_not_wired",
        message="Signal candidate extraction must be wired by an orchestrator.",
        retryable=False,
        context={"extraction_request_id": request.extraction_request_id},
    )


@dataclass(frozen=True)
class ReportSignalDependencies:
    run_signal_candidate_extraction: Callable[
        [SignalCandidateExtractionRequest, RunContext],
        SignalCandidateExtractionOutcome,
    ]
    analysis_store_pack: Callable[[AnalysisStorePackRequest, RunContext], object]

    @classmethod
    def default(cls) -> "ReportSignalDependencies":
        return cls(
            run_signal_candidate_extraction=_signal_candidate_dependency_not_wired,
            analysis_store_pack=report_analysis_store_service.store_pack,
        )
