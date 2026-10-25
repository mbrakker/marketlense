from __future__ import annotations

import pytest

from src.generators.artifact_normalization import (
    fallback_artifact_insights_from_findings,
    remap_editorial_plan_to_verified_facts,
    select_artifact_insights,
)
from src.utils.errors import AppError


def _plan(*evidence_ids: str) -> dict[str, object]:
    return {
        "report_thesis": "The retained evidence defines the decision surface.",
        "themes": [
            {
                "theme": f"Theme {index}",
                "priority": index,
                "evidence_ids": [evidence_id],
            }
            for index, evidence_id in enumerate(evidence_ids, start=1)
        ],
    }


def _finding(
    finding_id: str,
    section_id: str,
    *,
    confidence: str = "high",
    score: float = 0.9,
) -> dict[str, object]:
    return {
        "id": finding_id,
        "text": f"Finding {finding_id} has a supported implication.",
        "evidence": f"Source evidence for {finding_id}.",
        "confidence": confidence,
        "score": score,
        "pages": [4],
        "section_id": section_id,
    }


def _fidelity(*finding_ids: str) -> dict[str, object]:
    return {
        "results": [
            {
                "status": "supported",
                "candidate": {"claim_id": f"evidence:findings:{finding_id}"},
            }
            for finding_id in finding_ids
        ]
    }


def test_finding_fallback_resolves_editorial_plan_section_refs_and_preserves_direct_ids(
) -> None:
    findings = {
        "findings": [
            _finding("ai-finding", "ai-infrastructure", score=0.8),
            _finding("cross-finding", "multiplatform-strategy", score=0.7),
            _finding("unsupported", "ignored", score=1.0),
        ]
    }
    selected = fallback_artifact_insights_from_findings(
        findings,
        limit=2,
        editorial_plan=_plan("ai-infrastructure", "cross-finding"),
        evidence_fidelity=_fidelity("ai-finding", "cross-finding"),
    )

    assert [item["evidence_id"] for item in selected] == [
        "ai-finding",
        "cross-finding",
    ]
    assert "unsupported" not in {item["evidence_id"] for item in selected}


def test_finding_fallback_does_not_let_one_section_monopolize_capacity():
    findings = {
        "findings": [
            _finding("a-1", "section-a", score=0.99),
            _finding("a-2", "section-a", score=0.98),
            _finding("a-3", "section-a", score=0.97),
            _finding("b-1", "section-b", score=0.7),
            _finding("c-1", "section-c", score=0.6),
        ]
    }
    selected = fallback_artifact_insights_from_findings(findings, limit=4)

    selected_ids = [item["evidence_id"] for item in selected]
    assert selected_ids[0] == "a-1"
    assert {"b-1", "c-1"}.issubset(selected_ids)
    assert len(selected_ids) == 4


def test_verified_plan_maps_section_refs_only_through_original_findings():
    facts = [
        {
            "fact_id": "ai-fact",
            "provenance": {"discovery_candidate_id": "ai-finding"},
        },
        {
            "fact_id": "cross-fact",
            "provenance": {
                "discovery_evidence_ids": ["evidence:findings:cross-finding"]
            },
        },
    ]
    source_findings = {
        "findings": [
            _finding("ai-finding", "ai-infrastructure"),
            _finding("cross-finding", "multiplatform-strategy"),
        ]
    }

    remapped = remap_editorial_plan_to_verified_facts(
        _plan("ai-infrastructure", "cross-finding"),
        facts,
        source_findings=source_findings,
    )

    assert [theme["evidence_ids"] for theme in remapped["themes"]] == [
        ["verified-fact:ai-fact"],
        ["verified-fact:cross-fact"],
    ]


def test_verified_plan_keeps_multiple_admitted_facts_from_one_source_section():
    facts = [
        {
            "fact_id": "fact-a",
            "provenance": {"discovery_candidate_id": "finding-a"},
        },
        {
            "fact_id": "fact-b",
            "provenance": {"discovery_candidate_id": "finding-b"},
        },
        {
            "fact_id": "fact-c",
            "provenance": {"discovery_candidate_id": "finding-c"},
        },
    ]
    source_findings = {
        "findings": [
            _finding("finding-a", "shared-section"),
            _finding("finding-b", "shared-section"),
            _finding("finding-c", "other-section"),
        ]
    }

    remapped = remap_editorial_plan_to_verified_facts(
        _plan("shared-section", "finding-c"),
        facts,
        source_findings=source_findings,
    )

    assert remapped["themes"][0]["evidence_ids"] == [
        "verified-fact:fact-a",
        "verified-fact:fact-b",
    ]
    assert remapped["themes"][1]["evidence_ids"] == ["verified-fact:fact-c"]


def test_verified_plan_drops_section_refs_without_admitted_finding_bindings():
    facts = [
        {
            "fact_id": "fact-a",
            "provenance": {"discovery_candidate_id": "finding-a"},
        },
        {
            "fact_id": "fact-b",
            "provenance": {"discovery_candidate_id": "finding-b"},
        },
    ]
    source_findings = {
        "findings": [
            _finding("finding-a", "supported-section"),
            _finding("finding-b", "other-section"),
        ]
    }

    with pytest.raises(AppError, match="Verified-fact editorial coverage"):
        remap_editorial_plan_to_verified_facts(
            _plan("missing-section", "unsupported-section"),
            facts,
            source_findings=source_findings,
        )


def test_verified_selection_can_retain_all_admitted_facts_as_final_model_alternatives():
    candidates = [
        {
            "id": f"fact-{index}",
            "text": f"Supported proposition {index}.",
            "evidence_id": f"finding-{index}",
            "evidence": f"Source evidence {index}.",
            "pages": [index + 1],
            "metric": {},
        }
        for index in range(6)
    ]

    selected = select_artifact_insights(
        final_insights=candidates,
        candidate_insights=[],
        editorial_plan=_plan("finding-0", "finding-1"),
        preserve_all=True,
        verified_mode=True,
    )

    assert [item["id"] for item in selected] == [item["id"] for item in candidates]
