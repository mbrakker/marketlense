"""Evaluator-only behavioral check for ML-PERF-001.

The test drives the pre-existing public download orchestrator and does not
import a historical cache implementation or state-cache contract.
"""

from __future__ import annotations

from pathlib import Path

from src.contracts.run_context import RunContext
from tests._test_report_download_orchestrator._shared import (
    FileHashResponse,
    ReportDownloadDependencies,
    ReportDownloadOrchestratorRequest,
    ReportSourceRecordResponse,
    _md5_for_path,
    _result,
    _settings,
    get_publisher_download_route,
    record_publisher_download_route,
    run_report_download,
)


def _dependencies(*, download_calls: list[object]) -> ReportDownloadDependencies:
    def _download(request, _ctx):
        download_calls.append(request)
        path = Path(request.settings.output_dir) / "report.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.7 verified artifact")
        return _result(url=request.url, used_route_hint=False, path=str(path))

    return ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=get_publisher_download_route,
        record_publisher_download_route=record_publisher_download_route,
        file_md5=lambda request, _ctx: FileHashResponse(
            schema_version="1.0",
            path=request.path,
            md5=_md5_for_path(Path(request.path)),
        ),
        record_report_source=lambda request, _ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=request.source_domain,
            report_name=request.report_name,
            landing_page_url=request.landing_page_url,
            downloaded_at_utc=request.downloaded_at_utc,
            md5=request.md5,
        ),
        upsert_browser_download_identity_fields=lambda request, _ctx: type(
            "IdentityUpdate",
            (),
            {"path": "", "added_field_keys": [], "total_fields": 0},
        )(),
        record_report_value_score=lambda *_args: None,
        sleep_fn=lambda _seconds: None,
    )


def _request(tmp_path: Path) -> ReportDownloadOrchestratorRequest:
    settings = _settings(tmp_path)
    return ReportDownloadOrchestratorRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=settings,
        state_db=settings.state_db,
        reports_db=settings.reports_db,
    )


def _context() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="benchmark-run",
        task_id="artifact-reuse",
        span_id="behavioral-check",
    )


def test_verified_unchanged_artifact_is_reused_idempotently(tmp_path: Path) -> None:
    calls: list[object] = []
    request = _request(tmp_path)
    dependencies = _dependencies(download_calls=calls)

    first = run_report_download(request, ctx=_context(), dependencies=dependencies)
    second = run_report_download(request, ctx=_context(), dependencies=dependencies)

    assert len(calls) == 1
    assert first.outcome == second.outcome == "downloaded"
    assert second.terminal_evidence.artifact_validation_status == "verified"


def test_changed_artifact_identity_reacquires_instead_of_reusing(tmp_path: Path) -> None:
    calls: list[object] = []
    request = _request(tmp_path)
    dependencies = _dependencies(download_calls=calls)

    first = run_report_download(request, ctx=_context(), dependencies=dependencies)
    Path(first.downloaded_file_path).write_bytes(b"%PDF-1.7 mismatched content")
    second = run_report_download(request, ctx=_context(), dependencies=dependencies)

    assert len(calls) == 2
    assert second.outcome == "downloaded"
    assert second.terminal_evidence.artifact_validation_status == "verified"


def test_cache_miss_is_a_successful_acquisition_not_a_failed_one(tmp_path: Path) -> None:
    calls: list[object] = []

    result = run_report_download(
        _request(tmp_path), ctx=_context(), dependencies=_dependencies(download_calls=calls)
    )

    assert len(calls) == 1
    assert result.outcome == "downloaded"
    assert result.terminal_evidence.artifact_validation_status == "verified"
