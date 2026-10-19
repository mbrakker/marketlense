from __future__ import annotations

import hashlib
import json

import pymupdf as fitz
import pytest

from scripts.quality.reconcile_pdf_pages import main as reconcile_cli_main
from src.contracts.pdf_page_reconciliation import (
    PDF_PAGE_RECONCILIATION_ALGORITHM_VERSION,
    PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
    PdfPageLabelMapping,
    PdfPageReconciliationCoverage,
    PdfPageReconciliationEvidence,
    PdfPageReconciliationGeometry,
    PdfPageReconciliationRequest,
    PdfPageReconciliationResponse,
)
from src.contracts.schema_validation import SchemaValidateRequest
from src.services.pdf_service import reconcile_pdf_pages
from src.services.schema_validator_service import validate_schema
from src.utils.errors import AppError


def _make_pdf(
    path, pages: list[dict[str, object]], native_labels: list[dict] | None = None
) -> None:
    document = fitz.open()
    try:
        for page_spec in pages:
            page = document.new_page(width=612, height=792)
            body = page_spec.get("body", "")
            if body:
                page.insert_text((72, 150), body, fontsize=12)
            header = page_spec.get("header", "")
            if header:
                page.insert_text((72, 32), header, fontsize=10)
            footer = page_spec.get("footer", "")
            if footer:
                page.insert_text((72, 770), footer, fontsize=10)
            if page_spec.get("image_only"):
                pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 80, 80), False)
                pixmap.clear_with(220)
                page.insert_image(page.rect, pixmap=pixmap)
        if native_labels:
            document.set_page_labels(native_labels)
        document.save(path)
    finally:
        document.close()


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
                        fitz.Rect(*block["rect"]),
                        text,
                        fontsize=fontsize,
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


def test_response_rejects_missing_physical_page_mapping() -> None:
    mapping = PdfPageLabelMapping(
        schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
        physical_page=1,
        printed_label="1",
        status="verified",
        method="visible_footer",
        native_pdf_label=None,
        evidence=(
            PdfPageReconciliationEvidence(
                schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
                kind="visible_footer",
                detail="Page 1",
            ),
        ),
        source_geometry=PdfPageReconciliationGeometry(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
            physical_page=1,
            label_text="Page 1",
            location="visible_footer",
            bounding_box=(0.0, 0.0, 10.0, 10.0),
        ),
    )
    coverage = PdfPageReconciliationCoverage(
        schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
        verified_count=1,
        inferred_count=0,
        unresolved_count=0,
        verified_percentage=100.0,
        inferred_percentage=0.0,
        unresolved_percentage=0.0,
    )

    with pytest.raises(ValueError, match="one mapping for every physical page"):
        PdfPageReconciliationResponse(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
            algorithm_version=PDF_PAGE_RECONCILIATION_ALGORITHM_VERSION,
            input_pdf_md5="0" * 32,
            physical_page_count=2,
            mappings=(mapping,),
            coverage_statistics=coverage,
        )


def test_reconciliation_schema_rejects_invalid_status(run_context) -> None:
    payload = {
        "schema_version": PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
        "algorithm_version": PDF_PAGE_RECONCILIATION_ALGORITHM_VERSION,
        "input_pdf_md5": "0" * 32,
        "physical_page_count": 1,
        "mappings": [
            {
                "schema_version": PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
                "physical_page": 1,
                "printed_label": None,
                "status": "unsupported",
                "method": "unresolved",
                "native_pdf_label": None,
                "source_geometry": None,
                "evidence": [
                    {
                        "schema_version": PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
                        "kind": "no_visible_label",
                        "detail": "no label",
                        "anchor_physical_pages": [],
                    }
                ],
            }
        ],
        "coverage_statistics": {
            "schema_version": PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
            "verified_count": 0,
            "inferred_count": 0,
            "unresolved_count": 1,
            "verified_percentage": 0.0,
            "inferred_percentage": 0.0,
            "unresolved_percentage": 100.0,
        },
    }

    with pytest.raises(AppError) as captured:
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0",
                schema_name="pdf_page_reconciliation",
                payload=payload,
            ),
            run_context,
        )

    assert captured.value.code == "schema_enum_mismatch"


def test_reconciles_a_visible_footer_and_infers_one_missing_footer(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _make_pdf(
        pdf_path,
        [
            {"footer": "Page 10"},
            {},
            {"footer": "Page 12"},
        ],
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert [mapping.printed_label for mapping in response.mappings] == [
        "10",
        "11",
        "12",
    ]
    assert [mapping.status for mapping in response.mappings] == [
        "verified",
        "inferred",
        "verified",
    ]
    assert response.mappings[0].method == "visible_footer"
    geometry = response.mappings[0].source_geometry
    assert geometry is not None
    assert geometry.physical_page == 1
    assert geometry.label_text == "Page 10"
    assert geometry.location == "visible_footer"
    assert geometry.bounding_box_scope == "text_block"
    assert geometry.bounding_box[1] >= 750.0
    assert response.mappings[1].evidence[0].anchor_physical_pages == (1, 3)


def test_reconciles_printed_page_42_at_physical_page_44(tmp_path, run_context) -> None:
    pdf_path = tmp_path / "offset.pdf"
    _make_pdf(
        pdf_path,
        [{"footer": f"Page {42 if page == 44 else page}"} for page in range(1, 45)],
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert response.physical_page_count == 44
    assert response.mappings[43].physical_page == 44
    assert response.mappings[43].printed_label == "42"
    assert response.mappings[43].status == "verified"


def test_handles_roman_front_matter_offsets_and_numbering_restart(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "sections.pdf"
    _make_pdf(
        pdf_path,
        [
            {"footer": "i"},
            {"footer": "ii"},
            {"footer": "Page 1"},
            {"footer": "Page 2"},
            {"footer": "Page 3"},
            {"footer": "Page 1"},
            {},
            {"footer": "Page 3"},
        ],
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert [mapping.printed_label for mapping in response.mappings] == [
        "i",
        "ii",
        "1",
        "2",
        "3",
        "1",
        "2",
        "3",
    ]
    assert [mapping.status for mapping in response.mappings] == [
        "verified",
        "verified",
        "verified",
        "verified",
        "verified",
        "verified",
        "inferred",
        "verified",
    ]
    assert response.mappings[6].status == "inferred"
    assert response.mappings[6].evidence[0].anchor_physical_pages == (6, 8)


def test_weak_standalone_digit_is_not_verified_without_local_sequence(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "weak.pdf"
    _make_pdf(pdf_path, [{"footer": "7"}])

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert response.mappings[0].status == "unresolved"
    assert response.mappings[0].printed_label is None


def test_descending_weak_labels_remain_unresolved(tmp_path, run_context) -> None:
    pdf_path = tmp_path / "descending-weak.pdf"
    _make_pdf(
        pdf_path,
        [{"footer": "7"}, {"footer": "6"}, {"footer": "5"}],
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert [mapping.status for mapping in response.mappings] == [
        "unresolved",
        "unresolved",
        "unresolved",
    ]


def test_two_consecutive_weak_labels_do_not_validate_each_other(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "two-weak.pdf"
    _make_pdf(pdf_path, [{"footer": "7"}, {"footer": "8"}])

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert [mapping.status for mapping in response.mappings] == [
        "unresolved",
        "unresolved",
    ]


def test_three_page_ascending_weak_sequence_is_verified(tmp_path, run_context) -> None:
    pdf_path = tmp_path / "three-weak.pdf"
    _make_pdf(
        pdf_path,
        [{"footer": "7"}, {"footer": "8"}, {"footer": "9"}],
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert [mapping.status for mapping in response.mappings] == [
        "verified",
        "verified",
        "verified",
    ]
    assert response.mappings[1].evidence[0].anchor_physical_pages == (1, 3)


def test_ambiguous_prefixed_pair_requires_more_than_pairwise_corroboration(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "two-prefixed-weak.pdf"
    _make_pdf(pdf_path, [{"footer": "A-01"}, {"footer": "A-02"}])

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert [mapping.status for mapping in response.mappings] == [
        "unresolved",
        "unresolved",
    ]


def test_ambiguous_trailing_number_requires_corroboration(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "trailing-number.pdf"
    _make_pdf(pdf_path, [{"footer": "Section • 7"}])

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert response.mappings[0].status == "unresolved"


def test_weak_numbering_restart_does_not_accept_two_short_sequences(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "weak-restart.pdf"
    _make_pdf(
        pdf_path,
        [
            {"footer": "1"},
            {"footer": "2"},
            {"footer": "1"},
            {"footer": "2"},
        ],
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert [mapping.status for mapping in response.mappings] == [
        "unresolved",
        "unresolved",
        "unresolved",
        "unresolved",
    ]


def test_inference_preserves_prefixed_zero_padded_labels(tmp_path, run_context) -> None:
    pdf_path = tmp_path / "prefixed-labels.pdf"
    _make_pdf(
        pdf_path,
        [{"footer": "Page A-01"}, {}, {"footer": "Page A-03"}],
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert response.mappings[1].printed_label == "A-02"
    assert response.mappings[1].status == "inferred"


def test_conflicting_margin_labels_remain_unresolved(tmp_path, run_context) -> None:
    pdf_path = tmp_path / "conflict.pdf"
    _make_pdf(pdf_path, [{"header": "Page 7", "footer": "Page 8"}])

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert response.mappings[0].status == "unresolved"
    assert response.mappings[0].evidence[0].kind == "conflict"


def test_conflicting_strong_and_weak_labels_remain_unresolved(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "strong-weak-conflict.pdf"
    _make_pdf(
        pdf_path,
        [{"footer": "5"}, {"header": "Page 99", "footer": "6"}, {"footer": "7"}],
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    middle = response.mappings[1]
    assert middle.status == "unresolved"
    assert middle.printed_label is None
    assert middle.evidence[0].kind == "conflict"


def test_conflicted_page_cannot_corroborate_neighboring_weak_labels(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "conflicted-sequence.pdf"
    _make_pdf(
        pdf_path,
        [{"footer": "5"}, {"header": "Page 99", "footer": "6"}, {"footer": "7"}],
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert [mapping.status for mapping in response.mappings] == [
        "unresolved",
        "unresolved",
        "unresolved",
    ]


def test_same_printed_label_from_strong_and_weak_candidates_is_not_a_conflict(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "same-label-candidates.pdf"
    _make_pdf(pdf_path, [{"header": "Page 7", "footer": "7"}])

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    mapping = response.mappings[0]
    assert mapping.status == "verified"
    assert mapping.printed_label == "7"
    assert mapping.evidence[0].kind == "visible_header"


def test_multiple_weak_candidates_use_a_unique_valid_local_sequence(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "unique-weak-sequence.pdf"
    _make_pdf(
        pdf_path,
        [
            {"footer": "Page 5"},
            {"footer": "Section | 6\nSection | 7"},
            {"footer": "Page 7"},
        ],
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    mapping = response.mappings[1]
    assert mapping.status == "verified"
    assert mapping.printed_label == "6"
    assert mapping.evidence[0].kind == "visible_footer"


def test_duplicate_printed_labels_are_allowed(tmp_path, run_context) -> None:
    pdf_path = tmp_path / "duplicates.pdf"
    _make_pdf(pdf_path, [{"footer": "Page 1"}, {"footer": "Page 1"}])

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert [mapping.printed_label for mapping in response.mappings] == ["1", "1"]
    assert all(mapping.status == "verified" for mapping in response.mappings)


def test_contents_entries_and_chart_numerals_are_not_margin_proof(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "false-positives.pdf"
    _make_pdf(
        pdf_path,
        [
            {
                "body": (
                    "Contents\nOverview ........ 7\nMethodology ........ 8\n"
                    "2024 25 50 75 100"
                )
            }
        ],
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert response.mappings[0].status == "unresolved"
    assert response.mappings[0].printed_label is None


def test_long_lower_page_chart_block_does_not_conflict_with_real_footer(
    run_context,
) -> None:
    pdf_path = (
        "tests/fixtures/pdf_benchmark/golden/CAPGEMINI - 2026-Retail-Trends_ACIG.pdf"
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=pdf_path
        ),
        run_context,
    )

    mapping = response.mappings[9]
    assert mapping.physical_page == 10
    assert mapping.printed_label == "10"
    assert mapping.status == "verified"


def test_chart_card_number_does_not_hide_sequence_supported_footer(
    run_context,
) -> None:
    pdf_path = (
        "tests/fixtures/pdf_benchmark/golden/CAPGEMINI - 2026-Retail-Trends_ACIG.pdf"
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=pdf_path
        ),
        run_context,
    )

    mapping = response.mappings[11]
    assert mapping.physical_page == 12
    assert mapping.printed_label == "12"
    assert mapping.status == "verified"


def test_ias_footer_labels_embedded_in_long_text_blocks_are_verified(
    run_context,
) -> None:
    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
            path=(
                "tests/fixtures/pdf_benchmark/golden/"
                "IAS - Industry_Pulse_Report_2026_ACIG.pdf"
            ),
        ),
        run_context,
    )

    assert [response.mappings[page - 1].printed_label for page in range(8, 12)] == [
        "8",
        "9",
        "10",
        "11",
    ]
    assert [response.mappings[page - 1].status for page in range(8, 12)] == [
        "verified",
        "verified",
        "verified",
        "verified",
    ]
    assert all(
        response.mappings[page - 1].method == "visible_footer"
        and response.mappings[page - 1].source_geometry is not None
        for page in range(8, 12)
    )
    assert [response.mappings[page - 1].status for page in (16, 17)] == [
        "verified",
        "verified",
    ]
    assert all(
        response.mappings[page - 1].source_geometry is not None for page in (16, 17)
    )
    assert response.mappings[0].status == "unresolved"


def test_footer_marker_without_unique_numeric_label_remains_unresolved(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "footer-marker-without-label.pdf"
    _make_pdf(
        pdf_path,
        [
            {
                "body": "2024 25 50 75 100",
                "footer": "THE 2026 INDUSTRY PULSE REPORT |",
            }
        ],
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
            path=str(pdf_path),
        ),
        run_context,
    )

    assert response.mappings[0].status == "unresolved"
    assert response.mappings[0].printed_label is None


def test_structured_footer_requires_same_baseline_for_separate_blocks(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "footer-baseline.pdf"
    _make_geometry_pdf(
        pdf_path,
        [
            [
                {
                    "x": 72,
                    "y": 770,
                    "text": "THE 2026 INDUSTRY PULSE REPORT |",
                },
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

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
            path=str(pdf_path),
        ),
        run_context,
    )

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

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
            path=str(pdf_path),
        ),
        run_context,
    )

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

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
            path=str(pdf_path),
        ),
        run_context,
    )

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

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
            path=str(pdf_path),
        ),
        run_context,
    )

    mapping = response.mappings[0]
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

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
            path=str(pdf_path),
        ),
        run_context,
    )

    assert response.mappings[0].printed_label is None
    assert response.mappings[0].status == "unresolved"


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

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
            path=str(pdf_path),
        ),
        run_context,
    )

    assert response.mappings[0].printed_label is None
    assert response.mappings[0].status == "unresolved"
    assert response.mappings[0].evidence[0].kind == "conflict"


def test_native_labels_are_supplementary_to_visible_evidence(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "native-labels.pdf"
    _make_pdf(
        pdf_path,
        [{"footer": "Page 42"}, {}, {"footer": "Page 44"}, {}],
        native_labels=[
            {"startpage": 0, "prefix": "", "style": "D", "firstpagenum": 42},
            {"startpage": 2, "prefix": "", "style": "D", "firstpagenum": 45},
            {"startpage": 3, "prefix": "", "style": "D", "firstpagenum": 46},
        ],
    )

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert response.mappings[0].status == "verified"
    assert response.mappings[0].native_pdf_label == "42"
    assert response.mappings[1].status == "inferred"
    assert response.mappings[1].native_pdf_label == "43"
    assert response.mappings[2].status == "verified"
    assert response.mappings[2].native_pdf_label == "45"
    assert response.mappings[3].status == "unresolved"
    assert response.mappings[3].native_pdf_label == "46"
    assert any(
        item.kind == "native_pdf_metadata" for item in response.mappings[2].evidence
    )


def test_blank_and_image_only_pages_are_unresolved_without_ocr(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "non-text.pdf"
    _make_pdf(pdf_path, [{}, {"image_only": True}])

    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
        ),
        run_context,
    )

    assert [mapping.status for mapping in response.mappings] == [
        "unresolved",
        "unresolved",
    ]


def test_invalid_pdf_raises_typed_error_and_handles_close(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "invalid.pdf"
    pdf_path.write_bytes(b"not a pdf")

    with pytest.raises(AppError) as captured:
        reconcile_pdf_pages(
            PdfPageReconciliationRequest(
                schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
                path=str(pdf_path),
            ),
            run_context,
        )

    assert captured.value.code == "pdf_open_failed"


def test_reconciliation_is_deterministic_and_releases_pdf_handle(
    tmp_path, run_context
) -> None:
    pdf_path = tmp_path / "repeatable.pdf"
    _make_pdf(pdf_path, [{"footer": "Page 1"}, {"footer": "Page 2"}])
    request = PdfPageReconciliationRequest(
        schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION, path=str(pdf_path)
    )

    first = reconcile_pdf_pages(request, run_context)
    second = reconcile_pdf_pages(request, run_context)

    assert first == second
    pdf_path.unlink()
    assert not pdf_path.exists()


def test_runner_persists_and_reuses_an_md5_bound_cache(tmp_path, capsys) -> None:
    pdf_path = tmp_path / "runner.pdf"
    output_dir = tmp_path / "diagnostic-output"
    _make_pdf(pdf_path, [{"footer": "Page 1"}])
    args = ["--pdf", str(pdf_path), "--output-dir", str(output_dir)]

    assert reconcile_cli_main(args) == 0
    first_summary = capsys.readouterr().out
    md5 = hashlib.md5(pdf_path.read_bytes()).hexdigest()
    cache_path = output_dir / f"page_reconciliation-{md5}.json"
    first_bytes = cache_path.read_bytes()
    assert "cache=miss" in first_summary
    assert sorted(item.name for item in output_dir.iterdir()) == [cache_path.name]

    stale_contract = json.loads(first_bytes.decode("utf-8"))
    stale_contract["schema_version"] = "1.0"
    stale_contract["algorithm_version"] = "pdf-page-reconciliation-v1"
    cache_path.write_text(json.dumps(stale_contract), encoding="utf-8")
    assert reconcile_cli_main(args) == 0
    assert "cache=miss" in capsys.readouterr().out
    refreshed_bytes = cache_path.read_bytes()
    refreshed_mtime_ns = cache_path.stat().st_mtime_ns
    assert refreshed_bytes == first_bytes

    assert reconcile_cli_main(args) == 0
    second_summary = capsys.readouterr().out

    assert "cache=hit" in second_summary
    assert cache_path.read_bytes() == refreshed_bytes
    assert cache_path.stat().st_mtime_ns == refreshed_mtime_ns


def test_runner_rejects_invalid_stale_and_checksum_mismatched_cache(
    tmp_path, capsys
) -> None:
    pdf_path = tmp_path / "runner-invalid-cache.pdf"
    output_dir = tmp_path / "diagnostic-output"
    _make_pdf(pdf_path, [{"footer": "Page 1"}])
    args = ["--pdf", str(pdf_path), "--output-dir", str(output_dir)]
    assert reconcile_cli_main(args) == 0
    capsys.readouterr()
    md5 = hashlib.md5(pdf_path.read_bytes()).hexdigest()
    cache_path = output_dir / f"page_reconciliation-{md5}.json"

    cache_path.write_text("{invalid", encoding="utf-8")
    assert reconcile_cli_main(args) == 0
    assert "cache=miss" in capsys.readouterr().out

    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    payload["algorithm_version"] = "stale"
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    assert reconcile_cli_main(args) == 0
    assert "cache=miss" in capsys.readouterr().out

    changed_pdf = tmp_path / "changed.pdf"
    _make_pdf(changed_pdf, [{"footer": "Page 2"}])
    changed_md5 = hashlib.md5(changed_pdf.read_bytes()).hexdigest()
    changed_cache_path = output_dir / f"page_reconciliation-{changed_md5}.json"
    changed_cache_path.write_text(
        cache_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    changed_args = [
        "--pdf",
        str(changed_pdf),
        "--output-dir",
        str(output_dir),
    ]
    assert reconcile_cli_main(changed_args) == 0
    assert "cache=miss" in capsys.readouterr().out
    refreshed = json.loads(changed_cache_path.read_text(encoding="utf-8"))
    assert refreshed["input_pdf_md5"] == changed_md5
