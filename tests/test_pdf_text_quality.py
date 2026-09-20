from __future__ import annotations

import json
import logging
from pathlib import Path

try:
    import fitz
except ModuleNotFoundError:  # pragma: no cover - depends on PyMuPDF packaging alias
    import pymupdf as fitz

from src.contracts.pdf_context import PdfContext
from src.contracts.pdf_text import PdfTextExtractRequest, PdfTextSampleRequest
from src.contracts.run_context import RunContext
from src.services._pdf.text_quality import (
    evaluate_native_text_quality,
    select_healthier_native_text,
)
from src.services.pdf_service import extract_pdf_text, sample_pdf_text


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="run", task_id="task", span_id="span"
    )


def _service_events(caplog, logger_name: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != logger_name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _build_text_pdf(path: Path, *, paragraph: str = "") -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    body = paragraph or (
        "Market Lense synthetic PDF text for extraction coverage. " * 8
    )
    page.insert_text((72, 72), "Synthetic title page", fontsize=18)
    page.insert_textbox(fitz.Rect(72, 120, 520, 320), body, fontsize=12)
    doc.save(path.as_posix())
    doc.close()


# ---------------------------------------------------------------------------
# Deterministic malformation detection
# ---------------------------------------------------------------------------


def test_clean_english_text_is_not_flagged() -> None:
    text = (
        "Global consumer intelligence report covering category growth, pricing "
        "pressure, and shelf dynamics across 12 markets. Retailers adjusted "
        "assortments while manufacturers defended premium tiers. "
    ) * 4

    quality = evaluate_native_text_quality(text)

    assert quality.is_malformed is False
    assert quality.reasons == ()


def test_legitimate_accented_latin_text_is_not_flagged() -> None:
    text = (
        "Café chains in México und Köln verzeichneten Umsätze von naïve "
        "bílé příští roku, podle žprávy. "
        "Français : Dépenses des ménages en produits d'épicerie — 2026. "
    ) * 4

    quality = evaluate_native_text_quality(text)

    assert quality.is_malformed is False


def test_legitimate_ligatures_and_quotes_are_not_flagged() -> None:
    text = (
        "The report's \ufb01ndings \u2014 \u201cspending \ufb02ows toward "
        "value\u201d \u2014 describe caf\u00e9 demand (2026) for consumers "
        "aged 25\u201334. "
    ) * 4

    quality = evaluate_native_text_quality(text)

    assert quality.is_malformed is False


def test_legitimate_cyrillic_document_is_not_flagged() -> None:
    text = (
        "Российский рынок продуктов питания демонстрирует устойчивый рост "
        "спроса на категории здорового питания и напитков без сахара. "
    ) * 4

    quality = evaluate_native_text_quality(text)

    assert quality.is_malformed is False


def test_private_use_mapping_flood_is_flagged() -> None:
    text = "".join(chr(0xE000 + (i % 200)) for i in range(400)) + " " * 40

    quality = evaluate_native_text_quality(text)

    assert "unusable_character_mapping" in quality.reasons


def test_homoglyph_script_mixing_is_flagged() -> None:
    corrupt_words = [
        "Мoscow",
        "retаil",
        "Вeverage",
        "соnsumer",
        "trеnd",
        "Мarket",
        "global",
        "сategory",
    ]
    text = " ".join(corrupt_words * 6)

    quality = evaluate_native_text_quality(text)

    assert "homoglyph_script_mixing" in quality.reasons


def test_unspaced_extraction_is_flagged() -> None:
    token = "Turningtodaysignalsintotomorrowstrategies"
    text = token * 12

    quality = evaluate_native_text_quality(text)

    assert quality.is_malformed is True
    assert {"broken_spacing", "broken_word_boundaries"} & set(quality.reasons)


def test_control_character_flood_is_flagged() -> None:
    body = "Market intelligence report about category growth and pricing. "
    text = body + ("\x01\x02\x03\x04" * 40)

    quality = evaluate_native_text_quality(text)

    assert "control_character_flood" in quality.reasons


def test_empty_text_is_not_flagged() -> None:
    assert evaluate_native_text_quality("").is_malformed is False
    assert evaluate_native_text_quality("   \n\t ").is_malformed is False


# ---------------------------------------------------------------------------
# Healthier-extraction selection
# ---------------------------------------------------------------------------


def test_selection_keeps_healthy_primary() -> None:
    primary = "Healthy primary extraction with plenty of clean words."

    selection = select_healthier_native_text(primary, "Unused fallback text.")

    assert selection.used_fallback is False
    assert selection.text == primary


def test_selection_switches_to_clean_fallback_for_malformed_primary() -> None:
    corrupt = " ".join(
        [
            "Мoscow",
            "retаil",
            "Вeverage",
            "соnsumer",
            "trеnd",
            "Мarket",
            "сategory",
            "global",
        ]
        * 4
    )

    selection = select_healthier_native_text(
        corrupt,
        "Clean alternative extraction recovered the expected wording.",
    )

    assert selection.used_fallback is True
    assert "Clean alternative extraction" in selection.text


def test_selection_keeps_primary_when_fallback_is_empty() -> None:
    corrupt = " ".join(["Мoscow", "retаil", "Вeverage", "соnsumer"] * 6)

    selection = select_healthier_native_text(corrupt, "")

    assert selection.used_fallback is False
    assert selection.text == corrupt


def test_selection_keeps_primary_when_fallback_is_also_malformed() -> None:
    corrupt = "Мoscow retаil Вeverage соnsumer trеnd Мarket сategory global"

    selection = select_healthier_native_text(corrupt, corrupt.upper())

    assert selection.used_fallback is False


# ---------------------------------------------------------------------------
# Service-level native fallback behavior
# ---------------------------------------------------------------------------


class _FakePypdfPage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakePypdfReader:
    def __init__(self, page_texts: list[str]) -> None:
        self.pages = [_FakePypdfPage(text) for text in page_texts]


_CORRUPT_PAGE_TEXT = " ".join(
    [
        "Мoscow",
        "retаil",
        "Вeverage",
        "соnsumer",
        "trеnd",
        "Мarket",
        "сategory",
        "global",
        "prеmium",
        "demand",
        "brand",
        "loуalty",
    ]
    * 4
)

_HEALTHY_BODY = (
    "Global food and drink predictions covering category growth, pricing, "
    "and shopper behaviour across markets. "
) * 6


def test_extract_pdf_text_recovers_corrupt_page_from_fitz(tmp_path, caplog) -> None:
    pdf_path = tmp_path / "corrupt-native.pdf"
    _build_text_pdf(pdf_path, paragraph=_HEALTHY_BODY)
    fitz_doc = fitz.open(pdf_path)
    context = PdfContext(
        schema_version="1.0",
        path=str(pdf_path),
        fitz_doc=fitz_doc,
        pypdf_reader=_FakePypdfReader([_CORRUPT_PAGE_TEXT]),
    )
    caplog.set_level(logging.INFO, logger="market_lense.pdf_service")

    response = extract_pdf_text(
        PdfTextExtractRequest(
            schema_version="1.0",
            path=str(pdf_path),
            max_pages=1,
            max_chars=8000,
            pdf_context=context,
        ),
        _ctx(),
    )

    assert "Мoscow" not in response.text
    assert _HEALTHY_BODY.strip()[:40] in response.text
    events = _service_events(caplog, "market_lense.pdf_service")
    fallback_events = [
        event
        for event in events
        if event.get("event") == "pdf_text_native_fallback_applied"
    ]
    assert len(fallback_events) == 1
    fields = fallback_events[0]["fields"]
    assert fields["recovered_page_numbers"] == [1]
    assert "homoglyph_script_mixing" in fields["primary_reason_codes"]
    fitz_doc.close()
    context.close()


def test_extract_pdf_text_lazily_opens_fitz_without_context_document(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "corrupt-native-no-context.pdf"
    _build_text_pdf(pdf_path, paragraph=_HEALTHY_BODY)
    context = PdfContext(
        schema_version="1.0",
        path=str(pdf_path),
        fitz_doc=None,
        pypdf_reader=_FakePypdfReader([_CORRUPT_PAGE_TEXT]),
    )

    response = extract_pdf_text(
        PdfTextExtractRequest(
            schema_version="1.0",
            path=str(pdf_path),
            max_pages=1,
            max_chars=8000,
            pdf_context=context,
        ),
        _ctx(),
    )

    assert "Мoscow" not in response.text
    assert _HEALTHY_BODY.strip()[:40] in response.text
    context.close()


def test_extract_pdf_text_keeps_healthy_output_without_fallback(
    tmp_path, caplog
) -> None:
    pdf_path = tmp_path / "healthy.pdf"
    _build_text_pdf(pdf_path)
    caplog.set_level(logging.INFO, logger="market_lense.pdf_service")

    response = extract_pdf_text(
        PdfTextExtractRequest(
            schema_version="1.0",
            path=str(pdf_path),
            max_pages=1,
            max_chars=8000,
        ),
        _ctx(),
    )

    assert "Market Lense synthetic PDF text" in response.text
    events = _service_events(caplog, "market_lense.pdf_service")
    assert not [
        event
        for event in events
        if event.get("event") == "pdf_text_native_fallback_applied"
    ]


def test_sample_pdf_text_scores_recovered_text(tmp_path) -> None:
    pdf_path = tmp_path / "corrupt-native-sample.pdf"
    _build_text_pdf(pdf_path, paragraph=_HEALTHY_BODY)
    fitz_doc = fitz.open(pdf_path)
    context = PdfContext(
        schema_version="1.0",
        path=str(pdf_path),
        fitz_doc=fitz_doc,
        pypdf_reader=_FakePypdfReader([_CORRUPT_PAGE_TEXT]),
    )

    response = sample_pdf_text(
        PdfTextSampleRequest(
            schema_version="1.0",
            path=str(pdf_path),
            page_indices=[0],
            pdf_context=context,
        ),
        _ctx(),
    )

    assert response.samples[0].char_count > 0
    assert response.samples[0].confidence_score > 0.5
    fitz_doc.close()
    context.close()
