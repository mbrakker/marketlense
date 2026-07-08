from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.contracts.browser_download import (
    BrowserDownloadIdentity,
    BrowserDownloadSettings,
)
from src.contracts.mailbox_acquisition import (
    MailboxAcquisitionSettings,
    MailboxAttachmentArtifact,
    MailboxMessage,
    MailboxSearchResult,
)
from src.contracts.report_store import PublisherDownloadRouteGetRequest
from src.contracts.run_context import RunContext
from src.contracts.state import MailDeliveryRequestUpsertRequest
from src.contracts.workflow_control import MailDeliveryWorkflowRunRequest
from src.orchestrators.mail_report_acquisition_orchestrator import (
    MailReportAcquisitionDependencies,
    run_mail_report_acquisition,
)
from src.orchestrators.workflow_control_orchestrator import (
    run_due_mail_delivery_requests,
)
from src.services.report_store_service import get_publisher_download_route
from src.services.state_service import upsert_mail_delivery_request


def run_autonomous_happy_path_smoke(work_dir: Path) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    state_db = work_dir / "state.sqlite"
    reports_db = work_dir / "reports.sqlite"
    attachment_path = work_dir / "retail-trends-2026.pdf"
    attachment_path.write_bytes(b"%PDF-1.7 autonomous smoke report")
    ctx = RunContext(
        schema_version="1.0",
        run_id="autonomous-smoke",
        task_id="autonomous-smoke",
        span_id="root",
    )
    source_url = "https://example.com/report-form"
    mailbox_settings = _mailbox_settings(work_dir)
    browser_settings = _browser_settings(
        work_dir=work_dir,
        state_db=state_db,
        reports_db=reports_db,
    )
    upsert = upsert_mail_delivery_request(
        MailDeliveryRequestUpsertRequest(
            schema_version="1.0",
            state_db=str(state_db),
            idempotency_key="smoke:example:retail-trends-2026",
            source_url=source_url,
            report_title="Retail Trends 2026",
            publisher_name="Example Reports",
            delivery_email="reports@example.com",
            requested_after_utc="2026-07-04T11:08:00Z",
            route_family="browser_email_form",
            route_history_id="smoke-route-history",
        ),
        ctx,
    )

    def search(_request, _ctx):
        return MailboxSearchResult(
            schema_version="1.0",
            provider="smoke",
            searched_at_utc="2026-07-04T11:12:00Z",
            query="retail trends",
            messages=[
                MailboxMessage(
                    schema_version="1.0",
                    provider_message_id="smoke-msg-1",
                    subject="Your Retail Trends 2026 report download",
                    sender="Reports <reports@example.com>",
                    received_at_utc="2026-07-04T11:09:00Z",
                    text_body="Attached is your requested Retail Trends 2026 report.",
                    html_body="",
                    links=[],
                    attachment_file_names=["retail-trends-2026.pdf"],
                    attachment_artifacts=[
                        MailboxAttachmentArtifact(
                            schema_version="1.0",
                            file_name="retail-trends-2026.pdf",
                            content_type="application/pdf",
                            size_bytes=attachment_path.stat().st_size,
                            path=str(attachment_path),
                            source_container_file_name="",
                        )
                    ],
                )
            ],
        )

    deps = MailReportAcquisitionDependencies(
        search_mailbox_messages=search,
        run_report_download=lambda _request, _ctx: _raise_unexpected_download(),
        sleep_fn=lambda _seconds: None,
    )
    result = run_due_mail_delivery_requests(
        MailDeliveryWorkflowRunRequest(
            schema_version="1.0",
            state_db=str(state_db),
            reports_db=str(reports_db),
            now_utc="2026-07-04T11:10:00Z",
            limit=10,
            mailbox_settings=mailbox_settings,
            browser_download_settings=browser_settings,
        ),
        ctx=ctx,
        run_mail_report_acquisition_fn=lambda req, run_ctx: run_mail_report_acquisition(
            req,
            ctx=run_ctx,
            dependencies=deps,
        ),
    )
    route = get_publisher_download_route(
        PublisherDownloadRouteGetRequest(
            schema_version="1.0",
            db_path=str(reports_db),
            normalized_url=source_url,
        ),
        ctx,
    )
    idempotent_replay_confirmed = (
        not upsert.created
        and result.processed_count == 0
        and route is not None
        and route.outcome == "downloaded"
    )
    happy_path_confirmed = result.succeeded_count == 1 and route is not None
    return {
        "schema_version": "1.0",
        "status": (
            "passed"
            if happy_path_confirmed or idempotent_replay_confirmed
            else "failed"
        ),
        "mail_delivery_request_created": upsert.created,
        "idempotent_replay_confirmed": idempotent_replay_confirmed,
        "processed_count": result.processed_count,
        "succeeded_count": result.succeeded_count,
        "route_memory_promoted": route is not None,
        "route_kind": route.route_kind if route else "",
        "route_outcome": route.outcome if route else "",
        "downloaded_file_size_bytes": attachment_path.stat().st_size,
        "workflow_result": asdict(result),
    }


def _mailbox_settings(work_dir: Path) -> MailboxAcquisitionSettings:
    return MailboxAcquisitionSettings(
        schema_version="1.0",
        provider="smoke",
        output_dir=str(work_dir / "mailbox"),
        search_window_minutes=120,
        max_results=10,
        poll_timeout_seconds=0.0,
        poll_interval_seconds=0.0,
        gmail_oauth_client_path="",
        gmail_oauth_token_path="",
        gmail_user_id="",
        imap_host="",
        imap_port=993,
        imap_user="",
        imap_password="",
        imap_mailbox="INBOX",
    )


def _browser_settings(
    *,
    work_dir: Path,
    state_db: Path,
    reports_db: Path,
) -> BrowserDownloadSettings:
    return BrowserDownloadSettings(
        schema_version="1.0",
        openrouter_api_key="",
        model="openai/gpt-5-mini",
        temperature=0.0,
        timeout_seconds=30.0,
        max_steps=8,
        output_dir=str(work_dir / "downloads"),
        state_db=str(state_db),
        reports_db=str(reports_db),
        identity_config_path=str(work_dir / "identity.yaml"),
        identity_profile=BrowserDownloadIdentity(schema_version="1.0", fields=[]),
        drive_upload_enabled=False,
        drive_upload_required=False,
        retry_retries=0,
    )


def _raise_unexpected_download() -> None:
    raise AssertionError("attachment smoke should not follow mailbox links")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    if args.work_dir:
        payload = run_autonomous_happy_path_smoke(Path(args.work_dir))
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = run_autonomous_happy_path_smoke(Path(tmpdir))
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
