from __future__ import annotations

import hashlib

from src.contracts.regeneration import RegenerationPlan, RegenerationTarget
from src.generators._artifact_generator.storage import (
    build_executive_advisory_artifacts,
)
from src.generators.public_editorial_quality_generator import (
    public_editorial_report_review_scope,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _scope_validation_report,
)


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


def test_verified_strategic_context_requires_retained_sentence_binding() -> None:
    summary = {
        "tldr": "A retained source-backed planning signal.",
        "executive_summary": "A different executive summary.",
    }
    evidence_packs = {
        "verified_facts": {
            "verified_facts": [{"fact_id": "fact-1", "qualifiers": []}]
        }
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

    text_hash = hashlib.sha256(
        summary["tldr"].encode("utf-8")
    ).hexdigest()
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
