from src.generators.evidence_packs.common import derive_publisher_from_document_text


def test_derive_publisher_from_explicit_branding_in_document_text() -> None:
    assert (
        derive_publisher_from_document_text(
            "How GWI's brand tracking solution transforms metrics to meaning. "
            "© GWI 2025."
        )
        == "GWI"
    )


def test_derive_publisher_from_document_text_ignores_unattributed_prose() -> None:
    assert derive_publisher_from_document_text("A guide to market trends.") == ""
