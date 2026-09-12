"""Deterministic assembly of private soft-copy claim provenance."""

from __future__ import annotations

import hashlib
from typing import Any

from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_material_sentences,
)
from src.utils.errors import AppError

_SUPPORTED_FAMILIES = frozenset({"summary", "expert_comment", "linkedin_post"})
_CLASSIFICATIONS = frozenset({"factual", "interpretive", "recommendation"})


def build_soft_copy_claim_provenance(
    *,
    artifact_family: str,
    text: str,
    declared_claims: object,
    evidence_span_index: dict[str, list[dict[str, Any]]],
    producing_prompt_identity: dict[str, Any],
    generation_attempt: int,
    regeneration_attempt: int,
) -> list[SoftCopyClaimProvenance]:
    """Retain only model-declared soft-copy evidence bindings.

    The generator never infers evidence IDs from wording.  It maps declared IDs
    to the repository's existing canonical span index so the retained claim is
    auditable without creating a second evidence system.
    """

    family = str(artifact_family or "").strip()
    if family not in _SUPPORTED_FAMILIES:
        raise AppError(
            code="soft_copy_claim_provenance_family_invalid",
            message="Soft-copy provenance has an unsupported artifact family",
            retryable=False,
            context={"artifact_family": family},
        )
    public_text = _normalized_text(text)
    if not public_text:
        return []
    if not isinstance(declared_claims, list):
        raise AppError(
            code="soft_copy_claim_provenance_bindings_missing",
            message="Material soft-copy requires declared claim provenance bindings",
            retryable=False,
            context={"artifact_family": family},
        )

    claims: list[SoftCopyClaimProvenance] = []
    seen_claim_ids: set[str] = set()
    declared_texts: set[str] = set()
    for raw in declared_claims:
        if not isinstance(raw, dict):
            raise AppError(
                code="soft_copy_claim_provenance_binding_invalid",
                message="Soft-copy claim provenance binding must be an object",
                retryable=False,
                context={"artifact_family": family},
            )
        claim_text = _normalized_text(raw.get("claim"))
        classification = str(raw.get("classification") or "").strip()
        evidence_ids = _unique_strings(raw.get("evidence_ids"))
        if (
            not claim_text
            or claim_text not in public_text
            or classification not in _CLASSIFICATIONS
        ):
            raise AppError(
                code="soft_copy_claim_provenance_binding_invalid",
                message=(
                    "Soft-copy claim binding must match public text and classification"
                ),
                retryable=False,
                context={"artifact_family": family},
            )
        declared_texts.add(claim_text)
        if classification == "factual" and not evidence_ids:
            raise AppError(
                code="soft_copy_claim_provenance_binding_invalid",
                message="Factual soft-copy claim requires declared evidence IDs",
                retryable=False,
                context={"artifact_family": family},
            )
        text_hash = _sha256(claim_text)
        claim_id = f"soft_copy:{family}:{text_hash[:16]}"
        if claim_id in seen_claim_ids:
            continue
        seen_claim_ids.add(claim_id)
        source_spans = tuple(
            dict(span)
            for evidence_id in evidence_ids
            for span in evidence_span_index.get(evidence_id.casefold(), [])
        )
        claims.append(
            SoftCopyClaimProvenance(
                schema_version="1.0",
                artifact_family=family,
                claim_id=claim_id,
                text_hash=text_hash,
                classification=classification,  # type: ignore[arg-type]
                evidence_ids=tuple(evidence_ids),
                source_spans=source_spans,
                producing_prompt_identity=dict(producing_prompt_identity),
                generation_attempt=generation_attempt,
                regeneration_attempt=regeneration_attempt,
            ).validate()
        )
    if not claims:
        raise AppError(
            code="soft_copy_claim_provenance_bindings_missing",
            message="Material soft-copy requires at least one declared claim binding",
            retryable=False,
            context={"artifact_family": family},
        )
    if missing_sentences := [
        sentence
        for sentence in _material_sentences(public_text)
        if sentence not in declared_texts
    ]:
        raise AppError(
            code="soft_copy_claim_provenance_bindings_incomplete",
            message="Soft-copy provenance must declare every material sentence",
            retryable=False,
            context={
                "artifact_family": family,
                "missing_claim_count": len(missing_sentences),
            },
        )
    return claims


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _unique_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _material_sentences(text: str) -> list[str]:
    return soft_copy_material_sentences(text)


def retained_soft_copy_claims_cover_text(
    *, text: str, claims: list[SoftCopyClaimProvenance]
) -> bool:
    """Confirm retained claims exactly cover public sentences with no stale records."""
    sentence_hashes = {
        _sha256(sentence) for sentence in _material_sentences(_normalized_text(text))
    }
    claim_hashes = {claim.text_hash for claim in claims}
    return sentence_hashes == claim_hashes and len(claims) == len(claim_hashes)
