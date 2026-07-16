from __future__ import annotations

from .builders import *  # noqa: F401,F403
from src.services._browser_report_download.browser import BrowserAgentRunResult


def test_browser_use_route_steps_are_enriched_with_post_action_verification(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page, click Download report, and wait for the PDF save to finish.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_agent = runtime.Agent

    class VerifiedRouteAgent(original_agent):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "click",
                    "target_text": "Download report",
                    "target_role": "button",
                    "target_url": "https://example.com/report",
                    "result": "downloaded PDF",
                    "expected_evidence": ["artifact"],
                }
            ]

            class VerifiedHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

                def action_results(self_nonlocal) -> list[Any]:
                    return history.action_results()

            return VerifiedHistory()

    runtime.Agent = VerifiedRouteAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    caplog.set_level(logging.INFO, logger=artifact_runtime.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert response.route_steps[0].expected_evidence == ["artifact"]
    assert response.route_steps[0].observed_evidence == ["artifact"]
    assert response.route_steps[0].verification_status == "verified"
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == artifact_runtime.logger.name
    ]
    verification_events = [
        event
        for event in events
        if event.get("event") == "browser_report_download_route_step_verification"
    ]
    assert verification_events
    assert_logs_have_required_fields(verification_events)
    assert verification_events[-1]["fields"]["validation_result"] == "verified"
    assert verification_events[-1]["fields"]["verification_status"] == "verified"
    for field_name in ("expected_evidence", "observed_evidence"):
        evidence = verification_events[-1]["fields"][field_name]
        assert evidence[0]["redaction"] == "***REDACTED***"
        assert evidence[0]["character_count"] == len("artifact")


def test_browser_use_route_step_missing_post_action_verification_fails(
    tmp_path: Path,
    run_context,
    assert_app_error,
) -> None:
    raw_model_response = json.dumps(
        {
            "route_kind": "email_delivery",
            "route_summary": "Open the report form, click Submit, and wait for the confirmation message.",
            "email_submission_completed": True,
            "post_submit_message": "",
            "route_steps": [
                {
                    "index": 0,
                    "action": "submit",
                    "target_text": "Submit",
                    "target_role": "button",
                    "target_url": "https://example.com/report#form",
                    "result": "submitted",
                }
            ],
        }
    )

    with pytest.raises(AppError) as exc_info:
        artifact_runtime.finalize_browser_report_download_result(
            request=BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=_settings(tmp_path),
                route_family_hint="browser_email_form",
            ),
            ctx=run_context,
            normalized_url="https://example.com/report",
            delivery_email="ops@example.com",
            download_dir=tmp_path / "downloads",
            browser_run=BrowserAgentRunResult(
                schema_version="1.0",
                raw_model_response=raw_model_response,
                final_page_url="",
                final_page_title="",
                final_page_html="",
                downloaded_files=[],
                attachment_paths=[],
                network_resource_urls=[],
                network_events=[],
                html_snapshot_path="",
                screenshot_path="",
            ),
        )

    assert_app_error(
        exc_info.value,
        code="browser_download_route_step_verification_missing",
        retryable=True,
    )
    assert exc_info.value.context["missing_steps"][0]["expected_evidence"] == [
        "confirmation_text",
        "network_event",
        "screenshot",
    ]
