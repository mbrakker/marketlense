from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.report_analysis import (
    AnalysisGenerationCommitRequest,
    AnalysisGenerationReadRequest,
)
from src.contracts.workflow_queue import (
    PublicationReadinessPayload,
    WordPressPublishPayload,
    WorkflowJobSubmission,
)
from src.generators.publish_readiness_generator import (
    parse_publish_readiness_payload,
    publish_readiness_payload,
)
from src.orchestrators import workflow_queue_orchestrator
from src.orchestrators._publish_orchestrator.routing import (
    create_report_publication_package,
)
from src.services import report_analysis_store_service
from src.services.workflow_queue_service import approve_publication_package
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from tests._test_report_analysis_generator._shared import _runtime
from tests.test_autonomous_publication_approval import (
    _artifact_signature,
    _ready_report,
)
from tests.test_promotion_process_recovery import _promotion_worker
from tests.test_workflow_queue_registry import _ctx, _isolated_app_config, _workflow_job


def test_generation_package_reaches_publication_readiness(tmp_path_factory) -> None:
    tmp_path = tmp_path_factory.mktemp("pkg")
    config_path = _isolated_app_config(tmp_path)
    old = _ready_report(tmp_path, config_path)
    _promotion_worker(tmp_path / "source", "never", include_evidence=True)
    runtime = _runtime(tmp_path / "source")
    source = report_analysis_store_service.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    generation = report_analysis_store_service.commit_generation(
        AnalysisGenerationCommitRequest(
            schema_version="1.0",
            output_dir=str(tmp_path / "generated"),
            report_id="report-1",
            report_slug="report",
            packs=source.packs,
        ),
        _ctx(),
    )
    readiness_path = Path(old.validation_reference)
    artifact = parse_publish_readiness_payload(
        json.loads(readiness_path.read_text(encoding="utf-8"))
    )
    artifact = replace(
        artifact,
        artifact_hashes={
            name: sha256_json(generation.packs[name])
            for name in ("artifacts", "validation")
        }
        | {"evidence:findings": sha256_json({"findings": []})},
        artifact_hash="",
    )
    artifact = replace(artifact, artifact_hash=_artifact_signature(artifact))
    readiness_path.write_text(
        json.dumps(publish_readiness_payload(artifact)), encoding="utf-8"
    )
    package = create_report_publication_package(
        html_path=old.entity_package_reference,
        readiness_reference=str(readiness_path),
        output_dir=str(tmp_path / "generated"),
        report_id="report-1",
        report_slug="report",
        pack_paths=generation.pack_paths,
        ctx=_ctx(),
    )
    payload = PublicationReadinessPayload(
        entity_type="report",
        entity_package_reference=package.html_path,
        package_checksum=package.checksum,
        validation_reference=package.manifest_path,
        lineage_reference="retained:source",
        required_asset_status="ready",
        attributes={"config_path": str(config_path)},
    )
    result = workflow_queue_orchestrator._publication_readiness_handler(
        _workflow_job(
            queue_name="publication_readiness", job_type="publication_readiness.v1"
        ),
        payload,
        _ctx(),
    )
    assert result.result.summary["readiness_status"] == "awaiting_review"
    publish = WordPressPublishPayload(
        entity_type="report",
        entity_package_reference=package.html_path,
        package_checksum=package.checksum,
        readiness_reference=package.manifest_path,
        attributes={"config_path": str(config_path)},
        dry_run=True,
    )
    approval = approve_publication_package(
        str(tmp_path / "state.sqlite"),
        package_checksum=package.checksum,
        actor_id="reviewer",
        note="Generation test",
        publish_submission=WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="wordpress_publish",
            job_type="wordpress_publish.v1",
            payload=publish,
            idempotency_key="generation-package-test",
            deduplication_scope="validated-publication-package",
        ),
        ctx=_ctx(),
    )
    approved = replace(publish, approval_id=approval.approval_id)
    job = _workflow_job(queue_name="wordpress_publish", job_type="wordpress_publish.v1")
    completed = workflow_queue_orchestrator._wordpress_publish_handler(
        job, approved, _ctx()
    )
    assert completed.result.summary["publication_status"] == "dry_run"
    Path(package.readiness_path).write_text("tampered", encoding="utf-8")
    with pytest.raises(AppError):
        workflow_queue_orchestrator._wordpress_publish_handler(job, approved, _ctx())
