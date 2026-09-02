from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, cast

ProtectedFactStatus = Literal["compatible", "incompatible", "unknown"]

PROTECTED_FACT_DIMENSIONS = (
    "value",
    "unit_currency",
    "magnitude",
    "direction",
    "timeframe",
    "geography",
    "population",
    "comparison",
    "observation_status",
    "attribution",
    "certainty",
    "causality",
)


@dataclass(frozen=True)
class ProtectedFactDimension:
    """Literal claim/evidence values for one material fact dimension."""

    schema_version: str = field(
        metadata={"doc": "Protected fact-dimension comparison schema."}
    )
    claim_value: str | None
    evidence_value: str | None
    status: ProtectedFactStatus


@dataclass(frozen=True)
class ProtectedFactComparison:
    """Domain-neutral semantic comparison of a claim and linked evidence."""

    schema_version: str = field(
        metadata={"doc": "Protected factual-claim comparison schema."}
    )
    proposition_status: ProtectedFactStatus
    dimensions: Mapping[str, ProtectedFactDimension]

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any] | None,
        *,
        proposition_status: str = "unknown",
    ) -> ProtectedFactComparison:
        raw_dimensions = payload if isinstance(payload, Mapping) else {}
        dimensions = {
            name: _dimension_from_payload(raw_dimensions.get(name))
            for name in PROTECTED_FACT_DIMENSIONS
        }
        return cls(
            schema_version="1.0",
            proposition_status=_status(proposition_status), dimensions=dimensions
        )

    def dimension(self, name: str) -> ProtectedFactDimension:
        return self.dimensions[name]

    @property
    def incompatible_dimensions(self) -> tuple[str, ...]:
        incompatible = (
            name
            for name in PROTECTED_FACT_DIMENSIONS
            if self.dimensions[name].status == "incompatible"
        )
        return (
            (("factual_proposition",) if self.proposition_status == "incompatible" else ())
            + tuple(incompatible)
        )


def _dimension_from_payload(value: Any) -> ProtectedFactDimension:
    raw = value if isinstance(value, Mapping) else {}
    claim_value = _literal(raw.get("claim_value"))
    evidence_value = _literal(raw.get("evidence_value"))
    status = _status(raw.get("status"))
    if status != "unknown" and (claim_value is None or evidence_value is None):
        status = "unknown"
    return ProtectedFactDimension(
        schema_version="1.0",
        claim_value=claim_value,
        evidence_value=evidence_value,
        status=status,
    )


def _literal(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _status(value: Any) -> ProtectedFactStatus:
    normalized = str(value or "").strip().lower()
    if normalized in {"compatible", "incompatible", "unknown"}:
        return cast(ProtectedFactStatus, normalized)
    return "unknown"
