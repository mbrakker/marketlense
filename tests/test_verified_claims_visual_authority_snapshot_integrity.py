from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from src.generators._artifact_generator.generation import generate_artifacts
from src.generators.verified_claims_canary import admit_visual_authority_candidates
from src.utils.errors import AppError
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


def _theme_coverage_response(
    candidates: list[dict[str, object]],
    plan_evidence_ids: list[str],
    *,
    covered_evidence_ids: set[str],
    theme_names: list[str] | None = None,
) -> dict[str, object]:
    candidate_ids = {
        str(candidate.get("evidence_id")): str(candidate.get("id"))
        for candidate in candidates
        if candidate.get("evidence_id") and candidate.get("id")
    }
    names = theme_names or [
        f"Theme {index}" for index in range(1, len(plan_evidence_ids) + 1)
    ]
    return {
        "theme_coverage": [
            {
                "theme": names[index - 1],
                "status": (
                    "covered" if evidence_id in covered_evidence_ids else "uncovered"
                ),
                "supporting_insight_ids": (
                    [candidate_ids[evidence_id]]
                    if evidence_id in covered_evidence_ids
                    and evidence_id in candidate_ids
                    else []
                ),
                "explanation": (
                    f"Final prose develops the supported {evidence_id} theme."
                    if evidence_id in covered_evidence_ids
                    else (
                        "The final roster does not develop the supported "
                        f"{evidence_id} theme."
                    )
                ),
            }
            for index, evidence_id in enumerate(plan_evidence_ids, start=1)
        ]
    }


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
    responses["editorial_theme_coverage"] = _theme_coverage_response(
        candidates,
        [f"f{i}" for i in range(1, 6)],
        covered_evidence_ids={"f1", "f2"},
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
    responses["editorial_theme_coverage"] = _theme_coverage_response(
        candidates,
        ["f1", "f2"],
        covered_evidence_ids={"f1", "f2"},
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
    assert len(final_requests) == 1
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


def test_verified_generation_fills_omitted_theme_from_admitted_candidate(tmp_path):
    candidates = [
        _insight("f1", score=0.99, text="The first decision signal is material."),
        _insight("f2", score=0.98, text="The second decision signal is material."),
    ]
    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
    responses["insights_final"] = {
        "insights_final": [
            {
                **candidates[1],
                "evidence_id": f"verified-fact:{candidates[1]['id']}",
            }
        ]
    }
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        f"verified-fact:{candidates[1]['id']}"
    )
    responses["editorial_theme_coverage"] = _theme_coverage_response(
        candidates,
        ["f1", "f2"],
        covered_evidence_ids={"f1", "f2"},
    )

    payload = generate_artifacts(
        report_id="verified-omitted-theme",
        report_name="Verified omitted theme",
        doc_map=_doc_map(2),
        evidence_packs=_generation_evidence(2),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=lambda shortlisted: _verified_admission(
            shortlisted, digest="f" * 64
        ),
    )

    assert {item["evidence_id"] for item in payload["insights_final"]} == {
        f"verified-fact:{candidate['id']}" for candidate in candidates
    }


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
    responses["editorial_theme_coverage"] = _theme_coverage_response(
        candidates,
        ["f1", "f2", "f3"],
        covered_evidence_ids={"f1", "f3"},
        theme_names=["Central", "Optional", "Supported"],
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


def test_verified_generation_semantically_assesses_shared_theme_evidence(tmp_path):
    candidates = [
        _insight("f1", score=0.99, text="The first decision signal is material."),
        _insight("f2", score=0.98, text="The second decision signal is material."),
    ]
    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f1"])
    responses["insights_final"] = {
        "insights_final": [
            {**candidate, "evidence_id": f"verified-fact:{candidate['id']}"}
            for candidate in candidates
        ]
    }
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        f"verified-fact:{candidates[0]['id']}"
    )
    responses["editorial_theme_coverage"] = {
        "theme_coverage": [
            {
                "theme": "Theme 1",
                "status": "covered",
                "supporting_insight_ids": [candidates[0]["id"]],
                "explanation": (
                    "The first final proposition develops the first decision theme."
                ),
            },
            {
                "theme": "Theme 2",
                "status": "covered",
                "supporting_insight_ids": [candidates[1]["id"]],
                "explanation": (
                    "The second final proposition develops the second decision theme."
                ),
            },
        ]
    }
    prompt_client = CapturingPromptClient()

    def admit(shortlisted):
        return _verified_admission(shortlisted, digest="e" * 64)

    openai_client = FakeOpenAI(responses)
    payload = generate_artifacts(
        report_id="verified-shared-theme-coverage",
        report_name="Verified shared theme coverage",
        doc_map=_doc_map(2),
        evidence_packs=_generation_evidence(2),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=openai_client,
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=admit,
    )

    assert any(
        step == "editorial_theme_coverage"
        for _kind, _request, step in openai_client.requests
    )
    coverage = payload["_cache"]["candidate_generation"]["editorial_plan_coverage"][
        "final_selected_theme_coverage"
    ]["semantic_assessment"]
    assert coverage["assessment_source"] == "independent_semantic_coverage"
    assert [item["status"] for item in coverage["theme_assessments"]] == [
        "covered",
        "covered",
    ]
    assert prompt_client.variables_for_namespace(
        "report_vs/artifacts/editorial_theme_coverage"
    )


def test_verified_generation_semantically_assesses_unique_theme_evidence(tmp_path):
    candidates = [
        _insight("f1", score=0.99, text="The first decision signal is material."),
        _insight("f2", score=0.98, text="The second decision signal is material."),
    ]
    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
    responses["insights_final"] = {
        "insights_final": [
            {**candidate, "evidence_id": f"verified-fact:{candidate['id']}"}
            for candidate in candidates
        ]
    }
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        f"verified-fact:{candidates[1]['id']}"
    )
    responses["editorial_theme_coverage"] = {
        "theme_coverage": [
            {
                "theme": "Theme 1",
                "status": "covered",
                "supporting_insight_ids": [candidates[0]["id"]],
                "explanation": "The first final proposition develops Theme 1.",
            },
            {
                "theme": "Theme 2",
                "status": "covered",
                "supporting_insight_ids": [candidates[1]["id"]],
                "explanation": "The second final proposition develops Theme 2.",
            },
        ]
    }
    openai_client = FakeOpenAI(responses)

    payload = generate_artifacts(
        report_id="verified-unique-theme-coverage",
        report_name="Verified unique theme coverage",
        doc_map=_doc_map(2),
        evidence_packs=_generation_evidence(2),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=openai_client,
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=lambda shortlisted: _verified_admission(
            shortlisted, digest="u" * 64
        ),
    )

    assert any(
        step == "editorial_theme_coverage"
        for _kind, _request, step in openai_client.requests
    )
    coverage = payload["_cache"]["candidate_generation"]["editorial_plan_coverage"][
        "final_selected_theme_coverage"
    ]["semantic_assessment"]
    assert [item["status"] for item in coverage["theme_assessments"]] == [
        "covered",
        "covered",
    ]


def test_verified_generation_repairs_a_semantically_incomplete_central_theme(
    tmp_path,
):
    candidates = [
        _insight("f1", score=0.99, text="The first decision signal is material."),
        _insight("f2", score=0.98, text="The second decision signal is material."),
    ]
    bad_final = [
        {
            **deepcopy(candidates[0]),
            "evidence_id": f"verified-fact:{candidates[0]['id']}",
        },
        {
            **deepcopy(candidates[1]),
            "evidence_id": f"verified-fact:{candidates[1]['id']}",
            "text": "The first decision signal also governs the response.",
        },
    ]
    repaired_final = [
        {
            **deepcopy(candidates[0]),
            "evidence_id": f"verified-fact:{candidates[0]['id']}",
        },
        {
            **deepcopy(candidates[1]),
            "evidence_id": f"verified-fact:{candidates[1]['id']}",
            "text": "The second decision signal governs the response.",
        },
    ]
    responses = _generation_responses(candidates, plan_evidence_ids=["f2", "f1"])
    responses["insights_final"] = [
        {"insights_final": bad_final},
        {"insights_final": repaired_final},
    ]
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        f"verified-fact:{candidates[1]['id']}"
    )
    responses["editorial_theme_coverage"] = [
        {
            "theme_coverage": [
                {
                    "theme": "Theme 1",
                    "status": "uncovered",
                    "supporting_insight_ids": [],
                    "explanation": (
                        "The central theme is not developed by the final prose."
                    ),
                },
                {
                    "theme": "Theme 2",
                    "status": "covered",
                    "supporting_insight_ids": [candidates[0]["id"]],
                    "explanation": "The first final proposition develops Theme 2.",
                },
            ]
        },
        {
            "theme_coverage": [
                {
                    "theme": "Theme 1",
                    "status": "covered",
                    "supporting_insight_ids": [candidates[1]["id"]],
                    "explanation": "The repaired second proposition develops Theme 1.",
                },
                {
                    "theme": "Theme 2",
                    "status": "covered",
                    "supporting_insight_ids": [candidates[0]["id"]],
                    "explanation": "The first proposition develops Theme 2.",
                },
            ]
        },
    ]
    openai_client = FakeOpenAI(responses)

    payload = generate_artifacts(
        report_id="verified-semantic-theme-repair",
        report_name="Verified semantic theme repair",
        doc_map=_doc_map(2),
        evidence_packs=_generation_evidence(2),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=openai_client,
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=lambda shortlisted: _verified_admission(
            shortlisted, digest="r" * 64
        ),
    )

    final_requests = [
        request for request in openai_client.requests if request[2] == "insights_final"
    ]
    assert len(final_requests) == 2
    assert (
        next(
            item["text"]
            for item in payload["insights_final"]
            if item["id"] == candidates[1]["id"]
        )
        == "The second decision signal governs the response."
    )


def test_verified_generation_fails_closed_after_semantic_theme_repair_exhaustion(
    tmp_path,
):
    candidates = [
        _insight("f1", score=0.99, text="The first decision signal is material."),
        _insight("f2", score=0.98, text="The second decision signal is material."),
    ]
    final_insights = [
        {
            **deepcopy(candidate),
            "evidence_id": f"verified-fact:{candidate['id']}",
        }
        for candidate in candidates
    ]
    responses = _generation_responses(candidates, plan_evidence_ids=["f2", "f1"])
    responses["insights_final"] = [
        {"insights_final": final_insights},
        {"insights_final": final_insights},
    ]
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        f"verified-fact:{candidates[1]['id']}"
    )
    failed_coverage = {
        "theme_coverage": [
            {
                "theme": "Theme 1",
                "status": "uncovered",
                "supporting_insight_ids": [],
                "explanation": "The central theme remains absent after repair.",
            },
            {
                "theme": "Theme 2",
                "status": "covered",
                "supporting_insight_ids": [candidates[0]["id"]],
                "explanation": "The second theme remains supported.",
            },
        ]
    }
    responses["editorial_theme_coverage"] = [failed_coverage, failed_coverage]
    openai_client = FakeOpenAI(responses)

    with pytest.raises(AppError, match="omitted a supported central theme"):
        generate_artifacts(
            report_id="verified-semantic-theme-repair-exhausted",
            report_name="Verified semantic theme repair exhausted",
            doc_map=_doc_map(2),
            evidence_packs=_generation_evidence(2),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=openai_client,
            prompt_client=CapturingPromptClient(),
            analysis_store=FakeAnalysisStore(),
            visual_authority_admitter=lambda shortlisted: _verified_admission(
                shortlisted, digest="x" * 64
            ),
        )

    assert (
        len(
            [
                request
                for request in openai_client.requests
                if request[2] == "insights_final"
            ]
        )
        == 2
    )


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
    responses["editorial_theme_coverage"] = _theme_coverage_response(
        candidates,
        ["f1", "f2"],
        covered_evidence_ids={"f1", "f2"},
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
