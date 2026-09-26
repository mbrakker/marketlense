# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_scope_validation_rejects_tampered_derived_artifact_despite_allowed_dependency() -> (
    None
):
    plan = SimpleNamespace(
        targets=[SimpleNamespace(allowed_paths=["summary.tldr", "insights_final"])]
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
    plan = SimpleNamespace(targets=[SimpleNamespace(allowed_paths=["summary.tldr"])])
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
    plan = SimpleNamespace(targets=[SimpleNamespace(allowed_paths=["summary.tldr"])])
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
    candidate = {"insights_final": [], "metric_spine": []}
    verified, issues = _verify_derived_artifact_roots(
        current_artifacts=before,
        candidate_artifacts=candidate,
        evidence_packs={},
    )
    plan = SimpleNamespace(targets=[SimpleNamespace(allowed_paths=["insights_final"])])

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
        "insights_final": [],
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
    candidate["insights_final"] = [
        {"id": "one", "evidence_id": "finding-one", "pages": [3]}
    ]
    candidate["topics_covered"][0]["evidence_ids"] = ["finding-one"]
    candidate["topics_covered"][0]["status"] = "source_backed"
    plan = SimpleNamespace(targets=[SimpleNamespace(allowed_paths=["insights_final"])])

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
    plan = SimpleNamespace(targets=[SimpleNamespace(allowed_paths=["summary"])])

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


__all__ = [name for name in globals() if name.startswith("test_")]
