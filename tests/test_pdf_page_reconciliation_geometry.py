from __future__ import annotations

import pymupdf as fitz

from src.contracts.pdf_page_reconciliation import (
    PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
    PdfPageReconciliationRequest,
)
from src.services.pdf_service import reconcile_pdf_pages


def _make_geometry_pdf(path, pages: list[list[dict[str, object]]]) -> None:
    document = fitz.open()
    try:
        for page_spec in pages:
            page = document.new_page(width=612, height=792)
            for block in page_spec:
                text = str(block["text"])
                fontsize = float(block.get("fontsize", 10))
                if "rect" in block:
                    page.insert_textbox(
                        fitz.Rect(*block["rect"]), text, fontsize=fontsize
                    )
                else:
                    page.insert_text(
                        (float(block["x"]), float(block["y"])),
                        text,
                        fontsize=fontsize,
                    )
        document.save(path)
    finally:
        document.close()


def _reconcile(path, run_context):
    return reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
            path=str(path),
        ),
        run_context,
    )


def test_structured_footer_requires_same_baseline_for_separate_blocks(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "footer-baseline.pdf"
    _make_geometry_pdf(
        pdf_path,
        [
            [
                {"x": 72, "y": 770, "text": "THE 2026 INDUSTRY PULSE REPORT |"},
                {"x": 350, "y": 770, "text": "8"},
            ],
            [
                {
                    "rect": (72, 690, 540, 790),
                    "text": "THE 2026 INDUSTRY PULSE REPORT |\n8",
                }
            ],
        ],
    )

    response = _reconcile(pdf_path, run_context)

    assert response.mappings[0].printed_label == "8"
    assert response.mappings[0].status == "verified"
    assert response.mappings[1].printed_label is None
    assert response.mappings[1].status == "unresolved"


def test_multiline_body_numbers_crossing_footer_band_are_rejected(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "crossing-body-numbers.pdf"
    _make_geometry_pdf(
        pdf_path,
        [
            [{"rect": (72, 620, 540, 790), "text": "1\nbody"}],
            [{"rect": (72, 620, 540, 790), "text": "2\nbody"}],
            [{"rect": (72, 620, 540, 790), "text": "3\nbody"}],
        ],
    )

    response = _reconcile(pdf_path, run_context)

    assert [mapping.status for mapping in response.mappings] == [
        "unresolved",
        "unresolved",
        "unresolved",
    ]
    assert all(mapping.printed_label is None for mapping in response.mappings)


def test_structured_footer_requires_unique_right_aligned_number(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "footer-multiple-numbers.pdf"
    _make_geometry_pdf(
        pdf_path,
        [
            [
                {"x": 72, "y": 770, "text": "THE 2026 INDUSTRY PULSE REPORT |"},
                {"x": 350, "y": 770, "text": "8"},
                {"x": 400, "y": 770, "text": "9"},
            ],
            [
                {"x": 72, "y": 770, "text": "THE 2026 INDUSTRY PULSE REPORT |"},
                {"x": 350, "y": 770, "text": "8"},
                {"x": 400, "y": 770, "text": "9"},
            ],
            [{"x": 72, "y": 770, "text": "THE 2026 INDUSTRY PULSE REPORT |"}],
        ],
    )

    response = _reconcile(pdf_path, run_context)

    assert [mapping.status for mapping in response.mappings] == [
        "unresolved",
        "unresolved",
        "unresolved",
    ]
    assert all(mapping.printed_label is None for mapping in response.mappings)


def test_structured_footer_preserves_explicit_same_line_report_label(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "footer-explicit-label.pdf"
    _make_geometry_pdf(
        pdf_path,
        [[{"x": 72, "y": 770, "text": "THE 2026 INDUSTRY PULSE REPORT | 12"}]],
    )

    mapping = _reconcile(pdf_path, run_context).mappings[0]

    assert mapping.printed_label == "12"
    assert mapping.status == "verified"
    assert mapping.method == "visible_footer"


def test_structured_footer_rejects_number_left_of_marker(tmp_path, run_context) -> None:
    pdf_path = tmp_path / "footer-number-left-of-marker.pdf"
    _make_geometry_pdf(
        pdf_path,
        [
            [
                {"x": 350, "y": 770, "text": "THE 2026 INDUSTRY PULSE REPORT |"},
                {"x": 72, "y": 770, "text": "8"},
            ]
        ],
    )

    mapping = _reconcile(pdf_path, run_context).mappings[0]

    assert mapping.printed_label is None
    assert mapping.status == "unresolved"


def test_structured_footer_mixed_strong_and_weak_candidates_fail_closed(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "footer-strong-weak-conflict.pdf"
    _make_geometry_pdf(
        pdf_path,
        [
            [
                {
                    "rect": (72, 690, 540, 790),
                    "text": "THE 2026 INDUSTRY PULSE REPORT | 12\n13",
                }
            ]
        ],
    )

    mapping = _reconcile(pdf_path, run_context).mappings[0]

    assert mapping.printed_label is None
    assert mapping.status == "unresolved"
    assert mapping.evidence[0].kind == "conflict"
