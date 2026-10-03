# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_validation_repair_scorecard.py"
)

from ._split_support_test_validation_repair_scorecard import *  # noqa: F401,F403


@pytest.mark.parametrize(
    ("rule_id", "message", "evidence_ids", "entity_id", "expected"),
    [
        (
            "grounding",
            "[grounding|hallucinated_evidence_id] Candidate references unknown ID.",
            [],
            "",
            "unknown_or_hallucinated_evidence_introduction",
        ),
        (
            "retained_claim.evidence_reference_completeness",
            (
                "[retained_claim.evidence_reference_completeness|"
                "unknown_evidence_reference] Unknown reference."
            ),
            ["unknown-id"],
            "",
            "unknown_or_hallucinated_evidence_introduction",
        ),
        (
            "claim_support",
            "Summary claim references unknown evidence_id 'unknown-id'.",
            [],
            "unknown-id",
            "unknown_or_hallucinated_evidence_introduction",
        ),
        (
            "soft_copy_claim_provenance",
            "Candidate factual claim has no provenance binding.",
            ["finding-1"],
            "",
            "provenance_or_lineage_introduction",
        ),
        (
            "retained_claim.soft_copy_provenance_integrity",
            "[retained_claim.soft_copy_provenance_integrity|"
            "soft_copy_provenance_missing] Missing provenance.",
            ["finding-1"],
            "",
            "provenance_or_lineage_introduction",
        ),
        (
            "regeneration_source_page",
            "Candidate source page does not match retained evidence.",
            ["finding-1"],
            "",
            "provenance_or_lineage_introduction",
        ),
        (
            "retained_claim.number_value_unit_match",
            "[retained_claim.number_value_unit_match|quantity_not_entailed]",
            ["finding-1"],
            "",
            "unsupported_claim_evidence_introduction",
        ),
        (
            "retained_claim.protected_fact_value_consistency",
            "[retained_claim.protected_fact_value_consistency|"
            "protected_fact_value_incompatible]",
            ["finding-1"],
            "",
            "unsupported_claim_evidence_introduction",
        ),
        (
            "grounding",
            "[grounding|contradicted] Candidate statement conflicts with evidence.",
            ["finding-1"],
            "",
            "unsupported_claim_evidence_introduction",
        ),
        (
            "retained_claim.evidence_reference_completeness",
            "[retained_claim.evidence_reference_completeness|missing_evidence_reference]",
            [],
            "",
            "unsupported_claim_evidence_introduction",
        ),
        (
            "retained_claim.evidence_reference_completeness",
            "[retained_claim.evidence_reference_completeness|"
            "missing_or_unknown_evidence_reference] No evidence reference.",
            [],
            "claim-1",
            "unsupported_claim_evidence_introduction",
        ),
        (
            "retained_claim.evidence_reference_completeness",
            "Unknown evidence reference without a stable reason token.",
            ["finding-1"],
            "",
            "unsupported_claim_evidence_introduction",
        ),
    ],
)
def test_evidence_introduction_category_uses_specific_rule_and_reason(
    rule_id: str,
    message: str,
    evidence_ids: list[str],
    entity_id: str,
    expected: str,
) -> None:
    issue = ValidationIssue(
        message=message,
        severity="error",
        affected_section="summary.tldr",
        rule_id=rule_id,
        entity_id=entity_id,
        evidence_ids=evidence_ids,
    )
    classify = getattr(
        analysis_validation, "_evidence_introduction_category", lambda _issue: None
    )

    assert classify(issue) == expected


def test_repair_scorecard_reports_bounded_evidence_and_validation_call_metrics(
    tmp_path: Path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    audit_root = tmp_path / "audits"
    categories = (
        (
            "unknown",
            "grounding",
            "unknown_or_hallucinated_evidence_introduction",
            "evaluated",
        ),
        (
            "provenance",
            "soft_copy_claim_provenance",
            "provenance_or_lineage_introduction",
            "evaluated",
        ),
        (
            "numeric",
            "retained_claim.number_value_unit_match",
            "unsupported_claim_evidence_introduction",
            "evaluated",
        ),
        (
            "deterministic-reject",
            "regeneration_scope_violation",
            None,
            "not_evaluated_due_to_deterministic_failure",
        ),
    )
    for report_id, rule_id, category, validation_status in categories:
        _create_manifest(reports_db, report_id)
        append_usage(
            LLMUsageLedgerAppendRequest(
                schema_version="1.0",
                db_path=usage_db,
                entry=_usage(report_id, 1),
            ),
            _ctx(),
        )
        if validation_status == "evaluated":
            for family in ("validation_semantic", "validation_grounding"):
                append_usage(
                    LLMUsageLedgerAppendRequest(
                        schema_version="1.0",
                        db_path=usage_db,
                        entry=_validation_usage(report_id, family),
                    ),
                    _ctx(),
                )
        payload = _audit(report_id=report_id, promotion_outcome="rolled_back")
        delta = payload["repair_delta"]
        delta["introduced"] = [
            {
                "rule_id": rule_id,
                "affected_section": "summary.tldr",
                "entity_id": report_id,
                "evidence_ids": ["finding-1"] if category else [],
            }
        ]
        delta["introduced_failure_categories"] = [category] if category else []
        delta["semantic_grounding_validation_status"] = validation_status
        path = audit_root / report_id / "report_analysis"
        path.mkdir(parents=True)
        (path / "regeneration_candidate_audit_1.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
            repair_evidence_root=str(audit_root),
        ),
        _ctx(),
    )

    scorecard = artifact.repair_scorecard
    assert scorecard.unknown_or_hallucinated_evidence_introduction_attempt_count == 1
    assert scorecard.unsupported_claim_evidence_introduction_attempt_count == 1
    assert scorecard.provenance_or_lineage_introduction_attempt_count == 1
    assert scorecard.unsupported_evidence_introduction_attempt_count == 2
    assert scorecard.deterministic_rejection_attempt_count == 1
    assert scorecard.semantic_grounding_validation_invocations_avoided_count == 1
    assert scorecard.semantic_grounding_validation_provider_call_count == 6
    assert scorecard.semantic_grounding_validation_input_tokens == 600
    assert scorecard.semantic_grounding_validation_output_tokens == 120
    assert scorecard.semantic_grounding_validation_estimated_cost_usd == 0.072


def test_historical_repair_audit_without_new_telemetry_remains_readable(
    tmp_path: Path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    audit_root = tmp_path / "audits"
    _create_manifest(reports_db, "report-legacy")
    path = audit_root / "report-legacy" / "report_analysis"
    path.mkdir(parents=True)
    (path / "regeneration_candidate_audit_1.json").write_text(
        json.dumps(_audit(report_id="report-legacy", promotion_outcome="rolled_back")),
        encoding="utf-8",
    )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
            repair_evidence_root=str(audit_root),
        ),
        _ctx(),
    )

    scorecard = artifact.repair_scorecard
    assert scorecard.measurement_status == "available"
    assert scorecard.unknown_or_hallucinated_evidence_introduction_attempt_count is None
    assert scorecard.deterministic_rejection_attempt_count is None


def test_repair_scorecard_excludes_rolled_back_and_removed_candidates(
    tmp_path: Path,
) -> None:
    """Changing success to include rollback/removal must fail this scorecard."""

    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    audit_root = tmp_path / "audits"
    for report_id in ("report-1", "report-2", "report-3", "report-4"):
        _create_manifest(reports_db, report_id)
    append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=usage_db,
            entry=replace(
                _usage("report-3", 0),
                task_id="report:report-3:regen:1:regeneration",
            ),
        ),
        _ctx(),
    )
    append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=usage_db,
            entry=replace(
                _usage("report-3", 1),
                action="structured_output:repair",
                semantic_task="validation_grounding_model_repair",
                stage="validation_grounding_model_repair",
                artifact_family="validation_grounding",
                input_tokens=900,
                output_tokens=200,
                total_tokens=1100,
                estimated_cost_usd=0.25,
            ),
        ),
        _ctx(),
    )
    audit_payloads = (
        _audit(report_id="report-1", promotion_outcome="rolled_back"),
        _audit(report_id="report-2", promotion_outcome="rolled_back"),
        _audit(
            report_id="report-3",
            promotion_outcome="promoted",
            strategy_fingerprint="strategy-b",
            candidate_fingerprint="c" * 64,
            resolved=("failure-a",),
            persisting=(),
        ),
        _audit(
            report_id="report-4",
            promotion_outcome="promoted",
            repair_action="REMOVE_CLAIM",
            strategy_fingerprint="strategy-c",
            candidate_fingerprint="d" * 64,
            resolved=("failure-a",),
            persisting=(),
        ),
    )
    for index, payload in enumerate(audit_payloads, start=1):
        path = audit_root / f"report-{index}" / "report_analysis"
        path.mkdir(parents=True)
        (path / "regeneration_candidate_audit_1.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
            repair_evidence_root=str(audit_root),
        ),
        _ctx(),
    )

    scorecard = artifact.repair_scorecard
    assert scorecard.measurement_status == "available"
    assert scorecard.repair_chain_count == 4
    assert scorecard.success_at_1_count == 1
    assert scorecard.success_at_1_rate == 0.25
    assert scorecard.success_at_3_count == 1
    assert scorecard.rolled_back_attempt_count == 2
    assert scorecard.abstention_or_removal_attempt_count == 1
    assert scorecard.repeated_failed_strategy_evidence_attempt_count == 2
    assert scorecard.repeated_failed_candidate_attempt_count == 2
    assert scorecard.benchmark_denominator_complete is False
    assert scorecard.hard_failure_introduction_attempt_count == 0
    assert scorecard.hard_failure_introduction_count == 0
    assert scorecard.hard_failure_introduction_rate == 0.0
    assert scorecard.current_residual_failure_odds == 3.0
    assert scorecard.current_residual_failure_odds_state == "available"
    assert scorecard.deterministic_repair_share == 0.75
    assert scorecard.model_repair_share == 0.25
    assert scorecard.model_call_count == 1
    assert scorecard.input_tokens == 100
    assert scorecard.output_tokens == 20
    assert scorecard.estimated_cost_usd == 0.012
    assert scorecard.failure_class_distribution[0].failure_class == "grounding"
    assert scorecard.failure_class_distribution[0].attempt_count == 4
    assert {attempt.failure_rule_ids for attempt in scorecard.attempts} == {
        ("grounding",)
    }
    by_mode = {metric.repair_mode: metric for metric in scorecard.mode_metrics}
    assert by_mode["model"].attempt_count == 1
    assert by_mode["model"].successful_attempt_count == 1
    assert by_mode["model"].model_call_count == 1
    assert by_mode["deterministic"].attempt_count == 3
    assert by_mode["deterministic"].model_call_count == 0


def test_repair_scorecard_marks_missing_retained_audits_unavailable(
    tmp_path: Path,
) -> None:
    """Returning zero success for absent repair evidence must fail this scorecard."""

    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    _create_manifest(reports_db, "report-1")

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
        ),
        _ctx(),
    )

    scorecard = artifact.repair_scorecard
    assert scorecard.measurement_status == "unavailable"
    assert scorecard.repair_chain_count is None
    assert scorecard.success_at_1_rate is None
    assert scorecard.usage_attribution == "unavailable"
    assert scorecard.model_call_count is None
    assert scorecard.current_residual_failure_odds_state == "unavailable"
    assert scorecard.mode_metrics == ()


def test_repair_scorecard_does_not_treat_missing_hard_failure_attribution_as_zero(
    tmp_path: Path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    audit_root = tmp_path / "audits"
    _create_manifest(reports_db, "report-1")
    payload = _audit(report_id="report-1", promotion_outcome="rolled_back")
    del payload["repair_delta"]["introduced_hard_failure_count"]
    path = audit_root / "report-1" / "report_analysis"
    path.mkdir(parents=True)
    (path / "regeneration_candidate_audit_1.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
            repair_evidence_root=str(audit_root),
        ),
        _ctx(),
    )

    scorecard = artifact.repair_scorecard
    assert scorecard.repair_attempt_count == 1
    assert scorecard.hard_failure_introduction_count is None
    assert scorecard.hard_failure_introduction_attempt_count is None
    assert scorecard.hard_failure_introduction_rate is None


def test_repair_scorecard_counts_scope_rule_delta_without_diagnostic_text(
    tmp_path: Path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    audit_root = tmp_path / "audits"
    _create_manifest(reports_db, "report-1")
    payload = _audit(report_id="report-1", promotion_outcome="rolled_back")
    payload["repair_delta"]["introduced"] = [
        {
            "rule_id": "regeneration_scope_violation",
            "affected_section": "summary",
            "entity_id": "summary.tldr",
            "evidence_ids": [],
        }
    ]
    payload["repair_delta"]["mutation_scope_result"] = "fail"
    path = audit_root / "report-1" / "report_analysis"
    path.mkdir(parents=True)
    (path / "regeneration_candidate_audit_1.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
            repair_evidence_root=str(audit_root),
        ),
        _ctx(),
    )

    assert artifact.repair_scorecard.out_of_scope_mutation_attempt_count == 1


def test_repair_scorecard_keys_repeated_strategy_by_failure_and_evidence(
    tmp_path: Path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    audit_root = tmp_path / "audits"
    for report_id in ("report-1", "report-2"):
        _create_manifest(reports_db, report_id)
    payloads = (
        _audit(report_id="report-1", promotion_outcome="rolled_back"),
        _audit(
            report_id="report-2",
            promotion_outcome="rolled_back",
            evidence_ids=("finding-2",),
        ),
    )
    for payload in payloads:
        path = audit_root / payload["report_id"] / "report_analysis"
        path.mkdir(parents=True)
        (path / "regeneration_candidate_audit_1.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
            repair_evidence_root=str(audit_root),
        ),
        _ctx(),
    )

    scorecard = artifact.repair_scorecard
    assert scorecard.repeated_failed_strategy_evidence_attempt_count == 0
    assert scorecard.repeated_failed_candidate_attempt_count == 2


def test_repair_scorecard_pairs_a_frozen_baseline_denominator(
    tmp_path: Path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    audit_root = tmp_path / "audits"
    _create_manifest(reports_db, "report-1")
    initial_fingerprint = FailureFingerprint(
        rule_id="grounding",
        affected_section="summary",
        entity_id="failure-a",
        evidence_ids=["finding-1"],
    ).key
    baseline_audit = _audit(
        report_id="report-1",
        promotion_outcome="rolled_back",
        persisting=("failure-a",),
    )
    baseline_manifest = {
        "schema_version": "1.0",
        "frozen": True,
        "baseline_identity": {
            "configuration_hash": "configuration-hash",
            "policy_hash": "policy-hash",
            "producer_build_identity": "build-sha",
            "validator_identity": "validator-v1",
            "schema_identity_sha256": "2" * 64,
        },
        "cases": [
            {
                "report_id": "report-1",
                "original_artifact_canonical_sha256": "b" * 64,
                "initial_validation_sha256": "e" * 64,
                "initial_failure_fingerprints": [initial_fingerprint],
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
                "baseline_attempts": [baseline_audit],
            }
        ],
    }
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

    first = _audit(
        report_id="report-1",
        promotion_outcome="rolled_back",
        persisting=("failure-a",),
        attempt_index=1,
    )
    second = _audit(
        report_id="report-1",
        promotion_outcome="promoted",
        strategy_fingerprint="strategy-b",
        candidate_fingerprint="c" * 64,
        resolved=("failure-a",),
        persisting=(),
        attempt_index=2,
    )
    for payload in (first, second):
        path = audit_root / "report-1" / "report_analysis"
        path.mkdir(parents=True, exist_ok=True)
        (
            path / f"regeneration_candidate_audit_{payload['attempt_index']}.json"
        ).write_text(json.dumps(payload), encoding="utf-8")

    request = ValidationReliabilityBuildRequest(
        schema_version="1.0",
        reports_db_path=reports_db,
        usage_db_path=usage_db,
        validation_run_id="validation-1",
        repair_evidence_root=str(audit_root),
        repair_benchmark_manifest_path=str(manifest_path),
        current_schema_identity_sha256="2" * 64,
    )
    artifact = build_validation_reliability_artifact(request, _ctx())

    scorecard = artifact.repair_scorecard
    assert scorecard.benchmark_case_count == 1
    assert scorecard.benchmark_denominator_complete is True
    assert scorecard.benchmark_comparison_status == "paired"
    assert scorecard.success_at_1_count == 0
    assert scorecard.success_at_3_count == 1
    assert scorecard.baseline_success_at_3_count == 0
    assert scorecard.baseline_residual_failure_odds_state == "unbounded"
    assert scorecard.current_residual_failure_odds == 0
    assert scorecard.residual_odds_reduction_state == "unbounded"
    assert scorecard.baseline_usage_attribution == "unavailable"

    baseline_manifest["schema_version"] = "2.0"
    version_two_body = {
        key: value
        for key, value in baseline_manifest.items()
        if key != "manifest_sha256"
    }
    baseline_manifest["manifest_sha256"] = hashlib.sha256(
        (
            json.dumps(
                version_two_body,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(json.dumps(baseline_manifest), encoding="utf-8")
    version_two = build_validation_reliability_artifact(request, _ctx())
    assert version_two.repair_scorecard.benchmark_denominator_complete is True

    baseline_manifest["schema_version"] = "1.0"
    version_one_body = {
        key: value
        for key, value in baseline_manifest.items()
        if key != "manifest_sha256"
    }
    baseline_manifest["manifest_sha256"] = hashlib.sha256(
        (
            json.dumps(
                version_one_body,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(json.dumps(baseline_manifest), encoding="utf-8")

    second["allowed_paths"] = ["summary.tldr", "expert_comment"]
    second_path = (
        audit_root
        / "report-1"
        / "report_analysis"
        / "regeneration_candidate_audit_2.json"
    )
    second_path.write_text(json.dumps(second), encoding="utf-8")
    broadened = build_validation_reliability_artifact(request, _ctx())
    assert broadened.repair_scorecard.benchmark_denominator_complete is True
    assert broadened.repair_scorecard.out_of_scope_mutation_attempt_count == 1
    assert broadened.repair_scorecard.success_at_3_count == 0

    incompatible = build_validation_reliability_artifact(
        replace(request, current_schema_identity_sha256="3" * 64), _ctx()
    )
    assert incompatible.repair_scorecard.benchmark_denominator_complete is False
    assert incompatible.repair_scorecard.benchmark_comparison_status == "incompatible"
