from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contracts.artifact_lineage import ArtifactLineageTraceRequest
from src.contracts.prompt_family_materialization import (
    PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
    PromptFamilyMaterializationRequest,
)
from src.contracts.run_context import RunContext
from src.services.prompt_family_materialization_service import materialize_prompt_family
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
        prompt_policy_version="policy-hash",
        model_name="gpt-5-mini",
        routing_policy_version="routing-hash",
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
