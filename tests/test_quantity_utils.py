from __future__ import annotations

from src.generators.validation.quantities import quantities_match_numeric_only
from src.utils.quantity import extract_quantities, quantities_match


def _first(text: str):
    values = extract_quantities(text)
    assert values, f"No quantities parsed for: {text}"
    for quantity in values:
        if quantity.unit_family != "unknown":
            return quantity
    return values[0]


def _any_match(left: str, right: str) -> bool:
    left_q = extract_quantities(left)
    right_q = extract_quantities(right)
    for candidate in left_q:
        for evidence in right_q:
            if quantities_match(candidate, evidence):
                return True
    return False


def _numeric_grounding_match(left: str, right: str) -> bool:
    return quantities_match_numeric_only(_first(left), _first(right))


def test_extract_quantities_captures_generic_units_and_timeframes() -> None:
    parsed = extract_quantities(
        "Revenue was more than $10B and conversion reached 37.0% in Q3 2025."
    )
    assert any(
        q.unit_family == "currency" and q.comparator in {"gt", "gte"} for q in parsed
    )
    assert any(q.unit_family == "percent" for q in parsed)
    assert any("q3 2025" in q.timeframe for q in parsed if q.timeframe)


def test_percent_decimal_and_ratio_forms_match() -> None:
    assert _any_match("1 in 10 respondents converted.", "Conversion reached 10%.")
    assert _any_match("Conversion rate was 0.1.", "Conversion reached 10%.")
    assert _any_match("0.5% churn", "0.005 churn rate")


def test_currency_magnitude_forms_match() -> None:
    assert _any_match("$3M in spend", "3 million USD spend")
    assert _any_match("€2.1bn revenue", "2,100,000,000 EUR revenue")
    assert _any_match("£333mn annual spend", "333 million GBP annual spend")


def test_month_unit_is_not_parsed_as_million_magnitude() -> None:
    parsed = extract_quantities("Actions for the next 12 months: integrate checks.")
    assert any(q.unit_family == "time" and q.unit == "months" for q in parsed)
    assert not any(q.value == 12_000_000 for q in parsed)


def test_percentage_points_require_change_context() -> None:
    assert not _any_match("Satisfaction is 3pp.", "Satisfaction is 3%.")
    assert _any_match(
        "Change in satisfaction was 3pp.", "Change in satisfaction was 3%."
    )


def test_ranges_approx_and_sample_size() -> None:
    assert _any_match("between 10 and 12%", "11%")
    assert _any_match("10-12% adoption", "between 10 and 12 percent adoption")
    parsed = extract_quantities("Survey results (N=4,500) show rising adoption.")
    assert any(q.unit_family == "count" and q.value == 4500 for q in parsed)


def test_property_like_equivalent_surface_forms() -> None:
    groups = [
        [
            "37%",
            "37.0%",
            "37 percent",
        ],
        [
            "$3M",
            "3 million USD",
            "3,000,000 USD",
        ],
        [
            "more than $10 billion",
            ">10 USD bn",
            "over 10B usd",
        ],
        [
            "1 in 10",
            "10%",
            "0.1 conversion rate",
        ],
    ]
    for group in groups:
        parsed = [_first(value) for value in group]
        for i, candidate in enumerate(parsed):
            for j, evidence in enumerate(parsed):
                if i == j:
                    continue
                assert quantities_match(candidate, evidence), (
                    f"Expected match for {group[i]} <-> {group[j]}"
                )


def test_numeric_grounding_canonicalizes_equivalent_quantity_displays() -> None:
    """Removing a canonical primitive must reject numeric-only grounding."""
    equivalents = [
        ("$3.0T", "$3 trillion"),
        ("20%", "20 percent"),
        ("2x", "2 times"),
        ("10-12%", "between 10 and 12 percent"),
        ("-20%", "-20 percent"),
        ("$3T in Q1 2025", "$3 trillion in Q1 2025"),
    ]
    for candidate, evidence in equivalents:
        assert _numeric_grounding_match(candidate, evidence), (
            f"Expected canonical numeric grounding for {candidate!r} and {evidence!r}"
        )


def test_numeric_grounding_rejects_changed_quantity_primitives() -> None:
    """Erasing an explicit primitive must not make two quantities match."""
    inequivalents = [
        ("20%", "20 percentage points"),
        ("$3B", "$3T"),
        ("$3T", "€3T"),
        ("2x", "2%"),
        ("10-12%", "10-13%"),
        ("-20%", "20%"),
        ("20 users", "20 downloads"),
        ("$3T in Q1 2025", "$3 trillion in Q2 2025"),
    ]
    for candidate, evidence in inequivalents:
        assert not _numeric_grounding_match(candidate, evidence), (
            f"Unexpected numeric grounding for {candidate!r} and {evidence!r}"
        )
