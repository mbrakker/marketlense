from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.artifact_lineage import ArtifactLineageTraceRequest
from src.contracts.prompt_family_materialization import (
    PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
    PromptFamilyMaterializationRequest,
    PromptFamilyReuseRequest,
)
from src.contracts.run_context import RunContext
from src.services.prompt_family_materialization_service import (
    materialize_prompt_family,
    read_reusable_prompt_family,
)
from src.services.report_store_service import trace_artifact_lineage
from src.utils.errors import AppError

ROOT = Path(__file__).resolve().parents[1]
RETAINED_ARTIFACTS = (
    ROOT
    / "tests"
    / "fixtures"
    / "docpacks"
    / "golden"
    / "morningstar-2026-outlook-acig-pdf"
    / "report_analysis"
    / "artifacts.json"
)


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="prompt-family-test",
        task_id="prompt-family-test",
        span_id="prompt-family-test",
    )


def _request(tmp_path: Path, *, output: object, dependencies=None, hashes=None):
    return PromptFamilyMaterializationRequest(
        schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
        db_path=str(tmp_path / "reports.sqlite"),
        output_dir=str(tmp_path / "out"),
        report_id="retained-report",
        report_slug="retained-report",
        source_id="md5:retained",
        family_id="report_vs/artifacts/summary",
        family_schema_version="3.0",
        processing_version="report_generation_checkpoint_v2",
        output_payload=output,
        system_prompt_hash="system-hash",
        user_prompt_hash="user-hash",
        prompt_content_hash="prompt-content-hash",
        prompt_dependency_manifest={
            "namespace": "report_vs/artifacts/summary",
            "system_root": {"path": "prompts/report_vs/artifacts/summary/system.yaml"},
        },
        execution_identity="execution-identity-hash",
        execution_identity_manifest={"provider": "openai", "model": "gpt-5-mini"},
        prompt_policy_version="policy-hash",
        model_name="gpt-5-mini",
        model_provider="openai",
        model_policy_namespace="report_vs",
        routing_policy_version="routing-hash",
        relevant_input_hash="input-hash",
        configuration_policy_hash="configuration-policy-hash",
        validator_version="validation-v1",
        direct_dependency_artifact_ids=dependencies or [],
        direct_dependency_hashes=hashes or {},
        evidence_set_hash="evidence-hash",
        validation_status="pass",
    )


def test_materialization_is_independent_idempotent_and_supersedes_history(
    tmp_path: Path,
) -> None:
    retained = json.loads(RETAINED_ARTIFACTS.read_text(encoding="utf-8"))
    summary = retained["summary"]
    ctx = _ctx()

    first = materialize_prompt_family(_request(tmp_path, output=summary), ctx)
    second = materialize_prompt_family(_request(tmp_path, output=summary), ctx)

    assert first.created is True
    assert second.created is False
    assert first.materialization.output_hash == second.materialization.output_hash
    assert Path(first.materialization.output_reference).is_file()

    changed = materialize_prompt_family(
        _request(tmp_path, output={**summary, "_materialization_test": "changed"}),
        ctx,
    )

    assert changed.created is True
    assert (
        changed.materialization.superseded_materialization_reference
        == first.materialization.artifact_id
    )
    trace = trace_artifact_lineage(
        ArtifactLineageTraceRequest(
            schema_version="1.0",
            db_path=str(tmp_path / "reports.sqlite"),
            artifact_id=changed.materialization.artifact_id,
        ),
        ctx,
    )
    assert trace.records[0].state == "active"
    assert trace.records[0].metadata["evidence_set_hash"] == "evidence-hash"
    assert trace.records[0].compatibility["validator_versions"] == {
        "report_vs/artifacts/summary": "validation-v1"
    }
    assert trace.records[0].metadata["prompt_content_hash"] == "prompt-content-hash"
    assert trace.records[0].metadata["execution_identity"] == "execution-identity-hash"


def test_materialization_rejects_dependency_without_verified_hash(
    tmp_path: Path,
) -> None:
    retained = json.loads(RETAINED_ARTIFACTS.read_text(encoding="utf-8"))

    with pytest.raises(
        AppError, match="Every direct prompt-family dependency requires a verified hash"
    ):
        materialize_prompt_family(
            _request(
                tmp_path,
                output=retained["summary"],
                dependencies=["art_upstream"],
            ),
            _ctx(),
        )


def test_reusable_materialization_returns_hash_verified_output(tmp_path: Path) -> None:
    retained = json.loads(RETAINED_ARTIFACTS.read_text(encoding="utf-8"))
    request = _request(tmp_path, output=retained["summary"])
    materialize_prompt_family(request, _ctx())

    reused = read_reusable_prompt_family(
        PromptFamilyReuseRequest(
            schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
            db_path=request.db_path,
            output_dir=request.output_dir,
            report_id=request.report_id,
            report_slug=request.report_slug,
            source_id=request.source_id,
            family_id=request.family_id,
            family_schema_version=request.family_schema_version,
            processing_version=request.processing_version,
            prompt_content_hash=request.prompt_content_hash,
            execution_identity=request.execution_identity,
            model_provider="openai",
            model_name=request.model_name,
            model_policy_namespace="report_vs",
            routing_policy_version=request.routing_policy_version,
            validator_version=request.validator_version,
            relevant_input_hash="input-hash",
            configuration_policy_hash="configuration-policy-hash",
        ),
        _ctx(),
    )

    assert reused.reusable is True
    assert reused.output_payload == retained["summary"]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"prompt_content_hash": "changed-prompt"}, "prompt_version_changed"),
        ({"family_schema_version": "4.0"}, "schema_or_processing_changed"),
        ({"execution_identity": "changed-execution"}, "model_policy_changed"),
        ({"relevant_input_hash": "changed-input"}, "input_hash_changed"),
        (
            {"configuration_policy_hash": "changed-config"},
            "configuration_policy_changed",
        ),
    ],
)
def test_reuse_rejects_changed_family_compatibility(
    tmp_path: Path, changes: dict[str, str], reason: str
) -> None:
    retained = json.loads(RETAINED_ARTIFACTS.read_text(encoding="utf-8"))
    materialization = _request(tmp_path, output=retained["summary"])
    materialize_prompt_family(materialization, _ctx())
    request = PromptFamilyReuseRequest(
        schema_version="1.0",
        db_path=materialization.db_path,
        output_dir=materialization.output_dir,
        report_id=materialization.report_id,
        report_slug=materialization.report_slug,
        source_id=materialization.source_id,
        family_id=materialization.family_id,
        family_schema_version=materialization.family_schema_version,
        processing_version=materialization.processing_version,
        prompt_content_hash=materialization.prompt_content_hash,
        execution_identity=materialization.execution_identity,
        model_provider=materialization.model_provider,
        model_name=materialization.model_name,
        model_policy_namespace=materialization.model_policy_namespace,
        routing_policy_version=materialization.routing_policy_version,
        validator_version=materialization.validator_version,
        relevant_input_hash=materialization.relevant_input_hash,
        configuration_policy_hash=materialization.configuration_policy_hash,
    )

    response = read_reusable_prompt_family(replace(request, **changes), _ctx())

    assert response.reusable is False
    assert response.reason == reason


def test_reuse_rejects_missing_provenance_and_invalid_retained_output(
    tmp_path: Path,
) -> None:
    retained = json.loads(RETAINED_ARTIFACTS.read_text(encoding="utf-8"))
    complete = _request(tmp_path, output=retained["summary"])
    response = materialize_prompt_family(complete, _ctx())
    request = PromptFamilyReuseRequest(
        schema_version="1.0",
        db_path=complete.db_path,
        output_dir=complete.output_dir,
        report_id=complete.report_id,
        report_slug=complete.report_slug,
        source_id=complete.source_id,
        family_id=complete.family_id,
        family_schema_version=complete.family_schema_version,
        processing_version=complete.processing_version,
        prompt_content_hash=complete.prompt_content_hash,
        execution_identity=complete.execution_identity,
        model_provider=complete.model_provider,
        model_name=complete.model_name,
        model_policy_namespace=complete.model_policy_namespace,
        routing_policy_version=complete.routing_policy_version,
        validator_version=complete.validator_version,
        relevant_input_hash=complete.relevant_input_hash,
        configuration_policy_hash=complete.configuration_policy_hash,
    )
    Path(response.materialization.output_reference).write_text("{}", encoding="utf-8")

    invalid = read_reusable_prompt_family(request, _ctx())

    assert invalid.reusable is False
    assert invalid.reason == "output_hash_mismatch"


def test_recovery_output_without_primary_provenance_is_not_reusable(
    tmp_path: Path,
) -> None:
    """Recovered output cannot inherit compatibility from the primary prompt."""
    retained = json.loads(RETAINED_ARTIFACTS.read_text(encoding="utf-8"))
    recovered = replace(
        _request(tmp_path, output=retained["summary"]),
        # Checkpoint persistence deliberately removes this proof whenever
        # structured-output repair or regeneration was required.
        relevant_input_hash="",
    )
    materialize_prompt_family(recovered, _ctx())
    primary_request = PromptFamilyReuseRequest(
        schema_version="1.0",
        db_path=recovered.db_path,
        output_dir=recovered.output_dir,
        report_id=recovered.report_id,
        report_slug=recovered.report_slug,
        source_id=recovered.source_id,
        family_id=recovered.family_id,
        family_schema_version=recovered.family_schema_version,
        processing_version=recovered.processing_version,
        prompt_content_hash=recovered.prompt_content_hash,
        execution_identity=recovered.execution_identity,
        model_provider=recovered.model_provider,
        model_name=recovered.model_name,
        model_policy_namespace=recovered.model_policy_namespace,
        routing_policy_version=recovered.routing_policy_version,
        validator_version=recovered.validator_version,
        relevant_input_hash="input-hash",
        configuration_policy_hash=recovered.configuration_policy_hash,
    )

    result = read_reusable_prompt_family(primary_request, _ctx())

    assert result.reusable is False
    assert result.reason == "missing_provenance"
