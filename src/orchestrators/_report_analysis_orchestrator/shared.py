"""Shared logging surface for report-analysis orchestration helpers.

The public orchestrator remains `src.orchestrators.report_analysis_orchestrator`;
private owners import this logger so existing event module names remain stable.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("market_lense.report_analysis_orchestrator")
