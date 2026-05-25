from __future__ import annotations

import json
import logging

from src.contracts.prompts import PromptDryRunRequest
from src.services.prompt_service import validate_prompt_dry_run


def _events(caplog) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != "market_lense.prompt_service":
            continue
        try:
            payload = json.loads(record.message)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def test_cross_report_synthesis_prompt_namespace_dry_run_logs_hashes(
    run_context,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.prompt_service")

    response = validate_prompt_dry_run(
        PromptDryRunRequest(
            schema_version="1.0",
            namespaces=["cross_report_analysis/synthesis"],
            force_reload=True,
        ),
        run_context,
    )

    assert len(response.results) == 1
    result = response.results[0]
    assert result.namespace == "cross_report_analysis/synthesis"
    assert result.family == "cross_report_analysis"
    assert result.system_sha256
    assert result.user_sha256
    assert "Cross-report synthesis input JSON" in result.rendered_user_prompt
    assert "ev-report-a-claim-1" in result.rendered_user_prompt
    assert "raw_metric_policy" in result.rendered_user_prompt
    assert "divergent" in result.rendered_user_prompt
    assert "industry expert" in result.rendered_system_prompt
    assert "boardroom-ready editorial article" in result.rendered_user_prompt
    assert "consulting-grade synthesis" in result.rendered_user_prompt
    assert "full_report_text" not in result.rendered_user_prompt

    events = _events(caplog)
    assert_logs_have_required_fields(events)
    validated = [
        event
        for event in events
        if event["event"] == "prompt_dry_run_namespace_validated"
    ][0]
    assert validated["fields"]["namespace"] == "cross_report_analysis/synthesis"
    assert validated["fields"]["system_sha256"] == result.system_sha256
    assert validated["fields"]["user_sha256"] == result.user_sha256
