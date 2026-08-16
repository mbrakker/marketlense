from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadRouteStep,
    BrowserReportDownloadResult,
    DownloadTerminalEvidence,
)
from src.services._browser_report_download.playbooks import (
    promote_validated_browser_route_result_to_playbook,
)


def test_validated_route_promotion_rejects_wrong_locator_evidence(
    tmp_path: Path,
    run_context,
) -> None:
    result = replace(
        _result(),
        route_steps=[replace(_result().route_steps[0], locator_name="Wrong control")],
    )

    response = _promote(tmp_path, result, run_context)

    assert response.status == "not_promotable"
    assert response.reason == "step_0_locator_evidence_not_bound"
    assert response.path == ""
    assert not (tmp_path / "playbooks").exists()


def test_validated_route_promotion_rejects_locator_synthesized_from_target_prose(
    tmp_path: Path,
    run_context,
) -> None:
    result = replace(
        _result(),
        route_steps=[
            replace(
                _result().route_steps[0],
                locator_role="",
                locator_name="",
            )
        ],
    )

    response = _promote(tmp_path, result, run_context)

    assert response.status == "not_promotable"
    assert response.reason == "step_0_stable_locator_missing"
    assert response.path == ""
    assert not (tmp_path / "playbooks").exists()


def test_validated_route_promotion_rejects_terminal_only_postcondition_evidence(
    tmp_path: Path,
    run_context,
) -> None:
    result = replace(
        _result(),
        route_steps=[replace(_result().route_steps[0], postcondition_evidence=[])],
    )

    response = _promote(tmp_path, result, run_context)

    assert response.status == "not_promotable"
    assert response.reason == "step_0_postcondition_evidence_not_bound"
    assert response.path == ""
    assert not (tmp_path / "playbooks").exists()


def test_validated_route_promotion_rejects_email_route_missing_final_submit(
    tmp_path: Path,
    run_context,
) -> None:
    click_step = replace(
        _result().route_steps[0],
        action="click",
        expected_url_contains="/request",
        postcondition_evidence=["url:/request"],
    )
    fill_step = BrowserDownloadRouteStep(
        schema_version="1.0",
        index=1,
        action="fill",
        target_text="Work email",
        target_role="textbox",
        target_url="https://example.com/request",
        result="Filled work email.",
        expected_evidence=["page_info"],
        observed_evidence=["page_info"],
        verification_status="verified",
        locator_label="Work email",
        identity_field_reference="identity.delivery_email",
        expected_text="Work email",
        locator_evidence=["locator:label:Work email"],
        postcondition_evidence=["text:Work email"],
    )
    result = replace(
        _result(),
        route_kind="email_delivery",
        route_family="browser_email_form",
        outcome="email_requested",
        route_steps=[click_step, fill_step],
    )

    response = _promote(tmp_path, result, run_context)

    assert response.status == "not_promotable"
    assert response.reason == "missing_terminal_submit"
    assert response.path == ""
    assert not (tmp_path / "playbooks").exists()


def _promote(tmp_path: Path, result: BrowserReportDownloadResult, run_context):
    return promote_validated_browser_route_result_to_playbook(
        playbook_dir=str(tmp_path / "playbooks"),
        result=result,
        ctx=run_context,
        observed_at="2026-08-16T13:00:00+00:00",
    )


def _result() -> BrowserReportDownloadResult:
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url="https://example.com/research/report",
        normalized_url="https://example.com/research/report",
        route_kind="pdf_download",
        route_family="browser_pdf_click",
        route_status="verified",
        outcome="downloaded",
        route_summary="Use the download control.",
        final_page_url="https://example.com/report.pdf",
        resolved_target_url="https://example.com/report.pdf",
        used_route_hint=False,
        route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="click",
                target_text="Download report",
                target_role="button",
                target_url="https://example.com/report.pdf",
                result="Downloaded report.",
                expected_evidence=["artifact"],
                observed_evidence=["artifact"],
                verification_status="verified",
                locator_role="button",
                locator_name="Download report",
                expected_url_contains="/report.pdf",
                locator_evidence=["locator:role:button:Download report"],
                postcondition_evidence=["url:/report.pdf"],
            )
        ],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=True,
            visible_confirmation_text="",
            submit_button_state="",
            form_disappeared=False,
            final_page_url="https://example.com/report.pdf",
            confirmation_score=1,
            signal_labels=["artifact"],
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url="https://example.com/report.pdf",
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
    )
