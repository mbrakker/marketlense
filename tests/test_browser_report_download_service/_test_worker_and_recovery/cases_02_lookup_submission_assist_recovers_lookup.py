# ruff: noqa: F401,F403,F405
from __future__ import annotations

import asyncio

from src.contracts.browser_download import BrowserRoutePlaybook
from src.services._browser_report_download._browser_runtime import timeout_recovery
from src.services._browser_report_download._helpers.interaction import (
    browser_helper_form_autocomplete,
)

from ._shared import *  # noqa: F401,F403


def test_download_report_with_browser_use_lookup_submission_assist_recovers_lookup_blocked_submit(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = _settings(tmp_path)
    settings = replace(
        settings,
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                *settings.identity_profile.fields,
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="country",
                    label="Country",
                    value="Austria",
                    aliases=["location"],
                    option_aliases=["Republic of Austria"],
                ),
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
                        assert "option_aliases" in script_text
                        assert "Republic of Austria" in script_text
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
            settings=settings,
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


def test_lookup_submission_assist_sends_only_lookup_identity_fields(
    tmp_path: Path,
) -> None:
    settings = replace(
        _settings(tmp_path),
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="full_name",
                    label="Full name",
                    value="Example Person",
                    aliases=["name"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="company",
                    label="Company",
                    value="Marketlense",
                    aliases=["company"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="country",
                    label="Country",
                    value="Austria",
                    aliases=["location"],
                    option_aliases=["Republic of Austria"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="state_region",
                    label="State or region",
                    value="California",
                    aliases=["state", "province"],
                    option_aliases=["CA"],
                ),
            ],
        ),
    )

    values = timeout_recovery._browser_form_identity_field_values(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            route_family_hint="browser_email_form",
        )
    )

    assert [item["key"] for item in values] == ["country", "state_region"]
    assert values[0]["option_aliases"] == ["Republic of Austria"]
    assert values[1]["option_aliases"] == ["CA"]


def test_lookup_submission_assist_targets_blocked_lookup_label(
    tmp_path: Path,
) -> None:
    settings = replace(
        _settings(tmp_path),
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="country",
                    label="Country",
                    value="Austria",
                    aliases=["location"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="state_region",
                    label="State or region",
                    value="California",
                    aliases=["state", "province"],
                    option_aliases=["CA"],
                ),
            ],
        ),
    )
    lookup_labels = timeout_recovery._lookup_submission_assist_target_labels(
        {
            "encountered_form_fields": ["Business Email Address", "State"],
            "blocked_reason_detail": (
                "The State field did not resolve to a valid lookup selection."
            ),
        }
    )

    values = timeout_recovery._browser_form_identity_field_values(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            route_family_hint="browser_email_form",
        ),
        lookup_labels=lookup_labels,
    )

    assert lookup_labels == ("State",)
    assert [item["key"] for item in values] == ["state_region"]

    broad_values = timeout_recovery._browser_form_identity_field_values(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            route_family_hint="browser_email_form",
        ),
        lookup_labels=("Location",),
    )

    assert [item["key"] for item in broad_values] == ["country", "state_region"]


def test_lookup_submission_assist_never_invents_a_missing_identity_value(
    tmp_path: Path,
) -> None:
    settings = replace(
        _settings(tmp_path),
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="country",
                    label="Country",
                    value=None,
                    aliases=["location"],
                )
            ],
        ),
    )

    values = timeout_recovery._browser_form_identity_field_values(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            route_family_hint="browser_email_form",
        ),
        lookup_labels=("Country",),
    )

    assert values == []


def test_lookup_submission_assist_submits_access_resource_cta(
    run_context,
) -> None:
    class AccessResourcePage:
        def evaluate(self, script):
            assert "text.includes('access')" in str(script)
            return {
                "attempted_count": 1,
                "selected_count": 1,
                "selected_fields": ["Country"],
                "selection_verification": [],
                "unresolved_fields": [],
                "submitted": True,
                "final_url": "https://example.com/report#requested",
            }

    result = browser_helper_form_autocomplete(
        page=AccessResourcePage(),
        field_values=[
            {
                "key": "country",
                "label": "Country",
                "value": "Austria",
                "aliases": ["country"],
                "option_aliases": ["Austria"],
            }
        ],
        ctx=run_context,
        normalized_url="https://example.com/report",
        submit=True,
    )

    assert result.status == "ok"
    assert result.submitted is True


def test_download_report_with_browser_use_standard_form_assist_checks_mandatory_opt_in(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = replace(
        _settings(tmp_path, work_email="reports@example.test"),
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="first_name",
                    label="First name",
                    value="Example",
                    aliases=["first name", "firstname"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="last_name",
                    label="Last name",
                    value="Person",
                    aliases=["last name", "lastname"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="work_email",
                    label="Work email",
                    value="reports@example.test",
                    aliases=["email", "business email", "work email"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="company",
                    label="Company",
                    value="Market Lense",
                    aliases=["company", "organization"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="job_title",
                    label="Job title",
                    value="Researcher",
                    aliases=["job title", "title"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="country",
                    label="Country",
                    value="Austria",
                    aliases=["country"],
                    option_aliases=["Austria"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="industry",
                    label="Industry",
                    value="Research",
                    aliases=["industry"],
                    option_aliases=[],
                ),
            ],
        ),
    )
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Submitted the form, but it remained visible with required fields.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class RequiredControlsAgent(original_runtime):
        def run_sync(self, max_steps: int):
            browser = self.browser
            browser.url = "https://example.com/report#download"
            browser.title = "Example gated report"
            browser.html = "<html><body><iframe id='form'></iframe></body></html>"

            class RequiredControlsPage:
                def evaluate(self, script):
                    script_text = str(script or "")
                    if "standardFormSubmit" in script_text:
                        assert "reports@example.test" in script_text
                        assert "mandatoryAgreementCheckedCount" in script_text
                        browser.url = "https://example.com/report#requested"
                        browser.title = "Thank you"
                        browser.html = (
                            "<html><body>"
                            "Thank you for your interest. The report will be emailed "
                            "to you shortly."
                            "</body></html>"
                        )
                        return {
                            "attempted_count": 7,
                            "filled_count": 5,
                            "selected_count": 2,
                            "mandatory_agreement_checked_count": 1,
                            "submitted": True,
                            "final_url": browser.url,
                            "resolved_fields": [
                                "First name",
                                "Last name",
                                "Work email",
                                "Company",
                                "Job title",
                                "Country",
                                "Industry",
                                "Privacy agreement",
                            ],
                            "unresolved_fields": [],
                        }
                    if "navigationEntries" in script_text:
                        return []
                    if "document.querySelectorAll" in script_text:
                        return []
                    return []

            browser.current_page_factory = RequiredControlsPage
            payload = {
                "route_kind": "email_delivery",
                "route_summary": (
                    "Filled the form, clicked Submit, and validation required "
                    "Country, Industry, and the privacy agreement checkbox."
                ),
                "route_family": "browser_email_form",
                "resolved_target_url": "https://example.com/report#download",
                "final_page_url": "https://example.com/report#download",
                "email_submission_completed": False,
                "downloaded_file_path": None,
                "downloaded_file_name": None,
                "downloaded_mime_type": None,
                "encountered_form_fields": [
                    "First name",
                    "Last name",
                    "Business Email",
                    "Company",
                    "Job Title",
                    "Country",
                    "Industry",
                    "I have read, understand and agree to the Privacy Policy and Terms",
                ],
                "route_steps": [
                    {
                        "index": 1,
                        "action": "click",
                        "target_text": "Submit",
                        "target_role": "button",
                        "target_url": "https://example.com/report#download",
                        "result": "Submit was blocked because required controls remained empty.",
                    }
                ],
                "post_submit_message": None,
                "confirmation_url_changed": False,
                "submit_button_state": None,
                "form_disappeared": False,
                "blocked_reason": "blocked_unknown_required_enum",
                "blocked_reason_detail": (
                    "Country and Industry were not selected and the required "
                    "privacy terms agreement checkbox was unchecked."
                ),
                "final_page_title": "Example gated report",
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

            class RequiredControlsHistory:
                def final_result(self) -> str:
                    return json.dumps(payload)

                def action_results(self) -> list[Any]:
                    return []

            return RequiredControlsHistory()

    runtime.Agent = RequiredControlsAgent
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
            delivery_email="reports@example.test",
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.route_status == "verified"
    assert response.final_page_url == "https://example.com/report#requested"
    assert response.confirmation_evidence is not None
    assert "report will be emailed" in (
        response.confirmation_evidence.visible_confirmation_text.casefold()
    )


def test_download_report_with_browser_use_standard_form_assist_runs_after_lookup_only_progress(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = replace(
        _settings(tmp_path, work_email="reports@example.test"),
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="first_name",
                    label="First name",
                    value="Example",
                    aliases=["first name"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="last_name",
                    label="Last name",
                    value="Person",
                    aliases=["last name"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="work_email",
                    label="Work email",
                    value="reports@example.test",
                    aliases=["email", "business email"],
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
                    key="country",
                    label="Country",
                    value="Austria",
                    aliases=["country", "location"],
                    option_aliases=["Austria"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="industry",
                    label="Industry",
                    value="Research",
                    aliases=["industry"],
                ),
            ],
        ),
    )
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Submitted the form, but required controls remained.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent
    helper_calls: list[str] = []

    class LookupOnlyThenStandardFormAgent(original_runtime):
        def run_sync(self, max_steps: int):
            browser = self.browser
            browser.url = "https://example.com/report#download"
            browser.title = "Example gated report"
            browser.html = (
                "<html><body><form><input name='email' />"
                "<input type='checkbox' name='privacy' required />"
                "<button type='submit'>Submit</button></form></body></html>"
            )

            class LookupOnlyThenStandardFormPage:
                def evaluate(self, script):
                    script_text = str(script or "")
                    if (
                        "selected_count" in script_text
                        and ".lookupFormFieldBlock" in script_text
                    ):
                        helper_calls.append("lookup")
                        return {
                            "acted": True,
                            "selected_count": 1,
                            "submitted": False,
                            "final_url": browser.url,
                        }
                    if "standardFormSubmit" in script_text:
                        helper_calls.append("standard")
                        browser.url = "https://example.com/report#requested"
                        browser.title = "Thank you"
                        browser.html = (
                            "<html><body>Thank you. The report will be emailed "
                            "to your inbox shortly.</body></html>"
                        )
                        return {
                            "attempted_count": 6,
                            "filled_count": 4,
                            "selected_count": 2,
                            "mandatory_agreement_checked_count": 1,
                            "submitted": True,
                            "final_url": browser.url,
                            "resolved_fields": [
                                "First name",
                                "Last name",
                                "Work email",
                                "Company",
                                "Country",
                                "Industry",
                                "Privacy agreement",
                            ],
                            "unresolved_fields": [],
                        }
                    if "navigationEntries" in script_text:
                        return []
                    if "document.querySelectorAll" in script_text:
                        return []
                    return []

            browser.current_page_factory = LookupOnlyThenStandardFormPage
            payload = {
                "route_kind": "email_delivery",
                "route_summary": (
                    "Filled the form, selected Austria in Location, clicked Submit, "
                    "and remained blocked by required Industry and privacy agreement controls."
                ),
                "route_family": "browser_email_form",
                "resolved_target_url": "https://example.com/report#download",
                "final_page_url": "https://example.com/report#download",
                "email_submission_completed": False,
                "downloaded_file_path": None,
                "downloaded_file_name": None,
                "downloaded_mime_type": None,
                "encountered_form_fields": [
                    "First name",
                    "Last name",
                    "Business Email",
                    "Company",
                    "Location",
                    "Industry",
                    "Privacy agreement",
                ],
                "route_steps": [
                    {
                        "index": 1,
                        "action": "input",
                        "target_text": "Austria",
                        "target_role": "textbox",
                        "target_url": "https://example.com/report#download",
                        "result": "Resolved the Location lookup.",
                    },
                    {
                        "index": 2,
                        "action": "click",
                        "target_text": "Submit",
                        "target_role": "button",
                        "target_url": "https://example.com/report#download",
                        "result": "Submit stayed blocked by other required controls.",
                    },
                ],
                "post_submit_message": None,
                "confirmation_url_changed": False,
                "submit_button_state": None,
                "form_disappeared": False,
                "blocked_reason": "blocked_unknown_required_enum",
                "blocked_reason_detail": (
                    "Industry remained unselected and the privacy agreement checkbox was unchecked."
                ),
                "final_page_title": "Example gated report",
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

            class LookupOnlyThenStandardFormHistory:
                def final_result(self) -> str:
                    return json.dumps(payload)

                def action_results(self) -> list[Any]:
                    return []

            return LookupOnlyThenStandardFormHistory()

    runtime.Agent = LookupOnlyThenStandardFormAgent
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
            delivery_email="reports@example.test",
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.route_status == "verified"
    assert response.final_page_url == "https://example.com/report#requested"
    assert helper_calls == ["lookup", "standard"]


def test_download_report_with_browser_use_timeout_standard_form_assist_submits_open_form(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = replace(
        _settings(tmp_path, work_email="reports@example.test"),
        # Keep the main agent below its two-second simulated stall while
        # leaving enough bounded time for the terminal confirmation recovery.
        timeout_seconds=0.5,
        max_steps=1,
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="work_email",
                    label="Work email",
                    value="reports@example.test",
                    aliases=["email", "business email", "work email"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="country",
                    label="Country",
                    value="Austria",
                    aliases=["country"],
                    option_aliases=["Austria"],
                ),
            ],
        ),
    )
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class TimedOutOpenFormAgent(original_runtime):
        def run_sync(self, max_steps: int):
            browser = self.browser
            browser.url = "https://example.com/report#download"
            browser.title = "Example gated report"
            browser.html = (
                "<html><body><form><input name='email' value='reports@example.test'>"
                "<select name='country'><option>Austria</option></select>"
                "<input type='checkbox' name='privacy'>"
                "<button type='submit'>Submit</button></form></body></html>"
            )

            class OpenFormPage:
                def evaluate(self, script):
                    script_text = str(script or "")
                    if "standardFormSubmit" in script_text:
                        browser.url = "https://example.com/report#requested"
                        browser.title = "Thank you"
                        browser.html = (
                            "<html><body>Thank you. The report will be emailed "
                            "to you shortly.</body></html>"
                        )
                        return {
                            "__marketlense_js_helper": True,
                            "ok": True,
                            "result": {
                                "attempted_count": 1,
                                "filled_count": 0,
                                "selected_count": 0,
                                "mandatory_agreement_checked_count": 1,
                                "resolved_control_count": 3,
                                "submitted": True,
                                "final_url": browser.url,
                                "resolved_fields": [
                                    "Work email",
                                    "Country",
                                    "Privacy agreement",
                                ],
                                "unresolved_fields": [],
                            },
                            "result_type": "object",
                        }
                    if "navigationEntries" in script_text:
                        return []
                    if "document.querySelectorAll" in script_text:
                        return []
                    return []

                def content(self):
                    return browser.html

                def title(self):
                    return browser.title

            browser.current_page_factory = OpenFormPage
            time.sleep(2.0)
            return super().run_sync(max_steps)

    runtime.Agent = TimedOutOpenFormAgent
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
            delivery_email="reports@example.test",
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.route_status == "verified"
    assert response.confirmation_evidence is not None
    assert "report will be emailed" in (
        response.confirmation_evidence.visible_confirmation_text.casefold()
    )


__all__ = [
    "test_lookup_submission_assist_never_invents_a_missing_identity_value",
    "test_download_report_with_browser_use_lookup_submission_assist_recovers_lookup_blocked_submit",
    "test_download_report_with_browser_use_standard_form_assist_checks_mandatory_opt_in",
    "test_download_report_with_browser_use_standard_form_assist_runs_after_lookup_only_progress",
    "test_download_report_with_browser_use_timeout_standard_form_assist_submits_open_form",
]
