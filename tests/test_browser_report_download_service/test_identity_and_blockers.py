from __future__ import annotations

import asyncio

from src.services._browser_report_download._browser_runtime._session_lifecycle.history import (
    _run_agent_history_async_with_timeout,
)
from src.services._browser_report_download._artifact.classification import (
    _normalize_explicit_blocked_reason,
)

from .builders import *  # noqa: F401,F403


def test_async_agent_no_progress_returns_without_waiting_for_agent_cleanup(
    tmp_path: Path,
    run_context,
) -> None:
    class PartialHistory:
        def final_result(self) -> str:
            return ""

        def is_done(self) -> bool:
            return False

    class Detector:
        should_stop = False
        observation = SimpleNamespace(url="https://example.com/not-found")

    detector = Detector()

    class Agent:
        history = PartialHistory()

        def stop(self) -> None:
            return None

        async def run(self, *, max_steps: int) -> PartialHistory:
            detector.should_stop = True
            await asyncio.Event().wait()
            return self.history

    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
    )

    async def execute():
        return await _run_agent_history_async_with_timeout(
            agent=Agent(),
            browser=SimpleNamespace(),
            request=request,
            ctx=run_context,
            normalized_url=request.url,
            no_progress_detector=detector,
        )

    result = asyncio.run(asyncio.wait_for(execute(), timeout=0.5))

    assert result.no_progress_observation is detector.observation
    assert result.salvaged_completed_history is True


def test_download_report_with_browser_use_stops_after_three_equivalent_turns(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report landing page.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent
    original_browser = runtime.Browser

    class BrowserWithoutTerminalCapture(original_browser):
        def get_current_page(self):
            raise AssertionError(
                "no-progress completion must not re-enter terminal browser capture"
            )

    runtime.Browser = BrowserWithoutTerminalCapture

    class EquivalentTurnHistory:
        def final_result(self) -> str:
            return ""

        def action_results(self) -> list[Any]:
            return []

    class EquivalentTurnAgent(original_runtime):
        def __init__(
            self,
            *,
            task: str,
            llm: Any,
            browser: Any,
            output_model_schema: Any,
            register_new_step_callback: Any,
            register_should_stop_callback: Any,
            use_judge: bool = False,
            calculate_cost: bool = False,
        ) -> None:
            super().__init__(
                task=task,
                llm=llm,
                browser=browser,
                output_model_schema=output_model_schema,
                use_judge=use_judge,
                calculate_cost=calculate_cost,
            )
            self.register_new_step_callback = register_new_step_callback
            self.register_should_stop_callback = register_should_stop_callback
            self.turn_count = 0

        def run_sync(self, max_steps: int):
            state = SimpleNamespace(
                url="https://example.com/report",
                dom_state=SimpleNamespace(
                    selector_map={"1": object()},
                    llm_representation=lambda: "<button>Download report</button>",
                ),
                pending_network_requests=[],
                recent_events="",
            )
            output = SimpleNamespace(
                current_state=SimpleNamespace(
                    memory="", evaluation_previous_goal="", next_goal=""
                )
            )
            for step_number in range(1, max_steps + 1):
                self.turn_count += 1
                self.register_new_step_callback(state, output, step_number)
                if asyncio.run(self.register_should_stop_callback()):
                    break
            self.history = EquivalentTurnHistory()
            return self.history

    runtime.Agent = EquivalentTurnAgent
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
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.outcome == "email_required"
    assert response.route_family == "browser_pdf_click"
    assert response.blocked_reason == "blocked_no_progress"
    assert "blocked_no_progress" in response.terminal_evidence.evidence_labels
    events = _service_events(caplog)
    no_progress_event = next(
        event
        for event in events
        if event["event"] == "browser_report_download_no_progress_stopped"
    )
    assert no_progress_event["fields"]["consecutive_equivalent_turns"] == 3


def test_download_report_with_browser_use_keeps_success_after_document_progress(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page and download the report.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class DocumentProgressAgent(original_runtime):
        def __init__(
            self,
            *,
            task: str,
            llm: Any,
            browser: Any,
            output_model_schema: Any,
            register_new_step_callback: Any,
            register_should_stop_callback: Any,
            use_judge: bool = False,
            calculate_cost: bool = False,
        ) -> None:
            super().__init__(
                task=task,
                llm=llm,
                browser=browser,
                output_model_schema=output_model_schema,
                use_judge=use_judge,
                calculate_cost=calculate_cost,
            )
            self.register_new_step_callback = register_new_step_callback
            self.register_should_stop_callback = register_should_stop_callback

        def run_sync(self, max_steps: int):
            output = SimpleNamespace(
                current_state=SimpleNamespace(
                    memory="", evaluation_previous_goal="", next_goal=""
                )
            )
            for step_number, dom in enumerate(
                (
                    "<button>Download report</button>",
                    "<button>Download report</button>",
                    "<a href='/report.pdf'>Download report</a>",
                ),
                start=1,
            ):
                state = SimpleNamespace(
                    url="https://example.com/report",
                    dom_state=SimpleNamespace(
                        selector_map={"1": object()},
                        llm_representation=lambda dom=dom: dom,
                    ),
                    pending_network_requests=[],
                    recent_events="",
                )
                self.register_new_step_callback(state, output, step_number)
                assert asyncio.run(self.register_should_stop_callback()) is False
            return super().run_sync(max_steps)

    runtime.Agent = DocumentProgressAgent
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
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert response.blocked_reason is None
    assert not any(
        event["event"] == "browser_report_download_no_progress_stopped"
        for event in _service_events(caplog)
    )


def test_download_report_with_browser_use_maps_company_name_and_professional_email_without_false_blocker(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the form and submitted it successfully.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class AliasAwareAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["post_submit_message"] = "Thank you for submitting the form."
            payload["encountered_form_fields"] = [
                "First Name",
                "Last Name",
                "Company Name",
                "Professional Email",
                "Business Phone",
                "Country",
            ]

            class AliasAwareHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return AliasAwareHistory()

    runtime.Agent = AliasAwareAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/gated-report",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.blocked_reason is None


def test_resolve_effective_identity_fields_hydrates_semantic_alias_values(
    tmp_path: Path,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/form",
        settings=BrowserDownloadSettings(
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
                        aliases=["email", "business email"],
                    ),
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="company",
                        label="Company",
                        value="Market Lense",
                        aliases=["organization"],
                    ),
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="professional_email",
                        label="Professional Email",
                        value=None,
                        aliases=[],
                    ),
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="company_name",
                        label="Company Name",
                        value=None,
                        aliases=[],
                    ),
                ],
            ),
            headed=False,
        ),
    )

    effective = resolve_effective_identity_fields(request)
    by_key = {field.key: field for field in effective}

    assert by_key["professional_email"].value == "ops@example.com"
    assert by_key["company_name"].value == "Market Lense"


def test_explicit_missing_identity_blocker_is_evidence_based(
    tmp_path: Path,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://www.algolia.com/lp/algolia-forrester-tei-report-2026",
        settings=replace(
            _settings(tmp_path),
            identity_profile=BrowserDownloadIdentity(
                schema_version="1.0",
                fields=[
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="first_name",
                        label="First Name",
                        value="Market",
                        aliases=["first name", "given name"],
                    ),
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="last_name",
                        label="Last Name",
                        value="Lense",
                        aliases=["last name", "family name"],
                    ),
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="work_email",
                        label="Work email",
                        value="ops@example.com",
                        aliases=["email", "business email"],
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
                        key="country",
                        label="Country",
                        value="Austria",
                        aliases=["country"],
                    ),
                ],
            ),
        ),
    )

    blocked_reason = _normalize_explicit_blocked_reason(
        request=request,
        delivery_email="ops@example.com",
        explicit_blocked_reason="blocked_missing_identity_field",
        encountered_form_fields=[
            "First Name",
            "Last Name",
            "Business Email Address",
            "Company Name",
            "Country",
        ],
        blocker_haystack="The form requires these identity fields before submission.",
    )

    assert blocked_reason is None
    assert (
        _normalize_explicit_blocked_reason(
            request=request,
            delivery_email="ops@example.com",
            explicit_blocked_reason="blocked_missing_identity_field",
            encountered_form_fields=["Phone"],
            blocker_haystack=(
                "The form requires this identity field before submission."
            ),
        )
        == "blocked_missing_identity_field"
    )


def test_prompt_identity_entries_apply_delivery_email_to_email_aliases(
    tmp_path: Path,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/form",
        settings=BrowserDownloadSettings(
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
                        value="stale@example.com",
                        aliases=["email", "business email"],
                    ),
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="business_email_address",
                        label="Business Email Address",
                        value=None,
                        aliases=[],
                    ),
                ],
            ),
            headed=False,
        ),
        delivery_email="reports@marketbearing.eu",
    )

    entries = prompt_runtime._build_identity_entries(
        request=request,
        delivery_email="reports@marketbearing.eu",
    )

    by_label = {entry["label"]: entry for entry in entries}
    assert by_label["Work email"]["value"] == "reports@marketbearing.eu"
    assert by_label["Business Email Address"]["value"] == "reports@marketbearing.eu"
    assert "stale@example.com" not in json.dumps(entries)


def test_resolve_effective_identity_fields_applies_publisher_override_values(
    tmp_path: Path,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
        settings=BrowserDownloadSettings(
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
                        key="online_annual_revenue",
                        label="Online Annual Revenue",
                        value=None,
                        aliases=["projected annual revenue"],
                    ),
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="country",
                        label="Country",
                        value="Austria",
                        aliases=["country"],
                    ),
                ],
                publisher_overrides=[
                    BrowserDownloadPublisherOverride(
                        schema_version="1.0",
                        host_pattern="bigcommerce.com",
                        field_values=[
                            BrowserDownloadIdentityField(
                                schema_version="1.0",
                                key="company",
                                label="Company",
                                value="Market Bearing",
                                aliases=[
                                    "company",
                                    "organization",
                                    "business",
                                    "employer",
                                ],
                            ),
                            BrowserDownloadIdentityField(
                                schema_version="1.0",
                                key="online_annual_revenue",
                                label="Online Annual Revenue",
                                value="Less than $250k",
                                aliases=[
                                    "projected annual revenue",
                                    "projected annual online revenue",
                                ],
                            ),
                        ],
                    )
                ],
            ),
            headed=False,
        ),
    )

    effective = resolve_effective_identity_fields(request)
    by_key = {field.key: field for field in effective}

    assert by_key["online_annual_revenue"].value == "Less than $250k"
    assert by_key["country"].value == "Austria"
    assert by_key["company"].value == "Market Bearing"


def test_download_report_with_browser_use_salvages_partial_business_email_blocker(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    settings = replace(_settings(tmp_path), timeout_seconds=0.05, max_steps=1)
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Clicked Download and reached a form.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class PartialEmailBlockerHistory:
        def __init__(self) -> None:
            self.history = [
                SimpleNamespace(
                    model_output=SimpleNamespace(
                        current_state=SimpleNamespace(
                            memory=(
                                "Filled first name, last name, company, and business email. "
                                "The form has an email error and requires a business email."
                            ),
                            evaluation_previous_goal=(
                                "Submission failed because the configured email is not "
                                "accepted as a professional email."
                            ),
                            next_goal=(
                                "Do not retry the same email; classify the flow as blocked."
                            ),
                        ),
                        action=[
                            {
                                "click": {
                                    "index": 50,
                                    "target": "Download report",
                                }
                            }
                        ],
                    ),
                    result=[
                        SimpleNamespace(
                            error="Email error: please use a business email address.",
                            long_term_memory="",
                            extracted_content="",
                        )
                    ],
                    state=SimpleNamespace(
                        url="https://example.com/report#download",
                        title="Example ROI report",
                        screenshot_path="",
                    ),
                )
            ]

        def is_done(self) -> bool:
            return False

        def final_result(self) -> str:
            return ""

        def action_results(self) -> list[Any]:
            return []

    class BusinessEmailBlockedAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.history = PartialEmailBlockerHistory()
            self.browser.url = "https://example.com/report#download"
            self.browser.title = "Example ROI report"
            self.browser.html = "<html><body>Business email required</body></html>"
            time.sleep(2.0)
            return self.history

    runtime.Agent = BusinessEmailBlockedAgent
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
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_email_domain"
    assert response.blocked_reason_detail
    assert "business" in response.blocked_reason_detail.casefold()
    events = _service_events(caplog)
    assert any(
        event.get("event") == "browser_report_download_partial_email_blocker_observed"
        for event in events
    )
    assert not any(
        event.get("event")
        == "browser_report_download_timeout_salvaged_partial_history_blocker"
        for event in events
    )
