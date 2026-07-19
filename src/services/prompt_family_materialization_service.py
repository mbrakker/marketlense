"""Canonical persistence boundary for independent prompt-family outputs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from src.contracts.artifact_lineage import (
    ARTIFACT_LINEAGE_SCHEMA_VERSION,
    ArtifactLineageRegistrationRequest,
    ArtifactLineageStorageLookupRequest,
)
from src.contracts.prompt_family_materialization import (
    PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
    PromptFamilyMaterialization,
    PromptFamilyMaterializationRequest,
    PromptFamilyMaterializationResponse,
)
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import ReportId
from src.services import report_analysis_store_service
from src.services.report_store_service import (
    get_artifact_lineage_for_storage,
    record_artifact_lineage,
)
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.slugify import slugify


def _require_token(value: str, name: str) -> str:
    normalized = str(value or "").strip()
    if normalized:
        return normalized
    raise AppError(
        code="prompt_family_materialization_request_invalid",
        message="Prompt-family materialization requires its identifying provenance",
        retryable=False,
        context={"missing": name},
    )


def _pack_name(family_id: str) -> str:
    # The analysis-store service accepts one safe file-name segment.  The
    # full family ID stays in the payload and lineage metadata.
    return "prompt_family_" + slugify(family_id).replace("-", "_")


def _serialized_payload(
    request: PromptFamilyMaterializationRequest,
) -> dict[str, object]:
    return {
        "schema_version": PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
        "family_id": request.family_id,
        "family_schema_version": request.family_schema_version,
        "processing_version": request.processing_version,
        "output": request.output_payload,
    }


def _new_output_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    ).hexdigest()


def materialize_prompt_family(
    request: PromptFamilyMaterializationRequest, ctx: RunContext
) -> PromptFamilyMaterializationResponse:
    """Write one family output then register it in the existing lineage store.

    The retained JSON may contain approved report output, but emitted events
    contain only IDs, hashes, booleans, and counts.
    """
    report_id = _require_token(request.report_id, "report_id")
    source_id = _require_token(request.source_id, "source_id")
    family_id = _require_token(request.family_id, "family_id")
    family_schema_version = _require_token(
        request.family_schema_version, "family_schema_version"
    )
    processing_version = _require_token(
        request.processing_version, "processing_version"
    )
    if not request.db_path.strip() or not request.output_dir.strip():
        raise AppError(
            code="prompt_family_materialization_request_invalid",
            message=(
                "Prompt-family materialization requires report-store and output paths"
            ),
            retryable=False,
        )
    dependencies = sorted(
        {
            str(value).strip()
            for value in request.direct_dependency_artifact_ids
            if str(value).strip()
        }
    )
    dependency_hashes = {
        artifact_id: str(
            request.direct_dependency_hashes.get(artifact_id) or ""
        ).strip()
        for artifact_id in dependencies
    }
    if any(not digest for digest in dependency_hashes.values()):
        raise AppError(
            code="prompt_family_materialization_dependency_hash_missing",
            message="Every direct prompt-family dependency requires a verified hash",
            retryable=False,
            context={"dependency_count": len(dependencies)},
        )

    output_payload = _serialized_payload(request)
    output_hash = _new_output_hash(output_payload)
    artifact_kind = f"prompt_family:{family_id}"
    pack_name = _pack_name(family_id)
    output_reference = report_analysis_store_service.pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=request.output_dir,
            report_id=ReportId(report_id),
            pack_name=pack_name,
            report_slug=request.report_slug or report_id,
        ),
        ctx,
    ).output_path
    prior = get_artifact_lineage_for_storage(
        ArtifactLineageStorageLookupRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=request.db_path,
            report_id=report_id,
            artifact_kind=artifact_kind,
            storage_ref=output_reference,
        ),
        ctx,
    ).record
    previous_hash = ""
    path = Path(output_reference)
    if path.is_file():
        previous_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    superseded_reference = (
        prior.artifact_id if prior is not None and previous_hash != output_hash else ""
    )
    report_analysis_store_service.store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=request.output_dir,
            report_id=ReportId(report_id),
            pack_name=pack_name,
            payload=output_payload,
            report_slug=request.report_slug or report_id,
        ),
        ctx,
    )
    legacy_prompt_hash = sha256_json(
        {
            "system": request.system_prompt_hash,
            "user": request.user_prompt_hash,
            "policy": request.prompt_policy_version,
        }
    )
    prompt_content_hash = str(request.prompt_content_hash or "").strip()
    execution_identity = str(request.execution_identity or "").strip()
    prompt_hash = prompt_content_hash or legacy_prompt_hash
    response = record_artifact_lineage(
        ArtifactLineageRegistrationRequest(
            schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
            db_path=request.db_path,
            artifact_kind=artifact_kind,
            report_id=report_id,
            source_id=source_id,
            storage_ref=output_reference,
            producer="prompt_family_materialization",
            schema_version_used=family_schema_version,
            processing_version=processing_version,
            dependency_artifact_ids=dependencies,
            content_hash=output_hash,
            prompt_hash=prompt_hash,
            model_name=request.model_name,
            validation_status=request.validation_status,
            metadata={
                "family_id": family_id,
                "system_prompt_hash": request.system_prompt_hash,
                "user_prompt_hash": request.user_prompt_hash,
                "prompt_content_hash": prompt_content_hash,
                "prompt_dependency_manifest": dict(
                    request.prompt_dependency_manifest or {}
                ),
                "execution_identity": execution_identity,
                "execution_identity_manifest": dict(
                    request.execution_identity_manifest or {}
                ),
                "identity_status": (
                    "current" if prompt_content_hash and execution_identity else "legacy"
                ),
                "prompt_policy_version": request.prompt_policy_version,
                "routing_policy_version": request.routing_policy_version,
                "validator_version": request.validator_version,
                "evidence_set_hash": request.evidence_set_hash,
                "dependency_hashes": dependency_hashes,
                "superseded_materialization_reference": superseded_reference,
            },
            compatibility={
                "artifact_family": family_id,
                "schema_versions": {family_id: family_schema_version},
                "processing_versions": {family_id: processing_version},
                "prompt_versions": {
                    family_id: prompt_content_hash or request.prompt_policy_version
                },
                "execution_identities": {family_id: execution_identity},
                "model_policy_versions": {family_id: request.routing_policy_version},
                "validator_versions": {family_id: request.validator_version},
            },
            lineage_status="complete",
        ),
        ctx,
    )
    materialization = PromptFamilyMaterialization(
        schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
        family_id=family_id,
        family_schema_version=family_schema_version,
        processing_version=processing_version,
        system_prompt_hash=request.system_prompt_hash,
        user_prompt_hash=request.user_prompt_hash,
        prompt_content_hash=prompt_content_hash,
        prompt_dependency_manifest=dict(request.prompt_dependency_manifest or {}),
        execution_identity=execution_identity,
        execution_identity_manifest=dict(request.execution_identity_manifest or {}),
        prompt_policy_version=request.prompt_policy_version,
        model_name=request.model_name,
        routing_policy_version=request.routing_policy_version,
        validator_version=request.validator_version,
        direct_dependency_artifact_ids=dependencies,
        direct_dependency_hashes=dependency_hashes,
        evidence_set_hash=request.evidence_set_hash,
        output_reference=response.record.storage_ref,
        output_hash=response.record.content_hash,
        validation_status=request.validation_status,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        superseded_materialization_reference=superseded_reference,
        artifact_id=response.record.artifact_id,
    )
    log_event_payload = {
        "report_id": report_id,
        "family_id": family_id,
        "artifact_id": response.record.artifact_id,
        "dependency_count": len(dependencies),
        "validation_status": request.validation_status,
        "created": response.created,
        "superseded": bool(superseded_reference),
    }
    # Keep this module usable without a private logging singleton while still
    # emitting the canonical bounded structured event.
    import logging

    logging.getLogger("market_lense.prompt_family_materialization").info(
        log_event(
            ctx,
            role="service",
            event="prompt_family_materialized",
            module="market_lense.prompt_family_materialization",
            fields=log_event_payload,
        )
    )
    if not prompt_content_hash or not execution_identity:
        logging.getLogger("market_lense.prompt_family_materialization").info(
            log_event(
                ctx,
                role="service",
                event="legacy_identity_read",
                module="market_lense.prompt_family_materialization",
                fields={
                    "report_id": report_id,
                    "family_id": family_id,
                    "artifact_id": response.record.artifact_id,
                },
            )
        )
    return PromptFamilyMaterializationResponse(
        schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
        materialization=materialization,
        created=response.created,
    )


__all__ = ["materialize_prompt_family"]
