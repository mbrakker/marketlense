from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.contracts.browser_download import BrowserReportDownloadRequest
from src.contracts.run_budget import RunBudget
from src.contracts.run_context import RunContext
from tests.test_browser_report_download_service.builders import _settings


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_form_value_derivation_uses_the_acquisition_ledger_and_budget(
    tmp_path: Path, external_boundary_mocks_only
) -> None:
    """A form derivation must account to its acquisition, not provider defaults."""
    from src.services import llm_service
    from src.services._browser_report_download import browser as browser_runtime
    from src.utils.errors import AppError

    captured_request: list[object] = []

    def unavailable_model(prompt_request, *_args, **_kwargs):
        captured_request.append(prompt_request)
        raise AppError(
            code="openai_chat_failed",
            message="provider unavailable",
            retryable=True,
        )

    external_boundary_mocks_only.setattr(
        llm_service, "openai_chat_json", unavailable_model
    )
    settings = _settings(tmp_path)
    ctx = _ctx()
    budget = RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name="Example Publisher",
        usage_db_path=settings.usage_db_path,
    )
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/gated-report",
        settings=settings,
        route_family_hint="browser_email_form",
        publisher_name="Example Publisher",
        run_budget=budget,
    )

    assert (
        browser_runtime._derive_grounded_form_option(
            request=request,
            helper_result=SimpleNamespace(
                unresolved_options={"Industry": ("Technology",)}
            ),
            ctx=ctx,
        )
        is None
    )
    prompt_request = captured_request[0]
    assert prompt_request.usage_db_path == settings.usage_db_path
    assert prompt_request.cost_ledger_path == settings.cost_ledger_path
    assert prompt_request.cost_daily_path == settings.cost_daily_path
    assert prompt_request.run_budget == budget
