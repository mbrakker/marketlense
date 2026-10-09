from __future__ import annotations

import pytest

from src.contracts.llm_usage import LLMUsageLedgerAppendRequest, LLMUsageLedgerEntry
from src.contracts.publish import PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.wordpress import WordPressAuthSettings
from src.orchestrators._publish_orchestrator.budget import (
    build_publish_budget,
    read_publish_budget_usage,
    record_publish_budget_write,
)
from src.orchestrators.publish_orchestrator import run_publish
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="publish-budget-run",
        task_id="publish",
        span_id="publish-span",
    )


def test_publish_budget_records_final_wordpress_write_in_canonical_ledger(
    tmp_path,
) -> None:
    settings = PublishSettings(
        schema_version="1.0",
        output_dir=str(tmp_path / "out"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path=str(tmp_path / "categories.yaml"),
        wp=WordPressAuthSettings(
            schema_version="1.0",
            site_url="http://wordpress.local",
            username="operator",
            app_password="secret",
            bearer_token=None,
            post_status="publish",
        ),
        run_budget_enabled=True,
        usage_db_path=str(tmp_path / "llm_usage.sqlite"),
        run_budget_max_wordpress_writes=1,
    )

    budget = build_publish_budget(settings, _ctx())
    assert budget is not None
    assert budget.projection_ledger_path == ""

    record_publish_budget_write(
        budget,
        event_key="wordpress:publish-budget-run:report-1",
        ctx=_ctx(),
    )
    record_publish_budget_write(
        budget,
        event_key="wordpress:publish-budget-run:report-1",
        ctx=_ctx(),
    )

    usage = read_publish_budget_usage(budget, _ctx())
    assert usage is not None
    assert usage.wordpress_writes == 1


def test_publish_budget_materializes_current_projection_before_release(
    tmp_path,
) -> None:
    ledger_path = tmp_path / "cost-ledger.jsonl"
    daily_path = tmp_path / "cost-daily.json"
    settings = PublishSettings(
        schema_version="1.0",
        output_dir=str(tmp_path / "out"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path=str(tmp_path / "categories.yaml"),
        wp=WordPressAuthSettings(
            schema_version="1.0",
            site_url="http://wordpress.local",
            username="operator",
            app_password="secret",
            bearer_token=None,
            post_status="publish",
        ),
        run_budget_enabled=True,
        usage_db_path=str(tmp_path / "llm_usage.sqlite"),
        projection_ledger_path=str(ledger_path),
        projection_daily_path=str(daily_path),
    )
    budget = build_publish_budget(settings, _ctx())
    assert budget is not None

    from src.services.llm_usage_ledger_service import append_usage

    append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=budget.usage_db_path,
            entry=LLMUsageLedgerEntry(
                schema_version="1.0",
                timestamp_utc="2026-10-09T10:00:00+00:00",
                provider="openai",
                action="summary",
                run_id="publish-budget-run",
                task_id="report-1",
                span_id="summary-span",
                trace_id="publish-budget-trace",
                model="gpt-6-luna",
                request_id="request-1",
                publisher_name="Publisher",
                report_name="Report",
                source_url="https://example.test/report",
                input_tokens=3,
                output_tokens=4,
                total_tokens=7,
                cached_input_tokens=0,
                tool_calls=0,
                estimated_cost_usd=0.12,
                prompt_namespace="report_vs/artifacts/summary",
                prompt_hash="prompt-hash",
                provider_decision="openai_direct",
                cache_decision="miss",
                temperature=0.0,
                seed=None,
                timeout_seconds=30.0,
                pricing_status="matched",
            ),
        ),
        _ctx(),
    )

    usage = read_publish_budget_usage(budget, _ctx())

    assert usage is not None
    assert usage.tokens == 7
    assert ledger_path.is_file()
    assert daily_path.is_file()


def test_publish_budget_blocks_release_when_configured_projection_evidence_is_missing(
    tmp_path,
) -> None:
    settings = PublishSettings(
        schema_version="1.0",
        output_dir=str(tmp_path / "out"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path=str(tmp_path / "categories.yaml"),
        wp=WordPressAuthSettings(
            schema_version="1.0",
            site_url="http://wordpress.local",
            username="operator",
            app_password="secret",
            bearer_token=None,
            post_status="publish",
        ),
        run_budget_enabled=True,
        usage_db_path=str(tmp_path / "llm_usage.sqlite"),
        projection_ledger_path=str(tmp_path / "cost-ledger.jsonl"),
        projection_daily_path=str(tmp_path / "cost-daily.json"),
    )
    budget = build_publish_budget(settings, _ctx())

    with pytest.raises(AppError) as exc_info:
        read_publish_budget_usage(budget, _ctx())

    assert exc_info.value.code == "publish_budget_projection_not_release_ready"
    assert exc_info.value.retryable is False


def test_explicit_no_write_publish_with_no_candidates_does_not_require_auth(
    tmp_path,
) -> None:
    settings = PublishSettings(
        schema_version="1.0",
        output_dir=str(tmp_path / "out"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path=str(tmp_path / "categories.yaml"),
        wp=WordPressAuthSettings(
            schema_version="1.0",
            site_url="",
            username="",
            app_password=None,
            bearer_token=None,
            post_status="publish",
        ),
        run_budget_enabled=True,
        run_budget_max_wordpress_writes=0,
    )

    html_path = tmp_path / "candidate.html"
    html_path.write_text("<html><body>Candidate</body></html>", encoding="utf-8")

    outcomes = run_publish(settings, html_paths=[str(html_path)], ctx=_ctx())

    assert len(outcomes) == 1
    assert outcomes[0].status == "skipped"
    assert outcomes[0].error == "wordpress_write_budget_zero"
    assert outcomes[0].actual_write_count == 0
