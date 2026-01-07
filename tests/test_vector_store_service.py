import pytest
from unittest.mock import MagicMock, patch

from src.contracts.vector_store import (
    VectorStoreAttachFileResponse,
    VectorStoreCreateResponse,
    VectorStoreStatusResponse,
    VectorStoreUploadFileResponse,
)
from src.services import vector_store_service as svc
from src.utils.errors import AppError


def _mock_client():
    client = MagicMock()
    client.beta.vector_stores.create.return_value = {"id": "vs_123"}
    client.files.create.return_value = {"id": "file_123"}
    client.beta.vector_stores.files.create.return_value = {"id": "file_123"}
    client.beta.vector_stores.retrieve.return_value = {"status": "completed", "created_at": "2026-01-07T00:00:00Z"}
    return client


@patch.object(svc, "_client")
def test_create_vector_store(mock_client_factory):
    mock_client_factory.return_value = _mock_client()
    resp = svc.create_vector_store("report", {"k": "v"})
    assert isinstance(resp, VectorStoreCreateResponse)
    assert resp.vector_store_id == "vs_123"


@patch.object(svc, "_client")
def test_upload_file(mock_client_factory, tmp_path):
    mock_client_factory.return_value = _mock_client()
    pdf = tmp_path / "f.pdf"
    pdf.write_bytes(b"hello")
    resp = svc.upload_file(str(pdf))
    assert isinstance(resp, VectorStoreUploadFileResponse)
    assert resp.openai_file_id == "file_123"


@patch.object(svc, "_client")
def test_attach_file(mock_client_factory):
    mock_client_factory.return_value = _mock_client()
    resp = svc.attach_file("vs_123", "file_123")
    assert isinstance(resp, VectorStoreAttachFileResponse)
    assert resp.openai_file_id == "file_123"


@patch.object(svc, "_client")
def test_wait_until_indexed_success(mock_client_factory):
    client = _mock_client()
    mock_client_factory.return_value = client
    resp = svc.wait_until_indexed("vs_123", timeout_s=1, poll_interval_s=0)
    assert isinstance(resp, VectorStoreStatusResponse)
    assert resp.status == "completed"


@patch.object(svc, "_client")
def test_wait_until_indexed_timeout(mock_client_factory):
    client = _mock_client()
    client.beta.vector_stores.retrieve.side_effect = [
        {"status": "in_progress"},
        {"status": "in_progress"},
    ]
    mock_client_factory.return_value = client
    with pytest.raises(AppError) as exc:
        svc.wait_until_indexed("vs_123", timeout_s=0, poll_interval_s=0)
    assert exc.value.code == "vector_store_index_timeout"
