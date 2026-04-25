from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

try:
    import fitz
except ModuleNotFoundError:  # pragma: no cover - depends on PyMuPDF packaging alias
    import pymupdf as fitz

from src.contracts.file_cache import (
    FileCacheMd5SidecarResolveRequest,
    FileCacheMd5SidecarWriteRequest,
)
from src.contracts.drive import DriveListRequest
from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.llm import LLMClientPolicy
from src.contracts.openai import (
    OpenAIJSONPromptRequest,
    OpenAIPdfOcrRequest,
    OpenAIResponseRequest,
)
from src.contracts.pdf_text import PdfTextExtractRequest
from src.contracts.pdf_utils import PdfInfoRequest
from src.contracts.run_context import RunContext
from src.contracts.vector_store import (
    VectorStoreCreateRequest,
    VectorStoreMetadata,
    VectorStoreStatusRequest,
)
from src.contracts.wordpress import (
    WordPressPostUpdateRequest,
    WordPressTaxonomyEnsureRequest,
    WordPressTaxonomyTerm,
)
from src.services import (
    drive_service,
    file_cache_service,
    _http_acquisition as http_acquisition_service,
    llm_service,
    openai_service,
    pdf_service,
    vector_store_service,
)
from src.services.wordpress_service import ensure_taxonomy_terms, update_post_categories
from tests.support.fakes import FakeOpenAIResult


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="integration-run",
        task_id="integration-task",
        span_id="integration-span",
    )


@pytest.mark.integration
def test_pdf_service_extracts_local_pdf(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Integration PDF text 2026")
    doc.save(pdf_path)
    doc.close()

    info = pdf_service.extract_pdf_info(
        PdfInfoRequest(schema_version="1.0", path=str(pdf_path)),
        _ctx(),
    )
    extracted = pdf_service.extract_pdf_text(
        PdfTextExtractRequest(
            schema_version="1.0",
            path=str(pdf_path),
            max_pages=2,
            max_chars=2000,
        ),
        _ctx(),
    )

    assert info.page_count == 1
    assert extracted.pages_extracted == 1
    assert "Integration PDF text 2026" in extracted.text


@pytest.mark.integration
def test_file_cache_service_roundtrips_local_sidecar(tmp_path):
    cache_path = tmp_path / "sample.pdf"
    cache_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    stat = cache_path.stat()

    write_response = file_cache_service.write_md5_sidecar(
        FileCacheMd5SidecarWriteRequest(
            schema_version="1.0",
            cache_path=str(cache_path),
            file_id="integration-file",
            file_name="sample.pdf",
            md5="0123456789abcdef0123456789abcdef",
            size_bytes=stat.st_size,
            mtime_utc=stat.st_mtime,
        ),
        _ctx(),
    )
    resolve_response = file_cache_service.resolve_md5_sidecar(
        FileCacheMd5SidecarResolveRequest(
            schema_version="1.0",
            cache_path=str(cache_path),
            file_id="integration-file",
            size_bytes=stat.st_size,
            mtime_utc=stat.st_mtime,
        ),
        _ctx(),
    )

    assert write_response.written is True
    assert resolve_response.hit is True
    assert resolve_response.resolved_md5 == "0123456789abcdef0123456789abcdef"


class _HttpAcquisitionStubHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = b"<html><body><h1>Integration HTTP</h1></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


@pytest.mark.integration
def test_http_acquisition_service_against_local_stub():
    http_acquisition_service._SESSION_POOL._sessions.clear()
    server = HTTPServer(("127.0.0.1", 0), _HttpAcquisitionStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = http_acquisition_service.execute_http_acquisition(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="http_acquisition_integration",
                method="GET",
                url=f"http://127.0.0.1:{server.server_port}/report",
                headers={"Accept": "text/html"},
                timeout_seconds=5.0,
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=True,
                    capture_text=True,
                    capture_content_type_markers=("html",),
                    max_body_bytes=4096,
                ),
                error_code="http_acquisition_integration_failed",
                error_message="Integration HTTP acquisition failed",
            ),
            ctx=_ctx(),
        )

        assert response.status_code == 200
        assert response.used_pooled_session is True
        assert "Integration HTTP" in str(response.text_body or "")
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


class _WordPressStubHandler(BaseHTTPRequestHandler):
    categories: dict[str, int] = {}
    next_id: int = 1
    updated_posts: dict[int, list[int]] = {}

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path
        if path.startswith("/wp-json/wp/v2/categories?slug="):
            slug = path.split("slug=", 1)[-1]
            term_id = self.categories.get(slug)
            if term_id is None:
                self._send_json([])
            else:
                self._send_json([{"id": term_id, "slug": slug}])
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        payload = json.loads(raw.decode("utf-8") or "{}")

        if self.path == "/wp-json/wp/v2/categories":
            slug = str(payload.get("slug") or "")
            if not slug:
                self._send_json({"error": "slug required"}, status=400)
                return
            term_id = self.categories.get(slug)
            if term_id is None:
                term_id = self.next_id
                self.next_id += 1
                self.categories[slug] = term_id
            self._send_json({"id": term_id, "slug": slug}, status=201)
            return

        if self.path.startswith("/wp-json/wp/v2/posts/"):
            try:
                post_id = int(self.path.rsplit("/", 1)[-1])
            except ValueError:
                self._send_json({"error": "invalid post id"}, status=400)
                return
            categories = payload.get("categories")
            self.updated_posts[post_id] = (
                categories if isinstance(categories, list) else []
            )
            self._send_json(
                {"id": post_id, "link": f"https://example.local/p/{post_id}"}
            )
            return

        self._send_json({"error": "not found"}, status=404)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


@pytest.mark.integration
def test_wordpress_service_against_local_stub():
    server = HTTPServer(("127.0.0.1", 0), _WordPressStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        ensured = ensure_taxonomy_terms(
            WordPressTaxonomyEnsureRequest(
                schema_version="1.0",
                base_url=base_url,
                auth_header="Bearer test-token",
                taxonomy_rest_base="categories",
                terms=[
                    WordPressTaxonomyTerm(
                        schema_version="1.0",
                        slug="digital_payments",
                        name="Digital Payments",
                    )
                ],
            ),
            _ctx(),
        )
        assert "digital_payments" in ensured.slug_to_id

        updated = update_post_categories(
            WordPressPostUpdateRequest(
                schema_version="1.0",
                base_url=base_url,
                auth_header="Bearer test-token",
                post_id=42,
                categories=[ensured.slug_to_id["digital_payments"]],
            ),
            _ctx(),
        )
        assert updated.post_id == 42
        assert updated.link is not None
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.mark.integration
def test_drive_service_live_list_guarded():
    if os.getenv("RUN_DRIVE_INTEGRATION") != "1":
        pytest.skip("Set RUN_DRIVE_INTEGRATION=1 to run live Drive integration.")

    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    folder_id = os.getenv("GDRIVE_FOLDER_ID", "").strip()
    if not sa_path or not folder_id:
        pytest.skip("GOOGLE_SERVICE_ACCOUNT_JSON and GDRIVE_FOLDER_ID are required.")
    if not Path(sa_path).exists():
        pytest.skip("GOOGLE_SERVICE_ACCOUNT_JSON path does not exist.")

    files = list(
        drive_service.list_pdfs(
            DriveListRequest(
                schema_version="1.0",
                folder_id=folder_id,
                service_account_path=sa_path,
                page_size=5,
                list_mode="metadata",
            ),
            _ctx(),
        )
    )
    assert isinstance(files, list)


@pytest.mark.integration
def test_vector_store_service_live_guarded():
    if os.getenv("RUN_VECTOR_STORE_INTEGRATION") != "1":
        pytest.skip(
            "Set RUN_VECTOR_STORE_INTEGRATION=1 to run live vector-store integration."
        )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        pytest.skip("OPENAI_API_KEY is required.")

    create = vector_store_service.create_vector_store(
        VectorStoreCreateRequest(
            schema_version="1.0",
            name="integration.pdf",
            metadata=VectorStoreMetadata(
                schema_version="1.0",
                report_id="integration-vector-store",
                report_name="integration.pdf",
                taxonomy=[],
                categories=[],
            ),
        ),
        _ctx(),
    )
    status = vector_store_service.get_vector_store_status(
        VectorStoreStatusRequest(
            schema_version="1.0",
            vector_store_id=create.vector_store_id,
        ),
        _ctx(),
    )
    assert status.vector_store_id == create.vector_store_id
    assert status.status != ""


@pytest.mark.integration
def test_openai_service_live_smoke_guarded(tmp_path):
    if os.getenv("RUN_OPENAI_SERVICE_INTEGRATION") != "1":
        pytest.skip(
            "Set RUN_OPENAI_SERVICE_INTEGRATION=1 to run live OpenAI integration."
        )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        pytest.skip("OPENAI_API_KEY is required.")

    response = openai_service.openai_chat_json(
        request=OpenAIJSONPromptRequest(
            schema_version="1.0",
            system_prompt="Return JSON only",
            user_prompt='{"ping":"pong"}',
            model="gpt-4.1-mini",
            temperature=0.0,
            api_key=api_key,
            timeout_seconds=30.0,
            cost_ledger_path=str(tmp_path / "ledger.jsonl"),
            cost_daily_path=str(tmp_path / "daily.json"),
            model_pricing={},
        ),
        ctx=_ctx(),
    )
    assert response.text != ""


@pytest.mark.integration
def test_llm_service_wraps_openai_service_retry_and_backoff(
    tmp_path: Path,
    fake_openai,
) -> None:
    fake_openai.add("responses.create", RuntimeError("provider boom"))
    fake_openai.add(
        "responses.create",
        FakeOpenAIResult(
            output_text='{"ok":true}',
            usage={"input_tokens": 1, "output_tokens": 1, "total_tool_calls": 0},
            id="resp_retry_ok",
        ),
    )
    sleep_calls: list[float] = []
    client = llm_service.build_openai_client(
        base_client=openai_service,
        policy=LLMClientPolicy(
            schema_version="1.0",
            scope="integration-openai-chat",
            retries=1,
            base_delay_seconds=0.5,
            backoff_step_seconds=0.0,
            jitter_seconds=0.0,
            circuit_breaker_failure_threshold=0,
            circuit_breaker_recovery_seconds=0.0,
        ),
        sleep_fn=lambda seconds: sleep_calls.append(float(seconds)),
    )

    response = client.openai_respond_with_vector_store(
        OpenAIResponseRequest(
            schema_version="1.0",
            system_prompt="Return JSON only",
            user_prompt='{"ping":"pong"}',
            vector_store_id="vs_123",
            model="gpt-4.1-mini",
            temperature=0.0,
            api_key="openai-key",
            timeout_seconds=30.0,
            cost_ledger_path=str(tmp_path / "ledger.jsonl"),
            cost_daily_path=str(tmp_path / "daily.json"),
            model_pricing={},
        ),
        _ctx(),
    )

    assert response.parsed_json == {"ok": True}
    assert sleep_calls == [0.5]


def _service_events(caplog, logger_name: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != logger_name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _write_image_only_pdf(pdf_path: Path) -> None:
    raster_doc = fitz.open()
    raster_page = raster_doc.new_page(width=900, height=1200)
    raster_page.insert_text(
        (72, 120),
        "OpenAI OCR integration sample 2026",
        fontsize=28,
    )
    raster_page.insert_text(
        (72, 180),
        "This PDF intentionally contains only an embedded image layer.",
        fontsize=18,
    )
    image_bytes = raster_page.get_pixmap(dpi=150).tobytes("png")
    raster_doc.close()

    pdf_doc = fitz.open()
    page = pdf_doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=image_bytes)
    pdf_doc.save(pdf_path)
    pdf_doc.close()


@pytest.mark.integration
def test_openai_service_live_ocr_guarded(
    tmp_path: Path,
    caplog,
    assert_logs_have_required_fields,
):
    if os.getenv("RUN_OPENAI_OCR_INTEGRATION") != "1":
        pytest.skip(
            "Set RUN_OPENAI_OCR_INTEGRATION=1 to run live OpenAI OCR integration."
        )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        pytest.skip("OPENAI_API_KEY is required.")

    pdf_path = tmp_path / "scan-only.pdf"
    _write_image_only_pdf(pdf_path)
    extracted = pdf_service.extract_pdf_text(
        PdfTextExtractRequest(
            schema_version="1.0",
            path=str(pdf_path),
            max_pages=2,
            max_chars=1000,
        ),
        _ctx(),
    )
    assert extracted.text.strip() == ""

    caplog.set_level(logging.INFO, logger="market_lense.openai_service")
    response = openai_service.openai_ocr_pdf(
        OpenAIPdfOcrRequest(
            schema_version="1.0",
            api_key=api_key,
            pdf_path=str(pdf_path),
            model="gpt-5-mini",
            system_prompt=(
                'Return JSON only as {"pages":[{"page_number":1,"text":"..."}]}.'
            ),
            user_prompt="OCR this PDF and return page-structured text for every page.",
            timeout_seconds=120.0,
            cost_ledger_path=str(tmp_path / "ledger.jsonl"),
            cost_daily_path=str(tmp_path / "daily.json"),
            model_pricing={},
        ),
        _ctx(),
    )

    assert response.pages
    assert any(page.text.strip() for page in response.pages)
    events = _service_events(caplog, "market_lense.openai_service")
    assert_logs_have_required_fields(events)
