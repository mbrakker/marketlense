from __future__ import annotations

import json
from dataclasses import replace

from src.contracts.acquisition_audit import AcquisitionAuditBatchRequest
from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
    BrowserDownloadRouteStep,
    BrowserDownloadSettings,
    DownloadTerminalEvidence,
    ReportDownloadOrchestratorResult,
)
from src.contracts.files import WriteBytesResponse
from src.contracts.publisher_inventory import (
    PublisherInventoryCandidateTrace,
    PublisherInventoryDiscoveryResult,
    PublisherInventoryRunQualitySummary,
    PublisherInventorySettings,
)
from src.contracts.report_store import (
    PublisherListItem,
    PublishersListResponse,
)
from src.orchestrators.acquisition_audit_orchestrator import (
    AcquisitionAuditDependencies,
    run_acquisition_audit,
)


def _inventory_settings() -> PublisherInventorySettings:
    return PublisherInventorySettings(
        schema_version="1.0",
        openrouter_api_key="openrouter-key",
        model="openai/gpt-5-mini",
        temperature=0.0,
        timeout_seconds=30.0,
        max_steps=5,
        output_dir="./out/publisher_inventory_discovery",
        reports_db="./state/reports.sqlite",
        google_sa_path="./sa.json",
        prompt_namespace="publisher_inventory/discovery",
        pagination_max_pages=5,
        http_timeout_seconds=10.0,
        openrouter_http_referer=None,
        headed=False,
        retry_retries=1,
        retry_base_delay_seconds=0.0,
        retry_backoff_step_seconds=0.0,
        retry_jitter_seconds=0.0,
        openai_api_key="openai-key",
        candidate_screening_enabled=True,
        candidate_screening_model="gpt-5-nano",
        candidate_screening_temperature=1.0,
        candidate_screening_timeout_seconds=30.0,
        candidate_screening_prompt_namespace="publisher_inventory/meaningful_candidate_screen",
    )


def _browser_settings() -> BrowserDownloadSettings:
    return BrowserDownloadSettings(
        schema_version="1.0",
        openrouter_api_key="key",
        model="openai/gpt-5-mini",
        temperature=0.0,
        timeout_seconds=45.0,
        max_steps=12,
        output_dir="./out/browser_downloads",
        state_db="./state/index.sqlite",
        reports_db="./state/reports.sqlite",
        identity_config_path="./src/config/browser_download_identity.yaml",
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="work_email",
                    label="Work email",
                    value="ops@example.com",
                    aliases=["email"],
                )
            ],
        ),
        openrouter_http_referer="https://marketlense.local",
        headed=False,
        retry_retries=1,
        retry_base_delay_seconds=0.0,
        retry_backoff_step_seconds=0.0,
        retry_jitter_seconds=0.0,
    )


def _discovery_result() -> PublisherInventoryDiscoveryResult:
    return PublisherInventoryDiscoveryResult(
        schema_version="1.0",
        publisher_name="Activate Consulting",
        insights_url="https://www.activate.com/insights",
        normalized_insights_url="https://www.activate.com/insights",
        new_report_urls=[],
        current_report_count=2,
        previous_report_count=1,
        used_memory_route=False,
        snapshot_changed=True,
        run_quality_summary=PublisherInventoryRunQualitySummary(
            schema_version="1.0",
            outcome="accepted",
            status="passed",
            quality_band="high",
            route_kind="browser_render",
            recommended_route_kind="browser_render",
            used_memory_route=False,
            page_count=2,
            raw_candidate_count=2,
            current_report_count=2,
            previous_report_count=1,
            raw_new_report_count=1,
            screened_new_report_count=1,
            qualified_new_report_count=1,
            snapshot_changed=True,
            requires_review=False,
            recommended_route_reason="Reuse browser route.",
            summary="high quality via browser_render",
            candidate_provenance_counts={"browser_dom": 2},
        ),
        current_candidates=[
            PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://www.activate.com/reports/direct.pdf",
                title="Direct Report",
                discovered_on_page_number=1,
                source_page_urls=["https://www.activate.com/insights"],
                discovery_provenances=["browser_dom"],
                pdf_url="https://www.activate.com/reports/direct.pdf",
                published_at_text=None,
                max_confidence=0.9,
            ),
            PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://www.activate.com/reports/gated",
                title="Gated Report",
                discovered_on_page_number=2,
                source_page_urls=["https://www.activate.com/insights?page=2"],
                discovery_provenances=["browser_dom", "http_supplement"],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.7,
            ),
        ],
    )


def test_run_acquisition_audit_builds_candidate_and_publisher_maps(
    run_context,
    assert_logs_have_required_fields,
    caplog,
) -> None:
    writes = []
    download_requests = []

    def _run_download(req, ctx):
        download_requests.append(req)
        if req.url.endswith("direct.pdf"):
            return ReportDownloadOrchestratorResult(
                schema_version="1.0",
                source_url=req.url,
                normalized_url=req.url,
                route_kind="pdf_download",
                route_family="direct_pdf_probe",
                route_status="verified",
                outcome="downloaded",
                route_summary="Open the page and download the PDF.",
                final_page_url=req.url,
                resolved_target_url=req.url,
                used_memory_route=False,
                route_steps=[
                    BrowserDownloadRouteStep(
                        schema_version="1.0",
                        index=0,
                        action="open",
                        target_text=req.url,
                        target_role="url",
                        target_url=req.url,
                        result="downloaded",
                    )
                ],
                confirmation_evidence=BrowserDownloadConfirmationEvidence(
                    schema_version="1.0",
                    url_changed=False,
                    visible_confirmation_text="",
                    submit_button_state="unchanged",
                    form_disappeared=False,
                    final_page_url=req.url,
                ),
                terminal_evidence=DownloadTerminalEvidence(
                    schema_version="1.0",
                    final_page_url=req.url,
                    final_page_title="",
                    terminal_text_excerpt="",
                    artifact_url=req.url,
                    artifact_kind="pdf",
                    artifact_validation_status="verified",
                    artifact_validation_detail="",
                    confirmation_signal_count=0,
                    traversed_page_urls=[req.url],
                ),
                browser_had_structured_result=False,
                used_candidate_pdf_url=True,
                used_candidate_source_page=False,
                encountered_form_fields=[],
                identity_fields_added=[],
                blocked_reason=None,
                blocked_reason_detail=None,
                downloaded_file_path="./out/downloads/direct.pdf",
                downloaded_file_name="direct.pdf",
                downloaded_mime_type="application/pdf",
                downloaded_size_bytes=128,
                onsite_capture_path=None,
                onsite_capture_format=None,
                onsite_page_count=None,
                onsite_completeness_status=None,
            )
        return ReportDownloadOrchestratorResult(
            schema_version="1.0",
            source_url=req.url,
            normalized_url=req.url,
            route_kind="email_delivery",
            route_family="browser_email_form",
            route_status="inferred",
            outcome="email_required",
            route_summary="Open the page and inspect the gated form.",
            final_page_url=req.url,
            resolved_target_url=req.url,
            used_memory_route=False,
            route_steps=[],
            confirmation_evidence=BrowserDownloadConfirmationEvidence(
                schema_version="1.0",
                url_changed=False,
                visible_confirmation_text="",
                submit_button_state="unchanged",
                form_disappeared=False,
                final_page_url=req.url,
            ),
            terminal_evidence=DownloadTerminalEvidence(
                schema_version="1.0",
                final_page_url=req.url,
                final_page_title="",
                terminal_text_excerpt="",
                artifact_url=req.url,
                artifact_kind="email_delivery",
                artifact_validation_status="blocked",
                artifact_validation_detail="",
                confirmation_signal_count=0,
                traversed_page_urls=[req.url],
            ),
            browser_had_structured_result=True,
            used_candidate_pdf_url=False,
            used_candidate_source_page=False,
            encountered_form_fields=["Business email"],
            identity_fields_added=[],
            blocked_reason="blocked_email_domain",
            blocked_reason_detail="Business email required",
            downloaded_file_path=None,
            downloaded_file_name=None,
            downloaded_mime_type=None,
            downloaded_size_bytes=None,
            onsite_capture_path=None,
            onsite_capture_format=None,
            onsite_page_count=None,
            onsite_completeness_status=None,
        )

    deps = AcquisitionAuditDependencies(
        list_publishers=lambda req, ctx: PublishersListResponse(
            schema_version="1.0",
            publishers=[
                PublisherListItem(
                    schema_version="1.0",
                    publisher_name="Activate Consulting",
                    homepage="https://www.activate.com/",
                    insights_url="https://www.activate.com/insights",
                    normalized_insights_url="https://www.activate.com/insights",
                    google_folder="https://drive.google.com/drive/folders/abc123",
                    discovery_test_status="passed",
                    inventory_route_kind="browser_render",
                    inventory_route_summary="Open page 1 and page 2.",
                    inventory_run_quality_summary=None,
                )
            ],
        ),
        run_publisher_inventory_discovery=lambda req, ctx: _discovery_result(),
        run_report_download=_run_download,
        write_bytes=lambda req, ctx: (
            writes.append(req)
            or WriteBytesResponse(
                schema_version="1.0",
                path=req.path,
                bytes_written=len(req.content),
                md5="abc123",
            )
        ),
    )
    caplog.set_level("INFO", logger="market_lense.acquisition_audit_orchestrator")

    result = run_acquisition_audit(
        AcquisitionAuditBatchRequest(
            schema_version="1.0",
            reports_db="./state/reports.sqlite",
            publisher_inventory_settings=_inventory_settings(),
            browser_download_settings=_browser_settings(),
            output_dir="./out",
            delivery_email=None,
            publisher_limit=None,
            candidate_limit_per_publisher=None,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.publisher_count == 1
    assert result.candidate_count == 2
    assert len(result.publishers) == 1
    assert result.publishers[0].recommended_publisher_flow == "mixed_automation"
    assert result.publishers[0].downloaded_count == 1
    assert result.publishers[0].email_required_count == 1
    assert result.candidates[0].recommended_report_flow == "automate_pdf_download"
    assert result.candidates[1].recommended_report_flow == "complete_identity_profile"
    assert len(download_requests) == 2
    assert (
        download_requests[0].candidate_trace
        == _discovery_result().current_candidates[0]
    )
    assert download_requests[0].publisher_discovery_route_kind == "browser_render"
    assert (
        download_requests[0].publisher_recommended_discovery_route_kind
        == "browser_render"
    )
    assert all(req.reports_db != "./state/reports.sqlite" for req in download_requests)
    assert len(writes) == 1
    payload = json.loads(writes[0].content.decode("utf-8"))
    assert payload["publisher_count"] == 1
    assert payload["candidate_count"] == 2
    assert payload["publishers"][0]["publisher_name"] == "Activate Consulting"
    assert_logs_have_required_fields(
        [
            json.loads(record.message)
            for record in caplog.records
            if record.name == "market_lense.acquisition_audit_orchestrator"
        ]
    )


def test_run_acquisition_audit_limits_candidates_per_publisher(run_context) -> None:
    download_requests = []

    deps = AcquisitionAuditDependencies(
        list_publishers=lambda req, ctx: PublishersListResponse(
            schema_version="1.0",
            publishers=[
                PublisherListItem(
                    schema_version="1.0",
                    publisher_name="Activate Consulting",
                    homepage="https://www.activate.com/",
                    insights_url="https://www.activate.com/insights",
                    normalized_insights_url="https://www.activate.com/insights",
                    google_folder=None,
                    discovery_test_status=None,
                    inventory_route_kind=None,
                    inventory_route_summary=None,
                    inventory_run_quality_summary=None,
                )
            ],
        ),
        run_publisher_inventory_discovery=lambda req, ctx: _discovery_result(),
        run_report_download=lambda req, ctx: (
            download_requests.append(req)
            or ReportDownloadOrchestratorResult(
                schema_version="1.0",
                source_url=req.url,
                normalized_url=req.url,
                route_kind="pdf_download",
                route_family="direct_pdf_probe",
                route_status="verified",
                outcome="downloaded",
                route_summary="Download the PDF.",
                final_page_url=req.url,
                resolved_target_url=req.url,
                used_memory_route=False,
                route_steps=[
                    BrowserDownloadRouteStep(
                        schema_version="1.0",
                        index=0,
                        action="open",
                        target_text=req.url,
                        target_role="url",
                        target_url=req.url,
                        result="downloaded",
                    )
                ],
                confirmation_evidence=BrowserDownloadConfirmationEvidence(
                    schema_version="1.0",
                    url_changed=False,
                    visible_confirmation_text="",
                    submit_button_state="unchanged",
                    form_disappeared=False,
                    final_page_url=req.url,
                ),
                terminal_evidence=DownloadTerminalEvidence(
                    schema_version="1.0",
                    final_page_url=req.url,
                    final_page_title="",
                    terminal_text_excerpt="",
                    artifact_url=req.url,
                    artifact_kind="pdf",
                    artifact_validation_status="verified",
                    artifact_validation_detail="",
                    confirmation_signal_count=0,
                    traversed_page_urls=[req.url],
                ),
                browser_had_structured_result=False,
                used_candidate_pdf_url=True,
                used_candidate_source_page=False,
                encountered_form_fields=[],
                identity_fields_added=[],
                blocked_reason=None,
                blocked_reason_detail=None,
                downloaded_file_path="./out/download.pdf",
                downloaded_file_name="download.pdf",
                downloaded_mime_type="application/pdf",
                downloaded_size_bytes=42,
                onsite_capture_path=None,
                onsite_capture_format=None,
                onsite_page_count=None,
                onsite_completeness_status=None,
            )
        ),
        write_bytes=lambda req, ctx: WriteBytesResponse(
            schema_version="1.0",
            path=req.path,
            bytes_written=len(req.content),
            md5="abc123",
        ),
    )

    result = run_acquisition_audit(
        AcquisitionAuditBatchRequest(
            schema_version="1.0",
            reports_db="./state/reports.sqlite",
            publisher_inventory_settings=_inventory_settings(),
            browser_download_settings=replace(
                _browser_settings(),
                output_dir="./out/browser_downloads",
            ),
            output_dir="./out",
            delivery_email=None,
            publisher_limit=None,
            candidate_limit_per_publisher=1,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.candidate_count == 1
    assert len(download_requests) == 1
