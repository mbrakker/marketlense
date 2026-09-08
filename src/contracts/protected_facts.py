from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, cast

from src.utils.quantity import extract_quantities, quantities_match

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
            proposition_status=_status(proposition_status),
            dimensions=dimensions,
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
            ("factual_proposition",)
            if self.proposition_status == "incompatible"
            else ()
        ) + tuple(incompatible)


_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_DIRECTION_RE = re.compile(
    r"\b(?:grew|growth|increased?|rose|rising|up|gained?|declined?|decreased?|"
    r"fell|falling|dropped?|down|lost)\b",
    re.IGNORECASE,
)
_UPWARD_DIRECTIONS = {
    "grew",
    "growth",
    "increase",
    "increased",
    "rose",
    "rising",
    "up",
    "gained",
    "gain",
}
_DOWNWARD_DIRECTIONS = {
    "decline",
    "declined",
    "decrease",
    "decreased",
    "fell",
    "falling",
    "dropped",
    "drop",
    "down",
    "lost",
    "loss",
}
_GEOGRAPHY_RE = re.compile(
    r"\b(?:africa|america|americas|asia|australia|europe|global|india|china|"
    r"japan|canada|mexico|brazil|france|germany|italy|spain|sweden|norway|"
    r"finland|denmark|ireland|poland|uk|u\.s\.|united states|united kingdom|"
    r"middle east|north america|south america|latin america|apac|emea)\b",
    re.IGNORECASE,
)
_ATTRIBUTION_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3})\s+"
    r"(?:reported|reports?|said|says|found|finds|stated|states)\b"
)
_SUBJECT_RE = re.compile(
    r"\b(?:the\s+)?([A-Za-z][A-Za-z0-9&/-]*(?:\s+[A-Za-z][A-Za-z0-9&/-]*){0,5})\s+"
    r"(?:grew|increased?|rose|declined?|decreased?|fell|dropped?)\b",
    re.IGNORECASE,
)
_RANK_RE = re.compile(
    r"(?:#\s?(\d+)|\b(number\s+one|first(?!\s+time)|second|third|fourth|fifth|largest|smallest)\b)",
    re.IGNORECASE,
)
_COMPARISON_RE = re.compile(
    r"\b(?:versus|vs\.?|compared with|compared to)\s+([^.;,:]+)", re.IGNORECASE
)


def compare_protected_fact_texts(
    claim_text: str, evidence_text: str
) -> ProtectedFactComparison:
    """Compare only explicit, deterministic protected facts in two texts.

    Dimensions that cannot be reliably extracted remain ``unknown``.  This
    comparison intentionally leaves every dimension unknown unless both texts
    contain an explicit, conservatively extracted value.
    """

    payload: dict[str, dict[str, str | None]] = {}
    claim_quantities = extract_quantities(claim_text)
    evidence_quantities = extract_quantities(evidence_text)
    if claim_quantities:
        claim_value = ", ".join(
            sorted({str(float(item.value)) for item in claim_quantities})
        )
        evidence_value = ", ".join(
            sorted({str(float(item.value)) for item in evidence_quantities})
        )
        payload["value"] = {
            "claim_value": claim_value,
            "evidence_value": evidence_value or None,
            "status": (
                "compatible"
                if all(
                    any(
                        _quantity_entailed_by_evidence(claim, evidence)
                        for evidence in evidence_quantities
                    )
                    for claim in claim_quantities
                )
                else "incompatible"
                if evidence_quantities
                else "unknown"
            ),
        }
        explicit_claim_units = {
            item.unit_family
            for item in claim_quantities
            if item.unit_family != "unknown"
        }
        evidence_units = {item.unit_family for item in evidence_quantities}
        if explicit_claim_units:
            payload["unit_currency"] = {
                "claim_value": ", ".join(sorted(explicit_claim_units)),
                "evidence_value": ", ".join(sorted(evidence_units)) or None,
                "status": (
                    "compatible"
                    if all(
                        any(
                            _quantity_entailed_by_evidence(claim, evidence)
                            for evidence in evidence_quantities
                        )
                        for claim in claim_quantities
                        if claim.unit_family != "unknown"
                    )
                    else "incompatible"
                    if evidence_quantities
                    else "unknown"
                ),
            }

    claim_years = set(_YEAR_RE.findall(claim_text))
    evidence_years = set(_YEAR_RE.findall(evidence_text))
    if claim_years:
        payload["timeframe"] = {
            "claim_value": ", ".join(sorted(claim_years)),
            "evidence_value": ", ".join(sorted(evidence_years)) or None,
            "status": (
                "compatible"
                if claim_years <= evidence_years
                else "incompatible"
                if evidence_years
                else "unknown"
            ),
        }

    claim_direction = _direction(claim_text)
    evidence_direction = _direction(evidence_text)
    if claim_direction:
        payload["direction"] = {
            "claim_value": claim_direction,
            "evidence_value": evidence_direction or None,
            "status": (
                "compatible"
                if claim_direction == evidence_direction
                else "incompatible"
                if evidence_direction
                else "unknown"
            ),
        }
    claim_geographies = _geographies(claim_text)
    evidence_geographies = _geographies(evidence_text)
    if claim_geographies:
        payload["geography"] = {
            "claim_value": ", ".join(sorted(claim_geographies)),
            "evidence_value": ", ".join(sorted(evidence_geographies)) or None,
            "status": (
                "compatible"
                if claim_geographies <= evidence_geographies
                else "incompatible"
                if evidence_geographies
                else "unknown"
            ),
        }
    claim_attribution = _attribution(claim_text)
    evidence_attribution = _attribution(evidence_text)
    if claim_attribution:
        payload["attribution"] = {
            "claim_value": claim_attribution,
            "evidence_value": evidence_attribution,
            "status": (
                "compatible"
                if claim_attribution == evidence_attribution
                else "incompatible"
                if evidence_attribution
                else "unknown"
            ),
        }
    claim_subjects = _subjects(claim_text)
    evidence_subjects = _subjects(evidence_text)
    if claim_subjects:
        payload["population"] = {
            "claim_value": claim_subjects[0],
            "evidence_value": evidence_subjects[0] if evidence_subjects else None,
            "status": (
                "compatible"
                if any(
                    _subjects_compatible(claim_subject, evidence_subject)
                    for claim_subject in claim_subjects
                    for evidence_subject in evidence_subjects
                )
                else "incompatible"
                if evidence_subjects
                else "unknown"
            ),
        }
    claim_rank = _rank(claim_text)
    evidence_rank = _rank(evidence_text)
    if claim_rank:
        payload["observation_status"] = {
            "claim_value": claim_rank,
            "evidence_value": evidence_rank,
            "status": (
                "compatible"
                if claim_rank == evidence_rank
                else "incompatible"
                if evidence_rank
                else "unknown"
            ),
        }
    claim_comparison = _comparison(claim_text)
    evidence_comparison = _comparison(evidence_text)
    if claim_comparison:
        payload["comparison"] = {
            "claim_value": claim_comparison,
            "evidence_value": evidence_comparison,
            "status": (
                "compatible"
                if claim_comparison == evidence_comparison
                else "incompatible"
                if evidence_comparison
                else "unknown"
            ),
        }
    return ProtectedFactComparison.from_payload(payload)


def _direction(text: str) -> str | None:
    for match in _DIRECTION_RE.finditer(text):
        value = match.group(0).casefold()
        if value in _UPWARD_DIRECTIONS:
            return "up"
        if value in _DOWNWARD_DIRECTIONS:
            return "down"
    return None


def _geographies(text: str) -> set[str]:
    return {
        re.sub(r"\s+", " ", match.group(0).casefold()).strip()
        for match in _GEOGRAPHY_RE.finditer(text)
    }


def _attribution(text: str) -> str | None:
    match = _ATTRIBUTION_RE.search(text)
    return match.group(1).casefold() if match else None


def _subject(text: str) -> str | None:
    subjects = _subjects(text)
    return subjects[0] if subjects else None


def _subjects(text: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            subject.removeprefix("the ")
            for match in _SUBJECT_RE.finditer(text)
            if (subject := re.sub(r"\s+", " ", match.group(1).casefold()).strip())
        )
    )


def _subjects_compatible(claim_subject: str, evidence_subject: str) -> bool:
    if claim_subject == evidence_subject:
        return True
    ignored = {
        "all",
        "and",
        "covered",
        "every",
        "for",
        "from",
        "in",
        "of",
        "one",
        "report",
        "the",
        "this",
    }
    claim_terms = {
        term.removesuffix("s")
        for term in re.findall(r"[a-z]+", claim_subject)
        if term not in ignored
    }
    evidence_terms = {
        term.removesuffix("s")
        for term in re.findall(r"[a-z]+", evidence_subject)
        if term not in ignored
    }
    return bool(claim_terms and evidence_terms and claim_terms & evidence_terms)


def _rank(text: str) -> str | None:
    match = _RANK_RE.search(text)
    if not match:
        return None
    numeric = match.group(1)
    if numeric:
        return f"rank:{numeric}"
    word = match.group(2).casefold()
    aliases = {"number one": "1", "first": "1", "second": "2", "third": "3"}
    return f"rank:{aliases.get(word, word)}"


def _comparison(text: str) -> str | None:
    match = _COMPARISON_RE.search(text)
    return re.sub(r"\s+", " ", match.group(1).casefold()).strip() if match else None


def _quantity_entailed_by_evidence(claim: object, evidence: object) -> bool:
    """Apply one-way support semantics for protected numeric facts."""

    claim_comparator = str(getattr(claim, "comparator", ""))
    evidence_comparator = str(getattr(evidence, "comparator", ""))
    if claim_comparator in {"eq", "approx"} and evidence_comparator in {
        "gt",
        "gte",
        "lt",
        "lte",
    }:
        return False
    return quantities_match(claim, evidence)  # type: ignore[arg-type]


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
