from __future__ import annotations

import time
from typing import Iterable

from src.contracts.browser_download import (
    BrowserDownloadRouteStep,
    BrowserReportDownloadResult,
    ReportDownloadDriveUpload,
    ReportDownloadOrchestratorRequest,
)
from src.contracts.llm_usage import LLMUsageRunSummaryRequest
from src.contracts.report_store import (
    AcquisitionAttemptResourceRecordRequest,
    AcquisitionAttemptResourceSummary,
)
from src.contracts.run_context import RunContext
from src.orchestrators._report_download_orchestrator.budget import (
    read_report_download_run_usage,
)
from src.orchestrators._report_download_orchestrator.dependencies import (
    ReportDownloadDependencies,
)
from src.services.llm_usage_ledger_service import read_usage_run_summary
from src.utils.cache_utils import sha256_json
from src.utils.clock import utc_now_seconds_z


def route_suppression_policy_hash(request: ReportDownloadOrchestratorRequest) -> str:
    policy = request.settings.route_suppression_policy
    return sha256_json(
        {
            "schema_version": policy.schema_version,
            "enabled": policy.enabled,
            "minimum_sample_size": policy.minimum_sample_size,
            "terminal_failure_threshold": policy.terminal_failure_threshold,
            "ttl_seconds": policy.ttl_seconds,
            "terminal_failure_classes": sorted(policy.terminal_failure_classes),
        }
    )


def record_acquisition_resource_summary(
    *,
    request: ReportDownloadOrchestratorRequest,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
    started_at_utc: str,
    started_monotonic: float,
    route_family: str,
    terminal_outcome: str,
    terminal_reason: str = "",
    result: BrowserReportDownloadResult | None = None,
    source_identity_id: str = "",
    verified_artifact_hash: str = "",
    drive_uploads: Iterable[ReportDownloadDriveUpload] = (),
    avoided_operations: tuple[str, ...] = (),
) -> None:
    """Persist scalar acquisition telemetry using the canonical usage ledger."""
    usage = read_usage_run_summary(
        LLMUsageRunSummaryRequest(
            schema_version="1.0",
            db_path=request.settings.usage_db_path,
            run_id=ctx.run_id,
            action="browser_use_llm_call",
        ),
        ctx,
    )
    budget_usage = read_report_download_run_usage(request=request, ctx=ctx)
    steps = list(result.route_steps) if result is not None else []
    uploads = list(drive_uploads)
    browser_family = route_family.startswith("browser_")
    browser_launches = max(0, int(budget_usage.browser_launches))
    if browser_family and browser_launches == 0 and terminal_outcome != "suppressed":
        browser_launches = 1
    drive_writes = max(
        int(budget_usage.drive_writes),
        sum(1 for upload in uploads if upload.status == "uploaded"),
    )
    incomplete_fields = set()
    if not request.settings.run_budget_enabled:
        incomplete_fields.update({"drive_reads", "mailbox_reads", "retry_count"})
    if not browser_family and usage.call_count == 0:
        # A direct route's zero browser-model use is observed, not inferred.
        incomplete_fields.discard("browser_model_calls")
    completed_at_utc = utc_now_seconds_z()
    policy = request.settings.route_suppression_policy
    summary = AcquisitionAttemptResourceSummary(
        schema_version="1.0",
        attempt_id=sha256_json(
            {
                "run_id": ctx.run_id,
                "task_id": ctx.task_id,
                "normalized_url": _normalized_url(request, result),
                "route_family": route_family,
                "started_at_utc": started_at_utc,
                "terminal_outcome": terminal_outcome,
                "terminal_reason": terminal_reason,
            }
        ),
        publisher_id=str(request.publisher_name or "").strip(),
        source_identity_id=source_identity_id,
        source_identity_status=_source_identity_status(
            result=result,
            source_identity_id=source_identity_id,
        ),
        normalized_url=_normalized_url(request, result),
        route_family=route_family or "unknown",
        route_policy_version=policy.schema_version,
        source_policy_compatibility_hash=route_suppression_policy_hash(request),
        started_at_utc=started_at_utc,
        completed_at_utc=completed_at_utc,
        elapsed_ms=max(0, round((time.monotonic() - started_monotonic) * 1000)),
        browser_launches=browser_launches,
        browser_steps=len(steps),
        page_navigations=sum(
            1
            for step in steps
            if str(step.action or "").strip().lower() in {"open", "navigate", "goto"}
        ),
        screenshots=_screenshot_count(steps=steps, result=result),
        browser_model_calls=usage.call_count,
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        output_tokens=usage.output_tokens,
        drive_reads=max(0, int(budget_usage.drive_reads)),
        drive_writes=max(0, drive_writes),
        mailbox_reads=max(0, int(budget_usage.mailbox_reads)),
        retry_count=max(0, int(budget_usage.retries)),
        terminal_outcome=terminal_outcome,
        terminal_reason=str(terminal_reason or "").strip(),
        verified_artifact_hash=verified_artifact_hash,
        estimated_cost_usd=usage.estimated_cost_usd,
        avoided_operations=tuple(sorted(set(avoided_operations)))[:8],
        incomplete_fields=tuple(sorted(incomplete_fields))[:12],
        revalidation_override=request.revalidate_route_policy,
    )
    dependencies.record_acquisition_attempt_resource(
        AcquisitionAttemptResourceRecordRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            summary=summary,
        ),
        ctx,
    )


def _source_identity_status(
    *,
    result: BrowserReportDownloadResult | None,
    source_identity_id: str,
) -> str:
    if source_identity_id:
        return "resolved"
    if result is not None and result.outcome == "email_requested":
        return "provisional"
    return "unresolved"


def _normalized_url(
    request: ReportDownloadOrchestratorRequest,
    result: BrowserReportDownloadResult | None,
) -> str:
    if result is not None and str(result.normalized_url or "").strip():
        return str(result.normalized_url).strip()
    from src.utils.url_utils import normalize_url

    return normalize_url(request.url)


def _screenshot_count(
    *, steps: list[BrowserDownloadRouteStep], result: BrowserReportDownloadResult | None
) -> int:
    step_count = sum(
        1
        for step in steps
        if "screenshot"
        in {str(label or "").strip().lower() for label in step.observed_evidence}
    )
    terminal_path = (
        str(result.terminal_evidence.screenshot_path or "") if result else ""
    )
    return max(step_count, 1 if terminal_path else 0)
