from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.contracts.regeneration import (
    RegenerationIssue,
    RegenerationPlan,
    RegenerationTarget,
)
from src.contracts.run_context import RunContext
from src.generators.artifact_normalization import (
    artifact_evidence_span_index,
    bind_artifact_evidence_spans,
    page_bound_direct_evidence_packs,
)
from src.generators.report_regeneration_generator import (
    _build_grounding_package,
    _collect_required_relevant_evidence_entries,
)
from src.generators._artifact_generator.storage import (
    finalize_regeneration_candidate_artifacts,
)
from src.generators.validation.regeneration_candidate import (
    validate_regeneration_candidate,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _allowed_paths,
    _issue_grounding,
    _lookup_insight_grounding,
    _lookup_quote_grounding,
    _normalize_regeneration_issue,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _preflight_empty_grounding_strategies,
    _validate_public_editorial_review_payload,
    _verified_deterministic_mutation_paths,
)
from src.utils.errors import AppError
from src.utils.verified_facts import canonical_verified_evidence_packs
from tests._test_regeneration_candidate._shared import (
    _ctx,
    _retained_artifact_and_evidence,
)


def _insight_issue(*evidence_ids: str) -> RegenerationIssue:
    return RegenerationIssue(
        rule_id="grounding",
        affected_section="insights:combo.text",
        message="Repair the composite insight.",
        severity="error",
        entity_id="insight:combo:text",
        evidence_ids=list(evidence_ids),
    )


def _composite_artifacts() -> dict:
    return {
        "insights_final": [
            {
                "id": "combo",
                "text": "Two source-backed observations.",
                "evidence_id": "fact-a",
                "evidence_ids": ["fact-a", "fact-b"],
                "pages": [4, 9],
                "evidence_spans": [
                    {
                        "evidence_id": "fact-a",
                        "source_pack": "verified_facts",
                        "page": 4,
                        "text": "Fact A source truth.",
                    },
                    {
                        "evidence_id": "fact-b",
                        "source_pack": "verified_facts",
                        "page": 9,
                        "text": "Fact B source truth.",
                    },
                ],
            }
        ],
        "insights_candidates": [],
        "quotes_final": [
            {"id": "quote-a", "evidence_ids": ["fact-a"], "page": 4},
            {"id": "quote-b", "evidence_ids": ["fact-b"], "page": 9},
        ],
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "claim-a",
                    "evidence_id": "fact-a",
                    "pages": [4],
                },
                {
                    "id": "claim-b",
                    "evidence_id": "fact-b",
                    "pages": [9],
                },
            ]
        },
    }


def _direct_evidence_packs(ids: list[str]) -> dict:
    return {
        "findings": {
            "family_status": {
                "status": "generated",
                "policy_action": "keep",
                "source": "verified_facts",
            },
            "findings": [
                {
                    "id": evidence_id,
                    "text": f"Source truth for {evidence_id}.",
                    "evidence": f"Source truth for {evidence_id}.",
                    "pages": [index + 1],
                }
                for index, evidence_id in enumerate(ids)
            ],
        }
    }


def _public_scope(obligations: list[dict]) -> dict:
    return {
        "authority": "canonical_verified_facts",
        "source_identity": "source:test|pdf-sha256:" + "a" * 64,
        "verified_fact_digest": "digest-a",
        "verified_facts": {
            "verified-fact:f1": {"fact_id": "f1"},
            "verified-fact:f2": {"fact_id": "f2"},
        },
        "evidence_context": [
            {"evidence_id": "verified-fact:f1", "texts": ["Fact 1."]},
            {"evidence_id": "verified-fact:f2", "texts": ["Fact 2."]},
        ],
        "public_content": [
            {
                "item_id": "insight:i1:text",
                "artifact": "insights_final",
                "field": "text",
                "evidence_ids": ["verified-fact:f1", "verified-fact:f2"],
            }
        ],
        "original_editorial_plan_coverage": {
            "original_plan_identity": "plan-a",
            "original_essential_obligations": obligations,
        },
    }


def _public_items() -> list[dict]:
    return [
        {
            "public_item_id": "insight:i1:text",
            "artifact": "insights_final",
            "field": "text",
            "text": "The final insight develops both source-backed themes.",
            "evidence_ids": ["verified-fact:f1", "verified-fact:f2"],
            "evidence_text": "Fact 1. Fact 2.",
            "repair_target": "insights_bundle",
        }
    ]


def _public_payload(assessments: list[dict]) -> dict:
    return {
        "verdicts": [
            {
                "item_id": "insight:i1:text",
                "status": "pass",
                "classification": "factual_claim",
                "severity": "info",
                "rule_id": "",
                "hard_fail_class": "",
                "reason": "The final wording is supported by both retained facts.",
                "evidence_ids": ["verified-fact:f1", "verified-fact:f2"],
                "repair_target": "",
            }
        ],
        "report_verdict": {
            "status": "pass",
            "severity": "info",
            "rule_id": "",
            "hard_fail_class": "",
            "reason": "Both essential obligations remain materially covered.",
            "evidence_ids": ["verified-fact:f1", "verified-fact:f2"],
            "repair_target": "",
            "affected_item_id": "",
            "dimensions": {
                dimension: {
                    "status": "pass",
                    "reason": "The report satisfies this dimension.",
                }
                for dimension in (
                    "material_coverage",
                    "analytical_depth",
                    "distinctness",
                    "limitations",
                )
            },
        },
        "original_essential_obligation_assessments": assessments,
    }


def _validation_context() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="verified-multifact",
        task_id="contract",
        span_id="1",
    )


def _valid_public_obligations() -> list[dict]:
    return [
        {
            "theme": "Theme A",
            "evidence_ids": ["verified-fact:f1"],
            "importance": "essential",
            "coverage_obligation": "Develop fact A.",
        },
        {
            "theme": "Theme B",
            "evidence_ids": ["verified-fact:f2"],
            "importance": "essential",
            "coverage_obligation": "Develop fact B.",
        },
    ]


def _valid_public_assessments() -> list[dict]:
    return [
        {
            "theme": "Theme A",
            "evidence_ids": ["verified-fact:f1"],
            "status": "covered",
            "supporting_insight_ids": ["insight:i1:text"],
            "explanation": "The final insight explains fact A in the merged analysis.",
        },
        {
            "theme": "Theme B",
            "evidence_ids": ["verified-fact:f2"],
            "status": "covered",
            "supporting_insight_ids": ["insight:i1:text"],
            "explanation": (
                "The same insight also explains fact B in the merged analysis."
            ),
        },
    ]


def test_multifact_issue_grounding_keeps_fact_specific_pages() -> None:
    artifacts = _composite_artifacts()

    fact_a = _normalize_regeneration_issue(_insight_issue("fact-a"), artifacts)
    fact_b = _normalize_regeneration_issue(_insight_issue("fact-b"), artifacts)
    both = _normalize_regeneration_issue(_insight_issue("fact-a", "fact-b"), artifacts)

    assert fact_a.pages == [4]
    assert fact_b.pages == [9]
    assert both.pages == [4, 9]
    assert _issue_grounding("quotes", artifacts) == ([], [])
    assert _lookup_quote_grounding("", artifacts) == ([], [])
    assert _issue_grounding("summary.tldr", artifacts) == ([], [])


def test_ambiguous_duplicate_insight_identity_abstains_from_grounding() -> None:
    artifacts = _composite_artifacts()
    artifacts["insights_candidates"] = [
        {
            "id": "combo",
            "evidence_id": "fact-c",
            "pages": [12],
        }
    ]

    assert _lookup_insight_grounding("combo", artifacts) == ([], [])


def test_ambiguous_duplicate_quote_identity_abstains_from_grounding() -> None:
    artifacts = _composite_artifacts()
    artifacts["quotes_final"].append(
        {"id": "quote-a", "evidence_ids": ["fact-c"], "page": 12}
    )

    assert _lookup_quote_grounding("quote-a", artifacts) == ([], [])


def test_required_regeneration_evidence_is_complete_and_reports_missing() -> None:
    ids = [f"fact-{index}" for index in range(1, 10)]
    packs = _direct_evidence_packs(ids)
    packs["duplicate"] = {"items": [{"id": "fact-1", "pages": [101]}]}
    target = RegenerationTarget(
        target_section="insights_bundle",
        issues=[
            RegenerationIssue(
                rule_id="grounding",
                affected_section="insights:combo.text",
                message="Repair all facts.",
                severity="error",
                evidence_ids=[*ids, "fact-missing"],
            )
        ],
    )

    package = _build_grounding_package(
        target=target,
        prepared=SimpleNamespace(evidence_windows=[]),
        artifacts={"insights_final": []},
        evidence_packs=packs,
        doc_map={},
    )

    assert package["evidence_ids"] == ids
    assert len(package["relevant_evidence"]) == 9
    assert package["missing_evidence_ids"] == ["fact-missing"]
    assert {
        entry.get("entry", entry).get("id") for entry in package["relevant_evidence"]
    } == set(ids)


def test_missing_required_grounding_is_rejected_before_model_strategy() -> None:
    target = RegenerationTarget(
        target_section="summary",
        repair_action="REGENERATE",
        repair_strategy="current_evidence",
        issues=[
            RegenerationIssue(
                rule_id="grounding",
                affected_section="summary.tldr",
                message="Repair the missing source-backed summary.",
                severity="error",
                evidence_ids=["fact-present", "fact-missing"],
            )
        ],
        allowed_paths=["summary.tldr"],
    )
    plan = RegenerationPlan(
        mode="targeted",
        targets=[target],
        broad_retry_allowed=False,
    )

    updated, skipped = _preflight_empty_grounding_strategies(
        plan=plan,
        issues=target.issues,
        artifacts={"summary": {"tldr": "Existing summary."}},
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "fact-present",
                        "evidence": "Present source truth.",
                        "pages": [3],
                    }
                ]
            }
        },
        doc_map={},
        rejected_strategy_keys=set(),
        broad_retry_available=False,
    )

    assert skipped == [("summary", "current_evidence")]
    assert updated.targets == []


def test_duplicate_composite_evidence_representations_merge_all_required_ids() -> None:
    issues = [_insight_issue("fact-a", "fact-b", "fact-c")]
    packs = {
        "findings": {
            "findings": [
                {"id": "fact-a", "evidence_ids": ["fact-b"], "pages": [4, 9]},
                {"id": "fact-a", "evidence_ids": ["fact-c"], "pages": [12]},
            ]
        },
    }

    entries, missing = _collect_required_relevant_evidence_entries(issues, packs, {})

    assert missing == []
    assert {
        evidence_id
        for entry in entries
        for evidence_id in entry.get("entry", entry).get("evidence_ids", [])
    } == {"fact-b", "fact-c"}


def test_composite_finalization_and_candidate_validation_accept_a_plus_b_to_a_plus_c():
    baseline, evidence_packs = _retained_artifact_and_evidence()
    source_pages = {"finding-1": 2, "finding-3": 7, "finding-4": 3}
    for finding in evidence_packs["findings"]["findings"]:
        if finding.get("id") in source_pages:
            finding["pages"] = [source_pages[finding["id"]]]
    span_index = artifact_evidence_span_index(
        doc_map=evidence_packs["doc_map"], evidence_packs=evidence_packs
    )
    composite_baseline = deepcopy(baseline["insights_final"][0])
    composite_baseline["evidence_id"] = "finding-1"
    composite_baseline["evidence_ids"] = ["finding-1", "finding-3"]
    composite_baseline["evidence_spans"] = (
        span_index["finding-1"] + span_index["finding-3"]
    )
    composite_baseline["pages"] = [2, 7]
    baseline["insights_final"][0] = composite_baseline

    candidate = deepcopy(baseline)
    composite_candidate = deepcopy(candidate["insights_final"][0])
    composite_candidate["evidence_ids"] = ["finding-1", "finding-4"]
    composite_candidate["evidence_spans"] = (
        span_index["finding-1"] + span_index["finding-4"]
    )
    composite_candidate["pages"] = [2, 3]
    candidate["insights_final"][0] = composite_candidate

    finalize_regeneration_candidate_artifacts(
        promoted_baseline=baseline,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        atomic_source_patch={"insights_final": deepcopy(candidate["insights_final"])},
        verified_mode=True,
    )

    assert [
        span["evidence_id"] for span in candidate["insights_final"][0]["evidence_spans"]
    ] == ["finding-1", "finding-4"]
    assert candidate["insights_final"][0]["pages"] == [2, 3]

    integrity = validate_regeneration_candidate(
        current_artifacts=baseline,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )
    insight_issues = [
        issue
        for issue in integrity.issues
        if issue.affected_section.startswith("insights_final[item=insight-01]")
    ]
    assert not any(
        issue.rule_id in {"regeneration_source_page", "regeneration_evidence"}
        for issue in insight_issues
    )


def test_rebind_scope_and_deterministic_validation_support_complete_evidence_list() -> (
    None
):
    artifacts = _composite_artifacts()
    issue = _insight_issue("fact-a", "fact-b")
    paths = _allowed_paths(
        "insights_bundle",
        [issue],
        artifacts,
        "REBIND_EVIDENCE",
    )
    item_path = "insights_final[item=combo]"
    assert f"{item_path}.evidence_ids" in paths

    packs = _direct_evidence_packs(["fact-a", "fact-b", "fact-c"])
    before = {
        "insights_final": [
            {
                "id": "combo",
                "text": "Original.",
                "evidence_id": "fact-a",
                "evidence_ids": ["fact-a", "fact-b"],
                "evidence": "A and B",
                "pages": [1, 2],
                "evidence_spans": [],
            }
        ]
    }
    after_item = deepcopy(before["insights_final"][0])
    after_item["evidence_ids"] = ["fact-a", "fact-c"]
    after_item["evidence"] = "Source truth for fact-a. Source truth for fact-c."
    after_item["pages"] = [1, 3]
    after_item["evidence_spans"] = (
        artifact_evidence_span_index(doc_map={}, evidence_packs=packs)["fact-a"]
        + artifact_evidence_span_index(doc_map={}, evidence_packs=packs)["fact-c"]
    )
    after = {"insights_final": [after_item]}
    target = RegenerationTarget(
        target_section="insights_bundle",
        repair_action="REBIND_EVIDENCE",
        issues=[issue],
        allowed_paths=[
            f"{item_path}.evidence_id",
            f"{item_path}.evidence_ids",
            f"{item_path}.evidence",
            f"{item_path}.pages",
            f"{item_path}.evidence_spans",
        ],
        selected_evidence_ids=["fact-a", "fact-c"],
    )

    verified = _verified_deterministic_mutation_paths(
        paths=target.allowed_paths,
        before=before,
        after=after,
        plan=SimpleNamespace(targets=[target]),
        doc_map={},
        evidence_packs=packs,
    )

    actual_paths = [
        f"{item_path}.evidence_ids",
        f"{item_path}.evidence",
        f"{item_path}.pages",
        f"{item_path}.evidence_spans",
    ]
    authorized_paths = [
        f"{item_path}.evidence_id",
        *actual_paths,
    ]
    verified = _verified_deterministic_mutation_paths(
        paths=actual_paths,
        before=before,
        after=after,
        plan=SimpleNamespace(targets=[target]),
        doc_map={},
        evidence_packs=packs,
    )

    assert set(actual_paths).issubset(set(authorized_paths))
    assert verified == set(actual_paths)


def test_rebind_scope_records_a_real_primary_evidence_id_change() -> None:
    packs = _direct_evidence_packs(["fact-a", "fact-b", "fact-c"])
    item_path = "insights_final[item=combo]"
    before = {
        "insights_final": [
            {
                "id": "combo",
                "text": "Original.",
                "evidence_id": "fact-a",
                "evidence_ids": ["fact-a", "fact-b"],
                "evidence": "A and B",
                "pages": [1, 2],
                "evidence_spans": [],
            }
        ]
    }
    after_item = deepcopy(before["insights_final"][0])
    after_item["evidence_id"] = "fact-c"
    after_item["evidence_ids"] = ["fact-c", "fact-b"]
    after_item["evidence"] = "Source truth for fact-c. Source truth for fact-b."
    after_item["pages"] = [3, 2]
    after_item["evidence_spans"] = (
        artifact_evidence_span_index(doc_map={}, evidence_packs=packs)["fact-c"]
        + artifact_evidence_span_index(doc_map={}, evidence_packs=packs)["fact-b"]
    )
    after = {"insights_final": [after_item]}
    target = RegenerationTarget(
        target_section="insights_bundle",
        repair_action="REBIND_EVIDENCE",
        issues=[_insight_issue("fact-c", "fact-b")],
        allowed_paths=[
            f"{item_path}.evidence_id",
            f"{item_path}.evidence_ids",
            f"{item_path}.evidence",
            f"{item_path}.pages",
            f"{item_path}.evidence_spans",
        ],
        selected_evidence_ids=["fact-c", "fact-b"],
    )

    verified = _verified_deterministic_mutation_paths(
        paths=target.allowed_paths,
        before=before,
        after=after,
        plan=SimpleNamespace(targets=[target]),
        doc_map={},
        evidence_packs=packs,
    )

    assert f"{item_path}.evidence_id" in verified


def test_public_review_rejects_incomplete_original_obligation_assessments() -> None:
    obligations = _valid_public_obligations()
    payload = _public_payload([_valid_public_assessments()[0]])

    with pytest.raises(AppError):
        _validate_public_editorial_review_payload(
            payload,
            _public_items(),
            _validation_context(),
            _public_scope(obligations),
        )


def test_public_review_accepts_semantic_merge_of_original_obligations() -> None:
    obligations = _valid_public_obligations()
    payload = _public_payload(_valid_public_assessments())

    _validate_public_editorial_review_payload(
        payload,
        _public_items(),
        _validation_context(),
        _public_scope(obligations),
    )


@pytest.mark.parametrize(
    "non_final_artifact",
    ["summary", "expert_comment", "linkedin_post", "advisory", "distribution"],
)
def test_public_review_requires_support_from_retained_final_insights(
    non_final_artifact: str,
) -> None:
    obligations = _valid_public_obligations()
    items = _public_items()
    items[0]["artifact"] = non_final_artifact
    payload = _public_payload(_valid_public_assessments())

    with pytest.raises(AppError):
        _validate_public_editorial_review_payload(
            payload,
            items,
            _validation_context(),
            _public_scope(obligations),
        )


def test_public_review_fails_closed_without_original_obligation_metadata() -> None:
    payload = _public_payload(_valid_public_assessments())
    scope = _public_scope(_valid_public_obligations())
    scope.pop("original_editorial_plan_coverage")

    with pytest.raises(AppError):
        _validate_public_editorial_review_payload(
            payload,
            _public_items(),
            _validation_context(),
            scope,
        )


def test_public_review_rejects_passing_report_with_partial_obligation() -> None:
    obligations = _valid_public_obligations()
    assessments = _valid_public_assessments()
    assessments[0]["status"] = "partial"
    payload = _public_payload(assessments)

    with pytest.raises(AppError):
        _validate_public_editorial_review_payload(
            payload,
            _public_items(),
            _validation_context(),
            _public_scope(obligations),
        )


def test_public_review_rejects_unknown_obligation_support_or_evidence() -> None:
    obligations = _valid_public_obligations()
    assessment = _valid_public_assessments()[0]
    assessment["theme"] = "Unknown theme"
    assessment["evidence_ids"] = ["verified-fact:unknown"]
    payload = _public_payload([assessment, _valid_public_assessments()[1]])

    with pytest.raises(AppError):
        _validate_public_editorial_review_payload(
            payload,
            _public_items(),
            _validation_context(),
            _public_scope(obligations),
        )


def test_verified_fact_pack_is_opt_in_for_direct_evidence_projection() -> None:
    packs = {
        "findings": {
            "findings": [
                {"id": "finding-a", "evidence": "Finding source.", "pages": [2]}
            ]
        },
        "verified_facts": {
            "verified_facts": [
                {
                    "fact_id": "fact-a",
                    "source_identity": "source:test",
                    "supporting_physical_pages": [7],
                    "provenance": {"source_truth_notes_by_page": {"7": "Fact source."}},
                }
            ]
        },
    }

    assert "verified_facts" not in page_bound_direct_evidence_packs(packs)
    assert "verified_facts" in page_bound_direct_evidence_packs(
        packs, include_verified_facts=True
    )


def test_verified_fact_page_spans_preserve_page_specific_source_truth() -> None:
    facts = {
        "fact-a": {
            "fact_id": "fact-a",
            "source_identity": "source:test|pdf-sha256:" + "b" * 64,
            "statement": "A composite fact uses two source pages.",
            "metric": {
                "value": "40%",
                "unit": "%",
                "timeframe": "2025",
            },
            "supporting_physical_pages": [4, 9],
            "provenance": {
                "source_truth_notes_by_page": {
                    "4": "Page four establishes the first observation.",
                    "9": "Page nine establishes the second observation.",
                }
            },
        }
    }
    packs = canonical_verified_evidence_packs(facts)
    packs["findings"]["findings"][0]["evidence_spans"] = [
        {
            "evidence_id": "verified-fact:fact-a",
            "source_pack": "verified_facts",
            "page": 4,
            "text": "A parallel projection must not replace page four.",
        },
        {
            "evidence_id": "verified-fact:fact-a",
            "source_pack": "verified_facts",
            "page": 9,
            "text": "A parallel projection must not replace page nine.",
        },
    ]

    index = artifact_evidence_span_index(doc_map={}, evidence_packs=packs)
    spans = index["verified-fact:fact-a"]

    assert [(span["page"], span["text"]) for span in spans] == [
        (4, "Page four establishes the first observation."),
        (9, "Page nine establishes the second observation."),
    ]
    assert {span["source_identity"] for span in spans} == {
        "source:test|pdf-sha256:" + "b" * 64
    }

    summary: dict = {}
    final = [
        {
            "id": "insight-a",
            "text": "Editorial wording remains unchanged.",
            "evidence_id": "verified-fact:fact-a",
            "evidence": "stale text must be replaced",
            "pages": [1],
        }
    ]
    bind_artifact_evidence_spans(
        summary=summary,
        insights_candidates=[],
        insights_final=final,
        quotes_final=[],
        doc_map={},
        evidence_packs=packs,
    )

    assert final[0]["text"] == "Editorial wording remains unchanged."
    assert final[0]["pages"] == [4, 9]
    assert [span["text"] for span in final[0]["evidence_spans"]] == [
        "Page four establishes the first observation.",
        "Page nine establishes the second observation.",
    ]


def test_verified_fact_page_spans_do_not_broadcast_across_composite_facts() -> None:
    facts = {
        "fact-a": {
            "fact_id": "fact-a",
            "source_identity": "source:test|pdf-sha256:" + "c" * 64,
            "statement": "Fact A is supported by two pages.",
            "metric": {"value": "40%", "unit": "%"},
            "supporting_physical_pages": [4, 9],
            "provenance": {
                "source_truth_notes_by_page": {
                    "4": "Fact A page four.",
                    "9": "Fact A page nine.",
                }
            },
        },
        "fact-b": {
            "fact_id": "fact-b",
            "source_identity": "source:test|pdf-sha256:" + "c" * 64,
            "statement": "Fact B is supported by a separate page.",
            "metric": {"value": "12", "unit": "users"},
            "supporting_physical_pages": [12],
            "provenance": {"source_truth_notes_by_page": {"12": "Fact B page twelve."}},
        },
    }

    index = artifact_evidence_span_index(
        doc_map={}, evidence_packs=canonical_verified_evidence_packs(facts)
    )

    assert [(span["page"], span["text"]) for span in index["verified-fact:fact-a"]] == [
        (4, "Fact A page four."),
        (9, "Fact A page nine."),
    ]
    assert [(span["page"], span["text"]) for span in index["verified-fact:fact-b"]] == [
        (12, "Fact B page twelve.")
    ]
