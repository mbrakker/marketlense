from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.contracts.regeneration import RegenerationIssue, RegenerationTarget
from src.contracts.run_context import RunContext
from src.generators.artifact_normalization import (
    artifact_evidence_span_index,
    page_bound_direct_evidence_packs,
)
from src.generators.report_regeneration_generator import (
    _build_grounding_package,
    _collect_required_relevant_evidence_entries,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _allowed_paths,
    _issue_grounding,
    _lookup_insight_grounding,
    _lookup_quote_grounding,
    _normalize_regeneration_issue,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _validate_public_editorial_review_payload,
    _verified_deterministic_mutation_paths,
)
from src.utils.errors import AppError


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

    assert verified == set(target.allowed_paths)


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
