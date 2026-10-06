from __future__ import annotations

import pytest

from src.contracts.cto_evidence import (
    CTOEvidenceMetric,
    parse_cto_evidence_run,
    validate_cto_evidence_run,
)


def _run_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "run_id": "benchmark-2026-10-06",
        "run_type": "future_tool_benchmark",
        "objective": "Measure a bounded workflow change.",
        "tested_repository_sha": "a" * 40,
        "producer_repository_sha": None,
        "started_at_utc": "2026-10-06T10:00:00Z",
        "ended_at_utc": "2026-10-06T10:05:00Z",
        "subjects": [
            {
                "schema_version": "1.0",
                "subject_id": "subject-1",
                "identity_sha256": "b" * 64,
                "immutable": True,
            }
        ],
        "configuration_identities": [
            {"schema_version": "1.0", "key": "model", "value": "model-x"}
        ],
        "stages_in_scope": ["validation"],
        "stages_out_of_scope": ["publication"],
        "external_side_effects_enabled": False,
        "operator_intervention_policy": "No manual recovery during measurement.",
        "sources": [
            {
                "schema_version": "1.0",
                "source_id": "result",
                "producer": "fixture-producer",
                "format_id": "marketlense/generic-metrics/1.0",
                "path": "docs/quality/result.json",
                "sha256": "c" * 64,
                "tested_repository_sha": "a" * 40,
                "role": "run",
            }
        ],
        "required_evidence_classes": ["outcomes"],
        "criteria": [
            {
                "schema_version": "1.0",
                "criterion_id": "all-ready",
                "description": "Every subject reaches the ready state.",
                "metric_id": "outcomes.ready_count",
                "operator": "eq",
                "expected_value": 1,
                "required": True,
                "stage": "validation",
            }
        ],
        "comparison": None,
    }


def test_run_contract_accepts_open_run_types_and_immutable_subjects() -> None:
    run = parse_cto_evidence_run(_run_payload())

    assert run.run_type == "future_tool_benchmark"
    assert run.subjects[0].immutable is True
    assert run.subjects[0].identity_sha256 == "b" * 64
    assert run.sources[0].sha256 == "c" * 64


def test_run_contract_rejects_invalid_hashes_and_unbounded_fields() -> None:
    payload = _run_payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    source = sources[0]
    assert isinstance(source, dict)
    source["sha256"] = "not-a-sha"

    with pytest.raises(ValueError, match="sha256"):
        parse_cto_evidence_run(payload)

    payload = _run_payload()
    payload["private_prompt"] = "must not enter a CTO contract"
    with pytest.raises(ValueError, match="unexpected"):
        parse_cto_evidence_run(payload)


def test_unavailable_measurement_is_not_zero() -> None:
    unavailable = CTOEvidenceMetric(
        schema_version="1.0",
        metric_id="resource.provider_calls",
        status="unavailable",
        value=None,
        unit="calls",
        source_ids=(),
        limitations=("The producer did not retain run-scoped usage.",),
    )
    assert unavailable.value is None

    with pytest.raises(ValueError, match="unavailable"):
        CTOEvidenceMetric(
            schema_version="1.0",
            metric_id="resource.provider_calls",
            status="unavailable",
            value=0,
            unit="calls",
            source_ids=(),
            limitations=("The producer did not retain run-scoped usage.",),
        )

    observed_zero = CTOEvidenceMetric(
        schema_version="1.0",
        metric_id="side_effects.actual_writes",
        status="observed",
        value=0,
        unit="writes",
        source_ids=("result",),
        limitations=(),
    )
    assert observed_zero.value == 0


def test_comparison_must_preserve_compatibility_and_invariants() -> None:
    run_payload = _run_payload()
    run_payload["comparison"] = {
        "schema_version": "1.0",
        "comparison_id": "before-after",
        "baseline_source_id": "result",
        "candidate_source_id": "result",
        "baseline_selector": "before",
        "candidate_selector": "after",
        "baseline_repository_sha": "d" * 40,
        "candidate_repository_sha": "a" * 40,
        "baseline_identity": [
            {"schema_version": "1.0", "key": "cohort", "value": "cohort-a"}
        ],
        "candidate_identity": [
            {"schema_version": "1.0", "key": "cohort", "value": "cohort-b"}
        ],
        "invariants": [
            {
                "schema_version": "1.0",
                "key": "model",
                "baseline_value": "model-x",
                "candidate_value": "model-x",
            }
        ],
        "changed_variables": ["scheduler_concurrency"],
        "limitations": ["The before/after difference does not establish causation."],
    }

    with pytest.raises(ValueError, match="compatibility"):
        validate_cto_evidence_run(parse_cto_evidence_run(run_payload))


def test_required_immutable_subjects_cannot_be_omitted() -> None:
    payload = _run_payload()
    payload["subjects"] = []
    payload["required_evidence_classes"] = ["immutable_subjects"]

    with pytest.raises(ValueError, match="immutable subjects"):
        parse_cto_evidence_run(payload)


def test_run_timestamps_are_available_or_explicitly_unavailable_as_a_pair() -> None:
    payload = _run_payload()
    payload["started_at_utc"] = None
    payload["ended_at_utc"] = None
    run = parse_cto_evidence_run(payload)
    assert run.started_at_utc is None
    assert run.ended_at_utc is None

    payload["started_at_utc"] = "2026-10-06T10:00:00Z"
    with pytest.raises(ValueError, match="both be present or null"):
        parse_cto_evidence_run(payload)
