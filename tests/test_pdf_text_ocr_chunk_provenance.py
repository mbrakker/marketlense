import pytest

from src.contracts.pdf_ocr import PdfOcrChunk, PdfOcrPageText
from src.generators.pdf_text_ocr_generator import _map_chunk_pages
from src.utils.errors import AppError


def _chunk():
    return PdfOcrChunk(
        chunk_index=2,
        source_pdf_path="source.pdf",
        chunk_pdf_path="chunk.pdf",
        start_page_number=3,
        end_page_number=5,
        page_count=3,
    )


@pytest.mark.parametrize("numbers", [[1, 2], [3, 4], [1, 1, 2, 3], [1, 3, 4], [2, 3]])
def test_ocr_chunk_rejects_incomplete_duplicate_or_ambiguous_roster(numbers):
    pages = [PdfOcrPageText(page_number=n, text=f"page {n}") for n in numbers]
    with pytest.raises(AppError) as exc:
        _map_chunk_pages(_chunk(), pages)
    assert exc.value.code == "pdf_text_ocr_failed"


@pytest.mark.parametrize("numbers", [[3, 1, 2], [5, 3, 4]])
def test_ocr_chunk_maps_complete_roster_and_preserves_explicit_blank(numbers):
    pages = [
        PdfOcrPageText(page_number=n, text="" if n in (1, 3) else str(n))
        for n in numbers
    ]
    result = _map_chunk_pages(_chunk(), pages)
    assert [p.page_number for p in result] == [3, 4, 5]
    assert [p.text for p in result] == (
        ["", "2", ""] if numbers == [3, 1, 2] else ["", "4", "5"]
    )
