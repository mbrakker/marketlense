from __future__ import annotations

from dataclasses import asdict

from src.contracts.ingest import IngestSettings
from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    ArtifactRegenerationResponse,
    RegenerationAttemptResult,
    RegenerationCandidateAudit,
    RegenerationEvidenceLineage,
    RegenerationIssue,
    RegenerationLoopState,
    RegenerationPlan,
    RegenerationTarget,
)
from src.contracts.run_context import RunContext


def _settings() -> IngestSettings:
    return IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-5-mini",
        batch_limit=1,
        output_dir="./out",
        cache_dir="./cache",
        state_db="./state.sqlite",
        reports_db="./reports.sqlite",
        category_mapping_path="./cats.yaml",
        cover_style_path="./cover.yaml",
        ingest_lock_path="./ingest.lock",
        temperature=0.0,
    )


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="run",
        task_id="task",
        span_id="span",
    )


def test_regeneration_contracts_roundtrip(assert_no_defaulted_required_fields) -> None:
    issue = RegenerationIssue(
        rule_id="grounding",
        affected_section="executive_summary",
        message="[grounding] Unsupported summary claim",
        severity="error",
        evidence_ids=["f1"],
        pages=[1, 2],
    )
    target = RegenerationTarget(
        target_section="summary",
        regenerate_steps=["summary"],
        prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
        issues=[issue],
    )
    plan = RegenerationPlan(
        mode="targeted",
        targets=[target],
        unmappable_issues=[],
        broad_retry_allowed=True,
    )
    attempt = RegenerationAttemptResult(
        attempt_index=1,
        plan_mode="targeted",
        validation_before_status="fail",
        validation_after_status="pass",
        regenerated_sections=["summary"],
        artifacts_path="./out/report/report_analysis/artifacts.json",
        artifacts_snapshot_path="./out/report/report_analysis/artifacts_regen_attempt_1.json",
        validation_path="./out/report/report_analysis/validation.json",
        validation_snapshot_path="./out/report/report_analysis/validation_regen_attempt_1.json",
    )
    loop = RegenerationLoopState(
        attempt_count=1,
        max_attempts=3,
        final_status="pass",
        max_reached=False,
    )
    request = ArtifactRegenerationRequest(
        report_id="report-1",
        report_name="report-1",
        attempt_index=1,
        plan=plan,
        current_artifacts={"summary": {"tldr": "x"}},
        doc_map={"doc_id": "doc-1"},
        evidence_packs={"findings": {"findings": [{"id": "f1"}]}},
        settings=_settings(),
        ctx=_ctx(),
        source_status={"not_available": False},
        categories=["Category"],
        vector_store_id="vs_1",
        md5="md5",
    )
    response = ArtifactRegenerationResponse(
        updated_artifacts={"summary": {"tldr": "fixed"}},
        regenerated_sections=["summary"],
        prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
        artifacts_path="./out/report/report_analysis/artifacts.json",
        artifacts_snapshot_path="./out/report/report_analysis/artifacts_regen_attempt_1.json",
    )
    lineage = RegenerationEvidenceLineage(
        entity_kind="insight",
        entity_id="insight-1",
        original_evidence_ids=["f1"],
        candidate_evidence_ids=["f2"],
        original_source_pages=[1],
        candidate_source_pages=[2],
        validation_issues=[],
    )
    audit = RegenerationCandidateAudit(
        attempt_index=1,
        transformation_scope=["summary"],
        before_sha256="a" * 64,
        after_sha256="b" * 64,
        current_artifacts_path="./out/report/report_analysis/artifacts.json",
        candidate_artifacts_path="./out/report/report_analysis/artifacts_regen_candidate_1.json",
        validation_status="pass",
        promotion_outcome="promoted",
        validation_issues=[],
        evidence_lineage=[lineage],
    )

    for contract in (
        issue,
        target,
        plan,
        attempt,
        loop,
        request,
        response,
        lineage,
        audit,
    ):
        assert_no_defaulted_required_fields(contract)

    issue_raw = asdict(issue)
    target_raw = asdict(target)
    plan_raw = asdict(plan)
    attempt_raw = asdict(attempt)
    loop_raw = asdict(loop)
    request_raw = asdict(request)
    response_raw = asdict(response)
    lineage_raw = asdict(lineage)
    audit_raw = asdict(audit)

    assert RegenerationIssue(**issue_raw) == issue
    assert (
        RegenerationTarget(
            **{
                **target_raw,
                "issues": [RegenerationIssue(**item) for item in target_raw["issues"]],
            }
        )
        == target
    )
    assert (
        RegenerationPlan(
            **{
                **plan_raw,
                "targets": [
                    RegenerationTarget(
                        **{
                            **item,
                            "issues": [
                                RegenerationIssue(**issue_item)
                                for issue_item in item["issues"]
                            ],
                        }
                    )
                    for item in plan_raw["targets"]
                ],
                "unmappable_issues": [
                    RegenerationIssue(**item) for item in plan_raw["unmappable_issues"]
                ],
            }
        )
        == plan
    )
    assert RegenerationAttemptResult(**attempt_raw) == attempt
    assert RegenerationLoopState(**loop_raw) == loop
    assert (
        ArtifactRegenerationRequest(
            **{
                **request_raw,
                "plan": RegenerationPlan(
                    **{
                        **request_raw["plan"],
                        "targets": [
                            RegenerationTarget(
                                **{
                                    **item,
                                    "issues": [
                                        RegenerationIssue(**issue_item)
                                        for issue_item in item["issues"]
                                    ],
                                }
                            )
                            for item in request_raw["plan"]["targets"]
                        ],
                        "unmappable_issues": [
                            RegenerationIssue(**item)
                            for item in request_raw["plan"]["unmappable_issues"]
                        ],
                    }
                ),
                "settings": IngestSettings(**request_raw["settings"]),
                "ctx": RunContext(**request_raw["ctx"]),
            }
        )
        == request
    )
    assert ArtifactRegenerationResponse(**response_raw) == response
    assert RegenerationEvidenceLineage(**lineage_raw) == lineage
    assert (
        RegenerationCandidateAudit(
            **{
                **audit_raw,
                "evidence_lineage": [
                    RegenerationEvidenceLineage(**item)
                    for item in audit_raw["evidence_lineage"]
                ],
            }
        )
        == audit
    )
