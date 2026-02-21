from __future__ import annotations

import itertools

import pytest

from src.contracts.openai import (
    OpenAIVectorStoreAttachFileResponse,
    OpenAIVectorStoreCreateResponse,
    OpenAIVectorStoreFileUploadResponse,
    OpenAIVectorStoreStatusResponse,
)
from src.contracts.vector_store import (
    VectorStoreAttachFileRequest,
    VectorStoreAttachFileResponse,
    VectorStoreCreateRequest,
    VectorStoreCreateResponse,
    VectorStoreMetadata,
    VectorStoreStatusResponse,
    VectorStoreUploadFileRequest,
    VectorStoreUploadFileResponse,
    VectorStoreWaitRequest,
)
from src.services import vector_store_service as svc
from src.utils.errors import AppError


def _install_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def test_create_vector_store(monkeypatch: pytest.MonkeyPatch):
    _install_api_key(monkeypatch)

    def _create(req, ctx):
        return OpenAIVectorStoreCreateResponse(schema_version="1.0", vector_store_id="vs_123")

    monkeypatch.setattr(svc.openai_service, "openai_vector_store_create", _create)
    resp = svc.create_vector_store(
        VectorStoreCreateRequest(
            schema_version="1.0",
            name="report",
            metadata=VectorStoreMetadata(
                schema_version="1.0",
                report_id="report",
                report_name="Report",
                taxonomy=["Tag1"],
                categories=["cat1"],
                region="US",
                time_period="2024",
            ),
        )
    )
    assert isinstance(resp, VectorStoreCreateResponse)
    assert resp.vector_store_id == "vs_123"


def test_upload_file(monkeypatch: pytest.MonkeyPatch, tmp_path):
    _install_api_key(monkeypatch)

    def _upload(req, ctx):
        return OpenAIVectorStoreFileUploadResponse(schema_version="1.0", openai_file_id="file_123")

    monkeypatch.setattr(svc.openai_service, "openai_vector_store_upload_file", _upload)
    pdf = tmp_path / "f.pdf"
    pdf.write_bytes(b"hello")
    resp = svc.upload_file(
        VectorStoreUploadFileRequest(
            schema_version="1.0",
            vector_store_id="vs_123",
            file_path=str(pdf),
        )
    )
    assert isinstance(resp, VectorStoreUploadFileResponse)
    assert resp.openai_file_id == "file_123"


def test_attach_file(monkeypatch: pytest.MonkeyPatch):
    _install_api_key(monkeypatch)

    def _attach(req, ctx):
        return OpenAIVectorStoreAttachFileResponse(
            schema_version="1.0",
            vector_store_id="vs_123",
            openai_file_id="file_123",
        )

    monkeypatch.setattr(svc.openai_service, "openai_vector_store_attach_file", _attach)
    resp = svc.attach_file(
        VectorStoreAttachFileRequest(
            schema_version="1.0",
            vector_store_id="vs_123",
            openai_file_id="file_123",
        )
    )
    assert isinstance(resp, VectorStoreAttachFileResponse)
    assert resp.openai_file_id == "file_123"


def test_wait_until_indexed_success(monkeypatch: pytest.MonkeyPatch):
    _install_api_key(monkeypatch)

    def _status(req, ctx):
        return OpenAIVectorStoreStatusResponse(
            schema_version="1.0",
            vector_store_id=req.vector_store_id,
            status="completed",
            indexed_at_utc="2026-01-07T00:00:00Z",
            last_error=None,
        )

    monkeypatch.setattr(svc.openai_service, "openai_vector_store_status", _status)
    resp = svc.wait_until_indexed(
        VectorStoreWaitRequest(
            schema_version="1.0",
            vector_store_id="vs_123",
            timeout_s=1,
            poll_interval_s=1,
        )
    )
    assert isinstance(resp, VectorStoreStatusResponse)
    assert resp.status == "completed"


def test_wait_until_indexed_timeout(monkeypatch: pytest.MonkeyPatch):
    _install_api_key(monkeypatch)
    statuses = iter(
        [
            OpenAIVectorStoreStatusResponse(
                schema_version="1.0",
                vector_store_id="vs_123",
                status="in_progress",
                indexed_at_utc=None,
                last_error=None,
            ),
            OpenAIVectorStoreStatusResponse(
                schema_version="1.0",
                vector_store_id="vs_123",
                status="in_progress",
                indexed_at_utc=None,
                last_error=None,
            ),
        ]
    )

    monkeypatch.setattr(svc.openai_service, "openai_vector_store_status", lambda req, ctx: next(statuses))
    tick = itertools.chain([0.0, 0.1, 0.2, 1.1], itertools.repeat(1.1))
    monkeypatch.setattr(svc.time, "time", lambda: next(tick))
    monkeypatch.setattr(svc.time, "sleep", lambda _seconds: None)
    with pytest.raises(AppError) as exc:
        svc.wait_until_indexed(
            VectorStoreWaitRequest(
                schema_version="1.0",
                vector_store_id="vs_123",
                timeout_s=1,
                poll_interval_s=1,
            )
        )
    assert exc.value.code == "vector_store_index_timeout"
