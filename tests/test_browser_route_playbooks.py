from __future__ import annotations

from ._test_browser_route_playbooks.cases_01_safe_promotion import *  # noqa: F401,F403

import json
import logging
from dataclasses import replace
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
    BrowserRoutePlaybook,
    BrowserRoutePlaybookExecutionRequest,
    BrowserRoutePlaybookStep,
    BrowserRoutePrivateApiPromotionRequest,
    DownloadTerminalEvidence,
)
from src.services import browser_report_download_service
from src.services._browser_report_download.playbooks import (
    execute_browser_route_playbook,
    load_browser_route_playbooks,
    promote_private_api_evidence_to_browser_playbook,
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


def test_prompt_uses_route_family_namespace_for_email_form(
    tmp_path: Path,
    run_context,
) -> None:
    request = BrowserReportDownloadRequest(
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
            route_playbook_dir=str(tmp_path / "playbooks"),
        ),
        route_family_hint="browser_email_form",
    )

    bundle = render_browser_report_download_prompt(
        request=request,
        ctx=run_context,
        normalized_url="https://example.com/research/report",
        execution_url="https://example.com/research/report",
        download_dir=tmp_path / "downloads",
        delivery_email="reports@example.com",
    )

    assert (
        bundle.namespace == "browser_report_download/browser_route/browser_email_form"
    )
    assert "Route-family guidance for `browser_pdf_click`" not in bundle.task_prompt
    assert "Route-family guidance for `browser_email_form`" in bundle.task_prompt


def test_email_form_prompt_completes_safe_missing_fields_and_selects(
    tmp_path: Path,
    run_context,
) -> None:
    request = BrowserReportDownloadRequest(
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
            route_playbook_dir=str(tmp_path / "playbooks"),
        ),
        route_family_hint="browser_email_form",
    )

    bundle = render_browser_report_download_prompt(
        request=request,
        ctx=run_context,
        normalized_url="https://example.com/research/report",
        execution_url="https://example.com/research/report",
        download_dir=tmp_path / "downloads",
        delivery_email="reports@example.com",
    )

    assert "generate a bounded non-sensitive value" in bundle.task_prompt
    assert "choose the first visible non-placeholder option" in bundle.task_prompt
    assert "record that field and selected option in `required_select_evidence`" in (
        bundle.task_prompt
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


class _FakePageDriver:
    def __init__(self, *, texts):
        self.calls = []
        self._url = ""
        self._texts = set(texts)

    def open(self, url):
        self.calls.append(("open", url))
        self._url = url
        return url

    def click_css(self, selector):
        self.calls.append(("click_css", selector))
        return selector

    def click_text(self, text):
        self.calls.append(("click_text", text))
        return text

    def click_role(self, role, name):
        self.calls.append(("click_role", role, name))
        return name

    def click_label(self, label):
        self.calls.append(("click_label", label))
        return label

    def click_name(self, name):
        self.calls.append(("click_name", name))
        return name

    def click_data_attribute(self, selector):
        self.calls.append(("click_data_attribute", selector))
        return selector

    def fill_css(self, selector, value):
        self.calls.append(("fill_css", selector, value))
        return selector

    def fill_label(self, label, value):
        self.calls.append(("fill_label", label, value))
        return label

    def fill_name(self, name, value):
        self.calls.append(("fill_name", name, value))
        return name

    def fill_data_attribute(self, selector, value):
        self.calls.append(("fill_data_attribute", selector, value))
        return selector

    def select_css(self, selector, value):
        self.calls.append(("select_css", selector, value))
        return selector

    def select_label(self, label, value):
        self.calls.append(("select_label", label, value))
        return label

    def select_name(self, name, value):
        self.calls.append(("select_name", name, value))
        return name

    def select_data_attribute(self, selector, value):
        self.calls.append(("select_data_attribute", selector, value))
        return selector

    def current_url(self):
        return self._url

    def contains_text(self, text):
        return text in self._texts


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
    execution_step = BrowserDownloadRouteStep(
        schema_version="1.0",
        index=0,
        action="click_cta",
        target_text="Download report",
        target_role="button",
        target_url="https://example.com/report.pdf",
        result="opened",
        expected_evidence=["browser_execution"],
        observed_evidence=["browser_execution"],
        verification_status="verified",
        locator_role="button",
        locator_name="Download report",
        expected_url_contains="/report.pdf",
        locator_evidence=["locator:role:button:Download report"],
        postcondition_evidence=["url:/report.pdf"],
    )
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
        route_steps=[execution_step],
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
        execution_route_steps=[execution_step],
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
