from src.generators.artifact_normalization import (
    eligible_final_insight_candidates,
    normalize_artifact_insights,
    preserve_public_source_displays,
    select_artifact_insights,
)


def test_insight_normalization_collapses_ocr_double_numeric_signs() -> None:
    normalized = normalize_artifact_insights(
        [
            {
                "id": "time-spend",
                "text": "Social media changed by −-5% after shelter in place.",
                "evidence_id": "f1",
                "evidence": "Social media changed by -5% after shelter in place.",
            }
        ],
        prefix="insight",
    )

    assert normalized[0]["text"] == (
        "Social media changed by −5% after shelter in place."
    )


def test_preservation_replaces_an_unsupported_insight_number_and_clears_metric() -> (
    None
):
    summary = {"claim_evidence_map": []}
    evidence = "Private-label expansion is one of the trends expected through 2026."
    insights = [
        {
            "id": "private-label",
            "text": "Private labels contributed +3.6% to global value growth.",
            "evidence_id": "trend-1",
            "evidence": evidence,
            "metric": {
                "label": "Private-label contribution",
                "value": "+3.6%",
                "unit": "percent",
                "timeframe": "MAT",
                "trend": "growth",
            },
        }
    ]

    preserve_public_source_displays(
        summary=summary,
        insights_final=insights,
        expert_comment="",
        linkedin_post="",
    )

    assert (
        insights[0]["text"]
        == "Private labels contributed +3.6% to global value growth."
    )
    assert insights[0]["metric"]["value"] == "+3.6%"
    assert insights[0]["metric"]["label"] == "Private-label contribution"
    assert insights[0]["metric"]["timeframe"] == "MAT"


def test_select_artifact_insights_uses_each_stable_id_once():
    candidates = [
        {
            "id": f"insight-{index}",
            "text": f"Distinct source finding for category {index}.",
            "evidence_id": f"finding-{index}",
        }
        for index in range(6)
    ]
    final = [dict(item) for item in candidates[:5]]
    final.insert(
        1, {**candidates[0], "text": "Different wording for the first finding."}
    )

    selected = select_artifact_insights(
        final_insights=final,
        candidate_insights=candidates,
        editorial_plan={
            "report_thesis": "Distinct findings describe the market.",
            "themes": [
                {"theme": "First", "priority": 1, "evidence_ids": ["finding-0"]},
                {"theme": "Second", "priority": 2, "evidence_ids": ["finding-1"]},
            ],
        },
    )

    assert len(selected) == 5
    assert len({item["id"] for item in selected}) == len(selected)
    assert next(item for item in selected if item["id"] == "insight-0") == final[0]


def test_select_artifact_insights_preserves_chosen_candidate_factual_fields():
    """Candidate→final selection must not carry final-stage factual drift.

    This is the DHL/SimilarWeb mutation shape: the final model rewrote the
    same-stable-ID insight with a drifted metric display. Selection keeps the
    final editorial wording but deterministically restores the chosen
    candidate's protected factual fields.
    """
    plan = {
        "report_thesis": "The report supports grounded decisions.",
        "themes": [
            {"theme": "Margin", "priority": 1, "evidence_ids": ["f1"]},
            {"theme": "Retention", "priority": 2, "evidence_ids": ["f2"]},
            {"theme": "Reach", "priority": 3, "evidence_ids": ["f3"]},
        ],
    }
    candidate_metric = {
        "label": "Europe margin",
        "value": "46%",
        "unit": "%",
        "trend": "",
        "timeframe": "2025",
        "geography": "Europe",
        "segment": "",
        "sample_size": "",
        "confidence": "",
    }
    drifted_metric = {
        "label": "Drifted label",
        "value": "99%",
        "unit": "%",
        "trend": "",
        "timeframe": "2024",
        "geography": "Global",
        "segment": "",
        "sample_size": "",
        "confidence": "",
    }
    candidate_insights = [
        {
            "id": "insight-1",
            "text": "Margin reached 46% in Europe during 2025.",
            "evidence_id": "f1",
            "metric": dict(candidate_metric),
            "pages": [3],
        },
        {
            "id": "insight-2",
            "text": "Retention held at 88%.",
            "evidence_id": "f2",
        },
    ]
    final_insights = [
        {
            # Same stable ID, drifted editorial wording AND drifted facts.
            "id": "insight-1",
            "text": "Margin improved to 46% in Europe in 2025.",
            "evidence_id": "f1",
            "metric": dict(drifted_metric),
            "pages": [3],
        },
    ]

    selected = select_artifact_insights(
        final_insights=final_insights,
        candidate_insights=candidate_insights,
        editorial_plan=plan,
    )

    repaired = next(item for item in selected if item["id"] == "insight-1")
    assert repaired["text"] == "Margin improved to 46% in Europe in 2025."
    for field_name, value in candidate_metric.items():
        assert repaired["metric"][field_name] == value
    # A stable-ID insight without a matching candidate keeps its own facts.
    untouched = next(item for item in selected if item["id"] == "insight-2")
    assert untouched["text"] == "Retention held at 88%."


def test_verified_selection_preserves_complete_candidate_metric_extensions():
    candidate_metric = {
        "label": "Composite adoption",
        "value": "42%",
        "unit": "%",
        "observations": [
            {"population": "new buyers", "period": "2026", "value": "42%"}
        ],
        "report_specific_method": {
            "denominator_rule": "eligible respondents",
            "weighting": "region-adjusted",
        },
    }
    selected = select_artifact_insights(
        final_insights=[
            {
                "id": "insight-1",
                "text": "Editorial wording remains concise.",
                "evidence_id": "f1",
                "metric": {
                    "label": "Unsupported final metric",
                    "value": "99%",
                    "unit": "%",
                    "final_only_context": "not authoritative",
                },
            }
        ],
        candidate_insights=[
            {
                "id": "insight-1",
                "text": "The candidate fact is source-backed.",
                "evidence_id": "f1",
                "metric": candidate_metric,
            }
        ],
        editorial_plan={
            "report_thesis": "The canonical fact remains authoritative.",
            "themes": [
                {"theme": "Theme 1", "priority": 1, "evidence_ids": ["f1"]},
                {"theme": "Theme 2", "priority": 2, "evidence_ids": ["f2"]},
            ],
        },
        verified_mode=True,
    )

    metric = selected[0]["metric"]
    assert metric["value"] == "42%"
    assert metric["observations"] == candidate_metric["observations"]
    assert (
        metric["report_specific_method"] == candidate_metric["report_specific_method"]
    )
    assert "final_only_context" not in metric


def test_verified_selection_scopes_composite_metric_to_final_observation() -> None:
    candidate_metric = {
        "label": "Global e-commerce CPI",
        "value": "Global: $1.00 in 2024; $0.98 in 2025",
        "unit": "USD per install",
        "trend": "Down overall; deal discovery up",
        "timeframe": "2024-2025",
        "geography": "Global",
        "segment": "E-commerce apps and named subverticals",
        "cohort": "Global e-commerce apps; deal discovery and shopping",
        "observation_status": "Reported values; not identified as forecasts",
        "forecast_status": "Not identified as a forecast",
        "observations": [
            {
                "label": "Deal discovery CPI",
                "value": "2024: $1.44; 2025: $2.26",
                "unit": "USD per install",
                "timeframe": "2024-2025",
                "segment": "Deal discovery",
                "geography": "Global",
                "cohort": "E-commerce apps",
                "observation_status": "Reported values; not identified as forecasts",
            },
            {
                "label": "Shopping CPI",
                "value": "2024: $0.93; 2025: $0.91",
                "unit": "USD per install",
                "timeframe": "2024-2025",
                "segment": "Shopping",
                "geography": "Global",
                "cohort": "E-commerce apps",
                "observation_status": "Reported values; not identified as forecasts",
            },
        ],
    }
    selected = select_artifact_insights(
        final_insights=[
            {
                "id": "ecommerce-cpi",
                "text": (
                    "Global e-commerce deal discovery CPI rose from $1.44 in 2024 "
                    "to $2.26 in 2025."
                ),
                "evidence_id": "final-only",
                "metric": {
                    "label": "Global deal discovery CPI",
                    "value": "from $1.44 in 2024 to $2.26 in 2025",
                    "unit": "USD per install",
                    "trend": "Increased",
                    "timeframe": "2024-2025",
                    "geography": "Global",
                    "segment": "Deal discovery",
                    "cohort": "E-commerce apps",
                    "observation_status": (
                        "Reported values; not identified as forecasts"
                    ),
                    "forecast_status": "Not identified as a forecast",
                },
            }
        ],
        candidate_insights=[
            {
                "id": "ecommerce-cpi",
                "text": "The retained composite CPI fact.",
                "evidence_id": "verified-fact:ecommerce-cpi",
                "evidence": "The source reports all e-commerce CPI observations.",
                "pages": [29],
                "metric": candidate_metric,
            }
        ],
        editorial_plan={
            "report_thesis": "Composite source facts remain authoritative.",
            "themes": [
                {
                    "theme": "Acquisition economics",
                    "priority": 1,
                    "evidence_ids": ["verified-fact:ecommerce-cpi"],
                },
                {
                    "theme": "Subvertical differences",
                    "priority": 2,
                    "evidence_ids": ["verified-fact:ecommerce-cpi"],
                },
            ],
        },
        verified_mode=True,
    )

    metric = selected[0]["metric"]
    assert selected[0]["text"].startswith("Global e-commerce deal discovery CPI")
    assert selected[0]["evidence_id"] == "verified-fact:ecommerce-cpi"
    assert selected[0]["pages"] == [29]
    assert metric["label"] == "Global e-commerce CPI"
    assert metric["value"] == candidate_metric["value"]
    assert metric["segment"] == "E-commerce apps and named subverticals"
    assert metric["cohort"] == "Global e-commerce apps; deal discovery and shopping"
    assert metric["observations"] == candidate_metric["observations"]


def test_verified_selection_keeps_full_composite_when_final_metric_is_sparse() -> None:
    candidate_metric = {
        "label": "Global e-commerce CPI",
        "value": (
            "Overall: $1.00 to $0.98; deal discovery: $1.44 to $2.26; "
            "shopping: $0.93 to $0.91"
        ),
        "unit": "USD per install",
        "timeframe": "2024 to 2025",
        "geography": "Global",
        "segment": "E-commerce apps",
        "observations": [
            {
                "label": "All e-commerce apps",
                "value": "$1.00 in 2024; $0.98 in 2025",
                "unit": "USD per install",
                "timeframe": "2024 to 2025",
                "segment": "All",
                "geography": "Global",
            },
            {
                "label": "Deal discovery",
                "value": "$1.44 in 2024; $2.26 in 2025",
                "unit": "USD per install",
                "timeframe": "2024 to 2025",
                "segment": "Deal discovery",
                "geography": "Global",
            },
            {
                "label": "Shopping",
                "value": "$0.93 in 2024; $0.91 in 2025",
                "unit": "USD per install",
                "timeframe": "2024 to 2025",
                "segment": "Shopping",
                "geography": "Global",
            },
        ],
    }
    selected = select_artifact_insights(
        final_insights=[
            {
                "id": "ecommerce-cpi",
                "text": (
                    "Overall global e-commerce CPI fell from $1.00 to $0.98; "
                    "deal discovery rose from $1.44 to $2.26; shopping fell "
                    "from $0.93 to $0.91."
                ),
                "evidence_id": "final-only",
                "metric": {
                    "label": "Global e-commerce CPI",
                    "value": "$1.00 in 2024 to $0.98 in 2025",
                    "unit": "USD per install",
                    "timeframe": "2024 to 2025",
                    "geography": "Global",
                    "segment": "E-commerce apps",
                },
            }
        ],
        candidate_insights=[
            {
                "id": "ecommerce-cpi",
                "text": "The retained composite CPI fact.",
                "evidence_id": "verified-fact:ecommerce-cpi",
                "evidence": "The source reports all e-commerce CPI observations.",
                "pages": [29],
                "metric": candidate_metric,
            }
        ],
        editorial_plan={
            "report_thesis": "Composite source facts remain authoritative.",
            "themes": [
                {
                    "theme": "Acquisition economics",
                    "priority": 1,
                    "evidence_ids": ["verified-fact:ecommerce-cpi"],
                },
                {
                    "theme": "Subvertical differences",
                    "priority": 2,
                    "evidence_ids": ["verified-fact:ecommerce-cpi"],
                },
            ],
        },
        verified_mode=True,
    )

    assert selected[0]["text"].startswith("Overall global e-commerce CPI")
    assert selected[0]["evidence_id"] == "verified-fact:ecommerce-cpi"
    assert selected[0]["metric"]["label"] == candidate_metric["label"]
    assert selected[0]["metric"]["value"] == candidate_metric["value"]
    assert selected[0]["metric"]["observations"] == candidate_metric["observations"]


def test_verified_selection_preserves_units_on_bare_composite_observations() -> None:
    candidate_metric = {
        "label": "Finance app install and session growth",
        "value": "Installs: -4%; sessions: +21%",
        "unit": "percent year-over-year change",
        "timeframe": "2025 vs. 2024",
        "geography": "Global",
        "segment": "Finance apps",
        "observations": [
            {
                "label": "Finance app installs",
                "value": "-4",
                "unit": "% year over year",
                "timeframe": "2025 vs. 2024",
                "geography": "Global",
                "segment": "Finance apps",
            },
            {
                "label": "Finance app sessions",
                "value": "+21",
                "unit": "% year over year",
                "timeframe": "2025 vs. 2024",
                "geography": "Global",
                "segment": "Finance apps",
            },
        ],
    }
    selected = select_artifact_insights(
        final_insights=[
            {
                "id": "finance-install-session-divergence",
                "text": (
                    "Globally, finance-app installs fell 4% year over year in 2025, "
                    "while sessions rose 21%."
                ),
                "evidence_id": "editorial-only",
                "metric": {
                    "label": "Finance app install and session growth",
                    "value": "Installs: -4%; sessions: +21%",
                    "unit": "percent year-over-year change",
                    "timeframe": "2025 vs. 2024",
                    "geography": "Global",
                    "segment": "Finance apps",
                },
            }
        ],
        candidate_insights=[
            {
                "id": "finance-install-session-divergence",
                "text": "The retained finance-app composite fact.",
                "evidence_id": "verified-fact:finance-install-session-divergence",
                "evidence": "The source reports installs and sessions.",
                "pages": [34],
                "metric": candidate_metric,
            }
        ],
        editorial_plan={
            "report_thesis": "The composite fact remains authoritative.",
            "themes": [
                {
                    "theme": "Acquisition",
                    "priority": 1,
                    "evidence_ids": [
                        "verified-fact:finance-install-session-divergence"
                    ],
                },
                {
                    "theme": "Engagement",
                    "priority": 2,
                    "evidence_ids": [
                        "verified-fact:finance-install-session-divergence"
                    ],
                },
            ],
        },
        verified_mode=True,
    )

    assert selected[0]["metric"]["observations"] == candidate_metric["observations"]


def test_verified_selection_preserves_composite_with_qualitative_aggregate_observation() -> (
    None
):
    candidate_metric = {
        "label": "Finance app CPI",
        "value": (
            "Global: $1.51 to $1.13; Europe: $7.37 to $4.75; "
            "North America: $7.03 to $4.13"
        ),
        "unit": "USD",
        "timeframe": "2024 to 2025",
        "geography": "Global, Europe, and North America",
        "segment": "Finance apps",
        "observations": [
            {
                "label": "Global CPI, 2024 to 2025",
                "value": "$1.51 to $1.13",
                "unit": "USD",
                "timeframe": "2024 to 2025",
                "geography": "Global",
                "segment": "Finance apps",
            },
            {
                "label": "Europe CPI, 2024 to 2025",
                "value": "$7.37 to $4.75",
                "unit": "USD",
                "timeframe": "2024 to 2025",
                "geography": "Europe",
                "segment": "Finance apps",
            },
            {
                "label": "North America CPI, 2024 to 2025",
                "value": "$7.03 to $4.13",
                "unit": "USD",
                "timeframe": "2024 to 2025",
                "geography": "North America",
                "segment": "Finance apps",
            },
            {
                "label": "All regions shown",
                "value": "2025 CPI is lower than 2024 CPI in each region category",
                "unit": "Direction",
                "timeframe": "2024 to 2025",
                "geography": "Global, Europe, and North America",
                "segment": "Finance apps",
            },
        ],
    }
    selected = select_artifact_insights(
        final_insights=[
            {
                "id": "finance-cpi-regional-changes",
                "text": (
                    "Finance app CPI decreased from 2024 to 2025 in every region "
                    "shown. It fell from $1.51 to $1.13 globally, from $7.37 to "
                    "$4.75 in Europe, and from $7.03 to $4.13 in North America."
                ),
                "evidence_id": "editorial-only",
                "metric": {
                    "label": "Finance app CPI",
                    "value": (
                        "Global: $1.51 to $1.13; Europe: $7.37 to $4.75; "
                        "North America: $7.03 to $4.13"
                    ),
                    "unit": "USD",
                    "timeframe": "2024 to 2025",
                    "geography": "Global, Europe, and North America",
                    "segment": "Finance apps",
                },
            }
        ],
        candidate_insights=[
            {
                "id": "finance-cpi-regional-changes",
                "text": "The retained regional CPI fact.",
                "evidence_id": "verified-fact:finance-cpi-regional-changes",
                "evidence": "The source reports regional CPI changes.",
                "pages": [35],
                "metric": candidate_metric,
            }
        ],
        editorial_plan={
            "report_thesis": "Regional CPI differences remain authoritative.",
            "themes": [
                {
                    "theme": "Acquisition economics",
                    "priority": 1,
                    "evidence_ids": ["verified-fact:finance-cpi-regional-changes"],
                },
                {
                    "theme": "Regional divergence",
                    "priority": 2,
                    "evidence_ids": ["verified-fact:finance-cpi-regional-changes"],
                },
            ],
        },
        verified_mode=True,
    )

    assert selected[0]["metric"]["observations"] == candidate_metric["observations"]


def test_verified_fact_projection_remains_eligible_without_composite_rebinding() -> (
    None
):
    metric = {
        "label": "Global e-commerce CPI",
        "value": "Overall: $1.00 to $0.98; deal discovery: $1.44 to $2.26",
        "unit": "USD per install",
        "observations": [
            {
                "label": "All e-commerce apps",
                "value": "$1.00 in 2024; $0.98 in 2025",
                "unit": "USD per install",
                "segment": "All",
            },
            {
                "label": "Deal discovery",
                "value": "$1.44 in 2024; $2.26 in 2025",
                "unit": "USD per install",
                "segment": "Deal discovery",
            },
        ],
    }
    candidate = {
        "id": "ecommerce-cpi",
        "verified_fact_id": "ecommerce-cpi",
        "text": "The authoritative composite CPI fact.",
        "evidence_id": "verified-fact:ecommerce-cpi",
        "evidence": "The source reports the composite CPI fact.",
        "pages": [29],
        "evidence_spans": [
            {
                "evidence_id": "verified-fact:ecommerce-cpi",
                "source_pack": "verified_facts",
                "page": 29,
                "text": "The source reports the composite CPI fact.",
            }
        ],
        "metric": metric,
        "verified_fact": {
            "fact_id": "ecommerce-cpi",
            "statement": "The authoritative composite CPI fact.",
            "metric": metric,
            "source_identity": "source:adjust",
        },
    }

    eligible = eligible_final_insight_candidates([candidate])

    assert len(eligible) == 1
    assert eligible[0]["text"] == candidate["text"]
    assert eligible[0]["metric"] == metric
    assert eligible[0]["evidence_id"] == candidate["evidence_id"]
    assert eligible[0]["pages"] == [29]


def test_verified_selection_preserves_composite_without_observation_heuristic() -> None:
    candidate_metric = {
        "label": "Global e-commerce CPI",
        "value": "Global: $1.00 in 2024; $0.98 in 2025",
        "unit": "USD per install",
        "observations": [
            {
                "label": "Deal discovery CPI",
                "value": "2024: $1.44; 2025: $2.26",
                "unit": "USD per install",
                "segment": "Deal discovery",
            },
            {
                "label": "Shopping CPI",
                "value": "2024: $0.93; 2025: $0.91",
                "unit": "USD per install",
                "segment": "Shopping",
            },
        ],
    }

    selected = select_artifact_insights(
        final_insights=[
            {
                "id": "ecommerce-cpi",
                "text": (
                    "Deal discovery CPI rose from $1.00 in 2024 to $0.98 in 2025."
                ),
                "evidence_id": "final-only",
                "metric": {
                    "label": "Deal discovery CPI",
                    "value": "2024: $1.00; 2025: $0.98",
                    "unit": "USD per install",
                    "segment": "Deal discovery",
                },
            }
        ],
        candidate_insights=[
            {
                "id": "ecommerce-cpi",
                "text": "The retained composite CPI fact.",
                "evidence_id": "verified-fact:ecommerce-cpi",
                "evidence": "The source reports all e-commerce CPI observations.",
                "pages": [29],
                "metric": candidate_metric,
            }
        ],
        editorial_plan={
            "report_thesis": "Composite source facts remain authoritative.",
            "themes": [
                {
                    "theme": "Acquisition economics",
                    "priority": 1,
                    "evidence_ids": ["verified-fact:ecommerce-cpi"],
                },
                {
                    "theme": "Subvertical differences",
                    "priority": 2,
                    "evidence_ids": ["verified-fact:ecommerce-cpi"],
                },
            ],
        },
        verified_mode=True,
    )

    assert selected[0]["text"].startswith("Deal discovery CPI rose")
    assert selected[0]["metric"]["label"] == candidate_metric["label"]
    assert selected[0]["metric"]["value"] == candidate_metric["value"]
    assert selected[0]["metric"]["observations"] == candidate_metric["observations"]


def test_verified_multi_fact_binding_survives_insight_normalization_and_selection():
    primary_id = "verified-fact:north-america"
    comparison_id = "verified-fact:apac"
    final = normalize_artifact_insights(
        [
            {
                "id": "regional-video",
                "text": "North America has the same top environment as APAC.",
                "evidence_id": primary_id,
                "evidence_ids": [primary_id, comparison_id],
                "metric": {
                    "label": "North America video attention",
                    "value": "128",
                    "unit": "index",
                },
            }
        ],
        prefix="insight",
        verified_mode=True,
    )
    selected = select_artifact_insights(
        final_insights=final,
        candidate_insights=[
            {
                "id": "regional-video",
                "text": "North America video attention.",
                "evidence_id": primary_id,
                "metric": {
                    "label": "North America video attention",
                    "value": "128",
                    "unit": "index",
                },
            },
            {
                "id": "apac-video",
                "text": "APAC video attention.",
                "evidence_id": comparison_id,
                "metric": {
                    "label": "APAC video attention",
                    "value": "131",
                    "unit": "index",
                },
            },
        ],
        editorial_plan={
            "report_thesis": "Regional video attention differs by environment.",
            "themes": [
                {"theme": "North America", "priority": 1, "evidence_ids": [primary_id]},
                {"theme": "APAC", "priority": 2, "evidence_ids": [comparison_id]},
            ],
        },
        verified_mode=True,
    )

    assert selected[0]["evidence_ids"] == [primary_id, comparison_id]
