from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.document_identity_service import (
    extract_publisher_imprint,
    extract_source_provenance,
)


@pytest.mark.parametrize(
    "text",
    (
        "Market Outlook 2026\nPublished by: Acme Research\nAll rights reserved.",
        "A report by Acme Research\nMarket Outlook 2026",
        "Copyright © 2026 Acme Research\nMarket Outlook 2026",
    ),
)
def test_extract_publisher_imprint_accepts_explicit_document_evidence(
    text: str,
) -> None:
    observation = extract_publisher_imprint(text)

    assert observation is not None
    assert observation.publisher_name == "Acme Research"
    assert observation.evidence_locator == "document_pack:first_pages"
    assert len(observation.evidence_hash) == 64


def test_extract_publisher_imprint_accepts_repeated_document_header_domain() -> None:
    observation = extract_publisher_imprint(
        "www.activate.com\n"
        "Technology & Media Outlook\n"
        "www.activate.com\n"
        "Market analysis\n"
        "www.activate.com\n"
    )

    assert observation is not None
    assert observation.publisher_name == "activate.com"
    assert observation.evidence_locator == "document_pack:first_pages:repeated_domain"


@pytest.mark.parametrize(
    "text",
    (
        "acme-research-market-outlook-2026.pdf",
        "Acme Research expects growth to continue.",
        "Published by: Acme Research\nPublished by: Other Research",
    ),
)
def test_extract_publisher_imprint_rejects_weak_or_conflicting_evidence(
    text: str,
) -> None:
    assert extract_publisher_imprint(text) is None


def test_extract_source_provenance_preserves_distinct_explicit_roles() -> None:
    fixture_path = (
        Path(__file__).parent / "fixtures" / "source_provenance" / "role_cases.json"
    )
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))

    for case in cases:
        observed = extract_source_provenance(
            case["text"], pdf_metadata=case["pdf_metadata"]
        )
        expected = case["expected"]
        assert observed.publication_name == expected["publication_name"], case["id"]
        assert observed.publisher_name == expected["publisher_name"], case["id"]
        assert list(observed.author_names) == expected["author_names"], case["id"]
        assert observed.author_kind == expected["author_kind"], case["id"]
        assert list(observed.data_provider_names) == expected["data_provider_names"], case[
            "id"
        ]
        assert observed.report_owner_name == expected["report_owner_name"], case["id"]


def test_extract_source_provenance_never_promotes_citation_only_provider() -> None:
    observed = extract_source_provenance(
        "Market report\nKepios analysis indicates growth.\nData from Ookla show speeds.",
        pdf_metadata={"Title": "Market report"},
    )

    assert observed.publisher_name == ""
    assert observed.data_provider_names == ("Kepios", "Ookla")
    assert observed.status == "ambiguous"
    assert "publisher_missing" in observed.issues


def test_extract_source_provenance_accepts_pdf_text_replacement_for_copyright() -> None:
    observed = extract_source_provenance(
        "Digital 2022: Sweden\n� Kepios. All rights reserved.",
        pdf_metadata={
            "Title": "Digital 2022: Sweden � DataReportal � Global Digital Insights"
        },
    )

    assert observed.publisher_name == "DataReportal"
    assert observed.report_owner_name == "Kepios"


def test_extract_source_provenance_reports_equal_priority_publisher_conflict() -> None:
    observed = extract_source_provenance(
        "Published by Alpha Research\nPublished by Beta Research",
    )

    assert observed.publisher_name == ""
    assert observed.status == "conflicting"
    assert "publisher_conflict" in observed.issues
