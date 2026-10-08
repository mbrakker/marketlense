from __future__ import annotations

import hashlib
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pymupdf as fitz
import yaml

from src.contracts.browser_download import ReportDownloadOrchestratorRequest
from src.contracts.config import ConfigLoadRequest
from src.contracts.files import FileHashResponse
from src.contracts.mailbox_acquisition import MailboxSearchResult
from src.contracts.state import (
    MailDeliveryRequestByKeyGetRequest,
    MailDeliveryRequestGetRequest,
)
from src.contracts.workflow_queue import ReportAcquisitionPayload
from src.orchestrators import workflow_queue_orchestrator
from src.orchestrators.report_download_orchestrator import (
    ReportDownloadDependencies,
    run_report_download,
)
from src.services import mailbox_acquisition_service
from src.services.config_service import load_mailbox_acquisition_settings
from src.services.state_service import (
    get_mail_delivery_request,
    get_mail_delivery_request_by_key,
)
from src.services.workflow_queue_service import enqueue_workflow_job
from src.utils.idempotency import mail_delivery_request_idempotency_key
from tests._test_report_download_orchestrator._shared import _result, _settings
from tests._workflow_queue_registry_support import _isolated_app_config
from tests.test_workflow_queue_registry import _ctx, _workflow_job


def test_durable_mail_replay_polls_exact_request_and_ingests_local_signed_pdf(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Retail Trends 2026 report")
    pdf_bytes = document.tobytes()
    document.close()

    expected_request_path = "/Documents/CaseSensitive.pdf?token=A%2FB+Case"
    observed_http_paths: list[str] = []

    class PdfHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            observed_http_paths.append(self.path)
            self.send_response(200 if self.path == expected_request_path else 404)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(pdf_bytes)))
            self.end_headers()
            self.wfile.write(pdf_bytes)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    http_server = ThreadingHTTPServer(("127.0.0.1", 0), PdfHandler)
    http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    http_thread.start()
    try:
        http_base = f"http://127.0.0.1:{http_server.server_port}"
        source_url = f"{http_base}/reports/retail-trends"
        report_link = f"{http_base}{expected_request_path}"
        unsubscribe_link = f"{http_base}/unsubscribe"
        received_now = datetime.now(timezone.utc).replace(microsecond=0)
        confirmed_at = (
            (received_now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
        )
        old_received_at = (received_now - timedelta(minutes=2)).strftime(
            "%d-%b-%Y %H:%M:%S +0000"
        )
        valid_received_at = received_now.strftime("%d-%b-%Y %H:%M:%S +0000")

        def _message(download_url: str) -> bytes:
            message = EmailMessage()
            message["Subject"] = "Your Retail Trends 2026 report is ready"
            message["From"] = "Example Publisher <reports@example.test>"
            message["To"] = "ops@example.test"
            message.set_content(
                "Download your Retail Trends 2026 report from Example Publisher."
            )
            message.add_alternative(
                "<p>Your Retail Trends 2026 report from Example Publisher is ready.</p>"
                f'<a href="{download_url}">Download your Retail Trends 2026 report</a>'
                f'<a href="{unsubscribe_link}">Unsubscribe</a>',
                subtype="html",
            )
            return message.as_bytes()

        messages = {
            b"1": (
                old_received_at,
                _message(f"{http_base}/Documents/Old.pdf?token=stale"),
            ),
            b"2": (valid_received_at, _message(report_link)),
        }

        class ImapConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback) -> None:
                del exc_type, exc_value, traceback

            def login(self, user: str, password: str):
                assert user == "ops@example.test"
                assert password == "fixture-imap-password"
                return "OK", [b"authenticated"]

            def select(self, mailbox: str, readonly: bool = False):
                assert mailbox == "INBOX"
                assert readonly is True
                return "OK", [b"2"]

            def response(self, name: str):
                assert name == "UIDVALIDITY"
                return b"UIDVALIDITY", [b"314"]

            def uid(self, command: str, *args):
                if command == "search":
                    return "OK", [b"1 2"]
                assert command == "fetch"
                uid = args[0]
                received_at, raw_message = messages[uid]
                metadata = (
                    uid + b' (INTERNALDATE "' + received_at.encode("ascii") + b'")'
                )
                return "OK", [(metadata, raw_message), b")"]

        external_boundary_mocks_only.setattr(
            mailbox_acquisition_service.imaplib,
            "IMAP4_SSL",
            lambda host, port: ImapConnection(),
        )
        external_boundary_mocks_only.setenv("IMAP_PASS", "fixture-imap-password")
        external_boundary_mocks_only.setenv(
            "OPENROUTER_API_KEY", "fixture-openrouter-key"
        )
        config_path = _isolated_app_config(tmp_path)
        config_payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config_payload["browser_download"]["drive_upload"] = {
            "enabled": False,
            "required": False,
        }
        mailbox_config = config_payload["mailbox_acquisition"]
        mailbox_config.update(
            {
                "provider": "imap",
                "output_dir": str(tmp_path / "mailbox"),
                "search_window_minutes": 120,
                "max_results": 10,
                "poll_timeout_seconds": 0,
                "poll_interval_seconds": 1,
                "imap_host": "mailbox.example.test",
                "imap_port": 993,
                "imap_user": "ops@example.test",
                "imap_mailbox": "INBOX",
            }
        )
        config_path.write_text(
            yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8"
        )
        (tmp_path / "browser_download_identity.yaml").write_text(
            "schema_version: '1.0'\n"
            "fields:\n"
            "- schema_version: '1.0'\n"
            "  key: work_email\n"
            "  label: Work email\n"
            "  value: ops@example.test\n"
            "  aliases:\n"
            "  - email\n",
            encoding="utf-8",
        )
        external_boundary_mocks_only.setenv(
            "MARKET_LENSE_CONFIG_PATH", str(config_path)
        )

        generation_id = "mail-generation-integration"
        source_identity_id = "stable-source-identity"
        publisher_id = "publisher-integration"
        delivery_email = "ops@example.test"
        report_title = "Retail Trends 2026"
        request_key = mail_delivery_request_idempotency_key(
            generation_id=generation_id,
            source_url=source_url,
            delivery_email=delivery_email,
            source_identity_id=source_identity_id,
        )
        state_db = str(tmp_path / "state.sqlite")
        settings = _settings(tmp_path)
        browser_result = replace(
            _result(url=source_url, used_route_hint=False, path=None),
            outcome="email_requested",
            route_status="verified",
            blocked_reason=None,
            blocked_reason_detail=None,
            confirmation_evidence=replace(
                _result(
                    url=source_url, used_route_hint=False, path=None
                ).confirmation_evidence,
                submission_confirmed_at_utc=confirmed_at,
            ),
        )
        browser_intents = []

        def _submit_email_form(request, ctx):
            intent = get_mail_delivery_request_by_key(
                MailDeliveryRequestByKeyGetRequest(
                    schema_version="1.0",
                    state_db=state_db,
                    idempotency_key=request_key,
                ),
                ctx,
            ).request
            browser_intents.append(intent)
            return browser_result

        run_result = run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url=source_url,
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                delivery_email=delivery_email,
                report_title=report_title,
                publisher_name="Example Publisher",
                publisher_id=publisher_id,
                source_identity_id=source_identity_id,
                mailbox_settings=load_mailbox_acquisition_settings(
                    ConfigLoadRequest(schema_version="1.0", path=str(config_path)),
                    _ctx(),
                ),
                mail_delivery_generation_id=generation_id,
            ),
            ctx=_ctx(),
            dependencies=ReportDownloadDependencies(
                download_report_with_browser_use=_submit_email_form,
                get_publisher_download_route=lambda request, ctx: None,
                record_publisher_download_route=lambda request, ctx: None,
                file_md5=lambda request, ctx: FileHashResponse(
                    schema_version="1.0", path=request.path, md5="unused"
                ),
                record_report_source=lambda request, ctx: (_ for _ in ()).throw(
                    AssertionError("email submission must not record a report source")
                ),
                upsert_browser_download_identity_fields=lambda request, ctx: type(
                    "IdentityUpdate",
                    (),
                    {
                        "path": request.path,
                        "added_field_keys": [],
                        "total_fields": len(settings.identity_profile.fields),
                    },
                )(),
                sleep_fn=lambda seconds: None,
                preflight_mailbox_search=lambda request, ctx: MailboxSearchResult(
                    schema_version="1.0",
                    provider="imap",
                    searched_at_utc=confirmed_at,
                    query="preflight",
                    messages=[],
                ),
            ),
        )
        persisted_request = get_mail_delivery_request_by_key(
            MailDeliveryRequestByKeyGetRequest(
                schema_version="1.0",
                state_db=state_db,
                idempotency_key=request_key,
            ),
            _ctx(),
        ).request
        assert run_result.outcome == "email_requested"
        assert len(browser_intents) == 1
        assert browser_intents[0].status == "submission_started"
        assert persisted_request.requested_after_utc == confirmed_at
        assert persisted_request.submission_confirmed_at_utc == confirmed_at

        parent_job = replace(
            _workflow_job(
                queue_name="report_acquisition",
                job_type="report_acquisition.v1",
            ),
            root_workflow_id=generation_id,
            publisher_id=publisher_id,
            source_identity_id=source_identity_id,
        )
        acquisition_payload = ReportAcquisitionPayload(
            source_identity_id=source_identity_id,
            source_url=source_url,
            publisher_id=publisher_id,
            report_title=report_title,
            publisher_name="Example Publisher",
            delivery_email_reference=delivery_email,
            input_reference=source_url,
            input_content_hash="source-reference-hash",
            processing_version="mailbox-integration-v1",
        )
        acquisition_result = workflow_queue_orchestrator.execute_workflow_queue_handler(
            parent_job, acquisition_payload, _ctx()
        )

        assert len(acquisition_result.downstream) == 1
        mailbox_submission = acquisition_result.downstream[0]
        assert mailbox_submission.queue_name == "mailbox_delivery"
        mailbox_payload = mailbox_submission.payload
        assert mailbox_payload.source_url == source_url
        assert mailbox_payload.request_watermark == confirmed_at
        assert mailbox_payload.report_title == report_title
        assert mailbox_payload.publisher_id == publisher_id
        assert mailbox_payload.source_identity_id == source_identity_id
        assert mailbox_payload.attributes["delivery_email"] == delivery_email

        replay_result = workflow_queue_orchestrator.execute_workflow_queue_handler(
            parent_job, acquisition_payload, _ctx()
        )
        assert replay_result.downstream == acquisition_result.downstream

        mailbox_job, created = enqueue_workflow_job(
            state_db, mailbox_submission, _ctx()
        )
        assert created is True
        replayed_mailbox_job, replay_created = enqueue_workflow_job(
            state_db, replay_result.downstream[0], _ctx()
        )
        assert replay_created is False
        assert replayed_mailbox_job.job_id == mailbox_job.job_id
        mailbox_result = workflow_queue_orchestrator.execute_workflow_queue_handler(
            mailbox_job, mailbox_payload, _ctx()
        )

        assert len(mailbox_result.downstream) == 1
        ingest_submission = mailbox_result.downstream[0]
        assert ingest_submission.queue_name == "source_ingest"
        ingest_payload = ingest_submission.payload
        assert ingest_payload.source_artifact_reference
        assert Path(ingest_payload.source_artifact_reference).is_file()
        assert ingest_payload.source_content_hash == hashlib.md5(pdf_bytes).hexdigest()
        request = get_mail_delivery_request(
            MailDeliveryRequestGetRequest(
                schema_version="1.0",
                state_db=state_db,
                request_id=int(mailbox_payload.delivery_request_id),
            ),
            _ctx(),
        ).request
        assert request.status == "pending"
        assert request.source_url == source_url
        assert request.delivery_email == delivery_email
        assert request.report_title == report_title
        assert request.publisher_name == "Example Publisher"
        assert request.publisher_id == publisher_id
        assert request.source_identity_id == source_identity_id
        assert request.requested_after_utc == confirmed_at
        assert observed_http_paths == [expected_request_path]
    finally:
        http_server.shutdown()
        http_thread.join(timeout=5)
        http_server.server_close()
