from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from src.contracts.browser_download import (
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
    BrowserDownloadSettings,
    BrowserReportDownloadResult,
    ReportDownloadOrchestratorRequest,
)
from src.contracts.files import FileHashResponse
from src.contracts.report_store import ReportSourceRecordResponse
from src.contracts.state import StateReportDownloadRouteResponse
from src.orchestrators.report_download_orchestrator import (
    ReportDownloadDependencies,
    run_report_download,
)
from src.services.state_service import (
    get_report_download_route,
    record_report_download_route,
)
from src.utils.errors import AppError


def _settings(tmp_path: Path) -> BrowserDownloadSettings:
    return BrowserDownloadSettings(
        schema_version="1.0",
        openrouter_api_key="openrouter-key",
        model="openai/gpt-5-mini",
        temperature=0.0,
        timeout_seconds=30.0,
        max_steps=5,
        output_dir=str(tmp_path / "downloads"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        identity_config_path=str(tmp_path / "browser_download_identity.yaml"),
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="work_email",
                    label="Work email",
                    value="ops@example.com",
                    aliases=["email"],
                )
            ],
        ),
        openrouter_http_referer="https://marketlense.local",
        headed=False,
        retry_retries=1,
        retry_base_delay_seconds=0.1,
        retry_backoff_step_seconds=0.0,
        retry_jitter_seconds=0.0,
    )


def _result(
    *, url: str, used_route_hint: bool, path: str | None
) -> BrowserReportDownloadResult:
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=url,
        normalized_url=url,
        route_kind="pdf_download" if path else "email_delivery",
        outcome="downloaded" if path else "email_required",
        route_summary="Click the report CTA and wait for completion.",
        final_page_url=f"{url}/final",
        used_route_hint=used_route_hint,
        encountered_form_fields=["Name", "Business"] if not path else [],
        downloaded_file_path=path,
        downloaded_file_name=Path(path).name if path else None,
        downloaded_mime_type="application/pdf" if path else None,
        downloaded_size_bytes=128 if path else None,
    )


def _events(caplog, logger_name: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != logger_name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def test_run_report_download_uses_memory_and_records_route(
    tmp_path: Path,
    caplog,
    run_context,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    settings = _settings(tmp_path)
    saved_records = []
    saved_sources = []

    def _download(req, ctx):
        assert req.route_hint == "Use the first Download report button."
        return _result(
            url="https://example.com/report",
            used_route_hint=True,
            path=str(Path(settings.output_dir) / "report.pdf"),
        )

    def _get_route(req, ctx):
        return StateReportDownloadRouteResponse(
            schema_version="1.0",
            normalized_url=req.normalized_url,
            source_url="https://example.com/report",
            route_kind="pdf_download",
            route_summary="Use the first Download report button.",
            outcome="downloaded",
            updated_at=1,
            last_downloaded_file_path=str(Path(settings.output_dir) / "report.pdf"),
            last_final_page_url="https://example.com/report/final",
        )

    def _record_route(req, ctx):
        saved_records.append(req)

    def _file_md5(req, ctx):
        return FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="abc123",
        )

    def _record_source(req, ctx):
        saved_sources.append(req)
        return ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        )

    def _upsert_identity(req, ctx):
        return type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )()

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_report_download_route=_get_route,
        record_report_download_route=_record_route,
        file_md5=_file_md5,
        record_report_source=_record_source,
        upsert_browser_download_identity_fields=_upsert_identity,
        sleep_fn=lambda seconds: None,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.used_memory_route is True
    assert response.outcome == "downloaded"
    assert len(saved_records) == 1
    assert len(saved_sources) == 1
    assert saved_records[0].normalized_url == "https://example.com/report"
    assert saved_sources[0].source_domain == "example.com"
    assert saved_sources[0].report_name == "report"
    assert saved_sources[0].landing_page_url == "https://example.com/report"
    assert saved_sources[0].md5 == "abc123"
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(
        _events(caplog, "market_lense.report_download_orchestrator")
    )


def test_run_report_download_falls_back_after_memory_failure_and_retries(
    tmp_path: Path,
    caplog,
    run_context,
    assert_logs_have_required_fields,
) -> None:
    settings = _settings(tmp_path)
    attempts = {"memory": 0, "discovery": 0}
    sleep_calls: list[float] = []
    saved_records = []
    identity_updates = []
    saved_sources = []

    def _download(req, ctx):
        if req.route_hint:
            attempts["memory"] += 1
            raise AppError(
                code="browser_download_agent_failed",
                message="stored route stale",
                retryable=True,
            )
        attempts["discovery"] += 1
        if attempts["discovery"] == 1:
            raise AppError(
                code="browser_download_agent_failed",
                message="transient browser error",
                retryable=True,
            )
        return _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=str(Path(settings.output_dir) / "report.pdf"),
        )

    def _get_route(req, ctx):
        return StateReportDownloadRouteResponse(
            schema_version="1.0",
            normalized_url=req.normalized_url,
            source_url="https://example.com/report",
            route_kind="pdf_download",
            route_summary="Use the first Download report button.",
            outcome="downloaded",
            updated_at=1,
            last_downloaded_file_path=None,
            last_final_page_url=None,
        )

    def _record_route(req, ctx):
        saved_records.append(req)

    def _file_md5(req, ctx):
        return FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="def456",
        )

    def _record_source(req, ctx):
        saved_sources.append(req)
        return ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=2,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        )

    def _upsert_identity(req, ctx):
        identity_updates.append(req)
        return type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": ["name", "business"],
                "total_fields": len(settings.identity_profile.fields) + 2,
            },
        )()

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_report_download_route=_get_route,
        record_report_download_route=_record_route,
        file_md5=_file_md5,
        record_report_source=_record_source,
        upsert_browser_download_identity_fields=_upsert_identity,
        sleep_fn=lambda seconds: sleep_calls.append(float(seconds)),
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert attempts["memory"] == 2
    assert attempts["discovery"] == 2
    assert sleep_calls == [0.1, 0.1]
    assert response.used_memory_route is False
    assert response.outcome == "downloaded"
    assert len(saved_records) == 1
    assert len(saved_sources) == 1
    assert identity_updates[0].encountered_form_fields == []
    assert_logs_have_required_fields(
        _events(caplog, "market_lense.report_download_orchestrator")
    )


def test_run_report_download_is_idempotent_for_route_memory(
    tmp_path: Path,
    run_context,
    idempotency_guard,
) -> None:
    settings = _settings(tmp_path)
    file_path = Path(settings.output_dir)
    file_path.mkdir(parents=True, exist_ok=True)
    pdf_path = file_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 idempotent")

    def _download(req, ctx):
        return _result(
            url="https://example.com/report",
            used_route_hint=bool(req.route_hint),
            path=str(pdf_path),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_report_download_route=get_report_download_route,
        record_report_download_route=record_report_download_route,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="idempotent-md5",
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        sleep_fn=lambda seconds: None,
    )

    def _run_once():
        return run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            ctx=run_context,
            dependencies=deps,
        )

    def _route_count() -> int:
        conn = sqlite3.connect(settings.state_db)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM report_download_routes WHERE normalized_url=?",
                ("https://example.com/report",),
            ).fetchone()
        finally:
            conn.close()
        return int(row[0] if row else 0)

    first, second = idempotency_guard(_run_once, side_effect_count=_route_count)
    assert first.outcome == "downloaded"
    assert second.outcome == "downloaded"


def test_run_report_download_does_not_record_source_for_email_outcome(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    source_record_calls: list[object] = []

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=None,
        ),
        get_report_download_route=lambda req, ctx: None,
        record_report_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="unused",
        ),
        record_report_source=lambda req, ctx: source_record_calls.append(req),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        sleep_fn=lambda seconds: None,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.outcome == "email_required"
    assert source_record_calls == []
