from __future__ import annotations

from dataclasses import replace

import pytest

from src.contracts.pdf_text import PdfTextPage
from src.contracts.report_identity import ReportTitleResolution
from src.contracts.validation import ValidationRequest
from src.generators.validation.grounding import grounding_payload, run_grounding_check
from tests._test_validation_generator._shared import (
    FakeOpenAI,
    FakePromptClient,
    _ctx,
    _report,
    _settings,
)


@pytest.mark.parametrize("response_key", ["checks", "unsupported"])
def test_unestablished_public_fact_is_a_repair_error(tmp_path, response_key):
    issues = run_grounding_check(
        request=ValidationRequest(
            schema_version="1.0",
            report_id="identity",
            report=replace(_report(), title="Unproven title"),
            artifacts={},
            evidence_packs={"doc_map": {"title": "Established source title"}},
            vector_store_id=None,
        ),
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            grounding_payload={
                response_key: [
                    {
                        "item_id": "metadata:title",
                        "section": "metadata.title",
                        "text": "Unproven title",
                        "classification": "factual_claim",
                        "entailment_outcome": "not_established",
                        "reason": "No source support",
                    }
                ]
            }
        ),
        ctx=_ctx(),
    )
    assert len(issues) == 1
    assert issues[0].severity == "error"


def test_metadata_mismatch_has_canonical_comparison_evidence():
    artifacts = {"insights_final": []}
    payload = grounding_payload(
        ValidationRequest(
            schema_version="1.0",
            report_id="identity",
            report=replace(_report(), title="Wrong report title", publisher=""),
            artifacts=artifacts,
            evidence_packs={"doc_map": {"title": "Technology Outlook 2026"}},
        ),
        artifacts,
    )
    item = next(
        x for x in payload["public_factual_items"] if x["item_id"] == "metadata:title"
    )
    assert item["retained_evidence"] == "Technology Outlook 2026"
    assert item["evidence_ids"] == ["doc_map:title"]


def test_explicit_source_title_establishes_identity_over_conflicting_doc_map():
    artifacts = {"insights_final": []}
    payload = grounding_payload(
        ValidationRequest(
            schema_version="1.0",
            report_id="identity",
            report=replace(
                _report(), title="TECH AND MEDIA OUTLOOK 2016", publisher=""
            ),
            artifacts=artifacts,
            evidence_packs={
                "doc_map": {
                    "title": "The 9 most important insights for tech and media in 2016"
                }
            },
            source_pages=[
                PdfTextPage(
                    page_number=1,
                    text=(
                        "THINK AGAIN:\nTECH AND MEDIA OUTLOOK 2016\n"
                        "WSJD Live Conference\nOctober 20, 2015\nwww.activate.com"
                    ),
                )
            ],
        ),
        artifacts,
    )

    assert "title" not in payload
    assert all(
        item["item_id"] != "metadata:title" for item in payload["public_factual_items"]
    )


def test_bain_cover_title_establishes_identity_over_filename_slug():
    artifacts = {"insights_final": []}
    payload = grounding_payload(
        ValidationRequest(
            schema_version="1.0",
            report_id="identity",
            report=replace(
                _report(),
                title="Technology isn't just an industry anymore. It's everything",
                publisher="",
            ),
            artifacts=artifacts,
            evidence_packs={
                "doc_map": {
                    "title": "Technology isn't just an industry anymore. It's everything"
                }
            },
            source_pages=[
                PdfTextPage(
                    page_number=1,
                    text=(
                        "Technology isn't just\n"
                        "an industry anymore.\n"
                        "It's everything\n\n"
                        "Most of the largest value creators in recent years were "
                        "technology companies or businesses with a tech-led strategy."
                    ),
                )
            ],
        ),
        artifacts,
    )

    assert "title" not in payload
    assert all(
        item["item_id"] != "metadata:title" for item in payload["public_factual_items"]
    )


def test_grounding_uses_propagated_source_title_resolution_without_rebuilding_identity():
    artifacts = {"insights_final": []}
    source_title = "Technology isn't just an industry anymore. It's everything"
    payload = grounding_payload(
        ValidationRequest(
            schema_version="1.0",
            report_id="identity",
            report=replace(_report(), title=source_title, publisher=""),
            artifacts=artifacts,
            evidence_packs={"doc_map": {"title": "Stale generated title"}},
            source_title_resolution=ReportTitleResolution(
                title=source_title,
                candidate_source="cover_title_page",
                explicit_source_title=source_title,
            ),
        ),
        artifacts,
    )

    assert "title" not in payload


@pytest.mark.parametrize("trusted", [True, False])
def test_attribution_context_requires_explicit_publisher_provenance(trusted):
    artifacts = {
        "insights_final": [
            {
                "id": "forecast",
                "text": "Acme forecasts growth.",
                "evidence_id": "f1",
                "evidence": "We forecast growth.",
            }
        ]
    }
    roles = {
        "status": "resolved" if trusted else "ambiguous",
        "publisher_name": "Acme",
        "evidence": [
            {
                "role": "publisher" if trusted else "data_provider",
                "name": "Acme",
                "evidence_locator": "pdf:page:1",
                "evidence_hash": "source-proof",
            }
        ],
    }
    payload = grounding_payload(
        ValidationRequest(
            schema_version="1.0",
            report_id="identity",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={
                "doc_map": {"publisher": "Acme", "provenance_roles": roles}
            },
        ),
        artifacts,
    )
    item = next(
        x
        for x in payload["public_factual_items"]
        if x["item_id"] == "insight:forecast:text"
    )
    assert item["retained_evidence"] == "We forecast growth."
    if trusted:
        assert item["source_identity"]["publisher_name"] == "Acme"
    else:
        assert "source_identity" not in item


def test_insight_grounding_includes_authoritative_source_page_context():
    artifacts = {
        "insights_final": [
            {
                "id": "pay-tv",
                "text": "The report says U.S. Pay TV prices reached the upper bound.",
                "evidence_id": "pay-tv-limit",
                "evidence": "Pay TV prices reached the upper bound.",
            }
        ]
    }
    payload = grounding_payload(
        ValidationRequest(
            schema_version="1.0",
            report_id="identity",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={
                "findings": {
                    "findings": [
                        {
                            "id": "pay-tv-limit",
                            "text": "Pay TV prices reached the upper bound.",
                            "evidence": "Pay TV prices reached the upper bound.",
                            "pages": [95],
                        }
                    ]
                }
            },
            source_pages=[
                PdfTextPage(
                    page_number=95,
                    text="PRICE OF EXPANDED BASIC CABLE, U.S., 2010-2016E",
                )
            ],
        ),
        artifacts,
    )
    item = next(
        x
        for x in payload["public_factual_items"]
        if x["item_id"] == "insight:pay-tv:text"
    )
    assert "U.S." in item["retained_evidence"]
