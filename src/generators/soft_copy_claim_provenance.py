"""Deterministic assembly of private soft-copy claim provenance.

Sentence segmentation, claim identity, text hashes, source spans, and coverage
are derived mechanically from the generated public text and the canonical
evidence span index.  The model contributes only the semantic binding: which
material sentences carry which classification and which retained evidence IDs.
"""

from __future__ import annotations

import hashlib
from typing import Any

from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    align_soft_copy_claim_bindings_to_text,
    soft_copy_material_sentences,
    soft_copy_public_text,
    soft_copy_claim_provenance_from_payload,
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
    """Retain model-declared soft-copy evidence bindings on the canonical grid.

    The generator never infers evidence IDs from wording.  Declared quotes are
    resolved onto the segmented public sentences by the contract's canonical
    resolver, so quoting variance in mechanically equivalent text cannot fail
    provenance, while every material sentence still needs one declared binding
    and every factual binding still needs retained evidence IDs.
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

    sentences = soft_copy_material_sentences(public_text)
    resolved_bindings = align_soft_copy_claim_bindings_to_text(
        artifact_family=family,
        text=public_text,
        claim_bindings=declared_claims,
    )
    covered_claims = {
        _normalized_text(binding.get("claim"))
        for binding in resolved_bindings
        if isinstance(binding, dict)
    }
    if missing_sentences := [
        sentence for sentence in sentences if sentence not in covered_claims
    ]:
        first_excerpt = " ".join(str(missing_sentences[0]).split())[:100]
        raise AppError(
            code="soft_copy_claim_provenance_bindings_incomplete",
            message=(
                "Soft-copy provenance must declare every material sentence; "
                f"uncovered sentences: {len(missing_sentences)}; first uncovered "
                f"sentence starts: {first_excerpt}"
            ),
            retryable=False,
            context={
                "artifact_family": family,
                "missing_claim_count": len(missing_sentences),
            },
        )

    claims: list[SoftCopyClaimProvenance] = []
    seen_claim_ids: set[str] = set()
    for binding in resolved_bindings:
        claim_text = _normalized_text(binding.get("claim"))
        classification = str(binding.get("classification") or "").strip()
        evidence_ids = _unique_strings(binding.get("evidence_ids"))
        if classification not in _CLASSIFICATIONS:
            raise AppError(
                code="soft_copy_claim_provenance_binding_invalid",
                message="Soft-copy claim binding must declare a valid classification",
                retryable=False,
                context={"artifact_family": family},
            )
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


def assert_retained_soft_copy_claims_match_public_copy(
    artifacts: dict[str, Any],
) -> None:
    """Reject a retained payload whose public soft copy changed after finalization."""

    raw_provenance = artifacts.get("soft_copy_claim_provenance")
    claims = soft_copy_claim_provenance_from_payload(raw_provenance)
    for family in sorted(_SUPPORTED_FAMILIES):
        public_text = soft_copy_public_text(family, artifacts.get(family))
        family_claims = [
            claim for claim in claims if claim.artifact_family == family
        ]
        if retained_soft_copy_claims_cover_text(
            text=public_text, claims=family_claims
        ):
            continue
        public_hashes = {
            _sha256(sentence)
            for sentence in soft_copy_material_sentences(_normalized_text(public_text))
        }
        retained_hashes = {claim.text_hash for claim in family_claims}
        raise AppError(
            code="soft_copy_claim_provenance_coverage_invalid",
            message=(
                "Retained soft-copy provenance must exactly match final public prose"
            ),
            retryable=False,
            context={
                "artifact_family": family,
                "missing_public_sentence_count": len(public_hashes - retained_hashes),
                "obsolete_provenance_sentence_count": len(
                    retained_hashes - public_hashes
                ),
                "duplicate_provenance_count": len(family_claims)
                - len(retained_hashes),
            },
        )
