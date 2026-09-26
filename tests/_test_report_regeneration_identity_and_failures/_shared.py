# ruff: noqa: F401,F403,F405
from __future__ import annotations

import hashlib

from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from tests.test_report_regeneration_generator import _current_artifacts


def _source_backed_artifacts() -> dict:
    """Current artifacts whose summary prose is backed by its claim map.

    Every summary sentence equals the mapped claim, so assembly reuses the
    retained provenance instead of triggering the source-backed fallback.
    """

    artifacts = _current_artifacts()
    artifacts["summary"]["tldr"] = "Old claim."
    artifacts["summary"]["card_tldr_compact"] = "Old claim."
    artifacts["summary"]["executive_summary"] = "Old claim."
    artifacts["summary"]["claim_evidence_map"][0]["claim"] = "Old claim."
    retained_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family=family,
            claim_id=(
                f"soft_copy:{family}:{hashlib.sha256(text.encode()).hexdigest()[:16]}"
            ),
            text_hash=hashlib.sha256(text.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=("f1",) if family == "summary" else (),
            source_spans=(),
            producing_prompt_identity={"namespace": f"report_vs/artifacts/{family}"},
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for family, text in (
            ("summary", "Old claim."),
            ("expert_comment", "Old expert"),
            ("linkedin_post", "Old linkedin"),
        )
    ]
    artifacts["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        retained_claims
    )
    return artifacts


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
    }
]
