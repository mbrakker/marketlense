from __future__ import annotations

import logging

from src.contracts.costs import CostReportingRequest, CostReportingResponse
from src.contracts.run_context import RunContext
from src.services.cost_ledger_service import generate_cost_report, rollup_daily
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.cost_reporting_orchestrator")


def run_cost_reporting(request: CostReportingRequest, ctx: RunContext) -> CostReportingResponse:
    if request.report_request is None and request.rollup_request is None:
        raise ValueError("At least one of report_request or rollup_request must be provided.")

    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="cost_reporting_start",
        module=logger.name,
        fields={
            "has_report_request": request.report_request is not None,
            "has_rollup_request": request.rollup_request is not None,
        },
    ))

    report = generate_cost_report(request.report_request, ctx) if request.report_request else None
    rollup = rollup_daily(request.rollup_request, ctx) if request.rollup_request else None

    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="cost_reporting_complete",
        module=logger.name,
        fields={
            "report_filter_type": report.filter_type if report else "",
            "report_filter_value": report.filter_value if report else "",
            "report_matched_entries": report.matched_entries if report else 0,
            "rollup_out_path": rollup.out_path if rollup else "",
            "rollup_days": len(rollup.totals_by_date) if rollup else 0,
        },
    ))
    return CostReportingResponse(
        schema_version="1.0",
        report=report,
        rollup=rollup,
    )
