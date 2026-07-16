from __future__ import annotations

import pytest

from src.contracts.browser_download import BrowserReportDownloadRequest
from src.contracts.drive import DriveUploadBytesRequest
from src.contracts.mailbox_acquisition import (
    MailboxAcquisitionSettings,
    MailboxSearchRequest,
)
from src.contracts.run_budget import RunBudget, RunBudgetUsage
from src.contracts.run_context import RunContext
from src.contracts.wordpress import WordPressPostCreateRequest
from src.services._browser_report_download.browser import run_browser_report_download_agent
from src.services._browser_report_download.prompt import BrowserDownloadPromptBundle
from src.services.drive_service import upload_bytes
from src.services.mailbox_acquisition_service import search_mailbox_messages
from src.services.wordpress_service import create_post
from src.utils.errors import AppError
from tests.test_browser_report_download_service.builders import _settings as browser_settings


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="budget-run", task_id="task", span_id="span")


def _budget() -> RunBudget:
    return RunBudget(
        schema_version="1.0",
        run_id="budget-run",
        publisher_name="publisher",
        max_drive_writes=1,
        max_wordpress_writes=1,
    )


def test_drive_budget_stop_occurs_before_authentication_or_network() -> None:
    with pytest.raises(AppError) as exc_info:
        upload_bytes(
            DriveUploadBytesRequest(
                schema_version="1.0", folder_id="folder", service_account_path="missing.json",
                file_name="artifact.json", content=b"{}", mime_type="application/json",
                run_budget=_budget(),
                run_budget_usage=RunBudgetUsage(schema_version="1.0", drive_writes=1),
            ),
            _ctx(),
        )

    assert exc_info.value.code == "drive_upload_budget_stop"
    assert exc_info.value.retryable is False


def test_wordpress_budget_stop_occurs_before_http_request() -> None:
    with pytest.raises(AppError) as exc_info:
        create_post(
            WordPressPostCreateRequest(
                schema_version="1.0", base_url="https://example.invalid", auth_header="redacted",
                title="Title", content_html="<p>content</p>", status="draft",
                run_budget=_budget(),
                run_budget_usage=RunBudgetUsage(schema_version="1.0", wordpress_writes=1),
            ),
            _ctx(),
        )

    assert exc_info.value.code == "wordpress_post_create_budget_stop"
    assert exc_info.value.retryable is False


def test_mailbox_budget_stop_occurs_before_credentials_or_network() -> None:
    budget = RunBudget(
        schema_version="1.0",
        run_id="budget-run",
        publisher_name="publisher",
        max_mailbox_reads=1,
    )
    settings = MailboxAcquisitionSettings(
        schema_version="1.0",
        provider="gmail",
        output_dir="./out",
        search_window_minutes=60,
        max_results=5,
        poll_timeout_seconds=30.0,
        poll_interval_seconds=5.0,
        gmail_oauth_client_path="",
        gmail_oauth_token_path="missing-token.json",
        gmail_user_id="me",
        imap_host="",
        imap_port=993,
        imap_user="",
        imap_password="",
        imap_mailbox="INBOX",
    )
    with pytest.raises(AppError) as exc_info:
        search_mailbox_messages(
            MailboxSearchRequest(
                schema_version="1.0",
                settings=settings,
                delivery_email="operator@example.com",
                source_url="https://example.invalid/report",
                report_title="Report",
                publisher_name="publisher",
                query_terms=["report"],
                run_budget=budget,
                poll_number=1,
            ),
            _ctx(),
        )
    assert exc_info.value.code == "mailbox_search_budget_stop"
    assert exc_info.value.retryable is False


def test_browser_launch_budget_stop_occurs_before_browser_runtime_load(tmp_path) -> None:
    budget = RunBudget(
        schema_version="1.0",
        run_id="budget-run",
        publisher_name="publisher",
        usage_db_path=str(tmp_path / "usage.sqlite"),
        max_browser_launches=1,
    )
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.invalid/report",
        settings=browser_settings(tmp_path),
        publisher_name="publisher",
        run_budget=budget,
    )
    prompt_bundle = BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace="browser_report_download/browser_route",
        system_prompt_path="system.yaml",
        user_prompt_path="user.yaml",
        system_prompt_sha256="system",
        user_prompt_sha256="user",
        rendered_system_prompt="system",
        rendered_user_prompt="user",
        task_prompt="open the report",
    )

    with pytest.raises(AppError) as exc_info:
        run_browser_report_download_agent(
            request=request,
            ctx=_ctx(),
            normalized_url=request.url,
            execution_url=request.url,
            download_dir=tmp_path / "downloads",
            prompt_bundle=prompt_bundle,
        )

    assert exc_info.value.code == "browser_budget_stop"
    assert exc_info.value.retryable is False
