"""Report-generation dependency facade.

This module preserves the public import surface while semantic dependency
families live under `src/generators/_report_generation_dependencies/`.
"""

from __future__ import annotations

from ._report_generation_dependencies.analysis import ReportAnalysisDependencies
from ._report_generation_dependencies.bundle import ReportGenerationDependencies
from ._report_generation_dependencies.figure_caption import (
    FigureCaptionDependencies,
)
from ._report_generation_dependencies.render import ReportRenderDependencies
from ._report_generation_dependencies.selection import ReportSelectionDependencies
from ._report_generation_dependencies.signal import ReportSignalDependencies
from ._report_generation_dependencies.source import ReportSourceDependencies

__all__ = [
    "FigureCaptionDependencies",
    "ReportAnalysisDependencies",
    "ReportGenerationDependencies",
    "ReportRenderDependencies",
    "ReportSelectionDependencies",
    "ReportSignalDependencies",
    "ReportSourceDependencies",
]
