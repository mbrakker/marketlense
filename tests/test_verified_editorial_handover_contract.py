from __future__ import annotations

import hashlib

import pytest

from src.contracts.regeneration import RegenerationPlan, RegenerationTarget
from src.generators._artifact_generator.storage import (
    build_executive_advisory_artifacts,
)
from src.generators.public_editorial_quality_generator import (
    public_editorial_report_review_scope,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _scope_validation_report,
    _validate_original_essential_obligation_assessments,
)
from src.utils.errors import AppError


def test_public_review_scope_uses_the_rendered_limitations_projection() -> None:
    artifacts = {
        "verified_facts": [
            {
                "fact_id": "fact-1",
                "source_identity": "report|pdf-sha256:abc",
                "qualifiers": ["The sample excludes non-users."],
            }
        ],
        "insights_final": [
            {
                "id": "insight-1",
                "evidence_id": "verified-fact:fact-1",
            }
        ],
    }
    scope = public_editorial_report_review_scope(
        artifacts,
        [],
        evidence_packs={
            "verified_facts": {"verified_facts": artifacts["verified_facts"]}
        },
    )

    assert scope["rendered_limitations"] == [
        {
            "text": "The sample excludes non-users.",
            "evidence_ids": ["verified-fact:fact-1"],
        }
    ]


def test_public_review_scope_retains_final_insight_identity_and_bindings() -> None:
    artifacts = {
        "verified_facts": [
            {"fact_id": "fact-1", "source_identity": "report|pdf-sha256:abc"}
        ],
        "insights_final": [
            {
                "id": "insight-1",
                "text": "A source-backed finding.",
                "evidence_ids": ["verified-fact:fact-1"],
            }
        ],
    }
    items = [
        {
            "public_item_id": "insight:insight-1:text",
            "artifact": "insights_final",
            "field": "text",
            "evidence_ids": ["verified-fact:fact-1"],
        }
    ]

    scope = public_editorial_report_review_scope(artifacts, items)

    assert scope["final_insights"] == [
        {
            "insight_id": "insight-1",
            "public_item_ids": ["insight:insight-1:text"],
            "evidence_ids": ["verified-fact:fact-1"],
            "verified_fact_ids": ["fact-1"],
        }
    ]


def _obligation_review_scope() -> dict:
    return {
        "authority": "canonical_verified_facts",
        "original_editorial_plan_coverage": {
            "original_essential_obligations": [
                {"theme": "Essential signal", "evidence_ids": ["verified-fact:f1"]}
            ]
        },
    }


def _obligation_review_items() -> list[dict]:
    return [
        {
            "public_item_id": "insight:i1:text",
            "artifact": "insights_final",
            "field": "text",
            "evidence_ids": ["verified-fact:f1"],
        }
    ]


def test_public_review_obligation_diagnostics_identify_unknown_ids_and_evidence():
    payload = {
        "original_essential_obligation_assessments": [
            {
                "theme": "Essential signal",
                "status": "covered",
                "explanation": "The primary insight covers the source obligation.",
                "evidence_ids": ["verified-fact:f1"],
                "supporting_insight_ids": ["insight:unknown", "insight:unknown"],
            }
        ]
    }

    with pytest.raises(AppError) as exc_info:
        _validate_original_essential_obligation_assessments(
            payload=payload,
            items=_obligation_review_items(),
            report_scope=_obligation_review_scope(),
        )

    assert exc_info.value.context["invalid_insight_ids"] == ["insight:unknown"]
    assert exc_info.value.context["duplicate_insight_ids"] == ["insight:unknown"]


def test_public_review_obligation_diagnostics_identify_missing_evidence():
    payload = {
        "original_essential_obligation_assessments": [
            {
                "theme": "Essential signal",
                "status": "covered",
                "explanation": "The primary insight covers the source obligation.",
                "evidence_ids": ["verified-fact:f2"],
                "supporting_insight_ids": ["insight:i1"],
            }
        ]
    }

    with pytest.raises(AppError) as exc_info:
        _validate_original_essential_obligation_assessments(
            payload=payload,
            items=_obligation_review_items(),
            report_scope=_obligation_review_scope(),
        )

    assert exc_info.value.context["missing_evidence_ids"] == ["verified-fact:f1"]
    assert exc_info.value.context["unknown_evidence_ids"] == ["verified-fact:f2"]


def test_public_review_obligation_diagnostics_identify_omitted_obligations():
    scope = _obligation_review_scope()
    scope["original_editorial_plan_coverage"]["original_essential_obligations"].append(
        {"theme": "Second signal", "evidence_ids": ["verified-fact:f2"]}
    )
    payload = {
        "original_essential_obligation_assessments": [
            {
                "theme": "Essential signal",
                "status": "uncovered",
                "explanation": "The original obligation is not represented.",
                "evidence_ids": [],
                "supporting_insight_ids": [],
            }
        ]
    }

    with pytest.raises(AppError) as exc_info:
        _validate_original_essential_obligation_assessments(
            payload=payload,
            items=_obligation_review_items(),
            report_scope=scope,
        )

    assert exc_info.value.context["missing_obligation_ids"] == ["Second signal"]


def test_verified_strategic_context_requires_retained_sentence_binding() -> None:
    summary = {
        "tldr": "A retained source-backed planning signal.",
        "executive_summary": "A different executive summary.",
    }
    evidence_packs = {
        "verified_facts": {"verified_facts": [{"fact_id": "fact-1", "qualifiers": []}]}
    }
    common = {
        "summary": summary,
        "insights_final": [
            {"id": "i1", "text": "Signal", "evidence_id": "verified-fact:fact-1"}
        ],
        "quotes_final": [],
        "metric_spine": [],
        "evidence_packs": evidence_packs,
        "verified_facts": evidence_packs["verified_facts"]["verified_facts"],
    }

    unbound = build_executive_advisory_artifacts(**common)
    assert unbound["decision_brief"]["strategic_context"] == ""

    text_hash = hashlib.sha256(summary["tldr"].encode("utf-8")).hexdigest()
    bound = build_executive_advisory_artifacts(
        **common,
        soft_copy_claim_provenance={
            "schema_version": "1.0",
            "claims": [
                {
                    "schema_version": "1.0",
                    "artifact_family": "summary",
                    "claim_id": "summary:context",
                    "text_hash": text_hash,
                    "classification": "interpretive",
                    "evidence_ids": ["verified-fact:fact-1"],
                    "source_spans": [],
                    "producing_prompt_identity": {},
                    "generation_attempt": 1,
                    "regeneration_attempt": 0,
                }
            ],
        },
    )
    assert bound["decision_brief"]["strategic_context"] == summary["tldr"]
    assert bound["decision_brief"]["evidence_links_by_item"]["strategic_context"] == [
        {
            "text": summary["tldr"],
            "evidence_ids": ["verified-fact:fact-1"],
        }
    ]


def test_prompt_family_scope_allows_only_declared_family_root() -> None:
    plan = RegenerationPlan(
        mode="targeted",
        targets=[RegenerationTarget(target_section="summary")],
    )
    before = {"summary": {"tldr": "Old"}, "insights_final": [{"id": "i1"}]}
    after = {"summary": {"tldr": "New"}, "insights_final": [{"id": "i1"}]}

    passed = _scope_validation_report(
        before=before,
        after=after,
        plan=plan,
        declared_family_roots=frozenset({"summary"}),
    )
    failed = _scope_validation_report(
        before=before,
        after={"summary": {"tldr": "New"}, "insights_final": [{"id": "i2"}]},
        plan=plan,
        declared_family_roots=frozenset({"summary"}),
    )

    assert passed.status == "pass"
    assert failed.status == "fail"
