from __future__ import annotations

import hashlib
import json

from src.contracts.logging import MAX_LOG_EVENT_BYTES
from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserReportDownloadResult,
    DownloadTerminalEvidence,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.logging import (
    browser_download_result_log_fields,
)
from src.utils.logging import (
    child_context,
    log_event,
    new_run_context,
    validate_log_event_payload,
)


def test_log_event_matches_unified_schema() -> None:
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-1",
        task_id="task-1",
        span_id="span-1",
    )

    payload = log_event(
        ctx,
        role="service",
        event="service_started",
        module="src.services.example",
        fields={"authorization": "Bearer secret-token", "count": 1},
    )
    result = validate_log_event_payload(payload)

    assert result.valid is True
    assert result.missing_fields == ()
    assert result.invalid_fields == ()
    assert '"trace_id": "run-1"' in payload
    assert '"span_name": "task-1"' in payload
    assert "secret-token" not in payload


def test_child_context_preserves_trace_and_parent_span() -> None:
    root = new_run_context(task_id="root")
    child = child_context(root, task_id="child")

    assert child.trace_id == root.trace_id
    assert child.parent_span_id == root.span_id
    assert child.span_name == "child"
    assert child.span_depth == root.span_depth + 1


def test_log_event_schema_reports_missing_and_invalid_fields() -> None:
    result = validate_log_event_payload(
        {"run_id": "", "role": "controller", "fields": "not-a-dict"}
    )

    assert result.valid is False
    assert result.missing_fields == (
        "event",
        "module",
        "parent_span_id",
        "span_depth",
        "span_id",
        "span_name",
        "task_id",
        "timestamp_utc",
        "trace_id",
    )
    assert result.invalid_fields == ("fields", "role", "run_id")


def test_log_event_redacts_sensitive_url_query_values() -> None:
    ctx = new_run_context(task_id="redaction-test")
    payload = log_event(
        ctx,
        role="service",
        event="http_request",
        module="src.services.example",
        fields={
            "url": (
                "https://example.com/thank-you?"
                "downloadData=report&email=ops%40example.com&token=secret-token"
            ),
            "nested": {
                "final_url": "https://example.com/report?sig=abc123&email=ops@example.com"
            },
            "events": [
                {
                    "target_url": (
                        "https://example.com/report?mkt_tok=abc&"
                        "signature=def&email=ops%40example.com"
                    )
                }
            ],
        },
    )

    assert "ops@example.com" not in payload
    assert "ops%40example.com" not in payload
    assert "secret-token" not in payload
    assert "abc123" not in payload
    assert "email=***REDACTED***" in payload
    assert "token=***REDACTED***" in payload
    assert "sig=***REDACTED***" in payload


def test_log_event_summarizes_report_and_editorial_text() -> None:
    source_paragraph = "Source evidence paragraph " + ("with retained detail " * 12)
    editorial_paragraph = "Generated editorial paragraph " + (
        "with publishable analysis " * 12
    )
    payload = log_event(
        new_run_context(task_id="content-redaction-test"),
        role="generator",
        event="report_generated",
        module="src.generators.example",
        fields={
            "source_text": source_paragraph,
            "linkedin_post": editorial_paragraph,
            "unlabeled": source_paragraph,
            "evidence": [source_paragraph],
        },
    )

    assert source_paragraph not in payload
    assert editorial_paragraph not in payload
    assert hashlib.sha256(source_paragraph.encode("utf-8")).hexdigest() in payload
    assert hashlib.sha256(editorial_paragraph.encode("utf-8")).hexdigest() in payload
    assert '"redaction": "***REDACTED***"' in payload


def test_log_event_bounds_oversized_nested_fields_deterministically() -> None:
    source_paragraph = "Known source paragraph that must never be logged. " * 20
    nested = [
        {f"field_{index}_{column}": source_paragraph for column in range(20)}
        for index in range(20)
    ]
    ctx = new_run_context(task_id="bounded-nested-fields")

    first = json.loads(
        log_event(
            ctx,
            role="service",
            event="bounded_nested_fields",
            module="src.services.example",
            fields={"nested": nested},
        )
    )
    second = json.loads(
        log_event(
            ctx,
            role="service",
            event="bounded_nested_fields",
            module="src.services.example",
            fields={"nested": nested},
        )
    )

    assert (
        len(json.dumps(first, ensure_ascii=True).encode("utf-8")) <= MAX_LOG_EVENT_BYTES
    )
    assert source_paragraph not in json.dumps(first, ensure_ascii=True)
    assert first["fields"] == second["fields"]
    assert first["fields"]["log_payload_reduced"] == {
        "attempted_size_bytes": first["fields"]["log_payload_reduced"][
            "attempted_size_bytes"
        ],
        "maximum_size_bytes": MAX_LOG_EVENT_BYTES,
        "original_field_count": 1,
        "omitted_field_count": 0,
    }


def test_log_event_bounds_many_artifact_references_without_silent_loss() -> None:
    artifact_references = {
        f"artifact_reference_{index:02d}": f"out/audit/{index:02d}/" + "a" * 480
        for index in range(32)
    }

    payload = json.loads(
        log_event(
            new_run_context(task_id="bounded-artifact-references"),
            role="service",
            event="bounded_artifact_references",
            module="src.services.example",
            fields=artifact_references,
        )
    )

    assert (
        len(json.dumps(payload, ensure_ascii=True).encode("utf-8"))
        <= MAX_LOG_EVENT_BYTES
    )
    reduction = payload["fields"]["log_payload_reduced"]
    assert (
        reduction["hashed_artifact_reference_count"]
        + reduction["omitted_artifact_reference_count"]
        > 0
    )
    assert reduction["original_field_count"] == len(artifact_references)


def test_log_event_keeps_long_plural_artifacts_root_reference() -> None:
    artifact_root = "out/" + ("deep/" * 32)

    payload = json.loads(
        log_event(
            new_run_context(task_id="plural-artifacts-root"),
            role="generator",
            event="artifact_root_observed",
            module="src.generators.example",
            fields={"recent_artifacts_root": artifact_root},
        )
    )

    assert payload["fields"]["recent_artifacts_root"] == artifact_root


def test_log_event_redacts_email_phone_credentials_and_sensitive_url_values() -> None:
    payload = log_event(
        new_run_context(task_id="sensitive-patterns"),
        role="service",
        event="sensitive_patterns",
        module="src.services.example",
        fields={
            "email_content": "Contact alex@example.com at +1 (415) 555-0199",
            "password": "not-for-logs",
            "url": "https://example.com/report?signature=secret-value",
        },
    )

    assert "alex@example.com" not in payload
    assert "415) 555-0199" not in payload
    assert "not-for-logs" not in payload
    assert "secret-value" not in payload


def test_browser_completion_summary_excludes_terminal_and_form_content() -> None:
    terminal_excerpt = "Terminal excerpt with private business-email guidance."
    form_field = "Work email address"
    result = BrowserReportDownloadResult(
        schema_version="1.0",
        source_url="https://example.com/report",
        normalized_url="https://example.com/report",
        route_kind="email_delivery",
        route_family="browser_email_form",
        route_status="verified",
        outcome="email_required",
        route_summary="Submitted form",
        final_page_url="https://example.com/confirmation",
        resolved_target_url="https://example.com/confirmation",
        used_route_hint=False,
        route_steps=[],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=True,
            visible_confirmation_text="A private confirmation message",
            submit_button_state="replaced",
            form_disappeared=True,
            final_page_url="https://example.com/confirmation",
            confirmation_score=3,
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url="https://example.com/confirmation",
            final_page_title="Private page title",
            terminal_text_excerpt=terminal_excerpt,
            artifact_url="https://example.com/report.pdf?token=secret-value",
            artifact_kind="email_delivery",
            artifact_validation_status="blocked",
            artifact_validation_detail="A private terminal detail",
            confirmation_signal_count=3,
            html_snapshot_path="out/audit/terminal.html",
            screenshot_path="out/audit/terminal.png",
        ),
        browser_had_structured_result=True,
        used_candidate_pdf_url=False,
        used_candidate_source_page=False,
        encountered_form_fields=[form_field],
        blocked_reason="blocked_email_domain",
        blocked_reason_detail="Private domain restriction detail",
        downloaded_file_path=None,
        downloaded_file_name=None,
        downloaded_mime_type=None,
        downloaded_size_bytes=None,
        onsite_capture_path=None,
        onsite_capture_format=None,
        onsite_page_count=None,
        onsite_completeness_status=None,
    )

    payload = log_event(
        new_run_context(task_id="browser-complete"),
        role="service",
        event="browser_report_download_complete",
        module="src.services.browser_report_download_service",
        fields=browser_download_result_log_fields(result),
    )

    assert terminal_excerpt not in payload
    assert form_field not in payload
    assert "secret-value" not in payload
    assert '"confirmation_score": 3' in payload
    assert '"blocker_code": "blocked_email_domain"' in payload
    assert '"html_snapshot_audit_ref": "out/audit/terminal.html"' in payload
