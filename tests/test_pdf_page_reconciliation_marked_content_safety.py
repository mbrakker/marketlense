from __future__ import annotations

import pymupdf as fitz

from src.contracts.pdf_page_reconciliation import (
    PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
    PdfPageReconciliationRequest,
)
from src.services.pdf_service import reconcile_pdf_pages


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
