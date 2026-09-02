from __future__ import annotations

from src.contracts.minimal_execution_plan import (
    ExecutionCompatibilityVersions,
    MinimalExecutionPlanInput,
    RetainedArtifact,
    RetainedArtifactGraph,
)
from src.utils.minimal_execution_planner import plan_minimal_execution


def _artifact(
    artifact_id: str,
    kind: str,
    family: str,
    dependencies: list[str],
    prompt_version: str,
) -> RetainedArtifact:
    return RetainedArtifact(
        schema_version="1.0",
        artifact_id=artifact_id,
        artifact_kind=kind,
        report_id="report-1",
        source_id="source-1",
        content_hash=artifact_id + "-hash",
        storage_ref="retained:" + artifact_id,
        state="active",
        schema_version_used="1.0",
        processing_version="report_generation_checkpoint_v2",
        validation_status="pass",
        dependency_artifact_ids=dependencies,
        compatibility={
            "artifact_family": family,
            "schema_versions": {family: "1.0"},
            "processing_versions": {family: "report_generation_checkpoint_v2"},
            "prompt_versions": {family: prompt_version},
            "model_policy_versions": {family: "routing-v1"},
        },
        lineage_status="complete",
        storage_available=True,
        observed_content_hash=artifact_id + "-hash",
    )


def test_prompt_change_targets_only_changed_family_and_downstream_dependents() -> None:
    candidate_family = "report_vs/artifacts/insights_candidates"
    final_family = "report_vs/artifacts/insights_final"
    summary_family = "report_vs/artifacts/summary"
    candidates = _artifact(
        "candidates",
        "prompt_family:" + candidate_family,
        candidate_family,
        [],
        "old-candidates",
    )
    final = _artifact(
        "final",
        "prompt_family:" + final_family,
        final_family,
        ["candidates"],
        "current-final",
    )
    summary = _artifact(
        "summary",
        "prompt_family:" + summary_family,
        summary_family,
        [],
        "current-summary",
    )
    plan = plan_minimal_execution(
        MinimalExecutionPlanInput(
            schema_version="1.0",
            execution_intent="targeted_repair",
            report_id="report-1",
            source_id="source-1",
            current_source_content_hashes={},
            retained_graph=RetainedArtifactGraph(
                schema_version="1.0",
                artifacts=[candidates, final, summary],
                edges=[("final", "candidates")],
            ),
            requested_output_families=[final_family, summary_family],
            current_compatibility=ExecutionCompatibilityVersions(
                schema_version="1.0",
                schema_versions={"*": "1.0"},
                processing_versions={"*": "report_generation_checkpoint_v2"},
                prompt_versions={
                    candidate_family: "current-candidates",
                    final_family: "current-final",
                    summary_family: "current-summary",
                },
                model_policy_versions={"*": "routing-v1"},
            ),
        )
    )

    assert [item.artifact_id for item in plan.invalid_artifacts] == [
        "candidates",
        "final",
    ]
    assert plan.required_prompt_families == [candidate_family, final_family]
    assert plan.reused_prompt_families == [summary_family]


def test_upstream_prompt_change_uses_normal_analysis_resume() -> None:
    """An evidence-pack change must not enter an artifact-only repair path."""
    findings_family = "report_vs/evidence_packs/findings"
    findings = _artifact(
        "findings",
        "prompt_family:" + findings_family,
        findings_family,
        [],
        "retained-findings",
    )

    plan = plan_minimal_execution(
        MinimalExecutionPlanInput(
            schema_version="1.0",
            execution_intent="targeted_repair",
            report_id="report-1",
            source_id="source-1",
            current_source_content_hashes={},
            retained_graph=RetainedArtifactGraph(
                schema_version="1.0",
                artifacts=[findings],
                edges=[],
            ),
            requested_output_families=[findings_family],
            current_compatibility=ExecutionCompatibilityVersions(
                schema_version="1.0",
                schema_versions={"*": "1.0"},
                processing_versions={"*": "report_generation_checkpoint_v2"},
                prompt_versions={findings_family: "current-findings"},
                model_policy_versions={"*": "routing-v1"},
            ),
        )
    )

    assert plan.required_prompt_families == []
    assert plan.required_stages == ["analysis_complete", "render_complete"]
    assert plan.required_external_calls == [
        "html_render",
        "report_analysis_model",
        "validator_model",
        "vector_store",
    ]
