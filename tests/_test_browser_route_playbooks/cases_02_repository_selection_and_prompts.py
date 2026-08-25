# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_browser_route_playbooks.py"
)

from ._shared import *  # noqa: F401,F403


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


def test_adjust_ebook_listing_selects_the_deterministic_report_entry_playbook(
    run_context,
) -> None:
    playbook_dir = (
        Path(__file__).resolve().parents[1] / "src" / "playbooks" / "browser_routes"
    )
    playbooks = load_browser_route_playbooks(
        playbook_dir=str(playbook_dir),
        ctx=run_context,
    )
    selection = select_browser_route_playbooks(
        playbooks=playbooks,
        normalized_url="https://www.adjust.com/resources/ebooks/all",
        route_family_hint="browser_email_form",
        now=datetime.fromisoformat("2026-08-22T19:00:00+00:00"),
    )

    assert selection.selected_playbooks[0].playbook_id == (
        "learned-www-adjust-com-browser-email-form-listing"
    )
    assert selection.selected_playbooks[0].route_kind == "email_delivery"
    playbook = next(
        item
        for item in load_browser_route_playbooks(
            playbook_dir=str(playbook_dir),
            ctx=run_context,
        )
        if item.playbook_id == "learned-www-adjust-com-browser-email-form-listing"
    )
    assert playbook.steps[0].action == "navigate"
    assert playbook.steps[0].selector == (
        "https://www.adjust.com/resources/ebooks/japan-app-trends/"
    )


def test_gwi_email_form_playbook_is_executable_for_both_observed_submit_labels(
    run_context,
) -> None:
    playbook_dir = (
        Path(__file__).resolve().parents[1] / "src" / "playbooks" / "browser_routes"
    )
    playbook = next(
        item
        for item in load_browser_route_playbooks(
            playbook_dir=str(playbook_dir),
            ctx=run_context,
        )
        if item.playbook_id == "learned-www-gwi-com-browser-email-form"
    )

    assert [step.action for step in playbook.steps] == [
        "fill",
        "fill",
        "fill",
        "select",
        "select",
        "submit",
    ]
    assert [step.selector_type for step in playbook.steps] == [
        "name",
        "name",
        "name",
        "name",
        "name",
        "css",
    ]
    assert [step.value_reference for step in playbook.steps[:-1]] == [
        "${identity.first_name}",
        "${identity.last_name}",
        "${identity.work_email}",
        "${identity.company_size}",
        "${identity.country}",
    ]
    assert [step.selector for step in playbook.steps[:-1]] == [
        "firstname",
        "lastname",
        "email",
        "company_size_legacy",
        "country_dropdown",
    ]
    assert playbook.steps[-1].selector == "input.hs-button.primary.large"
    assert playbook.steps[-1].expected_url_contains == "/reports/"
    assert all(
        step.expected_text or step.expected_url_contains for step in playbook.steps
    )


def test_bcg_digital_infrastructure_playbook_uses_a_deterministic_rendered_pdf_route(
    run_context,
) -> None:
    """Removing BCG's local-PDF route would return this public report to Agent work."""

    playbook_dir = (
        Path(__file__).resolve().parents[1] / "src" / "playbooks" / "browser_routes"
    )
    playbooks = load_browser_route_playbooks(
        playbook_dir=str(playbook_dir),
        ctx=run_context,
    )
    selection = select_browser_route_playbooks(
        playbooks=playbooks,
        normalized_url=(
            "https://www.bcg.com/publications/2026/digital-infrastructure-playbook"
        ),
        route_family_hint="browser_onsite_report",
        now=datetime.fromisoformat("2026-08-23T20:00:00+00:00"),
    )

    assert selection.selected_playbooks[0].playbook_id == (
        "learned-www-bcg-com-browser-onsite-report"
    )
    playbook = next(
        item
        for item in playbooks
        if item.playbook_id == "learned-www-bcg-com-browser-onsite-report"
    )
    assert [step.action for step in playbook.steps] == ["save_as_pdf"]
    assert playbook.route_kind == "onsite_report"
    assert playbook.steps[0].expected_text == (
        "The Digital Infrastructure Universe Continues to Expand"
    )


def test_deterministic_executor_runs_save_as_pdf_after_its_page_postcondition(
    run_context,
) -> None:
    """Removing PDF-render support would force a proven public route to Agent."""

    class SavePdfDriver:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def save_as_pdf(self, target: str) -> str:
            self.calls.append(("save_as_pdf", target))
            return "saved"

        def current_url(self) -> str:
            return (
                "https://www.bcg.com/publications/2026/digital-infrastructure-playbook"
            )

        def contains_text(self, text: str) -> bool:
            return text == "Digital Infrastructure Investing Playbook for 2026"

    playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="bcg-rendered-pdf",
        version="1.0.0",
        status="active",
        updated_at="2026-08-23T00:00:00+00:00",
        stale_after_days=120,
        publisher_pattern="www.bcg.com",
        host_patterns=["www.bcg.com"],
        url_path_markers=["digital-infrastructure-playbook"],
        route_family="browser_onsite_report",
        route_kind="pdf_download",
        summary="Render the verified public BCG report page as a local PDF.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="save_as_pdf",
                target="Render the public report page as a local PDF",
                verification=(
                    "A local browser-rendered PDF is available for verification."
                ),
                selector_type="url",
                selector=(
                    "https://www.bcg.com/publications/2026/"
                    "digital-infrastructure-playbook"
                ),
                expected_text="Digital Infrastructure Investing Playbook for 2026",
            )
        ],
    )
    driver = SavePdfDriver()

    response = execute_browser_route_playbook(
        BrowserRoutePlaybookExecutionRequest(
            schema_version="1.0",
            playbook=playbook,
            normalized_url=(
                "https://www.bcg.com/publications/2026/digital-infrastructure-playbook"
            ),
            page_driver=driver,
        ),
        run_context,
    )

    assert response.status == "completed"
    assert driver.calls == [
        (
            "save_as_pdf",
            "https://www.bcg.com/publications/2026/digital-infrastructure-playbook",
        )
    ]


def test_rendered_pdf_playbook_postcondition_uses_the_local_pdf_text(
    tmp_path: Path,
) -> None:
    """A hung page bridge must not prevent checking the PDF just rendered locally."""

    pdf_path = tmp_path / "bcg.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Digital Infrastructure Investing Playbook for 2026",
    )
    document.save(pdf_path)
    document.close()

    class PageThatMustNotBeEvaluated:
        def evaluate(self, _expression: str):
            raise AssertionError(
                "page evaluation should not be needed after PDF rendering"
            )

    driver = _DeterministicPlaybookPageDriver(
        browser=object(),
        page=PageThatMustNotBeEvaluated(),
        rendered_pdf_path=pdf_path,
    )

    assert driver.contains_text("Digital Infrastructure Investing Playbook for 2026")
    assert driver.contains_text("Digital Infrastructure Investing\nPlaybook for 2026")


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


__all__ = [
    "test_repo_browser_route_playbooks_load_and_select",
    "test_adjust_ebook_listing_selects_the_deterministic_report_entry_playbook",
    "test_gwi_email_form_playbook_is_executable_for_both_observed_submit_labels",
    "test_bcg_digital_infrastructure_playbook_uses_a_deterministic_rendered_pdf_route",
    "test_deterministic_executor_runs_save_as_pdf_after_its_page_postcondition",
    "test_rendered_pdf_playbook_postcondition_uses_the_local_pdf_text",
    "test_stale_playbook_fallback_and_fail_policies_are_logged",
    "test_prompt_cites_selected_playbook_id_version_and_steps",
    "test_prompt_uses_route_family_namespace_for_email_form",
    "test_email_form_prompt_completes_safe_missing_fields_and_selects",
    "test_validated_route_promotion_writes_reviewable_file_and_rejects_unverified",
]
