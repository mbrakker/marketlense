# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_qualify_publisher_inventory_candidates_rejects_legal_pages() -> None:
    candidate = _candidate(
        "https://example.com/legal/transparency-report",
        "Transparency Report",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        h1_title="Transparency Report",
                        has_asset_type_term=True,
                        has_document_structure=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "legal_or_compliance_page"

def test_qualify_publisher_inventory_candidates_rejects_case_studies() -> None:
    candidate = _candidate(
        "https://example.com/case-studies/state-of-snacking-report",
        "State of Snacking Report",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        h1_title="State of Snacking Report",
                        has_asset_type_term=True,
                        has_download_language=True,
                        has_editorial_markers=True,
                        has_newsletter_cta=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "case_study_or_customer_story_page"

def test_qualify_publisher_inventory_candidates_rejects_report_section_pages() -> None:
    candidate = _candidate(
        "https://example.com/global-culture-report/2025-conclusion",
        "Conclusion",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        h1_title="Conclusion",
                        final_title="Conclusion | 2025 Global Culture Report",
                        has_asset_type_term=True,
                        has_download_language=True,
                        has_document_structure=True,
                        has_editorial_markers=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "report_section_page"

def test_qualify_publisher_inventory_candidates_rejects_nested_report_section_urls() -> (
    None
):
    candidate = _candidate(
        "https://example.com/enterprise-software-technology-predictions-report-2026/innovation",
        "2026 Enterprise software technology predictions report",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        h1_title="2026 Enterprise software technology predictions report",
                        has_asset_type_term=True,
                        has_document_structure=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "report_section_page"

def test_qualify_publisher_inventory_candidates_rejects_legal_practice_area_guides() -> (
    None
):
    candidate = _candidate(
        "https://iclg.com/practice-areas/sanctions/germany",
        "Sanctions Germany 2026",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        h1_title="Sanctions Germany 2026",
                        has_price_or_purchase=True,
                        has_asset_type_term=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "legal_or_compliance_page"

def test_qualify_publisher_inventory_candidates_rejects_research_announcements_without_asset_flow() -> (
    None
):
    candidate = _candidate(
        "https://example.com/insights/despite-gains-finds-new-research",
        "Despite Gains, CMOs Still Struggle to Prove Value to CFOs, Finds New Research from Example and Partner",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        h1_title="Despite Gains, CMOs Still Struggle to Prove Value to CFOs, Finds New Research from Example and Partner",
                        has_asset_type_term=True,
                        has_download_language=True,
                        has_document_structure=True,
                        has_editorial_markers=True,
                        has_newsletter_cta=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "research_announcement_page"

def test_qualify_publisher_inventory_candidates_rejects_informational_how_to_pages() -> (
    None
):
    candidate = _candidate(
        "https://example.com/resources/how-to-use-x",
        "How to use X",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        h1_title="How to use Reddit for social listening",
                        has_asset_type_term=True,
                        has_document_structure=True,
                        has_editorial_markers=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "informational_article_page"

def test_qualify_publisher_inventory_candidates_rejects_how_to_reporting_pages() -> (
    None
):
    candidate = _candidate(
        "https://example.com/insights/reporting-and-data-analytics-with-ai",
        "How to maximise international reporting and data analytics with AI",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        h1_title="How to maximise international reporting and data analytics with AI",
                        has_asset_type_term=True,
                        has_print_language=True,
                        has_editorial_markers=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "informational_article_page"

def test_qualify_publisher_inventory_candidates_rejects_regulatory_disclosure_documents() -> (
    None
):
    candidate = _candidate(
        "https://example.com/docs/disclosure-notes.pdf",
        "Pillar 3 Disclosures",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        is_pdf=True,
                        content_type="application/pdf",
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "regulatory_or_disclosure_document"

def test_qualify_publisher_inventory_candidates_rejects_corporate_policy_pdfs() -> None:
    candidate = _candidate(
        "https://example.com/docs/modern-slavery-statement.pdf",
        "Modern Slavery Statement",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        is_pdf=True,
                        content_type="application/pdf",
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "corporate_policy_document"

def test_qualify_publisher_inventory_candidates_rejects_gender_equality_index_pdfs() -> (
    None
):
    candidate = _candidate(
        "https://example.com/docs/index-de-l-egalite-femmes-hommes.pdf",
        "Index de l’égalité femmes-hommes",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        final_title="Index de l’égalité femmes-hommes",
                        h1_title="Index de l’égalité femmes-hommes",
                        content_type="application/pdf",
                        is_pdf=True,
                        has_download_language=False,
                        has_document_structure=False,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert [item.canonical_url for item in response.rejected_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "corporate_policy_document"

def test_qualify_publisher_inventory_candidates_rejects_binding_corporate_rules_documents() -> (
    None
):
    candidate = _candidate(
        "https://example.com/docs/company-bcr-summary.pdf",
        "UK BCR Summarypdf 159.3 KB",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        final_title="UK BCR Summarypdf 159.3 KB",
                        h1_title="UK BCR Summarypdf 159.3 KB",
                        content_type="application/pdf",
                        is_pdf=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "legal_or_compliance_page",
        "legal_or_policy_document",
        "regulatory_or_disclosure_document",
    }

def test_qualify_publisher_inventory_candidates_rejects_survey_platform_pages_without_report_signals() -> (
    None
):
    candidate = _candidate(
        "https://www.surveymonkey.com/r/SFSA_BTB_Sep25",
        "SurveyMonkey logo with text in primary",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url="https://www.surveymonkey.com/survey-closed",
                        final_title="SurveyMonkey logo with text in primary",
                        has_gated_form=True,
                        has_newsletter_cta=True,
                        has_contact_sales_cta=True,
                        has_editorial_markers=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "survey_or_questionnaire_page"

def test_qualify_publisher_inventory_candidates_rejects_survey_platform_pages_even_with_report_like_title() -> (
    None
):
    candidate = _candidate(
        "https://www.surveymonkey.com/r/SFSA_BTB_Feb26",
        "SFSA Business Trend Survey - February 2026",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url="https://www.surveymonkey.com/r/SFSA_BTB_Feb26",
                        final_title="SFSA Business Trend Survey - February 2026",
                        has_gated_form=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "survey_or_questionnaire_page"

def test_qualify_publisher_inventory_candidates_uses_pdf_filename_when_source_title_is_generic() -> (
    None
):
    candidate = _candidate(
        "https://cdn.example.com/files/2026-market-forecast.pdf",
        "here",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        is_pdf=True,
                        content_type="application/pdf",
                    )
                ],
            )
        ),
    )

    assert response.approved_items[0].title == "2026 market forecast"
    assert response.decisions[0].resolved_title == "2026 market forecast"

def test_qualify_publisher_inventory_candidates_rejects_plural_asset_bucket_titles_without_distribution_signals() -> (
    None
):
    candidate = _candidate(
        "https://example.com/subject-areas/education/whitepapers",
        "White papers",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        final_title="White papers",
                        h1_title="White papers",
                        has_asset_type_term=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "generic_asset_hub_page"
    assert response.decisions[0].resolved_title == candidate.canonical_url

def test_qualify_publisher_inventory_candidates_rejects_report_root_hub_even_with_document_structure() -> (
    None
):
    candidate = _candidate(
        "https://example.com/reports",
        "Reports - Resources, Marketing Infographics & Guides",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/reports",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        final_title="Reports - Resources, Marketing Infographics & Guides",
                        h1_title="Reports",
                        has_document_structure=True,
                        has_asset_type_term=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "generic_asset_hub_page"

def test_qualify_publisher_inventory_candidates_rejects_service_membership_pages() -> (
    None
):
    candidate = _candidate(
        "https://example.com/research/ai-access",
        "AI Access",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/research",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        final_title="AI Access",
                        h1_title="AI Access",
                        has_document_structure=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "service_or_membership_page"

__all__ = [
    "test_qualify_publisher_inventory_candidates_rejects_legal_pages",
    "test_qualify_publisher_inventory_candidates_rejects_case_studies",
    "test_qualify_publisher_inventory_candidates_rejects_report_section_pages",
    "test_qualify_publisher_inventory_candidates_rejects_nested_report_section_urls",
    "test_qualify_publisher_inventory_candidates_rejects_legal_practice_area_guides",
    "test_qualify_publisher_inventory_candidates_rejects_research_announcements_without_asset_flow",
    "test_qualify_publisher_inventory_candidates_rejects_informational_how_to_pages",
    "test_qualify_publisher_inventory_candidates_rejects_how_to_reporting_pages",
    "test_qualify_publisher_inventory_candidates_rejects_regulatory_disclosure_documents",
    "test_qualify_publisher_inventory_candidates_rejects_corporate_policy_pdfs",
    "test_qualify_publisher_inventory_candidates_rejects_gender_equality_index_pdfs",
    "test_qualify_publisher_inventory_candidates_rejects_binding_corporate_rules_documents",
    "test_qualify_publisher_inventory_candidates_rejects_survey_platform_pages_without_report_signals",
    "test_qualify_publisher_inventory_candidates_rejects_survey_platform_pages_even_with_report_like_title",
    "test_qualify_publisher_inventory_candidates_uses_pdf_filename_when_source_title_is_generic",
    "test_qualify_publisher_inventory_candidates_rejects_plural_asset_bucket_titles_without_distribution_signals",
    "test_qualify_publisher_inventory_candidates_rejects_report_root_hub_even_with_document_structure",
    "test_qualify_publisher_inventory_candidates_rejects_service_membership_pages",
]
