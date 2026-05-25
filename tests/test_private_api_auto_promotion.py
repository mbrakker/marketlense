from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadIdentity,
    BrowserDownloadNetworkEvent,
    BrowserDownloadRouteStep,
    BrowserDownloadSettings,
    BrowserReportDownloadResult,
    BrowserRoutePrivateApiAutoPromotionDetectionRequest,
    DownloadTerminalEvidence,
)
from src.contracts.report_store import (
    PublisherPrivateApiCandidateObservationRecordRequest,
    PublisherPrivateApiCandidatePromotedRequest,
)
from src.services.browser_report_download_service import (
    detect_private_api_promotion_candidates,
)
from src.services.report_store_service import (
    mark_publisher_private_api_candidate_promoted,
    record_publisher_private_api_candidate_observation,
)


class _PrivateApiFixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/reports/"):
            payload = {
                "asset": {
                    "pdfUrl": f"http://127.0.0.1:{self.server.server_port}/files/report-2026.pdf"
                }
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/files/report-2026.pdf":
            body = b"%PDF-1.4\n% fixture\n%%EOF\n"
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def _serve_private_api_fixture():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PrivateApiFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _settings(tmp_path: Path) -> BrowserDownloadSettings:
    return BrowserDownloadSettings(
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
        identity_profile=BrowserDownloadIdentity(schema_version="1.0", fields=[]),
        private_api_playbook_promotion_mode="write",
        private_api_playbook_min_success_count=3,
        private_api_playbook_min_distinct_source_urls=2,
    )


def _download_result(base_url: str, source_path: str) -> BrowserReportDownloadResult:
    source_url = f"{base_url}{source_path}"
    api_url = f"{base_url}/api/reports/{source_path.rsplit('/', 1)[-1]}"
    pdf_url = f"{base_url}/files/report-2026.pdf"
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=source_url,
        normalized_url=source_url,
        route_kind="pdf_download",
        route_family="browser_pdf_click",
        route_status="verified",
        outcome="downloaded",
        route_summary="Click the report CTA and wait for the PDF response.",
        final_page_url=source_url,
        resolved_target_url=pdf_url,
        used_route_hint=False,
        route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="click",
                target_text="Download report",
                target_role="link",
                target_url=source_url,
                result="downloaded",
            )
        ],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=True,
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=source_url,
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=source_url,
            final_page_title="Report",
            terminal_text_excerpt="Download report",
            artifact_url=pdf_url,
            artifact_kind="pdf",
            artifact_validation_status="verified",
            artifact_validation_detail="Verified browser PDF artifact.",
            confirmation_signal_count=1,
            traversed_page_urls=[source_url],
            observed_document_urls=[pdf_url],
            network_events=[
                BrowserDownloadNetworkEvent(
                    schema_version="1.0",
                    url=api_url,
                    initiator_type="fetch",
                    signal_kind="document_request",
                )
            ],
        ),
        browser_had_structured_result=True,
        used_candidate_pdf_url=False,
        used_candidate_source_page=False,
        encountered_form_fields=[],
        blocked_reason=None,
        blocked_reason_detail=None,
        downloaded_file_path=str(Path("downloaded.pdf")),
        downloaded_file_name="downloaded.pdf",
        downloaded_mime_type="application/pdf",
        downloaded_size_bytes=24,
        onsite_capture_path=None,
        onsite_capture_format=None,
        onsite_page_count=None,
        onsite_completeness_status=None,
    )


def test_detect_private_api_candidate_replays_safe_get_and_derives_json_pointer(
    tmp_path, run_context
) -> None:
    server = _serve_private_api_fixture()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        result = _download_result(base_url, "/research/report-2026")

        response = detect_private_api_promotion_candidates(
            BrowserRoutePrivateApiAutoPromotionDetectionRequest(
                schema_version="1.0",
                settings=_settings(tmp_path),
                result=result,
                observed_at="2026-05-23T08:00:00+00:00",
            ),
            run_context,
        )

        assert response.candidate_count == 1
        candidate = response.candidates[0]
        assert candidate.endpoint_pattern == "/api/reports/{last_path_segment}"
        assert candidate.method == "GET"
        assert candidate.response_pdf_url_json_pointer == "/asset/pdfUrl"
        assert candidate.selected_pdf_url == f"{base_url}/files/report-2026.pdf"
        assert candidate.required_response_markers == ["pdfUrl"]
    finally:
        server.shutdown()
        server.server_close()


def test_private_api_candidate_store_requires_threshold_and_marks_promotion(
    tmp_path, run_context
) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    common = {
        "schema_version": "1.0",
        "db_path": db_path,
        "fingerprint": "fp-example",
        "publisher_host": "example.com",
        "endpoint_pattern": "/api/reports/{last_path_segment}",
        "method": "GET",
        "request_shape_summary": "GET without cookies or auth headers.",
        "response_pdf_url_json_pointer": "/asset/pdfUrl",
        "expected_status_codes": [200],
        "required_response_markers": ["pdfUrl"],
        "fallback_route_family": "browser_pdf_click",
        "route_family": "browser_pdf_click",
        "route_kind": "pdf_download",
        "evidence_labels": ["browser_network_private_api"],
        "min_success_count": 3,
        "min_distinct_source_urls": 2,
    }

    first = record_publisher_private_api_candidate_observation(
        PublisherPrivateApiCandidateObservationRecordRequest(
            **common,
            source_url="https://example.com/research/report-1",
            observed_at="2026-05-23T08:00:00+00:00",
        ),
        run_context,
    )
    assert first.success_count == 1
    assert first.eligible_for_promotion is False

    record_publisher_private_api_candidate_observation(
        PublisherPrivateApiCandidateObservationRecordRequest(
            **common,
            source_url="https://example.com/research/report-2",
            observed_at="2026-05-23T08:01:00+00:00",
        ),
        run_context,
    )
    third = record_publisher_private_api_candidate_observation(
        PublisherPrivateApiCandidateObservationRecordRequest(
            **common,
            source_url="https://example.com/research/report-2",
            observed_at="2026-05-23T08:02:00+00:00",
        ),
        run_context,
    )

    assert third.success_count == 3
    assert third.distinct_source_url_count == 2
    assert third.eligible_for_promotion is True
    assert third.already_promoted is False

    mark_publisher_private_api_candidate_promoted(
        PublisherPrivateApiCandidatePromotedRequest(
            schema_version="1.0",
            db_path=db_path,
            fingerprint="fp-example",
            playbook_id="private-api-example-com-pdf-download",
            promoted_at="2026-05-23T08:03:00+00:00",
        ),
        run_context,
    )
    after_promotion = record_publisher_private_api_candidate_observation(
        PublisherPrivateApiCandidateObservationRecordRequest(
            **common,
            source_url="https://example.com/research/report-3",
            observed_at="2026-05-23T08:04:00+00:00",
        ),
        run_context,
    )
    assert after_promotion.already_promoted is True
    assert after_promotion.eligible_for_promotion is False
