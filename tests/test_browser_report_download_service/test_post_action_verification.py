from __future__ import annotations

import asyncio

from .builders import *  # noqa: F401,F403
from src.services._browser_report_download.browser import BrowserAgentRunResult
from src.services._browser_report_download._browser_runtime.no_progress import (
    BrowserNoProgressDetector,
)


def _no_progress_state(
    *,
    url: str = "https://example.com/report",
    dom: str = "<button>Download report</button><form><input name='email'></form>",
    blocker: str = "",
    pending_network_urls: list[str] | None = None,
    recent_events: str = "",
) -> Any:
    return SimpleNamespace(
        url=url,
        dom_state=SimpleNamespace(
            selector_map={"1": object()},
            llm_representation=lambda: dom,
        ),
        pending_network_requests=[
            SimpleNamespace(url=item, method="GET", resource_type="Document")
            for item in pending_network_urls or []
        ],
        recent_events=recent_events,
        closed_popup_messages=[],
        browser_errors=[],
        title="Example report",
    ), SimpleNamespace(
        current_state=SimpleNamespace(
            memory=blocker,
            evaluation_previous_goal=blocker,
            next_goal=blocker,
        )
    )


def test_browser_no_progress_requires_three_equivalent_turns() -> None:
    detector = BrowserNoProgressDetector()
    state, output = _no_progress_state()

    first = detector.observe(state=state, model_output=output, step_number=1)
    second = detector.observe(state=state, model_output=output, step_number=2)
    third = detector.observe(state=state, model_output=output, step_number=3)

    assert first.should_stop is False
    assert second.should_stop is False
    assert third.should_stop is True
    assert third.consecutive_equivalent_turns == 3


def test_browser_no_progress_fails_open_when_actionable_dom_is_missing() -> None:
    detector = BrowserNoProgressDetector()
    state, output = _no_progress_state()
    state.dom_state = None

    observations = [
        detector.observe(state=state, model_output=output, step_number=step_number)
        for step_number in range(1, 6)
    ]

    assert all(observation.should_stop is False for observation in observations)
    assert all(
        observation.consecutive_equivalent_turns == 0
        for observation in observations
    )


def test_browser_no_progress_fails_open_when_actionable_dom_is_empty() -> None:
    detector = BrowserNoProgressDetector()
    state, output = _no_progress_state(dom="")

    observations = [
        detector.observe(state=state, model_output=output, step_number=step_number)
        for step_number in range(1, 6)
    ]

    assert all(observation.actionable_dom_available is False for observation in observations)
    assert all(observation.should_stop is False for observation in observations)
    assert all(
        observation.consecutive_equivalent_turns == 0
        for observation in observations
    )


def test_browser_no_progress_fails_open_when_dom_reader_raises() -> None:
    detector = BrowserNoProgressDetector()
    state, output = _no_progress_state()

    def raise_dom_reader_error() -> str:
        raise RuntimeError("Browser DOM instrumentation is unavailable")

    state.dom_state.llm_representation = raise_dom_reader_error
    observations = [
        detector.observe(state=state, model_output=output, step_number=step_number)
        for step_number in range(1, 6)
    ]

    assert all(observation.should_stop is False for observation in observations)
    assert all(
        observation.consecutive_equivalent_turns == 0
        for observation in observations
    )


def test_browser_no_progress_stays_disabled_after_dom_instrumentation_failure() -> None:
    detector = BrowserNoProgressDetector()
    valid_state, output = _no_progress_state()
    detector.observe(state=valid_state, model_output=output, step_number=1)
    detector.observe(state=valid_state, model_output=output, step_number=2)

    unavailable_state, unavailable_output = _no_progress_state()
    unavailable_state.dom_state = None
    unavailable = detector.observe(
        state=unavailable_state,
        model_output=unavailable_output,
        step_number=3,
    )
    later_valid = detector.observe(
        state=valid_state,
        model_output=output,
        step_number=4,
    )

    assert unavailable.should_stop is False
    assert later_valid.should_stop is False
    assert later_valid.consecutive_equivalent_turns == 0


def test_browser_no_progress_resets_for_each_material_progress_signal() -> None:
    detector = BrowserNoProgressDetector()
    baseline_state, baseline_output = _no_progress_state()
    detector.observe(state=baseline_state, model_output=baseline_output, step_number=1)
    detector.observe(state=baseline_state, model_output=baseline_output, step_number=2)

    progressed_states = [
        _no_progress_state(url="https://example.com/report/thank-you"),
        _no_progress_state(dom="<form><input value='submitted'></form>"),
        _no_progress_state(dom="<a href='/report.pdf'>Download PDF</a>"),
        _no_progress_state(pending_network_urls=["https://example.com/report.pdf"]),
        _no_progress_state(recent_events="Submission confirmed"),
        _no_progress_state(blocker="captcha challenge"),
    ]

    for step_number, (state, output) in enumerate(progressed_states, start=3):
        observation = detector.observe(
            state=state,
            model_output=output,
            step_number=step_number,
        )

        assert observation.consecutive_equivalent_turns == 1
        assert observation.should_stop is False


def test_browser_no_progress_resets_when_a_browser_artifact_appears() -> None:
    browser = SimpleNamespace(downloaded_files=[])
    detector = BrowserNoProgressDetector(browser=browser)
    state, output = _no_progress_state()
    detector.observe(state=state, model_output=output, step_number=1)
    detector.observe(state=state, model_output=output, step_number=2)

    browser.downloaded_files.append("C:/safe/report.pdf")
    observation = detector.observe(state=state, model_output=output, step_number=3)

    assert observation.artifact_count == 1
    assert observation.consecutive_equivalent_turns == 1
    assert observation.should_stop is False


def test_browser_no_progress_stop_marks_browser_teardown_intentional() -> None:
    browser = SimpleNamespace(
        _intentional_stop=False,
        browser_profile=SimpleNamespace(cdp_url="ws://127.0.0.1:9222/devtools/browser/example"),
    )
    detector = BrowserNoProgressDetector(browser=browser)
    state, output = _no_progress_state()

    for step_number in range(1, 4):
        detector.observe(
            state=state,
            model_output=output,
            step_number=step_number,
        )

    assert asyncio.run(detector.should_stop_callback()) is True
    assert browser._intentional_stop is True
    assert browser.browser_profile.cdp_url is None


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
