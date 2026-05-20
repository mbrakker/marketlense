from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from src.contracts.openai import OpenAIPdfOcrRequest
from src.contracts.run_context import RunContext
from src.services.openai_service import OPENAI_OCR_RESPONSE_FORMAT, openai_ocr_pdf
from src.utils.errors import AppError
from tests.support.fakes import FakeOpenAIResult


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="run",
        task_id="task",
        span_id="span",
    )


def _events(caplog) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != "market_lense.openai_service":
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events


def test_openai_ocr_service_sends_pdf_payload_and_adapts_response(
    tmp_path: Path,
    fake_openai,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    fake_openai.add(
        "responses.create",
        FakeOpenAIResult(
            output_text='{"pages":[{"page_number":1,"text":"OCR page one"},{"page_number":2,"text":"OCR page two"}]}',
            usage={"input_tokens": 12, "output_tokens": 34, "total_tool_calls": 0},
            id="resp_ocr_1",
        ),
    )
    caplog.set_level(logging.INFO, logger="market_lense.openai_service")

    response = openai_ocr_pdf(
        OpenAIPdfOcrRequest(
            schema_version="1.0",
            api_key="openai-key",
            pdf_path=str(pdf_path),
            model="gpt-5-mini",
            system_prompt="system",
            user_prompt="user",
            timeout_seconds=45.0,
            cost_ledger_path=str(tmp_path / "ledger.jsonl"),
            cost_daily_path=str(tmp_path / "daily.json"),
            model_pricing={},
        ),
        _ctx(),
    )

    assert fake_openai.client_kwargs == [{"api_key": "openai-key", "timeout": 45.0}]
    call = fake_openai.calls["responses.create"][0]
    assert call["model"] == "gpt-5-mini"
    assert call["instructions"] == "system"
    assert call["text"] == {"format": OPENAI_OCR_RESPONSE_FORMAT}
    user_content = call["input"][0]["content"]
    assert user_content[0] == {"type": "input_text", "text": "user"}
    assert user_content[1]["type"] == "input_file"
    assert user_content[1]["filename"] == "scan.pdf"
    assert str(user_content[1]["file_data"]).startswith("data:application/pdf;base64,")
    assert response.request_id == "resp_ocr_1"
    assert [page.page_number for page in response.pages] == [1, 2]
    assert response.pages[0].text == "OCR page one"
    assert response.input_tokens == 12
    assert response.output_tokens == 34
    assert_no_defaulted_required_fields(response)

    events = _events(caplog)
    assert_logs_have_required_fields(events)


def test_openai_ocr_service_missing_key_raises_typed_error(
    tmp_path: Path,
    assert_app_error,
) -> None:
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")

    with pytest.raises(AppError) as exc_info:
        openai_ocr_pdf(
            OpenAIPdfOcrRequest(
                schema_version="1.0",
                api_key="",
                pdf_path=str(pdf_path),
                model="gpt-5-mini",
                system_prompt="system",
                user_prompt="user",
                timeout_seconds=30.0,
                cost_ledger_path=str(tmp_path / "ledger.jsonl"),
                cost_daily_path=str(tmp_path / "daily.json"),
                model_pricing={},
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="openai_missing_api_key",
        retryable=False,
    )


def test_openai_ocr_service_accepts_blank_structured_page(
    tmp_path: Path,
    fake_openai,
    assert_no_defaulted_required_fields,
) -> None:
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    fake_openai.add(
        "responses.create",
        FakeOpenAIResult(
            output_text='{"pages":[{"page_number":1,"text":""}]}',
            usage={"input_tokens": 10, "output_tokens": 2, "total_tool_calls": 0},
            id="resp_invalid",
        ),
    )

    response = openai_ocr_pdf(
        OpenAIPdfOcrRequest(
            schema_version="1.0",
            api_key="openai-key",
            pdf_path=str(pdf_path),
            model="gpt-5-mini",
            system_prompt="system",
            user_prompt="user",
            timeout_seconds=30.0,
            cost_ledger_path=str(tmp_path / "ledger.jsonl"),
            cost_daily_path=str(tmp_path / "daily.json"),
            model_pricing={},
        ),
        _ctx(),
    )

    assert response.request_id == "resp_invalid"
    assert [(page.page_number, page.text) for page in response.pages] == [(1, "")]
    assert_no_defaulted_required_fields(response)


def test_openai_ocr_service_rejects_missing_structured_pages(
    tmp_path: Path,
    fake_openai,
    assert_app_error,
) -> None:
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    fake_openai.add(
        "responses.create",
        FakeOpenAIResult(
            output_text='{"pages":[]}',
            usage={"input_tokens": 10, "output_tokens": 2, "total_tool_calls": 0},
            id="resp_invalid",
        ),
    )

    with pytest.raises(AppError) as exc_info:
        openai_ocr_pdf(
            OpenAIPdfOcrRequest(
                schema_version="1.0",
                api_key="openai-key",
                pdf_path=str(pdf_path),
                model="gpt-5-mini",
                system_prompt="system",
                user_prompt="user",
                timeout_seconds=30.0,
                cost_ledger_path=str(tmp_path / "ledger.jsonl"),
                cost_daily_path=str(tmp_path / "daily.json"),
                model_pricing={},
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="openai_ocr_invalid_response",
        retryable=False,
    )


def test_openai_ocr_service_wraps_provider_exception_as_retryable_request_failure(
    tmp_path: Path,
    fake_openai,
    assert_app_error,
) -> None:
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    fake_openai.add("responses.create", RuntimeError("provider boom"))

    with pytest.raises(AppError) as exc_info:
        openai_ocr_pdf(
            OpenAIPdfOcrRequest(
                schema_version="1.0",
                api_key="openai-key",
                pdf_path=str(pdf_path),
                model="gpt-5-mini",
                system_prompt="system",
                user_prompt="user",
                timeout_seconds=30.0,
                cost_ledger_path=str(tmp_path / "ledger.jsonl"),
                cost_daily_path=str(tmp_path / "daily.json"),
                model_pricing={},
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="openai_ocr_request_failed",
        retryable=True,
    )
