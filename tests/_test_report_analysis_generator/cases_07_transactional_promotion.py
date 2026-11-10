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
    _attempt_strategy_fingerprint,
    _candidate_audit,
    _load_promoted_claim_validation_for_reuse,
    _promote_validated_regeneration_candidate,
    _run_validation_regeneration_loop,
)
from src.services import file_service, report_analysis_store_service
from src.utils.cache_utils import sha256_json

from ._shared import *  # noqa: F401,F403


@pytest.mark.parametrize(
    ("source_path", "persisted_payload", "expected_code"),
    [
        ("", None, "retained_claim_candidate_validation_artifact_missing"),
        (
            "candidate-validation.json",
            {"status": "pass", "issues": []},
            "retained_claim_candidate_validation_artifact_stale",
        ),
        (
            "candidate-validation.json",
            "unreadable",
            "retained_claim_candidate_validation_artifact_invalid",
        ),
    ],
)
def test_verified_promotion_requires_current_persisted_validation_artifact(
    tmp_path, source_path, persisted_payload, expected_code
) -> None:
    runtime = _runtime(tmp_path)
    validation_report = ValidationReport(
        schema_version="1.1",
        status="pass",
        severity="pass",
        issues=[],
        source_path=source_path,
    )

    def _read_json(_request, _ctx):
        if persisted_payload == "unreadable":
            raise AppError(
                code="file_not_found",
                message="Candidate validation artifact is absent.",
                retryable=False,
            )
        return SimpleNamespace(payload=persisted_payload)

    dependencies = _deps(read_json=_read_json)
    with pytest.raises(AppError) as exc_info:
        _promote_validated_regeneration_candidate(
            runtime=runtime,
            dependencies=dependencies,
            candidate_artifacts={},
            candidate_validation_report=validation_report,
            candidate_validation_pack_name="validation_regen_candidate_1",
            promoted_artifacts={},
            promoted_validation_report=ValidationReport(
                schema_version="1.1",
                status="fail",
                severity="error",
                issues=[],
            ),
            promoted_claim_validation_package=None,
            current_artifacts_path=str(tmp_path / "artifacts.json"),
            expected_source_id="source:canonical",
            expected_source_md5=runtime.md5,
            require_execution_identity=True,
            evidence_packs={},
            ctx=runtime.ctx,
        )

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    "failure_stage",
    [
        "candidate_audit",
        "canonical_artifacts",
        "promoted_claim_validation",
        "canonical_validation",
        "final_promotion_audit",
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
    (tmp_path / "packs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "packs" / "artifacts.json").write_text(
        json.dumps(original, sort_keys=True), encoding="utf-8"
    )

    def _analysis_pack_path(request, _ctx):
        return SimpleNamespace(
            output_path=str(tmp_path / "packs" / f"{request.pack_name}.json")
        )

    def _read_json(request, _ctx):
        if "validation_regen_candidate_1_retained_claim_validation_candidate" in (
            request.path
        ):
            return SimpleNamespace(payload=candidate_package)
        path = Path(request.path)
        if path.exists():
            return SimpleNamespace(payload=json.loads(path.read_text(encoding="utf-8")))
        raise AppError(
            code="file_not_found",
            message="No prior promoted claim package is retained in this test.",
        )

    def _analysis_store_pack(request, _ctx):
        nonlocal injected
        writes.append(request.pack_name)
        stored[request.pack_name] = request.payload
        path = tmp_path / "packs" / f"{request.pack_name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(request.payload, sort_keys=True), encoding="utf-8")
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
            or failure_stage == "final_promotion_audit"
            and request.pack_name == "regeneration_candidate_audit_1"
            and request.payload.get("promotion_outcome") == "promoted"
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
            validation_openai_client=_SemanticPassOpenAIClient(),
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
        assert (
            json.loads(
                (tmp_path / "packs" / "artifacts.json").read_text(encoding="utf-8")
            )
            == original
        )
    if failure_stage == "canonical_validation":
        assert not (tmp_path / "packs" / "validation.json").exists()
    if failure_stage == "final_promotion_audit":
        audit = json.loads(
            (tmp_path / "packs" / "regeneration_candidate_audit_1.json").read_text(
                encoding="utf-8"
            )
        )
        assert audit["promotion_outcome"] == "rolled_back"
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


@pytest.mark.parametrize("previous_package_kind", ["valid", "non_reusable"])
def test_promotion_rollback_restores_existing_claim_package_exactly(
    tmp_path, previous_package_kind: str
) -> None:
    """Rollback restores prior bytes even when the old package cannot be reused."""

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
    validation = ValidationReport(
        schema_version="1.1", status="pass", severity="pass", issues=[]
    )
    previous_claim = {
        "schema_version": "1.4",
        "artifact_hash": sha256_json(original),
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
    if previous_package_kind == "non_reusable":
        previous_claim["artifact_hash"] = "f" * 64
    previous_claim["package_hash"] = claim_validation_package_hash(previous_claim)
    previous_validation = ValidationReport(
        schema_version="1.1",
        status="fail",
        severity="error",
        issues=[
            ValidationIssue(
                schema_version="1.0",
                message="Prior failure",
                severity="error",
                affected_section="summary",
                rule_id="prior_failure",
            )
        ],
    ).to_dict()
    previous_audit = {
        "schema_version": "1.0",
        "attempt_index": 1,
        "transformation_scope": ["summary"],
        "before_sha256": sha256_json(original),
        "after_sha256": sha256_json(candidate),
        "current_artifacts_path": "prior-artifacts.json",
        "candidate_artifacts_path": "prior-candidate.json",
        "validation_status": "fail",
        "promotion_outcome": "rolled_back",
        "validation_issues": ["prior_failure"],
        "evidence_lineage": [],
    }

    def _store_pack(pack_name: str, payload: dict) -> str:
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

    artifacts_path = _store_pack("artifacts", original)
    claim_path = _store_pack(
        "validation_retained_claim_validation_candidate", previous_claim
    )
    validation_path = _store_pack("validation", previous_validation)
    audit_path = _store_pack("regeneration_candidate_audit_1", previous_audit)
    prior_bytes = {
        path: Path(path).read_bytes()
        for path in (artifacts_path, claim_path, validation_path, audit_path)
    }

    base_dependencies = _deps()
    injected = False

    def _store_with_failure(request, ctx):
        nonlocal injected
        result = base_dependencies.analysis_store_pack(request, ctx)
        if request.pack_name == "validation" and not injected:
            injected = True
            raise AppError(
                code="injected_after_validation_write",
                message="Injected failure after validation replacement.",
                retryable=False,
            )
        return result

    dependencies = _deps(analysis_store_pack=_store_with_failure)
    candidate_package = dict(previous_claim)
    candidate_package["artifact_hash"] = sha256_json(candidate)
    candidate_package["package_hash"] = claim_validation_package_hash(candidate_package)
    _store_pack(
        "validation_regen_candidate_1_retained_claim_validation_candidate",
        candidate_package,
    )
    promotion_audit = _candidate_audit(
        runtime=runtime,
        attempt_index=1,
        transformation_scope=["summary"],
        current_artifacts=original,
        candidate_artifacts=candidate,
        current_artifacts_path=artifacts_path,
        candidate_artifacts_path=str(tmp_path / "candidate.json"),
        candidate_result=CandidateIntegrityResult(issues=[], evidence_lineage=[]),
        validation_report=validation,
        promotion_outcome="promoted",
    )

    with pytest.raises(AppError) as exc_info:
        _promote_validated_regeneration_candidate(
            runtime=runtime,
            dependencies=dependencies,
            candidate_artifacts=candidate,
            candidate_validation_report=validation,
            candidate_validation_pack_name="validation_regen_candidate_1",
            promoted_artifacts=original,
            promoted_validation_report=ValidationReport(
                schema_version="1.1",
                status="fail",
                severity="error",
                issues=[],
            ),
            promoted_claim_validation_package=previous_claim,
            current_artifacts_path=artifacts_path,
            expected_source_id="",
            expected_source_md5="md5",
            promotion_audit=promotion_audit,
            ctx=runtime.ctx,
        )

    assert exc_info.value.code == "injected_after_validation_write"
    assert injected is True
    assert {path: Path(path).read_bytes() for path in prior_bytes} == prior_bytes


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


def test_executed_decision_metadata_overrides_planner_response_fields(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    current = _artifacts_without_retained_claims(
        summary={"tldr": "Original", "claim_evidence_map": []}
    )
    candidate = deepcopy(current)
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
    decision = RepairDecision(
        diagnosed_failure_class="grounding",
        repair_action="ABSTAIN",
        repair_strategy="current_evidence:provider_rejected:evidence_not_retained_or_quarantined",
        evidence_ids_used=[],
    )
    response = SimpleNamespace(
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
        selected_evidence_ids=["planner-f1"],
        deterministic_mutation_paths=[],
        repair_decisions=[decision],
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

    assert audit.repair_action == "ABSTAIN"
    assert audit.repair_strategy == (
        "current_evidence:provider_rejected:evidence_not_retained_or_quarantined"
    )
    assert audit.selected_evidence_ids == []
    assert _attempt_strategy_fingerprint(
        plan, response
    ) != _attempt_strategy_fingerprint(plan, SimpleNamespace(repair_decisions=[]))


__all__ = [
    "test_promotion_persistence_failures_do_not_authorize_partial_state",
    "test_promoted_claim_reuse_is_restart_safe_for_partial_promotion",
    "test_promotion_rollback_restores_existing_claim_package_exactly",
    "test_candidate_audit_records_executed_evidence_without_planner_fallback",
]
