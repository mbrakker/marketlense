from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from src.generators.verified_claims_canary import admit_visual_authority_candidates
from src.utils.verified_facts import validated_verified_facts
from tests.test_verified_claims_visual_authority_canary import (
    SOURCE_IDENTITY,
    _candidate,
    _evidence_packs,
    _metric,
    _response,
    _result,
)


def test_material_correction_cannot_retain_stale_binding_status():
    candidate = _candidate()
    result = _result(
        candidate,
        final_claim="A source-supported replacement conclusion.",
        corrected_status="retained",
        verified_fact={
            "statement": "A source-supported replacement conclusion.",
            "metric": _metric("51%", cohort="repeat buyers"),
            "qualifiers": ["Observed among repeat buyers."],
            "supporting_physical_pages": [7],
        },
        physical_page=7,
    )

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(result),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert admission.verified_facts == []
    assert admission.audit["quarantined"][0]["reason"] == (
        "verified_fact_corrected_binding_conflict"
    )


def test_material_correction_cannot_carry_partial_unbound_discovery_binding():
    candidate = _candidate()
    result = _result(
        candidate,
        final_claim="A source-supported replacement conclusion.",
        corrected_status="unbound",
        verified_fact={
            "statement": "A source-supported replacement conclusion.",
            "metric": _metric("51%", cohort="repeat buyers"),
            "qualifiers": ["Observed among repeat buyers."],
            "supporting_physical_pages": [7],
        },
        physical_page=7,
    )
    result = replace(
        result,
        corrected_evidence_ids=[candidate["evidence_id"]],
        corrected_evidence_spans=deepcopy(candidate["evidence_spans"]),
        corrected_metric_binding=deepcopy(candidate["metric"]),
    )

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(result),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert admission.verified_facts == []
    assert admission.audit["quarantined"][0]["reason"] == (
        "verified_fact_corrected_binding_conflict"
    )


def test_empty_metric_fields_are_equivalent_across_candidate_snapshot_shapes():
    candidate = _candidate()
    result = _result(candidate)
    result = replace(
        result,
        original_metric_binding={
            **deepcopy(candidate["metric"]),
            "forecast_status": "",
            "observations": "",
        },
    )

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(result),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert [fact["fact_id"] for fact in admission.verified_facts] == [candidate["id"]]


def test_multi_page_verified_fact_pack_matches_canonical_snapshot_order():
    candidate = _candidate()
    result = _result(
        candidate,
        verified_fact={
            "statement": candidate["text"],
            "metric": deepcopy(candidate["metric"]),
            "qualifiers": [],
            "supporting_physical_pages": [4, 2],
        },
    )
    result = replace(
        result,
        physical_pages=[4, 2],
        inspected_physical_pages=[4, 2],
        supporting_physical_pages=[4, 2],
        source_truth_notes_by_page={
            "4": "The source supports the fact.",
            "2": "The source supports the same fact.",
        },
    )

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(result),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    validated = validated_verified_facts(
        {"verified_facts": admission.verified_facts},
        admission.verified_evidence_packs,
    )
    assert validated[candidate["id"]]["supporting_physical_pages"] == [2, 4]
