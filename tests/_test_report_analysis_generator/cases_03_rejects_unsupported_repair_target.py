# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.contracts.regeneration import (
    FailureFingerprint,
    RepairDelta,
    RepairSeverityChange,
    repair_strategy_fingerprint,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _load_candidate_claim_validation_for_promotion,
    _store_promoted_candidate_claim_validation,
)
from src.utils.cache_utils import sha256_json

from ._shared import *  # noqa: F401,F403


def test_load_retained_claim_candidate_binds_to_promoted_artifacts(tmp_path):
    runtime = _runtime(tmp_path)
    candidate_artifacts = {"summary": {"tldr": "Promoted copy."}}
    artifact_hash = sha256_json(candidate_artifacts)
    candidate_package = {
        "schema_version": "1.3",
        "artifact_hash": artifact_hash,
        "package_hash": "promoted-package-hash",
    }
    read_requests = []

    def _analysis_pack_path(request, _ctx):
        return SimpleNamespace(output_path=f"candidate/{request.pack_name}.json")

    def _read_json(request, _ctx):
        read_requests.append(request)
        return SimpleNamespace(payload=candidate_package)

    dependencies = _deps(
        analysis_pack_path=_analysis_pack_path,
        read_json=_read_json,
    )

    loaded_package = _load_candidate_claim_validation_for_promotion(
        runtime=runtime,
        dependencies=dependencies,
        candidate_validation_pack_name="validation_regen_candidate_2",
        expected_artifact_hash=artifact_hash,
        ctx=runtime.ctx,
    )

    assert loaded_package == candidate_package
    assert len(read_requests) == 1
    assert read_requests[0].path.endswith(
        "validation_regen_candidate_2_retained_claim_validation_candidate.json"
    )


def test_store_promoted_retained_claim_candidate_to_report_scoped_pack(tmp_path):
    runtime = _runtime(tmp_path)
    stored_requests = []
    dependencies = _deps(
        analysis_store_pack=lambda request, _ctx: (
            stored_requests.append(request)
            or SimpleNamespace(output_path=f"promoted/{request.pack_name}.json")
        )
    )
    payload = {"schema_version": "1.3", "artifact_hash": "current"}

    stored_path = _store_promoted_candidate_claim_validation(
        runtime=runtime,
        dependencies=dependencies,
        candidate_package=payload,
        ctx=runtime.ctx,
    )

    assert len(stored_requests) == 1
    assert stored_requests[0].pack_name == (
        "validation_retained_claim_validation_candidate"
    )
    assert stored_requests[0].payload == payload
    assert stored_path.endswith("validation_retained_claim_validation_candidate.json")


def test_promote_retained_claim_candidate_rejects_artifact_mismatch(tmp_path):
    runtime = _runtime(tmp_path)
    stored_requests = []
    dependencies = _deps(
        analysis_pack_path=lambda request, _ctx: SimpleNamespace(
            output_path=f"candidate/{request.pack_name}.json"
        ),
        read_json=lambda _request, _ctx: SimpleNamespace(
            payload={"schema_version": "1.3", "artifact_hash": "stale"}
        ),
        analysis_store_pack=lambda request, _ctx: stored_requests.append(request),
    )

    with pytest.raises(AppError) as excinfo:
        _load_candidate_claim_validation_for_promotion(
            runtime=runtime,
            dependencies=dependencies,
            candidate_validation_pack_name="validation_regen_candidate_1",
            expected_artifact_hash="current",
            ctx=runtime.ctx,
        )

    assert excinfo.value.code == "retained_claim_candidate_artifact_mismatch"
    assert stored_requests == []


def test_build_regeneration_plan_skips_info_and_orders_errors_first():
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                schema_version="1.0",
                message="[summary_warning] Warning issue",
                severity="warning",
                affected_section="summary",
                rule_id="summary_warning",
            ),
            ValidationIssue(
                schema_version="1.0",
                message="[summary_info] Informational issue",
                severity="info",
                affected_section="summary",
                rule_id="summary_info",
            ),
            ValidationIssue(
                schema_version="1.0",
                message="[summary_error] Error issue",
                severity="error",
                affected_section="summary",
                rule_id="summary_error",
            ),
        ],
        artifacts={},
        broad_retry_available=True,
    )

    assert plan.mode == "targeted"
    assert len(plan.targets) == 1
    assert [issue.rule_id for issue in plan.targets[0].issues] == [
        "summary_error",
        "summary_warning",
    ]


def test_run_report_analysis_rejects_unsupported_repair_target(tmp_path):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del req, settings, ctx, pack_name, report_name, md5
        return ValidationReport(
            schema_version="1.1",
            status="fail",
            issues=[
                ValidationIssue(
                    schema_version="1.0",
                    message="[custom_rule] Unsupported custom repair target",
                    severity="error",
                    affected_section="custom_pack",
                    rule_id="custom_rule",
                    repair_target="custom_pack",
                )
            ],
            severity="error",
            source_path=str(tmp_path / "out" / "validation.json"),
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {"doc_map": {}},
        generate_artifacts=lambda **kwargs: _artifacts(
            summary={
                "tldr": "x",
                "executive_summary": "x",
                "claim_evidence_map": [],
            }
        ),
        run_validation=_run_validation,
        regenerate_artifacts=lambda request: (_ for _ in ()).throw(
            AssertionError("unsupported repair target should fail before regeneration")
        ),
    )

    with pytest.raises(AppError) as excinfo:
        run_report_analysis(
            runtime,
            source,
            selection,
            VectorStoreIndexingState(
                vector_store_id="vs_1",
                openai_file_id="file_1",
                vector_store_status="completed",
                indexed_at_utc="2026-01-01T00:00:00Z",
                last_error=None,
            ),
            deps,
        )

    assert excinfo.value.code == "regeneration_repair_target_unsupported"
    assert excinfo.value.retryable is False


def test_build_regeneration_plan_maps_public_artifact_copy_to_its_family():
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                schema_version="1.0",
                message="Public copy needs a grounded repair",
                severity="error",
                affected_section="key_figures:0.takeaway",
                rule_id="public_editorial_quality.generic_copy",
                repair_target="artifact_copy",
            )
        ],
        artifacts={},
        broad_retry_available=True,
    )

    assert plan.mode == "targeted"
    assert [target.target_section for target in plan.targets] == ["key_figures"]


def test_build_regeneration_plan_keeps_hard_repair_claim_scoped():
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                schema_version="1.0",
                message="Unsupported factual claim.",
                severity="error",
                affected_section="expert_comment",
                rule_id="grounding",
                repair_target="expert_comment",
                entity_id="soft_copy:expert_comment:failed",
            ),
            ValidationIssue(
                schema_version="1.0",
                message="Quote family warning.",
                severity="warning",
                affected_section="quotes",
                rule_id="family_confidence",
                repair_target="quotes",
            ),
            ValidationIssue(
                schema_version="1.0",
                message="Summary copy warning.",
                severity="warning",
                affected_section="summary.executive_summary",
                rule_id="artifact_quality",
                repair_target="artifact_copy",
            ),
        ],
        artifacts={},
        broad_retry_available=True,
    )

    assert plan.mode == "targeted"
    assert [target.target_section for target in plan.targets] == ["expert_comment"]
    assert [issue.rule_id for issue in plan.targets[0].issues] == ["grounding"]


def test_mobile_numbers_failure_targets_exact_insight_so_what_leaf():
    artifacts = {
        "insights_final": [
            {
                "id": "insight-002",
                "text": "Existing text",
                "so_what": "Existing implication",
            },
            {
                "id": "insight-005",
                "text": "Existing text",
                "so_what": "The 1.0 day checkpoint is proven.",
            },
        ],
        "insights_candidates": [],
    }
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                schema_version="1.0",
                message="[numbers] 1.0 is not supported",
                severity="error",
                affected_section="insights:insight-005.so_what",
                rule_id="numbers",
                entity_id="insight:insight-005:so_what",
            ),
            ValidationIssue(
                schema_version="1.0",
                message="[artifact_quality] Existing warning",
                severity="warning",
                affected_section="insights_final[0].text",
                rule_id="artifact_quality",
            ),
            ValidationIssue(
                schema_version="1.0",
                message="[artifact_quality] Same-item warning",
                severity="warning",
                affected_section="insights:insight-005.text",
                rule_id="artifact_quality",
                entity_id="insight:insight-005:text",
            ),
        ],
        artifacts=artifacts,
        broad_retry_available=False,
    )

    assert plan.mode == "targeted"
    assert len(plan.targets) == 1
    target = plan.targets[0]
    assert target.target_section == "insights_bundle"
    assert target.repair_action == "REGENERATE_ITEM"
    assert target.allowed_paths == ["insights_final[item=insight-005].so_what"]
    assert [issue.rule_id for issue in target.issues] == [
        "numbers",
        "artifact_quality",
    ]


def test_persisting_insight_metric_failures_preempt_linkedin_and_skip_noop_copy():
    metric = {
        "label": "Regional Ad Attention Index",
        "value": "99–110",
        "unit": "index",
        "timeframe": "Q1 2026",
        "geography": "APAC, EMEA, LATAM, North America",
        "cohort": "Regional benchmarks",
        "denominator": "",
        "observation_status": "observed",
    }
    artifacts = {
        "insights_final": [
            {
                "id": "q1-regional-ad-attention-index",
                "text": "Regional attention",
                "metric": dict(metric),
                "evidence_id": "s8",
            }
        ],
        "insights_candidates": [
            {
                "id": "q1-regional-ad-attention-index",
                "text": "Regional attention",
                "metric": dict(metric),
                "evidence_id": "s8",
            }
        ],
        "linkedin_post": "Regional Ad Attention Index is 110 in EMEA and 99 in North America.",
        "soft_copy_claim_provenance": {"schema_version": "1.0", "claims": []},
    }
    public_issue = ValidationIssue(
        schema_version="1.0",
        message="Metric label and value relationship is unsupported.",
        severity="error",
        affected_section="linkedin_post",
        rule_id="public_editorial_quality.metric_label_relationship",
        entity_id="soft_copy:linkedin_post:regional-metric",
        evidence_ids=["s8"],
        repair_target="linkedin_post",
    )
    persisted_root_failures = [
        FailureFingerprint(
            rule_id=rule_id,
            affected_section="insights:q1-regional-ad-attention-index.metric",
            entity_id="insight:q1-regional-ad-attention-index:metric",
            evidence_ids=["s8", "s8"],
        )
        for rule_id in (
            "retained_claim.protected_fact_value_consistency",
            "retained_claim.protected_fact_unit_currency_consistency",
            "retained_claim.number_value_unit_match",
        )
    ]
    repair_memory = [
        RepairDelta(
            persisting=persisted_root_failures,
            severity_changes=[
                RepairSeverityChange(
                    failure_fingerprint=fingerprint.key,
                    before="warning",
                    after="error",
                )
                for fingerprint in persisted_root_failures
            ],
        )
    ]

    plan = _build_regeneration_plan(
        issues=[public_issue],
        artifacts=artifacts,
        broad_retry_available=False,
        repair_memory=repair_memory,
    )

    assert plan.mode == "targeted"
    assert [target.target_section for target in plan.targets] == ["insights_bundle"]
    target = plan.targets[0]
    assert target.repair_action == "REGENERATE_ITEM"
    assert target.allowed_paths == [
        "insights_final[item=q1-regional-ad-attention-index].metric.unit",
        "insights_final[item=q1-regional-ad-attention-index].metric.value",
    ]
    assert {issue.rule_id for issue in target.issues} == {
        "retained_claim.protected_fact_value_consistency",
        "retained_claim.protected_fact_unit_currency_consistency",
        "retained_claim.number_value_unit_match",
    }

    linkedin_text = artifacts["linkedin_post"]
    linkedin_claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="linkedin_post",
        claim_id="soft_copy:linkedin_post:regional-metric",
        text_hash=hashlib.sha256(" ".join(linkedin_text.split()).encode()).hexdigest(),
        classification="factual",
        evidence_ids=("s8",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/linkedin_post"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    artifacts["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        [linkedin_claim]
    )
    current_root_issues = [
        ValidationIssue(
            schema_version="1.0",
            message=f"{fingerprint.rule_id} persists",
            severity="error",
            affected_section=fingerprint.affected_section,
            rule_id=fingerprint.rule_id,
            entity_id=fingerprint.entity_id,
            evidence_ids=list(fingerprint.evidence_ids),
        )
        for fingerprint in persisted_root_failures
    ]
    retry_plan = _build_regeneration_plan(
        issues=[*current_root_issues, public_issue],
        artifacts=artifacts,
        broad_retry_available=False,
        repair_memory=[RepairDelta(resolved=persisted_root_failures)],
    )

    assert [target.target_section for target in retry_plan.targets] == [
        "insights_bundle",
        "linkedin_post",
    ]
    assert retry_plan.targets[0].allowed_paths == target.allowed_paths
    assert retry_plan.targets[1].allowed_paths == ["linkedin_post[claim_index=0]"]


def test_repair_memory_does_not_upgrade_unknown_severity_to_hard_error():
    unknown_severity = FailureFingerprint(
        rule_id="retained_claim.protected_fact_value_consistency",
        affected_section="insights:q1-regional-ad-attention-index.metric",
        entity_id="insight:q1-regional-ad-attention-index:metric",
        evidence_ids=["s8"],
    )

    plan = _build_regeneration_plan(
        issues=[],
        artifacts={},
        broad_retry_available=False,
        repair_memory=[RepairDelta(persisting=[unknown_severity])],
    )

    assert plan.mode == "skip"
    assert plan.targets == []


def test_multi_insight_retry_does_not_offer_single_item_safe_removal():
    insights = [
        {
            "id": insight_id,
            "text": f"Supported text for {insight_id}.",
            "metric": {"value": "10", "unit": "index"},
            "evidence_id": evidence_id,
            "evidence": f"Source supports 10 for {insight_id}.",
        }
        for insight_id, evidence_id in (
            ("insight-a", "evidence-a"),
            ("insight-b", "evidence-b"),
        )
    ]
    artifacts = {
        "insights_final": insights,
        "insights_candidates": [dict(insight) for insight in insights],
    }
    issues = [
        ValidationIssue(
            schema_version="1.0",
            message="Retained metric is unsupported.",
            severity="error",
            affected_section=f"insights:{insight_id}.metric",
            rule_id="retained_claim.protected_fact_value_consistency",
            entity_id=f"insight:{insight_id}:metric",
            evidence_ids=[evidence_id],
        )
        for insight_id, evidence_id in (
            ("insight-a", "evidence-a"),
            ("insight-b", "evidence-b"),
        )
    ]

    first_plan = _build_regeneration_plan(
        issues=issues, artifacts=artifacts, broad_retry_available=False
    )
    assert first_plan.targets[0].repair_action == "REGENERATE_ITEM"
    fingerprints = [issue.failure_fingerprint for issue in first_plan.targets[0].issues]
    rejected = {
        repair_strategy_fingerprint(
            fingerprints,
            first_plan.targets[0].repair_strategy,
            first_plan.targets[0].selected_evidence_ids,
        ),
        repair_strategy_fingerprint(
            fingerprints, "alternative_evidence", ["evidence-a", "evidence-b"]
        ),
    }

    exhausted = _build_regeneration_plan(
        issues=issues,
        artifacts=artifacts,
        broad_retry_available=False,
        rejected_strategy_keys=rejected,
    )

    assert exhausted.mode == "skip"
    assert exhausted.targets == []
    assert {issue.rule_id for issue in exhausted.unmappable_issues} == {
        "retained_claim.protected_fact_value_consistency"
    }


def test_run_report_analysis_snapshot_preserves_internal_payload_metadata(tmp_path):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    source.payload._text_density = 100.0
    source.payload._text_pages_sampled = 3
    source.payload._text_char_count = 100
    source.payload._text_not_available = False
    selection = _selection(runtime, source)
    stored_payloads: dict[str, dict] = {}

    def _analysis_pack_path(req, ctx):
        del ctx
        return SimpleNamespace(
            output_path=str(tmp_path / "out" / f"{req.pack_name}.json")
        )

    def _analysis_store_pack(req, ctx):
        del ctx
        stored_payloads[req.pack_name] = req.payload
        return SimpleNamespace(
            output_path=str(tmp_path / "out" / f"{req.pack_name}.json")
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {
                "title": "Doc Title",
                "publisher": "Doc Publisher",
            },
            "findings": {"schema_version": "1.0", "findings": []},
        },
        generate_artifacts=lambda **kwargs: _artifacts(),
        run_validation=lambda *args, **kwargs: ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        ),
        analysis_pack_path=_analysis_pack_path,
        analysis_store_pack=_analysis_store_pack,
    )

    state = run_report_analysis(
        runtime,
        source,
        selection,
        VectorStoreIndexingState(
            vector_store_id="vs_1",
            openai_file_id="file_1",
            vector_store_status="completed",
            indexed_at_utc="2026-01-01T00:00:00Z",
            last_error=None,
        ),
        deps,
    )

    snapshot = stored_payloads["analysis_vector_store"]
    assert state.normalized_payload._vector_store_id == "vs_1"
    assert state.normalized_payload._text_density == 100.0
    assert state.normalized_payload._text_pages_sampled == 3
    assert state.normalized_payload._text_char_count == 100
    assert snapshot["_vector_store_id"] == "vs_1"
    assert snapshot["_text_density"] == 100.0
    assert snapshot["_text_pages_sampled"] == 3
    assert snapshot["_text_char_count"] == 100
    assert snapshot["_evidence_packs"]["doc_map"].endswith("doc_map.json")
    assert snapshot["_evidence_packs"]["validation"].endswith("validation.json")


__all__ = [
    "test_load_retained_claim_candidate_binds_to_promoted_artifacts",
    "test_store_promoted_retained_claim_candidate_to_report_scoped_pack",
    "test_promote_retained_claim_candidate_rejects_artifact_mismatch",
    "test_build_regeneration_plan_skips_info_and_orders_errors_first",
    "test_build_regeneration_plan_maps_public_artifact_copy_to_its_family",
    "test_build_regeneration_plan_keeps_hard_repair_claim_scoped",
    "test_mobile_numbers_failure_targets_exact_insight_so_what_leaf",
    "test_persisting_insight_metric_failures_preempt_linkedin_and_skip_noop_copy",
    "test_repair_memory_does_not_upgrade_unknown_severity_to_hard_error",
    "test_multi_insight_retry_does_not_offer_single_item_safe_removal",
    "test_run_report_analysis_rejects_unsupported_repair_target",
    "test_run_report_analysis_snapshot_preserves_internal_payload_metadata",
]
