from __future__ import annotations

from .builders import *  # noqa: F401,F403


def test_download_report_with_browser_use_preserves_configured_location_lookup_blocker(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = replace(
        _settings(tmp_path),
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="work_email",
                    label="Work email",
                    value="ops@example.com",
                    aliases=["email", "email address"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="company",
                    label="Company",
                    value="Market Lense",
                    aliases=["company"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="location",
                    label="Location",
                    value="Austria",
                    aliases=["country", "location"],
                ),
            ],
        ),
    )
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary=(
            "Opened the report page, filled the form, clicked submit, and observed the Location blocker."
        ),
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class LocationBlockerAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["encountered_form_fields"] = [
                "Business Email Address",
                "Company Name",
                "Location",
            ]
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "click",
                    "target_text": "Submit",
                    "target_role": "button",
                    "target_url": "https://example.com/report#download",
                    "result": "Clicked Submit button.",
                }
            ]
            payload["blocked_reason"] = "blocked_missing_identity_field"
            payload["blocked_reason_detail"] = (
                "The Location field could not be successfully selected, preventing form submission."
            )

            class LocationBlockerHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return LocationBlockerHistory()

    runtime.Agent = LocationBlockerAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_unknown_required_enum"
    assert "Location field could not be successfully selected" in str(
        response.blocked_reason_detail
    )


def test_download_report_with_browser_use_salvages_completed_history_when_agent_cleanup_stalls(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    settings = replace(_settings(tmp_path), timeout_seconds=0.05, max_steps=1)
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Open the report page and submit the form.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent
    original_browser = runtime.Browser

    class CompletedHistory:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._payload = payload
            self.history: list[Any] = []

        def is_done(self) -> bool:
            return True

        def final_result(self) -> str:
            return json.dumps(self._payload)

        def action_results(self) -> list[Any]:
            return []

    class CleanupStalledAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/thank-you"
            self.browser.title = "Thank you"
            self.browser.html = "<html><body><h1>Thank you</h1></body></html>"
            payload = {
                "route_kind": "email_delivery",
                "route_summary": "Submitted the form and reached the thank-you page.",
                "route_family": "browser_email_form",
                "resolved_target_url": "https://example.com/thank-you",
                "final_page_url": "https://example.com/thank-you",
                "email_submission_completed": True,
                "downloaded_file_path": None,
                "downloaded_file_name": None,
                "downloaded_mime_type": None,
                "encountered_form_fields": ["Work Email"],
                "route_steps": [],
                "post_submit_message": "Thank you",
                "confirmation_url_changed": True,
                "submit_button_state": "replaced",
                "form_disappeared": True,
                "blocked_reason": "",
                "blocked_reason_detail": "",
                "final_page_title": "Thank you",
                "terminal_text_excerpt": "Thanks for your interest.",
                "traversed_page_urls": [
                    "https://example.com/report",
                    "https://example.com/thank-you",
                ],
                "onsite_capture_path": None,
                "onsite_capture_format": None,
                "onsite_page_count": None,
                "onsite_completeness_status": "",
            }
            self.history = CompletedHistory(payload)
            time.sleep(2.0)
            return self.history

    class CaptureUnsafeBrowser(original_browser):
        def get_current_page(self):
            raise AssertionError(
                "salvaged completed history should skip live terminal capture"
            )

    runtime.Agent = CleanupStalledAgent
    runtime.Browser = CaptureUnsafeBrowser
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.final_page_url == "https://example.com/thank-you"
    assert response.confirmation_evidence is not None
    assert response.confirmation_evidence.visible_confirmation_text == "Thank you"
    events = _service_events(caplog)
    assert any(
        event.get("event") == "browser_report_download_completed_history_observed"
        for event in events
    )
    assert not any(
        event.get("event")
        == "browser_report_download_timeout_salvaged_completed_history"
        for event in events
    )


def test_download_report_with_browser_use_recovers_lookup_before_completed_history_shutdown(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = replace(_settings(tmp_path), timeout_seconds=0.05, max_steps=1)
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the form and clicked submit.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent
    original_browser = runtime.Browser

    class CompletedHistory:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._payload = payload
            self.history: list[Any] = []

        def is_done(self) -> bool:
            return True

        def final_result(self) -> str:
            return json.dumps(self._payload)

        def action_results(self) -> list[Any]:
            return []

    class ShutdownSensitiveBrowser(original_browser):
        def get_current_page(self):
            if getattr(self, "_intentional_stop", False):
                raise AssertionError("lookup assist must run before browser shutdown")
            return super().get_current_page()

    class LookupRecoveredAgent(original_runtime):
        def run_sync(self, max_steps: int):
            browser = self.browser
            browser.url = "https://example.com/report#download"
            browser.title = "Example report"
            browser.html = ""

            class LookupAssistPage:
                def evaluate(self, script):
                    script_text = str(script or "")
                    if (
                        "selected_count" in script_text
                        and ".lookupFormFieldBlock" in script_text
                    ):
                        browser.url = "https://example.com/report#success"
                        browser.title = "Thank you"
                        browser.html = (
                            "<html><body>"
                            "Thank you for your interest. You will be emailed a "
                            "downloadable copy of this insight shortly."
                            "</body></html>"
                        )
                        return {
                            "acted": True,
                            "selected_count": 1,
                            "submitted": True,
                            "final_url": browser.url,
                        }
                    if "navigationEntries" in script_text:
                        return []
                    if "document.querySelectorAll" in script_text:
                        return []
                    return []

            browser.current_page_factory = LookupAssistPage
            payload = {
                "route_kind": "email_delivery",
                "route_summary": "Filled the form and clicked submit.",
                "route_family": "browser_email_form",
                "resolved_target_url": "https://example.com/report#download",
                "final_page_url": "https://example.com/report#download",
                "email_submission_completed": True,
                "downloaded_file_path": None,
                "downloaded_file_name": None,
                "downloaded_mime_type": None,
                "encountered_form_fields": [
                    "First Name",
                    "Last Name",
                    "Business Email Address",
                    "Location",
                ],
                "route_steps": [
                    {
                        "index": 0,
                        "action": "click",
                        "target_text": "Submit",
                        "target_role": "button",
                        "target_url": "https://example.com/report#download",
                        "result": 'Clicked button "Submit"',
                    }
                ],
                "post_submit_message": None,
                "confirmation_url_changed": False,
                "submit_button_state": None,
                "form_disappeared": False,
                "blocked_reason": None,
                "blocked_reason_detail": None,
                "final_page_title": "Example report",
                "terminal_text_excerpt": None,
                "traversed_page_urls": [
                    "https://example.com/report",
                    "https://example.com/report#download",
                ],
                "onsite_capture_path": None,
                "onsite_capture_format": None,
                "onsite_page_count": None,
                "onsite_completeness_status": None,
            }
            self.history = CompletedHistory(payload)
            time.sleep(2.0)
            return self.history

    runtime.Agent = LookupRecoveredAgent
    runtime.Browser = ShutdownSensitiveBrowser
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.route_status == "verified"
    assert response.final_page_url == "https://example.com/report#success"


def test_download_report_with_browser_use_bounds_lookup_assist_after_completed_history_timeout(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    settings = replace(_settings(tmp_path), timeout_seconds=0.05, max_steps=1)
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the form but the location lookup still blocked submission.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class CompletedHistory:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._payload = payload
            self.history: list[Any] = []

        def is_done(self) -> bool:
            return True

        def final_result(self) -> str:
            return json.dumps(self._payload)

        def action_results(self) -> list[Any]:
            return []

    class TimedOutLookupBlockedAgent(original_runtime):
        def run_sync(self, max_steps: int):
            browser = self.browser
            browser.url = "https://example.com/report#download"
            browser.title = "Example report"
            browser.html = "<html><body><h1>Example report</h1></body></html>"

            class BlockingLookupPage:
                def evaluate(self, script):
                    script_text = str(script or "")
                    if (
                        "selected_count" in script_text
                        and ".lookupFormFieldBlock" in script_text
                    ):
                        time.sleep(7.0)
                        return {"acted": False}
                    if "navigationEntries" in script_text:
                        return []
                    if "document.querySelectorAll" in script_text:
                        return []
                    return []

            browser.current_page_factory = BlockingLookupPage
            payload = {
                "route_kind": "email_delivery",
                "route_summary": (
                    "Filled the form but the location lookup still blocked submission."
                ),
                "route_family": "browser_email_form",
                "resolved_target_url": "https://example.com/report#download",
                "final_page_url": "https://example.com/report#download",
                "email_submission_completed": False,
                "downloaded_file_path": None,
                "downloaded_file_name": None,
                "downloaded_mime_type": None,
                "encountered_form_fields": [
                    "First Name",
                    "Last Name",
                    "Business Email Address",
                    "Location",
                ],
                "route_steps": [
                    {
                        "index": 0,
                        "action": "click",
                        "target_text": "Submit",
                        "target_role": "button",
                        "target_url": "https://example.com/report#download",
                        "result": 'Clicked button "Submit"',
                    }
                ],
                "post_submit_message": None,
                "confirmation_url_changed": False,
                "submit_button_state": None,
                "form_disappeared": False,
                "blocked_reason": "blocked_unknown_required_enum",
                "blocked_reason_detail": (
                    "The Location field could not be successfully filled or submitted."
                ),
                "final_page_title": "Example report",
                "terminal_text_excerpt": "Location:\nSearch country...",
                "traversed_page_urls": [
                    "https://example.com/report",
                    "https://example.com/report#download",
                ],
                "onsite_capture_path": None,
                "onsite_capture_format": None,
                "onsite_page_count": None,
                "onsite_completeness_status": None,
            }
            self.history = CompletedHistory(payload)
            time.sleep(2.0)
            return self.history

    runtime.Agent = TimedOutLookupBlockedAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert "Location field could not be successfully filled or submitted" in str(
        response.blocked_reason_detail
    )
    assert any(
        event.get("event") == "browser_report_download_timeout_recovery_timed_out"
        and event.get("fields", {}).get("operation") == "lookup_submission_assist"
        for event in _service_events(caplog)
    )


def test_download_report_with_browser_use_maps_partial_lookup_timeout_to_blocker(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    settings = replace(_settings(tmp_path), timeout_seconds=0.05, max_steps=1)
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class PartialHistory:
        def __init__(self, entries: list[Any]) -> None:
            self.history = entries

        def is_done(self) -> bool:
            return False

        def final_result(self) -> None:
            return None

    class TimedOutPartialLookupAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/report#download"
            self.browser.title = "Example report"
            self.browser.html = "<html><body><form>Location Submit</form></body></html>"
            self.history = PartialHistory(
                [
                    SimpleNamespace(
                        model_output=SimpleNamespace(
                            thinking="",
                            evaluation_previous_goal=(
                                "The previous attempt to select Austria from the "
                                "Location dropdown and submit the form was unsuccessful "
                                "due to incorrect input processing and selection."
                            ),
                            memory=(
                                "All fields are filled except the Location lookup. "
                                "Submit was clicked, but Location did not resolve."
                            ),
                            next_goal=(
                                "Correctly select Austria from the Location dropdown "
                                "and then click the submit button."
                            ),
                            action=[
                                {
                                    "input": {
                                        "index": 92,
                                        "text": "Austria",
                                        "clear": True,
                                    }
                                },
                                {"click": {"index": 1841}},
                            ],
                        ),
                        result=[
                            SimpleNamespace(
                                error=None,
                                long_term_memory='Clicked button "Submit"',
                                extracted_content=None,
                            )
                        ],
                        state=SimpleNamespace(
                            url="https://example.com/report#download",
                            title="Example report",
                            screenshot_path=None,
                        ),
                    )
                ]
            )
            time.sleep(2.0)
            return self.history

    runtime.Agent = TimedOutPartialLookupAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_unknown_required_enum"
    assert "Location field did not resolve" in str(response.blocked_reason_detail)
    assert response.final_page_url == "https://example.com/report#download"
    assert any(
        event.get("event")
        == "browser_report_download_timeout_salvaged_partial_history_blocker"
        for event in _service_events(caplog)
    )


def test_download_report_with_browser_use_lookup_submission_assist_recovers_lookup_blocked_submit(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the form but the location lookup still blocked submission.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class LookupBlockedSubmitAgent(original_runtime):
        def run_sync(self, max_steps: int):
            browser = self.browser
            browser.url = "https://example.com/report#download"
            browser.title = "Example report"
            browser.html = ""

            class LookupBlockedSubmitPage:
                def evaluate(self, script):
                    script_text = str(script or "")
                    if (
                        "selected_count" in script_text
                        and ".lookupFormFieldBlock" in script_text
                    ):
                        browser.url = "https://example.com/report#success"
                        browser.title = "Thank you"
                        browser.html = (
                            "<html><body>"
                            "Thank you for your interest. You will be emailed a "
                            "downloadable copy of this insight shortly."
                            "</body></html>"
                        )
                        return {
                            "acted": True,
                            "selected_count": 1,
                            "submitted": True,
                            "final_url": browser.url,
                        }
                    if "navigationEntries" in script_text:
                        return []
                    if "document.querySelectorAll" in script_text:
                        return []
                    return []

            browser.current_page_factory = LookupBlockedSubmitPage
            payload = {
                "route_kind": "email_delivery",
                "route_summary": (
                    "Filled the form, typed Austria in Location, clicked submit, "
                    "and remained on the form."
                ),
                "route_family": "browser_email_form",
                "resolved_target_url": "https://example.com/report#download",
                "final_page_url": "https://example.com/report#download",
                "email_submission_completed": False,
                "downloaded_file_path": None,
                "downloaded_file_name": None,
                "downloaded_mime_type": None,
                "encountered_form_fields": [
                    "First Name",
                    "Last Name",
                    "Business Email Address",
                    "Business Phone",
                    "Company Name",
                    "Role",
                    "Department",
                    "Industry",
                    "Location",
                ],
                "route_steps": [
                    {
                        "index": 10,
                        "action": "input",
                        "target_text": "Austria",
                        "target_role": "textbox",
                        "target_url": "https://example.com/report#download",
                        "result": "Typed 'Austria'",
                    },
                    {
                        "index": 11,
                        "action": "click",
                        "target_text": "Submit",
                        "target_role": "button",
                        "target_url": "https://example.com/report#download",
                        "result": 'Clicked button "Submit"',
                    },
                ],
                "post_submit_message": None,
                "confirmation_url_changed": False,
                "submit_button_state": None,
                "form_disappeared": False,
                "blocked_reason": "blocked_unknown_required_enum",
                "blocked_reason_detail": (
                    "The Location field did not resolve to a valid lookup selection."
                ),
                "final_page_title": "Example report",
                "terminal_text_excerpt": None,
                "traversed_page_urls": [
                    "https://example.com/report",
                    "https://example.com/report#download",
                ],
                "onsite_capture_path": None,
                "onsite_capture_format": None,
                "onsite_page_count": None,
                "onsite_completeness_status": None,
            }

            class LookupBlockedSubmitHistory:
                def final_result(self) -> str:
                    return json.dumps(payload)

                def action_results(self) -> list[Any]:
                    return []

            return LookupBlockedSubmitHistory()

    runtime.Agent = LookupBlockedSubmitAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.route_status == "verified"
    assert response.final_page_url == "https://example.com/report#success"
    assert response.confirmation_evidence is not None
    assert response.confirmation_evidence.visible_confirmation_text.startswith(
        "Thank you for your interest."
    )


def test_browser_worker_main_preserves_candidate_trace(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://example.com/report",
        title="Example Report",
        discovered_on_page_number=2,
        source_page_urls=[
            "https://example.com/insights",
            "https://example.com/resources",
        ],
        discovery_provenances=["http_parse", "browser_dom"],
        pdf_url="https://cdn.example.com/example-report.pdf",
        published_at_text="April 2026",
        max_confidence=0.92,
    )
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url=candidate_trace.canonical_url,
        settings=_settings(tmp_path),
        candidate_trace=candidate_trace,
        attempt_url="https://example.com/report?download=1",
        route_family_hint="browser_pdf_click",
    )
    download_dir = tmp_path / "worker-run"
    payload_path = tmp_path / "browser_agent_worker_request.json"
    response_path = tmp_path / "browser_agent_worker_response.json"
    payload_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "request": {
                    **json.loads(
                        json.dumps(request, default=lambda value: value.__dict__)
                    ),
                },
                "ctx": run_context.__dict__,
                "normalized_url": request.url,
                "execution_url": request.attempt_url,
                "download_dir": str(download_dir),
                "prompt_bundle": {
                    "schema_version": "1.0",
                    "namespace": "browser_report_download/browser_route",
                    "system_prompt_path": "system.yaml",
                    "user_prompt_path": "user.yaml",
                    "system_prompt_sha256": "system",
                    "user_prompt_sha256": "user",
                    "rendered_system_prompt": "system",
                    "rendered_user_prompt": "user",
                    "task_prompt": "task",
                },
            }
        ),
        encoding="utf-8",
    )

    observed_requests: list[BrowserReportDownloadRequest] = []

    def fake_run_browser_report_download_agent(**kwargs):
        observed_requests.append(kwargs["request"])
        return browser_runtime.BrowserAgentRunResult(
            schema_version="1.0",
            raw_model_response="{}",
            final_page_url="https://example.com/final",
            final_page_title="Example",
            final_page_html="<html></html>",
            downloaded_files=[],
            attachment_paths=[],
            network_resource_urls=[],
            network_events=[],
            html_snapshot_path="",
            screenshot_path="",
        )

    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "run_browser_report_download_agent",
        fake_run_browser_report_download_agent,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "setup_logging",
        lambda *args, **kwargs: None,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime.sys,
        "argv",
        [
            "browser_worker.py",
            str(payload_path),
            str(response_path),
        ],
    )

    assert browser_worker_runtime.main() == 0
    assert response_path.exists()
    assert len(observed_requests) == 1
    observed_request = observed_requests[0]
    assert observed_request.candidate_trace is not None
    assert (
        observed_request.candidate_trace.canonical_url == candidate_trace.canonical_url
    )
    assert observed_request.candidate_trace.pdf_url == candidate_trace.pdf_url
    assert observed_request.candidate_trace.discovery_provenances == (
        candidate_trace.discovery_provenances
    )


def test_browser_worker_subprocess_forces_utf8_and_captures_output(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
    )
    prompt_bundle = prompt_runtime.BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace="browser_report_download/browser_route",
        system_prompt_path="system.yaml",
        user_prompt_path="user.yaml",
        system_prompt_sha256="system",
        user_prompt_sha256="user",
        rendered_system_prompt="system",
        rendered_user_prompt="user",
        task_prompt="task",
    )

    def fake_run(*args, **kwargs):
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["stderr"] == subprocess.STDOUT
        assert kwargs["text"] is True
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
        assert kwargs["env"][browser_runtime._BROWSER_AGENT_WORKER_ENV] == "1"
        assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
        assert kwargs["env"]["PYTHONUTF8"] == "1"
        assert kwargs["env"]["NO_COLOR"] == "1"
        assert kwargs["env"]["RICH_DISABLE"] == "1"
        response_path = Path(args[0][-1])
        response_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "ok",
                    "result": {
                        "schema_version": "1.0",
                        "raw_model_response": "{}",
                        "final_page_url": "https://example.com/final",
                        "final_page_title": "Final",
                        "final_page_html": "<html></html>",
                        "downloaded_files": [],
                        "attachment_paths": [],
                        "network_resource_urls": [],
                        "network_events": [],
                        "html_snapshot_path": "",
                        "screenshot_path": "",
                    },
                    "error": None,
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="INFO browser_use.Agent Step 1: click download\n",
        )

    external_boundary_mocks_only.setattr(browser_runtime.subprocess, "run", fake_run)

    result = browser_runtime._run_browser_report_download_agent_subprocess(
        request=request,
        ctx=run_context,
        normalized_url=request.url,
        execution_url=request.url,
        download_dir=tmp_path / "worker-download",
        prompt_bundle=prompt_bundle,
    )

    assert result.final_page_url == "https://example.com/final"
    completion_events = [
        event
        for event in _service_events(caplog)
        if event.get("event") == "browser_report_download_worker_complete"
    ]
    assert len(completion_events) == 1
    completion_fields = completion_events[0]["fields"]
    assert completion_fields["worker_output_captured"] is True
    assert completion_fields["worker_output_excerpt"] == (
        "INFO browser_use.Agent Step 1: click download"
    )
    assert_logs_have_required_fields(_service_events(caplog))


def test_browser_worker_subprocess_sanitizes_failure_output_excerpt(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
    )
    prompt_bundle = prompt_runtime.BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace="browser_report_download/browser_route",
        system_prompt_path="system.yaml",
        user_prompt_path="user.yaml",
        system_prompt_sha256="system",
        user_prompt_sha256="user",
        rendered_system_prompt="system",
        rendered_user_prompt="user",
        task_prompt="task",
    )

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="browser_use.Agent🤖\r\n\x1b[31mStep 1 failed\x1b[0m\r\n",
        )

    external_boundary_mocks_only.setattr(browser_runtime.subprocess, "run", fake_run)

    with pytest.raises(AppError) as exc_info:
        browser_runtime._run_browser_report_download_agent_subprocess(
            request=request,
            ctx=run_context,
            normalized_url=request.url,
            execution_url=request.url,
            download_dir=tmp_path / "worker-download",
            prompt_bundle=prompt_bundle,
        )

    assert exc_info.value.code == "browser_download_agent_missing_result"
    assert exc_info.value.context == {
        "normalized_url": "https://example.com/report",
        "return_code": 1,
        "worker_output_excerpt": "browser_use.Agent\nStep 1 failed",
    }
    completion_events = [
        event
        for event in _service_events(caplog)
        if event.get("event") == "browser_report_download_worker_complete"
    ]
    assert len(completion_events) == 1
    completion_fields = completion_events[0]["fields"]
    assert completion_fields["worker_output_excerpt"] == (
        "browser_use.Agent\nStep 1 failed"
    )
    assert_logs_have_required_fields(_service_events(caplog))


def test_download_report_with_browser_use_cleans_stale_browser_use_temp_dirs_before_launch(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    stale_profile_dir = tmp_path / "browser-use-user-data-dir-stale"
    stale_profile_dir.mkdir(parents=True, exist_ok=True)
    (stale_profile_dir / "SingletonLock").write_text("lock", encoding="utf-8")
    stale_download_dir = tmp_path / "browser-use-downloads-stale"
    stale_download_dir.mkdir(parents=True, exist_ok=True)
    (stale_download_dir / "artifact.tmp").write_text("x", encoding="utf-8")
    old_timestamp = time.time() - (
        browser_runtime._STALE_BROWSER_USE_TEMP_DIR_MIN_AGE_SECONDS + 60.0
    )
    os.utime(stale_profile_dir, (old_timestamp, old_timestamp))
    os.utime(stale_download_dir, (old_timestamp, old_timestamp))

    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page and save the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime.tempfile,
        "gettempdir",
        lambda: str(tmp_path),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/stale-temp-report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert not stale_profile_dir.exists()
    assert not stale_download_dir.exists()


def test_download_report_with_browser_use_cleans_new_browser_use_temp_dirs_after_run(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page and save the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class TempLeakAgent(original_runtime):
        def run_sync(self, max_steps: int):
            leaked_profile_dir = tmp_path / "browseruse-tmp-created-during-run"
            leaked_profile_dir.mkdir(parents=True, exist_ok=True)
            (leaked_profile_dir / "cache.tmp").write_text("temp", encoding="utf-8")
            return super().run_sync(max_steps)

    runtime.Agent = TempLeakAgent
    external_boundary_mocks_only.setattr(
        browser_runtime.tempfile,
        "gettempdir",
        lambda: str(tmp_path),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/temp-leak-report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert not (tmp_path / "browseruse-tmp-created-during-run").exists()


def test_download_report_with_browser_use_reuses_bounded_same_publisher_profile(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    caplog,
) -> None:
    caplog.set_level(
        logging.INFO,
        logger="market_lense.browser_report_download_service.session_reuse",
    )
    reuse_base_dir = tmp_path / "session-reuse"
    settings = replace(
        _settings(tmp_path),
        session_reuse_policy=BrowserDownloadSessionReusePolicy(
            schema_version="1.0",
            enabled=True,
            mode="same_publisher_batch",
            session_key="batch-key",
            publisher_scope="example.com",
            ttl_seconds=120.0,
            base_dir=str(reuse_base_dir),
        ),
    )
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page and save the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_browser = runtime.Browser
    browser_profile_paths: list[str] = []

    class ReuseTrackingBrowser(original_browser):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            browser_profile_paths.append(str(kwargs.get("user_data_dir") or ""))

    runtime.Browser = ReuseTrackingBrowser
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    first = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/reuse-report",
            settings=settings,
        ),
        run_context,
    )
    second = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/reuse-report",
            settings=settings,
        ),
        run_context,
    )

    assert first.outcome == "downloaded"
    assert second.outcome == "downloaded"
    assert len(browser_profile_paths) == 2
    assert browser_profile_paths[0] == browser_profile_paths[1]
    profile_path = Path(browser_profile_paths[0])
    assert profile_path.exists()
    assert (profile_path / "session_reuse_ledger.json").exists()
    reuse_events = []
    for record in caplog.records:
        payload = json.loads(record.message)
        if payload.get("event") == "browser_report_download_session_reuse_resolved":
            reuse_events.append(payload)
    assert [event["fields"]["profile_reused"] for event in reuse_events[-2:]] == [
        False,
        True,
    ]


def test_browser_session_reuse_rejects_cross_publisher_key_without_override(
    tmp_path: Path,
    run_context,
) -> None:
    policy = BrowserDownloadSessionReusePolicy(
        schema_version="1.0",
        enabled=True,
        mode="same_publisher_batch",
        session_key="shared-key",
        publisher_scope="example.com",
        ttl_seconds=120.0,
        base_dir=str(tmp_path / "session-reuse"),
    )
    first = browser_runtime.resolve_browser_session_reuse(
        policy=policy,
        default_base_dir=tmp_path,
        normalized_url="https://example.com/report",
        ctx=run_context,
    )
    second = browser_runtime.resolve_browser_session_reuse(
        policy=replace(policy, publisher_scope="other.example"),
        default_base_dir=tmp_path,
        normalized_url="https://other.example/report",
        ctx=run_context,
    )

    assert first.accepted is True
    assert second.accepted is False
    assert second.rejection_reason == "cross_publisher_scope_mismatch"


def test_prepare_download_dir_tolerates_locked_managed_browser_profile_dir(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    normalized_url = (
        "https://www.brightlocal.com/research/local-rankings-investigation-dentist"
    )
    download_dir = request_runtime.prepare_download_dir(
        root_dir=str(tmp_path),
        normalized_url=normalized_url,
    )
    locked_profile_dir = download_dir / "browser-use-user-data-dir-profile-locked"
    locked_profile_dir.mkdir(parents=True, exist_ok=True)
    (locked_profile_dir / "journal.baj").write_text("locked", encoding="utf-8")
    stale_artifact = download_dir / "stale.txt"
    stale_artifact.write_text("stale", encoding="utf-8")
    original_rmtree = request_runtime.rmtree

    def fake_rmtree(path: str | Path, *args: Any, **kwargs: Any) -> None:
        candidate = Path(path)
        if candidate == locked_profile_dir:
            raise PermissionError(13, "locked", str(candidate))
        return original_rmtree(path, *args, **kwargs)

    external_boundary_mocks_only.setattr(request_runtime, "rmtree", fake_rmtree)

    prepared_dir = request_runtime.prepare_download_dir(
        root_dir=str(tmp_path),
        normalized_url=normalized_url,
    )

    assert prepared_dir == download_dir
    assert locked_profile_dir.exists()
    assert not stale_artifact.exists()


def test_kill_browser_force_stops_local_watchdog_process_tree(
    run_context,
    external_boundary_mocks_only,
) -> None:
    class _FakeProcess:
        def __init__(
            self, pid: int, children: list["_FakeProcess"] | None = None
        ) -> None:
            self.pid = pid
            self._children = children or []
            self.terminate_calls = 0
            self.kill_calls = 0

        def children(self, recursive: bool = False) -> list["_FakeProcess"]:
            if not recursive:
                return list(self._children)
            descendants: list[_FakeProcess] = []
            for child in self._children:
                descendants.append(child)
                descendants.extend(child.children(recursive=True))
            return descendants

        def terminate(self) -> None:
            self.terminate_calls += 1

        def kill(self) -> None:
            self.kill_calls += 1

    grandchild = _FakeProcess(pid=3003)
    child = _FakeProcess(pid=3002, children=[grandchild])
    root = _FakeProcess(pid=3001, children=[child])

    def _fake_psutil_process(pid: int) -> _FakeProcess:
        assert pid == 3001
        return root

    def _fake_wait_procs(processes: list[_FakeProcess], timeout: float):
        assert timeout > 0.0
        return list(processes), []

    fake_browser = SimpleNamespace(
        browser_profile=SimpleNamespace(user_data_dir="active-profile"),
        _local_browser_watchdog=SimpleNamespace(
            _subprocess=SimpleNamespace(pid=3001),
            _temp_dirs_to_cleanup=[],
            _original_user_data_dir=None,
        ),
        kill=lambda: (_ for _ in ()).throw(
            AssertionError("browser.kill should not run")
        ),
    )

    external_boundary_mocks_only.setattr(
        browser_runtime.psutil,
        "Process",
        _fake_psutil_process,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime.psutil,
        "wait_procs",
        _fake_wait_procs,
    )

    browser_runtime._kill_browser(
        fake_browser,
        ctx=run_context,
        normalized_url="https://example.com/report",
    )

    assert root.terminate_calls == 1
    assert child.terminate_calls == 1
    assert grandchild.terminate_calls == 1
    assert root.kill_calls == 0
    assert child.kill_calls == 0
    assert grandchild.kill_calls == 0
    assert fake_browser._local_browser_watchdog._subprocess is None


def test_prepare_browser_for_shutdown_awaits_cancelled_reconnect_task(
    run_context,
) -> None:
    event_calls: list[str] = []

    class FakeReconnectTask:
        def __init__(self) -> None:
            self.cancelled = False
            self.awaited = False

        def done(self) -> bool:
            return False

        def cancel(self) -> None:
            self.cancelled = True

        def __await__(self):
            self.awaited = True
            if False:
                yield None
            return None

    reconnect_task = FakeReconnectTask()
    fake_browser = SimpleNamespace(
        browser_profile=SimpleNamespace(cdp_url="ws://example"),
        _reconnect_task=reconnect_task,
        _reconnect_event=SimpleNamespace(set=lambda: event_calls.append("set")),
        _reconnecting=True,
    )

    browser_runtime._prepare_browser_for_shutdown(
        fake_browser,
        ctx=run_context,
        normalized_url="https://example.com/report",
    )

    assert reconnect_task.cancelled is True
    assert reconnect_task.awaited is True
    assert fake_browser._reconnect_task is None
    assert fake_browser._reconnecting is False
    assert fake_browser.browser_profile.cdp_url is None
    assert event_calls == ["set"]


def test_download_report_with_browser_use_maps_browser_start_timeout_to_typed_error(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class BrowserStartTimeoutAgent(original_runtime):
        def run_sync(self, max_steps: int):
            raise TimeoutError(
                "Event handler browser_use.browser.watchdog_base.BrowserSession.on_BrowserStartEvent "
                "timed out after 30.0s and interrupted any processing of 1 child events"
            )

    runtime.Agent = BrowserStartTimeoutAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    with pytest.raises(AppError) as exc_info:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://datareportal.com/reports/digital-2026-mozambique",
                settings=_settings(tmp_path),
            ),
            run_context,
        )

    assert_app_error(
        exc_info.value,
        code="browser_download_browser_start_timeout",
        retryable=True,
    )


def test_download_report_with_browser_use_times_out_stalled_agent(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = _settings(tmp_path)
    settings = replace(settings, timeout_seconds=0.05, max_steps=1)

    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent
    original_browser = runtime.Browser
    kill_calls: list[str] = []
    stop_observations: list[bool] = []

    class TrackingBrowser(original_browser):
        async def kill(self) -> None:
            kill_calls.append("kill")
            await super().kill()

    class StalledAgent(original_runtime):
        def stop(self) -> None:
            stop_observations.append(hasattr(self, "_task_start_time"))
            super().stop()

        def run_sync(self, max_steps: int):
            time.sleep(2.0)
            return super().run_sync(max_steps)

    runtime.Browser = TrackingBrowser
    runtime.Agent = StalledAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    with pytest.raises(AppError) as exc_info:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/whitepapers/eu-cosmetics-regulations-foundations-plm",
                settings=settings,
                route_family_hint="browser_pdf_click",
            ),
            run_context,
        )

    assert exc_info.value.code == "browser_download_agent_timeout"
    assert kill_calls
    assert stop_observations == [True]
