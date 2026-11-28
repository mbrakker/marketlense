from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.files import PipelineCheckpointWriteRequest, PipelineStageCheckpoint
from src.contracts.ingest import IngestOutcome
from src.contracts.verified_claims import VISUAL_ADMISSION_POLICY_VERSION
from src.generators.verified_claims_canary import VisualAuthorityCanaryConfig
from src.orchestrators._report_generation_orchestrator.checkpoints import (
    _render_checkpoint_payload,
)
from src.orchestrators._report_generation_orchestrator.resume import (
    _resume_from_analysis_checkpoint,
    _resume_from_render_checkpoint,
)
from src.services.file_service import write_pipeline_checkpoint
from src.utils.errors import AppError
from src.utils.verified_facts import build_verified_authority_context
from tests.test_report_checkpoint_lineage_validation import _runtime
from tests.test_report_render_generator import _analysis, _selection, _source
from tests.test_verified_facts_validation_authority import (
    SOURCE_IDENTITY,
    _authority_artifacts,
)


def _write_verified_render_checkpoint(tmp_path: Path, policy_version: str | None):
    base_runtime = _runtime(tmp_path)
    runtime = replace(
        base_runtime,
        ctx=replace(base_runtime.ctx, source_identity_id=SOURCE_IDENTITY),
    )
    source = replace(_source(runtime), runtime=runtime)
    selection = replace(_selection(runtime, source), runtime=runtime, source=source)
    artifacts = _authority_artifacts()
    if policy_version is not None:
        artifacts["_cache"]["visual_authority_canary"]["admission_policy_version"] = (
            policy_version
        )
    authority = build_verified_authority_context(
        artifacts, expected_source_identity=SOURCE_IDENTITY
    )
    analysis = replace(
        _analysis(runtime, source, selection),
        runtime=runtime,
        source=source,
        selection=selection,
        artifacts_payload=artifacts,
        authoritative_evidence_packs=authority.evidence_packs,
        verified_authority_context=authority,
    )
    outcome = IngestOutcome(
        schema_version="1.0",
        file_id=runtime.file.file_id,
        name=runtime.file_name,
        md5=runtime.md5,
        html_path=str(tmp_path / "out" / "report.html"),
        status="processed",
        publish_readiness_status="pass",
    )
    checkpoint = PipelineStageCheckpoint(
        schema_version="1.0",
        pipeline_name="report_generation",
        file_id=runtime.file.file_id,
        report_slug=runtime.report_name,
        stage_name="render_complete",
        stage_status="completed",
        artifact_refs={},
        payload=_render_checkpoint_payload(
            source, selection, analysis, SimpleNamespace(), outcome
        ),
        completed_at_utc="2026-07-13T00:00:00+00:00",
        source_run_id=runtime.ctx.run_id,
        source_task_id=runtime.ctx.task_id,
    )
    write_pipeline_checkpoint(
        PipelineCheckpointWriteRequest(
            schema_version="1.0",
            checkpoint_root=runtime.settings.output_dir,
            checkpoint=checkpoint,
        ),
        runtime.ctx,
    )
    write_pipeline_checkpoint(
        PipelineCheckpointWriteRequest(
            schema_version="1.0",
            checkpoint_root=runtime.settings.output_dir,
            checkpoint=replace(checkpoint, stage_name="analysis_complete"),
        ),
        runtime.ctx,
    )
    return runtime, outcome


def test_verified_render_reentry_reads_sibling_source_and_selection_payloads(
    tmp_path: Path,
) -> None:
    runtime, outcome = _write_verified_render_checkpoint(
        tmp_path, VISUAL_ADMISSION_POLICY_VERSION
    )

    restored = _resume_from_render_checkpoint(
        runtime,
        visual_authority_canary=VisualAuthorityCanaryConfig(
            source_identity=SOURCE_IDENTITY
        ),
    )

    assert restored == outcome


def test_verified_analysis_reentry_accepts_current_admission_policy(
    tmp_path: Path,
) -> None:
    runtime, _ = _write_verified_render_checkpoint(
        tmp_path, VISUAL_ADMISSION_POLICY_VERSION
    )

    outcome = _resume_from_analysis_checkpoint(
        runtime,
        None,
        None,
        stop_after_stage="analysis_complete",
        visual_authority_canary=VisualAuthorityCanaryConfig(
            source_identity=SOURCE_IDENTITY
        ),
    )

    assert outcome.file_id == runtime.file.file_id


@pytest.mark.parametrize(
    "policy_version",
    [
        None,
        "source-reading-v0",
        "source-reading-v1",
        "source-reading-v2",
        "source-comparison-v1",
    ],
)
def test_verified_analysis_reentry_rejects_missing_or_outdated_admission_policy(
    tmp_path: Path, policy_version: str | None
) -> None:
    runtime, _ = _write_verified_render_checkpoint(tmp_path, policy_version)

    with pytest.raises(AppError):
        _resume_from_analysis_checkpoint(
            runtime,
            None,
            None,
            stop_after_stage="analysis_complete",
            visual_authority_canary=VisualAuthorityCanaryConfig(
                source_identity=SOURCE_IDENTITY
            ),
        )


@pytest.mark.parametrize(
    "policy_version",
    [
        None,
        "source-reading-v0",
        "source-reading-v1",
        "source-reading-v2",
        "source-comparison-v1",
    ],
)
def test_verified_render_reentry_rejects_missing_or_outdated_admission_policy(
    tmp_path: Path, policy_version: str | None
) -> None:
    runtime, _ = _write_verified_render_checkpoint(tmp_path, policy_version)

    with pytest.raises(AppError):
        _resume_from_render_checkpoint(
            runtime,
            visual_authority_canary=VisualAuthorityCanaryConfig(
                source_identity=SOURCE_IDENTITY
            ),
        )


def test_historical_authority_snapshot_without_admission_policy_remains_readable() -> (
    None
):
    artifacts = _authority_artifacts()
    original = deepcopy(artifacts)

    authority = build_verified_authority_context(
        artifacts, expected_source_identity=SOURCE_IDENTITY
    )

    assert authority.source_identity == SOURCE_IDENTITY
    assert artifacts == original
