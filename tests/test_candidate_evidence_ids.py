from __future__ import annotations

import json

import pytest

from src.generators.artifact_generator import generate_artifacts
from src.generators.artifact_normalization import (
    artifact_candidate_allowed_evidence_ids,
    validate_artifact_candidate_evidence_ids,
)
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


def test_candidate_prompt_receives_all_eligible_factual_evidence_ids(tmp_path):
    candidates = [
        _insight(f"f{index}", score=1 - (index / 100)) for index in range(1, 9)
    ]
    evidence = _generation_evidence(10)
    prompt_client = CapturingPromptClient()

    generate_artifacts(
        report_id="candidate-evidence-vocabulary",
        report_name="Candidate evidence vocabulary",
        doc_map=_doc_map(10),
        evidence_packs=evidence,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(
            _generation_responses(
                candidates,
                plan_evidence_ids=[f"f{index}" for index in range(1, 7)],
            )
        ),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )

    variables = prompt_client.variables_for_namespace(
        "report_vs/artifacts/insights_candidates"
    )
    allowed_ids = json.loads(variables["candidate_allowed_evidence_ids_json"])

    assert set(allowed_ids) == {f"f{index}" for index in range(1, 11)} | {"q1"}
    assert not any(item.startswith("section-") for item in allowed_ids)
    assert not any(item.startswith("source:page:") for item in allowed_ids)


def test_candidate_docmap_reference_is_rejected_before_shortlisting(tmp_path):
    invalid = _insight("f1", score=0.99)
    invalid["evidence_id"] = "section-1"
    candidates = [invalid] + [
        _insight(f"f{index}", score=1 - (index / 100)) for index in range(2, 9)
    ]
    responses = _generation_responses(
        candidates,
        plan_evidence_ids=[f"f{index}" for index in range(1, 7)],
    )
    responses["insights_final"] = {
        "insights_final": [_insight("f2", score=0.98), _insight("f3", score=0.97)]
    }

    payload = generate_artifacts(
        report_id="candidate-docmap-reference",
        report_name="Candidate DocMap reference",
        doc_map=_doc_map(8),
        evidence_packs=_generation_evidence(8),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    candidate_ids = {
        item.get("evidence_id")
        for item in payload["insights_candidates"]
        if isinstance(item, dict)
    }
    assert "section-1" not in candidate_ids


def test_candidate_evidence_vocabulary_reuses_fidelity_and_source_eligibility():
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": "Supported finding",
                    "evidence": "Supported source excerpt",
                    "pages": [2],
                },
                {
                    "id": "f2",
                    "text": "Unsupported finding",
                    "evidence": "Unsupported source excerpt",
                    "pages": [3],
                },
            ]
        },
        "evidence_fidelity": {
            "results": [
                {
                    "candidate": {"claim_id": "evidence:findings:f1"},
                    "status": "supported",
                },
                {
                    "candidate": {"claim_id": "evidence:findings:f2"},
                    "status": "unsupported",
                },
            ]
        },
        "quote_candidates": {
            "quote_candidates": [
                {
                    "id": "q1",
                    "text": "A source-backed quote.",
                    "source": "Research team",
                    "page": 4,
                },
                {
                    "id": "q-unknown",
                    "text": "An unattributed quote.",
                    "source": "unknown",
                    "page": 5,
                },
                {
                    "id": "source:page:6",
                    "text": "A location label.",
                    "source": "Research team",
                    "page": 6,
                },
            ]
        },
        "doc_map": {"sections": [{"id": "section-1"}]},
    }

    assert artifact_candidate_allowed_evidence_ids(evidence_packs) == ["f1", "q1"]


def test_candidate_secondary_evidence_ids_must_use_the_same_allowed_vocabulary():
    with pytest.raises(AppError) as error:
        validate_artifact_candidate_evidence_ids(
            [
                {
                    "evidence_id": "f1",
                    "evidence_ids": ["f1", "f2", "section-1"],
                }
            ],
            ["f1", "f2"],
        )

    assert error.value.code == "artifact_candidate_evidence_reference_invalid"
    assert error.value.context["invalid_references"] == [
        {"index": 0, "evidence_id": "section-1"}
    ]
