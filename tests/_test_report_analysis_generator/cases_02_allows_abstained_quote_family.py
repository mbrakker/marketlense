# ruff: noqa: F401,F403,F405
from __future__ import annotations
from ._split_support_cases_02_allows_abstained_quote_family import *  # noqa: F401,F403


def test_run_report_analysis_allows_abstained_quote_family(tmp_path):
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(_runtime(tmp_path).settings, figure_caption_enabled=False),
    )
    source = _source(runtime)
    source.payload.quote.text = ""
    selection = _selection(runtime, source)
    validation_calls = []
    artifacts = _artifacts(
        quotes_final=[],
        family_status={
            "quotes": {
                "schema_version": "1.0",
                "family": "quotes",
                "source": "artifact",
                "status": "abstained",
                "confidence_score": 0.65,
                "policy_action": "regenerate",
                "reason": "quotes_missing_verbatim_source",
            }
        },
    )
    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=lambda **kwargs: artifacts,
        run_validation=lambda *args, **kwargs: (
            validation_calls.append(args[0])
            or ValidationReport(
                schema_version="1.1",
                status="pass",
                issues=[],
                severity="pass",
                source_path=str(tmp_path / "out" / "validation.json"),
            )
        ),
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

    assert validation_calls
    assert state.payload.quote.text == ""
    assert state.artifacts_payload["family_status"]["quotes"]["status"] == "abstained"


def test_run_report_analysis_regenerates_failed_section_until_pass(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
):
    caplog.set_level(logging.INFO, logger="market_lense.report_analysis_orchestrator")
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    validation_calls: list[str] = []
    regeneration_requests = []

    initial = _artifacts_without_retained_claims(
        summary={
            "tldr": "",
            "executive_summary": "",
            "claim_evidence_map": [
                {
                    "id": "summary-claim-1",
                    "claim": "Unsupported summary claim",
                    "evidence_id": "rejected-source",
                    "pages": [1],
                }
            ],
        }
    )
    repaired = _artifacts_without_retained_claims(
        summary={
            "tldr": "",
            "executive_summary": "",
            "claim_evidence_map": [],
        }
    )

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del settings, ctx, report_name, md5
        validation_calls.append(
            f"{pack_name}:{req.artifacts.get('summary', {}).get('tldr', '')}"
        )
        if len(validation_calls) == 1:
            return ValidationReport(
                schema_version="1.1",
                status="fail",
                issues=[
                    ValidationIssue(
                        schema_version="1.0",
                        message="[grounding] The claim is not established by its cited source.",
                        severity="error",
                        affected_section="summary.claim_evidence_map:summary-claim-1.claim",
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
            updated_artifacts=repaired,
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            artifacts_path=str(tmp_path / "out" / "artifacts.json"),
            artifacts_snapshot_path=str(
                tmp_path / "out" / "artifacts_regen_attempt_1.json"
            ),
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=lambda **kwargs: initial,
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
    assert state.regeneration_loop_state is not None
    assert state.regeneration_loop_state.attempt_count == 1
    assert state.regeneration_loop_state.final_status == "pass"
    assert state.regeneration_attempts[0].regenerated_sections == ["summary"]
    assert regeneration_requests[0].plan.mode == "targeted"
    assert regeneration_requests[0].plan.targets[0].target_section == "summary"
    assert "artifacts_regen_attempt_1" in state.evidence_paths
    assert "validation_regen_attempt_1" in state.evidence_paths

    events = _orchestrator_events(caplog)
    regen_events = [
        event
        for event in events
        if str(event.get("event", "")).startswith("validation_regen_")
    ]
    assert_logs_have_required_fields(regen_events)
    assert {event["event"] for event in regen_events} >= {
        "validation_regen_loop_start",
        "validation_regen_plan_built",
        "validation_regen_attempt_start",
        "validation_regen_attempt_complete",
        "validation_regen_pass",
    }


def test_run_report_analysis_rolls_back_failed_candidate_regeneration(tmp_path):
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(
            _runtime(tmp_path).settings, validation_regeneration_max_attempts=1
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    original = _artifacts_without_retained_claims(
        summary={
            "tldr": "current artifact",
            "card_tldr_compact": "current artifact",
            "executive_summary": "Current summary",
            "claim_evidence_map": [],
        }
    )
    candidate = _artifacts_without_retained_claims(
        summary={
            "tldr": "candidate artifact",
            "card_tldr_compact": "current artifact",
            "executive_summary": "Current summary",
            "claim_evidence_map": [],
        },
    )
    _set_interpretive_summary_provenance(original)
    _set_interpretive_summary_provenance(candidate)
    validation_calls = 0

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
                        message="[grounding] Unsupported summary claim",
                        severity="error",
                        affected_section="summary.tldr",
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
                    message="[grounding] Candidate introduced issue Y",
                    severity="error",
                    affected_section="linkedin_post",
                    rule_id="candidate_y",
                    repair_target="linkedin_post",
                )
            ],
            severity="error",
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
        regenerate_artifacts=lambda request: ArtifactRegenerationResponse(
            updated_artifacts=candidate,
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            candidate_artifacts_path=str(
                tmp_path / "out" / "artifacts_regen_candidate_1.json"
            ),
        ),
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

    assert state.artifacts_payload["summary"]["tldr"] == "current artifact"
    assert state.regeneration_attempts[0].promotion_outcome == "rolled_back"
    assert state.regeneration_attempts[0].candidate_audit_path
    assert state.validation_report.status == "fail"
    assert [issue.rule_id for issue in state.validation_report.issues] == ["grounding"]
    candidate_audit = json.loads(
        Path(state.regeneration_attempts[0].candidate_audit_path).read_text(
            encoding="utf-8"
        )
    )
    assert candidate_audit["validation_issues"] == ["candidate_y:linkedin_post"]


@pytest.mark.parametrize(
    ("baseline_retained_severity", "expected_outcome"),
    [("error", "rolled_back"), ("warning", "promoted")],
)
def test_candidate_promotion_preserves_promoted_retained_claim_severity(
    tmp_path, baseline_retained_severity: str, expected_outcome: str
) -> None:
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(
            _runtime(tmp_path).settings, validation_regeneration_max_attempts=1
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    evidence_packs = {
        "doc_map": {"docMap": {"title": "Doc Title"}},
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": "European loyalty reached 49% in 2024.",
                    "pages": [1],
                },
                *[{"id": f"f{index}", "pages": [index]} for index in range(2, 6)],
            ]
        },
        "quote_candidates": {"quote_candidates": [{"id": "q1", "page": 1}]},
    }
    original = _artifacts_without_retained_claims(
        summary={
            "tldr": "Broken summary",
            "card_tldr_compact": "Stable summary card text",
            "executive_summary": "Current summary",
            "claim_evidence_map": [
                {
                    "id": "summary-claim-1",
                    "claim": "European loyalty reached 99% in 2023.",
                    "evidence_id": "f1",
                    "evidence": "European loyalty reached 49% in 2024.",
                    "pages": [1],
                }
            ],
        }
    )
    _set_interpretive_summary_provenance(original)
    candidate = deepcopy(original)
    candidate["summary"]["tldr"] = "Repaired summary"
    _set_interpretive_summary_provenance(candidate)
    retained_issues = [
        replace(issue, severity=baseline_retained_severity)
        for issue in retained_claim_repair_issues(original, evidence_packs)
    ]
    validation_calls: list[str] = []
    candidate_package_reads: list[str] = []
    promoted_candidate_packages = []
    candidate_package_payload = {}

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
                        message="[grounding] Broken summary text",
                        severity="error",
                        affected_section="summary.tldr",
                        rule_id="grounding",
                        repair_target="summary",
                    ),
                    *retained_issues,
                ],
                severity="error",
            )
        if expected_outcome == "promoted" and pack_name == (
            "validation_regen_candidate_1"
        ):
            candidate_package_payload.update(
                {
                    "schema_version": "1.3",
                    "artifact_hash": sha256_json(req.artifacts),
                    "package_hash": "candidate-package-1",
                }
            )
        return ValidationReport(
            schema_version="1.1", status="pass", issues=[], severity="pass"
        )

    def _read_candidate_package(request, _ctx):
        candidate_package_reads.append(request.path)
        return SimpleNamespace(payload=candidate_package_payload)

    def _store_analysis_pack(request, ctx):
        if request.pack_name == "validation_retained_claim_validation_candidate":
            promoted_candidate_packages.append(request)
            return SimpleNamespace(output_path=f"promoted/{request.pack_name}.json")
        return report_analysis_store_service.store_pack(request, ctx)

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: evidence_packs,
        generate_artifacts=lambda **kwargs: original,
        run_validation=_run_validation,
        regenerate_artifacts=lambda request: ArtifactRegenerationResponse(
            updated_artifacts=candidate,
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            candidate_artifacts_path=str(
                tmp_path / "out" / "artifacts_regen_candidate_1.json"
            ),
        ),
        read_json=_read_candidate_package,
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

    assert len(state.regeneration_attempts) == 1
    assert validation_calls == ["validation", "validation_regen_candidate_1"]
    assert state.regeneration_attempts[0].promotion_outcome == expected_outcome
    assert len(candidate_package_reads) == int(expected_outcome == "promoted")
    assert len(promoted_candidate_packages) == int(expected_outcome == "promoted")
    assert state.artifacts_payload["summary"]["tldr"] == (
        "Repaired summary" if expected_outcome == "promoted" else "Broken summary"
    )
    if expected_outcome == "rolled_back":
        assert (
            state.regeneration_attempts[
                0
            ].repair_delta.semantic_grounding_validation_status
            == "not_evaluated_due_to_deterministic_failure"
        )
        assert any(
            item.rule_id == "retained_claim.number_value_unit_match"
            for item in state.regeneration_attempts[0].repair_delta.persisting
        )
    else:
        assert candidate_package_payload["artifact_hash"] == sha256_json(
            state.artifacts_payload
        )
        assert (
            state.regeneration_attempts[
                0
            ].repair_delta.semantic_grounding_validation_status
            == "evaluated"
        )
        assert "public_editorial_quality_regen_attempt_1" in state.evidence_paths
        assert any(
            issue.rule_id == "retained_claim.number_value_unit_match"
            and issue.severity == "warning"
            for issue in state.validation_report.issues
        )


from .cases_01_split_long_module import *  # noqa: F401,F403

from .cases_02_split_long_module import *  # noqa: F401,F403
