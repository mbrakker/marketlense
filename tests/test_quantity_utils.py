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


def test_calendar_year_pair_near_percentage_is_not_a_percentage_range() -> None:
    parsed = extract_quantities(
        "Q3 and Q4 contributed 54% of total revenue in both 2023 and 2024."
    )

    assert [(q.value, q.unit_family) for q in parsed] == [(54.0, "percent")]


def test_compact_year_range_end_is_not_parsed_as_a_metric_number() -> None:
    parsed = extract_quantities(
        "In 2015–20, born-tech companies accounted for 52% of growth, "
        "while a tech-led strategy accounted for 20%."
    )

    assert [(quantity.value, quantity.unit_family) for quantity in parsed] == [
        (52.0, "percent"),
        (20.0, "percent"),
    ]


def test_n_equals_sample_size_is_not_reclassified_by_nearby_percentages() -> None:
    parsed = extract_quantities(
        "Among respondents in the total n=220 sample, 58% wanted more offers."
    )

    assert [(quantity.value, quantity.unit_family) for quantity in parsed] == [
        (220.0, "count"),
        (58.0, "percent"),
    ]


def test_percent_decimal_and_ratio_forms_match() -> None:
    assert _any_match("1 in 10 respondents converted.", "Conversion reached 10%.")
    assert _any_match("Conversion rate was 0.1.", "Conversion reached 10%.")
    assert _any_match("0.5% churn", "0.005 churn rate")


def test_spelled_ratio_matches_source_using_numeric_of_form() -> None:
    assert _numeric_grounding_match(
        "Four in five consumers shop online weekly.",
        "4 of 5 consumers shop online weekly.",
    )
    assert not _numeric_grounding_match(
        "Three in five consumers shop online weekly.",
        "4 of 5 consumers shop online weekly.",
    )


def test_decimal_values_followed_by_years_are_not_parsed_as_ratios() -> None:
    parsed = extract_quantities(
        "Global finance app day 0 sessions per user declined from 1.52 in 2024 "
        "to 1.48 in 2025."
    )

    assert not any(quantity.unit_family == "ratio" for quantity in parsed)
    assert any(quantity.value == 1.52 for quantity in parsed)


def test_hyphenated_percentage_point_matches_spelled_out_points() -> None:
    """A hyphenated "percentage-point" is pp, not a percent value.

    Regression: "a 24 percentage-point increase" prefix-matched "percent"
    inside "percentage-point" and canonicalized to percent, so evidence that
    states the same fact as "24 percentage points" could never ground it and
    the numbers gate blocked an Emplifi report with
    "Number 24.0 not present in report or evidence".
    """

    assert _first("a 24 percentage-point increase").unit_family == "points"
    assert _first("a 24 percentage-point increase").unit == "pp"
    assert _numeric_grounding_match(
        "a 24 percentage-point increase",
        "research time increases by 24 percentage points",
    )
    assert _numeric_grounding_match(
        "a 2 basis-point cut",
        "yields fell 2 basis points",
    )


def test_unit_word_boundary_does_not_absorb_prose() -> None:
    """A unit match must not consume the prefix of a longer word."""

    parsed = extract_quantities("Adoption reached 56 percentage globally.")
    assert all(q.unit != "percent" for q in parsed)
    assert _any_match("Support grew 5 percent.", "Support grew 5 percent.")


def test_currency_magnitude_forms_match() -> None:
    assert _any_match("$3M in spend", "3 million USD spend")
    assert _any_match("€2.1bn revenue", "2,100,000,000 EUR revenue")
    assert _any_match("£333mn annual spend", "333 million GBP annual spend")


def test_percent_precision_and_canonical_magnitude_displays_match() -> None:
    assert _any_match("50.0%", "50%")
    assert _any_match("$3 trillion", "$3T")
    assert _any_match("3T", "3000B")
    assert not _any_match("42%", "43%")
    assert not _any_match("18%", "$18m")


def test_financial_magnitude_abbreviations_match_their_canonical_forms() -> None:
    assert _any_match("200+ mil globally", "200+ million globally")
    assert _any_match("$450 bil", "$450B")


def test_uk_initialism_does_not_turn_a_nearby_percentage_into_thousands() -> None:
    parsed = extract_quantities("50% of U.K. media experts expressed interest.")

    assert [(quantity.value, quantity.magnitude) for quantity in parsed] == [(50.0, "")]
    assert _any_match("50% of U.K. media experts", "50 percent of media experts")


def test_month_unit_is_not_parsed_as_million_magnitude() -> None:
    parsed = extract_quantities("Actions for the next 12 months: integrate checks.")
    assert any(q.unit_family == "time" and q.unit == "months" for q in parsed)
    assert not any(q.value == 12_000_000 for q in parsed)


def test_semicolon_does_not_join_a_year_to_the_following_count_noun() -> None:
    parsed = extract_quantities(
        "The survey was published in 2024; respondents described their priorities."
    )
    explicitly_counted = extract_quantities(
        "The survey included 2024 respondents who described their priorities."
    )

    assert not any(
        quantity.unit_family == "count" and quantity.unit == "respondent"
        for quantity in parsed
    )
    assert any(
        quantity.value == 2024
        and quantity.unit_family == "count"
        and quantity.unit == "respondent"
        for quantity in explicitly_counted
    )


def test_duration_is_one_time_quantity_and_preserves_its_timeframe() -> None:
    parsed = extract_quantities("Average daily viewing is 0:52 in 2024E.")

    assert [(q.raw, q.value, q.unit_family, q.unit) for q in parsed] == [
        ("0:52", 52.0, "time", "minutes")
    ]
    assert parsed[0].timeframe == "2024e"


def test_percentages_keep_their_nearest_year_in_a_multi_year_sentence() -> None:
    parsed = extract_quantities(
        "In the 2026 edition, the 2025 report records 42% for user intent, "
        "up from 34% in 2024."
    )

    assert [
        (quantity.value, quantity.timeframe)
        for quantity in parsed
        if quantity.unit_family == "percent"
    ] == [(42.0, "2025"), (34.0, "2024")]


def test_duration_numeric_grounding_rejects_a_different_minute_value() -> None:
    assert _numeric_grounding_match("0:52 in 2024E", "0:52 in 2024E")
    assert not _numeric_grounding_match("0:48 in 2024E", "0:52 in 2024E")


def test_data_rate_units_match_across_source_and_public_prose() -> None:
    assert _numeric_grounding_match(
        "Median mobile speed was 59.61 Mbps.",
        "Mobile speed reached 59.61 Mbps.",
    )
    assert _first("Median mobile speed was 59.61 Mbps.").unit_family == "data_rate"


def test_count_unit_is_found_after_descriptive_words_following_a_magnitude() -> None:
    assert _numeric_grounding_match(
        "9.25 million social media users represented the population.",
        "9.25 million users",
    )


def test_numeric_grounding_matches_standalone_key_figure_value_to_timed_source() -> (
    None
):
    assert _numeric_grounding_match(
        "9.88 million users",
        "There were 9.88 million internet users in January 2022.",
    )


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


def test_extract_quantities_does_not_treat_year_to_percent_as_a_range() -> None:
    """A year used as a comparison point must not become a percentage range."""

    parsed = extract_quantities(
        "Retail Search increased from 16.3% in 2024 to 17.8% in 2025."
    )

    assert not any(q.value == 1020.9 for q in parsed)
    assert any(q.value == 17.8 and q.unit_family == "percent" for q in parsed)


def test_extract_quantities_does_not_join_a_year_to_a_timed_measurement() -> None:
    """A period year must not pair with the next timed value as a range."""

    parsed = extract_quantities(
        "Session length declined from 10.04 minutes in 2024 to 9.6 minutes "
        "in 2025."
    )

    assert not any(quantity.value == 1016.8 for quantity in parsed)
    assert [
        (quantity.value, quantity.unit_family)
        for quantity in parsed
        if quantity.unit_family == "time"
    ] == [(10.04, "time"), (9.6, "time")]


def test_quantity_match_normalizes_hyphenated_user_count_noun() -> None:
    """A hyphenated user-count noun must retain the same source quantity."""

    assert _numeric_grounding_match(
        "its 9.25 million-user total may not represent unique individuals.",
        "Kepios reported 9.25 million social media users.",
    )


def test_hyphenated_forecast_duration_matches_the_same_spaced_duration() -> None:
    """Temporal compounds keep their explicit duration unit for grounding."""

    assert _numeric_grounding_match(
        "the next-12-month findings",
        "the next 12 months",
    )
    assert not _numeric_grounding_match(
        "the next-13-month findings",
        "the next 12 months",
    )


def test_extract_quantities_ignores_year_range_endpoint_and_b2b_token() -> None:
    """Date spans and B2B labels must not become public numeric claims."""

    parsed = extract_quantities(
        "Revenue grows in 2020E–2024E while B2B commercial models expand."
    )

    assert not any(quantity.value == -2024.0 for quantity in parsed)
    assert not any(quantity.value == 2_000_000_000.0 for quantity in parsed)


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


def test_hyphenated_prose_compound_is_not_a_signed_quantity() -> None:
    parsed = extract_quantities(
        "Review onboarding promises, first-90-day communication, and support."
    )
    assert [quantity.value for quantity in parsed] == [90.0]
    candidate = extract_quantities("first-90-day communication")[0]
    bare_ninety = extract_quantities("90")[0]
    assert quantities_match_numeric_only(candidate, bare_ninety) is True


def test_signed_and_spaced_negative_quantities_stay_negative() -> None:
    attached = extract_quantities("Revenue fell -90 percent.")
    spaced = extract_quantities("Revenue fell - 9 percent.")
    assert [quantity.value for quantity in attached] == [-90.0]
    assert [quantity.value for quantity in spaced] == [-9.0]


def test_designation_compound_extracts_positive_year_number() -> None:
    parsed = extract_quantities("COVID-19-era spending changed.")
    assert 19.0 in [quantity.value for quantity in parsed]
