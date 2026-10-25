from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from src.generators._artifact_generator.generation import generate_artifacts
from src.generators.verified_claims_canary import admit_visual_authority_candidates
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


def test_same_id_result_from_a_stale_candidate_snapshot_fails_closed():
    current = _candidate()
    stale = _candidate(
        current["id"],
        evidence_id="finding-2",
        page=7,
        text="A stale candidate proposition.",
        metric=_metric("51%", cohort="repeat buyers"),
    )
    admission = admit_visual_authority_candidates(
        candidates=[current],
        evaluation=_response(_result(stale)),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(current),
    )
    assert admission.admitted_candidates == []
    assert admission.audit["quarantined"] == [
        {
            "candidate_id": current["id"],
            "reason": "evaluation_candidate_snapshot_mismatch",
        }
    ]


def test_same_id_result_with_only_a_changed_evidence_span_fails_closed():
    current = _candidate()
    stale = deepcopy(current)
    stale["pages"] = [7]
    stale["evidence_spans"][0]["page"] = 7
    admission = admit_visual_authority_candidates(
        candidates=[current],
        evaluation=_response(_result(stale)),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(current),
    )
    assert admission.admitted_candidates == []
    assert admission.audit["quarantined"] == [
        {
            "candidate_id": current["id"],
            "reason": "evaluation_candidate_snapshot_mismatch",
        }
    ]


def test_mismatched_evaluation_roster_digest_fails_closed():
    candidate = _candidate()
    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=replace(
            _response(_result(candidate)),
            candidate_roster_digest="stale-roster",
        ),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )
    assert admission.admitted_candidates == []
    assert admission.audit["terminal_error"] == "evaluation_candidate_roster_mismatch"


def test_verified_visual_evaluation_sees_full_candidate_roster_before_editorial_limit(
    tmp_path,
):
    candidates = [_insight(f"f{i}", score=1.0 - i / 100) for i in range(1, 7)]
    evaluated_roster: list[str] = []

    def admit(shortlisted):
        evaluated_roster.extend(item["evidence_id"] for item in shortlisted)
        return _verified_admission(shortlisted, digest="e" * 64)

    responses = _generation_responses(
        candidates, plan_evidence_ids=[f"f{i}" for i in range(1, 6)]
    )
    responses["insights_final"] = {
        "insights_final": [
            {
                **deepcopy(candidate),
                "evidence_id": f"verified-fact:{candidate['id']}",
                "evidence_spans": [],
            }
            for candidate in candidates[:2]
        ]
    }
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        "verified-fact:insight-f1-0.99"
    )
    payload = generate_artifacts(
        report_id="visual-authority-roster-separation",
        report_name="Visual Authority Roster Separation",
        doc_map=_doc_map(6),
        evidence_packs=_generation_evidence(6),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=admit,
    )
    assert evaluated_roster == [f"f{i}" for i in range(1, 7)]
    assert len(payload["verified_facts"]) == 6
    assert [item["id"] for item in payload["insights_final"]] == [
        "insight-f1-0.99",
        "insight-f2-0.98",
    ]


def test_verified_final_selection_recovers_when_a_central_theme_is_omitted(
    tmp_path,
):
    candidates = [_insight("f1", score=0.99), _insight("f2", score=0.98)]

    def admit(shortlisted):
        return _verified_admission(shortlisted, digest="c" * 64)

    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
    responses["insights_final"] = [
        {
            "insights_final": [
                {
                    **deepcopy(candidates[1]),
                    "evidence_id": "verified-fact:insight-f2-0.98",
                    "evidence_spans": [],
                }
            ]
        },
        {
            "insights_final": [
                {
                    **deepcopy(candidate),
                    "evidence_id": f"verified-fact:{candidate['id']}",
                    "evidence_spans": [],
                }
                for candidate in candidates
            ]
        },
    ]
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        "verified-fact:insight-f1-0.99"
    )
    openai_client = FakeOpenAI(responses)

    payload = generate_artifacts(
        report_id="verified-central-theme-recovery",
        report_name="Verified central theme recovery",
        doc_map=_doc_map(2),
        evidence_packs=_generation_evidence(2),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=openai_client,
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=admit,
    )

    final_requests = [
        request for request in openai_client.requests if request[2] == "insights_final"
    ]
    assert len(final_requests) == 2
    assert {item["id"] for item in payload["insights_final"]} == {
        "insight-f1-0.99",
        "insight-f2-0.98",
    }
    assert (
        payload["_cache"]["candidate_generation"]["editorial_plan_coverage"][
            "final_selected_theme_coverage"
        ]["omitted_central_themes"]
        == []
    )


def test_verified_final_selection_may_omit_an_optional_theme(tmp_path):
    candidates = [
        _insight("f1", score=0.99),
        _insight("f2", score=0.98),
        _insight("f3", score=0.97),
    ]

    def admit(shortlisted):
        return _verified_admission(shortlisted, digest="o" * 64)

    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2", "f3"])
    responses["editorial_plan"] = {
        "editorial_plan": {
            "report_thesis": "The retained evidence defines the decision surface.",
            "themes": [
                {"theme": "Central", "priority": 1, "evidence_ids": ["f1"]},
                {"theme": "Optional", "priority": 2, "evidence_ids": ["f2"]},
                {"theme": "Supported", "priority": 3, "evidence_ids": ["f3"]},
            ],
        }
    }
    responses["insights_final"] = {
        "insights_final": [
            {
                **deepcopy(candidates[0]),
                "evidence_id": "verified-fact:insight-f1-0.99",
                "evidence_spans": [],
            },
            {
                **deepcopy(candidates[2]),
                "evidence_id": "verified-fact:insight-f3-0.97",
                "evidence_spans": [],
            },
        ]
    }
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        "verified-fact:insight-f1-0.99"
    )

    payload = generate_artifacts(
        report_id="verified-optional-theme-omission",
        report_name="Verified optional theme omission",
        doc_map=_doc_map(3),
        evidence_packs=_generation_evidence(3),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=admit,
    )

    assert [item["id"] for item in payload["insights_final"]] == [
        "insight-f1-0.99",
        "insight-f3-0.97",
    ]
    assert payload["_cache"]["candidate_generation"]["editorial_plan_coverage"][
        "final_selected_theme_coverage"
    ]["omitted_themes"] == ["Optional"]


def test_verified_generation_materializes_downstream_insights_from_snapshot(
    tmp_path,
):
    candidates = [_insight("f1", score=0.99), _insight("f2", score=0.98)]

    def admit(shortlisted):
        admission = _verified_admission(shortlisted, digest="s" * 64)
        admission.admitted_candidates[0]["text"] = "Stale projection wording."
        admission.admitted_candidates[0]["metric"] = {
            **admission.admitted_candidates[0]["metric"],
            "value": "999%",
        }
        return admission

    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
    responses["insights_final"] = {
        "insights_final": [
            {
                **deepcopy(candidate),
                "evidence_id": f"verified-fact:{candidate['id']}",
                "evidence_spans": [],
            }
            for candidate in candidates
        ]
    }
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        "verified-fact:insight-f1-0.99"
    )
    payload = generate_artifacts(
        report_id="visual-authority-snapshot-materialization",
        report_name="Visual Authority Snapshot Materialization",
        doc_map=_doc_map(2),
        evidence_packs=_generation_evidence(2),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=admit,
    )
    assert all(item["metric"]["value"] != "999%" for item in payload["insights_final"])
    assert all(item["metric"]["value"] == "10" for item in payload["insights_final"])
    assert payload["verified_facts"][0]["metric"]["value"] == "10"
