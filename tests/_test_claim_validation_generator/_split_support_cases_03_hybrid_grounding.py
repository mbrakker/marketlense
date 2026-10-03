# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(_SplitPath(__file__).resolve().parent / "cases_03_hybrid_grounding.py")

import hashlib
from dataclasses import asdict, replace
import pytest
import src.generators.claim_validation_generator as claim_validation
from src.contracts.claim_validation import (
    CLAIM_GROUNDING_VALIDATOR_VERSION,
    ClaimSemanticGroundingResult,
    ClaimSemanticValidationIdentity,
)
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from src.contracts.validation import ValidationReport
from src.generators.artifact_normalization import normalize_artifact_quotes
from src.generators.claim_validation_generator import validate_retained_claims
from src.generators.publish_readiness_generator import evaluate_publish_readiness
from src.utils.cache_utils import sha256_json


def _ambiguous_claim(
    text: str = "Wallet use is becoming a common checkout method across retailers.",
) -> tuple[dict, dict]:
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {"id": "claim-1", "claim": text, "evidence_id": "f1"}
            ]
        }
    }
    evidence = {
        "findings": {
            "findings": [
                {"id": "f1", "text": "Wallet use is becoming a common checkout method."}
            ]
        }
    }
    return artifacts, evidence


def _semantic_result(claim_input, outcome: str) -> ClaimSemanticGroundingResult:
    identity = ClaimSemanticValidationIdentity(
        schema_version="1.0",
        claim_id=claim_input.candidate.claim_id,
        claim_text_hash=claim_input.candidate.text_hash,
        evidence_ids=[
            ref.evidence_id for ref in claim_input.candidate.evidence_references
        ],
        evidence_hash=claim_input.evidence_hash,
        source_identity=claim_input.source_identity,
        prompt_family="report_vs/validate/grounding",
        prompt_content_hash="prompt-content-1",
        execution_identity="execution-1",
        validator_version=CLAIM_GROUNDING_VALIDATOR_VERSION,
        model_provider="openai",
        model_name="test-model",
        configuration_policy_identity="policy-1",
        relevant_input_hash="input-1",
    )
    return ClaimSemanticGroundingResult(
        schema_version="1.0",
        outcome=outcome,
        reason=f"semantic_{outcome}",
        identity=identity,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
