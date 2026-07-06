from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadIdentity,
    BrowserDownloadSettings,
    DownloadTerminalEvidence,
    ReportDownloadOrchestratorResult,
)
from src.contracts.mailbox_acquisition import (
    MailboxAttachment,
    MailboxAttachmentMaterializeRequest,
    MailReportAcquisitionRequest,
    MailboxAcquisitionSettings,
    MailboxAttachmentArtifact,
    MailboxMessage,
    MailboxSearchResult,
)
from src.orchestrators.mail_report_acquisition_orchestrator import (
    MailReportAcquisitionDependencies,
    run_mail_report_acquisition,
)
from src.generators.mail_report_acquisition_generator import (
    select_mail_report_link_candidates,
)
from src.services.mailbox_acquisition_service import materialize_mailbox_attachments
from src.utils.errors import AppError


def _mailbox_settings(tmp_path, *, poll_timeout_seconds=120.0):
    return MailboxAcquisitionSettings(
        schema_version="1.0",
        provider="gmail",
        output_dir=str(tmp_path / "mailbox"),
        search_window_minutes=120,
        max_results=10,
        poll_timeout_seconds=poll_timeout_seconds,
        poll_interval_seconds=30.0,
        gmail_oauth_client_path="client.json",
        gmail_oauth_token_path="token.json",
        gmail_user_id="me",
        imap_host="",
        imap_port=993,
        imap_user="",
        imap_password="",
        imap_mailbox="INBOX",
    )


def _browser_settings(tmp_path):
    return BrowserDownloadSettings(
        schema_version="1.0",
        openrouter_api_key="openrouter-key",
        model="openai/gpt-5-mini",
        temperature=0.0,
        timeout_seconds=30.0,
        max_steps=8,
        output_dir=str(tmp_path / "downloads"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        identity_config_path=str(tmp_path / "identity.yaml"),
        identity_profile=BrowserDownloadIdentity(schema_version="1.0", fields=[]),
        drive_upload_enabled=False,
        drive_upload_required=False,
        retry_retries=0,
    )


def _message(*, links):
    return MailboxMessage(
        schema_version="1.0",
        provider_message_id="msg-1",
        subject="Your Retail Trends 2026 report download",
        sender="reports@example.com",
        received_at_utc="2026-07-04T11:10:00Z",
        text_body="Download the report",
        html_body="",
        links=list(links),
        attachment_file_names=[],
    )


def _message_received(*, provider_message_id: str, received_at_utc: str, links):
    return MailboxMessage(
        schema_version="1.0",
        provider_message_id=provider_message_id,
        subject="Your Retail Trends 2026 report download",
        sender="reports@example.com",
        received_at_utc=received_at_utc,
        text_body="Download the report",
        html_body="",
        links=list(links),
        attachment_file_names=[],
    )


def _message_with_attachment_artifact(
    *,
    provider_message_id: str,
    received_at_utc: str,
    attachment_path: str,
):
    return MailboxMessage(
        schema_version="1.0",
        provider_message_id=provider_message_id,
        subject="Your Retail Trends 2026 report download",
        sender="reports@example.com",
        received_at_utc=received_at_utc,
        text_body="Attached is your requested Retail Trends 2026 report.",
        html_body="",
        links=[],
        attachment_file_names=["retail-trends-2026.pdf"],
        attachment_artifacts=[
            MailboxAttachmentArtifact(
                schema_version="1.0",
                file_name="retail-trends-2026.pdf",
                content_type="application/pdf",
                size_bytes=27,
                path=attachment_path,
                source_container_file_name="",
            )
        ],
    )


def _downloaded_result(url: str, path: str):
    return ReportDownloadOrchestratorResult(
        schema_version="1.0",
        source_url=url,
        normalized_url=url,
        route_kind="pdf_download",
        route_family="direct_pdf_probe",
        route_status="verified",
        outcome="downloaded",
        route_summary="Downloaded the report link delivered by email.",
        final_page_url=url,
        resolved_target_url=url,
        used_memory_route=False,
        route_steps=[],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=False,
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=url,
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=url,
            final_page_title="",
            terminal_text_excerpt="",
            artifact_url=url,
            artifact_kind="pdf",
            artifact_validation_status="verified",
            artifact_validation_detail="",
            confirmation_signal_count=0,
            traversed_page_urls=[url],
        ),
        browser_had_structured_result=False,
        used_candidate_pdf_url=False,
        used_candidate_source_page=False,
        encountered_form_fields=[],
        identity_fields_added=[],
        blocked_reason=None,
        blocked_reason_detail=None,
        downloaded_file_path=path,
        downloaded_file_name="report.pdf",
        downloaded_mime_type="application/pdf",
        downloaded_size_bytes=512,
        onsite_capture_path=None,
        onsite_capture_format=None,
        onsite_page_count=None,
        onsite_completeness_status=None,
    )


def test_mail_report_acquisition_polls_until_delayed_report_link_arrives(
    tmp_path, run_context, assert_logs_have_required_fields, caplog
):
    searches = []
    sleeps = []
    downloads = []

    def search(req, ctx):
        searches.append(req)
        if len(searches) == 1:
            return MailboxSearchResult(
                schema_version="1.0",
                provider="gmail",
                searched_at_utc="2026-07-04T11:10:00Z",
                query="",
                messages=[],
            )
        return MailboxSearchResult(
            schema_version="1.0",
            provider="gmail",
            searched_at_utc="2026-07-04T11:11:00Z",
            query="",
            messages=[
                _message(
                    links=[
                        "https://example.com/unsubscribe",
                        "https://reports.example.com/retail-trends-2026.pdf",
                    ]
                )
            ],
        )

    def download(req, ctx):
        downloads.append(req)
        return _downloaded_result(req.url, str(tmp_path / "report.pdf"))

    deps = MailReportAcquisitionDependencies(
        search_mailbox_messages=search,
        run_report_download=download,
        sleep_fn=lambda seconds: sleeps.append(seconds),
    )
    caplog.set_level("INFO", logger="market_lense.mail_report_acquisition_orchestrator")

    result = run_mail_report_acquisition(
        MailReportAcquisitionRequest(
            schema_version="1.0",
            source_url="https://example.com/report-form",
            report_title="Retail Trends 2026",
            publisher_name="Example Reports",
            delivery_email="reports@example.com",
            reports_db=str(tmp_path / "reports.sqlite"),
            mailbox_settings=_mailbox_settings(tmp_path),
            browser_download_settings=_browser_settings(tmp_path),
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.outcome == "downloaded"
    assert result.mailbox_poll_count == 2
    assert result.selected_report_url == "https://reports.example.com/retail-trends-2026.pdf"
    assert result.downloaded_file_path == str(tmp_path / "report.pdf")
    assert sleeps == [30.0]
    assert len(downloads) == 1
    assert downloads[0].url == result.selected_report_url
    assert downloads[0].report_title == "Retail Trends 2026"
    assert downloads[0].publisher_name == "Example Reports"
    assert searches[0].query_terms[:2] == ["Example Reports", "Retail Trends 2026"]
    assert_logs_have_required_fields(
        [
            record.message
            for record in caplog.records
            if record.name == "market_lense.mail_report_acquisition_orchestrator"
        ]
    )


def test_mail_report_acquisition_returns_retryable_error_when_mail_is_delayed(
    tmp_path, run_context
):
    deps = MailReportAcquisitionDependencies(
        search_mailbox_messages=lambda req, ctx: MailboxSearchResult(
            schema_version="1.0",
            provider="gmail",
            searched_at_utc="2026-07-04T11:10:00Z",
            query="",
            messages=[],
        ),
        run_report_download=lambda req, ctx: pytest.fail("download should not run"),
        sleep_fn=lambda seconds: None,
    )

    with pytest.raises(AppError) as exc_info:
        run_mail_report_acquisition(
            MailReportAcquisitionRequest(
                schema_version="1.0",
                source_url="https://example.com/report-form",
                report_title="Retail Trends 2026",
                publisher_name="Example Reports",
                delivery_email="reports@example.com",
                reports_db=str(tmp_path / "reports.sqlite"),
                mailbox_settings=_mailbox_settings(
                    tmp_path, poll_timeout_seconds=0.0
                ),
                browser_download_settings=_browser_settings(tmp_path),
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert exc_info.value.code == "mail_report_not_arrived_yet"
    assert exc_info.value.retryable is True
    assert exc_info.value.severity == "warning"


def test_mail_report_acquisition_stops_on_retryable_candidate_download_error(
    tmp_path, run_context
):
    downloads = []

    def download(req, ctx):
        downloads.append(req)
        raise AppError(
            code="browser_download_agent_timeout",
            message="Browser agent timed out",
            retryable=True,
            severity="error",
        )

    deps = MailReportAcquisitionDependencies(
        search_mailbox_messages=lambda req, ctx: MailboxSearchResult(
            schema_version="1.0",
            provider="gmail",
            searched_at_utc="2026-07-04T11:10:00Z",
            query="",
            messages=[
                _message(
                    links=[
                        "https://reports.example.com/retail-trends-2026.pdf",
                        "https://reports.example.com/retail-trends-2026-backup.pdf",
                    ]
                )
            ],
        ),
        run_report_download=download,
        sleep_fn=lambda seconds: pytest.fail("retryable candidate failure should surface"),
    )

    with pytest.raises(AppError) as exc_info:
        run_mail_report_acquisition(
            MailReportAcquisitionRequest(
                schema_version="1.0",
                source_url="https://example.com/report-form",
                report_title="Retail Trends 2026",
                publisher_name="Example Reports",
                delivery_email="reports@example.com",
                reports_db=str(tmp_path / "reports.sqlite"),
                mailbox_settings=_mailbox_settings(tmp_path),
                browser_download_settings=_browser_settings(tmp_path),
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert exc_info.value.code == "mail_report_candidate_download_retryable_failed"
    assert exc_info.value.retryable is True
    assert exc_info.value.context["candidate_error_code"] == "browser_download_agent_timeout"
    assert len(downloads) == 1


def test_mail_report_acquisition_ignores_unrelated_mail_links(tmp_path, run_context):
    deps = MailReportAcquisitionDependencies(
        search_mailbox_messages=lambda req, ctx: MailboxSearchResult(
            schema_version="1.0",
            provider="gmail",
            searched_at_utc="2026-07-04T11:10:00Z",
            query="",
            messages=[
                _message(
                    links=[
                        "https://example.com/privacy",
                        "https://example.com/newsletter",
                    ]
                )
            ],
        ),
        run_report_download=lambda req, ctx: pytest.fail("download should not run"),
        sleep_fn=lambda seconds: None,
    )

    with pytest.raises(AppError) as exc_info:
        run_mail_report_acquisition(
            MailReportAcquisitionRequest(
                schema_version="1.0",
                source_url="https://example.com/report-form",
                report_title="Retail Trends 2026",
                publisher_name="Example Reports",
                delivery_email="reports@example.com",
                reports_db=str(tmp_path / "reports.sqlite"),
                mailbox_settings=_mailbox_settings(
                    tmp_path, poll_timeout_seconds=0.0
                ),
                browser_download_settings=_browser_settings(tmp_path),
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert exc_info.value.code == "mail_report_not_arrived_yet"


def test_mail_report_link_candidates_include_opaque_publisher_download_cta(
    run_context,
) -> None:
    webview_url = "https://grow.bigcommerce.com/index.php/email/emailWebview?mkt_tok=token"
    download_url = "https://about.bigcommerce.com/opaque-token"
    unsubscribe_url = "https://about.bigcommerce.com/unsubscribe"
    message = MailboxMessage(
        schema_version="1.0",
        provider_message_id="msg-bigcommerce",
        subject="Your Global B2B Buyer Behavior Report is here.",
        sender="The BigCommerce Team <sellmore@bigcommerce.com>",
        received_at_utc="2026-07-05T12:53:18Z",
        text_body=(
            f"To view this email as a web page, go to {webview_url}. "
            "Download your Global B2B Buyer Behavior Report. "
            f"Download Now <{download_url}>. "
            "Thank you for requesting a copy of the Global B2B Buyer Behavior Report. "
            f"Manage preferences at {unsubscribe_url}."
        ),
        html_body="",
        links=[webview_url, download_url, unsubscribe_url],
        attachment_file_names=[],
    )

    candidates = select_mail_report_link_candidates(
        messages=[message],
        source_url=(
            "https://www.bigcommerce.com/resources/reports/"
            "global-b2b-buyer-report-cdl-report/"
        ),
        report_title="Global B2B Buyer Behavior Report",
        publisher_name="BigCommerce",
        ctx=run_context,
    )

    assert [candidate.url for candidate in candidates] == [download_url]
    assert "message_report_delivery_context" in candidates[0].reason
    assert "link_report_cta_context" in candidates[0].reason
    assert "publisher_token_match" in candidates[0].reason


def test_mail_report_link_candidates_reject_cross_publisher_cta_context(
    run_context,
) -> None:
    download_url = "https://about.bigcommerce.com/opaque-token"
    message = MailboxMessage(
        schema_version="1.0",
        provider_message_id="msg-bigcommerce",
        subject="Your Global Consumer Report is here.",
        sender="The BigCommerce Team <sellmore@bigcommerce.com>",
        received_at_utc="2026-07-05T13:35:25Z",
        text_body=(
            "Download your Global Consumer Report. "
            f"Download Now <{download_url}>. "
            "Thank you for requesting a copy of the Global Consumer Report."
        ),
        html_body="",
        links=[download_url],
        attachment_file_names=[],
    )

    candidates = select_mail_report_link_candidates(
        messages=[message],
        source_url="https://www.gwi.com/reports/connecting-the-dots",
        report_title="Connecting the Dots",
        publisher_name="GWI",
        ctx=run_context,
    )

    assert candidates == []


def test_mail_report_link_candidates_reject_unrelated_marketo_report_delivery(
    run_context,
) -> None:
    delivery_url = (
        "https://explore.contentsquare.com/2025-digital-experience-benchmark-en/"
        "c/2025-benchmark-data-en?h_f=1&utm_source=marketo"
    )
    message = MailboxMessage(
        schema_version="1.0",
        provider_message_id="msg-contentsquare",
        subject="Your Digital Experience Benchmark report is ready",
        sender="Contentsquare <marketing@contentsquare.com>",
        received_at_utc="2026-07-06T08:01:00Z",
        text_body=(
            "Download the 2025 Digital Experience Benchmark report for customer teams. "
            f"Access the report <{delivery_url}>."
        ),
        html_body="",
        links=[delivery_url],
        attachment_file_names=[],
    )

    candidates = select_mail_report_link_candidates(
        messages=[message],
        source_url=(
            "https://resources.satisfyd.com/"
            "2026-employee-and-customer-experience-benchmark-report-satisfyd"
        ),
        report_title="2026 Employee and Customer Experience Benchmark Report",
        publisher_name="SATISFYD",
        ctx=run_context,
    )

    assert candidates == []


def test_mail_report_acquisition_ignores_matching_messages_before_request_watermark(
    tmp_path, run_context
):
    downloads = []

    def download(req, ctx):
        downloads.append(req)
        return _downloaded_result(req.url, str(tmp_path / "report.pdf"))

    deps = MailReportAcquisitionDependencies(
        search_mailbox_messages=lambda req, ctx: MailboxSearchResult(
            schema_version="1.0",
            provider="gmail",
            searched_at_utc="2026-07-04T11:12:00Z",
            query="",
            messages=[
                _message_received(
                    provider_message_id="old-msg",
                    received_at_utc="2026-07-04T11:07:59Z",
                    links=["https://reports.example.com/old-retail-trends-2026.pdf"],
                ),
                _message_received(
                    provider_message_id="new-msg",
                    received_at_utc="2026-07-04T11:08:30Z",
                    links=["https://reports.example.com/new-retail-trends-2026.pdf"],
                ),
            ],
        ),
        run_report_download=download,
        sleep_fn=lambda seconds: None,
    )

    result = run_mail_report_acquisition(
        MailReportAcquisitionRequest(
            schema_version="1.0",
            source_url="https://example.com/report-form",
            report_title="Retail Trends 2026",
            publisher_name="Example Reports",
            delivery_email="reports@example.com",
            requested_after_utc="2026-07-04T11:08:00Z",
            reports_db=str(tmp_path / "reports.sqlite"),
            mailbox_settings=_mailbox_settings(tmp_path),
            browser_download_settings=_browser_settings(tmp_path),
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.selected_message_id == "new-msg"
    assert result.selected_report_url == "https://reports.example.com/new-retail-trends-2026.pdf"
    assert len(downloads) == 1


def test_mail_report_acquisition_acquires_matching_pdf_attachment_without_link_followup(
    tmp_path, run_context
):
    attachment_path = tmp_path / "retail-trends-2026.pdf"
    attachment_path.write_bytes(b"%PDF-1.7 attachment report")
    deps = MailReportAcquisitionDependencies(
        search_mailbox_messages=lambda req, ctx: MailboxSearchResult(
            schema_version="1.0",
            provider="imap",
            searched_at_utc="2026-07-04T11:12:00Z",
            query="",
            messages=[
                _message_with_attachment_artifact(
                    provider_message_id="msg-attachment",
                    received_at_utc="2026-07-04T11:09:00Z",
                    attachment_path=str(attachment_path),
                )
            ],
        ),
        run_report_download=lambda req, ctx: pytest.fail("link download should not run"),
        sleep_fn=lambda seconds: None,
    )

    result = run_mail_report_acquisition(
        MailReportAcquisitionRequest(
            schema_version="1.0",
            source_url="https://example.com/report-form",
            report_title="Retail Trends 2026",
            publisher_name="Example Reports",
            delivery_email="reports@example.com",
            reports_db=str(tmp_path / "reports.sqlite"),
            mailbox_settings=_mailbox_settings(tmp_path),
            browser_download_settings=_browser_settings(tmp_path),
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.outcome == "downloaded_attachment"
    assert result.selected_message_id == "msg-attachment"
    assert result.downloaded_file_path == str(attachment_path)
    assert result.acquisition_result_taxonomy == "mailbox_attachment_pdf"


def test_mailbox_service_materializes_attached_zip_pdfs(tmp_path, run_context):
    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, "w") as archive:
        archive.writestr("nested/retail-trends-2026.pdf", b"%PDF-1.7 zipped report")
        archive.writestr("nested/readme.txt", b"not a report")

    response = materialize_mailbox_attachments(
        MailboxAttachmentMaterializeRequest(
            schema_version="1.0",
            settings=_mailbox_settings(tmp_path),
            provider_message_id="zip-msg",
            attachments=[
                MailboxAttachment(
                    schema_version="1.0",
                    file_name="delivery.zip",
                    content_type="application/zip",
                    payload=zip_buffer.getvalue(),
                )
            ],
        ),
        run_context,
    )

    assert len(response.artifacts) == 1
    assert response.artifacts[0].file_name == "retail-trends-2026.pdf"
    assert response.artifacts[0].source_container_file_name == "delivery.zip"
    assert response.artifacts[0].path.endswith("retail-trends-2026.pdf")
    assert Path(response.artifacts[0].path).read_bytes() == b"%PDF-1.7 zipped report"
