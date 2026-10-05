# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_scope_validation_rejects_tampered_derived_artifact_despite_allowed_dependency() -> (
    None
):
    plan = SimpleNamespace(
        targets=[
            SimpleNamespace(allowed_paths=["summary.tldr[claim_index=0]"])
        ]
    )
    before = {
        "summary": {"tldr": "Before."},
        "insights_final": [{"id": "one", "text": "Before."}],
        "metric_spine": [{"value": "1"}],
        "key_figures": [{"figure": "1"}],
        "cover_semantics": {"title": "Stable"},
    }
    candidate = {
        **deepcopy(before),
        "summary": {"tldr": "After."},
        "metric_spine": [{"value": "2"}],
        "key_figures": [{"figure": "2"}],
    }

    report = _scope_validation_report(before=before, after=candidate, plan=plan)

    assert report.status == "fail"
    assert [issue.affected_section for issue in report.issues] == [
        "key_figures[0].figure",
        "metric_spine[0].value",
    ]
    assert {issue.rule_id for issue in report.issues} == {
        "regeneration_scope_violation"
    }


def test_scope_validation_rejects_unlisted_nested_field() -> None:
    plan = SimpleNamespace(
        targets=[SimpleNamespace(allowed_paths=["summary.tldr[claim_index=0]"])]
    )
    before = {"summary": {"tldr": "Before.", "executive_summary": "Stable."}}
    after = {"summary": {"tldr": "Repaired.", "executive_summary": "Changed sibling."}}

    report = _scope_validation_report(before=before, after=after, plan=plan)

    assert report.status == "fail"
    assert [(item.rule_id, item.affected_section) for item in report.issues] == [
        (
            "regeneration_scope_violation",
            "summary.executive_summary[claim_index=0]",
        )
    ]


def test_scope_validation_rejects_mutated_sibling_item() -> None:
    plan = SimpleNamespace(
        targets=[SimpleNamespace(allowed_paths=["insights_final[item=one].text"])]
    )
    before = {
        "insights_final": [
            {"id": "one", "text": "Failed claim."},
            {"id": "two", "text": "Untouched sibling."},
        ]
    }
    after = deepcopy(before)
    after["insights_final"][0]["text"] = "Repaired claim."
    after["insights_final"][1]["text"] = "Altered sibling."

    report = _scope_validation_report(before=before, after=after, plan=plan)

    assert report.status == "fail"
    assert [item.affected_section for item in report.issues] == [
        "insights_final[item=two].text"
    ]


def test_scope_allows_only_the_claim_map_row_derived_from_summary_copy_removal() -> (
    None
):
    from src.orchestrators._report_analysis_orchestrator.validation import (
        _verified_deterministic_mutation_paths,
    )

    retained_text = "The retained cohort remains stable."
    removed_text = "An unsupported forecast is removed."
    retained_claim = _soft_copy_claim(
        family="summary", text=retained_text, evidence_id="finding-1", page=6
    )
    removed_claim = _soft_copy_claim(
        family="summary", text=removed_text, evidence_id="finding-2", page=7
    )
    before = {
        "summary": {
            "executive_summary": f"{retained_text} {removed_text}",
            "claim_evidence_map": [
                {
                    "id": "retained",
                    "claim": retained_text,
                    "evidence_id": "finding-1",
                    "pages": [6],
                },
                {
                    "id": "removed",
                    "claim": removed_text,
                    "evidence_id": "finding-2",
                    "pages": [7],
                },
            ],
        },
        "soft_copy_claim_provenance": {
            "schema_version": "1.0",
            "claims": [retained_claim, removed_claim],
        },
    }
    after = deepcopy(before)
    after["summary"]["executive_summary"] = retained_text
    after["summary"]["claim_evidence_map"].pop(1)
    after["soft_copy_claim_provenance"]["claims"].pop(1)
    removed_map_path = "summary.claim_evidence_map[item=removed]"
    plan = SimpleNamespace(
        targets=[
            SimpleNamespace(
                target_section="summary",
                repair_action="REMOVE_CLAIM",
                allowed_paths=["summary.executive_summary[claim_index=1]"],
                issues=[SimpleNamespace(entity_id=removed_claim["claim_id"])],
            )
        ]
    )

    verified_paths = _verified_deterministic_mutation_paths(
        paths=[removed_map_path], before=before, after=after, plan=plan
    )
    scope = _scope_validation_report(
        before=before,
        after=after,
        plan=plan,
        verified_derived_roots=frozenset({"soft_copy_claim_provenance"}),
        deterministic_mutation_paths=[removed_map_path],
    )
    unplanned_scope = _scope_validation_report(
        before=before,
        after=after,
        plan=plan,
        verified_derived_roots=frozenset({"soft_copy_claim_provenance"}),
        deterministic_mutation_paths=["summary.claim_evidence_map[item=retained]"],
    )
    integrity = validate_regeneration_candidate(
        current_artifacts=before,
        candidate_artifacts=after,
        evidence_packs={},
        ctx=_ctx(),
        removed_summary_claim_paths=tuple(verified_paths),
    )
    reintroduced = deepcopy(after)
    reintroduced["summary"]["claim_evidence_map"].append(
        before["summary"]["claim_evidence_map"][1]
    )
    reintroduced_integrity = validate_regeneration_candidate(
        current_artifacts=before,
        candidate_artifacts=reintroduced,
        evidence_packs={},
        ctx=_ctx(),
        removed_summary_claim_paths=tuple(verified_paths),
    )
    ambiguous_before = deepcopy(before)
    ambiguous_claim = _soft_copy_claim(
        family="summary",
        text="A second claim uses the same evidence.",
        evidence_id="finding-2",
        page=7,
    )
    ambiguous_before["soft_copy_claim_provenance"]["claims"].append(
        ambiguous_claim
    )
    ambiguous_after = deepcopy(after)
    ambiguous_after["soft_copy_claim_provenance"]["claims"].append(
        ambiguous_claim
    )
    ambiguous_paths = _verified_deterministic_mutation_paths(
        paths=[removed_map_path],
        before=ambiguous_before,
        after=ambiguous_after,
        plan=plan,
    )

    assert verified_paths == {removed_map_path}
    assert not ambiguous_paths
    assert scope.status == "pass"
    assert unplanned_scope.status == "fail"
    assert not any(
        "lost the original material evidence" in issue.message
        for issue in integrity.issues
    )
    assert any(
        issue.rule_id == "regeneration_removed_summary_claim_reintroduced"
        for issue in reintroduced_integrity.issues
    )
    assert after["summary"]["claim_evidence_map"] == [
        before["summary"]["claim_evidence_map"][0]
    ]


def test_scope_validation_tracks_stable_item_additions_and_removals() -> None:
    before = {
        "insights_final": [
            {"id": "one", "text": "Keep."},
            {"id": "failed", "text": "Remove."},
        ]
    }
    after = {
        "insights_final": [
            {"id": "one", "text": "Keep."},
            {"id": "new", "text": "Added."},
        ]
    }
    plan = SimpleNamespace(
        targets=[SimpleNamespace(allowed_paths=["insights_final[item=failed]"])]
    )

    report = _scope_validation_report(before=before, after=after, plan=plan)

    assert report.status == "fail"
    assert [issue.affected_section for issue in report.issues] == [
        "insights_final[item=new]"
    ]


def test_candidate_audit_records_verified_dependent_paths() -> None:
    before = {
        "insights_final": [{"id": "one", "text": "Old claim."}],
        "metric_spine": [{"id": "one", "value": "stale"}],
    }
    after = {
        "insights_final": [{"id": "one", "text": "New claim."}],
        "metric_spine": [{"id": "one", "value": "derived"}],
    }
    runtime = SimpleNamespace(
        ctx=SimpleNamespace(
            report_id="report",
            validation_run_id="validation",
            cohort_id="cohort",
            run_id="run",
            configuration_hash="config",
            policy_hash="policy",
            producer_commit_sha="commit",
        ),
        file=SimpleNamespace(file_id="report"),
    )
    plan = SimpleNamespace(
        targets=[
            SimpleNamespace(
                allowed_paths=["insights_final[item=one].text"],
                repair_action="CORRECT_PROTECTED_FACT",
                repair_strategy="retained_evidence",
                selected_evidence_ids=[],
                quarantined_evidence_ids=[],
            )
        ]
    )

    audit = _candidate_audit(
        runtime=runtime,
        attempt_index=1,
        transformation_scope=["insights_final"],
        current_artifacts=before,
        candidate_artifacts=after,
        current_artifacts_path="artifacts.json",
        candidate_artifacts_path="candidate.json",
        candidate_result=CandidateIntegrityResult(
            issues=[],
            evidence_lineage=[],
            verified_derived_roots=frozenset({"metric_spine"}),
        ),
        plan=plan,
    )

    assert audit.allowed_paths == ["insights_final[item=one].text"]
    assert audit.verified_dependent_paths == ["metric_spine[item=one].value"]


def test_candidate_audit_retains_planned_and_applied_summary_leaf_paths() -> None:
    claim_path = "summary.claim_evidence_map[item=claim-one].claim"
    copy_path = "summary.executive_summary[claim_index=0]"
    before = {
        "summary": {
            "claim_evidence_map": [
                {"id": "claim-one", "claim": "Old source claim."}
            ],
            "executive_summary": "Old public claim. Stable sibling.",
        }
    }
    after = deepcopy(before)
    after["summary"]["claim_evidence_map"][0]["claim"] = "New source claim."
    after["summary"]["executive_summary"] = "New public claim. Stable sibling."
    target_fields = {
        "repair_action": "REGENERATE_ITEM",
        "repair_strategy": "current_evidence",
        "selected_evidence_ids": ["evidence-1"],
        "quarantined_evidence_ids": [],
    }
    plan = SimpleNamespace(
        targets=[
            SimpleNamespace(allowed_paths=[claim_path], **target_fields),
            SimpleNamespace(allowed_paths=[copy_path], **target_fields),
        ]
    )
    decisions = [
        RepairDecision(
            diagnosed_failure_class="retained_claim.number_value_unit_match",
            repair_action="REGENERATE_ITEM",
            repair_strategy="current_evidence",
            evidence_ids_used=["evidence-1"],
            changed_paths=[path],
            minimal_patch=[
                RepairPatchOperation(op="replace", path=path, value=value)
            ],
        )
        for path, value in (
            (claim_path, "New source claim."),
            (copy_path, "New public claim."),
        )
    ]
    response = SimpleNamespace(
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
        selected_evidence_ids=["evidence-1"],
        repair_decisions=decisions,
    )
    runtime = SimpleNamespace(
        ctx=SimpleNamespace(
            report_id="report",
            validation_run_id="validation",
            cohort_id="cohort",
            run_id="run",
            configuration_hash="config",
            policy_hash="policy",
            producer_commit_sha="commit",
        ),
        file=SimpleNamespace(file_id="report"),
    )

    audit = _candidate_audit(
        runtime=runtime,
        attempt_index=1,
        transformation_scope=["summary"],
        current_artifacts=before,
        candidate_artifacts=after,
        current_artifacts_path="artifacts.json",
        candidate_artifacts_path="candidate.json",
        candidate_result=CandidateIntegrityResult(
            issues=[], evidence_lineage=[], verified_derived_roots=frozenset()
        ),
        plan=plan,
        regeneration_response=response,
    )

    assert audit.allowed_paths == sorted([claim_path, copy_path])
    assert [decision.changed_paths for decision in audit.repair_decisions] == [
        [claim_path],
        [copy_path],
    ]


def test_scope_validation_allows_only_verified_deterministic_dependents() -> None:
    before = {
        "insights_final": [{"id": "one", "text": "Old claim."}],
        "metric_spine": [{"id": "one", "value": "stale"}],
    }
    candidate = {
        "insights_final": [{"id": "one", "text": "New claim."}],
        "metric_spine": [{"id": "one", "value": "derived"}],
    }
    plan = SimpleNamespace(
        targets=[SimpleNamespace(allowed_paths=["insights_final[item=one].text"])]
    )

    assert (
        _scope_validation_report(
            before=before,
            after=candidate,
            plan=plan,
            verified_derived_roots=frozenset({"metric_spine"}),
        ).status
        == "pass"
    )
    report = _scope_validation_report(
        before=before,
        after=candidate,
        plan=plan,
        verified_derived_roots=frozenset(),
    )
    assert [issue.affected_section for issue in report.issues] == [
        "metric_spine[item=one].value"
    ]


def test_retained_claim_diagnostics_are_structured_before_and_after_repair() -> None:
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "summary-claim-1",
                    "claim": "European loyalty reached 99% in 2023.",
                    "evidence_id": "finding-1",
                },
                {
                    "id": "summary-claim-2",
                    "claim": "An unbound assertion remains.",
                    "evidence_id": "missing-evidence",
                },
            ]
        },
        "quotes_final": [
            {
                "id": "quote-1",
                "text": "“Customers choose the clear option.”",
                "evidence_id": "quote-source-1",
            }
        ],
    }
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "finding-1",
                    "text": "European loyalty reached 49% in 2024.",
                }
            ]
        },
        "quote_candidates": {
            "quote_candidates": [
                {"id": "quote-source-1", "text": "Customers prefer the clear option."}
            ]
        },
    }

    diagnostics = retained_claim_repair_issues(artifacts, evidence_packs)
    baseline_report = _with_retained_claim_repair_diagnostics(
        ValidationReport(schema_version="1.1", status="fail", issues=[]),
        artifacts,
        evidence_packs,
    )
    candidate = validate_regeneration_candidate(
        current_artifacts=artifacts,
        candidate_artifacts=deepcopy(artifacts),
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    expected_rules = {
        "retained_claim.number_value_unit_match",
        "retained_claim.protected_fact_value_consistency",
        "retained_claim.protected_fact_timeframe_consistency",
        "retained_claim.quote_match",
        "retained_claim.evidence_reference_completeness",
    }
    assert expected_rules <= {issue.rule_id for issue in diagnostics}
    assert expected_rules <= {issue.rule_id for issue in baseline_report.issues}
    assert expected_rules <= {issue.rule_id for issue in candidate.issues}
    assert all(
        issue.entity_id and issue.affected_section and issue.evidence_ids
        for issue in diagnostics
    )
    assert all(issue.rule_id.startswith("retained_claim.") for issue in diagnostics)


def _retained_claim_severity_fixture() -> tuple[dict, dict]:
    return (
        {
            "summary": {
                "tldr": "Keep this section stable.",
                "claim_evidence_map": [
                    {
                        "id": "summary-claim-1",
                        "claim": "European loyalty reached 99% in 2023.",
                        "evidence_id": "finding-1",
                    }
                ],
            }
        },
        {
            "findings": {
                "findings": [
                    {
                        "id": "finding-1",
                        "text": "European loyalty reached 49% in 2024.",
                    }
                ]
            }
        },
    )


@pytest.mark.parametrize("baseline_severity", ["error", "warning"])
def test_unchanged_retained_claim_preserves_promoted_baseline_severity(
    baseline_severity: str,
) -> None:
    artifacts, evidence_packs = _retained_claim_severity_fixture()
    baseline_diagnostics = retained_claim_repair_issues(artifacts, evidence_packs)
    baseline_severities = {
        _failure_fingerprint(issue).key: baseline_severity
        for issue in baseline_diagnostics
    }

    candidate = validate_regeneration_candidate(
        current_artifacts=artifacts,
        candidate_artifacts=deepcopy(artifacts),
        evidence_packs=evidence_packs,
        ctx=_ctx(),
        baseline_retained_claim_severities=baseline_severities,
    )

    number_issue = next(
        issue
        for issue in candidate.issues
        if issue.rule_id == "retained_claim.number_value_unit_match"
    )
    assert number_issue.severity == baseline_severity


def test_changed_retained_claim_with_new_unsupported_fact_is_an_error() -> None:
    artifacts, evidence_packs = _retained_claim_severity_fixture()
    baseline_diagnostics = retained_claim_repair_issues(artifacts, evidence_packs)
    baseline_severities = {
        _failure_fingerprint(issue).key: "warning"
        for issue in baseline_diagnostics
    }
    candidate_artifacts = deepcopy(artifacts)
    candidate_artifacts["summary"]["claim_evidence_map"][0][
        "id"
    ] = "summary-claim-2"
    candidate_artifacts["summary"]["claim_evidence_map"][0][
        "claim"
    ] = "European loyalty reached 88% in 2022."

    candidate = validate_regeneration_candidate(
        current_artifacts=artifacts,
        candidate_artifacts=candidate_artifacts,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
        baseline_retained_claim_severities=baseline_severities,
    )

    introduced_claim_issue = next(
        issue
        for issue in candidate.issues
        if issue.rule_id == "retained_claim.number_value_unit_match"
        and issue.entity_id == "summary_claim:summary-claim-2"
    )
    assert introduced_claim_issue.severity == "error"
    delta = _repair_delta(
        ValidationReport(
            schema_version="1.1", status="fail", issues=baseline_diagnostics
        ),
        ValidationReport(
            schema_version="1.1", status="fail", issues=candidate.issues
        ),
    )
    assert _failure_fingerprint(introduced_claim_issue).key in {
        fingerprint.key for fingerprint in delta.introduced
    }


def test_repaired_retained_claim_fingerprint_moves_to_resolved() -> None:
    artifacts, evidence_packs = _retained_claim_severity_fixture()
    baseline_diagnostics = retained_claim_repair_issues(artifacts, evidence_packs)
    baseline_severities = {
        _failure_fingerprint(issue).key: issue.severity
        for issue in baseline_diagnostics
    }
    repaired_artifacts = deepcopy(artifacts)
    repaired_artifacts["summary"]["claim_evidence_map"][0][
        "claim"
    ] = "European loyalty reached 49% in 2024."
    candidate_diagnostics = retained_claim_repair_issues(
        repaired_artifacts,
        evidence_packs,
        previous_artifacts=artifacts,
        baseline_retained_claim_severities=baseline_severities,
    )
    delta = _repair_delta(
        ValidationReport(
            schema_version="1.1", status="fail", issues=baseline_diagnostics
        ),
        ValidationReport(
            schema_version="1.1", status="pass", issues=candidate_diagnostics
        ),
    )

    resolved_keys = {item.key for item in delta.resolved}
    repaired_claim_keys = {
        _failure_fingerprint(issue).key
        for issue in baseline_diagnostics
        if issue.entity_id == "summary_claim:summary-claim-1"
    }
    assert repaired_claim_keys
    assert repaired_claim_keys <= resolved_keys


def test_candidate_verifies_only_prompt_cache_metadata_used_by_repair() -> None:
    current, evidence_packs = _retained_artifact_and_evidence()
    namespace = "report_vs/artifacts/regenerate/expert_comment"
    family = "report_vs/artifacts/expert_comment"
    current["_cache"] = {
        "prompts": {},
        "producing_prompt_identities": {},
        "regeneration_prompt_requirements": {},
    }
    identity = {
        "namespace": namespace,
        "prompt_content_hash": "a" * 64,
        "execution_identity": "b" * 64,
        "configuration_policy_hash": "c" * 64,
    }
    candidate = deepcopy(current)
    candidate["_cache"]["prompts"][namespace] = deepcopy(identity)
    candidate["_cache"]["producing_prompt_identities"][family] = deepcopy(identity)
    candidate["_cache"]["regeneration_prompt_requirements"][family] = namespace

    verified = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
        planned_prompt_namespaces=[namespace],
        actual_prompt_namespaces=[namespace],
    )

    assert "_cache" in verified.verified_derived_roots
    plan = SimpleNamespace(
        targets=[SimpleNamespace(allowed_paths=["expert_comment[claim_index=0]"])]
    )
    scope = _scope_validation_report(
        before=current,
        after=candidate,
        plan=plan,
        verified_derived_roots=verified.verified_derived_roots,
    )
    assert scope.status == "pass"

    rogue = deepcopy(candidate)
    rogue_namespace = "report_vs/artifacts/regenerate/summary"
    rogue["_cache"]["prompts"][rogue_namespace] = {
        "namespace": rogue_namespace,
        "prompt_content_hash": "d" * 64,
        "execution_identity": "e" * 64,
        "configuration_policy_hash": "f" * 64,
    }
    unverified = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=rogue,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
        planned_prompt_namespaces=[namespace],
        actual_prompt_namespaces=[namespace],
    )
    assert "_cache" not in unverified.verified_derived_roots


def test_scope_validation_allows_soft_copy_provenance_for_repaired_soft_copy() -> None:
    plan = SimpleNamespace(
        targets=[SimpleNamespace(allowed_paths=["summary.tldr[claim_index=0]"])]
    )
    before = {
        "summary": {"tldr": "Before."},
        "soft_copy_claim_provenance": {"claims": [{"claim_id": "before"}]},
        "cover_semantics": {"title": "Stable"},
    }
    candidate = {
        **deepcopy(before),
        "summary": {"tldr": "After."},
        "soft_copy_claim_provenance": {"claims": [{"claim_id": "after"}]},
    }

    assert (
        _scope_validation_report(
            before=before,
            after=candidate,
            plan=plan,
            verified_derived_roots=frozenset({"soft_copy_claim_provenance"}),
        ).status
        == "pass"
    )
    unverified = _scope_validation_report(before=before, after=candidate, plan=plan)
    assert unverified.status == "fail"
    assert all(
        issue.rule_id == "regeneration_scope_violation" for issue in unverified.issues
    )

    candidate["cover_semantics"] = {"title": "Unrelated change"}

    report = _scope_validation_report(before=before, after=candidate, plan=plan)

    assert report.status == "fail"
    assert [issue.affected_section for issue in report.issues] == [
        "cover_semantics.title",
        "soft_copy_claim_provenance.claims[item=after]",
        "soft_copy_claim_provenance.claims[item=before]",
    ]


def test_insight_repair_allows_only_verified_derived_projection() -> None:
    before = {
        "insights_final": [{"id": "one", "text": "Old claim."}],
        "metric_spine": [{"value": "stale"}],
    }
    candidate = deepcopy(before)
    candidate["insights_final"][0]["text"] = "New claim."
    candidate["metric_spine"] = []
    verified, issues = _verify_derived_artifact_roots(
        current_artifacts=before,
        candidate_artifacts=candidate,
        evidence_packs={},
    )
    plan = SimpleNamespace(
        targets=[
            SimpleNamespace(allowed_paths=["insights_final[item=one].text"])
        ]
    )

    assert not issues
    assert "metric_spine" in verified
    assert (
        _scope_validation_report(
            before=before,
            after=candidate,
            plan=plan,
            verified_derived_roots=verified,
        ).status
        == "pass"
    )

    candidate["metric_spine"] = [{"value": "invented"}]
    verified, issues = _verify_derived_artifact_roots(
        current_artifacts=before,
        candidate_artifacts=candidate,
        evidence_packs={},
    )
    assert "metric_spine" not in verified
    assert any(issue.affected_section == "metric_spine" for issue in issues)


def test_insight_repair_rebuilds_only_source_proven_topics() -> None:
    toc = [
        {
            "section_id": "topic-one",
            "section_title": "Source topic",
            "pages": [3],
            "key_points": ["Source topic detail"],
        }
    ]
    before = {
        "toc_entries": toc,
        "summary": {},
        "insights_final": [
            {"id": "one", "evidence_id": "old-evidence", "pages": [3]}
        ],
        "topics_covered": [
            {
                "schema_version": "1.0",
                "topic_id": "topic-one",
                "topic": "Source topic",
                "subtopics": ["Source topic detail"],
                "why_it_matters": "Source topic detail",
                "evidence_ids": [],
                "pages": [3],
                "status": "toc_only",
            }
        ],
    }
    candidate = deepcopy(before)
    candidate["insights_final"][0]["evidence_id"] = "finding-one"
    candidate["topics_covered"][0]["evidence_ids"] = ["finding-one"]
    candidate["topics_covered"][0]["status"] = "source_backed"
    plan = SimpleNamespace(
        targets=[
            SimpleNamespace(
                allowed_paths=["insights_final[item=one].evidence_id"]
            )
        ]
    )

    verified, issues = _verify_derived_artifact_roots(
        current_artifacts=before,
        candidate_artifacts=candidate,
        evidence_packs={},
    )

    assert not issues
    assert "topics_covered" in verified
    assert (
        _scope_validation_report(
            before=before,
            after=candidate,
            plan=plan,
            verified_derived_roots=verified,
        ).status
        == "pass"
    )

    candidate["topics_covered"][0]["evidence_ids"] = ["unrelated"]
    verified, issues = _verify_derived_artifact_roots(
        current_artifacts=before,
        candidate_artifacts=candidate,
        evidence_packs={},
    )
    assert "topics_covered" not in verified
    assert any(issue.affected_section == "topics_covered" for issue in issues)


def test_summary_repair_allows_only_verified_chart_projection() -> None:
    before = {
        "summary": {"tldr": "Old summary."},
        "chart_insight_cards": [{"caption": "Old chart."}],
    }
    candidate = {
        "summary": {"tldr": "New summary."},
        "chart_insight_cards": [],
    }
    plan = SimpleNamespace(
        targets=[
            SimpleNamespace(allowed_paths=["summary.tldr[claim_index=0]"])
        ]
    )

    verified, issues = _verify_derived_artifact_roots(
        current_artifacts=before,
        candidate_artifacts=candidate,
        evidence_packs={},
    )

    assert not issues
    assert "chart_insight_cards" in verified
    assert (
        _scope_validation_report(
            before=before,
            after=candidate,
            plan=plan,
            verified_derived_roots=verified,
        ).status
        == "pass"
    )

    candidate["chart_insight_cards"] = [{"caption": "Invented chart."}]
    verified, issues = _verify_derived_artifact_roots(
        current_artifacts=before,
        candidate_artifacts=candidate,
        evidence_packs={},
    )
    assert "chart_insight_cards" not in verified
    assert any(issue.affected_section == "chart_insight_cards" for issue in issues)


def test_summary_repair_rebuilds_exact_key_figure_and_chart_dependents() -> None:
    evidence_text = "Retail media adoption reached 42% among merchants."
    insight = {
        "id": "metric-one",
        "text": evidence_text,
        "evidence": evidence_text,
        "evidence_id": "f1",
        "metric": {
            "label": "Retail media adoption",
            "value": "42%",
            "unit": "",
            "confidence": "high",
            "segment": "merchants",
        },
    }
    evidence_packs = {
        "findings": {
            "findings": [
                {"id": "f1", "text": evidence_text, "evidence": evidence_text}
            ]
        }
    }
    before = {
        "summary": {
            "executive_summary": "A broad overview.",
            "claim_evidence_map": [{"claim": "Old claim.", "evidence_id": "f1"}],
        },
        "insights_final": [insight],
        "metric_spine": derive_metric_spine_from_insights([insight]),
        "key_figures": [],
        "chart_insight_cards": [],
    }
    candidate = deepcopy(before)
    candidate["summary"]["executive_summary"] = (
        "Retail media adoption reached 42% among merchants."
    )
    writable_roots = {"summary"}

    rebuilt_roots = rebuild_regeneration_derived_artifacts(
        artifacts=candidate,
        evidence_packs=evidence_packs,
        writable_roots=writable_roots,
    )

    assert {"key_figures", "chart_insight_cards"} <= rebuilt_roots
    assert [figure["figure"] for figure in candidate["key_figures"]] == ["42%"]
    assert candidate["chart_insight_cards"][0]["evidence_id"] == "f1"
    verified_roots, issues = _verify_derived_artifact_roots(
        current_artifacts=before,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
    )
    assert not issues
    assert {"key_figures", "chart_insight_cards"} <= verified_roots

    plan = SimpleNamespace(
        targets=[
            SimpleNamespace(
                allowed_paths=["summary.executive_summary[claim_index=0]"]
            )
        ]
    )
    assert (
        _scope_validation_report(
            before=before,
            after=candidate,
            plan=plan,
            verified_derived_roots=verified_roots,
        ).status
        == "pass"
    )

    for root, field in (
        ("key_figures", "figure"),
        ("chart_insight_cards", "caption"),
    ):
        unrelated_change = deepcopy(candidate)
        unrelated_change[root][0][field] = "Unrelated mutation"
        verified_roots, issues = _verify_derived_artifact_roots(
            current_artifacts=before,
            candidate_artifacts=unrelated_change,
            evidence_packs=evidence_packs,
        )
        assert root not in verified_roots
        assert any(
            issue.rule_id == "regeneration_derived_projection"
            and issue.affected_section == root
            for issue in issues
        )
        scope = _scope_validation_report(
            before=before,
            after=unrelated_change,
            plan=plan,
            verified_derived_roots=verified_roots,
        )
        assert scope.status == "fail"
        assert any(
            issue.rule_id == "regeneration_scope_violation"
            and issue.affected_section.startswith(root)
            for issue in scope.issues
        )


__all__ = [name for name in globals() if name.startswith("test_")]
