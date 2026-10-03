# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_validation_repair_scorecard.py"
)

from ._split_support_test_validation_repair_scorecard import *  # noqa: F401,F403


def test_repair_scorecard_excludes_explicitly_nonreproducible_cases(
    tmp_path: Path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    audit_root = tmp_path / "audits"
    _create_manifest(reports_db, "report-1")
    _create_manifest(reports_db, "report-2")
    initial_one = FailureFingerprint(
        rule_id="grounding",
        affected_section="summary",
        entity_id="failure-a",
        evidence_ids=["finding-1"],
    ).key
    initial_two = FailureFingerprint(
        rule_id="grounding",
        affected_section="summary",
        entity_id="failure-b",
        evidence_ids=["finding-1"],
    ).key
    baseline_manifest = {
        "schema_version": "2.0",
        "frozen": True,
        "baseline_identity": {
            "configuration_hash": "configuration-hash",
            "policy_hash": "policy-hash",
            "producer_build_identity": "build-sha",
            "validator_identity": "validator-v1",
            "schema_identity_sha256": "2" * 64,
        },
        "cases": [],
    }
    for report_id, fingerprint in (
        ("report-1", initial_one),
        ("report-2", initial_two),
    ):
        failure_id = "failure-a" if report_id == "report-1" else "failure-b"
        baseline_manifest["cases"].append(
            {
                "case_id": f"case-{report_id}",
                "report_id": report_id,
                "original_artifact_canonical_sha256": "b" * 64,
                "initial_validation_sha256": "e" * 64,
                "initial_failure_fingerprints": [fingerprint],
                "evidence_pack_sha256": {"findings": "f" * 64},
                "expected_legal_mutation_scope": ["summary.tldr"],
                "identities": {
                    "prompt_identity_sha256": "1" * 64,
                    "artifact_schema_identity": "schema-" + "2" * 64,
                    "validator_identity": "validator-v1",
                    "configuration_hash": "configuration-hash",
                    "policy_hash": "policy-hash",
                    "producer_build_identity": "build-sha",
                },
                "historical_outcome": "rolled_back_validation_fail",
                "baseline_attempts": [
                    _audit(
                        report_id=report_id,
                        promotion_outcome="rolled_back",
                        persisting=(failure_id,),
                    )
                ],
            }
        )
    canonical = (
        json.dumps(
            baseline_manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    )
    baseline_manifest["manifest_sha256"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    manifest_path = tmp_path / "frozen-benchmark.json"
    manifest_path.write_text(json.dumps(baseline_manifest), encoding="utf-8")

    current_audit = _audit(
        report_id="report-1",
        promotion_outcome="rolled_back",
        persisting=("failure-a",),
    )
    audit_path = audit_root / "report-1" / "report_analysis"
    audit_path.mkdir(parents=True)
    (audit_path / "regeneration_candidate_audit_1.json").write_text(
        json.dumps(current_audit), encoding="utf-8"
    )
    identity = ValidationReliabilityValidationIdentity(
        schema_version="1.0",
        validator_identity="validator-v1",
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_build_identity="build-sha",
    )
    attributions = (
        ValidationReliabilityBenchmarkCaseAttribution(
            schema_version="1.0",
            case_id="case-report-1",
            report_id="report-1",
            reproducibility_status="reproducible",
            historical_failure_fingerprints=(initial_one,),
            current_baseline_failure_fingerprints=(initial_one,),
            current_baseline_issue_fingerprints=(initial_one,),
            baseline_validation_identity=identity,
            candidate_validation_identity=identity,
            candidate_validation_attempt_count=1,
            candidate_audit_count=1,
        ),
        ValidationReliabilityBenchmarkCaseAttribution(
            schema_version="1.0",
            case_id="case-report-2",
            report_id="report-2",
            reproducibility_status="no_longer_reproducible",
            historical_failure_fingerprints=(initial_two,),
            current_baseline_failure_fingerprints=(),
            current_baseline_issue_fingerprints=(),
            baseline_validation_identity=identity,
            candidate_validation_identity=None,
            candidate_validation_attempt_count=0,
            candidate_audit_count=0,
        ),
    )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
            repair_evidence_root=str(audit_root),
            repair_benchmark_manifest_path=str(manifest_path),
            current_schema_identity_sha256="2" * 64,
            repair_benchmark_case_attributions=attributions,
        ),
        _ctx(),
    )

    scorecard = artifact.repair_scorecard
    assert scorecard.benchmark_case_count == 2
    assert scorecard.reproducible_case_count == 1
    assert scorecard.no_longer_reproducible_case_count == 1
    assert scorecard.success_denominator == 1
    assert scorecard.repair_chain_count == 1
    assert scorecard.benchmark_denominator_complete is True
    assert scorecard.benchmark_comparison_status == "incompatible"
    assert scorecard.residual_odds_reduction_state == "unavailable"
    assert len(scorecard.benchmark_case_attributions) == 2
