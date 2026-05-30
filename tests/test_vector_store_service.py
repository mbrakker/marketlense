from __future__ import annotations

import pytest

from src.contracts.openai import (
    OpenAIVectorStoreAttachFileResponse,
    OpenAIVectorStoreCreateResponse,
    OpenAIVectorStoreDeleteResponse,
    OpenAIVectorStoreFileUploadResponse,
    OpenAIVectorStoreStatusResponse,
)
from src.contracts.vector_store import (
    VectorStoreAttachFileRequest,
    VectorStoreAttachFileResponse,
    VectorStoreCreateRequest,
    VectorStoreCreateResponse,
    VectorStoreDeleteRequest,
    VectorStoreDeleteResponse,
    VectorStoreMetadata,
    VectorStorePruneItem,
    VectorStorePruneRequest,
    VectorStorePruneResponse,
    VectorStoreStatusRequest,
    VectorStoreStatusResponse,
    VectorStoreUploadFileRequest,
    VectorStoreUploadFileResponse,
)
from src.services import vector_store_service as svc
from src.utils.errors import AppError


def _install_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def test_create_vector_store(monkeypatch: pytest.MonkeyPatch):
    _install_api_key(monkeypatch)

    def _create(req, ctx):
        return OpenAIVectorStoreCreateResponse(
            schema_version="1.0", vector_store_id="vs_123"
        )

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
        return OpenAIVectorStoreFileUploadResponse(
            schema_version="1.0", openai_file_id="file_123"
        )

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


def test_get_vector_store_status(monkeypatch: pytest.MonkeyPatch):
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
    resp = svc.get_vector_store_status(
        VectorStoreStatusRequest(
            schema_version="1.0",
            vector_store_id="vs_123",
        )
    )
    assert isinstance(resp, VectorStoreStatusResponse)
    assert resp.status == "completed"


def test_delete_vector_store_handles_missing_remote_asset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_api_key(monkeypatch)

    def _delete(req, ctx):
        raise AppError(
            code="openai_vector_store_delete_not_found",
            message="missing",
            retryable=False,
        )

    monkeypatch.setattr(svc.openai_service, "openai_vector_store_delete", _delete)

    resp = svc.delete_vector_store(
        VectorStoreDeleteRequest(
            schema_version="1.0",
            vector_store_id="vs_missing",
            missing_ok=True,
        )
    )

    assert isinstance(resp, VectorStoreDeleteResponse)
    assert resp.vector_store_id == "vs_missing"
    assert resp.deleted is False
    assert resp.missing_remote is True


def test_prune_vector_stores_deduplicates_and_reports_deletions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_api_key(monkeypatch)
    calls: list[str] = []

    def _delete(req, ctx):
        calls.append(req.vector_store_id)
        if req.vector_store_id == "vs_missing":
            raise AppError(
                code="openai_vector_store_delete_not_found",
                message="missing",
                retryable=False,
            )
        return OpenAIVectorStoreDeleteResponse(
            schema_version="1.0",
            vector_store_id=req.vector_store_id,
            deleted=True,
        )

    monkeypatch.setattr(svc.openai_service, "openai_vector_store_delete", _delete)

    resp = svc.prune_vector_stores(
        VectorStorePruneRequest(
            schema_version="1.0",
            items=[
                VectorStorePruneItem(
                    schema_version="1.0",
                    vector_store_id="vs_old",
                    reason="retention_expired",
                    file_id="file-1",
                ),
                VectorStorePruneItem(
                    schema_version="1.0",
                    vector_store_id="vs_old",
                    reason="retention_expired",
                    file_id="file-1",
                ),
                VectorStorePruneItem(
                    schema_version="1.0",
                    vector_store_id="vs_missing",
                    reason="retention_expired",
                    file_id="file-2",
                ),
            ],
        )
    )

    assert isinstance(resp, VectorStorePruneResponse)
    assert calls == ["vs_old", "vs_missing"]
    assert resp.requested_count == 3
    assert resp.deleted_vector_store_ids == ["vs_old"]
    assert resp.missing_vector_store_ids == ["vs_missing"]
    assert resp.skipped_duplicate_vector_store_ids == ["vs_old"]
