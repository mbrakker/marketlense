from __future__ import annotations

import json

import pytest

from scripts.quality.persist_verified_claims_step2_acceptance import (
    build_adversarial_acceptance_artifact,
    write_immutable_artifact,
)


def test_adversarial_acceptance_artifact_keeps_hashes_and_terminal_cases() -> None:
    corpus = {
        "cases": [
            {
                "case_id": "case-1",
                "candidate_id": "candidate-1",
                "expected_terminal": "verified_or_corrected",
            }
        ]
    }
    result = {
        "claims": [
            {
                "case_id": "case-1",
                "candidate_id": "candidate-1",
                "outcome": "verified",
                "source_identity": "source|pdf-sha256:" + "a" * 64,
                "physical_pages": [3],
                "original_physical_pages": [3],
                "inspected_physical_pages": [3],
                "supporting_physical_pages": [3],
                "evidence_ids": ["e1"],
                "final_claim": "A source-grounded claim.",
            }
        ]
    }
    comparator = {"passed": True, "case_count": 1, "mismatches": []}

    artifact = build_adversarial_acceptance_artifact(
        corpus=corpus,
        result=result,
        comparator=comparator,
        corpus_sha256="c" * 64,
        result_sha256="r" * 64,
        comparator_sha256="m" * 64,
        git_sha="g" * 40,
    )

    assert artifact["immutable"] is True
    assert artifact["acceptance"] == comparator
    assert artifact["corpus_sha256"] == "c" * 64
    assert artifact["cases"][0]["candidate_id"] == "candidate-1"
    assert artifact["cases"][0]["final_claim"] == "A source-grounded claim."


def test_immutable_artifact_refuses_overwrite(tmp_path) -> None:
    path = tmp_path / "acceptance.json"
    write_immutable_artifact(path, {"immutable": True})

    with pytest.raises(FileExistsError):
        write_immutable_artifact(path, {"immutable": True, "changed": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {"immutable": True}
