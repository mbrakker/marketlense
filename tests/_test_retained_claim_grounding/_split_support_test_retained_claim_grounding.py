# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_retained_claim_grounding.py"
)

import hashlib
from dataclasses import replace
from types import SimpleNamespace
from src.contracts.claim_validation import (
    CLAIM_GROUNDING_VALIDATOR_VERSION,
    ClaimValidationPackage,
)
from src.contracts.protected_facts import PROTECTED_FACT_DIMENSIONS
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from src.contracts.validation import ValidationRequest
from src.generators.claim_validation_generator import validate_retained_claims
from src.generators.validation.grounding import (
    _deterministic_claim_validation_issues,
    grounding_payload,
    run_grounding_check,
    run_grounding_rule,
)
from src.generators.validation.regeneration_candidate import (
    retained_claim_repair_issues,
)
from src.generators.validation_generator import validate_report
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from tests._test_validation_generator._shared import (
    FakeAnalysisStore,
    FakeOpenAI,
    FakePromptClient,
    _ctx,
    _report,
    _settings,
)


def _retained_request() -> ValidationRequest:
    claim = "Wallet use is becoming a common checkout method across retailers."
    return ValidationRequest(
        schema_version="1.0",
        report_id="retained-grounding",
        report=_report(),
        artifacts={
            "summary": {
                "claim_evidence_map": [
                    {"id": "claim-1", "claim": claim, "evidence_id": "f1"}
                ]
            }
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "Wallet use is becoming a common checkout method.",
                    }
                ]
            }
        },
        source_id="source-retained-grounding",
    )


def _grounding_check(item_id: str, text: str, outcome: str) -> dict:
    return {
        "item_id": item_id,
        "section": "summary.claim_evidence_map:claim-1.claim",
        "text": text,
        "classification": "factual_claim",
        "entailment_outcome": outcome,
        "proposition_status": "compatible",
        "protected_facts": {
            dimension: {
                "claim_value": None,
                "evidence_value": None,
                "status": "unknown",
            }
            for dimension in PROTECTED_FACT_DIMENSIONS
        },
        "reason": f"semantic_{outcome}",
    }


__all__ = [name for name in globals() if not name.startswith("__")]
