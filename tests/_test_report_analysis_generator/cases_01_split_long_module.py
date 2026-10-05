# ruff: noqa: F401,F403,F405
from __future__ import annotations
from ._split_support_cases_02_allows_abstained_quote_family import *  # noqa: F401,F403


def test_scope_rejection_runs_deterministic_validation_without_provider_calls(
    tmp_path,
) -> None:
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(
            _runtime(tmp_path).settings, validation_regeneration_max_attempts=2
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    original = _artifacts_without_retained_claims(
        summary={
            "tldr": "Original summary",
            "card_tldr_compact": "Original card",
            "executive_summary": "Original executive summary",
            "claim_evidence_map": [],
        }
    )
    original["linkedin_post"] = "Original LinkedIn copy"
    _set_interpretive_summary_provenance(original)
    candidates = []
    for index in (1, 2):
        candidate = deepcopy(original)
        candidate["summary"]["tldr"] = (
            "not available from text"
            if index == 2
            else f"European loyalty reached 99% in 2025, attempt {index}."
        )
        candidate["summary"]["executive_summary"] = f"Candidate summary {index}"
        candidate["summary"]["claim_evidence_map"] = [
            {
                "id": f"candidate-claim-{index}",
                "claim": "European loyalty reached 99% in 2025.",
                "evidence_id": "f1",
            }
        ]
        candidate["linkedin_post"] = f"Unplanned LinkedIn change {index}"
        _set_interpretive_summary_provenance(candidate)
        candidates.append(candidate)
    validation_calls: list[str] = []
    validation_modes: list[str] = []
    retry_memories = []

    class ProviderSpy:
        def __init__(self):
            self.calls = []

        def openai_chat_json(self, request, ctx):
            self.calls.append(str(getattr(ctx, "task_id", "")))
            raise AssertionError("semantic/grounding providers must be skipped")

        def openai_respond_with_vector_store(self, request, ctx):
            self.calls.append(str(getattr(ctx, "task_id", "")))
            raise AssertionError("semantic/grounding providers must be skipped")

    provider_spy = ProviderSpy()

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        validation_modes.append(req.validation_mode)
        validation_calls.append(pack_name)
        if req.validation_mode == "inline_deterministic":
            return validate_report(
                req,
                settings,
                ctx,
                openai_client=provider_spy,
                pack_name=pack_name,
                report_name=report_name,
                md5=md5,
            )
        del settings, ctx, report_name, md5
        return ValidationReport(
            schema_version="1.1",
            status="fail",
            issues=[
                ValidationIssue(
                    schema_version="1.0",
                    message="[grounding] Unsupported summary claim",
                    severity="error",
                    affected_section="executive_summary",
                    rule_id="grounding",
                )
            ],
            severity="error",
        )

    def _regenerate(request):
        retry_memories.append(list(request.repair_memory))
        attempt = request.attempt_index
        return ArtifactRegenerationResponse(
            updated_artifacts=candidates[attempt - 1],
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            candidate_artifacts_path=str(
                tmp_path / "out" / f"artifacts_regen_candidate_{attempt}.json"
            ),
            repair_action="REGENERATE_ITEM",
            repair_strategy=f"strategy-{attempt}",
            selected_evidence_ids=[f"f{attempt}"],
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title"}},
            "findings": {
                "findings": [
                    {
                        "id": f"f{index}",
                        "text": (
                            "European loyalty reached 49% in 2024."
                            if index == 1
                            else ""
                        ),
                        "pages": [index],
                    }
                    for index in range(1, 6)
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

    assert validation_calls == [
        "validation",
        "validation_regen_candidate_1",
        "validation_regen_candidate_2",
    ]
    assert validation_modes == ["full", "inline_deterministic", "inline_deterministic"]
    assert provider_spy.calls == []
    assert len(state.regeneration_attempts) == 2
    assert all(
        attempt.promotion_outcome == "rolled_back"
        and attempt.repair_delta.mutation_scope_result == "fail"
        and attempt.repair_delta.semantic_grounding_validation_status
        == "not_evaluated_due_to_deterministic_failure"
        for attempt in state.regeneration_attempts
    )
    assert all(
        issue.rule_id != "deferred_grounding_required"
        for attempt in state.regeneration_attempts
        for issues in (
            attempt.repair_delta.introduced,
            attempt.repair_delta.persisting,
            attempt.repair_delta.resolved,
        )
        for issue in issues
    )
    assert any(
        issue.rule_id == "regeneration_scope_violation"
        for issue in state.regeneration_attempts[0].repair_delta.introduced
    )
    assert any(
        issue.rule_id == "claim_support"
        for issue in state.regeneration_attempts[0].repair_delta.introduced
    )
    assert any(
        issue.rule_id == "grounding" and issue.affected_section == "executive_summary"
        for issue in state.regeneration_attempts[0].repair_delta.resolved
    )
    first_audit = json.loads(
        Path(state.regeneration_attempts[0].candidate_audit_path).read_text(
            encoding="utf-8"
        )
    )
    assert first_audit["repair_delta"]["mutation_scope_result"] == "fail"
    assert (
        first_audit["repair_delta"]["semantic_grounding_validation_status"]
        == "not_evaluated_due_to_deterministic_failure"
    )
    assert any(
        key.startswith("deferred_grounding_required")
        for key in first_audit["validation_issues"]
    )
    validation_snapshot = json.loads(
        Path(state.regeneration_attempts[0].validation_snapshot_path).read_text(
            encoding="utf-8"
        )
    )
    assert any(
        issue["rule_id"] == "deferred_grounding_required"
        for issue in validation_snapshot["issues"]
    )
    assert any(
        item["rule_id"] == "claim_support"
        for item in first_audit["repair_delta"]["introduced"]
    )
    assert "public_editorial_quality_regen_attempt_1" in state.evidence_paths
    assert retry_memories[0] == []
    assert retry_memories[1][0].mutation_scope_result == "fail"
    assert any(
        issue.rule_id == "regeneration_scope_violation"
        for issue in retry_memories[1][0].introduced
    )
    assert any(
        issue.rule_id == "claim_support" for issue in retry_memories[1][0].introduced
    )
    assert all(
        issue.rule_id != "deferred_grounding_required"
        for issues in (
            retry_memories[1][0].introduced,
            retry_memories[1][0].persisting,
            retry_memories[1][0].resolved,
        )
        for issue in issues
    )
    assert any(
        issue.rule_id == "report_payload_incomplete"
        for issue in state.regeneration_attempts[1].repair_delta.introduced
    )
    second_audit = json.loads(
        Path(state.regeneration_attempts[1].candidate_audit_path).read_text(
            encoding="utf-8"
        )
    )
    assert any(
        item["rule_id"] == "report_payload_incomplete"
        for item in second_audit["repair_delta"]["introduced"]
    )
    assert any(
        item["rule_id"] == "claim_support"
        for item in second_audit["repair_delta"]["introduced"]
    )


def test_candidate_validation_merges_duplicate_fingerprints_at_strongest_severity():
    deterministic_issue = ValidationIssue(
        schema_version="1.0",
        message="Unsupported claim relationship",
        severity="error",
        affected_section="summary.claim_evidence_map[0]",
        rule_id="claim_support",
        entity_id="f1",
        evidence_ids=["f1"],
    )
    inline_duplicate = replace(deterministic_issue, severity="warning")

    report = _candidate_validation_report(
        ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[inline_duplicate],
            severity="warning",
        ),
        CandidateIntegrityResult(
            issues=[deterministic_issue],
            evidence_lineage=[],
        ),
    )

    assert report.status == "fail"
    assert report.severity == "error"
    assert report.issues == [deterministic_issue]


def test_run_report_analysis_retries_from_last_promoted_artifacts_after_rollback(
    tmp_path,
):
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(
            _runtime(tmp_path).settings, validation_regeneration_max_attempts=2
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    original = _artifacts_without_retained_claims(
        summary={
            "tldr": "original artifact",
            "card_tldr_compact": "original artifact",
            "executive_summary": "Original summary",
            "claim_evidence_map": [],
        }
    )
    candidates = [
        _artifacts_without_retained_claims(
            summary={
                "tldr": "failed candidate",
                "card_tldr_compact": "original artifact",
                "executive_summary": "Original summary",
                "claim_evidence_map": [],
            },
        ),
        _artifacts_without_retained_claims(
            summary={
                "tldr": "repaired artifact",
                "card_tldr_compact": "original artifact",
                "executive_summary": "Original summary",
                "claim_evidence_map": [],
            },
        ),
    ]
    for artifact in [original, *candidates]:
        _set_interpretive_summary_provenance(artifact)
    regeneration_inputs = []
    regeneration_artifact_inputs = []
    repair_usage_attempts = []
    regeneration_targets = []
    regeneration_strategies = []
    retry_memories = []
    candidate_package_reads = []
    promoted_candidate_packages = []
    candidate_package_payload = {}
    validation_calls = 0

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        nonlocal validation_calls
        del settings, ctx, report_name, md5
        validation_calls += 1
        if validation_calls == 1:
            return ValidationReport(
                schema_version="1.1",
                status="fail",
                issues=[
                    ValidationIssue(
                        schema_version="1.0",
                        message="[grounding] Unsupported summary claim",
                        severity="error",
                        affected_section="summary.tldr",
                        rule_id="grounding",
                        repair_target="summary",
                    )
                ],
                severity="error",
            )
        if validation_calls == 2:
            return ValidationReport(
                schema_version="1.1",
                status="fail",
                issues=[
                    ValidationIssue(
                        schema_version="1.0",
                        message="[grounding] Candidate introduced issue Y",
                        severity="error",
                        affected_section="linkedin_post",
                        rule_id="candidate_y",
                        repair_target="linkedin_post",
                    )
                ],
                severity="error",
            )
        if pack_name == "validation_regen_candidate_2":
            candidate_package_payload.update(
                {
                    "schema_version": "1.3",
                    "artifact_hash": sha256_json(req.artifacts),
                    "package_hash": "candidate-package-2",
                }
            )
        return ValidationReport(
            schema_version="1.1", status="pass", issues=[], severity="pass"
        )

    def _read_json(request, _ctx):
        candidate_package_reads.append(request.path)
        if not request.path.endswith(
            "validation_regen_candidate_2_retained_claim_validation_candidate.json"
        ):
            raise AppError(
                code="file_not_found",
                message="Only a promoted candidate package is retained in this test.",
            )
        return SimpleNamespace(payload=candidate_package_payload)

    def _store_analysis_pack(request, ctx):
        if request.pack_name == "validation_retained_claim_validation_candidate":
            promoted_candidate_packages.append(request)
            return SimpleNamespace(output_path=f"promoted/{request.pack_name}.json")
        return report_analysis_store_service.store_pack(request, ctx)

    def _regenerate(request):
        repair_usage_attempts.append(request.ctx.repair_attempt)
        regeneration_inputs.append(request.current_artifacts["summary"]["tldr"])
        regeneration_artifact_inputs.append(deepcopy(request.current_artifacts))
        regeneration_targets.append(
            [target.target_section for target in request.plan.targets]
        )
        retry_memories.append(list(request.repair_memory))
        attempt = request.attempt_index
        strategy = "current_evidence" if attempt == 1 else "alternative_evidence"
        evidence_id = "f1" if attempt == 1 else "f2"
        regeneration_strategies.append(request.plan.targets[0].repair_strategy)
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
                    value=candidates[attempt - 1]["summary"]["tldr"],
                )
            ],
        )
        return ArtifactRegenerationResponse(
            updated_artifacts=candidates[attempt - 1],
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            candidate_artifacts_path=str(
                tmp_path / "out" / f"artifacts_regen_candidate_{attempt}.json"
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
        read_json=_read_json,
        analysis_store_pack=_store_analysis_pack,
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
    assert regeneration_inputs == ["original artifact", "original artifact"]
    assert regeneration_artifact_inputs[0] == regeneration_artifact_inputs[1]
    assert repair_usage_attempts == [1, 2]
    assert regeneration_targets == [["summary"], ["summary"]]
    assert regeneration_strategies == ["current_evidence", "alternative_evidence"]
    assert retry_memories[0] == []
    assert retry_memories[1][0].introduced[0].rule_id == "candidate_y"
    assert retry_memories[1][0].repair_strategy == "current_evidence"
    assert retry_memories[1][0].strategy_fingerprint == (
        state.regeneration_attempts[0].strategy_fingerprint
    )
    assert retry_memories[1][0].evidence_ids_used == ["f1"]
    assert (
        retry_memories[1][0].candidate_sha256
        == json.loads(
            Path(state.regeneration_attempts[0].candidate_audit_path).read_text(
                encoding="utf-8"
            )
        )["after_sha256"]
    )
    assert len(state.regeneration_attempts) == 2
    assert state.regeneration_attempts[0].promotion_outcome == "rolled_back"
    assert state.regeneration_attempts[1].promotion_outcome == "promoted"
    assert state.artifacts_payload["summary"]["tldr"] == "repaired artifact"
    first_audit = json.loads(
        Path(state.regeneration_attempts[0].candidate_audit_path).read_text(
            encoding="utf-8"
        )
    )
    assert first_audit["repair_delta"]["introduced_hard_failure_count"] == 1
    assert first_audit["repair_decisions"][0]["minimal_patch"][0]["value"] == (
        "failed candidate"
    )
    assert (
        state.artifacts_payload["summary"]["tldr"]
        != first_audit["repair_decisions"][0]["minimal_patch"][0]["value"]
    )
    assert state.validation_report is not None
    assert state.validation_report.status == "pass"
    assert len(candidate_package_reads) == 1
    assert candidate_package_reads[0].endswith(
        "validation_regen_candidate_2_retained_claim_validation_candidate.json"
    )
    assert len(promoted_candidate_packages) == 1
    assert promoted_candidate_packages[0].payload == candidate_package_payload
    assert promoted_candidate_packages[0].payload["artifact_hash"] == sha256_json(
        state.artifacts_payload
    )
    assert (
        state.regeneration_attempts[1].artifacts_path
        == state.evidence_paths["artifacts"]
    )
    assert (
        state.regeneration_attempts[1].validation_path
        == state.evidence_paths["validation"]
    )


def test_noop_summary_repairs_advance_to_bounded_safe_removal(tmp_path):
    from src.generators.claim_validation_generator import (
        claim_validation_package_hash,
    )
    from src.orchestrators._report_analysis_orchestrator.validation import (
        _run_validation_regeneration_loop,
    )

    runtime = replace(
        _runtime(tmp_path),
        settings=replace(
            _runtime(tmp_path).settings, validation_regeneration_max_attempts=3
        ),
    )
    original = _artifacts_without_retained_claims(
        summary={
            "tldr": "The report documents a market shift.",
            "card_tldr_compact": "Observed changes shaped market priorities.",
            "executive_summary": "The report describes evidence-backed findings.",
            "claim_evidence_map": [
                {
                    "id": "claim-one",
                    "claim": "The market shifted during the observed period.",
                    "evidence_id": "f1",
                    "pages": [1],
                }
            ],
        }
    )
    _set_interpretive_summary_provenance(original)
    issue = ValidationIssue(
        schema_version="1.0",
        message="[semantic] The cited evidence does not establish the claim relationship.",
        severity="error",
        affected_section="summary.claim_evidence_map:claim-one.claim",
        rule_id="semantic",
        repair_target="summary",
        evidence_ids=["f1"],
    )
    validation_requests = []
    regeneration_requests = []
    candidate_package = {}

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del settings, ctx, report_name, md5
        validation_requests.append((pack_name, req.artifacts))
        if pack_name == "validation_regen_candidate_3":
            candidate_package.update(
                {
                    "schema_version": "1.3",
                    "artifact_hash": sha256_json(req.artifacts),
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
            )
            candidate_package["package_hash"] = claim_validation_package_hash(
                candidate_package
            )
            return ValidationReport(
                schema_version="1.1", status="pass", issues=[], severity="pass"
            )
        return ValidationReport(
            schema_version="1.1",
            status="fail",
            issues=[issue],
            severity="error",
        )

    def _regenerate(request):
        regeneration_requests.append(request)
        plan_target = request.plan.targets[0]
        candidate = deepcopy(request.current_artifacts)
        if request.attempt_index == 3:
            candidate["summary"]["claim_evidence_map"] = []
        return ArtifactRegenerationResponse(
            updated_artifacts=candidate,
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            candidate_artifacts_path=str(
                tmp_path
                / "out"
                / f"artifacts_regen_candidate_{request.attempt_index}.json"
            ),
            repair_action=plan_target.repair_action,
            repair_strategy=plan_target.repair_strategy,
            selected_evidence_ids=list(plan_target.selected_evidence_ids),
            deterministic_mutation_paths=(
                ["summary.claim_evidence_map[0]"] if request.attempt_index == 3 else []
            ),
        )

    deps = _deps(
        read_json=lambda _request, _ctx: SimpleNamespace(payload=candidate_package),
        run_validation=_run_validation,
        regenerate_artifacts=_regenerate,
    )
    (
        promoted_artifacts,
        promoted_validation,
        attempts,
        loop_state,
        _evidence_paths,
        _payload_overrides,
    ) = _run_validation_regeneration_loop(
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
                        "evidence": "Retained evidence supports the topic.",
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
        dependencies=deps,
    )

    assert [
        request.plan.targets[0].repair_strategy for request in regeneration_requests
    ] == ["current_evidence", "alternative_evidence", "safe_removal"]
    assert [name for name, _artifacts in validation_requests] == [
        "validation_regen_candidate_1",
        "validation_regen_candidate_2",
        "validation_regen_candidate_3",
    ]
    assert [attempt.promotion_outcome for attempt in attempts] == [
        "rolled_back",
        "rolled_back",
        "promoted",
    ]
    assert loop_state.final_status == "pass"
    assert promoted_validation.status == "pass"
    assert promoted_artifacts["summary"]["claim_evidence_map"] == []


def test_run_report_analysis_maps_topic_section_failures_to_topics_regeneration(
    tmp_path,
):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    validation_calls: list[str] = []
    regeneration_requests = []

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del settings, ctx, report_name, md5
        validation_calls.append(pack_name)
        if len(validation_calls) == 1:
            return ValidationReport(
                schema_version="1.1",
                status="fail",
                issues=[
                    ValidationIssue(
                        schema_version="1.0",
                        message="[toc_integrity] TOC coverage is missing section 'Media brands'.",
                        severity="error",
                        affected_section="toc_entries:section-1",
                        rule_id="toc_integrity",
                        repair_target="topics",
                        entity_id="section-1",
                    )
                ],
                severity="error",
                source_path=str(tmp_path / "out" / "validation.json"),
            )
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        )

    def _regenerate(request):
        regeneration_requests.append(request)
        return ArtifactRegenerationResponse(
            updated_artifacts=request.current_artifacts,
            regenerated_sections=[
                "toc_entries",
                "toc_topics",
                "toc_topics_expanded",
            ],
            prompt_namespaces=[],
            artifacts_path=str(tmp_path / "out" / "artifacts.json"),
            artifacts_snapshot_path=str(
                tmp_path / "out" / "artifacts_regen_attempt_1.json"
            ),
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {
                "title": "Doc Title",
                "publisher": "Doc Publisher",
                "sections": [
                    {
                        "id": "section-1",
                        "title": "Media brands",
                        "summary": "Media brand ad equity section.",
                        "key_points": [],
                        "pages": [17],
                    }
                ],
            }
        },
        generate_artifacts=lambda **kwargs: _artifacts(
            toc_entries=[
                {
                    "section_id": "section-2",
                    "section_title": "Sentiments on GenAI",
                    "display_title": "Media brand ad equity",
                    "summary": "Wrong section summary",
                    "key_points": [],
                    "pages": [25],
                    "order": 1,
                }
            ],
            toc_topics=["Media brand ad equity"],
            toc_topics_expanded=[
                {
                    "topic": "Media brand ad equity",
                    "summary": "Wrong section summary",
                    "key_points": [],
                    "section_id": "section-2",
                    "section_title": "Sentiments on GenAI",
                    "pages": [25],
                }
            ],
            summary={
                "tldr": "broken",
                "executive_summary": "Broken summary",
                "claim_evidence_map": [],
            },
        ),
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
            vector_store_status="indexing",
            indexed_at_utc=None,
            last_error=None,
        ),
        deps,
    )

    assert state.validation_report is not None
    assert state.validation_report.status == "pass"
    assert len(regeneration_requests) == 1
    assert regeneration_requests[0].plan.mode == "targeted"
    assert regeneration_requests[0].plan.targets[0].target_section == "topics"
    assert regeneration_requests[0].plan.targets[0].regenerate_steps == [
        "toc_entries",
        "toc_topics",
        "toc_topics_expanded",
    ]
    assert state.regeneration_attempts[0].regenerated_sections == [
        "toc_entries",
        "toc_topics",
        "toc_topics_expanded",
    ]
