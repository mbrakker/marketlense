# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath
__file__ = str(_SplitPath(__file__).resolve().parent.parent / "test_drive_service_listing.py")

from dataclasses import dataclass

from typing import Any

import pytest

from src.contracts.drive import (
    DriveOAuthAuthorizeRequest,
    DriveDownloadToPathRequest,
    DriveFolderFileListRequest,
    DriveListRequest,
    DriveWritePreflightRequest,
    DriveUploadBytesRequest,
    DriveUploadLocalFileRequest,
    DriveFile,
    DriveFolderEnsureRequest,
)

from src.contracts.run_context import RunContext

from src.services import drive_service

from src.utils.errors import AppError

@dataclass
class _FakeListCall:
    payload: dict

    def execute(self):
        return self.payload

class _FakeFilesResource:
    def __init__(
        self,
        responses: dict[Any, dict],
        raise_on_query: str | None = None,
        get_response: dict | None = None,
        get_error: Exception | None = None,
        create_error: Exception | None = None,
        delete_error: Exception | None = None,
    ):
        self._responses = responses
        self._raise_on_query = raise_on_query
        self._get_response = get_response or {}
        self._get_error = get_error
        self._create_error = create_error
        self._delete_error = delete_error
        self.created_payloads: list[dict] = []
        self.delete_calls: list[dict] = []
        self.list_calls: list[dict] = []
        self.get_calls: list[dict] = []

    def list(self, **kwargs):
        query = kwargs.get("q", "")
        if self._raise_on_query and self._raise_on_query == query:
            raise RuntimeError("boom")
        self.list_calls.append(dict(kwargs))
        page_token = kwargs.get("pageToken")
        payload = self._responses.get((query, page_token))
        if payload is None:
            payload = self._responses.get(query, {"files": [], "nextPageToken": None})
        return _FakeListCall(payload)

    def create(self, **kwargs):
        if self._create_error is not None:
            raise self._create_error
        payload = {
            "id": "uploaded-file",
            "name": kwargs["body"]["name"],
            "modifiedTime": "2026-03-29T00:00:00Z",
            "md5Checksum": "abc123",
            "mimeType": "application/json",
        }
        self.created_payloads.append(kwargs)
        return _FakeListCall(payload)

    def delete(self, **kwargs):
        self.delete_calls.append(dict(kwargs))
        if self._delete_error is not None:
            raise self._delete_error
        return _FakeListCall({})

    def get(self, **kwargs):
        self.get_calls.append(dict(kwargs))
        if self._get_error is not None:
            raise self._get_error
        return _FakeListCall(self._get_response)

    def get_media(self, *, fileId):
        return {"fileId": fileId}

class _FakeDriveClient:
    def __init__(
        self,
        responses: dict[str, dict],
        raise_on_query: str | None = None,
        get_response: dict | None = None,
        get_error: Exception | None = None,
        create_error: Exception | None = None,
        delete_error: Exception | None = None,
    ):
        self._files_resource = _FakeFilesResource(
            responses,
            raise_on_query=raise_on_query,
            get_response=get_response,
            get_error=get_error,
            create_error=create_error,
            delete_error=delete_error,
        )

    def files(self):
        return self._files_resource

class _FakeAuthorizedUserCredentials:
    def __init__(
        self,
        *,
        valid: bool = True,
        expired: bool = False,
        refresh_token: str | None = "refresh-token",
        scopes: list[str] | None = None,
        refresh_error: Exception | None = None,
    ):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.scopes = scopes or ["https://www.googleapis.com/auth/drive"]
        self.refresh_error = refresh_error
        self.refresh_count = 0

    def refresh(self, _request):
        self.refresh_count += 1
        if self.refresh_error is not None:
            raise self.refresh_error
        self.valid = True
        self.expired = False

    def to_json(self) -> str:
        return '{"refresh_token":"refresh-token","client_id":"client","client_secret":"secret","scopes":["https://www.googleapis.com/auth/drive"]}'

def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r1", task_id="t1", span_id="s1")

def _reset_drive_caches() -> None:
    drive_service._DRIVE_CLIENTS = {}
    drive_service._FOLDER_SCOPE_CACHE = {}

def _request() -> DriveListRequest:
    return DriveListRequest(
        schema_version="1.0",
        folder_id="root-folder",
        service_account_path="/tmp/fake-sa.json",
        list_mode="full",
    )



__all__ = [
    name
    for name in globals()
    if name
    not in {
        '__name__', '__annotations__', '__doc__', '__spec__',
        '__file__', '__package__', '__loader__', '__cached__',
        '__builtins__', '_SplitPath',
    }
]
