from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.utils.errors import AppError


@dataclass(frozen=True)
class ArtifactRef:
    schema_version: str = field(metadata={"doc": "Artifact reference schema version."})
    artifact_id: str = field(
        metadata={"doc": "Stable artifact identifier used by checkpoints."}
    )
    kind: str = field(metadata={"doc": "Artifact kind, for example source_pdf."})
    path: str = field(metadata={"doc": "Filesystem path for the artifact."})
    content_hash: str = field(
        metadata={"doc": "Content hash recorded when the artifact is available."}
    )
    producer_step: str = field(
        metadata={
            "doc": "Pipeline step that produced or first referenced the artifact."
        }
    )
    required: bool = field(
        metadata={"doc": "Whether the artifact must exist for resume/publish safety."}
    )
    created_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the artifact reference was recorded."}
    )


@dataclass(frozen=True)
class ArtifactRegistry:
    schema_version: str = field(
        metadata={"doc": "Cross-step artifact registry schema version."}
    )
    refs: list[ArtifactRef] = field(
        metadata={"doc": "Typed artifact references keyed by artifact_id."}
    )

    def validate(self) -> "ArtifactRegistry":
        seen: set[str] = set()
        for ref in self.refs:
            artifact_id = str(ref.artifact_id or "").strip()
            if not artifact_id:
                raise AppError(
                    code="artifact_registry_invalid",
                    message="Artifact registry entry is missing artifact_id",
                    retryable=False,
                )
            if artifact_id in seen:
                raise AppError(
                    code="artifact_registry_duplicate_id",
                    message="Artifact registry contains duplicate artifact IDs",
                    retryable=False,
                    context={"artifact_id": artifact_id},
                )
            seen.add(artifact_id)
            if ref.required and not str(ref.path or "").strip():
                raise AppError(
                    code="artifact_registry_required_path_missing",
                    message="Required artifact registry entry is missing a path",
                    retryable=False,
                    context={"artifact_id": artifact_id},
                )
        return self


def artifact_registry_from_payload(payload: object) -> ArtifactRegistry | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise AppError(
            code="artifact_registry_invalid",
            message="Artifact registry payload must be an object",
            retryable=False,
        )
    raw_refs = payload.get("refs")
    if not isinstance(raw_refs, list):
        raise AppError(
            code="artifact_registry_invalid",
            message="Artifact registry payload must contain a refs list",
            retryable=False,
        )
    refs: list[ArtifactRef] = []
    for raw_ref in raw_refs:
        if not isinstance(raw_ref, dict):
            raise AppError(
                code="artifact_registry_invalid",
                message="Artifact registry ref must be an object",
                retryable=False,
            )
        refs.append(
            ArtifactRef(
                schema_version=str(raw_ref.get("schema_version") or "1.0"),
                artifact_id=str(raw_ref.get("artifact_id") or "").strip(),
                kind=str(raw_ref.get("kind") or "").strip(),
                path=str(raw_ref.get("path") or "").strip(),
                content_hash=str(raw_ref.get("content_hash") or "").strip(),
                producer_step=str(raw_ref.get("producer_step") or "").strip(),
                required=bool(raw_ref.get("required", True)),
                created_at_utc=str(raw_ref.get("created_at_utc") or "").strip(),
            )
        )
    return ArtifactRegistry(
        schema_version=str(payload.get("schema_version") or "1.0"),
        refs=refs,
    ).validate()


def artifact_registry_to_payload(registry: ArtifactRegistry) -> dict[str, Any]:
    registry.validate()
    return {
        "schema_version": registry.schema_version,
        "refs": [
            {
                "schema_version": ref.schema_version,
                "artifact_id": ref.artifact_id,
                "kind": ref.kind,
                "path": ref.path,
                "content_hash": ref.content_hash,
                "producer_step": ref.producer_step,
                "required": ref.required,
                "created_at_utc": ref.created_at_utc,
            }
            for ref in registry.refs
        ],
    }
