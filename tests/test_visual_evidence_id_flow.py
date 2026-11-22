from __future__ import annotations

from copy import deepcopy

from src.generators.verified_claims_canary import admit_visual_authority_candidates
from src.generators.verified_claims_visual_generator import evaluate_shortlisted_claims
from tests._test_verified_claims_visual_generator.cases_01_visual import (
    _ctx,
    _dependencies,
    _request,
    _settings,
)
from tests.test_verified_claims_visual_authority_canary import (
    _candidate,
    _evidence_packs,
)


def _evaluate_and_admit(tmp_path, candidate):
    request = _request(tmp_path, [candidate])
    responses = iter(
        [
            {"claim": candidate["text"], "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The source page confirms the reported research trend "
                    "and buyer cohort."
                ),
                "verified_fact": {
                    "statement": candidate["text"],
                    "metric": deepcopy(candidate["metric"]),
                    "qualifiers": [],
                },
            },
        ]
    )
    evaluation = evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )
    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=evaluation,
        source_identity=request.source_identity,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )
    return evaluation.claims[0], admission


def test_primary_evidence_order_and_spans_survive_evaluation_and_admission(tmp_path):
    candidate = _candidate(page=5)
    candidate["evidence_ids"] = ["finding-2", "finding-1", "finding-2"]
    candidate["evidence_spans"].append(
        {
            "evidence_id": "finding-2",
            "source_pack": "findings",
            "page": 5,
            "text": "Additional supporting evidence.",
        }
    )

    result, admission = _evaluate_and_admit(tmp_path, candidate)

    assert result.evidence_ids == ["finding-1", "finding-2"]
    assert result.corrected_evidence_ids == ["finding-1", "finding-2"]
    assert result.evidence_spans == candidate["evidence_spans"]
    assert result.corrected_evidence_spans == candidate["evidence_spans"]
    assert [fact["fact_id"] for fact in admission.verified_facts] == ["candidate-1"]
    assert admission.verified_facts[0]["provenance"]["discovery_evidence_ids"] == [
        "finding-1",
        "finding-2",
    ]


def test_span_only_evidence_id_is_rejected_through_evaluation_and_admission(tmp_path):
    candidate = _candidate(page=5)
    candidate["evidence_spans"].append(
        {
            "evidence_id": "unauthorized",
            "source_pack": "findings",
            "page": 5,
            "text": "Unrelated evidence.",
        }
    )

    result, admission = _evaluate_and_admit(tmp_path, candidate)

    assert result.evidence_ids == ["finding-1"]
    assert result.evidence_spans == candidate["evidence_spans"]
    assert result.outcome == "skipped"
    assert result.failure_reason == "source_binding_conflict"
    assert not admission.verified_facts
    assert not admission.admitted_candidates
