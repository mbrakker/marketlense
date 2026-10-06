# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


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
