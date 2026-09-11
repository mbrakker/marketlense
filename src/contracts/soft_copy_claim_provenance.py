"""Typed private provenance for sentence-level public soft-copy claims."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.utils.errors import AppError

SOFT_COPY_CLAIM_PROVENANCE_SCHEMA_VERSION = "1.0"
SoftCopyClaimClassification = Literal["factual", "interpretive", "recommendation"]
_CLASSIFICATIONS = frozenset({"factual", "interpretive", "recommendation"})


@dataclass(frozen=True)
class SoftCopyClaimProvenance:
    """Private source and production provenance for one material soft-copy claim."""

    schema_version: str = field(
        metadata={"doc": "Soft-copy claim provenance schema version."}
    )
    artifact_family: str = field(
        metadata={"doc": "Public artifact family containing the claim."}
    )
    claim_id: str = field(
        metadata={"doc": "Stable content-addressed claim identifier within its family."}
    )
    text_hash: str = field(metadata={"doc": "SHA-256 of the public claim text."})
    classification: SoftCopyClaimClassification = field(
        metadata={"doc": "Claim type: factual, interpretive, or recommendation."}
    )
    evidence_ids: tuple[str, ...] = field(
        metadata={"doc": "Explicit model-declared canonical evidence IDs."}
    )
    source_spans: tuple[dict[str, Any], ...] = field(
        metadata={"doc": "Known canonical evidence pages and offsets."}
    )
    producing_prompt_identity: dict[str, Any] = field(
        metadata={"doc": "Retained prompt namespace and content identity."}
    )
    generation_attempt: int = field(
        metadata={"doc": "Structured-output generation attempt that produced the claim."}
    )
    regeneration_attempt: int = field(
        metadata={"doc": "Targeted regeneration pass; zero for initial generation."}
    )

    def validate(self) -> "SoftCopyClaimProvenance":
        if not str(self.artifact_family).strip() or not str(self.claim_id).strip():
            raise AppError(
                code="soft_copy_claim_provenance_invalid",
                message="Soft-copy claim provenance requires artifact family and claim ID",
                retryable=False,
            )
        if len(str(self.text_hash).strip()) != 64:
            raise AppError(
                code="soft_copy_claim_provenance_invalid",
                message="Soft-copy claim provenance requires a SHA-256 text hash",
                retryable=False,
            )
        if self.classification not in _CLASSIFICATIONS:
            raise AppError(
                code="soft_copy_claim_provenance_invalid",
                message="Soft-copy claim provenance has an invalid classification",
                retryable=False,
            )
        if self.generation_attempt < 1 or self.regeneration_attempt < 0:
            raise AppError(
                code="soft_copy_claim_provenance_invalid",
                message="Soft-copy claim provenance has an invalid generation attempt",
                retryable=False,
            )
        return self


def soft_copy_claim_provenance_to_payload(
    claims: list[SoftCopyClaimProvenance],
) -> dict[str, Any]:
    """Serialize private claim provenance for the retained artifacts payload."""

    return {
        "schema_version": SOFT_COPY_CLAIM_PROVENANCE_SCHEMA_VERSION,
        "claims": [
            {
                "schema_version": claim.schema_version,
                "artifact_family": claim.artifact_family,
                "claim_id": claim.claim_id,
                "text_hash": claim.text_hash,
                "classification": claim.classification,
                "evidence_ids": list(claim.evidence_ids),
                "source_spans": [dict(span) for span in claim.source_spans],
                "producing_prompt_identity": dict(claim.producing_prompt_identity),
                "generation_attempt": claim.generation_attempt,
                "regeneration_attempt": claim.regeneration_attempt,
            }
            for claim in (item.validate() for item in claims)
        ],
    }


def soft_copy_claim_provenance_from_payload(
    payload: object,
) -> list[SoftCopyClaimProvenance]:
    """Deserialize retained private provenance without reconstructing evidence."""

    if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
        raise AppError(
            code="soft_copy_claim_provenance_invalid",
            message="Soft-copy claim provenance payload requires a claims list",
            retryable=False,
        )
    claims: list[SoftCopyClaimProvenance] = []
    for raw in payload["claims"]:
        if not isinstance(raw, dict):
            raise AppError(
                code="soft_copy_claim_provenance_invalid",
                message="Soft-copy claim provenance entry must be an object",
                retryable=False,
            )
        raw_prompt_identity = raw.get("producing_prompt_identity")
        prompt_identity = (
            dict(raw_prompt_identity)
            if isinstance(raw_prompt_identity, dict)
            else {}
        )
        claims.append(
            SoftCopyClaimProvenance(
                schema_version=str(raw.get("schema_version") or "").strip(),
                artifact_family=str(raw.get("artifact_family") or "").strip(),
                claim_id=str(raw.get("claim_id") or "").strip(),
                text_hash=str(raw.get("text_hash") or "").strip(),
                classification=str(raw.get("classification") or ""),  # type: ignore[arg-type]
                evidence_ids=tuple(
                    str(value).strip()
                    for value in raw.get("evidence_ids") or []
                    if str(value).strip()
                ),
                source_spans=tuple(
                    dict(span)
                    for span in raw.get("source_spans") or []
                    if isinstance(span, dict)
                ),
                producing_prompt_identity=prompt_identity,
                generation_attempt=int(raw.get("generation_attempt") or 0),
                regeneration_attempt=int(raw.get("regeneration_attempt") or 0),
            ).validate()
        )
    return claims
