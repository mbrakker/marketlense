from unittest.mock import MagicMock

import pytest

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


def _mock_client():
    client = MagicMock()
    client.vector_stores.create.return_value = {"id": "vs_123"}
    client.files.create.return_value = {"id": "file_123"}
    client.vector_stores.files.create.return_value = {"id": "file_123"}
    client.vector_stores.retrieve.return_value = {"status": "completed", "created_at": "2026-01-07T00:00:00Z"}
    return client


def _install_openai_client(monkeypatch: pytest.MonkeyPatch, client: MagicMock) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(svc, "OpenAI", lambda api_key: client)


def test_create_vector_store(monkeypatch: pytest.MonkeyPatch):
    _install_openai_client(monkeypatch, _mock_client())
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
    _install_openai_client(monkeypatch, _mock_client())
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
    _install_openai_client(monkeypatch, _mock_client())
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
    client = _mock_client()
    _install_openai_client(monkeypatch, client)
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
    client = _mock_client()
    client.vector_stores.retrieve.side_effect = [
        {"status": "in_progress"},
        {"status": "in_progress"},
    ]
    _install_openai_client(monkeypatch, client)
    tick = iter([0.0, 0.1, 0.2, 1.1])
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
