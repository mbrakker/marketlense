from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadIdentity,
    BrowserDownloadRouteStep,
    BrowserDownloadSettings,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
    DownloadTerminalEvidence,
)
from src.services import browser_report_download_service
from src.services._browser_report_download.playbooks import (
    load_browser_route_playbooks,
    promote_validated_browser_route_result_to_playbook,
)
from src.services._browser_report_download.prompt import (
    render_browser_report_download_prompt,
)
from src.utils.browser_route_playbooks import select_browser_route_playbooks
from src.utils.errors import AppError


def test_repo_browser_route_playbooks_load_and_select(run_context) -> None:
    playbook_dir = (
        Path(__file__).resolve().parents[1] / "src" / "playbooks" / "browser_routes"
    )

    playbooks = load_browser_route_playbooks(
        playbook_dir=str(playbook_dir),
        ctx=run_context,
    )
    selection = select_browser_route_playbooks(
        playbooks=playbooks,
        normalized_url="https://publisher.example/research/2026-report",
        route_family_hint="browser_pdf_click",
        now=datetime.fromisoformat("2026-05-06T12:00:00+00:00"),
    )

    assert len(playbooks) >= 3
    assert [item.playbook_id for item in selection.selected_playbooks] == [
        "generic-pdf-click"
    ]
    assert selection.selected_playbooks[0].version == "1.0.0"
    assert selection.fallback_to_discovery is False


def test_stale_playbook_fallback_and_fail_policies_are_logged(
    tmp_path: Path,
    run_context,
    caplog: pytest.LogCaptureFixture,
) -> None:
    playbook_dir = tmp_path / "playbooks"
    playbook_dir.mkdir()
    _write_playbook(
        playbook_dir / "old.yaml",
        playbook_id="old-pdf-click",
        updated_at="2020-01-01T00:00:00+00:00",
        stale_after_days=1,
    )
    caplog.set_level(logging.INFO, logger=browser_report_download_service.logger.name)

    fallback_request = browser_report_download_service.attach_browser_route_playbooks(
        request=_request(tmp_path, route_playbook_dir=str(playbook_dir)),
        ctx=run_context,
        normalized_url="https://example.com/research/report",
    )

    assert fallback_request.selected_playbooks == []
    events = _service_events(caplog)
    selection_events = [
        event
        for event in events
        if event["event"] == "browser_route_playbook_selection"
    ]
    assert selection_events
    assert selection_events[-1]["fields"]["stale_playbook_ids"] == ["old-pdf-click"]
    assert selection_events[-1]["fields"]["fallback_to_discovery"] is True

    with pytest.raises(AppError) as excinfo:
        browser_report_download_service.attach_browser_route_playbooks(
            request=_request(
                tmp_path,
                route_playbook_dir=str(playbook_dir),
                route_playbook_stale_policy="fail",
            ),
            ctx=run_context,
            normalized_url="https://example.com/research/report",
        )
    assert excinfo.value.code == "browser_route_playbook_stale"
    assert excinfo.value.retryable is False
    assert excinfo.value.context["stale_playbook_ids"] == ["old-pdf-click"]


def test_prompt_cites_selected_playbook_id_version_and_steps(
    tmp_path: Path,
    run_context,
) -> None:
    playbook_dir = tmp_path / "playbooks"
    playbook_dir.mkdir()
    _write_playbook(
        playbook_dir / "pdf.yaml",
        playbook_id="local-pdf-click",
        updated_at="2026-05-06T00:00:00+00:00",
    )
    request = browser_report_download_service.attach_browser_route_playbooks(
        request=_request(tmp_path, route_playbook_dir=str(playbook_dir)),
        ctx=run_context,
        normalized_url="https://example.com/research/report",
    )

    bundle = render_browser_report_download_prompt(
        request=request,
        ctx=run_context,
        normalized_url="https://example.com/research/report",
        execution_url="https://example.com/research/report",
        download_dir=tmp_path / "downloads",
        delivery_email=None,
    )

    assert (
        "Selected browser-route playbooks for this attempt:"
        in bundle.rendered_user_prompt
    )
    assert "local-pdf-click@1.0.0" in bundle.rendered_user_prompt
    assert (
        "click_cta: Download report -> verify local PDF" in bundle.rendered_user_prompt
    )


def test_validated_route_promotion_writes_reviewable_file_and_rejects_unverified(
    tmp_path: Path,
    run_context,
) -> None:
    result = _result(route_status="verified")

    response = promote_validated_browser_route_result_to_playbook(
        playbook_dir=str(tmp_path / "playbooks"),
        result=result,
        ctx=run_context,
        observed_at="2026-05-06T12:00:00+00:00",
    )
    payload = yaml.safe_load(Path(response.path).read_text(encoding="utf-8"))

    assert response.status == "created"
    assert response.playbook_id == "learned-example-com-browser-pdf-click"
    assert response.version == "1.0.0"
    assert (
        "--- learned-example-com-browser-pdf-click.yaml:before" in response.review_diff
    )
    assert payload["history"][0]["source"] == "validated_route_promotion"
    assert payload["source_evidence"] == ["downloaded_file_path"]
    assert payload["steps"][0]["verification"] == "opened"

    with pytest.raises(AppError) as excinfo:
        promote_validated_browser_route_result_to_playbook(
            playbook_dir=str(tmp_path / "playbooks"),
            result=_result(route_status="inferred"),
            ctx=run_context,
            observed_at="2026-05-06T12:00:00+00:00",
        )
    assert excinfo.value.code == "browser_route_playbook_promotion_unverified"
    assert excinfo.value.retryable is False


def _request(
    tmp_path: Path,
    *,
    route_playbook_dir: str,
    route_playbook_stale_policy: str = "fallback",
) -> BrowserReportDownloadRequest:
    return BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/research/report",
        settings=BrowserDownloadSettings(
            schema_version="1.0",
            openrouter_api_key="key",
            model="openai/gpt-5-mini",
            temperature=0.0,
            timeout_seconds=30.0,
            max_steps=5,
            output_dir=str(tmp_path / "downloads"),
            state_db=str(tmp_path / "state.sqlite"),
            reports_db=str(tmp_path / "reports.sqlite"),
            identity_config_path=str(tmp_path / "identity.yaml"),
            identity_profile=BrowserDownloadIdentity(
                schema_version="1.0",
                fields=[],
                delivery_emails=[],
            ),
            route_playbook_dir=route_playbook_dir,
            route_playbook_stale_policy=route_playbook_stale_policy,
        ),
        route_family_hint="browser_pdf_click",
    )


def _result(*, route_status: str) -> BrowserReportDownloadResult:
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url="https://example.com/research/report",
        normalized_url="https://example.com/research/report",
        route_kind="pdf_download",
        route_family="browser_pdf_click",
        route_status=route_status,
        outcome="downloaded",
        route_summary="Open the report page and use the Download report CTA.",
        final_page_url="https://example.com/research/report",
        resolved_target_url="https://example.com/report.pdf",
        used_route_hint=False,
        route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="click_cta",
                target_text="Download report",
                target_role="button",
                target_url="https://example.com/report.pdf",
                result="opened",
            )
        ],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=True,
            visible_confirmation_text="",
            submit_button_state="",
            form_disappeared=False,
            final_page_url="https://example.com/research/report",
            confirmation_score=1,
            signal_labels=["artifact"],
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url="https://example.com/research/report",
            final_page_title="Report",
            terminal_text_excerpt="Report",
            artifact_url="https://example.com/report.pdf",
            artifact_kind="pdf",
            artifact_validation_status="verified",
            artifact_validation_detail="local PDF",
            confirmation_signal_count=1,
            evidence_labels=["downloaded_file_path"],
        ),
        browser_had_structured_result=True,
        used_candidate_pdf_url=False,
        used_candidate_source_page=False,
        downloaded_file_path="C:/tmp/report.pdf",
        downloaded_file_name="report.pdf",
        downloaded_mime_type="application/pdf",
        downloaded_size_bytes=1234,
    )


def _write_playbook(
    path: Path,
    *,
    playbook_id: str,
    updated_at: str,
    stale_after_days: int = 120,
) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "playbook_id": playbook_id,
                "version": "1.0.0",
                "status": "active",
                "updated_at": updated_at,
                "stale_after_days": stale_after_days,
                "publisher_pattern": "Example",
                "host_patterns": ["example.com"],
                "url_path_markers": ["research", "report"],
                "route_family": "browser_pdf_click",
                "route_kind": "pdf_download",
                "summary": "Use the download CTA.",
                "steps": [
                    {
                        "schema_version": "1.0",
                        "action": "click_cta",
                        "target": "Download report",
                        "verification": "local PDF",
                    }
                ],
                "traps": ["Avoid unrelated navigation."],
                "evidence_notes": ["Seeded test evidence."],
                "source_evidence": ["test"],
                "history": [
                    {
                        "schema_version": "1.0",
                        "changed_at": updated_at,
                        "source": "test_seed",
                        "summary": "Seeded test playbook.",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _service_events(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != browser_report_download_service.logger.name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events
