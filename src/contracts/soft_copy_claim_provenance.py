"""Typed private provenance for sentence-level public soft-copy claims."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from src.utils.errors import AppError

SOFT_COPY_CLAIM_PROVENANCE_SCHEMA_VERSION = "1.0"
SOFT_COPY_PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION = "1.0"
SoftCopyClaimClassification = Literal["factual", "interpretive", "recommendation"]
_CLASSIFICATIONS = frozenset({"factual", "interpretive", "recommendation"})
_PROMPT_FAMILY_TO_ARTIFACT_FAMILY = {
    "report_vs/artifacts/summary": "summary",
    "report_vs/artifacts/expert_comment": "expert_comment",
    "report_vs/artifacts/linkedin_post": "linkedin_post",
}


@dataclass(frozen=True)
class SoftCopyPromptFamilyMaterialization:
    """Private retained representation for reusable material soft-copy."""

    schema_version: str = field(
        metadata={"doc": "Soft-copy prompt-family materialization schema version."}
    )
    public_output: Any = field(
        metadata={"doc": "The original public family output retained for reuse."}
    )
    claim_provenance: list[dict[str, Any]] = field(
        metadata={"doc": "Model-declared claim text, classification, and evidence IDs."}
    )
    producing_prompt_identity: dict[str, Any] = field(
        metadata={"doc": "Verified materialization identity that produced this output."}
    )
    generation_attempt: int = field(
        metadata={"doc": "Original structured-output attempt number."}
    )

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "public_output": self.public_output,
            "claim_provenance": [
                dict(binding)
                for binding in self.claim_provenance
                if isinstance(binding, dict)
            ],
            "producing_prompt_identity": dict(self.producing_prompt_identity),
            "generation_attempt": self.generation_attempt,
        }


def soft_copy_artifact_family_for_prompt_family(family_id: str) -> str:
    """Return the soft-copy artifact family for a prompt family, if any."""
    return _PROMPT_FAMILY_TO_ARTIFACT_FAMILY.get(str(family_id or "").strip(), "")


def soft_copy_public_text(artifact_family: str, public_output: object) -> str:
    """Return material public prose without reconstructing provenance from it."""
    family = str(artifact_family or "").strip()
    values: tuple[object, ...]
    if family == "summary" and isinstance(public_output, dict):
        values = (
            public_output.get("tldr"),
            public_output.get("card_tldr_compact"),
            public_output.get("executive_summary"),
        )
    elif family in {"expert_comment", "linkedin_post"}:
        values = (public_output,)
    else:
        values = ()
    return " ".join(
        " ".join(str(value or "").split())
        for value in values
        if str(value or "").strip()
    )


def soft_copy_prompt_family_materialization_from_payload(
    payload: object,
) -> SoftCopyPromptFamilyMaterialization | None:
    """Read the private reuse envelope, returning ``None`` for legacy output."""
    if not isinstance(payload, dict):
        return None
    required = {
        "schema_version",
        "public_output",
        "claim_provenance",
        "producing_prompt_identity",
        "generation_attempt",
    }
    if not required.issubset(payload):
        return None
    bindings = payload.get("claim_provenance")
    identity = payload.get("producing_prompt_identity")
    if not isinstance(bindings, list) or not isinstance(identity, dict):
        return None
    try:
        attempt = int(payload.get("generation_attempt") or 0)
    except (TypeError, ValueError):
        return None
    if (
        str(payload.get("schema_version") or "").strip()
        != SOFT_COPY_PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION
        or attempt < 1
    ):
        return None
    return SoftCopyPromptFamilyMaterialization(
        schema_version=SOFT_COPY_PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
        public_output=payload.get("public_output"),
        claim_provenance=[
            dict(binding) for binding in bindings if isinstance(binding, dict)
        ],
        producing_prompt_identity=dict(identity),
        generation_attempt=attempt,
    )


def soft_copy_claim_bindings_cover_public_text(
    *, artifact_family: str, public_output: object, claim_bindings: object
) -> bool:
    """Check that retained model bindings declare each material public sentence."""
    text = soft_copy_public_text(artifact_family, public_output)
    if not text:
        return True
    if not isinstance(claim_bindings, list) or not claim_bindings:
        return False
    declared = {
        " ".join(str(binding.get("claim") or "").split())
        for binding in claim_bindings
        if isinstance(binding, dict) and str(binding.get("claim") or "").strip()
    }
    sentences = [
        " ".join(sentence.split())
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if " ".join(sentence.split())
    ]
    return bool(declared) and all(sentence in declared for sentence in sentences)


def valid_soft_copy_evidence_selection(
    key: str,
    value: object,
    *,
    require_selected_evidence_entries: bool = False,
) -> bool:
    """Validate the private Prompt 5 claim-evidence selection record.

    ``repaired_claim_id`` is later repair-lineage metadata, so it deliberately
    stays outside the Prompt 5 package hash.  Earlier retained Prompt 5
    records may omit selected evidence content; only claim-scoped replacement
    validation requires that complete hashed package.
    """

    if not isinstance(value, dict):
        return False
    required_keys = {
        "schema_version",
        "claim_id",
        "strategy",
        "direct_evidence_ids",
        "parent_evidence_ids",
        "quarantined_evidence_ids",
        "selected_evidence_ids",
        "package_sha256",
    }
    allowed_keys = required_keys | {"selected_evidence_entries", "repaired_claim_id"}
    if set(value) - allowed_keys or not required_keys.issubset(value):
        return False
    if (
        value.get("schema_version") != "1.0"
        or not isinstance(value.get("claim_id"), str)
        or not value["claim_id"]
        or not key.endswith(value["claim_id"])
        or value.get("strategy")
        not in {
            "claim_evidence_ids",
            "parent_insight_or_theme",
            "lexical_fallback",
            "abstain",
        }
        or not isinstance(value.get("package_sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", value["package_sha256"])
    ):
        return False
    for field_name in (
        "direct_evidence_ids",
        "parent_evidence_ids",
        "quarantined_evidence_ids",
        "selected_evidence_ids",
    ):
        if not isinstance(value.get(field_name), list) or not all(
            isinstance(item, str) for item in value[field_name]
        ):
            return False
    if "repaired_claim_id" in value and (
        not isinstance(value["repaired_claim_id"], str)
        or not value["repaired_claim_id"]
    ):
        return False
    entries = value.get("selected_evidence_entries")
    if entries is None:
        return not require_selected_evidence_entries
    if not isinstance(entries, list) or not all(
        isinstance(entry, dict) for entry in entries
    ):
        return False
    hash_payload = {
        name: item
        for name, item in value.items()
        if name not in {"package_sha256", "repaired_claim_id"}
    }
    canonical_json = json.dumps(
        hash_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return (
        value["package_sha256"]
        == hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    )


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
        metadata={
            "doc": "Structured-output generation attempt that produced the claim."
        }
    )
    regeneration_attempt: int = field(
        metadata={"doc": "Targeted regeneration pass; zero for initial generation."}
    )
    repaired_from_claim_id: str = field(
        default="",
        metadata={
            "doc": "Original claim ID replaced by this regenerated claim, if any."
        },
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

    payload = {
        "schema_version": SOFT_COPY_CLAIM_PROVENANCE_SCHEMA_VERSION,
        "claims": [
            _soft_copy_claim_to_payload(claim)
            for claim in (item.validate() for item in claims)
        ],
    }
    return payload


def _soft_copy_claim_to_payload(claim: SoftCopyClaimProvenance) -> dict[str, Any]:
    payload = {
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
    if claim.repaired_from_claim_id:
        payload["repaired_from_claim_id"] = claim.repaired_from_claim_id
    return payload


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
            dict(raw_prompt_identity) if isinstance(raw_prompt_identity, dict) else {}
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
                repaired_from_claim_id=str(
                    raw.get("repaired_from_claim_id") or ""
                ).strip(),
            ).validate()
        )
    return claims
