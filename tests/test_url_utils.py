from __future__ import annotations

from src.utils.url_utils import (
    host_matches_domain,
    normalize_url,
    text_has_url_or_domain_marker,
)


def test_normalize_url_strips_tracking_query_parameters() -> None:
    assert (
        normalize_url(
            "https://www.pwc.com/gx/en/issues/c-suite-insights/ceo-survey.html?icid=tla-top-banner&utm_source=newsletter"
        )
        == "https://www.pwc.com/gx/en/issues/c-suite-insights/ceo-survey.html"
    )


def test_normalize_url_preserves_functional_query_parameters() -> None:
    assert (
        normalize_url(
            "https://www.proximic.com/home/Resources?keywords=&typeofcontent=presentations_page&page=2"
        )
        == "https://www.proximic.com/home/Resources?keywords=&typeofcontent=presentations_page&page=2"
    )


def test_normalize_url_preserves_signed_path_and_query_bytes() -> None:
    url = (
        "HTTPS://EXAMPLE.COM:443/Reports/Annual/"
        "?token=a%2fb+Case&token=second%2Bvalue&X-Amz-Signature=AbC%2f+Z"
    )

    assert normalize_url(url) == (
        "https://example.com/Reports/Annual/"
        "?token=a%2fb+Case&token=second%2Bvalue&X-Amz-Signature=AbC%2f+Z"
    )
    azure_sas_url = "https://example.com/Reports/Annual?sv=2026-10-01&sig=a%2Fb+Case&utm_source=mail"
    assert normalize_url(azure_sas_url) == azure_sas_url


def test_host_matches_domain_requires_exact_host_or_subdomain() -> None:
    assert host_matches_domain("https://salesforce.com/app", "salesforce.com")
    assert host_matches_domain("https://foo.salesforce.com/app", "salesforce.com")
    assert not host_matches_domain("https://evilsalesforce.com/app", "salesforce.com")
    assert not host_matches_domain(
        "https://salesforce.com.evil.test/app",
        "salesforce.com",
    )


def test_text_has_url_or_domain_marker_detects_urls_and_exact_domains() -> None:
    assert text_has_url_or_domain_marker(
        "IEA reference https://www.iea.org/reports/energy-and-ai",
        domains={"doi.org"},
    )
    assert text_has_url_or_domain_marker(
        "Reference DOI https://doi.org/10.1000/example",
        domains={"doi.org"},
    )
    assert text_has_url_or_domain_marker(
        "Reference DOI doi.org/10.1000/example",
        domains={"doi.org"},
    )
    assert not text_has_url_or_domain_marker(
        "This table explains pseudoi.org metrics without a URL.",
        domains={"doi.org"},
    )
