from __future__ import annotations

from dataclasses import dataclass

from .analysis import ReportAnalysisDependencies
from .render import ReportRenderDependencies
from .selection import ReportSelectionDependencies
from .source import ReportSourceDependencies


@dataclass(frozen=True)
class ReportGenerationDependencies:
    source: ReportSourceDependencies
    selection: ReportSelectionDependencies
    analysis: ReportAnalysisDependencies
    render: ReportRenderDependencies

    @classmethod
    def default(cls) -> "ReportGenerationDependencies":
        return cls(
            source=ReportSourceDependencies.default(),
            selection=ReportSelectionDependencies.default(),
            analysis=ReportAnalysisDependencies.default(),
            render=ReportRenderDependencies.default(),
        )

