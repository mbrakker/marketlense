from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from src.contracts.minimal_execution_plan import (
    MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
    ExecutionCompatibilityVersions,
    MinimalExecutionPlanInput,
    RetainedArtifact,
    RetainedArtifactGraph,
)
from src.utils.minimal_execution_planner import plan_minimal_execution


def _versions() -> ExecutionCompatibilityVersions:
    return ExecutionCompatibilityVersions(
        schema_versions={"*": "schema-v1"},
        processing_versions={"*": "processor-v1"},
        prompt_versions={
            "report_vs/artifacts/summary": "summary-v1",
            "report_vs/artifacts/linkedin_post": "linkedin-v1",
        },
        model_policy_versions={"*": "model-policy-v1"},
        validator_versions={"validation": "validator-v1"},
        crop_profiles={"*": "crop-v1"},
        template_render_versions={"rendered_html": "template-v1"},
        parser_version="parser-v1",
        ocr_policy_version="ocr-v1",
    )


def _artifact(
    artifact_id: str,
    kind: str,
    *,
    dependencies: list[str] | None = None,
    compatibility: dict[str, object] | None = None,
    lineage_status: str = "complete",
    available: bool = True,
    observed_hash: str = "hash",
) -> RetainedArtifact:
    profile = asdict(_versions())
    profile["artifact_family"] = kind
    profile["source_metadata_hash"] = {"rendered_html": "source-meta-v1"}
    if compatibility:
        profile.update(compatibility)
    return RetainedArtifact(
        artifact_id=artifact_id,
        artifact_kind=kind,
        report_id="report-1",
        source_id="source-1",
        content_hash="hash",
        storage_ref=f"retained/{artifact_id}",
        state="active",
        schema_version_used="schema-v1",
        processing_version="processor-v1",
        validation_status="pass",
        dependency_artifact_ids=dependencies or [],
        compatibility=profile,
        lineage_status=lineage_status,
        storage_available=available,
        observed_content_hash=observed_hash,
    )


def _input(
    *,
    versions: ExecutionCompatibilityVersions | None = None,
    intent: str = "report_generation",
    source_hash: str = "hash",
    source_metadata_hash: str = "",
    publication_target: str = "",
    graph: RetainedArtifactGraph | None = None,
) -> MinimalExecutionPlanInput:
    source = _artifact("source", "source_pdf")
    analysis = _artifact("analysis", "analysis_pdf", dependencies=["source"])
    crop = _artifact("crop", "crop_image", dependencies=["analysis"])
    artifacts = _artifact("artifacts", "artifacts", dependencies=["analysis"])
    validation = _artifact("validation", "validation", dependencies=["artifacts"])
    rendered = _artifact(
        "rendered",
        "rendered_html",
        dependencies=["artifacts", "validation", "crop"],
    )
    publication = _artifact(
        "publication",
        "publication",
        dependencies=["rendered"],
        compatibility={"publication_target": {"publication": "wordpress-v1"}},
    )
    retained = graph or RetainedArtifactGraph(
        artifacts=[
            source,
            analysis,
            crop,
            artifacts,
            validation,
            rendered,
            publication,
        ],
        edges=[
            ("analysis", "source"),
            ("crop", "analysis"),
            ("artifacts", "analysis"),
            ("validation", "artifacts"),
            ("rendered", "artifacts"),
            ("rendered", "validation"),
            ("rendered", "crop"),
            ("publication", "rendered"),
        ],
    )
    requested = "publication" if intent == "publication_repair" else "rendered_html"
    return MinimalExecutionPlanInput(
        schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
        execution_intent=intent,
        report_id="report-1",
        source_id="source-1",
        current_source_content_hashes={"source-1": source_hash},
        retained_graph=retained,
        requested_output_families=[requested],
        current_compatibility=versions or _versions(),
        source_metadata_hash=source_metadata_hash,
        current_publication_state=(
            {"target": publication_target} if publication_target else {}
        ),
    )


def _reasons(plan) -> set[str]:
    return {item.reason for item in plan.invalid_artifacts}


def test_identical_inputs_have_a_stable_hash_and_skip_all_but_render() -> None:
    first = plan_minimal_execution(_input(intent="render_repair"))
    second = plan_minimal_execution(_input(intent="render_repair"))

    assert first.plan_hash == second.plan_hash
    assert first.required_stages == ["render_complete"]
    assert first.skipped_stages == [
        "source_prepared",
        "selection_complete",
        "analysis_complete",
        "publication_complete",
    ]


@pytest.mark.parametrize(
    ("change", "assertion"),
    [
        ("source", "source_content_changed"),
        ("metadata", "source_metadata_changed"),
        ("parser", "parser_version_changed"),
        ("ocr", "ocr_policy_version_changed"),
        ("summary", "prompt_changed:summary"),
        ("linkedin", "prompt_changed:linkedin_post"),
        ("schema", "output_schema_changed"),
        ("model", "model_policy_changed"),
        ("validator", "validator_changed"),
        ("crop", "crop_profile_changed"),
        ("template", "template_changed"),
        ("publication", "publication_target_changed"),
    ],
)
def test_compatibility_matrix_invalidates_only_the_required_family(
    change: str, assertion: str
) -> None:
    versions = _versions()
    kwargs: dict[str, object] = {}
    intent = "report_generation"
    if change == "source":
        kwargs["source_hash"] = "changed-source"
    elif change == "metadata":
        kwargs["source_metadata_hash"] = "source-meta-v2"
    elif change == "parser":
        versions = replace(versions, parser_version="parser-v2")
    elif change == "ocr":
        versions = replace(versions, ocr_policy_version="ocr-v2")
    elif change == "summary":
        versions = replace(
            versions,
            prompt_versions={
                **versions.prompt_versions,
                "report_vs/artifacts/summary": "summary-v2",
            },
        )
    elif change == "linkedin":
        versions = replace(
            versions,
            prompt_versions={
                **versions.prompt_versions,
                "report_vs/artifacts/linkedin_post": "linkedin-v2",
            },
        )
    elif change == "schema":
        versions = replace(versions, schema_versions={"*": "schema-v2"})
    elif change == "model":
        versions = replace(versions, model_policy_versions={"*": "model-policy-v2"})
    elif change == "validator":
        versions = replace(versions, validator_versions={"validation": "validator-v2"})
    elif change == "crop":
        versions = replace(versions, crop_profiles={"*": "crop-v2"})
        intent = "crop_repair"
    elif change == "template":
        versions = replace(
            versions, template_render_versions={"rendered_html": "template-v2"}
        )
        intent = "render_repair"
    else:
        intent = "publication_repair"
        kwargs["publication_target"] = "wordpress-v2"

    plan = plan_minimal_execution(_input(versions=versions, intent=intent, **kwargs))

    assert any(
        reason == assertion or reason.startswith(f"{assertion}:")
        for reason in _reasons(plan)
    )
    if change == "source":
        assert plan.required_stages == [
            "source_prepared",
            "selection_complete",
            "analysis_complete",
            "render_complete",
        ]
    if change == "crop":
        assert plan.required_stages == ["selection_complete", "render_complete"]
        assert "analysis_complete" not in plan.required_stages
    if change in {"template", "metadata"}:
        assert plan.required_stages == ["render_complete"]
    if change == "publication":
        assert plan.required_stages == ["publication_complete"]


@pytest.mark.parametrize("failure", ["missing", "hash", "edge", "historic"])
def test_integrity_matrix_fails_closed(failure: str) -> None:
    input_value = _input()
    artifacts = list(input_value.retained_graph.artifacts)
    edges = list(input_value.retained_graph.edges)
    if failure == "missing":
        artifacts[0] = replace(artifacts[0], storage_available=False)
    elif failure == "hash":
        artifacts[0] = replace(artifacts[0], observed_content_hash="wrong")
    elif failure == "edge":
        edges.remove(("rendered", "validation"))
    else:
        artifacts[3] = replace(artifacts[3], lineage_status="legacy_unverified")
    plan = plan_minimal_execution(
        replace(input_value, retained_graph=RetainedArtifactGraph(artifacts, edges))
    )

    assert plan.missing_lineage_blockers or plan.invalid_artifacts
    if failure == "missing":
        assert "retained_artifact_missing" in _reasons(plan)
    if failure == "hash":
        assert "artifact_hash_mismatch" in _reasons(plan)
    if failure == "edge":
        assert "dependency_edge_missing" in _reasons(plan)
    if failure == "historic":
        assert any(
            blocker.reason == "missing_lineage:compatibility_incomplete"
            for blocker in plan.missing_lineage_blockers
        )


def test_prompt_family_repair_keeps_crop_and_source_reusable() -> None:
    versions = replace(
        _versions(),
        prompt_versions={
            "report_vs/artifacts/summary": "summary-v2",
            "report_vs/artifacts/linkedin_post": "linkedin-v1",
        },
    )

    plan = plan_minimal_execution(_input(versions=versions, intent="targeted_repair"))

    assert "source" not in {item.artifact_id for item in plan.invalid_artifacts}
    assert "crop" not in {item.artifact_id for item in plan.invalid_artifacts}
    assert "prompt_changed:summary" in _reasons(plan)
    assert plan.required_stages == ["analysis_complete", "render_complete"]


def test_publication_only_retry_has_no_model_or_render_calls() -> None:
    plan = plan_minimal_execution(_input(intent="publication_repair"))

    assert plan.required_stages == ["publication_complete"]
    assert plan.required_external_calls == ["wordpress_write"]


def test_complete_current_record_supersedes_stale_audit_row() -> None:
    input_value = _input(intent="render_repair")
    stale_rendered = replace(
        next(
            item
            for item in input_value.retained_graph.artifacts
            if item.artifact_kind == "rendered_html"
        ),
        artifact_id="legacy-rendered",
        lineage_status="complete",
        observed_content_hash="old-content",
    )
    graph = RetainedArtifactGraph(
        artifacts=[*input_value.retained_graph.artifacts, stale_rendered],
        edges=input_value.retained_graph.edges,
    )

    plan = plan_minimal_execution(replace(input_value, retained_graph=graph))

    assert not plan.missing_lineage_blockers
    assert "legacy-rendered" not in {
        artifact.artifact_id for artifact in plan.invalid_artifacts
    }
    assert plan.required_stages == ["render_complete"]
