from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.cto_evidence import (
    CTOEvidenceOutcomeCount,
    cto_evidence_bundle_payload,
    validate_cto_evidence_bundle,
)
from tests.test_cto_evidence_projection import (
    BASELINE_SHA,
    RUN_SHA,
    _generic_payload,
    _project,
    _run_manifest,
    _source,
)


def test_complete_outcome_totals_must_match_subject_terminal_outcomes(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "repo" / "evidence" / "metrics.json",
        payload=_generic_payload(),
    )
    _, bundle = _project(
        tmp_path,
        _run_manifest(sources=[source], required=["outcomes"]),
    )

    assert bundle.completeness == "complete"
    assert bundle.run_evidence is not None
    contradictory_outcomes = (
        CTOEvidenceOutcomeCount(schema_version="1.0", outcome="success", count=2),
    )
    contradictory_evidence = replace(
        bundle.run_evidence, outcomes=contradictory_outcomes
    )
    contradictory_summary = replace(
        bundle.executive_summary, outcomes=contradictory_outcomes
    )
    contradictory_bundle = replace(
        bundle,
        run_evidence=contradictory_evidence,
        executive_summary=contradictory_summary,
    )

    with pytest.raises(ValueError, match="outcome totals do not reconcile"):
        validate_cto_evidence_bundle(contradictory_bundle)


def test_artifact_dag_comparison_verifies_each_endpoint_sha(tmp_path: Path) -> None:
    dag_path = tmp_path / "repo" / "evidence" / "dag.json"
    dag_payload = {
        "implementation": {"base_commit": BASELINE_SHA, "dag_commit": RUN_SHA},
        "before": {"duration_seconds": 12.0},
        "after": {"duration_seconds": 8.0},
        "comparison": {"measurement_limit": "Matched local benchmark runs."},
    }
    baseline = _source(
        dag_path,
        source_id="baseline",
        tested_sha=BASELINE_SHA,
        role="baseline",
        format_id="marketlense/artifact-dag-benchmark/1.0",
        payload=dag_payload,
    )
    candidate = _source(
        dag_path,
        source_id="candidate",
        tested_sha=RUN_SHA,
        role="candidate",
        format_id="marketlense/artifact-dag-benchmark/1.0",
        payload=dag_payload,
    )
    identity = [{"schema_version": "1.0", "key": "cohort", "value": "same-cohort"}]
    comparison = {
        "schema_version": "1.0",
        "comparison_id": "dag-before-after",
        "baseline_source_id": "baseline",
        "candidate_source_id": "candidate",
        "baseline_selector": "before",
        "candidate_selector": "after",
        "baseline_repository_sha": BASELINE_SHA,
        "candidate_repository_sha": RUN_SHA,
        "baseline_identity": identity,
        "candidate_identity": identity,
        "invariants": [],
        "changed_variables": ["artifact_scheduling"],
        "limitations": ["Local timings may vary."],
    }
    _, bundle = _project(
        tmp_path,
        _run_manifest(
            sources=[baseline, candidate],
            required=["comparison"],
            comparison=comparison,
        ),
    )

    assert bundle.completeness == "complete"
    assert bundle.run_evidence is not None
    assert bundle.run_evidence.comparison is not None
    assert bundle.run_evidence.comparison.status == "compatible"
    assert bundle.run_evidence.comparison.metric_deltas[0].value == -4.0


def test_crop_qa_uses_existing_sidecar_and_hashes_candidate_identity(
    tmp_path: Path,
) -> None:
    candidate_id = "fixture-crop-candidate"
    sidecar = _source(
        tmp_path / "repo" / candidate_id / "crop.qa.json",
        source_id="crop_qa",
        format_id="marketlense/crop-qa-sidecar/1.0",
        payload={
            "candidate_id": candidate_id,
            "candidate_type": "figure",
            "mode": "publication_strict",
            "accepted": True,
            "render_dpi": 300,
            "qa": {
                "accepted": True,
                "total_score": 0.9,
                "defect_labels": [],
                "detectors": {},
            },
        },
    )
    manifest = _run_manifest(
        sources=[sidecar],
        required=["immutable_subjects", "visual_quality"],
    )
    subjects = manifest["subjects"]
    assert isinstance(subjects, list) and isinstance(subjects[0], dict)
    subjects[0]["identity_sha256"] = hashlib.sha256(
        candidate_id.encode("utf-8")
    ).hexdigest()
    _, bundle = _project(tmp_path, manifest)

    assert bundle.completeness == "complete"
    assert bundle.run_evidence is not None
    assert bundle.run_evidence.quality_dimensions[0].reviewed_subject_count == 1
    assert candidate_id not in json.dumps(cto_evidence_bundle_payload(bundle))
