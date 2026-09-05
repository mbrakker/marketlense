from __future__ import annotations

import pytest

from src.services.document_identity_service import extract_publisher_imprint


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
