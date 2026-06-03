from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.run_context import RunContext
from src.contracts.signal_candidates import (
    SignalCandidateExtractionOutcome,
    SignalCandidateExtractionRequest,
)
from src.orchestrators.signal_candidate_orchestrator import (
    run_signal_candidate_extraction,
)
from src.services import report_analysis_store_service


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
            run_signal_candidate_extraction=run_signal_candidate_extraction,
            analysis_store_pack=report_analysis_store_service.store_pack,
        )
