from __future__ import annotations

import pytest

from src.contracts.publish import PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.wordpress import WordPressAuthSettings
from src.orchestrators._publish_orchestrator.budget import (
    build_publish_budget,
    read_publish_budget_usage,
    record_publish_budget_write,
)
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
