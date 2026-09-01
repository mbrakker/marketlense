from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from src.contracts.run_context import RunContext
from src.generators.artifact_normalization import normalize_artifact_evidence_ids
from src.generators.validation.metrics import validate_insight_metrics
from src.generators.validation.regeneration_candidate import (
    validate_regeneration_candidate,
)

_FIXTURE_ROOT = (
    Path(__file__).parent
    / "fixtures"
    / "docpacks"
    / "golden"
    / "the-akin-the-quarantine-cohort-exec-summary-pdf"
    / "report_analysis"
)


def _retained_artifact_and_evidence() -> tuple[dict, dict]:
    artifacts = json.loads((_FIXTURE_ROOT / "artifacts.json").read_text("utf-8"))
    evidence_packs = {
        path.stem: json.loads(path.read_text("utf-8"))
        for path in _FIXTURE_ROOT.glob("*.json")
        if path.stem not in {"artifacts", "validation", "analysis_vector_store"}
    }
    return artifacts, evidence_packs


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="run",
        task_id="task",
        span_id="span",
    )


def test_candidate_blocks_lost_and_hallucinated_evidence_ids() -> None:
    current, evidence_packs = _retained_artifact_and_evidence()
    lost = deepcopy(current)
    lost["insights_final"][0]["evidence_id"] = ""
    hallucinated = deepcopy(current)
    hallucinated["insights_final"][0]["evidence_id"] = "invented-evidence-id"

    lost_result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=lost,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )
    hallucinated_result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=hallucinated,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not lost_result.passed
    assert any(
        "missing_material_evidence" in issue.message for issue in lost_result.issues
    )
    assert not hallucinated_result.passed
    assert any(
        "hallucinated_evidence_id" in issue.message
        for issue in hallucinated_result.issues
    )


def test_candidate_allows_known_evidence_remapping_and_abstention() -> None:
    current, evidence_packs = _retained_artifact_and_evidence()
    remapped = deepcopy(current)
    remapped["quotes_final"][0]["evidence_id"] = "quote_3"
    normalize_artifact_evidence_ids(
        summary=remapped["summary"],
        insights_candidates=remapped["insights_candidates"],
        insights_final=remapped["insights_final"],
        quotes_final=remapped["quotes_final"],
        doc_map=evidence_packs["doc_map"],
        evidence_packs=evidence_packs,
    )
    abstained = deepcopy(current)
    abstained["quotes_final"] = []
    abstained["family_status"] = {
        "quotes": {
            "schema_version": "1.0",
            "family": "quotes",
            "source": "artifact",
            "status": "abstained",
            "confidence_score": 0.0,
            "policy_action": "abstain",
            "reason": "No directly attributable quote remains.",
        }
    }

    remapped_result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=remapped,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )
    abstained_result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=abstained,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert remapped["quotes_final"][0]["evidence_id"] == "qc_003"
    assert remapped_result.passed
    assert abstained_result.passed


def test_candidate_allows_a_unique_same_family_evidence_continuity_when_id_changes() -> (
    None
):
    current, evidence_packs = _retained_artifact_and_evidence()
    candidate = deepcopy(current)
    original = current["insights_candidates"][0]
    candidate["insights_candidates"][0]["id"] = "normalized-candidate-id"

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert result.passed
    assert not any(
        issue.entity_id == original["id"]
        and "lost the original material evidence" in issue.message
        for issue in result.issues
    )


def test_candidate_keeps_identifier_continuity_blocked_when_evidence_match_is_ambiguous() -> (
    None
):
    current, evidence_packs = _retained_artifact_and_evidence()
    candidate = deepcopy(current)
    original = current["insights_candidates"][0]
    candidate["insights_candidates"][0]["id"] = "normalized-candidate-id-1"
    duplicate = deepcopy(candidate["insights_candidates"][0])
    duplicate["id"] = "normalized-candidate-id-2"
    candidate["insights_candidates"].append(duplicate)

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any(
        issue.entity_id == original["id"]
        and "lost the original material evidence" in issue.message
        for issue in result.issues
    )


def test_candidate_keeps_identifier_continuity_blocked_without_source_pages() -> None:
    current, evidence_packs = _retained_artifact_and_evidence()
    candidate = deepcopy(current)
    original = current["insights_candidates"][0]
    original["pages"] = []
    original["evidence_spans"] = []
    candidate["insights_candidates"][0]["id"] = "normalized-candidate-id"
    candidate["insights_candidates"][0]["pages"] = []
    candidate["insights_candidates"][0]["evidence_spans"] = []

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any(
        issue.entity_id == original["id"]
        and "lost the original material evidence" in issue.message
        for issue in result.issues
    )


def test_candidate_blocks_unsupported_more_than_doubled_language() -> None:
    artifacts, _ = _retained_artifact_and_evidence()
    insight = deepcopy(artifacts["insights_final"][0])
    insight["text"] = "The reported spending power more than doubled."

    issues = validate_insight_metrics(
        insights=[insight],
        evidence_map={insight["evidence_id"]: insight["evidence"]},
    )

    assert any(
        issue.severity == "error" and "more than doubled" in issue.message
        for issue in issues
    )
