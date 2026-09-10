from src.generators.report_title_resolution_generator import (
    resolve_report_title,
)


def _resolve(**overrides):
    payload = {
        "file_name": "market-outlook-2026.pdf",
        "pdf_metadata": {},
        "pages": [],
        "publisher_name": "",
    }
    payload.update(overrides)
    return resolve_report_title(**payload)


def test_explicit_cover_title_beats_generic_powerpoint_metadata():
    resolution = _resolve(
        file_name="IAB_Europe_AdEx_Benchmark_2025_updated.pdf",
        pdf_metadata={"Title": "PowerPoint Presentation"},
        pages=[
            (
                1,
                "AdEx Benchmark 2025 Report\n"
                "The definitive guide to digital advertising spend",
            ),
            (2, "IAB Europe's AdEx Benchmark Report covers 30 European markets."),
        ],
        publisher_name="IAB Europe",
    )

    assert resolution.title == "AdEx Benchmark 2025 Report"
    assert resolution.candidate_source == "cover_title_page"
    assert resolution.explicit_source_title == "AdEx Benchmark 2025 Report"


def test_generic_word_metadata_never_beats_filename():
    resolution = _resolve(
        file_name="global-consumer-outlook-2026.pdf",
        pdf_metadata={"Title": "Microsoft Word"},
    )

    assert resolution.title == "global consumer outlook 2026"
    assert resolution.candidate_source == "filename"


def test_missing_metadata_uses_clean_filename_title():
    resolution = _resolve(file_name="State_of_Commerce_2026.pdf")

    assert resolution.title == "State of Commerce 2026"
    assert resolution.confidence == "medium"


def test_filename_fallback_strips_acquisition_month_year_suffix() -> None:
    resolution = _resolve(
        file_name="IAB_Europes_Guide_to_AI_in_Retail_Commerce_Media_June_26.pdf"
    )

    assert resolution.title == "IAB Europes Guide to AI in Retail Commerce Media"


def test_explicit_source_title_preserves_apostrophe_ampersand_and_acronym_casing():
    resolution = _resolve(
        file_name="IAB_Europes_Guide_to_AI_in_Retail_Commerce_Media_June_26.pdf",
        pages=[
            (
                1,
                "IAB Europe's Guide to AI in Retail & Commerce Media\nIAB Europe",
            )
        ],
    )

    assert resolution.title == "IAB Europe's Guide to AI in Retail & Commerce Media"
    assert resolution.candidate_source == "cover_title_page"


def test_source_title_line_preserves_punctuation_when_cover_text_is_empty():
    resolution = _resolve(
        file_name="IAB_Europes_Guide_to_AI_in_Retail_Commerce_Media_June_26.pdf",
        pages=[
            (1, ""),
            (
                2,
                "TABLE OF CONTENTS\n"
                "IAB Europe's Guide to AI in Retail & Commerce Media\n"
                "Published 2023\n",
            ),
        ],
    )

    assert resolution.title == "IAB Europe's Guide to AI in Retail & Commerce Media"
    assert resolution.candidate_source == "source_content"


def test_source_report_title_inherits_edition_from_filename():
    resolution = _resolve(
        file_name="IAB_Europe_AdEx_Benchmark_2025_updated.pdf",
        pages=[
            (
                2,
                "Welcome to the twentieth edition of IAB Europe's AdEx Benchmark "
                "Report, the definitive guide to the European digital advertising "
                "market.",
            )
        ],
        publisher_name="IAB Europe",
    )

    assert resolution.title == "AdEx Benchmark 2025 Report"
    assert resolution.edition == "2025"
    assert resolution.candidate_source == "source_content"


def test_repeated_generic_survey_phrase_does_not_beat_source_report_title():
    resolution = _resolve(
        file_name="consumer-outlook-to-2026.pdf",
        pages=[
            (2, "Consumer Outlook: Guide to 2026\nNIQ Consumer Outlook Report"),
            (24, "Our global survey 2025\nConsumer outlook evidence"),
            (29, "Our global survey 2025\nConsumer outlook evidence"),
        ],
    )

    assert resolution.title == "Consumer Outlook: Guide to 2026"
    assert resolution.candidate_source == "source_content"


def test_iab_adex_source_content_beats_powerpoint_document_metadata():
    resolution = _resolve(
        file_name="IAB_Europe_AdEx_Benchmark_2025_updated.pdf",
        pdf_metadata={
            "Title": "PowerPoint Presentation",
            "Creator": "Microsoft PowerPoint",
        },
        pages=[
            (1, "© IAB Europe"),
            (
                2,
                "Welcome to the twentieth edition of IAB Europe's AdEx Benchmark "
                "Report, the definitive guide to the state of the European digital "
                "advertising market.",
            ),
        ],
        publisher_name="IAB Europe",
    )

    assert resolution.title == "AdEx Benchmark 2025 Report"
    assert resolution.candidate_source == "source_content"
    assert resolution.issues == ()


def test_ambiguous_title_candidates_use_one_identity_resolver_call():
    calls = []

    def _identity_resolver(request):
        calls.append(request)
        return {
            "title": "Retail Media Outlook 2026",
            "edition": "2026",
            "publisher_candidate": "Example Research",
            "confidence": "high",
            "evidence": ["cover page", "page 2 header"],
        }

    resolution = _resolve(
        file_name="retail-media-outlook-2026.pdf",
        pages=[
            (2, "Retail Media Outlook 2026\nExample Research"),
            (3, "Commerce Media Outlook 2026\nExample Research"),
        ],
        identity_resolver=_identity_resolver,
    )

    assert resolution.title == "Retail Media Outlook 2026"
    assert resolution.candidate_source == "llm_identity_resolution"
    assert len(calls) == 1


def test_cover_subtitle_is_retained_when_it_completes_the_title():
    resolution = _resolve(
        file_name="state-of-commerce-2026.pdf",
        pages=[(1, "State of Commerce\n2026 Report\nA global benchmark")],
    )

    assert resolution.title == "State of Commerce 2026 Report"


def test_cover_publisher_mark_does_not_beat_visible_report_title():
    resolution = _resolve(
        file_name="technology-media-outlook-2026.pdf",
        pages=[
            (
                1,
                "ACTIVATE CONSULTING\nTECHNOLOGY & MEDIA OUTLOOK 2026\nECOMMERCE",
            )
        ],
        publisher_name="Activate Consulting",
    )

    assert resolution.title == "TECHNOLOGY & MEDIA OUTLOOK 2026 ECOMMERCE"
    assert resolution.explicit_source_title == resolution.title


def test_generic_and_identifier_only_values_are_rejected():
    generic = _resolve(
        file_name="d01c72af1b10260d54ec45e891bfc7af40a041ce-pdf.pdf",
        pdf_metadata={"Title": "PDF"},
        pages=[(1, "Document")],
    )

    assert generic.title == ""
    assert "generic_title_missing" in generic.issues

    internal_identifier = _resolve(
        file_name="file_id_01HZX6KN9HWV6P6N54XGX21KZB.pdf",
        pdf_metadata={"Title": "Document"},
    )

    assert internal_identifier.title == ""
