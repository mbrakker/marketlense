from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadRouteStep,
    BrowserReportDownloadResult,
    DownloadTerminalEvidence,
)
from src.services._browser_report_download._browser_runtime.action_evidence import (
    capture_browser_execution_route_steps,
)
from src.services._browser_report_download.playbooks import (
    promote_validated_browser_route_result_to_playbook,
)


def test_validated_route_promotion_rejects_fabricated_model_action_evidence(
    tmp_path: Path,
    run_context,
) -> None:
    response = _promote(
        tmp_path,
        replace(_result(), execution_route_steps=[]),
        run_context,
    )

    assert response.status == "not_promotable"
    assert response.reason == "browser_execution_evidence_missing"
    assert response.path == ""
    assert not (tmp_path / "playbooks").exists()


def test_validated_route_promotion_uses_resolved_browser_action_evidence(
    tmp_path: Path,
    run_context,
) -> None:
    action = SimpleNamespace(
        model_dump=lambda **_kwargs: {"click": {"index": 7}}
    )
    history = SimpleNamespace(
        history=[
            SimpleNamespace(
                model_output=SimpleNamespace(action=[action]),
                result=[SimpleNamespace(error=None, success=None)],
                state=SimpleNamespace(
                    interacted_element=[
                        SimpleNamespace(
                            attributes={"role": "button"},
                            ax_name="Get the verified report",
                        )
                    ]
                ),
            ),
            SimpleNamespace(
                model_output=None,
                result=[],
                state=SimpleNamespace(
                    url="https://example.com/verified-report.pdf",
                    title="Verified report download",
                ),
            ),
        ]
    )
    execution_steps = capture_browser_execution_route_steps(history=history)
    result = replace(
        _result(),
        route_steps=[
            replace(
                _result().route_steps[0],
                locator_name="Fabricated model control",
                locator_evidence=["locator:role:button:Fabricated model control"],
                expected_url_contains="/fabricated",
                postcondition_evidence=["url:/fabricated"],
            )
        ],
        execution_route_steps=execution_steps,
    )

    response = _promote(tmp_path, result, run_context)

    assert execution_steps[0].locator_evidence == [
        "locator:role:button:Get the verified report"
    ]
    assert execution_steps[0].postcondition_evidence == [
        "url:https://example.com/verified-report.pdf",
        "text:Verified report download",
    ]
    assert response.status == "created"
    payload = (tmp_path / "playbooks" / f"{response.playbook_id}.yaml").read_text(
        encoding="utf-8"
    )
    assert "Get the verified report" in payload
    assert "Fabricated model control" not in payload


def test_browser_action_evidence_binds_each_action_to_its_next_browser_state() -> None:
    first_action = SimpleNamespace(
        model_dump=lambda **_kwargs: {"click": {"index": 1}}
    )
    final_action = SimpleNamespace(
        model_dump=lambda **_kwargs: {"click": {"index": 2}}
    )
    history = SimpleNamespace(
        history=[
            _history_entry(
                action=first_action,
                role="button",
                name="Open form",
                url="https://example.com/report",
                title="Report",
            ),
            _history_entry(
                action=final_action,
                role="button",
                name="Request report",
                url="https://example.com/request",
                title="Request form",
            ),
        ]
    )

    steps = capture_browser_execution_route_steps(
        history=history,
        final_page_url="https://example.com/confirmed",
        final_page_title="Request confirmed",
    )

    assert steps[0].postcondition_evidence == [
        "url:https://example.com/request",
        "text:Request form",
    ]
    assert steps[1].postcondition_evidence == [
        "url:https://example.com/confirmed",
        "text:Request confirmed",
    ]


def test_browser_action_evidence_classifies_clicked_submit_button_from_runtime_element(
) -> None:
    step = capture_browser_execution_route_steps(
        history=SimpleNamespace(
            history=[
                _history_entry(
                    action=SimpleNamespace(
                        model_dump=lambda **_kwargs: {"click": {"index": 1}}
                    ),
                    role="button",
                    name="Request report",
                    url="https://example.com/requested",
                    title="Request received",
                    node_name="BUTTON",
                    attributes={"role": "button", "type": "submit"},
                )
            ]
        ),
        final_page_url="https://example.com/requested",
        final_page_title="Request received",
    )[0]

    assert step.action == "submit"


def test_browser_action_evidence_classifies_clicked_submit_input_from_runtime_element(
) -> None:
    step = capture_browser_execution_route_steps(
        history=SimpleNamespace(
            history=[
                _history_entry(
                    action=SimpleNamespace(
                        model_dump=lambda **_kwargs: {"click": {"index": 1}}
                    ),
                    role="button",
                    name="Send me the report",
                    url="https://example.com/requested",
                    title="Request received",
                    node_name="input",
                    attributes={"role": "button", "type": "submit"},
                )
            ]
        ),
        final_page_url="https://example.com/requested",
        final_page_title="Request received",
    )[0]

    assert step.action == "submit"


def test_browser_action_evidence_keeps_ordinary_button_click_despite_model_submit_claim(
) -> None:
    step = capture_browser_execution_route_steps(
        history=SimpleNamespace(
            history=[
                _history_entry(
                    action=SimpleNamespace(
                        model_dump=lambda **_kwargs: {
                            "click": {"index": 1},
                            "submit": {"claimed": True},
                        }
                    ),
                    role="button",
                    name="Show pricing",
                    url="https://example.com/pricing",
                    title="Pricing",
                    node_name="button",
                    attributes={"role": "button", "type": "button"},
                )
            ]
        ),
        final_page_url="https://example.com/pricing",
        final_page_title="Pricing",
    )[0]

    assert step.action == "click"


def test_browser_action_evidence_keeps_identity_values_unpersisted() -> None:
    action = SimpleNamespace(
        model_dump=lambda **_kwargs: {"input": {"index": 3, "text": "ops@example.com"}}
    )
    history = SimpleNamespace(
        history=[
            _history_entry(
                action=action,
                role="textbox",
                name="Work email",
                url="https://example.com/request",
                title="Request form",
            )
        ]
    )

    step = capture_browser_execution_route_steps(
        history=history,
        final_page_url="https://example.com/request?email=ops@example.com",
        final_page_title="Request for ops@example.com",
        identity_value_references={"ops@example.com": "identity.delivery_email"},
    )[0]

    assert step.identity_field_reference == "identity.delivery_email"
    assert step.postcondition_evidence == ["url:https://example.com/request"]
    assert "ops@example.com" not in str(asdict(step))


def test_validated_route_promotion_rejects_wrong_locator_evidence(
    tmp_path: Path,
    run_context,
) -> None:
    result = replace(
        _result(),
        execution_route_steps=[
            replace(_result().execution_route_steps[0], locator_name="Wrong control")
        ],
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
        execution_route_steps=[
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
        execution_route_steps=[
            replace(_result().execution_route_steps[0], postcondition_evidence=[])
        ],
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
        _result().execution_route_steps[0],
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
        execution_route_steps=[click_step, fill_step],
    )

    response = _promote(tmp_path, result, run_context)

    assert response.status == "not_promotable"
    assert response.reason == "missing_terminal_submit"
    assert response.path == ""
    assert not (tmp_path / "playbooks").exists()


def test_validated_email_route_with_runtime_submit_can_be_promoted(
    tmp_path: Path,
    run_context,
) -> None:
    submit_step = capture_browser_execution_route_steps(
        history=SimpleNamespace(
            history=[
                _history_entry(
                    action=SimpleNamespace(
                        model_dump=lambda **_kwargs: {"click": {"index": 1}}
                    ),
                    role="button",
                    name="Request report",
                    url="https://example.com/requested",
                    title="Request received",
                    node_name="button",
                    attributes={"role": "button", "type": "submit"},
                )
            ]
        ),
        final_page_url="https://example.com/requested",
        final_page_title="Request received",
    )[0]
    result = replace(
        _result(),
        route_kind="email_delivery",
        route_family="browser_email_form",
        outcome="email_requested",
        execution_route_steps=[submit_step],
    )

    response = _promote(tmp_path, result, run_context)

    assert response.status == "created"
    assert response.reason == ""


def test_validated_email_route_with_runtime_non_submit_click_is_not_promotable(
    tmp_path: Path,
    run_context,
) -> None:
    click_step = capture_browser_execution_route_steps(
        history=SimpleNamespace(
            history=[
                _history_entry(
                    action=SimpleNamespace(
                        model_dump=lambda **_kwargs: {"click": {"index": 1}}
                    ),
                    role="button",
                    name="Show pricing",
                    url="https://example.com/pricing",
                    title="Pricing",
                    node_name="button",
                    attributes={"role": "button", "type": "button"},
                )
            ]
        ),
        final_page_url="https://example.com/pricing",
        final_page_title="Pricing",
    )[0]
    result = replace(
        _result(),
        route_kind="email_delivery",
        route_family="browser_email_form",
        outcome="email_requested",
        execution_route_steps=[click_step],
    )

    response = _promote(tmp_path, result, run_context)

    assert response.status == "not_promotable"
    assert response.reason == "missing_terminal_submit"


def _promote(tmp_path: Path, result: BrowserReportDownloadResult, run_context):
    return promote_validated_browser_route_result_to_playbook(
        playbook_dir=str(tmp_path / "playbooks"),
        result=result,
        ctx=run_context,
        observed_at="2026-08-16T13:00:00+00:00",
    )


def _history_entry(
    *,
    action,
    role: str,
    name: str,
    url: str,
    title: str,
    node_name: str = "",
    attributes: dict[str, str] | None = None,
):
    return SimpleNamespace(
        model_output=SimpleNamespace(action=[action]),
        result=[SimpleNamespace(error=None, success=None)],
        state=SimpleNamespace(
            url=url,
            title=title,
            interacted_element=[
                SimpleNamespace(
                    attributes=attributes or {"role": role},
                    ax_name=name,
                    node_name=node_name,
                )
            ],
        ),
    )


def _result() -> BrowserReportDownloadResult:
    execution_step = BrowserDownloadRouteStep(
        schema_version="1.0",
        index=0,
        action="click",
        target_text="Download report",
        target_role="button",
        target_url="https://example.com/report.pdf",
        result="Downloaded report.",
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
        route_status="verified",
        outcome="downloaded",
        route_summary="Use the download control.",
        final_page_url="https://example.com/report.pdf",
        resolved_target_url="https://example.com/report.pdf",
        used_route_hint=False,
        route_steps=[execution_step],
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
        execution_route_steps=[execution_step],
    )
