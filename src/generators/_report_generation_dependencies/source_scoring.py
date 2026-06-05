from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.contracts.report_store import (
    ReportSourceRecordRequest,
    ReportSourceRecordResponse,
    ReportValueScoreRecordRequest,
    ReportValueScoreRequest,
    ReportValueScoreResponse,
)
from src.contracts.run_context import RunContext
from src.generators.report_value_generator import score_report_value
from src.services.report_store_service import (
    record_report_source,
    record_report_value_score,
)


@dataclass(frozen=True)
class ReportSourceScoringDependencies:
    record_report_source: Callable[
        [ReportSourceRecordRequest, RunContext], ReportSourceRecordResponse
    ]
    score_report_value: Callable[
        [ReportValueScoreRequest, RunContext], ReportValueScoreResponse
    ]
    record_report_value_score: Callable[
        [ReportValueScoreRecordRequest, RunContext], None
    ]

    @classmethod
    def default(cls) -> "ReportSourceScoringDependencies":
        return cls(
            record_report_source=record_report_source,
            score_report_value=score_report_value,
            record_report_value_score=record_report_value_score,
        )
