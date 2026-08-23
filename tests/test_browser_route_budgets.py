from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts._browser_download.session_reuse import (
    BrowserDownloadSessionReuseDecision,
)
from src.contracts.browser_download import (
    BrowserDownloadRouteBudget,
    BrowserReportDownloadRequest,
)
from src.contracts.run_budget import BudgetRequest, RunBudget, RunBudgetUsageReadRequest
from src.contracts.run_context import RunContext
from src.services._browser_report_download.browser import (
    BrowserPreflightSession,
    close_browser_preflight_session,
)
from src.services._browser_report_download.budgets import apply_browser_route_budget
from src.services.llm_usage_ledger_service import (
    evaluate_budget_request,
    read_run_budget_usage,
)
from tests.test_browser_report_download_service.builders import _settings


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _request(tmp_path: Path, *, route_family: str) -> BrowserReportDownloadRequest:
    settings = replace(
        _settings(tmp_path),
        timeout_seconds=30.0,
        max_steps=10,
        route_budgets=[
            BrowserDownloadRouteBudget(
                schema_version="1.0",
                route_family="browser_email_form",
                timeout_seconds=12.0,
                max_steps=4,
            ),
            BrowserDownloadRouteBudget(
                schema_version="1.0",
                route_family="browser_listing_hub",
                timeout_seconds=90.0,
                max_steps=40,
            ),
        ],
    )
    return BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=settings,
        route_family_hint=route_family,
    )


def _service_events(caplog) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != "market_lense.browser_report_download_service":
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            fields = payload.get("fields")
            if isinstance(fields, dict):
                payload = {**payload, **fields}
            events.append(payload)
    return events


def test_apply_browser_route_budget_caps_agent_steps_and_timeout(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    request = _request(tmp_path, route_family="browser_email_form")

    budgeted = apply_browser_route_budget(
        request=request,
        ctx=_ctx(),
        normalized_url="https://example.com/report",
    )

    assert budgeted.settings.max_steps == 4
    assert budgeted.settings.timeout_seconds == 12.0
    assert any(
        event.get("event") == "browser_report_download_route_budget_resolved"
        and event.get("budget_configured") is True
        and event.get("effective_max_steps") == 4
        and event.get("effective_timeout_seconds") == 12.0
        for event in _service_events(caplog)
    )


def test_apply_browser_route_budget_never_exceeds_global_budget(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    request = _request(tmp_path, route_family="browser_listing_hub")

    budgeted = apply_browser_route_budget(
        request=request,
        ctx=_ctx(),
        normalized_url="https://example.com/report",
    )

    assert budgeted.settings.max_steps == 10
    assert budgeted.settings.timeout_seconds == 30.0
    assert any(
        event.get("event") == "browser_report_download_route_budget_resolved"
        and event.get("budget_configured") is True
        and event.get("configured_max_steps") == 40
        and event.get("effective_max_steps") == 10
        for event in _service_events(caplog)
    )


def test_apply_browser_route_budget_preserves_unconfigured_route(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    request = _request(tmp_path, route_family="browser_onsite_report")

    budgeted = apply_browser_route_budget(
        request=request,
        ctx=_ctx(),
        normalized_url="https://example.com/report",
    )

    assert budgeted is request
    assert any(
        event.get("event") == "browser_report_download_route_budget_resolved"
        and event.get("budget_configured") is False
        and event.get("effective_max_steps") == 10
        for event in _service_events(caplog)
    )


@pytest.mark.parametrize(
    "lifecycle_outcome", ["deterministic_handoff", "deterministic_isolation"]
)
def test_preflight_lifecycle_transition_finalizes_browser_budget_as_completed(
    tmp_path, lifecycle_outcome: str
) -> None:
    class NoopBrowser:
        def kill(self) -> None:
            return None

    ctx = _ctx()
    budget = RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name="publisher-a",
        usage_db_path=str(tmp_path / "usage.sqlite"),
    )
    decision = evaluate_budget_request(
        BudgetRequest(
            schema_version="1.0",
            budget=budget,
            run_id=ctx.run_id,
            workflow_id="browser_acquisition",
            publisher_id="publisher-a",
            report_id="report-a",
            resource_type="browser_launch",
            operation="browser_launch",
            idempotency_key="browser-launch:handoff",
            reserve_in_flight=True,
        ),
        ctx,
    )
    session = BrowserPreflightSession(
        browser_use=object(),
        browser=NoopBrowser(),
        launch_budget=budget,
        launch_decision=decision,
        launch_started_at=0.0,
        session_reuse_decision=BrowserDownloadSessionReuseDecision(
            schema_version="1.0",
            enabled=False,
            accepted=False,
            mode="disabled",
            session_key_hash="",
            publisher_scope="",
            profile_path="",
            profile_reused=False,
            ttl_seconds=0.0,
            expires_at_epoch_seconds=0.0,
            cleanup_removed_count=0,
        ),
        profile_dir=tmp_path / "profile",
        preexisting_temp_dirs=set(),
    )

    close_browser_preflight_session(
        session=session,
        ctx=ctx,
        normalized_url="https://publisher.example/report",
        outcome=lifecycle_outcome,
    )

    usage = read_run_budget_usage(
        RunBudgetUsageReadRequest(schema_version="1.0", budget=budget), ctx
    ).usage
    assert usage.browser_launches == 1
