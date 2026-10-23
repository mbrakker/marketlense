"""Versioned contracts for shadow-mode verified-claims evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION = "1.1"
VERIFIED_FACT_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class VisualClaimEvaluationRequest:
    schema_version: str = field(
        metadata={"doc": "Visual verified-claim evaluation request schema version."}
    )
    pdf_path: str = field(metadata={"doc": "Original source PDF path."})
    output_dir: str = field(metadata={"doc": "Output root for full-page renders."})
    report_name: str = field(metadata={"doc": "Safe report name for render paths."})
    source_identity: str = field(
        metadata={"doc": "Canonical source/PDF identity used for evaluation."}
    )
    claims: List[Dict[str, Any]] = field(
        metadata={"doc": "Shortlisted claims with retained source bindings."}
    )
    candidate_roster_digest: str = field(
        default="",
        metadata={
            "doc": (
                "Digest of the exact candidate roster evaluated; empty only for "
                "legacy direct callers."
            )
        },
    )
    shadow_mode: bool = field(
        default=True,
        metadata={"doc": "Evaluation must not mutate authoritative report artifacts."},
    )
    dpi: int = field(
        default=180,
        metadata={"doc": "Full-page render DPI for visual assessment."},
    )
    recovery_enabled: bool = field(
        default=False,
        metadata={
            "doc": (
                "Whether bounded deterministic recovery candidates may be inspected; "
                "disabled for reference/adversarial fixtures."
            )
        },
    )
    recovery_candidates: Dict[str, List[Dict[str, Any]]] = field(
        default_factory=dict,
        metadata={
            "doc": (
                "Provisional page candidates keyed by stable candidate ID; these "
                "never replace the retained evidence binding."
            )
        },
    )
    source_page_text_by_physical_page: Dict[int, str] = field(
        default_factory=dict,
        metadata={
            "doc": (
                "Optional deterministic native text keyed by one-based physical "
                "page for source-page attribution checks."
            )
        },
    )


@dataclass(frozen=True)
class VisualClaimCorrectionAttempt:
    schema_version: str = field(
        metadata={"doc": "Correction-attempt record schema version."}
    )
    attempt: int = field(metadata={"doc": "One-based correction attempt number."})
    claim: str = field(metadata={"doc": "Model-produced corrected analytical claim."})
    status: str = field(
        metadata={"doc": "Model status: corrected, unresolved, or failed."}
    )
    issues: List[str] = field(
        default_factory=list,
        metadata={"doc": "Deterministic or model-reported correction issues."},
    )
    request_id: str = field(default="", metadata={"doc": "Provider request ID."})
    model: str = field(default="", metadata={"doc": "Resolved provider model."})


@dataclass(frozen=True)
class VisualClaimVerificationAttempt:
    schema_version: str = field(
        metadata={"doc": "Verification-attempt record schema version."}
    )
    attempt: int = field(metadata={"doc": "One-based verification attempt number."})
    outcome: str = field(
        metadata={"doc": "Verification outcome: verified or rejected."}
    )
    diagnostics: List[str] = field(
        default_factory=list,
        metadata={"doc": "Source-based verification diagnostics."},
    )
    source_truth_notes: str = field(
        default="", metadata={"doc": "Verifier explanation tied to the source page."}
    )
    supporting_physical_pages: List[int] = field(
        default_factory=list,
        metadata={
            "doc": (
                "One-based physical pages independently identified as supporting "
                "the final corrected claim."
            )
        },
    )
    source_truth_notes_by_page: Dict[str, str] = field(
        default_factory=dict,
        metadata={
            "doc": (
                "Page-keyed source-grounded explanations for supporting physical pages."
            )
        },
    )
    verified_fact: Dict[str, Any] = field(
        default_factory=dict,
        metadata={
            "doc": (
                "Source-established factual statement and structured metric; "
                "empty unless the verification response supplied a valid fact."
            )
        },
    )
    request_id: str = field(default="", metadata={"doc": "Provider request ID."})
    model: str = field(default="", metadata={"doc": "Resolved provider model."})


@dataclass(frozen=True)
class VisualClaimEvaluationResult:
    schema_version: str = field(
        metadata={"doc": "Per-claim visual evaluation result schema version."}
    )
    candidate_id: str = field(metadata={"doc": "Stable shortlisted candidate ID."})
    original_claim: str = field(
        metadata={"doc": "Original claim supplied for direction."}
    )
    source_identity: str = field(metadata={"doc": "Authoritative source identity."})
    physical_page: int = field(
        metadata={"doc": "One-based physical PDF page used for visual assessment."}
    )
    outcome: str = field(
        metadata={
            "doc": (
                "Terminal outcome: verified, verified_after_retry, "
                "failed_verification, unresolved, or skipped."
            )
        }
    )
    physical_pages: List[int] = field(
        default_factory=list,
        metadata={"doc": "All one-based physical PDF pages supplied to the model."},
    )
    evidence_ids: List[str] = field(
        default_factory=list,
        metadata={"doc": "Copied canonical evidence IDs from the shortlisted claim."},
    )
    evidence_spans: List[Dict[str, Any]] = field(
        default_factory=list,
        metadata={
            "doc": "Copied authoritative evidence spans from the shortlisted claim."
        },
    )
    original_metric_binding: Dict[str, Any] = field(
        default_factory=dict,
        metadata={
            "doc": "Complete protected metric binding retained from the original claim."
        },
    )
    corrected_evidence_ids: List[str] = field(
        default_factory=list,
        metadata={
            "doc": (
                "Evidence IDs independently bound to the final claim; empty when "
                "the corrected proposition differs from the retained claim."
            )
        },
    )
    corrected_evidence_spans: List[Dict[str, Any]] = field(
        default_factory=list,
        metadata={"doc": "Evidence spans bound to the final corrected proposition."},
    )
    corrected_metric_binding: Dict[str, Any] = field(
        default_factory=dict,
        metadata={
            "doc": "Protected metric binding for the final claim, when authoritative."
        },
    )
    corrected_source_binding_status: str = field(
        default="unbound",
        metadata={
            "doc": (
                "Final-claim binding state: retained only for an unchanged claim; "
                "otherwise unbound until independently sourced."
            )
        },
    )
    correction_attempts: List[VisualClaimCorrectionAttempt] = field(
        default_factory=list,
        metadata={"doc": "All bounded correction attempts."},
    )
    verification_attempts: List[VisualClaimVerificationAttempt] = field(
        default_factory=list,
        metadata={"doc": "All independent verification attempts."},
    )
    final_claim: str = field(
        default="",
        metadata={"doc": "Verified corrected claim, never unverified output."},
    )
    failure_reason: str = field(
        default="", metadata={"doc": "Terminal reason when the claim is not verified."}
    )
    original_physical_pages: List[int] = field(
        default_factory=list,
        metadata={"doc": "Original retained physical pages and immutable binding."},
    )
    inspected_physical_pages: List[int] = field(
        default_factory=list,
        metadata={"doc": "All physical pages supplied to correction and verification."},
    )
    recovered_physical_pages: List[int] = field(
        default_factory=list,
        metadata={"doc": "Additional provisional pages inspected during recovery."},
    )
    recovery_reason: str = field(
        default="",
        metadata={"doc": "Deterministic reason provisional recovery was attempted."},
    )
    source_binding_status: str = field(
        default="retained",
        metadata={
            "doc": (
                "Binding state: retained, or provisional_recovered; never canonical."
            )
        },
    )
    supporting_physical_pages: List[int] = field(
        default_factory=list,
        metadata={
            "doc": (
                "One-based physical pages independently identified as supporting "
                "the final corrected claim."
            )
        },
    )
    source_truth_notes_by_page: Dict[str, str] = field(
        default_factory=dict,
        metadata={
            "doc": (
                "Page-keyed source-grounded explanations for supporting physical pages."
            )
        },
    )
    canonical_approval_status: str = field(
        default="not_approved",
        metadata={
            "doc": (
                "Canonical promotion state; shadow verification never approves a claim."
            )
        },
    )
    verified_fact: Dict[str, Any] = field(
        default_factory=dict,
        metadata={
            "doc": (
                "Authoritative visual fact; original candidate fields remain "
                "diagnostic lineage only."
            )
        },
    )


@dataclass(frozen=True)
class VisualClaimEvaluationResponse:
    schema_version: str = field(
        metadata={"doc": "Batch visual evaluation response schema version."}
    )
    shadow_mode: bool = field(
        metadata={"doc": "Whether authoritative artifacts were isolated from results."}
    )
    claims: List[VisualClaimEvaluationResult] = field(
        default_factory=list, metadata={"doc": "Per-claim evaluation results."}
    )
    candidate_roster_digest: str = field(
        default="",
        metadata={"doc": "Digest of the exact candidate roster evaluated."},
    )
    rendered_pages: Dict[int, str] = field(
        default_factory=dict,
        metadata={"doc": "Cached full-page render paths keyed by physical page."},
    )


__all__ = [
    "VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION",
    "VERIFIED_FACT_SCHEMA_VERSION",
    "VisualClaimCorrectionAttempt",
    "VisualClaimEvaluationRequest",
    "VisualClaimEvaluationResponse",
    "VisualClaimEvaluationResult",
    "VisualClaimVerificationAttempt",
]
