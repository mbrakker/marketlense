from __future__ import annotations

from src.contracts.report_store import (
    AcquisitionAttemptResourceRecordRequest,
    AcquisitionAttemptResourceSummary,
    AcquisitionResourceAggregateRequest,
    AcquisitionRouteSuppressionRequest,
)
from src.contracts.run_context import RunContext
from src.services.report_store_service import (
    evaluate_acquisition_route_suppression,
    list_acquisition_resource_aggregates,
    record_acquisition_attempt_resource,
)


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="acq-run", task_id="task", span_id="span"
    )


def _summary(
    *, attempt_id: str, outcome: str, reason: str = ""
) -> AcquisitionAttemptResourceSummary:
    return AcquisitionAttemptResourceSummary(
        schema_version="1.0",
        attempt_id=attempt_id,
        publisher_id="publisher-a",
        source_identity_id="source-1" if outcome == "success" else "",
        source_identity_status="resolved" if outcome == "success" else "unresolved",
        normalized_url="https://publisher.example/report",
        route_family="browser_email_form",
        route_policy_version="1.0",
        source_policy_compatibility_hash="policy-a",
        started_at_utc="2026-07-19T10:00:00+00:00",
        completed_at_utc="2026-07-19T10:00:01+00:00",
        elapsed_ms=1000,
        terminal_outcome=outcome,
        browser_launches=0 if outcome == "success" else 1,
        browser_steps=0 if outcome == "success" else 4,
        browser_model_calls=0 if outcome == "success" else 2,
        input_tokens=0 if outcome == "success" else 120,
        cached_input_tokens=0,
        output_tokens=0 if outcome == "success" else 40,
        terminal_reason=reason,
        verified_artifact_hash="md5:abc" if outcome == "success" else "",
        estimated_cost_usd=0.0 if outcome == "success" else 0.012,
        incomplete_fields=("mailbox_reads",) if outcome == "success" else (),
    )


def _record(tmp_path, summary: AcquisitionAttemptResourceSummary) -> None:
    record_acquisition_attempt_resource(
        AcquisitionAttemptResourceRecordRequest(
            schema_version="1.0",
            db_path=str(tmp_path / "reports.sqlite"),
            summary=summary,
        ),
        _ctx(),
    )


def _suppression_request(tmp_path, **overrides) -> AcquisitionRouteSuppressionRequest:
    values = {
        "schema_version": "1.0",
        "db_path": str(tmp_path / "reports.sqlite"),
        "normalized_url": "https://publisher.example/report",
        "publisher_id": "publisher-a",
        "route_family": "browser_email_form",
        "policy_version": "1.0",
        "source_policy_compatibility_hash": "policy-a",
        "enabled": True,
        "minimum_sample_size": 3,
        "terminal_failure_threshold": 1.0,
        "terminal_failure_classes": ("blocked_captcha", "blocked_email_domain"),
        "ttl_seconds": 60,
        "now_utc": "2026-07-19T10:02:00+00:00",
    }
    values.update(overrides)
    return AcquisitionRouteSuppressionRequest(**values)


def test_aggregate_keeps_incomplete_records_distinct_from_zero_usage(tmp_path) -> None:
    _record(tmp_path, _summary(attempt_id="direct-success", outcome="success"))

    aggregate = list_acquisition_resource_aggregates(
        AcquisitionResourceAggregateRequest(
            schema_version="1.0", db_path=str(tmp_path / "reports.sqlite")
        ),
        _ctx(),
    ).aggregates

    assert len(aggregate) == 1
    row = aggregate[0]
    assert row.sample_size == 1
    assert row.verified_acquisition_count == 1
    assert row.estimated_cost_usd == 0.0
    assert row.incomplete_record_count == 1
    assert row.cost_per_verified_acquisition_usd == 0.0


def test_terminal_suppression_requires_three_compatible_failures_and_expires(
    tmp_path,
) -> None:
    _record(
        tmp_path,
        _summary(attempt_id="failure-1", outcome="failed", reason="blocked_captcha"),
    )
    _record(
        tmp_path,
        _summary(attempt_id="failure-2", outcome="failed", reason="blocked_captcha"),
    )

    below_threshold = evaluate_acquisition_route_suppression(
        _suppression_request(tmp_path), _ctx()
    )

    assert not below_threshold.suppressed
    assert below_threshold.reason == "insufficient_terminal_failure_evidence"

    _record(
        tmp_path,
        _summary(attempt_id="failure-3", outcome="failed", reason="blocked_captcha"),
    )
    active = evaluate_acquisition_route_suppression(
        _suppression_request(tmp_path), _ctx()
    )

    assert active.suppressed
    assert active.sample_size == 3
    assert active.terminal_failure_count == 3

    expired = evaluate_acquisition_route_suppression(
        _suppression_request(tmp_path, now_utc="2026-07-19T10:04:00+00:00"), _ctx()
    )

    assert expired.suppressed
    assert expired.decision_id != active.decision_id


def test_changed_policy_and_explicit_revalidation_do_not_suppress(tmp_path) -> None:
    for index in range(3):
        _record(
            tmp_path,
            _summary(
                attempt_id=f"failure-{index}",
                outcome="failed",
                reason="blocked_email_domain",
            ),
        )

    activated = evaluate_acquisition_route_suppression(
        _suppression_request(tmp_path), _ctx()
    )
    changed_policy = evaluate_acquisition_route_suppression(
        _suppression_request(tmp_path, source_policy_compatibility_hash="policy-b"),
        _ctx(),
    )
    explicit_revalidation = evaluate_acquisition_route_suppression(
        _suppression_request(tmp_path, revalidation_override=True), _ctx()
    )

    assert not changed_policy.suppressed
    assert changed_policy.sample_size == 0
    assert not explicit_revalidation.suppressed
    assert explicit_revalidation.reason == "explicit_revalidation_override"

    response = record_acquisition_attempt_resource(
        AcquisitionAttemptResourceRecordRequest(
            schema_version="1.0",
            db_path=str(tmp_path / "reports.sqlite"),
            summary=AcquisitionAttemptResourceSummary(
                **{
                    **_summary(attempt_id="revalidated", outcome="success").__dict__,
                    "revalidation_override": True,
                }
            ),
        ),
        _ctx(),
    )
    after_success = evaluate_acquisition_route_suppression(
        _suppression_request(tmp_path), _ctx()
    )

    assert activated.suppressed
    assert response.superseded_suppression_count == 1
    assert not after_success.suppressed
