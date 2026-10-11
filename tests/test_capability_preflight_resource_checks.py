from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.llm import OpenAIModelPreflightResponse
from src.contracts.pipeline_preflight import CapabilityPreflightRequest
from src.contracts.files import ExecutableAvailabilityResponse
from src.contracts.sqlite_migration import SqliteCapabilityInspectionResponse
from src.orchestrators.pipeline_preflight_orchestrator import (
    run_capability_preflight,
)
from tests.test_capability_preflight_orchestrator import (
    _control,
    _ctx,
    _dependencies,
    _queues,
    _settings,
)


@pytest.mark.parametrize(
    ("version", "executable", "expected"),
    [((3, 11), "python", False), ((3, 12), "python", True), ((3, 13), "", False)],
)
def test_python_runtime_support_matches_project_minimum(
    version: tuple[int, int], executable: str, expected: bool
) -> None:
    from src.orchestrators.pipeline_preflight_orchestrator import (
        _python_runtime_supported,
    )

    assert _python_runtime_supported(version, executable) is expected


def test_manual_llm_workflow_checks_the_usage_ledger(tmp_path: Path) -> None:
    calls = []
    settings = _settings(tmp_path)
    dependencies = _dependencies(
        sqlite_check=lambda request, _ctx: (
            calls.append((request.database_key, request.db_path))
            or SqliteCapabilityInspectionResponse(
                schema_version="1.0",
                database_key=request.database_key,
                status="ready",
                reason_code="sqlite_capability_ready",
                retryable=False,
                current_version=1,
                expected_version=1,
                integrity_ok=True,
                foreign_keys_ok=True,
                write_lock_available=True,
            )
        )
    )

    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="manual",
            settings=settings,
            workflow_control=_control("manual"),
            queue_policies=_queues(),
            live_checks=False,
        ),
        _ctx(),
        dependencies=dependencies,
    )

    usage_ledger = next(
        check for check in report.checks if check.capability == "llm_usage_db"
    )
    assert usage_ledger.status == "ready"
    assert usage_ledger.affected_workflows == ["report_generation"]
    assert ("llm_usage_db", settings.usage_db_path) in calls


def test_signal_workflows_inspect_the_signal_store_only_when_enabled(
    tmp_path: Path,
) -> None:
    calls = []
    settings = _settings(tmp_path)
    dependencies = _dependencies(
        sqlite_check=lambda request, _ctx: (
            calls.append((request.database_key, request.db_path))
            or SqliteCapabilityInspectionResponse(
                schema_version="1.0",
                database_key=request.database_key,
                status="ready",
                reason_code="sqlite_capability_ready",
                retryable=False,
                current_version=1,
                expected_version=1,
                integrity_ok=True,
                foreign_keys_ok=True,
                write_lock_available=True,
            )
        )
    )
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=settings,
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues("signal_candidate"),
            live_checks=False,
        ),
        _ctx(),
        dependencies=dependencies,
    )

    signal_store = next(
        check for check in report.checks if check.capability == "signal_store_db"
    )
    assert signal_store.status == "ready"
    assert signal_store.affected_workflows == ["signal_candidate"]
    assert ("reports_db", settings.signal_store_db) in calls

    inspected_signal_store_count = calls.count(("reports_db", settings.signal_store_db))
    unrelated_settings = _settings(tmp_path / "unrelated")
    unrelated = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=unrelated_settings,
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues("cost_reconciliation"),
            live_checks=False,
        ),
        _ctx(),
        dependencies=dependencies,
    )
    assert (
        calls.count(("reports_db", settings.signal_store_db))
        == inspected_signal_store_count
    )
    assert ("reports_db", unrelated_settings.signal_store_db) not in calls
    assert not [
        check for check in unrelated.checks if check.capability == "signal_store_db"
    ]


def test_signal_store_preflight_uses_runtime_reports_db_fallback(
    tmp_path: Path,
) -> None:
    calls = []
    settings = replace(_settings(tmp_path), signal_store_db="")
    dependencies = _dependencies(
        sqlite_check=lambda request, _ctx: (
            calls.append((request.database_key, request.db_path))
            or SqliteCapabilityInspectionResponse(
                schema_version="1.0",
                database_key=request.database_key,
                status="ready",
                reason_code="sqlite_capability_ready",
                retryable=False,
                current_version=1,
                expected_version=1,
                integrity_ok=True,
                foreign_keys_ok=True,
                write_lock_available=True,
            )
        )
    )

    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=settings,
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues("signal_candidate"),
            live_checks=False,
        ),
        _ctx(),
        dependencies=dependencies,
    )

    signal_store = next(
        check for check in report.checks if check.capability == "signal_store_db"
    )
    assert signal_store.status == "ready"
    assert ("reports_db", settings.reports_db) in calls


def test_ocr_preflight_does_not_require_tesseract(tmp_path: Path) -> None:
    executable_names = []
    settings = replace(_settings(tmp_path), pdf_text_ocr_enabled=True)
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="manual",
            settings=settings,
            workflow_control=_control("manual"),
            queue_policies=_queues(),
            live_checks=False,
        ),
        _ctx(),
        dependencies=_dependencies(
            executable_check=lambda request, _ctx: (
                executable_names.append(request.executable_name)
                or ExecutableAvailabilityResponse(
                    schema_version="1.0",
                    executable_name=request.executable_name,
                    available=False,
                )
            )
        ),
    )

    ocr = next(check for check in report.checks if check.capability == "ocr_executable")
    assert ocr.status == "not_required"
    assert ocr.required is False
    assert "tesseract" not in executable_names


def test_enabled_ocr_workflow_checks_its_configured_openai_model(
    tmp_path: Path,
) -> None:
    model_requests = []
    prompt_namespaces = []
    settings = replace(_settings(tmp_path), pdf_text_ocr_enabled=True)

    def model_check(request, _ctx):
        model_requests.append(request)
        return OpenAIModelPreflightResponse(
            schema_version="1.0",
            model=request.model,
            accessible=True,
            provider_calls=1,
        )

    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=settings,
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues("source_ingest"),
            live_checks=True,
        ),
        _ctx(),
        dependencies=_dependencies(
            model_check=model_check,
            prompt_check=lambda request, _ctx: (
                prompt_namespaces.append(request.namespace) or object()
            ),
        ),
    )

    ocr_model = next(
        check for check in report.checks if check.capability == "ocr_model"
    )
    assert ocr_model.status == "ready"
    assert ocr_model.affected_workflows == ["source_ingest"]
    assert len(model_requests) == 1
    assert model_requests[0].model == settings.pdf_text_ocr_model
    assert settings.pdf_text_ocr_prompt_namespace in prompt_namespaces
    assert report.provider_calls == 1
    openai_dependencies = next(
        check for check in report.checks if check.capability == "openai_dependencies"
    )
    assert openai_dependencies.affected_workflows == ["source_ingest"]


def test_enabled_ocr_workflow_requires_a_live_model_probe(tmp_path: Path) -> None:
    settings = replace(_settings(tmp_path), pdf_text_ocr_enabled=True)
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=settings,
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues("source_ingest"),
            live_checks=False,
        ),
        _ctx(),
        dependencies=_dependencies(),
    )

    ocr_model = next(
        check for check in report.checks if check.capability == "ocr_model"
    )
    assert ocr_model.status == "not_checked"
    assert ocr_model.required is True
    assert ocr_model.reason_code == "openai_model_live_probe_skipped"
