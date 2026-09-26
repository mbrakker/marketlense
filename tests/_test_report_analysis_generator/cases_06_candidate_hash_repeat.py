# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json
from pathlib import Path

from src.contracts.regeneration import RepairDecision, RepairPatchOperation

from ._shared import *  # noqa: F401,F403


def test_rejected_candidate_hash_stops_an_equivalent_retry(tmp_path) -> None:
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(
            _runtime(tmp_path).settings,
            validation_regeneration_max_attempts=3,
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    original = _artifacts_without_retained_claims(
        summary={
            "tldr": "original artifact",
            "executive_summary": "Original summary",
            "claim_evidence_map": [],
        }
    )
    candidate = _artifacts_without_retained_claims(
        summary={
            "tldr": "same rejected candidate",
            "executive_summary": "Original summary",
            "claim_evidence_map": [],
        }
    )
    _set_interpretive_summary_provenance(original)
    _set_interpretive_summary_provenance(candidate)
    validation_calls = 0
    regeneration_strategies = []

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        nonlocal validation_calls
        del req, settings, ctx, pack_name, report_name, md5
        validation_calls += 1
        if validation_calls == 1:
            return ValidationReport(
                schema_version="1.1",
                status="fail",
                issues=[
                    ValidationIssue(
                        schema_version="1.0",
                        message="[grounding] Initial promoted failure",
                        severity="error",
                        affected_section="summary",
                        rule_id="grounding",
                        repair_target="summary",
                    )
                ],
                severity="error",
            )
        return ValidationReport(
            schema_version="1.1",
            status="fail",
            issues=[
                ValidationIssue(
                    schema_version="1.0",
                    message="[candidate_y] Candidate remains invalid",
                    severity="error",
                    affected_section="linkedin_post",
                    rule_id="candidate_y",
                    repair_target="linkedin_post",
                )
            ],
            severity="error",
        )

    def _regenerate(request):
        strategy = (
            "current_evidence" if request.attempt_index == 1 else "alternative_evidence"
        )
        evidence_id = "f1" if request.attempt_index == 1 else "f2"
        regeneration_strategies.append(strategy)
        decision = RepairDecision(
            diagnosed_failure_class="grounding",
            repair_action="REGENERATE_ITEM",
            repair_strategy=strategy,
            evidence_ids_used=[evidence_id],
            protected_fields=["summary.card_tldr_compact"],
            changed_paths=["summary.tldr"],
            minimal_patch=[
                RepairPatchOperation(
                    op="replace",
                    path="summary.tldr",
                    value="same rejected candidate",
                )
            ],
        )
        return ArtifactRegenerationResponse(
            updated_artifacts=candidate,
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            candidate_artifacts_path=str(
                tmp_path
                / "out"
                / f"artifacts_regen_candidate_{request.attempt_index}.json"
            ),
            repair_action="REGENERATE_ITEM",
            repair_strategy=strategy,
            selected_evidence_ids=[evidence_id],
            repair_decisions=[decision],
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title"}},
            "findings": {
                "findings": [
                    {"id": f"f{index}", "pages": [index]} for index in range(1, 6)
                ]
            },
            "quote_candidates": {"quote_candidates": [{"id": "q1", "page": 1}]},
        },
        generate_artifacts=lambda **kwargs: original,
        run_validation=_run_validation,
        regenerate_artifacts=_regenerate,
    )
    state = run_report_analysis(
        runtime,
        source,
        selection,
        VectorStoreIndexingState(
            vector_store_id="vs_1",
            openai_file_id="file_1",
            vector_store_status="completed",
            indexed_at_utc="2026-01-01T00:00:00Z",
            last_error=None,
        ),
        deps,
    )

    assert len(state.regeneration_attempts) == 2
    assert regeneration_strategies == ["current_evidence", "alternative_evidence"]
    first_audit = json.loads(
        Path(state.regeneration_attempts[0].candidate_audit_path).read_text(
            encoding="utf-8"
        )
    )
    second_audit = json.loads(
        Path(state.regeneration_attempts[1].candidate_audit_path).read_text(
            encoding="utf-8"
        )
    )
    assert first_audit["after_sha256"] == second_audit["after_sha256"]
    assert (
        first_audit["repair_delta"]["input_sha256"]
        == second_audit["repair_delta"]["input_sha256"]
    )
    assert any(
        item["rule_id"] == "regeneration_candidate_hash_repeat"
        for item in second_audit["repair_delta"]["introduced"]
    )
    assert (
        "regeneration_candidate_hash_repeat:regeneration_candidate"
        in (second_audit["validation_issues"])
    )
    assert state.regeneration_attempts[1].promotion_outcome == "rolled_back"
    assert state.artifacts_payload["summary"]["tldr"] == "original artifact"


__all__ = ["test_rejected_candidate_hash_stops_an_equivalent_retry"]
