from __future__ import annotations

import pymupdf as fitz

from src.contracts.pdf_page_reconciliation import (
    PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
    PdfPageReconciliationRequest,
)
from src.services.pdf_service import reconcile_pdf_pages
from tests.test_pdf_page_reconciliation import (
    _make_replacement_character_footer_pdf,
    _patch_page_streams,
)


def _make_pdf(path) -> None:
    document = fitz.open()
    try:
        page = document.new_page(width=612, height=792)
        page.insert_text((72, 770), "Page 5", fontsize=10)
        page.insert_text((72, 750), "5 | 6", fontsize=10)
        document.save(path)
    finally:
        document.close()


def _patch_page_stream(path) -> None:
    document = fitz.open(path)
    try:
        page = document[0]
        text = "5 | 6"
        encoded_text = text.encode().hex().encode()
        original = b"[<" + encoded_text + b">]TJ"
        replacement = (
            b"/Span <</ActualText (\xfe\xff\xff\xfc)>> BDC ( )Tj EMC " + original
        )
        stream_xref = next(
            xref
            for xref in page.get_contents()
            if original in document.xref_stream(xref)
        )
        stream = document.xref_stream(stream_xref)
        document.update_stream(stream_xref, stream.replace(original, replacement))
        patched_path = path.with_name(f"{path.stem}-patched{path.suffix}")
        document.save(patched_path)
    finally:
        document.close()
    patched_path.replace(path)


def test_ambiguous_replacement_character_blocks_direct_footer_confirmation(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "direct-and-ambiguous-replacement-character-footer.pdf"
    _make_pdf(pdf_path)
    _patch_page_stream(pdf_path)

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert response.mappings[0].printed_label is None
    assert response.mappings[0].status == "unresolved"
    assert response.mappings[0].evidence[0].kind == "conflict"


def _reconcile(path, run_context):
    return reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(path)
        ),
        run_context,
    )


def test_isolated_artifact_prefixed_arabic_token_stays_unresolved(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "isolated-artifact-token.pdf"
    _make_replacement_character_footer_pdf(pdf_path, labels=["42"])

    mapping = _reconcile(pdf_path, run_context).mappings[0]

    assert mapping.printed_label is None
    assert mapping.status == "unresolved"


def test_two_consecutive_artifact_prefixed_tokens_do_not_corrobate_each_other(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "two-artifact-tokens.pdf"
    _make_replacement_character_footer_pdf(pdf_path, labels=["1", "2"])

    mappings = _reconcile(pdf_path, run_context).mappings

    assert [mapping.printed_label for mapping in mappings] == [None, None]
    assert [mapping.status for mapping in mappings] == ["unresolved", "unresolved"]


def test_three_consecutive_artifact_prefixed_tokens_use_sequence_anchors(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "three-artifact-tokens.pdf"
    _make_replacement_character_footer_pdf(pdf_path, labels=["1", "2", "3"])

    mappings = _reconcile(pdf_path, run_context).mappings

    assert [mapping.printed_label for mapping in mappings] == ["1", "2", "3"]
    assert [mapping.status for mapping in mappings] == [
        "verified",
        "verified",
        "verified",
    ]
    assert all(mapping.method == "visible_footer" for mapping in mappings)
    assert all(mapping.source_geometry is not None for mapping in mappings)
    assert all(
        mapping.evidence[0].anchor_physical_pages == (1, 3) for mapping in mappings
    )


def test_broken_artifact_prefixed_sequence_stays_unresolved(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "broken-artifact-sequence.pdf"
    _make_replacement_character_footer_pdf(pdf_path, labels=["1", "9", "3"])

    mappings = _reconcile(pdf_path, run_context).mappings

    assert [mapping.printed_label for mapping in mappings] == [None, None, None]
    assert [mapping.status for mapping in mappings] == [
        "unresolved",
        "unresolved",
        "unresolved",
    ]


def _make_multiline_source_note_pdf(path) -> None:
    base_path = path.with_name(f"{path.stem}-base{path.suffix}")
    document = fitz.open()
    try:
        for page_number in range(1, 4):
            page = document.new_page(width=612, height=792)
            page.insert_textbox(
                fitz.Rect(72, 690, 540, 785),
                (
                    f"Source note {page_number} alpha\n"
                    f"Source note {page_number} beta\n"
                    f"Source note {page_number} gamma\n"
                    f"{page_number}"
                ),
                fontsize=10,
            )
        document.save(base_path)
    finally:
        document.close()

    replacements = {}
    for page_number in range(1, 4):
        label = str(page_number)
        encoded_label = label.encode().hex().upper().encode()
        original = b"[<" + encoded_label + b">]TJ"
        replacement = (
            b"/Span <</ActualText (\xfe\xff\xff\xfc)>> BDC ( )Tj EMC " + original
        )
        replacements[page_number] = (original, replacement)
    _patch_page_streams(base_path, path, replacements)


def test_artifact_prefixed_footer_survives_multiline_source_note_block(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "multiline-source-note-artifact-footer.pdf"
    _make_multiline_source_note_pdf(pdf_path)

    mappings = _reconcile(pdf_path, run_context).mappings

    assert [mapping.printed_label for mapping in mappings] == ["1", "2", "3"]
    assert [mapping.status for mapping in mappings] == [
        "verified",
        "verified",
        "verified",
    ]
    assert all(
        mapping.evidence[0].anchor_physical_pages == (1, 3) for mapping in mappings
    )
