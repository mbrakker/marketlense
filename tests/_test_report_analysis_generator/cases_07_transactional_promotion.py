# ruff: noqa: F401,F403,F405
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from src.contracts.files import ReadJsonRequest
from src.contracts.regeneration import RepairDecision, RepairPatchOperation
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.generators.claim_validation_generator import claim_validation_package_hash
from src.generators.validation.regeneration_candidate import CandidateIntegrityResult
from src.orchestrators._report_analysis_orchestrator.validation import (
    _candidate_audit,
    _load_promoted_claim_validation_for_reuse,
    _run_validation_regeneration_loop,
)
from src.services import file_service, report_analysis_store_service
from src.utils.cache_utils import sha256_json

from ._shared import *  # noqa: F401,F403


@pytest.mark.parametrize(
    "failure_stage",
    [
        "candidate_audit",
        "canonical_artifacts",
        "promoted_claim_validation",
        "canonical_validation",
    ],
)
def test_promotion_persistence_failures_do_not_authorize_partial_state(
    tmp_path, failure_stage: str
) -> None:
    """A write that fails after replacing a file must still fail closed."""

    runtime = _runtime(tmp_path)
    original = _artifacts_without_retained_claims(
        summary={
            "tldr": "Original summary",
            "card_tldr_compact": "Original card",
            "executive_summary": "Original executive summary",
            "claim_evidence_map": [],
        }
    )
    candidate = deepcopy(original)
    candidate["summary"]["tldr"] = "Repaired summary"
    _set_interpretive_summary_provenance(original)
    _set_interpretive_summary_provenance(candidate)
    issue = ValidationIssue(
        schema_version="1.0",
        message="The retained summary claim is not grounded.",
        severity="error",
        affected_section="summary.tldr",
        rule_id="grounding",
        repair_target="summary",
    )
    candidate_package = {
        "schema_version": "1.4",
        "artifact_hash": sha256_json(candidate),
        "package_hash": "candidate-package",
        "results": [],
    }
    stored: dict[str, dict] = {}
    writes: list[str] = []
    injected = False

    def _analysis_pack_path(request, _ctx):
        return SimpleNamespace(
            output_path=str(tmp_path / "packs" / f"{request.pack_name}.json")
        )

    def _read_json(request, _ctx):
        if "validation_regen_candidate_1_retained_claim_validation_candidate" in (
            request.path
        ):
            return SimpleNamespace(payload=candidate_package)
        canonical = stored.get("validation_retained_claim_validation_candidate")
        if (
            canonical is not None
            and "validation_retained_claim_validation_candidate" in (request.path)
        ):
            return SimpleNamespace(payload=canonical)
        raise AppError(
            code="file_not_found",
            message="No prior promoted claim package is retained in this test.",
        )

    def _analysis_store_pack(request, _ctx):
        nonlocal injected
        writes.append(request.pack_name)
        stored[request.pack_name] = request.payload
        should_fail = not injected and (
            failure_stage == "candidate_audit"
            and request.pack_name == "regeneration_candidate_audit_1"
            or failure_stage == "canonical_artifacts"
            and request.pack_name == "artifacts"
            and request.payload == candidate
            or failure_stage == "promoted_claim_validation"
            and request.pack_name == "validation_retained_claim_validation_candidate"
            or failure_stage == "canonical_validation"
            and request.pack_name == "validation"
            and request.payload.get("status") == "pass"
        )
        if should_fail:
            injected = True
            raise AppError(
                code=f"injected_{failure_stage}",
                message="Injected post-write persistence failure.",
                retryable=False,
            )
        return SimpleNamespace(output_path=str(tmp_path / "packs" / request.pack_name))

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del req, settings, ctx, report_name, md5
        if pack_name != "validation_regen_candidate_1":
            raise AssertionError(f"unexpected validation pack: {pack_name}")
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
        )

    def _regenerate(request):
        decision = RepairDecision(
            diagnosed_failure_class="grounding",
            repair_action="REGENERATE_ITEM",
            repair_strategy="current_evidence",
            evidence_ids_used=["f1"],
            protected_fields=["summary.card_tldr_compact"],
            changed_paths=["summary.tldr"],
            minimal_patch=[
                RepairPatchOperation(
                    op="replace",
                    path="summary.tldr",
                    value="Repaired summary",
                )
            ],
        )
        return ArtifactRegenerationResponse(
            updated_artifacts=candidate,
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            candidate_artifacts_path=str(
                tmp_path / "candidates" / "artifacts_regen_candidate_1.json"
            ),
            repair_action="REGENERATE_ITEM",
            repair_strategy="current_evidence",
            selected_evidence_ids=["f1"],
            repair_decisions=[decision],
        )

    dependencies = _deps(
        analysis_pack_path=_analysis_pack_path,
        analysis_store_pack=_analysis_store_pack,
        read_json=_read_json,
        run_validation=_run_validation,
        regenerate_artifacts=_regenerate,
    )

    try:
        _run_validation_regeneration_loop(
            runtime=runtime,
            mode_ctx=runtime.ctx,
            base_payload=_payload(),
            current_artifacts=original,
            current_validation_report=ValidationReport(
                schema_version="1.1",
                status="fail",
                severity="error",
                issues=[issue],
            ),
            evidence_packs={
                "findings": {
                    "findings": [
                        {
                            "id": "f1",
                            "evidence": "Retained evidence supports the summary.",
                            "pages": [1],
                        },
                        {
                            "id": "f2",
                            "evidence": "Alternative retained evidence.",
                            "pages": [2],
                        },
                    ]
                },
                "doc_map": {"sections": []},
            },
            source_status=original["source_status"],
            category_labels=["Category"],
            vector_store_id=None,
            dependencies=dependencies,
        )
    except AppError as exc:
        caught = exc
    else:
        pytest.fail(
            f"fault injection did not execute; writes={writes!r}; "
            f"candidate_validation={stored.get('validation_regen_candidate_1')!r}"
        )

    assert caught.retryable is False
    assert injected is True
    if failure_stage == "candidate_audit":
        assert "artifacts" not in writes
    else:
        assert stored["artifacts"] == original
        assert writes.count("artifacts") >= 2
    if failure_stage == "canonical_validation":
        assert stored["validation"]["status"] == "fail"
    if failure_stage in {"promoted_claim_validation", "canonical_validation"}:
        # A partially written candidate package is not allowed to authorize
        # reuse against the restored artifact hash.
        assert (
            _load_promoted_claim_validation_for_reuse(
                runtime=runtime,
                dependencies=dependencies,
                expected_artifact_hash=sha256_json(original),
                ctx=runtime.ctx,
            )
            is None
        )


def test_promoted_claim_reuse_is_restart_safe_for_partial_promotion(tmp_path) -> None:
    """A reentry may reuse only a package matching persisted promoted artifacts."""

    runtime = _runtime(tmp_path)
    original = _artifacts_without_retained_claims(
        summary={
            "tldr": "Original summary.",
            "card_tldr_compact": "Original card.",
            "executive_summary": "Original executive summary.",
            "claim_evidence_map": [],
        }
    )
    candidate = deepcopy(original)
    candidate["summary"]["tldr"] = "Repaired summary."
    candidate_package = {
        "schema_version": "1.4",
        "artifact_hash": sha256_json(candidate),
        "package_hash": "",
        "results": [],
        "readiness_status": "awaiting_review",
        "unsupported_factual_count": 0,
        "unresolved_factual_count": 0,
        "deterministic_pass_count": 0,
        "semantic_validation_count": 0,
        "semantic_execution_identities": [],
        "validation_identity": None,
        "lineage": None,
    }
    candidate_package["package_hash"] = claim_validation_package_hash(candidate_package)

    def _store(pack_name: str, payload: dict) -> str:
        return report_analysis_store_service.store_pack(
            AnalysisStorePackRequest(
                schema_version="1.0",
                output_dir=runtime.settings.output_dir,
                report_id=runtime.file.file_id,
                pack_name=pack_name,
                payload=payload,
                report_slug=runtime.report_name,
            ),
            runtime.ctx,
        ).output_path

    _store("artifacts", candidate)
    _store("validation_retained_claim_validation_candidate", candidate_package)

    fresh_dependencies = _deps(
        analysis_pack_path=report_analysis_store_service.pack_path,
        analysis_store_pack=report_analysis_store_service.store_pack,
        read_json=file_service.read_json,
    )
    persisted_artifacts = file_service.read_json(
        ReadJsonRequest(
            schema_version="1.0",
            path=report_analysis_store_service.pack_path(
                AnalysisPackPathRequest(
                    schema_version="1.0",
                    output_dir=runtime.settings.output_dir,
                    report_id=runtime.file.file_id,
                    pack_name="artifacts",
                    report_slug=runtime.report_name,
                ),
                runtime.ctx,
            ).output_path,
        ),
        runtime.ctx,
    ).payload
    assert persisted_artifacts == candidate
    assert not (
        tmp_path / "out" / runtime.report_name / "report_analysis" / "validation.json"
    ).exists()
    assert (
        _load_promoted_claim_validation_for_reuse(
            runtime=runtime,
            dependencies=fresh_dependencies,
            expected_artifact_hash=sha256_json(persisted_artifacts),
            ctx=runtime.ctx,
        )
        == candidate_package
    )

    # Simulate interruption after a later artifact replacement while the old
    # promoted package remains on disk.  A new process must not bind the stale
    # package to the replacement artifact set.
    _store("artifacts", original)
    assert (
        _load_promoted_claim_validation_for_reuse(
            runtime=runtime,
            dependencies=fresh_dependencies,
            expected_artifact_hash=sha256_json(original),
            ctx=runtime.ctx,
        )
        is None
    )


@pytest.mark.parametrize(
    ("decisions", "response_selected", "expected"),
    [
        (
            [
                RepairDecision(
                    diagnosed_failure_class="grounding",
                    repair_action="ABSTAIN",
                    repair_strategy="safe_abstain",
                    evidence_ids_used=[],
                )
            ],
            ["planner-f1"],
            [],
        ),
        (
            [
                RepairDecision(
                    diagnosed_failure_class="grounding",
                    repair_action="REGENERATE_ITEM",
                    repair_strategy="current_evidence",
                    evidence_ids_used=["f1"],
                ),
                RepairDecision(
                    diagnosed_failure_class="grounding",
                    repair_action="ABSTAIN",
                    repair_strategy="safe_abstain",
                    evidence_ids_used=[],
                ),
            ],
            ["f1"],
            ["f1"],
        ),
        (
            [
                RepairDecision(
                    diagnosed_failure_class="grounding",
                    repair_action="REGENERATE_ITEM",
                    repair_strategy="current_evidence",
                    evidence_ids_used=["f1"],
                )
            ],
            ["f1"],
            ["f1"],
        ),
        (
            [
                RepairDecision(
                    diagnosed_failure_class="grounding",
                    repair_action="REGENERATE_ITEM",
                    repair_strategy="current_evidence",
                    evidence_ids_used=["f1"],
                ),
                RepairDecision(
                    diagnosed_failure_class="grounding",
                    repair_action="REGENERATE_ITEM",
                    repair_strategy="alternative_evidence",
                    evidence_ids_used=["f2"],
                ),
            ],
            ["f1", "f2"],
            ["f1", "f2"],
        ),
        (
            [
                RepairDecision(
                    diagnosed_failure_class="grounding",
                    repair_action="REMOVE_CLAIM",
                    repair_strategy="safe_removal",
                    evidence_ids_used=[],
                )
            ],
            ["planner-f1"],
            [],
        ),
    ],
)
def test_candidate_audit_records_executed_evidence_without_planner_fallback(
    tmp_path, decisions, response_selected, expected
) -> None:
    runtime = _runtime(tmp_path)
    current = _artifacts_without_retained_claims(
        summary={"tldr": "Original", "claim_evidence_map": []}
    )
    candidate = deepcopy(current)
    candidate["summary"]["tldr"] = "Candidate"
    plan = SimpleNamespace(
        targets=[
            SimpleNamespace(
                repair_action="REGENERATE_ITEM",
                repair_strategy="current_evidence",
                allowed_paths=["summary.tldr"],
                selected_evidence_ids=["planner-f1"],
                quarantined_evidence_ids=[],
                issues=[],
            )
        ]
    )
    response = SimpleNamespace(
        repair_action="+".join(dict.fromkeys(item.repair_action for item in decisions)),
        repair_strategy="+".join(
            dict.fromkeys(item.repair_strategy for item in decisions)
        ),
        selected_evidence_ids=response_selected,
        deterministic_mutation_paths=[],
        repair_decisions=decisions,
    )

    audit = _candidate_audit(
        runtime=runtime,
        attempt_index=1,
        transformation_scope=["summary"],
        current_artifacts=current,
        candidate_artifacts=candidate,
        current_artifacts_path="current.json",
        candidate_artifacts_path="candidate.json",
        candidate_result=CandidateIntegrityResult(issues=[], evidence_lineage=[]),
        plan=plan,
        regeneration_response=response,
    )

    assert audit.selected_evidence_ids == expected


__all__ = [
    "test_promotion_persistence_failures_do_not_authorize_partial_state",
    "test_promoted_claim_reuse_is_restart_safe_for_partial_promotion",
    "test_candidate_audit_records_executed_evidence_without_planner_fallback",
]
