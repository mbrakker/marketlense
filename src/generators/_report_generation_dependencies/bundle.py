from __future__ import annotations

from dataclasses import dataclass

from .analysis import ReportAnalysisDependencies
from .render import ReportRenderDependencies
from .selection import ReportSelectionDependencies
from .signal import ReportSignalDependencies
from .source import ReportSourceDependencies
from .source_scoring import ReportSourceScoringDependencies


@dataclass(frozen=True)
class ReportGenerationDependencies:
    source: ReportSourceDependencies
    selection: ReportSelectionDependencies
    analysis: ReportAnalysisDependencies
    render: ReportRenderDependencies
    signal: ReportSignalDependencies
    source_scoring: ReportSourceScoringDependencies

    @classmethod
    def default(cls) -> "ReportGenerationDependencies":
        return cls(
            source=ReportSourceDependencies.default(),
            selection=ReportSelectionDependencies.default(),
            analysis=ReportAnalysisDependencies.default(),
            render=ReportRenderDependencies.default(),
            signal=ReportSignalDependencies.default(),
            source_scoring=ReportSourceScoringDependencies.default(),
        )
