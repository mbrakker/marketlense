from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

from src.contracts.browser_download import (
    BrowserDownloadRouteBudget,
    BrowserReportDownloadRequest,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.budgets import apply_browser_route_budget

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
