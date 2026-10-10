from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, cast

from src.contracts.soft_copy_claim_provenance import soft_copy_material_sentences
from src.utils.quantity import Quantity, extract_quantities, quantities_match

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


_YEAR = r"(?:19|20)\d{2}"
_OBSERVATION_YEAR_RE = re.compile(
    rf"\b(?:in|during|for|as of|as at|collected(?: in)?|fielded(?: in)?|"
    rf"survey(?:ed)?(?: in)?|observed(?: in)?|reported(?: in)?|"
    rf"data(?: gathered| collected)?(?: in| for)?|year ended(?: in)?)\s+"
    rf"(?:the\s+)?(?P<year>{_YEAR})(?:e)?\b"
    rf"(?!\s+(?:edition|report|publication|outlook))",
    re.IGNORECASE,
)
_MONTH_YEAR_RE = re.compile(
    rf"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    rf"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
    rf"dec(?:ember)?)\.?\s+(?P<year>{_YEAR})\b",
    re.IGNORECASE,
)
_QUARTER_YEAR_RE = re.compile(
    rf"\b(?:q[1-4]\s*(?:fy\s*)?|fy\s*)?(?P<year>{_YEAR})\s*(?:q[1-4]|e)\b|"
    rf"\bq[1-4]\s*(?:fy\s*)?(?P<quarter_year>{_YEAR})\b",
    re.IGNORECASE,
)
_OBSERVATION_RANGE_RE = re.compile(
    rf"\b(?P<start>{_YEAR})(?:e)?(?:\s+[a-z]+)?"
    rf"(?:\s+(?:to|through|until)\s+|\s*[-–]\s*)"
    rf"(?:[a-z]+\s+)?(?P<end>{_YEAR})(?:e)?\b",
    re.IGNORECASE,
)
_FORECAST_YEAR_CONTEXT_RE = re.compile(
    r"\b(?:estimate[sd]?|expect(?:s|ed|ation|ations)?|forecast(?:s|ed|ing)?|"
    r"project(?:s|ed|ion|ions)?|will|would|may|might|likely|outlook)\b",
    re.IGNORECASE,
)
_OBSERVED_YEAR_CONTEXT_RE = re.compile(
    r"\b(?:observ(?:e|ed|ation)|survey(?:ed)?|respondents?|fieldwork|"
    r"collected|data|grew|growth|increas(?:e|ed|ing)|rose|declin(?:e|ed|ing)|"
    r"fell|drop(?:ped|ping)?|reached|achieved|attained|measured|reported|"
    r"recorded|actual|historical)\b",
    re.IGNORECASE,
)
_DIRECTION_WORD = (
    r"(?:grew|growth|increas(?:e|es|ed|ing)|rose|rising|up|gain(?:s|ed)?|"
    r"declin(?:e|es|ed|ing)|decreas(?:e|s|ed|ing)|fell|falling|"
    r"drop(?:s|ped|ping)?|down|lost|loss)"
)
_UPWARD_DIRECTIONS = {
    "grew",
    "growth",
    "increase",
    "increases",
    "increased",
    "increasing",
    "rose",
    "rising",
    "up",
    "gained",
    "gain",
    "gains",
}
_DOWNWARD_DIRECTIONS = {
    "decline",
    "declines",
    "declined",
    "declining",
    "decrease",
    "decreases",
    "decreased",
    "decreasing",
    "fell",
    "falling",
    "dropped",
    "drop",
    "drops",
    "dropping",
    "down",
    "lost",
    "loss",
}
_GEOGRAPHY_RE = re.compile(
    r"(?<![A-Za-z])(?:africa|america|americas|asia|australia|europe|global|"
    r"india|china|japan|canada|mexico|brazil|france|germany|italy|spain|"
    r"sweden|norway|finland|denmark|ireland|poland|u\.s\.|us|united states|"
    r"u\.k\.|uk|united kingdom|middle east|north america|south america|"
    r"latin america|apac|emea)(?![A-Za-z])",
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
_DIRECTION_SUBJECT_RE = re.compile(
    rf"\b(?:the\s+)?(?P<subject>[A-Za-z][A-Za-z0-9&/-]*(?:\s+[A-Za-z][A-Za-z0-9&/-]*){{0,5}})"
    rf"\s+(?P<direction>{_DIRECTION_WORD})\b",
    re.IGNORECASE,
)
_RANK_RE = re.compile(
    r"(?:#\s?(\d+)|\b(number\s+one|first(?![\w-])|second(?![\w-])|"
    r"third(?![\w-])|fourth(?![\w-])|fifth(?![\w-])|largest|smallest)\b)",
    re.IGNORECASE,
)
_COMPARISON_RE = re.compile(
    r"\b(?:versus|vs\.?|compared with|compared to)\s+([^.;,:]+)", re.IGNORECASE
)
_EXPLICIT_BASELINE_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


@dataclass(frozen=True)
class _DirectionFact:
    subject: str
    direction: str
    quantity: Quantity | None
    ambiguous_quantity: bool


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
            "status": _quantity_dimension_status(
                claim_quantities, evidence_quantities
            ),
        }
        explicit_claim_quantities = [
            item for item in claim_quantities if item.unit_family != "unknown"
        ]
        evidence_units = {item.unit_family for item in evidence_quantities}
        if explicit_claim_quantities:
            payload["unit_currency"] = {
                "claim_value": ", ".join(
                    sorted({item.unit_family for item in explicit_claim_quantities})
                ),
                "evidence_value": ", ".join(sorted(evidence_units)) or None,
                "status": _quantity_unit_dimension_status(
                    explicit_claim_quantities, evidence_quantities
                ),
            }

    claim_year_facts = _observation_year_facts(claim_text)
    evidence_year_facts = _observation_year_facts(evidence_text)
    claim_years = {year for year, status in claim_year_facts if status != "unknown"}
    evidence_years = {
        year for year, status in evidence_year_facts if status != "unknown"
    }
    if claim_years:
        evidence_ranges = _observation_year_range_facts(evidence_text)
        same_status_facts = [
            (year, status)
            for year, status in claim_year_facts
            if status != "unknown"
        ]
        same_status_evidence = {
            status
            for _year, status in evidence_year_facts
            if status != "unknown"
        }
        covered = {
            (year, status)
            for year, status in same_status_facts
            if (year, status) in evidence_year_facts
            or any(
                start <= year <= end and range_status == status
                for start, end, range_status in evidence_ranges
            )
        }
        has_comparable_evidence = any(
            status in same_status_evidence for _year, status in same_status_facts
        ) or any(
            status == range_status
            for _start, _end, range_status in evidence_ranges
            for _year, status in same_status_facts
        )
        payload["timeframe"] = {
            "claim_value": ", ".join(sorted(claim_years)),
            "evidence_value": ", ".join(sorted(evidence_years)) or None,
            "status": (
                "compatible"
                if len(covered) == len(same_status_facts)
                else "incompatible"
                if has_comparable_evidence
                else "unknown"
            ),
        }

    claim_directions = _direction_facts(claim_text)
    evidence_directions = _direction_facts(evidence_text)
    if claim_directions:
        direction_status = _direction_status(claim_directions, evidence_directions)
        payload["direction"] = {
            "claim_value": ", ".join(
                sorted({fact.direction for fact in claim_directions})
            ),
            "evidence_value": ", ".join(
                sorted({fact.direction for fact in evidence_directions})
            )
            or None,
            "status": direction_status,
        }
    claim_geographies = _geographies(claim_text)
    evidence_geographies = _geographies(evidence_text)
    if claim_geographies:
        if claim_geographies <= evidence_geographies:
            geography_status: ProtectedFactStatus = "compatible"
        elif len(claim_geographies) == len(evidence_geographies) == 1:
            claim_geography = next(iter(claim_geographies))
            evidence_geography = next(iter(evidence_geographies))
            geography_status = (
                "incompatible"
                if claim_geography != evidence_geography
                and _geography_tier(claim_geography) is not None
                and _geography_tier(claim_geography)
                == _geography_tier(evidence_geography)
                else "unknown"
            )
        else:
            geography_status = "unknown"
        payload["geography"] = {
            "claim_value": ", ".join(sorted(claim_geographies)),
            "evidence_value": ", ".join(sorted(evidence_geographies)) or None,
            "status": geography_status,
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
        claim_baselines = _comparison_baselines(claim_text)
        evidence_baselines = _comparison_baselines(evidence_text)
        comparison_status: ProtectedFactStatus = "unknown"
        if len(claim_baselines) == len(evidence_baselines) == 1:
            comparison_status = (
                "compatible"
                if claim_baselines[0] == evidence_baselines[0]
                else "incompatible"
            )
        payload["comparison"] = {
            "claim_value": claim_comparison,
            "evidence_value": evidence_comparison,
            "status": comparison_status,
        }
    return ProtectedFactComparison.from_payload(payload)


def _direction_facts(text: str) -> tuple[_DirectionFact, ...]:
    facts: list[_DirectionFact] = []
    for sentence in soft_copy_material_sentences(text):
        clauses = re.split(
            r";|,(?:\s+)|\b(?:while|whereas|but)\b", sentence, flags=re.I
        )
        for clause in clauses:
            matches = list(_DIRECTION_SUBJECT_RE.finditer(clause))
            if len(matches) != 1:
                continue
            match = matches[0]
            direction_word = match.group("direction").casefold()
            direction = (
                "up"
                if direction_word in _UPWARD_DIRECTIONS
                else "down"
                if direction_word in _DOWNWARD_DIRECTIONS
                else ""
            )
            if not direction:
                continue
            quantities = [
                quantity
                for quantity in extract_quantities(clause)
                if not (
                    quantity.unit_family == "unknown"
                    and quantity.value.is_integer()
                    and 1900 <= int(quantity.value) <= 2100
                )
            ]
            facts.append(
                _DirectionFact(
                    subject=re.sub(
                        r"\s+", " ", match.group("subject").casefold()
                    ).strip(),
                    direction=direction,
                    quantity=quantities[0] if len(quantities) == 1 else None,
                    ambiguous_quantity=len(quantities) > 1,
                )
            )
    return tuple(facts)


def _direction_status(
    claim_facts: tuple[_DirectionFact, ...],
    evidence_facts: tuple[_DirectionFact, ...],
) -> ProtectedFactStatus:
    unresolved = False
    for claim in claim_facts:
        if claim.ambiguous_quantity:
            unresolved = True
            continue
        relevant = [
            evidence
            for evidence in evidence_facts
            if evidence.subject == claim.subject
            and not evidence.ambiguous_quantity
            and (
                (claim.quantity is None and evidence.quantity is None)
                or (
                    claim.quantity is not None
                    and evidence.quantity is not None
                    and quantities_match(claim.quantity, evidence.quantity)
                )
            )
        ]
        if len(relevant) != 1:
            unresolved = True
        elif relevant[0].direction != claim.direction:
            return "incompatible"
    return "unknown" if unresolved else "compatible"


def _geography_tier(value: str) -> str | None:
    if value in {
        "us",
        "uk",
        "india",
        "china",
        "japan",
        "canada",
        "mexico",
        "brazil",
        "france",
        "germany",
        "italy",
        "spain",
        "sweden",
        "norway",
        "finland",
        "denmark",
        "ireland",
        "poland",
    }:
        return "country"
    if value in {"africa", "asia", "australia", "europe"}:
        return "continent"
    return None


def _geographies(text: str) -> set[str]:
    aliases = {
        "u.s.": "us",
        "united states": "us",
        "u.k.": "uk",
        "united kingdom": "uk",
    }
    return {
        aliases.get(
            re.sub(r"\s+", " ", match.group(0).casefold()).strip(),
            re.sub(r"\s+", " ", match.group(0).casefold()).strip(),
        )
        for match in _GEOGRAPHY_RE.finditer(text)
    }


def _attribution(text: str) -> str | None:
    match = _ATTRIBUTION_RE.search(text)
    if not match:
        return None
    actor = re.sub(r"\s+", " ", match.group(1).casefold()).strip()
    if actor.split()[0] in {
        "a",
        "an",
        "annual",
        "it",
        "quarterly",
        "the",
        "this",
        "that",
        "yearly",
    }:
        return None
    return actor


def _subject(text: str) -> str | None:
    subjects = _subjects(text)
    return subjects[0] if subjects else None


def _subjects(text: str) -> tuple[str, ...]:
    discourse_subject_starts = {
        "a",
        "an",
        "and",
        "as",
        "because",
        "but",
        "expected",
        "expect",
        "forecast",
        "from",
        "not",
        "of",
        "or",
        "reported",
        "that",
        "to",
        "whereas",
        "while",
    }
    leading_discourse_connectors = {"and", "or", "alongside"}
    quantities = extract_quantities(text)
    subjects: list[str] = []
    for match in _SUBJECT_RE.finditer(text):
        subject = re.sub(r"\s+", " ", match.group(1).casefold()).strip()
        subject_words = subject.split()
        while subject_words and subject_words[0] in leading_discourse_connectors:
            subject_words.pop(0)
        subject = " ".join(subject_words)
        if (
            not subject
            or subject.split()[0] in discourse_subject_starts
            or re.search(
                r"\b(?:expect|expected|expectation|reported|forecast)\b", subject
            )
        ):
            continue
        if any(
            quantity.start <= match.start(1) and match.end(1) <= quantity.end
            for quantity in quantities
        ):
            continue
        subjects.append(subject.removeprefix("the "))
    return tuple(dict.fromkeys(subjects))


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


def _observation_year_facts(text: str) -> tuple[tuple[str, str], ...]:
    facts: list[tuple[str, str]] = []
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text):
        years = {
            match.group("year")
            for pattern in (_OBSERVATION_YEAR_RE, _MONTH_YEAR_RE)
            for match in pattern.finditer(sentence)
        }
        for match in _QUARTER_YEAR_RE.finditer(sentence):
            years.add(match.group("year") or match.group("quarter_year"))
        ranges = list(_OBSERVATION_RANGE_RE.finditer(sentence))
        for match in ranges:
            years.update((match.group("start"), match.group("end")))
        if not years:
            continue
        status = (
            "forecast"
            if _FORECAST_YEAR_CONTEXT_RE.search(sentence)
            else "observed"
            if _OBSERVED_YEAR_CONTEXT_RE.search(sentence)
            else "unknown"
        )
        facts.extend((year, status) for year in sorted(years))
    return tuple(dict.fromkeys(facts))


def _observation_year_range_facts(text: str) -> tuple[tuple[str, str, str], ...]:
    ranges: list[tuple[str, str, str]] = []
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text):
        status = (
            "forecast"
            if _FORECAST_YEAR_CONTEXT_RE.search(sentence)
            else "observed"
            if _OBSERVED_YEAR_CONTEXT_RE.search(sentence)
            else "unknown"
        )
        ranges.extend(
            (match.group("start"), match.group("end"), status)
            for match in _OBSERVATION_RANGE_RE.finditer(sentence)
        )
    return tuple(dict.fromkeys(ranges))


def _comparison(text: str) -> str | None:
    match = _COMPARISON_RE.search(text)
    return re.sub(r"\s+", " ", match.group(1).casefold()).strip() if match else None


def _comparison_baselines(text: str) -> list[str]:
    baselines: list[str] = []
    for match in _COMPARISON_RE.finditer(text):
        years = _EXPLICIT_BASELINE_YEAR_RE.findall(match.group(1))
        if len(years) != 1:
            return []
        baselines.append(years[0])
    return baselines


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


def _quantity_dimension_status(
    claims: list[Quantity], evidence: list[Quantity]
) -> ProtectedFactStatus:
    if all(
        any(_quantity_entailed_by_evidence(claim, source) for source in evidence)
        for claim in claims
    ):
        return "compatible"
    if len(claims) == len(evidence) == 1:
        return "incompatible"
    return "unknown"


def _quantity_unit_dimension_status(
    claims: list[Quantity], evidence: list[Quantity]
) -> ProtectedFactStatus:
    if all(
        any(
            claim.unit_family == source.unit_family and claim.unit == source.unit
            for source in evidence
        )
        for claim in claims
    ):
        return "compatible"
    if len(claims) == len(evidence) == 1:
        return "incompatible"
    return "unknown"


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
