from __future__ import annotations

from src.services._browser_report_download._artifact.classification import (
    _normalize_explicit_blocked_reason,
)

from .builders import *  # noqa: F401,F403


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
