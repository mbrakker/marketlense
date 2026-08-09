"""Idempotency helpers for publication orchestration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from typing import List

from src.contracts.artifact_lineage import (
    ARTIFACT_LINEAGE_SCHEMA_VERSION,
    ArtifactLineageStorageLookupRequest,
)
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportPublishPackage,
    CrossReportPublishResultSummary,
)
from src.contracts.idempotency import (
    OrchestratorIdempotencyGetRequest,
    OrchestratorIdempotencyRecordRequest,
)
from src.contracts.publish import (
    PublishOutcome,
    PublishSettings,
)
from src.contracts.run_context import RunContext
from src.contracts.wordpress import WordPressPostReadCheck, WordPressPostReadExpectation
from src.orchestrators._publish_orchestrator.models import (
    _CROSS_REPORT_PUBLISH_IDEMPOTENCY_SCOPE,
    _PUBLISH_IDEMPOTENCY_SCOPE,
)
from src.services import idempotency_service
from src.services.report_store_service import get_artifact_lineage_for_storage


def _publish_idempotency_key(*, file_id: str, post_type: str) -> str:
    return f"{post_type}:{file_id}"


def _publish_checksum(
    *,
    file_id: str,
    html_path: str,
    html_text: str,
    post_type: str,
    validation_status: str,
    validation_issues: List[str],
) -> str:
    html_sha256 = hashlib.sha256((html_text or "").encode("utf-8")).hexdigest()
    payload = {
        "schema_version": "1.0",
        "file_id": file_id,
        "html_path": html_path,
        "html_sha256": html_sha256,
        "post_type": post_type,
        "validation_status": validation_status,
        "validation_issues": list(validation_issues or []),
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _lookup_publish_idempotency(
    *,
    settings: PublishSettings,
    file_id: str,
    post_type: str,
    checksum: str,
    ctx: RunContext,
) -> PublishOutcome | None:
    lookup = idempotency_service.get_outcome(
        OrchestratorIdempotencyGetRequest(
            schema_version="1.0",
            db_path=settings.state_db,
            scope=_PUBLISH_IDEMPOTENCY_SCOPE,
            idempotency_key=_publish_idempotency_key(
                file_id=file_id,
                post_type=post_type,
            ),
            input_checksum=checksum,
        ),
        ctx,
    )
    if not lookup.found or lookup.record is None:
        return None
    payload = dict(lookup.record.outcome_payload or {})
    expectation = payload.get("readback_expectation")
    if isinstance(expectation, dict):
        payload["readback_expectation"] = WordPressPostReadExpectation(**expectation)
    checks = payload.get("readback_checks")
    if isinstance(checks, list):
        payload["readback_checks"] = [
            WordPressPostReadCheck(**check)
            for check in checks
            if isinstance(check, dict)
        ]
    return PublishOutcome(**payload)


def _record_publish_idempotency(
    *,
    settings: PublishSettings,
    outcome: PublishOutcome,
    post_type: str,
    checksum: str,
    ctx: RunContext,
) -> None:
    if not outcome.file_id:
        return
    lineage = get_artifact_lineage_for_storage(
        ArtifactLineageStorageLookupRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=settings.reports_db,
            report_id=outcome.file_id,
            artifact_kind="rendered_html",
            storage_ref=outcome.html_path,
        ),
        ctx,
    )
    idempotency_service.record_outcome(
        OrchestratorIdempotencyRecordRequest(
            schema_version="1.0",
            db_path=settings.state_db,
            scope=_PUBLISH_IDEMPOTENCY_SCOPE,
            idempotency_key=_publish_idempotency_key(
                file_id=outcome.file_id,
                post_type=post_type,
            ),
            input_checksum=checksum,
            outcome_payload=asdict(outcome),
            artifact_references={
                "html_path": outcome.html_path,
                "status": outcome.status,
                "publication_outcome": outcome.publication_outcome,
                "transaction_outcome_count": len(outcome.transaction_outcomes),
                "post_id": outcome.post_id,
                "post_url": outcome.post_url,
                "lineage_artifact_id": (
                    lineage.record.artifact_id if lineage.record is not None else ""
                ),
            },
        ),
        ctx,
    )


def _cross_report_publish_checksum(
    package: CrossReportPublishPackage,
    settings: PublishSettings,
) -> str:
    payload = {
        "schema_version": CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        "selected_theme_id": package.selected_theme_id,
        "selected_report_ids": package.selected_report_ids,
        "artifact_sha256": package.artifact_sha256,
        "validation_sha256": package.validation_sha256,
        "prompt_hashes": package.prompt_hashes,
        "target_route": package.target_route,
        "post_type": settings.wp.post_type,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _cross_report_publish_idempotency_key(
    package: CrossReportPublishPackage,
    checksum: str,
) -> str:
    return f"{package.target_route}:{package.file_id}:{checksum}"


def _record_cross_report_publish_idempotency(
    *,
    package: CrossReportPublishPackage,
    settings: PublishSettings,
    result: CrossReportPublishResultSummary,
    checksum: str,
    ctx: RunContext,
) -> None:
    idempotency_service.record_outcome(
        OrchestratorIdempotencyRecordRequest(
            schema_version="1.0",
            db_path=settings.state_db,
            scope=_CROSS_REPORT_PUBLISH_IDEMPOTENCY_SCOPE,
            idempotency_key=_cross_report_publish_idempotency_key(package, checksum),
            input_checksum=checksum,
            outcome_payload=asdict(result),
            artifact_references={
                "html_path": package.html_path,
                "artifact_path": package.canonical_artifact_path,
                "status": result.status,
                "post_id": result.post_id,
                "post_url": result.post_url,
            },
        ),
        ctx,
    )


def _lookup_cross_report_publish_idempotency(
    *,
    package: CrossReportPublishPackage,
    settings: PublishSettings,
    checksum: str,
    ctx: RunContext,
) -> CrossReportPublishResultSummary | None:
    lookup = idempotency_service.get_outcome(
        OrchestratorIdempotencyGetRequest(
            schema_version="1.0",
            db_path=settings.state_db,
            scope=_CROSS_REPORT_PUBLISH_IDEMPOTENCY_SCOPE,
            idempotency_key=_cross_report_publish_idempotency_key(package, checksum),
            input_checksum=checksum,
        ),
        ctx,
    )
    if not lookup.found or lookup.record is None:
        return None
    return replace(
        CrossReportPublishResultSummary(**dict(lookup.record.outcome_payload or {})),
        idempotency_reused=True,
    )
