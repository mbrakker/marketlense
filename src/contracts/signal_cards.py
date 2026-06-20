from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from src.contracts.report_cards import CoverFingerprint
from src.utils.errors import AppError


SIGNAL_CARD_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class SignalCardContent:
    """Validated signal-specific content required before card covers are rendered."""

    schema_version: str = field(metadata={"doc": "Signal-card content schema version."})
    summary: str = field(metadata={"doc": "Complete grounded signal statement."})
    confidence: float = field(
        metadata={"doc": "Grounding confidence in the inclusive range 0..1."}
    )
    source_count: int = field(
        metadata={"doc": "Count of distinct source reports supporting the signal."}
    )
    evidence_count: int = field(
        metadata={"doc": "Count of grounded evidence items supporting the signal."}
    )
    uncertainty: str = field(
        metadata={
            "doc": "Complete coverage or uncertainty condition shown on large cards."
        }
    )
    fingerprint: CoverFingerprint = field(
        metadata={"doc": "Deterministic semantic fingerprint for the signal cover."}
    )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "SignalCardContent":
        if (
            str(payload.get("schema_version") or "").strip()
            != SIGNAL_CARD_SCHEMA_VERSION
        ):
            raise AppError(
                code="signal_card_contract_invalid",
                message="Signal card schema version is not supported",
                retryable=False,
            )
        fingerprint_payload = payload.get("fingerprint")
        if not isinstance(fingerprint_payload, Mapping):
            raise AppError(
                code="signal_card_contract_invalid",
                message="Signal card fingerprint must be an object",
                retryable=False,
            )
        try:
            confidence = float(str(payload.get("confidence") or ""))
            source_count = int(str(payload.get("source_count") or ""))
            evidence_count = int(str(payload.get("evidence_count") or ""))
        except (TypeError, ValueError) as exc:
            raise AppError(
                code="signal_card_contract_invalid",
                message="Signal card confidence and evidence counts must be numeric",
                cause=exc,
                retryable=False,
            ) from exc
        summary = " ".join(str(payload.get("summary") or "").split())
        uncertainty = " ".join(str(payload.get("uncertainty") or "").split())
        if (
            not summary
            or not uncertainty
            or not 0.0 <= confidence <= 1.0
            or source_count < 1
            or evidence_count < 1
        ):
            raise AppError(
                code="signal_card_contract_invalid",
                message="Signal card fields are incomplete or invalid",
                retryable=False,
            )
        return cls(
            schema_version=SIGNAL_CARD_SCHEMA_VERSION,
            summary=summary,
            confidence=confidence,
            source_count=source_count,
            evidence_count=evidence_count,
            uncertainty=uncertainty,
            fingerprint=CoverFingerprint.from_dict(fingerprint_payload),
        )
