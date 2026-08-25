# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_browser_route_playbooks.py"
)

from ._shared import *  # noqa: F401,F403


def test_validated_route_promotion_returns_not_promotable_for_partial_route(
    tmp_path: Path,
    run_context,
) -> None:
    result = replace(
        _result(route_status="verified"),
        execution_route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="submit",
                target_text="Submit",
                target_role="button",
                target_url="https://example.com/research/report",
                result="Submission was not verified.",
                expected_evidence=["confirmation_text"],
                observed_evidence=[],
                verification_status="missing",
            ),
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=1,
                action="submit",
                target_text="Access The Resource",
                target_role="button",
                target_url="https://example.com/research/report",
                result="Confirmed report email request.",
                expected_evidence=["confirmation_text"],
                observed_evidence=["confirmation_text"],
                verification_status="verified",
                locator_role="button",
                locator_name="Access The Resource",
            ),
        ],
    )

    response = promote_validated_browser_route_result_to_playbook(
        playbook_dir=str(tmp_path / "playbooks"),
        result=result,
        ctx=run_context,
        observed_at="2026-08-11T18:50:18+00:00",
    )
    assert response.status == "not_promotable"
    assert response.reason == "step_0_verification_status_unverified"
    assert response.path == ""
    assert not (tmp_path / "playbooks").exists()


def test_validated_route_promotion_round_trips_complete_semantic_route_and_identity_references(
    tmp_path: Path,
    run_context,
) -> None:
    result = replace(
        _result(route_status="verified"),
        execution_route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="click",
                target_text="Download report",
                target_role="button",
                target_url="https://example.com/research/report",
                result="Opened the download route.",
                expected_evidence=["page_info"],
                observed_evidence=["page_info"],
                verification_status="verified",
                locator_role="button",
                locator_name="Download report",
                locator_data_attribute="data-testid=download-report",
                locator_css=".download-report",
                expected_url_contains="/download",
                locator_evidence=["locator:role:button:Download report"],
                postcondition_evidence=["url:/download"],
            ),
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=1,
                action="fill",
                target_text="Work email",
                target_role="textbox",
                target_url="https://example.com/research/report",
                result="Filled the configured work email field.",
                expected_evidence=["page_info"],
                observed_evidence=["page_info"],
                verification_status="verified",
                locator_label="Work email",
                identity_field_reference="identity.delivery_email",
                expected_text="Request received",
                locator_evidence=["locator:label:Work email"],
                postcondition_evidence=["text:Request received"],
            ),
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=2,
                action="click",
                target_text="Submit",
                target_role="button",
                target_url="https://example.com/research/report",
                result="Submission confirmed.",
                expected_evidence=["confirmation_text"],
                observed_evidence=["confirmation_text"],
                verification_status="verified",
                locator_role="button",
                locator_name="Submit",
                expected_text="Request received",
                locator_evidence=["locator:role:button:Submit"],
                postcondition_evidence=["text:Request received"],
            ),
        ],
    )

    response = promote_validated_browser_route_result_to_playbook(
        playbook_dir=str(tmp_path / "playbooks"),
        result=result,
        ctx=run_context,
        observed_at="2026-08-16T12:00:00+00:00",
    )
    loaded = load_browser_route_playbooks(
        playbook_dir=str(tmp_path / "playbooks"), ctx=run_context
    )[0]
    payload = yaml.safe_load(Path(response.path).read_text(encoding="utf-8"))

    assert [step["action"] for step in payload["steps"]] == ["click", "fill", "click"]
    assert payload["steps"][0]["selector_type"] == "role"
    assert payload["steps"][0]["selector"] == "button:Download report"
    assert payload["steps"][0]["expected_url_contains"] == "/download"
    assert payload["steps"][0]["verification"] == "Opened the download route."
    assert payload["steps"][1]["selector_type"] == "label"
    assert payload["steps"][1]["selector"] == "Work email"
    assert payload["steps"][1]["value_reference"] == "${identity.delivery_email}"
    assert "@" not in payload["steps"][1]["value_reference"]
    assert payload["steps"][1]["expected_text"] == "Request received"
    assert loaded.steps[0].selector_type == "role"
    assert loaded.steps[1].value_reference == "${identity.delivery_email}"


def test_validated_route_promotion_dry_run_returns_review_diff_without_write(
    tmp_path: Path,
    run_context,
) -> None:
    playbook_dir = tmp_path / "playbooks"

    response = promote_validated_browser_route_result_to_playbook(
        playbook_dir=str(playbook_dir),
        result=_result(route_status="verified"),
        ctx=run_context,
        observed_at="2026-05-06T12:00:00+00:00",
        write_file=False,
    )

    assert response.status == "dry_run_created"
    assert response.path == str(playbook_dir.resolve() / f"{response.playbook_id}.yaml")
    assert "validated_route_promotion" in response.review_diff
    assert not Path(response.path).exists()


def test_private_api_promotion_writes_dedicated_playbook_and_requires_repeated_success(
    tmp_path: Path,
    run_context,
) -> None:
    request = BrowserRoutePrivateApiPromotionRequest(
        schema_version="1.0",
        playbook_dir=str(tmp_path / "playbooks"),
        source_url="https://example.com/research/report-2026",
        route_family="browser_pdf_click",
        route_kind="pdf_download",
        endpoint_pattern="/api/reports/{last_path_segment}",
        method="GET",
        request_shape_summary="GET with report slug path parameter; no auth headers.",
        response_pdf_url_json_pointer="/asset/pdfUrl",
        validated_success_count=2,
        fallback_route_family="browser_pdf_click",
        required_response_markers=["pdfUrl"],
        evidence_labels=["network_document_request"],
        observed_at="2026-05-06T12:00:00+00:00",
    )

    response = promote_private_api_evidence_to_browser_playbook(
        request=request,
        ctx=run_context,
    )
    payload = yaml.safe_load(Path(response.path).read_text(encoding="utf-8"))
    loaded = load_browser_route_playbooks(
        playbook_dir=str(tmp_path / "playbooks"),
        ctx=run_context,
    )

    assert Path(response.path).parent.name == "private_api"
    assert response.playbook_id == "private-api-example-com-pdf-download"
    assert payload["private_api_evidence"][0]["success_count"] == 2
    assert payload["private_api_evidence"][0]["request_shape_summary"] == (
        "GET with report slug path parameter; no auth headers."
    )
    assert loaded[0].private_api_evidence[0].response_pdf_url_json_pointer == (
        "/asset/pdfUrl"
    )

    with pytest.raises(AppError) as excinfo:
        promote_private_api_evidence_to_browser_playbook(
            request=BrowserRoutePrivateApiPromotionRequest(
                schema_version="1.0",
                playbook_dir=str(tmp_path / "playbooks"),
                source_url="https://example.com/research/report-2026",
                route_family="browser_pdf_click",
                route_kind="pdf_download",
                endpoint_pattern="/api/reports/{last_path_segment}",
                method="GET",
                request_shape_summary="GET with report slug path parameter.",
                response_pdf_url_json_pointer="/asset/pdfUrl",
                validated_success_count=1,
                fallback_route_family="browser_pdf_click",
            ),
            ctx=run_context,
        )
    assert excinfo.value.code == (
        "browser_route_private_api_promotion_insufficient_evidence"
    )
    assert excinfo.value.retryable is False


def test_private_api_promotion_rejects_missing_markers_and_cross_host_endpoint(
    tmp_path: Path,
    run_context,
) -> None:
    with pytest.raises(AppError) as missing_markers:
        promote_private_api_evidence_to_browser_playbook(
            request=BrowserRoutePrivateApiPromotionRequest(
                schema_version="1.0",
                playbook_dir=str(tmp_path / "playbooks"),
                source_url="https://example.com/research/report-2026",
                route_family="browser_pdf_click",
                route_kind="pdf_download",
                endpoint_pattern="/api/reports/{last_path_segment}",
                method="GET",
                request_shape_summary="GET with report slug path parameter.",
                response_pdf_url_json_pointer="/asset/pdfUrl",
                validated_success_count=2,
                fallback_route_family="browser_pdf_click",
                evidence_labels=["network_document_request"],
            ),
            ctx=run_context,
        )
    assert missing_markers.value.code == (
        "browser_route_private_api_promotion_markers_missing"
    )

    with pytest.raises(AppError) as host_mismatch:
        promote_private_api_evidence_to_browser_playbook(
            request=BrowserRoutePrivateApiPromotionRequest(
                schema_version="1.0",
                playbook_dir=str(tmp_path / "playbooks"),
                source_url="https://example.com/research/report-2026",
                route_family="browser_pdf_click",
                route_kind="pdf_download",
                endpoint_pattern="https://other.example/api/reports/report-2026",
                method="GET",
                request_shape_summary="GET with report slug path parameter.",
                response_pdf_url_json_pointer="/asset/pdfUrl",
                validated_success_count=2,
                fallback_route_family="browser_pdf_click",
                required_response_markers=["pdfUrl"],
                evidence_labels=["network_document_request"],
            ),
            ctx=run_context,
        )
    assert host_mismatch.value.code == (
        "browser_route_private_api_promotion_host_mismatch"
    )


def test_deterministic_route_playbook_executor_runs_selectors_and_reports_drift(
    run_context,
) -> None:
    playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="local-deterministic",
        version="1.0.0",
        status="active",
        updated_at="2026-05-06T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="example.com",
        host_patterns=["example.com"],
        url_path_markers=["report"],
        route_family="browser_pdf_click",
        route_kind="pdf_download",
        summary="Open page and click download.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="open",
                target="https://example.com/report",
                verification="page loaded",
                selector_type="url",
                selector="https://example.com/report",
                expected_url_contains="/report",
            ),
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="click",
                target="Download report",
                verification="PDF link visible",
                selector_type="css",
                selector="a.download",
                expected_text="PDF ready",
            ),
        ],
    )
    driver = _FakePageDriver(texts={"PDF ready"})

    response = execute_browser_route_playbook(
        BrowserRoutePlaybookExecutionRequest(
            schema_version="1.0",
            playbook=playbook,
            normalized_url="https://example.com/report",
            page_driver=driver,
        ),
        run_context,
    )

    assert response.status == "completed"
    assert [call[0] for call in driver.calls] == ["open", "click_css"]

    drift_response = execute_browser_route_playbook(
        BrowserRoutePlaybookExecutionRequest(
            schema_version="1.0",
            playbook=playbook,
            normalized_url="https://example.com/report",
            page_driver=_FakePageDriver(texts=set()),
        ),
        run_context,
    )
    assert drift_response.status == "drifted"
    assert drift_response.drift_reasons == ["expected_text_not_observed"]


def test_deterministic_route_playbook_executor_resolves_semantic_locators_and_identity_reference(
    run_context,
) -> None:
    playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="local-semantic",
        version="1.0.0",
        status="active",
        updated_at="2026-08-16T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="example.com",
        host_patterns=["example.com"],
        url_path_markers=["report"],
        route_family="browser_email_form",
        route_kind="email_delivery",
        summary="Use the verified form route.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="click",
                target="Request report",
                verification="opened form",
                selector_type="role",
                selector="button:Request report",
                expected_text="Form ready",
            ),
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="fill",
                target="Work email",
                verification="field filled",
                selector_type="label",
                selector="Work email",
                value_reference="${identity.delivery_email}",
                expected_text="Form ready",
            ),
        ],
    )
    driver = _FakePageDriver(texts={"Form ready"})

    response = execute_browser_route_playbook(
        BrowserRoutePlaybookExecutionRequest(
            schema_version="1.0",
            playbook=playbook,
            normalized_url="https://example.com/report",
            page_driver=driver,
            identity_values={"delivery_email": "configured-email"},
        ),
        run_context,
    )

    assert response.status == "completed"
    assert driver.calls == [
        ("click_role", "button", "Request report"),
        ("fill_label", "Work email", "configured-email"),
    ]


def test_deterministic_route_playbook_executor_skips_missing_postcondition(
    run_context,
) -> None:
    playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="local-incomplete",
        version="1.0.0",
        status="active",
        updated_at="2026-08-16T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="example.com",
        host_patterns=["example.com"],
        url_path_markers=["report"],
        route_family="browser_pdf_click",
        route_kind="pdf_download",
        summary="Click the download control.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="click",
                target="Download report",
                verification="PDF link visible",
                selector_type="css",
                selector="a.download",
            )
        ],
    )

    response = execute_browser_route_playbook(
        BrowserRoutePlaybookExecutionRequest(
            schema_version="1.0",
            playbook=playbook,
            normalized_url="https://example.com/report",
            page_driver=_FakePageDriver(texts=set()),
        ),
        run_context,
    )

    assert response.status == "skipped"
    assert response.drift_reasons == ["step_0_missing_deterministic_postcondition"]


def test_deterministic_route_playbook_executor_rejects_raw_identity_value(
    run_context,
) -> None:
    playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="local-raw-identity",
        version="1.0.0",
        status="active",
        updated_at="2026-08-20T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="example.com",
        host_patterns=["example.com"],
        url_path_markers=["report"],
        route_family="browser_email_form",
        route_kind="email_delivery",
        summary="Use the verified form route.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="fill",
                target="Work email",
                verification="field filled",
                selector_type="name",
                selector="email",
                value="ops@example.com",
                expected_text="Form ready",
            )
        ],
    )

    response = execute_browser_route_playbook(
        BrowserRoutePlaybookExecutionRequest(
            schema_version="1.0",
            playbook=playbook,
            normalized_url="https://example.com/report",
            page_driver=_FakePageDriver(texts={"Form ready"}),
        ),
        run_context,
    )

    assert response.status == "skipped"
    assert response.drift_reasons == ["step_0_identity_reference_invalid"]


def test_runtime_role_form_evidence_promotes_and_executes_async(
    tmp_path: Path,
    run_context,
) -> None:
    history = SimpleNamespace(
        history=[
            _runtime_history_entry(
                action={"input": {"index": 1, "text": "ops@example.com"}},
                role="textbox",
                name="Work email",
                url="https://example.com/request",
                title="Request form",
                node_name="input",
                attributes={"role": "textbox", "type": "email"},
            ),
            _runtime_history_entry(
                action={"select_dropdown": {"index": 2, "text": "Retail"}},
                role="combobox",
                name="Industry",
                url="https://example.com/request",
                title="Choose industry",
                node_name="select",
                attributes={"role": "combobox"},
            ),
            _runtime_history_entry(
                action={"click": {"index": 3}},
                role="button",
                name="Request report",
                url="https://example.com/request",
                title="Request form",
                node_name="button",
                attributes={"role": "button", "type": "submit"},
            ),
        ]
    )
    execution_steps = capture_browser_execution_route_steps(
        history=history,
        final_page_url="https://example.com/requested",
        final_page_title="Request confirmed",
        identity_value_references={
            "ops@example.com": "identity.delivery_email",
            "Retail": "identity.industry",
        },
    )
    result = replace(
        _result(route_status="verified"),
        route_kind="email_delivery",
        route_family="browser_email_form",
        outcome="email_requested",
        execution_route_steps=execution_steps,
    )

    promotion = promote_validated_browser_route_result_to_playbook(
        playbook_dir=str(tmp_path / "playbooks"),
        result=result,
        ctx=run_context,
        observed_at="2026-08-20T12:00:00+00:00",
    )
    playbook = load_browser_route_playbooks(
        playbook_dir=str(tmp_path / "playbooks"), ctx=run_context
    )[0]
    driver = _AsyncRoleFormPageDriver(
        texts={"Choose industry", "Request form", "Request confirmed"}
    )

    response = asyncio.run(
        execute_browser_route_playbook_async(
            BrowserRoutePlaybookExecutionRequest(
                schema_version="1.0",
                playbook=playbook,
                normalized_url="https://example.com/request",
                page_driver=driver,
                identity_values={
                    "delivery_email": "ops@example.com",
                    "industry": "Retail",
                },
            ),
            run_context,
        )
    )

    assert promotion.status == "created"
    assert [step.selector for step in playbook.steps] == [
        "textbox:Work email",
        "combobox:Industry",
        "button:Request report",
    ]
    assert [step.value_reference for step in playbook.steps[:2]] == [
        "${identity.delivery_email}",
        "${identity.industry}",
    ]
    assert response.status == "completed"
    assert driver.calls == [
        ("fill_role", "textbox", "Work email", "ops@example.com"),
        ("select_role", "combobox", "Industry", "Retail"),
        ("click_role", "button", "Request report"),
    ]


def test_async_deterministic_submit_waits_for_the_page_driver_to_settle(
    run_context,
) -> None:
    """A client-side form response must settle before submit verification runs."""

    class SubmitDriver:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def click_css(self, _selector: str) -> str:
            self.calls.append("click")
            return "clicked"

        async def wait_for_post_submit(self) -> None:
            self.calls.append("settle")

        async def current_url(self) -> str:
            self.calls.append("current_url")
            return "https://example.com/request"

        async def contains_text(self, _text: str) -> bool:
            return True

    playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="async-submit-settlement",
        version="1.0.0",
        status="active",
        updated_at="2026-08-23T00:00:00+00:00",
        stale_after_days=120,
        publisher_pattern="example.com",
        host_patterns=["example.com"],
        url_path_markers=["request"],
        route_family="browser_email_form",
        route_kind="email_delivery",
        summary="Submit a client-side report request form.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="submit",
                target="Request report",
                verification="The request page remains available after submission.",
                selector_type="css",
                selector="button[type=submit]",
                expected_url_contains="/request",
            )
        ],
    )
    driver = SubmitDriver()

    response = asyncio.run(
        execute_browser_route_playbook_async(
            BrowserRoutePlaybookExecutionRequest(
                schema_version="1.0",
                playbook=playbook,
                normalized_url="https://example.com/request",
                page_driver=driver,
            ),
            run_context,
        )
    )

    assert response.status == "completed"
    assert driver.calls == ["click", "settle", "current_url"]


def test_deterministic_executor_rejects_role_select_for_non_native_control(
    run_context,
) -> None:
    playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="role-select-custom-control",
        version="1.0.0",
        status="active",
        updated_at="2026-08-20T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="example.com",
        host_patterns=["example.com"],
        url_path_markers=["report"],
        route_family="browser_email_form",
        route_kind="email_delivery",
        summary="Select a required identity value.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="select",
                target="Industry",
                verification="industry selected",
                selector_type="role",
                selector="textbox:Industry",
                value_reference="${identity.industry}",
                expected_text="Request form",
            )
        ],
    )

    response = asyncio.run(
        execute_browser_route_playbook_async(
            BrowserRoutePlaybookExecutionRequest(
                schema_version="1.0",
                playbook=playbook,
                normalized_url="https://example.com/request",
                page_driver=_AsyncRoleFormPageDriver(texts={"Request form"}),
                identity_values={"industry": "Retail"},
            ),
            run_context,
        )
    )

    assert response.status == "skipped"
    assert response.drift_reasons == ["step_0_unsupported_deterministic_role_action"]


def test_promotion_rejects_role_select_that_executor_cannot_run(
    tmp_path: Path,
    run_context,
) -> None:
    step = replace(
        _result(route_status="verified").execution_route_steps[0],
        action="select",
        locator_role="textbox",
        locator_name="Industry",
        identity_field_reference="identity.industry",
        expected_url_contains="",
        expected_text="Request form",
        locator_evidence=["locator:role:textbox:Industry"],
        postcondition_evidence=["text:Request form"],
    )
    result = replace(
        _result(route_status="verified"),
        execution_route_steps=[step],
    )

    response = promote_validated_browser_route_result_to_playbook(
        playbook_dir=str(tmp_path / "playbooks"),
        result=result,
        ctx=run_context,
        observed_at="2026-08-20T12:00:00+00:00",
    )

    assert response.status == "not_promotable"
    assert response.reason == "step_0_unsupported_deterministic_role_action"
    assert not (tmp_path / "playbooks").exists()


__all__ = [
    "test_validated_route_promotion_returns_not_promotable_for_partial_route",
    "test_validated_route_promotion_round_trips_complete_semantic_route_and_identity_references",
    "test_validated_route_promotion_dry_run_returns_review_diff_without_write",
    "test_private_api_promotion_writes_dedicated_playbook_and_requires_repeated_success",
    "test_private_api_promotion_rejects_missing_markers_and_cross_host_endpoint",
    "test_deterministic_route_playbook_executor_runs_selectors_and_reports_drift",
    "test_deterministic_route_playbook_executor_resolves_semantic_locators_and_identity_reference",
    "test_deterministic_route_playbook_executor_skips_missing_postcondition",
    "test_deterministic_route_playbook_executor_rejects_raw_identity_value",
    "test_runtime_role_form_evidence_promotes_and_executes_async",
    "test_async_deterministic_submit_waits_for_the_page_driver_to_settle",
    "test_deterministic_executor_rejects_role_select_for_non_native_control",
    "test_promotion_rejects_role_select_that_executor_cannot_run",
]
