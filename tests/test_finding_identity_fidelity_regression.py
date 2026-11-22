from types import SimpleNamespace

import pytest

from src.generators.artifact_normalization import (
    artifact_candidate_allowed_evidence_ids,
    artifact_evidence_span_index,
    fallback_artifact_insights_from_findings,
)
from src.generators.evidence_pack_generator import _attach_verified_finding_pages


def test_conflicting_duplicate_finding_ids_are_not_fallback_candidates():
    findings = {
        "findings": [
            {
                "id": "same",
                "text": "Sales rose 10%.",
                "evidence": "Sales +10%",
                "pages": [1],
            },
            {
                "id": "same",
                "text": "Sales fell 10%.",
                "evidence": "Sales -10%",
                "pages": [2],
            },
            {
                "id": "safe",
                "text": "Costs rose 5%.",
                "evidence": "Costs +5%",
                "pages": [3],
            },
        ]
    }
    assert [
        x["evidence_id"] for x in fallback_artifact_insights_from_findings(findings)
    ] == ["safe"]


@pytest.mark.parametrize(
    ("evidence", "pages"), [("Different quote", [1]), ("Sales +10%", [9])]
)
def test_same_text_with_conflicting_provenance_is_not_a_fallback(evidence, pages):
    first = {
        "id": "same",
        "text": "Sales rose 10%.",
        "evidence": "Sales +10%",
        "pages": [1],
    }
    second = {**first, "evidence": evidence, "pages": pages}
    assert fallback_artifact_insights_from_findings({"findings": [first, second]}) == []


def test_conflicting_duplicate_ids_do_not_receive_verified_pages():
    findings = [
        {"id": "same", "text": "Sales rose 10%."},
        {"id": "same", "text": "Sales fell 10%."},
    ]
    candidate = SimpleNamespace(
        claim_id="evidence:findings:same",
        text="Sales rose 10%.",
        evidence_references=[SimpleNamespace(page=1)],
    )
    fidelity = SimpleNamespace(
        results=[SimpleNamespace(candidate=candidate, status="supported")]
    )
    assert _attach_verified_finding_pages(findings, fidelity) == set()
    assert all("pages" not in item for item in findings)


def test_same_text_conflicting_evidence_does_not_receive_verified_pages():
    findings = [
        {
            "id": "same",
            "text": "Sales rose 10%.",
            "evidence": "Sales +10%",
            "pages": [1],
        },
        {
            "id": "same",
            "text": "Sales rose 10%.",
            "evidence": "Other quote",
            "pages": [2],
        },
    ]
    candidate = SimpleNamespace(
        claim_id="evidence:findings:same",
        text="Sales rose 10%.",
        evidence_references=[SimpleNamespace(page=3)],
    )
    fidelity = SimpleNamespace(
        results=[SimpleNamespace(candidate=candidate, status="supported")]
    )
    assert _attach_verified_finding_pages(findings, fidelity) == set()
    assert [item["pages"] for item in findings] == [[1], [2]]


def test_identical_duplicate_findings_receive_matching_verified_pages():
    findings = [
        {"id": "same", "text": "Sales rose 10%."},
        {"id": "same", "text": "Sales rose 10%."},
    ]
    candidate = SimpleNamespace(
        claim_id="evidence:findings:same",
        text="Sales rose 10%.",
        evidence_references=[SimpleNamespace(page=1)],
    )
    fidelity = SimpleNamespace(
        results=[SimpleNamespace(candidate=candidate, status="supported")]
    )
    assert _attach_verified_finding_pages(findings, fidelity) == {"same"}
    assert [item["pages"] for item in findings] == [[1], [1]]


def test_nested_fidelity_is_used_when_top_level_is_absent():
    statement = "Sales rose 10%."
    pack = {
        "family_status": {"status": "generated", "policy_action": "keep"},
        "findings": [
            {"id": "f1", "text": statement, "evidence": "Sales +10%", "pages": [1]}
        ],
        "evidence_fidelity": {
            "results": [
                {
                    "status": "supported",
                    "candidate": {
                        "claim_id": "evidence:findings:f1",
                        "text": statement,
                        "evidence_references": [
                            {"source_pack": "source_pdf", "page": 1}
                        ],
                    },
                }
            ]
        },
    }
    spans = artifact_evidence_span_index(doc_map={}, evidence_packs={"findings": pack})[
        "f1"
    ]
    assert any(
        span["source_pack"] == "findings_statement" and span["text"] == statement
        for span in spans
    )


def test_conflicting_duplicate_ids_do_not_share_source_spans():
    pack = {
        "findings": [
            {
                "id": "same",
                "text": "Sales rose 10%.",
                "evidence": "Sales +10%",
                "pages": [1],
            },
            {
                "id": "same",
                "text": "Sales fell 10%.",
                "evidence": "Sales -10%",
                "pages": [2],
            },
        ]
    }
    assert "same" not in artifact_evidence_span_index(
        doc_map={}, evidence_packs={"findings": pack}
    )


def test_explicit_empty_top_level_fidelity_does_not_use_nested_fidelity():
    statement = "Sales rose 10%."
    pack = {
        "family_status": {"status": "generated", "policy_action": "keep"},
        "findings": [
            {"id": "f1", "text": statement, "evidence": "Sales +10%", "pages": [1]}
        ],
        "evidence_fidelity": {
            "results": [
                {
                    "status": "supported",
                    "candidate": {
                        "claim_id": "evidence:findings:f1",
                        "text": statement,
                        "evidence_references": [
                            {"source_pack": "source_pdf", "page": 1}
                        ],
                    },
                }
            ]
        },
    }
    spans = artifact_evidence_span_index(
        doc_map={},
        evidence_packs={"findings": pack, "evidence_fidelity": {"results": []}},
    )["f1"]
    assert not any(span["source_pack"] == "findings_statement" for span in spans)


def test_verified_candidate_vocabulary_requires_recorded_fidelity():
    packs = {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": "Sales rose 10%.",
                    "evidence": "Sales +10%",
                    "pages": [1],
                }
            ]
        }
    }
    assert artifact_candidate_allowed_evidence_ids(packs, require_fidelity=True) == []
    assert artifact_candidate_allowed_evidence_ids(packs) == ["f1"]


def test_verified_candidate_vocabulary_keeps_fidelity_approved_finding():
    packs = {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": "Sales rose 10%.",
                    "evidence": "Sales +10%",
                    "pages": [1],
                }
            ]
        },
        "evidence_fidelity": {
            "results": [
                {
                    "status": "supported",
                    "candidate": {"claim_id": "evidence:findings:f1"},
                }
            ]
        },
    }
    assert artifact_candidate_allowed_evidence_ids(packs, require_fidelity=True) == [
        "f1"
    ]
