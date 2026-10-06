# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.contracts.regeneration import (
    FailureFingerprint,
    RepairDelta,
    RepairSeverityChange,
    repair_strategy_fingerprint,
)
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.soft_copy_claim_provenance import (
    soft_copy_claim_provenance_to_payload,
)
from src.contracts.validation import ValidationReport
from src.generators.soft_copy_claim_provenance import build_soft_copy_claim_provenance
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
    _normalize_regeneration_issue,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _load_candidate_claim_validation_for_promotion,
    _run_validation_regeneration_loop,
    _store_promoted_candidate_claim_validation,
)
from src.services import file_service, report_analysis_store_service
from src.utils.cache_utils import sha256_json

from ._shared import *  # noqa: F401,F403


def test_load_retained_claim_candidate_binds_to_promoted_artifacts(tmp_path):
    runtime = _runtime(tmp_path)
    candidate_artifacts = {"summary": {"tldr": "Promoted copy."}}
    artifact_hash = sha256_json(candidate_artifacts)
    candidate_package = {
        "schema_version": "1.4",
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
    payload = {"schema_version": "1.4", "artifact_hash": "current"}

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


def test_long_validation_candidate_pack_stores_and_loads_after_path_compaction(
    tmp_path,
):
    runtime = _runtime(tmp_path)
    pack_name = "validation_regen_candidate_3_retained_claim_validation_candidate"
    report_slug = "very-long-report-slug-for-a-frozen-reliability-cohort-member"
    output_dir = tmp_path / "isolated-cohort"
    pre_compaction_path = (
        output_dir / ("a" * 12) / "report_analysis" / f"{pack_name}.json"
    )
    padding_length = 260 - len(str(pre_compaction_path.resolve()))
    output_dir = output_dir / ("x" * padding_length)
    old_slug_only_path = (
        output_dir / ("a" * 12) / "report_analysis" / f"{pack_name}.json"
    )
    assert len(str(old_slug_only_path.resolve())) == 261
    runtime = replace(
        runtime,
        settings=replace(runtime.settings, output_dir=str(output_dir)),
        report_name=report_slug,
    )
    candidate_artifacts = {"summary": {"tldr": "Promoted copy."}}
    artifact_hash = sha256_json(candidate_artifacts)
    candidate_package = {
        "schema_version": "1.4",
        "artifact_hash": artifact_hash,
        "package_hash": "b" * 64,
        "results": [],
        "readiness_status": "awaiting_review",
        "unsupported_factual_count": 0,
        "unresolved_factual_count": 0,
        "deterministic_pass_count": 0,
        "semantic_validation_count": 0,
        "semantic_execution_identities": [],
        "validation_identity": None,
        "lineage": None,
    }
    dependencies = _deps(
        analysis_pack_path=report_analysis_store_service.pack_path,
        analysis_store_pack=report_analysis_store_service.store_pack,
        read_json=file_service.read_json,
    )
    stored_path = report_analysis_store_service.store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            pack_name=pack_name,
            payload=candidate_package,
            report_slug=report_slug,
        ),
        runtime.ctx,
    ).output_path

    loaded_package = _load_candidate_claim_validation_for_promotion(
        runtime=runtime,
        dependencies=dependencies,
        candidate_validation_pack_name="validation_regen_candidate_3",
        expected_artifact_hash=artifact_hash,
        ctx=runtime.ctx,
    )

    resolved_path = report_analysis_store_service.pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            pack_name=pack_name,
            report_slug=report_slug,
        ),
        runtime.ctx,
    ).output_path
    assert loaded_package == candidate_package
    assert stored_path == resolved_path
    assert len(str(Path(resolved_path).resolve())) < 260


def test_promote_retained_claim_candidate_rejects_artifact_mismatch(tmp_path):
    runtime = _runtime(tmp_path)
    stored_requests = []
    dependencies = _deps(
        analysis_pack_path=lambda request, _ctx: SimpleNamespace(
            output_path=f"candidate/{request.pack_name}.json"
        ),
        read_json=lambda _request, _ctx: SimpleNamespace(
            payload={"schema_version": "1.4", "artifact_hash": "stale"}
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
                affected_section="summary.tldr",
                rule_id="summary_warning",
            ),
            ValidationIssue(
                schema_version="1.0",
                message="[summary_info] Informational issue",
                severity="info",
                affected_section="summary.tldr",
                rule_id="summary_info",
            ),
            ValidationIssue(
                schema_version="1.0",
                message="[summary_error] Error issue",
                severity="error",
                affected_section="summary.tldr",
                rule_id="summary_error",
            ),
        ],
        artifacts={"summary": {"tldr": "Existing summary."}},
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
                affected_section="key_figures:figure-1.why_it_matters",
                rule_id="public_editorial_quality.generic_copy",
                repair_target="artifact_copy",
                entity_id="key_figure:figure-1:why_it_matters",
            )
        ],
        artifacts={
            "key_figures": [
                {
                    "figure_id": "figure-1",
                    "insight_id": "insight-1",
                    "why_it_matters": "Existing implication.",
                }
            ],
            "insights_final": [
                {
                    "id": "insight-1",
                    "text": "Evidence-backed insight.",
                    "evidence_id": "f1",
                }
            ],
            "insights_candidates": [],
        },
        broad_retry_available=True,
    )

    assert plan.mode == "targeted"
    assert [target.target_section for target in plan.targets] == ["insights_bundle"]


def test_build_regeneration_plan_keeps_hard_repair_claim_scoped():
    public_text = "Unsupported factual claim."
    provenance = build_soft_copy_claim_provenance(
        artifact_family="expert_comment",
        text=public_text,
        declared_claims=[
            {
                "claim": public_text,
                "classification": "factual",
                "evidence_ids": ["e1"],
            }
        ],
        evidence_span_index={},
        producing_prompt_identity={"namespace": "test/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    artifacts = {
        "expert_comment": public_text,
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(provenance),
    }
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                schema_version="1.0",
                message="Unsupported factual claim.",
                severity="error",
                affected_section="expert_comment",
                rule_id="grounding",
                repair_target="expert_comment",
                entity_id=provenance[0].claim_id,
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
        artifacts=artifacts,
        broad_retry_available=True,
    )

    assert plan.mode == "targeted"
    assert [target.target_section for target in plan.targets] == ["expert_comment"]
    assert [issue.rule_id for issue in plan.targets[0].issues] == ["grounding"]


def test_hard_soft_copy_repair_keeps_coupled_grounding_warnings_in_plan():
    expert_text = "Expert copy overstates the evidence."
    expert_claim = build_soft_copy_claim_provenance(
        artifact_family="expert_comment",
        text=expert_text,
        declared_claims=[
            {
                "claim": expert_text,
                "classification": "factual",
                "evidence_ids": ["e2"],
            }
        ],
        evidence_span_index={},
        producing_prompt_identity={"namespace": "test/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )[0]
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                schema_version="1.0",
                message="Unsupported summary fact.",
                severity="error",
                affected_section="summary.claim_evidence_map:1.claim",
                rule_id="grounding",
                repair_target="summary",
                entity_id="soft_copy:summary:unsupported",
            ),
            ValidationIssue(
                schema_version="1.0",
                message="Expert copy overstates the evidence.",
                severity="warning",
                affected_section="expert_comment",
                rule_id="grounding",
                repair_target="expert_comment",
                entity_id=expert_claim.claim_id,
            ),
            ValidationIssue(
                schema_version="1.0",
                message="Unrelated topic wording warning.",
                severity="warning",
                affected_section="topics_covered[2].why_it_matters",
                rule_id="artifact_quality",
                repair_target="topics",
            ),
        ],
        artifacts={
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": "Unsupported summary fact.",
                        "evidence_id": "e1",
                        "pages": [1],
                    }
                ]
            },
            "expert_comment": expert_text,
            "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
                [expert_claim]
            ),
            "topics_covered": [{"id": "topic-2", "why_it_matters": "Copy."}],
        },
        broad_retry_available=True,
    )

    assert plan.mode == "targeted"
    assert [target.target_section for target in plan.targets] == [
        "summary",
        "expert_comment",
    ]
    assert [issue.severity for target in plan.targets for issue in target.issues] == [
        "error",
        "warning",
    ]


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
        "linkedin_post": (
            "Regional Ad Attention Index is 110 in EMEA and 99 in North America."
        ),
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


def test_soft_copy_repair_fingerprint_stays_with_sentence_slot_after_rewrite():
    first_text = "The report establishes a global trend."
    second_text = "The report describes a worldwide pattern."
    evidence_id = "survey-scope"

    def artifacts_for(text: str) -> tuple[dict, str]:
        text_hash = hashlib.sha256(" ".join(text.split()).encode()).hexdigest()
        claim_id = f"soft_copy:linkedin_post:{text_hash[:16]}"
        artifacts = {
            "linkedin_post": text,
            "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
                [
                    SoftCopyClaimProvenance(
                        schema_version="1.0",
                        artifact_family="linkedin_post",
                        claim_id=claim_id,
                        text_hash=text_hash,
                        classification="factual",
                        evidence_ids=(evidence_id,),
                        source_spans=(),
                        producing_prompt_identity={"namespace": "test/linkedin"},
                        generation_attempt=1,
                        regeneration_attempt=0,
                    )
                ]
            ),
        }
        return artifacts, claim_id

    first_artifacts, first_claim_id = artifacts_for(first_text)
    second_artifacts, second_claim_id = artifacts_for(second_text)
    first_issue = ValidationIssue(
        schema_version="1.0",
        message="Unsupported sentence.",
        severity="error",
        affected_section="linkedin_post",
        rule_id="grounding",
        entity_id=first_claim_id,
        repair_target="linkedin_post",
        evidence_ids=[evidence_id],
    )
    second_issue = ValidationIssue(
        schema_version="1.0",
        message="Unsupported paraphrase.",
        severity="error",
        affected_section="linkedin_post",
        rule_id="grounding",
        entity_id=second_claim_id,
        repair_target="linkedin_post",
        evidence_ids=[evidence_id],
    )

    first = _normalize_regeneration_issue(first_issue, first_artifacts)
    second = _normalize_regeneration_issue(second_issue, second_artifacts)

    assert first.failure_fingerprint == second.failure_fingerprint

    first_plan = _build_regeneration_plan(
        issues=[first_issue],
        artifacts=first_artifacts,
        broad_retry_available=False,
    )
    rejected_strategy = repair_strategy_fingerprint(
        [first.failure_fingerprint],
        first_plan.targets[0].repair_strategy,
        first_plan.targets[0].selected_evidence_ids,
    )
    next_plan = _build_regeneration_plan(
        issues=[second_issue],
        artifacts=second_artifacts,
        broad_retry_available=False,
        rejected_strategy_keys={rejected_strategy},
    )

    assert first_plan.targets[0].repair_strategy == "current_evidence"
    assert next_plan.targets[0].repair_strategy != "current_evidence"


def test_duplicate_insight_issue_is_planned_as_its_own_repair_target():
    artifacts = _artifacts()
    artifacts["insights_final"][0]["so_what"] = "Current implication."
    issues = [
        ValidationIssue(
            schema_version="1.0",
            message="An insight implication is unsupported.",
            severity="error",
            affected_section="insights:insight-1.so_what",
            rule_id="grounding",
            entity_id="insight:insight-1:so_what",
            evidence_ids=["f1"],
        ),
        ValidationIssue(
            schema_version="1.0",
            message="This insight duplicates a prior insight.",
            severity="error",
            affected_section="insights:insight-2~insights:insight-1",
            rule_id="public_editorial_quality.duplicate_insight",
            repair_target="insights_bundle",
            entity_id="insight:insight-2:text",
            evidence_ids=["f2"],
        ),
    ]

    plan = _build_regeneration_plan(
        issues=issues,
        artifacts=artifacts,
        broad_retry_available=False,
    )

    assert plan.mode == "targeted"
    assert [target.target_section for target in plan.targets] == [
        "insights_bundle",
        "insights_bundle",
    ]
    assert [target.allowed_paths for target in plan.targets] == [
        ["insights_final[item=insight-1].so_what"],
        ["insights_final[item=insight-2].text"],
    ]


def test_summary_claim_map_grounding_is_limited_to_the_failed_item():
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "claim": "Supported sibling claim.",
                    "evidence_id": "evidence-a",
                    "pages": [4],
                },
                {"claim": "Failed claim.", "evidence_id": "evidence-b", "pages": [27]},
                {
                    "claim": "Another supported sibling.",
                    "evidence_id": "evidence-c",
                    "pages": [42],
                },
            ]
        }
    }
    issue = ValidationIssue(
        schema_version="1.0",
        message="The failed summary claim is not established by its evidence.",
        severity="error",
        affected_section="summary.claim_evidence_map:2.claim",
        rule_id="grounding",
    )

    normalized = _normalize_regeneration_issue(issue, artifacts)

    assert normalized.evidence_ids == ["evidence-b"]
    assert normalized.pages == [27]
    assert normalized.excluded_evidence_ids == ["evidence-b"]


def test_indexed_summary_claim_issue_resolves_only_the_failed_item():
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "claim": "First claim.",
                    "evidence_id": "evidence-a",
                    "pages": [4],
                },
                {
                    "claim": "Failed claim.",
                    "evidence_id": "evidence-b",
                    "pages": [27],
                },
            ]
        }
    }
    issue = ValidationIssue(
        schema_version="1.0",
        message="The failed summary claim is not established by its evidence.",
        severity="error",
        affected_section="summary.claim_evidence_map[1]",
        rule_id="claim_support",
        repair_target="summary",
        entity_id="evidence-b",
    )

    normalized = _normalize_regeneration_issue(issue, artifacts)
    rewritten_identity = _normalize_regeneration_issue(
        replace(issue, entity_id="replacement-evidence"), artifacts
    )

    assert normalized.evidence_ids == ["evidence-b"]
    assert normalized.pages == [27]
    assert normalized.failure_fingerprint == rewritten_identity.failure_fingerprint


def test_indexed_summary_claim_support_failure_gets_exact_repair_path():
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "claim": "Failed claim.",
                    "evidence_id": "evidence-conclusion",
                    "pages": [40, 41],
                }
            ]
        }
    }
    issue = ValidationIssue(
        schema_version="1.0",
        message="A strong claim is supported only by a section summary.",
        severity="error",
        affected_section="summary.claim_evidence_map[0]",
        rule_id="claim_support",
        repair_target="summary",
        entity_id="evidence-conclusion",
    )

    plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=artifacts,
        broad_retry_available=True,
    )

    assert plan.mode == "targeted"
    assert len(plan.targets) == 1
    assert plan.targets[0].repair_action == "REGENERATE_ITEM"
    assert plan.targets[0].repair_strategy == "current_evidence"
    assert plan.targets[0].allowed_paths == ["summary.claim_evidence_map[0].claim"]
    assert plan.targets[0].selected_evidence_ids == ["evidence-conclusion"]


def test_validation_loop_preflights_empty_summary_package_to_safe_removal(tmp_path):
    class _StopAtRegeneration(Exception):
        pass

    artifacts = _artifacts_without_retained_claims(
        summary={
            "tldr": "",
            "executive_summary": "",
            "claim_evidence_map": [
                {
                    "claim": "The unsupported claim has no retained backing.",
                    "evidence_id": "rejected-source",
                    "pages": [27],
                }
            ],
        }
    )
    issue = ValidationIssue(
        schema_version="1.0",
        message="The claim is not established by its cited source.",
        severity="error",
        affected_section="summary.claim_evidence_map:1.claim",
        rule_id="grounding",
    )
    runtime = _runtime(tmp_path)
    regeneration_requests = []

    def _stop_at_regeneration(request):
        regeneration_requests.append(request)
        raise _StopAtRegeneration

    with pytest.raises(_StopAtRegeneration):
        _run_validation_regeneration_loop(
            runtime=runtime,
            mode_ctx=runtime.ctx,
            base_payload=_payload(),
            current_artifacts=artifacts,
            current_validation_report=ValidationReport(
                schema_version="1.1",
                status="fail",
                severity="error",
                issues=[issue],
            ),
            evidence_packs={
                "findings": {"findings": []},
                "doc_map": {"sections": []},
            },
            source_status=artifacts["source_status"],
            category_labels=["Category"],
            vector_store_id=None,
            dependencies=_deps(regenerate_artifacts=_stop_at_regeneration),
        )

    assert len(regeneration_requests) == 1
    target = regeneration_requests[0].plan.targets[0]
    assert target.repair_action == "REMOVE_CLAIM"
    assert target.repair_strategy == "safe_removal"
    assert target.allowed_paths == ["summary.claim_evidence_map[0]"]


def test_insight_repair_authorizes_same_claim_grounding_warning_fields():
    insight_id = "insight-1"
    artifacts = {
        "insights_final": [
            {
                "id": insight_id,
                "text": "A partly unsupported insight.",
                "so_what": "A partly unsupported implication.",
                "now_what": "A partly unsupported recommendation.",
                "evidence_id": "f1",
                "evidence": "Retained evidence.",
            }
        ],
        "insights_candidates": [],
    }
    issues = [
        ValidationIssue(
            message="The recommendation is unsupported.",
            severity="error",
            affected_section=f"insights:{insight_id}.now_what",
            rule_id="grounding",
            repair_target="insights_bundle",
            entity_id=f"insight:{insight_id}:now_what",
            evidence_ids=["f1"],
        ),
        ValidationIssue(
            message="The public insight contains an unsupported clause.",
            severity="warning",
            affected_section=f"insights:{insight_id}.text",
            rule_id="grounding",
            repair_target="insights_bundle",
            entity_id=f"insight:{insight_id}:text",
            evidence_ids=["f1"],
        ),
        ValidationIssue(
            message="The implication contains an unsupported clause.",
            severity="warning",
            affected_section=f"insights:{insight_id}.so_what",
            rule_id="grounding",
            repair_target="insights_bundle",
            entity_id=f"insight:{insight_id}:so_what",
            evidence_ids=["f1"],
        ),
    ]

    plan = _build_regeneration_plan(
        issues=issues,
        artifacts=artifacts,
        broad_retry_available=True,
    )

    assert plan.mode == "targeted"
    assert len(plan.targets) == 1
    assert plan.targets[0].allowed_paths == [
        f"insights_final[item={insight_id}].now_what",
        f"insights_final[item={insight_id}].so_what",
        f"insights_final[item={insight_id}].text",
    ]
    assert plan.targets[0].repair_action == "REGENERATE_ITEM"


def test_summary_repair_keeps_same_claim_grounding_context_only():
    claim_id = "soft_copy:summary:claim-hash"
    claim = "The report covers gaming performance."
    artifacts = {
        "summary": {
            "tldr": "A broad summary sentence.",
            "executive_summary": claim,
            "claim_evidence_map": [
                {"id": "claim-one", "claim": claim, "evidence_id": "f1"}
            ],
        }
    }
    issues = [
        ValidationIssue(
            message="The linked source does not establish this claim.",
            severity="error",
            affected_section="summary.claim_evidence_map:claim-one.claim",
            rule_id="grounding",
            entity_id=claim_id,
        ),
        ValidationIssue(
            message="The summary sentence is contradicted by its evidence.",
            severity="error",
            affected_section="summary.executive_summary",
            rule_id="grounding",
            entity_id=claim_id,
        ),
        ValidationIssue(
            message="The source also leaves the claim unestablished.",
            severity="warning",
            affected_section="summary.executive_summary",
            rule_id="grounding",
            entity_id=claim_id,
        ),
        ValidationIssue(
            message="The TLDR opening could be more concrete.",
            severity="warning",
            affected_section="summary.tldr",
            rule_id="artifact_quality",
            entity_id="summary.tldr",
        ),
    ]

    plan = _build_regeneration_plan(
        issues=issues,
        artifacts=artifacts,
        broad_retry_available=False,
    )

    planned_issues = [issue for target in plan.targets for issue in target.issues]
    assert any(
        issue.severity == "warning" and issue.rule_id == "grounding"
        for issue in planned_issues
    )
    assert all(issue.rule_id != "artifact_quality" for issue in planned_issues)


def test_summary_repair_maps_duplicate_claim_surfaces_together():
    copy_text = "The report benchmarks gaming, commerce, and finance applications."
    provenance = build_soft_copy_claim_provenance(
        artifact_family="summary",
        text=copy_text,
        declared_claims=[
            {
                "claim": copy_text,
                "classification": "factual",
                "evidence_ids": ["e1"],
            }
        ],
        evidence_span_index={},
        producing_prompt_identity={"namespace": "test/summary"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    artifacts = {
        "summary": {
            "tldr": copy_text,
            "card_tldr_compact": copy_text,
            "executive_summary": copy_text,
        },
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(provenance),
    }
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                message="The evidence does not establish the benchmark framing.",
                severity="error",
                affected_section="summary",
                rule_id="grounding",
                repair_target="summary",
                entity_id=provenance[0].claim_id,
            )
        ],
        artifacts=artifacts,
        broad_retry_available=True,
    )

    assert plan.mode == "targeted"
    assert len(plan.targets) == 1
    assert plan.targets[0].allowed_paths == [
        "summary.card_tldr_compact[claim_index=0]",
        "summary.executive_summary[claim_index=0]",
        "summary.tldr[claim_index=0]",
    ]


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
    "test_long_validation_candidate_pack_stores_and_loads_after_path_compaction",
    "test_promote_retained_claim_candidate_rejects_artifact_mismatch",
    "test_build_regeneration_plan_skips_info_and_orders_errors_first",
    "test_build_regeneration_plan_maps_public_artifact_copy_to_its_family",
    "test_build_regeneration_plan_keeps_hard_repair_claim_scoped",
    "test_hard_soft_copy_repair_keeps_coupled_grounding_warnings_in_plan",
    "test_mobile_numbers_failure_targets_exact_insight_so_what_leaf",
    "test_persisting_insight_metric_failures_preempt_linkedin_and_skip_noop_copy",
    "test_repair_memory_does_not_upgrade_unknown_severity_to_hard_error",
    "test_multi_insight_retry_does_not_offer_single_item_safe_removal",
    "test_summary_claim_map_grounding_is_limited_to_the_failed_item",
    "test_indexed_summary_claim_issue_resolves_only_the_failed_item",
    "test_indexed_summary_claim_support_failure_gets_exact_repair_path",
    "test_validation_loop_preflights_empty_summary_package_to_safe_removal",
    "test_insight_repair_authorizes_same_claim_grounding_warning_fields",
    "test_summary_repair_keeps_same_claim_grounding_context_only",
    "test_summary_repair_maps_duplicate_claim_surfaces_together",
    "test_run_report_analysis_rejects_unsupported_repair_target",
    "test_run_report_analysis_snapshot_preserves_internal_payload_metadata",
]
