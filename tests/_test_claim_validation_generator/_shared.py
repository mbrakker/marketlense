# ruff: noqa: F401,F403,F405
from __future__ import annotations

from __future__ import annotations
import hashlib
from src.generators.claim_validation_generator import (
    exclude_untrusted_evidence,
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
                    "page": 4,
                },
                {"id": "q1", "text": "Wallets are now core checkout infrastructure."},
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
