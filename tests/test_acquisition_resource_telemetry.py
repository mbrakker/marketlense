from __future__ import annotations

import sqlite3

from src.contracts.browser_download import (
    BrowserDownloadIdentity,
    BrowserDownloadSettings,
    ReportDownloadOrchestratorRequest,
)
from src.contracts.llm_usage import (
    LLMUsageLedgerAppendRequest,
    LLMUsageLedgerEntry,
    LLMUsageRunSummaryRequest,
)
from src.contracts.report_store import (
    AcquisitionAttemptResourceRecordRequest,
    AcquisitionAttemptResourceSummary,
    AcquisitionResourceAggregateRequest,
    AcquisitionRouteSuppressionRequest,
)
from src.contracts.run_budget import RunBudget, RunBudgetEventAppendRequest
from src.contracts.run_context import RunContext
from src.orchestrators._report_download_orchestrator.budget import (
    read_report_download_run_usage,
)
from src.orchestrators._report_download_orchestrator.dependencies import (
    ReportDownloadDependencies,
)
from src.orchestrators._report_download_orchestrator.resource_telemetry import (
    capture_acquisition_resource_usage,
    record_acquisition_resource_summary,
)
from src.services.llm_usage_ledger_service import (
    append_run_budget_side_effect,
    append_usage,
    read_usage_run_summary,
)
from src.services.report_store_service import (
    evaluate_acquisition_route_suppression,
    list_acquisition_resource_aggregates,
    record_acquisition_attempt_resource,
)


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="acq-run", task_id="task", span_id="span"
    )


def _telemetry_settings(tmp_path) -> BrowserDownloadSettings:
    return BrowserDownloadSettings(
        schema_version="1.0",
        openrouter_api_key="",
        model="gpt-5-mini",
        temperature=0.0,
        timeout_seconds=30.0,
        max_steps=5,
        output_dir=str(tmp_path / "downloads"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        identity_config_path=str(tmp_path / "identity.yaml"),
        identity_profile=BrowserDownloadIdentity(schema_version="1.0", fields=[]),
        usage_db_path=str(tmp_path / "usage.sqlite"),
        run_budget_enabled=True,
    )


def _telemetry_request(tmp_path) -> ReportDownloadOrchestratorRequest:
    settings = _telemetry_settings(tmp_path)
    return ReportDownloadOrchestratorRequest(
        schema_version="1.0",
        url="https://publisher.example/report",
        settings=settings,
        state_db=settings.state_db,
        reports_db=settings.reports_db,
        publisher_name="publisher-a",
    )


def _append_browser_usage(
    *, db_path: str, ctx: RunContext, input_tokens: int, output_tokens: int, cost: float
) -> None:
    append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=db_path,
            entry=LLMUsageLedgerEntry(
                schema_version="1.0",
                timestamp_utc="2026-08-16T10:00:00+00:00",
                provider="openai",
                action="browser_use_llm_call",
                run_id=ctx.run_id,
                task_id=ctx.task_id,
                span_id=ctx.span_id,
                trace_id="trace",
                model="gpt-5-mini",
                request_id=f"request-{ctx.task_id}",
                publisher_name="publisher-a",
                report_name="report",
                source_url="https://publisher.example/report",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                cached_input_tokens=0,
                tool_calls=0,
                estimated_cost_usd=cost,
                prompt_namespace="browser",
                prompt_hash="hash",
                provider_decision="direct",
                cache_decision="miss",
                temperature=0.0,
                seed=None,
                timeout_seconds=30.0,
                metadata={},
            ),
        ),
        ctx,
    )


def _append_acquisition_side_effects(
    *, db_path: str, ctx: RunContext, retries: int
) -> None:
    budget = RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name="publisher-a",
        usage_db_path=db_path,
        day_utc="2026-08-16",
    )
    append_run_budget_side_effect(
        RunBudgetEventAppendRequest(
            schema_version="1.0",
            budget=budget,
            event_key=f"browser-launch:{ctx.task_id}",
            metric="browser_launches",
        ),
        ctx,
    )
    append_run_budget_side_effect(
        RunBudgetEventAppendRequest(
            schema_version="1.0",
            budget=budget,
            event_key=f"retry:{ctx.task_id}",
            metric="retries",
            quantity=retries,
        ),
        ctx,
    )


def _summary(
    *, attempt_id: str, outcome: str, reason: str = ""
) -> AcquisitionAttemptResourceSummary:
    return AcquisitionAttemptResourceSummary(
        schema_version="1.0",
        attempt_id=attempt_id,
        publisher_id="publisher-a",
        source_identity_id="source-1" if outcome == "success" else "",
        source_identity_status="resolved" if outcome == "success" else "unresolved",
        normalized_url="https://publisher.example/report",
        route_family="browser_email_form",
        route_policy_version="1.0",
        source_policy_compatibility_hash="policy-a",
        started_at_utc="2026-07-19T10:00:00+00:00",
        completed_at_utc="2026-07-19T10:00:01+00:00",
        elapsed_ms=1000,
        terminal_outcome=outcome,
        browser_launches=0 if outcome == "success" else 1,
        browser_steps=0 if outcome == "success" else 4,
        browser_model_calls=0 if outcome == "success" else 2,
        input_tokens=0 if outcome == "success" else 120,
        cached_input_tokens=0,
        output_tokens=0 if outcome == "success" else 40,
        terminal_reason=reason,
        verified_artifact_hash="md5:abc" if outcome == "success" else "",
        estimated_cost_usd=0.0 if outcome == "success" else 0.012,
        incomplete_fields=("mailbox_reads",) if outcome == "success" else (),
    )


def _record(tmp_path, summary: AcquisitionAttemptResourceSummary) -> None:
    record_acquisition_attempt_resource(
        AcquisitionAttemptResourceRecordRequest(
            schema_version="1.0",
            db_path=str(tmp_path / "reports.sqlite"),
            summary=summary,
        ),
        _ctx(),
    )


def _suppression_request(tmp_path, **overrides) -> AcquisitionRouteSuppressionRequest:
    values = {
        "schema_version": "1.0",
        "db_path": str(tmp_path / "reports.sqlite"),
        "normalized_url": "https://publisher.example/report",
        "publisher_id": "publisher-a",
        "route_family": "browser_email_form",
        "policy_version": "1.0",
        "source_policy_compatibility_hash": "policy-a",
        "enabled": True,
        "minimum_sample_size": 3,
        "terminal_failure_threshold": 1.0,
        "terminal_failure_classes": ("blocked_captcha", "blocked_email_domain"),
        "ttl_seconds": 60,
        "now_utc": "2026-07-19T10:02:00+00:00",
    }
    values.update(overrides)
    return AcquisitionRouteSuppressionRequest(**values)


def test_aggregate_keeps_incomplete_records_distinct_from_zero_usage(tmp_path) -> None:
    _record(tmp_path, _summary(attempt_id="direct-success", outcome="success"))

    aggregate = list_acquisition_resource_aggregates(
        AcquisitionResourceAggregateRequest(
            schema_version="1.0", db_path=str(tmp_path / "reports.sqlite")
        ),
        _ctx(),
    ).aggregates

    assert len(aggregate) == 1
    row = aggregate[0]
    assert row.sample_size == 1
    assert row.verified_acquisition_count == 1
    assert row.estimated_cost_usd == 0.0
    assert row.incomplete_record_count == 1
    assert row.cost_per_verified_acquisition_usd == 0.0


def test_terminal_suppression_requires_three_compatible_failures_and_expires(
    tmp_path,
) -> None:
    _record(
        tmp_path,
        _summary(attempt_id="failure-1", outcome="failed", reason="blocked_captcha"),
    )
    _record(
        tmp_path,
        _summary(attempt_id="failure-2", outcome="failed", reason="blocked_captcha"),
    )

    below_threshold = evaluate_acquisition_route_suppression(
        _suppression_request(tmp_path), _ctx()
    )

    assert not below_threshold.suppressed
    assert below_threshold.reason == "insufficient_terminal_failure_evidence"

    _record(
        tmp_path,
        _summary(attempt_id="failure-3", outcome="failed", reason="blocked_captcha"),
    )
    active = evaluate_acquisition_route_suppression(
        _suppression_request(tmp_path), _ctx()
    )

    assert active.suppressed
    assert active.sample_size == 3
    assert active.terminal_failure_count == 3

    expired = evaluate_acquisition_route_suppression(
        _suppression_request(tmp_path, now_utc="2026-07-19T10:04:00+00:00"), _ctx()
    )

    assert expired.suppressed
    assert expired.decision_id != active.decision_id


def test_changed_policy_and_explicit_revalidation_do_not_suppress(tmp_path) -> None:
    for index in range(3):
        _record(
            tmp_path,
            _summary(
                attempt_id=f"failure-{index}",
                outcome="failed",
                reason="blocked_email_domain",
            ),
        )

    activated = evaluate_acquisition_route_suppression(
        _suppression_request(tmp_path), _ctx()
    )
    changed_policy = evaluate_acquisition_route_suppression(
        _suppression_request(tmp_path, source_policy_compatibility_hash="policy-b"),
        _ctx(),
    )
    explicit_revalidation = evaluate_acquisition_route_suppression(
        _suppression_request(tmp_path, revalidation_override=True), _ctx()
    )

    assert not changed_policy.suppressed
    assert changed_policy.sample_size == 0
    assert not explicit_revalidation.suppressed
    assert explicit_revalidation.reason == "explicit_revalidation_override"

    response = record_acquisition_attempt_resource(
        AcquisitionAttemptResourceRecordRequest(
            schema_version="1.0",
            db_path=str(tmp_path / "reports.sqlite"),
            summary=AcquisitionAttemptResourceSummary(
                **{
                    **_summary(attempt_id="revalidated", outcome="success").__dict__,
                    "revalidation_override": True,
                }
            ),
        ),
        _ctx(),
    )
    after_success = evaluate_acquisition_route_suppression(
        _suppression_request(tmp_path), _ctx()
    )

    assert activated.suppressed
    assert response.superseded_suppression_count == 1
    assert not after_success.suppressed


def test_sequential_acquisitions_record_only_their_own_ledger_usage(tmp_path) -> None:
    request = _telemetry_request(tmp_path)
    first_ctx = RunContext(
        schema_version="1.0", run_id="shared-run", task_id="first", span_id="one"
    )
    second_ctx = RunContext(
        schema_version="1.0", run_id="shared-run", task_id="second", span_id="two"
    )

    first_start = capture_acquisition_resource_usage(request=request, ctx=first_ctx)
    _append_browser_usage(
        db_path=request.settings.usage_db_path,
        ctx=first_ctx,
        input_tokens=11,
        output_tokens=7,
        cost=0.0011,
    )
    _append_acquisition_side_effects(
        db_path=request.settings.usage_db_path, ctx=first_ctx, retries=1
    )
    record_acquisition_resource_summary(
        request=request,
        ctx=first_ctx,
        dependencies=ReportDownloadDependencies.default(),
        started_at_utc="2026-08-16T10:00:00+00:00",
        started_monotonic=0.0,
        route_family="browser_email_form",
        terminal_outcome="success",
        usage_at_start=first_start,
    )

    second_start = capture_acquisition_resource_usage(request=request, ctx=second_ctx)
    _append_browser_usage(
        db_path=request.settings.usage_db_path,
        ctx=second_ctx,
        input_tokens=13,
        output_tokens=5,
        cost=0.0023,
    )
    _append_acquisition_side_effects(
        db_path=request.settings.usage_db_path, ctx=second_ctx, retries=2
    )
    record_acquisition_resource_summary(
        request=request,
        ctx=second_ctx,
        dependencies=ReportDownloadDependencies.default(),
        started_at_utc="2026-08-16T10:01:00+00:00",
        started_monotonic=0.0,
        route_family="browser_email_form",
        terminal_outcome="success",
        usage_at_start=second_start,
    )

    with sqlite3.connect(request.reports_db) as conn:
        rows = conn.execute(
            """
            select browser_model_calls, input_tokens, output_tokens,
                   browser_launches, retry_count, estimated_cost_usd
            from acquisition_attempt_resources
            order by started_at_utc
            """
        ).fetchall()

    assert rows == [(1, 11, 7, 1, 1, 0.0011), (1, 13, 5, 1, 2, 0.0023)]
    run_usage = read_usage_run_summary(
        LLMUsageRunSummaryRequest(
            schema_version="1.0",
            db_path=request.settings.usage_db_path,
            run_id="shared-run",
            action="browser_use_llm_call",
        ),
        first_ctx,
    )
    assert sum(row[0] for row in rows) == run_usage.call_count
    assert sum(row[1] for row in rows) == run_usage.input_tokens
    assert sum(row[2] for row in rows) == run_usage.output_tokens
    assert round(sum(row[5] for row in rows), 6) == run_usage.estimated_cost_usd
    run_budget_usage = read_report_download_run_usage(
        request=request, ctx=first_ctx
    )
    assert sum(row[3] for row in rows) == run_budget_usage.browser_launches
    assert sum(row[4] for row in rows) == run_budget_usage.retries
