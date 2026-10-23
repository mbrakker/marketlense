"""Compatibility exports for the deterministic verified-facts utilities."""

from src.utils.verified_facts import (
    PROTECTED_METRIC_FIELDS,
    VERIFIED_FACT_EVIDENCE_PREFIX,
    canonical_evidence_map,
    canonical_fact_text,
    canonical_verified_evidence_packs,
    expected_pdf_sha256,
    expected_pdf_sha256_from_identity,
    fact_for_evidence_id,
    metric_binding_mismatches,
    validated_verified_facts,
    validate_verified_artifact_bindings,
    verified_facts_mode,
)

__all__ = [
    "PROTECTED_METRIC_FIELDS",
    "VERIFIED_FACT_EVIDENCE_PREFIX",
    "canonical_evidence_map",
    "canonical_fact_text",
    "canonical_verified_evidence_packs",
    "expected_pdf_sha256",
    "expected_pdf_sha256_from_identity",
    "fact_for_evidence_id",
    "metric_binding_mismatches",
    "validated_verified_facts",
    "validate_verified_artifact_bindings",
    "verified_facts_mode",
]
