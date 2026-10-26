from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from src.generators._artifact_generator.generation import generate_artifacts
from src.generators.verified_claims_canary import admit_visual_authority_candidates
from src.utils.verified_facts import validated_verified_facts
from tests._test_artifact_generator._shared import (
    CapturingPromptClient,
    FakeAnalysisStore,
    FakeOpenAI,
    _ctx,
    _settings,
)
from tests._test_artifact_generator.cases_05_docmap_insight_selection import (
    _doc_map,
    _generation_evidence,
    _generation_responses,
    _insight,
)
from tests.test_verified_claims_visual_authority_canary import (
    SOURCE_IDENTITY,
    _candidate,
    _evidence_packs,
    _metric,
    _response,
    _result,
    _verified_admission,
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


def test_retained_binding_accepts_source_consistent_authoritative_metric_enrichment():
    candidate = _candidate(
        text=(
            "Only around 31% of marketers report complete satisfaction with "
            "their ability to unify and read data across platforms."
        ),
        page=11,
        metric={
            "label": (
                "Marketers reporting complete satisfaction with cross-platform data"
            ),
            "value": "around 31%",
            "unit": "",
            "trend": "",
            "timeframe": "",
            "geography": "",
            "segment": "Marketers",
            "sample_size": "",
            "confidence": "",
            "subject": "marketers",
            "cohort": "",
            "denominator": "Marketers",
            "observation_status": "observed",
        },
    )
    authoritative_metric = {
        **deepcopy(candidate["metric"]),
        "label": (
            "Complete satisfaction with ability to unify and read data across platforms"
        ),
        "unit": "percent of marketers",
        "segment": "marketers",
        "cohort": "marketers",
        "denominator": "marketers; further denominator details are not stated",
        "observation_status": "reported satisfaction; collection method is not stated",
        "forecast_status": "not identified as a forecast",
    }
    result = _result(
        candidate,
        verified_fact={
            "statement": candidate["text"],
            "metric": authoritative_metric,
            "qualifiers": ["The source does not state a timeframe or geography."],
            "supporting_physical_pages": [11],
        },
        physical_page=11,
    )

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(result),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert [fact["fact_id"] for fact in admission.verified_facts] == [candidate["id"]]
    assert admission.verified_facts[0]["metric"] == authoritative_metric


@pytest.mark.parametrize(
    "field, value",
    [
        ("cohort", "app users"),
        ("forecast_status", "conditional_forecast"),
    ],
)
def test_retained_binding_rejects_authoritative_material_metric_changes(
    field: str, value: str
):
    candidate = _candidate(
        text="Only around 31% of marketers report complete satisfaction.",
        page=11,
        metric={
            "label": "Satisfaction",
            "value": "around 31%",
            "unit": "%",
            "segment": "marketers",
            "subject": "marketers",
            "cohort": "marketers" if field != "cohort" else "marketers",
            "denominator": "marketers",
            "observation_status": "observed",
            "forecast_status": "observed" if field == "forecast_status" else "",
        },
    )
    authoritative_metric = {
        **deepcopy(candidate["metric"]),
        field: value,
    }
    result = _result(
        candidate,
        verified_fact={
            "statement": candidate["text"],
            "metric": authoritative_metric,
            "qualifiers": [],
            "supporting_physical_pages": [11],
        },
        physical_page=11,
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


def test_retained_binding_rejects_authoritative_metric_conflict():
    candidate = _candidate()
    result = _result(
        candidate,
        verified_fact={
            "statement": candidate["text"],
            "metric": _metric("51%"),
            "qualifiers": [],
            "supporting_physical_pages": [4],
        },
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


def test_retained_binding_rejects_authoritative_page_conflict():
    candidate = _candidate()
    result = _result(
        candidate,
        physical_page=5,
        verified_fact={
            "statement": candidate["text"],
            "metric": deepcopy(candidate["metric"]),
            "qualifiers": [],
            "supporting_physical_pages": [5],
        },
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


def test_full_verified_roster_keeps_authority_without_prompt_fact_duplication(
    tmp_path,
):
    candidates = [
        _insight(
            f"f{index}",
            score=1 - (index / 100),
            text=f"Retained full-roster finding {index}.",
        )
        for index in range(1, 11)
    ]
    prompt_client = CapturingPromptClient()

    def admit(shortlisted):
        assert 1 <= len(shortlisted) <= 8
        return _verified_admission(shortlisted, digest="e" * 64)

    responses = _generation_responses(
        candidates,
        plan_evidence_ids=[f"f{index}" for index in range(1, 8)],
    )
    responses["insights_final"] = {
        "insights_final": [
            {
                **candidate,
                "evidence_id": f"verified-fact:{candidate['id']}",
                "evidence_spans": [],
            }
            for candidate in candidates[:2]
        ]
    }
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        f"verified-fact:{candidates[0]['id']}"
    )
    payload = generate_artifacts(
        report_id="visual-authority-full-roster",
        report_name="Visual Authority Full Roster",
        doc_map=_doc_map(10),
        evidence_packs=_generation_evidence(10),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=admit,
    )

    final_vars = prompt_client.variables_for_namespace(
        "report_vs/artifacts/insights_final"
    )
    prompt_candidates = json.loads(final_vars["insights_candidates_json"])
    prompt_evidence = json.loads(final_vars["evidence_json"])

    assert len(payload["verified_facts"]) <= 8
    assert len(prompt_candidates) <= 8
    assert all("verified_fact" not in item for item in prompt_candidates)
    assert {
        fact["fact_id"] for fact in prompt_evidence["verified_facts"]["verified_facts"]
    } == {item["id"] for item in prompt_candidates}
