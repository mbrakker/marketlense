from __future__ import annotations

from pathlib import Path

import pytest

from src.contracts.pdf_ocr import PdfOcrSplitRequest
from src.contracts.pdf_utils import PdfInfoRequest
from src.services.pdf_service import extract_pdf_info, split_pdf_for_ocr
from src.utils.errors import AppError
from tests.test_pdf_text_service import _build_multi_page_text_pdf, _ctx


def _path_units(path: Path) -> int:
    return len(str(path.resolve()).encode("utf-16-le")) // 2


def test_ocr_split_compacts_long_stem_and_preserves_page_sequence(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_pdf = source_dir / (("Очень-длинный-источник-" * 3) + ".pdf")
    _build_multi_page_text_pdf(source_pdf, page_count=5)
    output_dir = tmp_path / ("ocr-output-" * 7)

    response = split_pdf_for_ocr(
        PdfOcrSplitRequest(
            schema_version="1.0",
            source_pdf_path=str(source_pdf),
            output_dir=str(output_dir),
            chunk_page_count=2,
        ),
        _ctx(),
    )

    assert [chunk.chunk_index for chunk in response.chunks] == [1, 2, 3]
    assert [
        (chunk.start_page_number, chunk.end_page_number) for chunk in response.chunks
    ] == [
        (1, 2),
        (3, 4),
        (5, 5),
    ]
    for chunk in response.chunks:
        chunk_path = Path(chunk.chunk_pdf_path)
        assert chunk_path.is_absolute()
        assert _path_units(chunk_path) <= 240
        assert len(chunk_path.name) <= 255
        info = extract_pdf_info(
            PdfInfoRequest(schema_version="1.0", path=str(chunk_path)), _ctx()
        )
        assert info.page_count == chunk.page_count


def test_ocr_split_does_not_casefold_collide_for_distinct_sources(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_pdf = first_dir / "Report.pdf"
    second_pdf = second_dir / "report.pdf"
    _build_multi_page_text_pdf(first_pdf, page_count=3)
    _build_multi_page_text_pdf(second_pdf, page_count=3)
    output_dir = tmp_path / "shared-chunks"

    first_response = split_pdf_for_ocr(
        PdfOcrSplitRequest("1.0", str(first_pdf), str(output_dir), 2), _ctx()
    )
    second_response = split_pdf_for_ocr(
        PdfOcrSplitRequest("1.0", str(second_pdf), str(output_dir), 2), _ctx()
    )

    first_paths = [Path(chunk.chunk_pdf_path) for chunk in first_response.chunks]
    second_paths = [Path(chunk.chunk_pdf_path) for chunk in second_response.chunks]
    assert {path.name.casefold() for path in first_paths}.isdisjoint(
        {path.name.casefold() for path in second_paths}
    )
    assert all(path.exists() for path in first_paths + second_paths)


def test_ocr_split_preserves_conflicting_chunk_bytes(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    _build_multi_page_text_pdf(source_pdf, page_count=3)
    output_dir = tmp_path / "chunks"
    request = PdfOcrSplitRequest("1.0", str(source_pdf), str(output_dir), 2)

    first_response = split_pdf_for_ocr(request, _ctx())
    conflicting_path = Path(first_response.chunks[0].chunk_pdf_path)
    conflicting_bytes = b"not the source chunk"
    conflicting_path.write_bytes(conflicting_bytes)

    with pytest.raises(AppError) as exc_info:
        split_pdf_for_ocr(request, _ctx())

    assert exc_info.value.code == "pdf_ocr_split_artifact_conflict"
    assert exc_info.value.retryable is False
    assert conflicting_path.read_bytes() == conflicting_bytes


def test_ocr_split_rejects_impossible_output_root_before_creating_it(
    tmp_path: Path,
) -> None:
    source_pdf = tmp_path / "source.pdf"
    _build_multi_page_text_pdf(source_pdf, page_count=3)
    output_dir = tmp_path / ("impossible-output-" * 20)

    with pytest.raises(AppError) as exc_info:
        split_pdf_for_ocr(
            PdfOcrSplitRequest("1.0", str(source_pdf), str(output_dir), 2), _ctx()
        )

    assert exc_info.value.code == "pdf_ocr_split_path_invalid"
    assert exc_info.value.retryable is False
    assert not output_dir.exists()


__all__ = [
    "test_ocr_split_compacts_long_stem_and_preserves_page_sequence",
    "test_ocr_split_does_not_casefold_collide_for_distinct_sources",
    "test_ocr_split_preserves_conflicting_chunk_bytes",
    "test_ocr_split_rejects_impossible_output_root_before_creating_it",
]
