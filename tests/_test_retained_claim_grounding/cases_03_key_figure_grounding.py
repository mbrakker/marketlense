# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._split_support_test_retained_claim_grounding import *  # noqa: F401,F403,F405


def test_key_figure_grounding_uses_the_full_public_metric_and_direct_evidence() -> None:
    evidence_id = "quality-brand-suitability-rate"
    evidence_text = (
        "In the Q1 2026 Global Quality Benchmarks, Brand Suitability Violation "
        "Rate was APAC 8.0%, EMEA 6.3%, LATAM 6.0%, and North America 3.7%."
    )
    figure = {
        "figure_id": "quality-brand-suitability-rate",
        "label": "Brand Suitability Violation Rate",
        "subject": "Brand Suitability Violation Rate",
        "figure": "8.0%",
        "geography": "APAC",
        "timeframe": "Q1 2026",
        "observation_status": "observed",
        "evidence_id": evidence_id,
    }
    request = ValidationRequest(
        schema_version="1.0",
        report_id="key-figure-grounding",
        report=_report(),
        artifacts={"key_figures": [figure]},
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": evidence_id,
                        "text": evidence_text,
                        "evidence": evidence_text,
                        "pages": [3],
                    }
                ]
            }
        },
        source_id="source-key-figure-grounding",
    )

    items = grounding_payload(request, request.artifacts)["public_factual_items"]
    key_figure_items = [
        item for item in items if item["item_id"].startswith("key_figure:1:")
    ]
    metric_item = next(
        item for item in key_figure_items if item["item_id"] == "key_figure:1:figure"
    )

    assert len(key_figure_items) == 1
    assert metric_item["section"] == "key_figures:1.figure"
    assert metric_item["text"] == (
        "Brand Suitability Violation Rate Brand Suitability Violation Rate "
        "8.0% APAC Q1 2026 observed"
    )
    assert metric_item["evidence_ids"] == [evidence_id]
    assert metric_item["retained_evidence"] == evidence_text


def test_key_figure_grounding_retains_cohort_and_denominator_scope() -> None:
    evidence_id = "f1"
    evidence_text = (
        "Born-tech companies created 52% of total market-value growth for the "
        "top 20 gainers across sectors since 2015."
    )
    figure = {
        "figure_id": "technology-market-growth-born-tech",
        "label": "Share of total market-value growth attributed to born-tech companies",
        "subject": "Born-tech companies",
        "figure": "52% of total market-value growth",
        "cohort": "Top 20 gainers across sectors",
        "denominator": "Total market-value growth",
        "timeframe": "since 2015",
        "observation_status": "observed",
        "evidence_id": evidence_id,
    }
    request = ValidationRequest(
        schema_version="1.0",
        report_id="key-figure-population-grounding",
        report=_report(),
        artifacts={"key_figures": [figure]},
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": evidence_id,
                        "text": evidence_text,
                        "evidence": evidence_text,
                    }
                ]
            }
        },
        source_id="source-key-figure-population-grounding",
    )

    items = grounding_payload(request, request.artifacts)["public_factual_items"]
    metric_item = next(
        item for item in items if item["item_id"] == "key_figure:1:figure"
    )

    assert "Top 20 gainers across sectors" in metric_item["text"]
    assert "Total market-value growth" in metric_item["text"]
    assert evidence_text in metric_item["retained_evidence"]
