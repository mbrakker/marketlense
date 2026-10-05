from __future__ import annotations

from types import SimpleNamespace

from src.contracts.report_analysis import AnalysisPackPathResponse
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationReport
from src.orchestrators._report_analysis_orchestrator.validation import (
    _run_validation_with_fallback,
)
from src.utils.errors import AppError


def _fallback_inputs(validate):
    stored = []
    runtime = SimpleNamespace(
        file=SimpleNamespace(file_id="report-1"),
        settings=SimpleNamespace(output_dir="output"),
        analysis_mode="full",
        report_name="report-1",
        md5="content-hash",
    )
    dependencies = SimpleNamespace(
        run_validation=validate,
        analysis_pack_path=lambda _request, _ctx: AnalysisPackPathResponse(
            schema_version="1.0", output_path="validation.json"
        ),
        analysis_store_pack=lambda request, _ctx: stored.append(request),
    )
    return runtime, dependencies, stored


def test_validation_retries_one_retryable_provider_failure_then_returns_result():
    calls = 0

    def validate(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise AppError(
                code="openai_chat_failed",
                message="OpenAI chat request failed",
                retryable=True,
            )
        return ValidationReport(schema_version="1.1", status="pass")

    runtime, dependencies, stored = _fallback_inputs(validate)
    result = _run_validation_with_fallback(
        runtime=runtime,
        mode_ctx=RunContext("1.0", "run-1", "task-1", "span-1"),
        dependencies=dependencies,
        validation_req=SimpleNamespace(),
        pack_name="validation",
    )

    assert calls == 2
    assert result.status == "pass"
    assert stored == []


def test_validation_does_not_retry_non_retryable_provider_failure():
    calls = 0

    def validate(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AppError(
            code="openai_bad_request",
            message="OpenAI request was rejected permanently",
            retryable=False,
        )

    runtime, dependencies, stored = _fallback_inputs(validate)
    result = _run_validation_with_fallback(
        runtime=runtime,
        mode_ctx=RunContext("1.0", "run-1", "task-1", "span-1"),
        dependencies=dependencies,
        validation_req=SimpleNamespace(),
        pack_name="validation",
    )

    assert calls == 1
    assert result.status == "fail"
    assert len(stored) == 1


def test_validation_caps_retryable_provider_failure_at_one_retry():
    calls = 0

    def validate(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AppError(
            code="openai_chat_failed",
            message="OpenAI chat request failed",
            retryable=True,
        )

    runtime, dependencies, stored = _fallback_inputs(validate)
    result = _run_validation_with_fallback(
        runtime=runtime,
        mode_ctx=RunContext("1.0", "run-1", "task-1", "span-1"),
        dependencies=dependencies,
        validation_req=SimpleNamespace(),
        pack_name="validation",
    )

    assert calls == 2
    assert result.status == "fail"
    assert len(stored) == 1
