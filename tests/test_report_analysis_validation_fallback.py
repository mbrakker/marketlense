from __future__ import annotations

import logging
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.contracts.report_analysis import AnalysisPackPathResponse
from src.contracts.run_context import RunContext
from src.contracts.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationRequest,
)
from src.contracts.workflow_queue import (
    ReportAnalysisPayload,
    ReportAnalysisResult,
    WorkflowJobSubmission,
)
from src.generators.report_generation_dependencies import ReportAnalysisDependencies
from src.generators.validation_generator import validate_report
from src.orchestrators._report_analysis_orchestrator.validation import (
    _run_validation_with_fallback,
)
from src.orchestrators.workflow_queue_orchestrator import (
    WorkflowQueueHandlerRegistration,
    WorkflowQueueHandlerResult,
)
from src.orchestrators.workflow_worker_orchestrator import run_workflow_worker_once
from src.services.workflow_queue_service import (
    enqueue_workflow_job,
    get_workflow_job,
    list_workflow_job_attempts,
)
from src.utils.errors import AppError
from src.utils.logging import new_run_context
from tests._test_validation_generator._shared import (
    FakeAnalysisStore,
    FakeOpenAI,
    FakePromptClient,
)
from tests._test_validation_generator._shared import (
    _report as _semantic_report,
)
from tests._test_validation_generator._shared import (
    _settings as _semantic_settings,
)


def _fallback_inputs(validate):
    stored = []
    runtime = SimpleNamespace(
        file=SimpleNamespace(file_id="report-1"),
        settings=SimpleNamespace(output_dir="output"),
        analysis_mode="full",
        report_name="report-1",
        md5="content-hash",
    )
    dependencies = replace(
        ReportAnalysisDependencies.default(),
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
    assert result.issues[0].rule_id == "validation_execution"
    assert result.issues[0].violation_type == "openai_bad_request"
    assert "OpenAI request was rejected permanently" not in result.issues[0].message


def test_validation_propagates_retryable_failure_after_one_owned_retry():
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
    with pytest.raises(AppError) as raised:
        _run_validation_with_fallback(
            runtime=runtime,
            mode_ctx=RunContext("1.0", "run-1", "task-1", "span-1"),
            dependencies=dependencies,
            validation_req=SimpleNamespace(),
            pack_name="validation",
        )

    assert calls == 2
    assert raised.value.code == "openai_chat_failed"
    assert raised.value.retryable is True
    assert stored == []


def test_validation_retry_logs_exclude_error_message_and_context(caplog):
    marker = "untrusted-debug-payload"

    def validate(*_args, **_kwargs):
        raise AppError(
            code="openai_chat_failed",
            message=marker,
            retryable=True,
            context={"retry_decision": "defer", "next_action": marker},
        )

    runtime, dependencies, _stored = _fallback_inputs(validate)
    with caplog.at_level(logging.INFO), pytest.raises(AppError):
        _run_validation_with_fallback(
            runtime=runtime,
            mode_ctx=RunContext("1.0", "run-1", "task-1", "span-1"),
            dependencies=dependencies,
            validation_req=SimpleNamespace(),
            pack_name="validation",
        )

    assert marker not in caplog.text


def test_completed_unsupported_validation_remains_a_content_failure():
    completed = ValidationReport(
        schema_version="1.1",
        status="fail",
        issues=[
            ValidationIssue(
                schema_version="1.0",
                rule_id="grounding",
                violation_type="unsupported_factual_claim",
                message="Claim is unsupported.",
                severity="error",
                affected_section="summary",
            )
        ],
        severity="error",
    )
    calls = 0

    def validate(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return completed

    runtime, dependencies, stored = _fallback_inputs(validate)
    result = _run_validation_with_fallback(
        runtime=runtime,
        mode_ctx=RunContext("1.0", "run-1", "task-1", "span-1"),
        dependencies=dependencies,
        validation_req=SimpleNamespace(),
        pack_name="validation",
    )

    assert result is completed
    assert calls == 1
    assert stored == []


def test_unexpected_validation_exception_is_fail_closed_and_redacted(caplog):
    marker = "untrusted-debug-payload"

    def validate(*_args, **_kwargs):
        raise RuntimeError(marker)

    runtime, dependencies, stored = _fallback_inputs(validate)
    with caplog.at_level(logging.INFO):
        result = _run_validation_with_fallback(
            runtime=runtime,
            mode_ctx=RunContext("1.0", "run-1", "task-1", "span-1"),
            dependencies=dependencies,
            validation_req=SimpleNamespace(),
            pack_name="validation",
        )

    assert result.status == "fail"
    assert result.issues[0].rule_id == "validation_execution"
    assert result.issues[0].violation_type == "validation_unexpected_error"
    assert marker not in result.issues[0].message
    assert marker not in caplog.text
    assert len(stored) == 1


def _queue_validation_replay(
    tmp_path,
    *,
    max_attempts: int,
    always_fail: bool,
    validation_runner=None,
    validation_req=None,
):
    calls = 0
    marker = "untrusted-provider-detail"

    def validate(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if validation_runner is not None:
            return validation_runner(*_args, **_kwargs)
        if always_fail or calls <= 2:
            raise AppError(
                code="semantic_provider_timeout",
                message=marker,
                retryable=True,
                cause=TimeoutError(marker),
            )
        return ValidationReport(schema_version="1.1", status="pass")

    runtime, dependencies, stored = _fallback_inputs(validate)

    def handle(_job, _payload, ctx):
        report = _run_validation_with_fallback(
            runtime=runtime,
            mode_ctx=ctx,
            dependencies=dependencies,
            validation_req=(
                validation_req if validation_req is not None else SimpleNamespace()
            ),
            pack_name="validation",
        )
        return WorkflowQueueHandlerResult(
            result=ReportAnalysisResult(
                output_reference="retained:analysis/report-1",
                output_content_hash="analysis-hash",
                output_verified=True,
                summary={"validation_status": report.status},
            )
        )

    registration = WorkflowQueueHandlerRegistration(
        queue_name="report_analysis",
        job_type="report_analysis.v1",
        payload_type=ReportAnalysisPayload,
        result_type=ReportAnalysisResult,
        handler=handle,
        default_retry_policy="workflow_queue.default.v1",
        default_lease_seconds=900,
        budget_profile="report_analysis",
        expected_external_effects=(),
        allowed_downstream_job_types=(),
    )
    ctx = new_run_context(task_id="validation-retry-queue-replay")
    state_db = str(tmp_path / "workflow.sqlite")
    job, _ = enqueue_workflow_job(
        state_db,
        WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="report_analysis",
            job_type="report_analysis.v1",
            payload=ReportAnalysisPayload(
                report_id="report-1",
                input_reference="retained:selection/report-1",
                input_content_hash="selection-hash",
                processing_version="report_analysis.v1",
            ),
            idempotency_key=f"validation-replay:{max_attempts}:{always_fail}",
            deduplication_scope="validation-retry-test",
            entity_type="report",
            entity_id="report-1",
            report_id="report-1",
            available_at_utc="2026-08-01T00:00:00+00:00",
            max_attempts=max_attempts,
        ),
        ctx,
        now_utc="2026-08-01T00:00:00+00:00",
    )
    registry = {("report_analysis", "report_analysis.v1"): registration}

    def run_worker(now_utc: str):
        return run_workflow_worker_once(
            state_db=state_db,
            queue_name="report_analysis",
            worker_id="validation-worker",
            ctx=ctx,
            registry=registry,
            now_utc=now_utc,
        )

    return state_db, job, lambda: calls, stored, marker, run_worker


class _SemanticFailureOpenAI(FakeOpenAI):
    def __init__(
        self,
        *,
        failure_count: int | None,
        retryable: bool,
        semantic_payload: dict | None = None,
    ):
        super().__init__(
            semantic_payload=semantic_payload
            or {
                "metrics": [
                    {
                        "id": "metric-1",
                        "supported": True,
                        "confidence": 0.9,
                        "reason": "Supported by source evidence.",
                    }
                ],
                "quotes": [],
            },
            grounding_payload={"unsupported": []},
        )
        self.failure_count = failure_count
        self.retryable = retryable
        self.semantic_calls = 0
        self.raw_message = "raw-semantic-provider-detail-9f31"
        self.raw_context = "raw-semantic-provider-context-6a72"

    def openai_chat_json(self, req, ctx):
        if str(getattr(ctx, "task_id", "")).endswith(":semantic"):
            self.semantic_calls += 1
            if self.failure_count is None or self.semantic_calls <= self.failure_count:
                raise AppError(
                    code=(
                        "semantic_provider_timeout"
                        if self.retryable
                        else "semantic_provider_rejected"
                    ),
                    message=self.raw_message,
                    retryable=self.retryable,
                    context={"provider_response": self.raw_context},
                    cause=RuntimeError(self.raw_context),
                )
        return super().openai_chat_json(req, ctx)


def _semantic_validation_request():
    return ValidationRequest(
        schema_version="1.0",
        report_id="report-1",
        report=_semantic_report(),
        artifacts={
            "insights_final": [
                {
                    "id": "metric-1",
                    "text": "Revenue reached 10%.",
                    "evidence_id": "e1",
                    "evidence": "Revenue reached 10%.",
                    "metric": {"value": "10%", "unit": "%", "timeframe": "2025"},
                }
            ]
        },
        evidence_packs={
            "findings": {"findings": [{"id": "e1", "evidence": "Revenue reached 10%."}]}
        },
        vector_store_id=None,
    )


def _real_semantic_validation_runner(tmp_path, openai_client):
    settings = _semantic_settings(tmp_path)

    def validate(request, _settings, ctx, **kwargs):
        return validate_report(
            request,
            settings,
            ctx,
            prompt_client=FakePromptClient(),
            openai_client=openai_client,
            analysis_store=FakeAnalysisStore(),
            **kwargs,
        )

    return validate


def test_real_semantic_provider_retry_reaches_queue_then_succeeds(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    client = _SemanticFailureOpenAI(failure_count=2, retryable=True)
    state_db, job, calls, stored, _marker, run_worker = _queue_validation_replay(
        tmp_path,
        max_attempts=3,
        always_fail=False,
        validation_runner=_real_semantic_validation_runner(tmp_path, client),
        validation_req=_semantic_validation_request(),
    )

    first = run_worker("2026-08-01T00:00:01+00:00")
    pending = get_workflow_job(state_db, job.job_id, new_run_context())
    second = run_worker("2026-08-01T00:02:00+00:00")
    completed = get_workflow_job(state_db, job.job_id, new_run_context())

    assert first.terminal_status == "retry_wait"
    assert pending.error_code == "semantic_provider_timeout"
    assert second.terminal_status == "succeeded"
    assert completed.status == "succeeded"
    assert calls() == 3
    assert client.semantic_calls == 3
    assert stored == []
    assert client.raw_message not in caplog.text
    assert client.raw_context not in caplog.text


def test_real_semantic_provider_retry_exhaustion_dead_letters(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    client = _SemanticFailureOpenAI(failure_count=None, retryable=True)
    state_db, job, calls, stored, _marker, run_worker = _queue_validation_replay(
        tmp_path,
        max_attempts=2,
        always_fail=False,
        validation_runner=_real_semantic_validation_runner(tmp_path, client),
        validation_req=_semantic_validation_request(),
    )

    first = run_worker("2026-08-01T00:00:01+00:00")
    second = run_worker("2026-08-01T00:02:00+00:00")
    terminal = get_workflow_job(state_db, job.job_id, new_run_context())

    assert first.terminal_status == "retry_wait"
    assert second.terminal_status == "dead_letter"
    assert terminal.error_code == "semantic_provider_timeout"
    assert calls() == 4
    assert client.semantic_calls == 4
    assert stored == []
    assert client.raw_message not in caplog.text
    assert client.raw_context not in caplog.text


def test_real_semantic_nonretryable_failure_is_redacted_and_fail_closed(
    tmp_path, caplog
):
    caplog.set_level(logging.INFO)
    client = _SemanticFailureOpenAI(failure_count=None, retryable=False)
    runtime, dependencies, stored = _fallback_inputs(
        _real_semantic_validation_runner(tmp_path, client)
    )
    result = _run_validation_with_fallback(
        runtime=runtime,
        mode_ctx=RunContext("1.0", "run-1", "task-1", "span-1"),
        dependencies=dependencies,
        validation_req=_semantic_validation_request(),
        pack_name="validation",
    )

    assert result.status == "fail"
    assert result.issues[0].rule_id == "validation_execution"
    assert result.issues[0].violation_type == "semantic_provider_rejected"
    assert client.semantic_calls == 1
    assert stored
    assert client.raw_message not in repr(result.to_dict())
    assert client.raw_context not in repr(result.to_dict())
    assert client.raw_message not in repr(stored[0].payload)
    assert client.raw_context not in repr(stored[0].payload)
    assert client.raw_message not in caplog.text
    assert client.raw_context not in caplog.text


def test_real_semantic_incomplete_verdict_remains_content_validation_failure(tmp_path):
    client = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    runtime, dependencies, stored = _fallback_inputs(
        _real_semantic_validation_runner(tmp_path, client)
    )
    result = _run_validation_with_fallback(
        runtime=runtime,
        mode_ctx=RunContext("1.0", "run-1", "task-1", "span-1"),
        dependencies=dependencies,
        validation_req=_semantic_validation_request(),
        pack_name="validation",
    )

    assert result.status == "fail"
    assert any(
        issue.violation_type == "semantic_verdicts_incomplete"
        and issue.severity == "error"
        for issue in result.issues
    )
    assert not any(issue.rule_id == "validation_execution" for issue in result.issues)
    assert stored == []


def test_report_analysis_queue_retries_transient_validation_then_succeeds(tmp_path):
    state_db, job, calls, stored, marker, run_worker = _queue_validation_replay(
        tmp_path, max_attempts=3, always_fail=False
    )

    first = run_worker("2026-08-01T00:00:01+00:00")
    pending = get_workflow_job(state_db, job.job_id, new_run_context())
    second = run_worker("2026-08-01T00:02:00+00:00")
    completed = get_workflow_job(state_db, job.job_id, new_run_context())
    attempts = list_workflow_job_attempts(state_db, job.job_id, new_run_context())

    assert first.terminal_status == "retry_wait"
    assert pending.error_code == "semantic_provider_timeout"
    assert second.terminal_status == "succeeded"
    assert completed.status == "succeeded"
    assert [attempt.outcome for attempt in attempts] == ["retry_wait", "succeeded"]
    assert calls() == 3
    assert stored == []
    assert marker not in completed.error_message_summary


def test_report_analysis_queue_exhausts_transient_validation_without_requeue(tmp_path):
    state_db, job, calls, stored, marker, run_worker = _queue_validation_replay(
        tmp_path, max_attempts=2, always_fail=True
    )

    first = run_worker("2026-08-01T00:00:01+00:00")
    second = run_worker("2026-08-01T00:02:00+00:00")
    terminal = get_workflow_job(state_db, job.job_id, new_run_context())
    attempts = list_workflow_job_attempts(state_db, job.job_id, new_run_context())

    assert first.terminal_status == "retry_wait"
    assert second.terminal_status == "dead_letter"
    assert terminal.error_code == "semantic_provider_timeout"
    assert terminal.terminal_reason == "semantic_provider_timeout"
    assert [attempt.outcome for attempt in attempts] == ["retry_wait", "dead_letter"]
    assert calls() == 4
    assert stored == []
    assert marker not in terminal.error_message_summary
