# ruff: noqa: F401,F403,F405
from __future__ import annotations

import asyncio

from ._shared import *  # noqa: F401,F403


def test_download_report_with_browser_use_runs_async_form_preflight_and_agent_on_one_event_loop(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    """A retained BrowserSession must not cross separate ``asyncio.run`` calls."""

    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Submitted the report request form.",
        create_pdf=False,
        email_submission_completed=True,
        post_submit_message="Thank you",
    )
    original_browser = runtime.Browser
    original_agent = runtime.Agent
    observed_loop_ids: list[int] = []

    class AsyncPage:
        async def evaluate(self, expression: str):
            if "outerHTML" in expression:
                return "<html><body><h1>Example report terminal</h1></body></html>"
            return {
                "attempted_count": 0,
                "filled_count": 0,
                "selected_count": 0,
                "mandatory_agreement_checked_count": 0,
                "resolved_control_count": 0,
                "submitted": False,
                "final_url": "https://example.com/report",
                "resolved_fields": [],
                "unresolved_fields": [],
                "unresolved_options": {},
            }

    class AsyncBrowser(original_browser):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.page = AsyncPage()

        async def start(self) -> None:
            observed_loop_ids.append(id(asyncio.get_running_loop()))

        async def get_current_page(self):
            return self.page

        async def get_current_page_url(self) -> str:
            return self.url or "https://example.com/report"

        async def get_current_page_title(self) -> str:
            return self.title

    class AsyncAgent(original_agent):
        def run_sync(self, max_steps: int):
            raise AssertionError("async BrowserSession must not use Agent.run_sync")

        async def run(self, max_steps: int):
            observed_loop_ids.append(id(asyncio.get_running_loop()))
            self.browser.url = "https://example.com/thank-you"
            self.browser.title = "Thank you"
            self.browser.html = "<html><body><h1>Thank you</h1></body></html>"
            return super().run_sync(max_steps)

    runtime.Browser = AsyncBrowser
    runtime.Agent = AsyncAgent
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

    assert response.outcome == "email_requested"
    assert len(observed_loop_ids) == 2
    assert observed_loop_ids[0] == observed_loop_ids[1]


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
    base_settings = _settings(tmp_path)
    settings = replace(
        base_settings,
        timeout_seconds=0.05,
        max_steps=1,
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                *base_settings.identity_profile.fields,
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="country",
                    label="Country",
                    value="Austria",
                    aliases=["location", "country"],
                ),
            ],
        ),
    )
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
    base_settings = _settings(tmp_path)
    settings = replace(
        base_settings,
        timeout_seconds=0.05,
        max_steps=1,
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                *base_settings.identity_profile.fields,
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="country",
                    label="Country",
                    value="Austria",
                    aliases=["location", "country"],
                ),
            ],
        ),
    )
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
    settings = replace(
        _settings(tmp_path),
        timeout_seconds=0.05,
        max_steps=1,
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="country",
                    label="Country",
                    value="Example Country",
                    aliases=["location"],
                )
            ],
        ),
    )
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
                        time.sleep(1.2)
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
    timeout_events = [
        event
        for event in _service_events(caplog)
        if event.get("event") == "browser_report_download_timeout_recovery_timed_out"
        and event.get("fields", {}).get("operation") == "lookup_submission_assist"
    ]
    assert len(timeout_events) == 1
    assert timeout_events[0]["fields"]["timeout_seconds"] == 0.05


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


__all__ = [
    "test_download_report_with_browser_use_runs_async_form_preflight_and_agent_on_one_event_loop",
    "test_download_report_with_browser_use_preserves_configured_location_lookup_blocker",
    "test_download_report_with_browser_use_salvages_completed_history_when_agent_cleanup_stalls",
    "test_download_report_with_browser_use_recovers_lookup_before_completed_history_shutdown",
    "test_download_report_with_browser_use_bounds_lookup_assist_after_completed_history_timeout",
    "test_download_report_with_browser_use_maps_partial_lookup_timeout_to_blocker",
]
