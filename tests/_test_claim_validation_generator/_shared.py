# ruff: noqa: F401,F403,F405
from __future__ import annotations

from __future__ import annotations
import hashlib
from src.contracts.claim_validation import (
    CLAIM_GROUNDING_VALIDATOR_VERSION,
    ClaimSemanticGroundingResult,
    ClaimSemanticValidationIdentity,
)
from src.contracts.protected_facts import ProtectedFactComparison
from src.generators.claim_validation_generator import (
    exclude_untrusted_evidence,
    retained_claim_semantic_inputs,
    validate_evidence_fidelity,
    validate_retained_claims,
)


def _evidence() -> dict:
    return {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": (
                        "Wallet adoption reached 42% in Global enterprise merchants in "
                        "2026."
                    ),
                    "evidence": (
                        "Wallet adoption reached 42% in Global enterprise merchants in "
                        "2026."
                    ),
                    "page": 4,
                },
                {
                    "id": "q1",
                    "text": "Wallets are now core checkout infrastructure.",
                    "evidence": "Wallets are now core checkout infrastructure.",
                },
            ]
        }
    }


def _soft_copy_claim(
    *,
    artifact_family: str,
    text: str,
    classification: str,
    evidence_ids: list[str],
    text_hash: str = "",
) -> dict:
    return {
        "schema_version": "1.0",
        "artifact_family": artifact_family,
        "claim_id": f"soft_copy:{artifact_family}:{len(text)}",
        "text_hash": text_hash or hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "classification": classification,
        "evidence_ids": evidence_ids,
        "source_spans": [],
        "producing_prompt_identity": {"namespace": f"test/{artifact_family}"},
        "generation_attempt": 1,
        "regeneration_attempt": 0,
    }


def _semantic_result(
    semantic_input,
    *,
    outcome: str = "entailed",
    proposition_status: str = "compatible",
    execution_identity: str = "test-semantic-execution",
) -> ClaimSemanticGroundingResult:
    """Build a complete provider verdict for migrated semantic-authority tests."""

    identity = ClaimSemanticValidationIdentity(
        schema_version="1.0",
        claim_id=semantic_input.candidate.claim_id,
        claim_text_hash=semantic_input.candidate.text_hash,
        evidence_ids=[
            reference.evidence_id
            for reference in semantic_input.candidate.evidence_references
        ],
        evidence_hash=semantic_input.evidence_hash,
        source_identity=semantic_input.source_identity,
        prompt_family="test/semantic-grounding",
        prompt_content_hash="test-prompt-content-hash",
        execution_identity=execution_identity,
        validator_version=CLAIM_GROUNDING_VALIDATOR_VERSION,
        model_provider="test",
        model_name="test-semantic-model",
        configuration_policy_identity="test-policy",
        relevant_input_hash="test-input",
    )
    return ClaimSemanticGroundingResult(
        schema_version="1.0",
        outcome=outcome,
        reason=f"test_semantic_{outcome}",
        identity=identity,
        protected_facts=ProtectedFactComparison.from_payload(
            {}, proposition_status=proposition_status
        ),
    )


def _semantic_batch_supported(semantic_inputs):
    return [_semantic_result(item) for item in semantic_inputs]


def _semantic_batch_contradicted(semantic_inputs):
    return [
        _semantic_result(
            item,
            outcome="contradicted",
            proposition_status="incompatible",
            execution_identity="test-semantic-contradiction",
        )
        for item in semantic_inputs
    ]


def _semantic_support(*_args):
    return True, "test_semantic_entailed", "test-semantic-execution"


def _semantic_reject(*_args):
    return False, "test_semantic_contradicted", "test-semantic-contradiction"


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
        "_SplitPath",
    }
]
