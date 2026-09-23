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
    return not soft_copy_uncovered_sentences(
        artifact_family=artifact_family,
        public_output=public_output,
        claim_bindings=claim_bindings,
    )


def soft_copy_uncovered_sentences(
    *,
    artifact_family: str,
    public_output: object,
    claim_bindings: object,
) -> list[str]:
    """Return material public sentences that no declared binding covers exactly."""

    text = soft_copy_public_text(artifact_family, public_output)
    if not text:
        return []
    if not isinstance(claim_bindings, list) or not claim_bindings:
        return soft_copy_material_sentences(text)
    declared = {
        " ".join(str(binding.get("claim") or "").split())
        for binding in claim_bindings
        if isinstance(binding, dict) and str(binding.get("claim") or "").strip()
    }
    if not declared:
        return soft_copy_material_sentences(text)
    return [
        sentence
        for sentence in soft_copy_material_sentences(text)
        if sentence not in declared
    ]


def align_soft_copy_claim_bindings_to_sentences(
    *,
    artifact_family: str,
    public_output: object,
    claim_bindings: object,
) -> list[dict[str, Any]]:
    """Resegment model-declared bindings onto the canonical sentence grid.

    The provenance contract retains one binding per material public sentence,
    while models legitimately declare one object per paragraph or clause group.
    """
    if not isinstance(claim_bindings, list):
        return []
    text = soft_copy_public_text(artifact_family, public_output)
    if not text:
        return [binding for binding in claim_bindings if isinstance(binding, dict)]
    return align_soft_copy_claim_bindings_to_text(
        artifact_family=artifact_family,
        text=text,
        claim_bindings=claim_bindings,
    )


def align_soft_copy_claim_bindings_to_text(
    *,
    artifact_family: str,
    text: str,
    claim_bindings: object,
) -> list[dict[str, Any]]:
    """Resegment declared bindings onto the sentence grid of normalized ``text``.

    Canonical companion to :func:`align_soft_copy_claim_bindings_to_sentences`
    for callers that already hold the joined public prose, such as the retained
    provenance builder, so render and storage gates share one resolver.
    """

    if not isinstance(claim_bindings, list):
        return []
    joined = " ".join(str(text or "").split())
    if not joined:
        return [binding for binding in claim_bindings if isinstance(binding, dict)]
    return _align_bindings_to_sentences(
        sentences=soft_copy_material_sentences(joined),
        claim_bindings=claim_bindings,
    )


def _align_bindings_to_sentences(
    *,
    sentences: list[str],
    claim_bindings: list[Any],
) -> list[dict[str, Any]]:
    """Split declared bindings across the exact public sentences they cover.

    Splitting a declared binding distributes its own unchanged classification
    and evidence IDs across the exact public sentences it already covers; it
    never invents evidence or rewrites declared text. A binding that matches no
    public sentence carries no provenance for the retained contract; it is
    dropped when the remaining bindings already cover every material sentence,
    and kept when they do not so the coverage gate can reject the payload with
    actionable context.
    """

    aligned: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    covered_sentences: set[str] = set()
    for binding in claim_bindings:
        if not isinstance(binding, dict):
            continue
        claim_text = " ".join(str(binding.get("claim") or "").split())
        if not claim_text:
            continue
        run = _matching_sentence_run(sentences, claim_text)
        if run is None:
            if claim_text not in covered_sentences:
                covered_sentences.add(claim_text)
                unmatched.append(binding)
            continue
        for sentence in run:
            if sentence in covered_sentences:
                continue
            covered_sentences.add(sentence)
            aligned.append({**binding, "claim": sentence})
    if any(sentence not in covered_sentences for sentence in sentences):
        # Coverage is incomplete: keep the unmatched bindings so the coverage
        # gate reports the full payload to the informed repair attempt.
        return aligned + unmatched
    return aligned


_BINDING_MIN_MATCH_TOKENS = 3
_BINDING_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _matching_sentence_run(sentences: list[str], claim_text: str) -> list[str] | None:
    """Return the consecutive sentence run a declared quote mechanically covers.

    Resolution is tiered so mechanically equivalent quotes never fail
    provenance while semantic matches stay anchored to declared text:

    1. exact equality with a sentence or a consecutive run join;
    2. equality after case and punctuation normalization (the model quoting
       the same words with different punctuation or capitalization);
    3. unique token containment — a quoted clause inside exactly one
       sentence, or exactly one sentence inside a longer quote.

    Ambiguous containment (several equally valid sentences) resolves nothing,
    so an unclear quote stays unmatched and the coverage gate fails closed
    instead of guessing which sentence the evidence belongs to.
    """

    run = _exact_sentence_run(sentences, claim_text)
    if run is not None:
        return run
    run = _normalized_sentence_run(sentences, claim_text)
    if run is not None:
        return run
    return _contained_sentence_run(sentences, claim_text)


def _exact_sentence_run(sentences: list[str], claim_text: str) -> list[str] | None:
    """Return the consecutive sentence run exactly equal to ``claim_text``."""

    if claim_text in sentences:
        return [claim_text]
    for start in range(len(sentences)):
        joined = sentences[start]
        for end in range(start + 1, len(sentences)):
            joined = f"{joined} {sentences[end]}"
            if joined == claim_text:
                return sentences[start : end + 1]
            if len(joined) > len(claim_text):
                break
    return None


def _normalized_sentence_run(sentences: list[str], claim_text: str) -> list[str] | None:
    """Return the run whose canonical text equals the quote's canonical text."""

    claimed = _canonical_binding_text(claim_text)
    if not claimed:
        return None
    for sentence in sentences:
        if _canonical_binding_text(sentence) == claimed:
            return [sentence]
    for start in range(len(sentences)):
        joined = _canonical_binding_text(sentences[start])
        for end in range(start + 1, len(sentences)):
            joined = f"{joined} {_canonical_binding_text(sentences[end])}"
            if joined == claimed:
                return sentences[start : end + 1]
            if len(joined) > len(claimed):
                break
    return None


def _contained_sentence_run(sentences: list[str], claim_text: str) -> list[str] | None:
    """Return the one sentence uniquely containing, or contained in, the quote."""

    claimed_tokens = frozenset(_binding_tokens(claim_text))
    if len(claimed_tokens) < _BINDING_MIN_MATCH_TOKENS:
        return None
    clause_candidates = [
        sentence
        for sentence in sentences
        if claimed_tokens <= _sentence_token_set(sentence)
    ]
    if len(clause_candidates) == 1:
        return [clause_candidates[0]]
    sentence_candidates = [
        sentence
        for sentence in sentences
        if len(_sentence_token_set(sentence)) >= _BINDING_MIN_MATCH_TOKENS
        and _sentence_token_set(sentence) <= claimed_tokens
    ]
    if len(sentence_candidates) == 1:
        return [sentence_candidates[0]]
    return None


def _canonical_binding_text(value: str) -> str:
    """Return the case- and punctuation-insensitive text form for matching."""

    return " ".join(_BINDING_TOKEN_PATTERN.findall(str(value or "").casefold()))


def _binding_tokens(value: str) -> list[str]:
    return _BINDING_TOKEN_PATTERN.findall(str(value or "").casefold())


def _sentence_token_set(sentence: str) -> frozenset[str]:
    return frozenset(_binding_tokens(sentence))


def soft_copy_material_sentences(text: object) -> list[str]:
    """Split public prose without treating an initialism as a sentence end.

    Provenance declares complete public sentences.  ``U.K. digital media`` is
    one such sentence, not the two fragments produced by a punctuation-only
    splitter.  The lowercase continuation condition keeps a genuine terminal
    initialism followed by a new capitalized sentence fail-closed.  Fragments
    that carry no prose (for example a closing line of only ``#tag``
    hashtags, which LinkedIn formatting treats as metadata rather than a
    claim) are not material sentences and therefore require no provenance.
    """

    fragments = [
        " ".join(fragment.split())
        for fragment in re.split(r"(?<=[.!?])\s+", " ".join(str(text or "").split()))
        if " ".join(fragment.split())
    ]
    sentences: list[str] = []
    for fragment in fragments:
        if (
            sentences
            and re.search(r"(?:\b[A-Za-z]\.){2,}$", sentences[-1])
            and fragment[:1].islower()
        ):
            sentences[-1] = f"{sentences[-1]} {fragment}"
        elif _is_prose_fragment(fragment):
            sentences.append(fragment)
    return sentences


def _is_prose_fragment(fragment: str) -> bool:
    without_hashtags = re.sub(r"#[A-Za-z0-9_]+", "", fragment)
    return bool(re.search(r"[A-Za-z0-9]", without_hashtags))


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
            "typed_compatibility_fallback",
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
