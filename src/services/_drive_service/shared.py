from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

from dataclasses import dataclass
import hashlib
import httplib2
import io
import logging
import json
import threading
import time
from pathlib import Path
from typing import Iterable, Iterator, Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.oauth2.credentials import Credentials as AuthorizedUserCredentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:  # pragma: no cover - dependency guard
    InstalledAppFlow = None

from src.contracts.drive import (
    DriveDownloadRequest,
    DriveDownloadResponse,
    DriveDownloadToPathRequest,
    DriveDownloadToPathResponse,
    DriveFile,
    DriveFileMetadataRequest,
    DriveFileMetadataResponse,
    DriveFolderEnsureRequest,
    DriveFolderEnsureResponse,
    DriveFolderFileListRequest,
    DriveFolderFileListResponse,
    DriveListRequest,
    DriveOAuthAuthorizeRequest,
    DriveOAuthAuthorizeResponse,
    DriveWritePreflightRequest,
    DriveWritePreflightResponse,
    DriveUploadBytesRequest,
    DriveUploadBytesResponse,
    DriveUploadLocalFileRequest,
    DriveUploadLocalFileResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.drive_service")
Credentials = ServiceAccountCredentials
DRIVE_CLIENT_CACHE_TTL_SECONDS = 900.0
DRIVE_CLIENT_CACHE_MAX_ENTRIES = 32
DRIVE_FOLDER_SCOPE_CACHE_TTL_SECONDS = 300.0
DRIVE_FOLDER_SCOPE_CACHE_MAX_ENTRIES = 128
DRIVE_HTTP_TIMEOUT_SECONDS = 30.0


@dataclass
class _DriveClientCacheEntry:
    client: object
    expires_at: float
    last_access_at: float


@dataclass
class _DriveFolderScopeCacheEntry:
    folder_ids: tuple[str, ...]
    expires_at: float
    last_access_at: float


@dataclass(frozen=True)
class _DriveCredentialResolution:
    credentials: object
    refreshed: bool
    credential_path: str


_DRIVE_CLIENTS: dict[tuple[str, str, int], _DriveClientCacheEntry] = {}
_DRIVE_CLIENTS_LOCK = threading.Lock()
_FOLDER_SCOPE_CACHE: dict[
    tuple[str, str, str, bool, bool], _DriveFolderScopeCacheEntry
] = {}
_FOLDER_SCOPE_CACHE_LOCK = threading.Lock()
DRIVE_BOUNDARY_EXCEPTIONS = (HttpError, OSError, RuntimeError, ValueError, TypeError)
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


class _HashingWriter:
    def __init__(self, handle):
        self._handle = handle
        self._hash = hashlib.md5()
        self._bytes_written = 0

    def write(self, data: bytes) -> int:
        if not data:
            return 0
        self._hash.update(data)
        self._bytes_written += len(data)
        return self._handle.write(data)

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        return self._handle.seek(offset, whence)

    def tell(self) -> int:
        return self._handle.tell()

    def flush(self) -> None:
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()

    @property
    def md5(self) -> Optional[str]:
        if self._bytes_written <= 0:
            return None
        return self._hash.hexdigest()

    @property
    def bytes_written(self) -> int:
        return self._bytes_written


def _normalize_drive_auth_mode(raw_mode: str | None) -> str:
    token = str(raw_mode or "service_account").strip().lower()
    if token in {"service_account", "oauth_user"}:
        return token
    raise AppError(
        code="drive_auth_mode_invalid",
        message="Drive auth mode must be service_account or oauth_user",
        retryable=False,
        context={"auth_mode": raw_mode or ""},
    )


def _now_monotonic_seconds() -> float:
    return float(time.monotonic())


def _principal_path(
    *, auth_mode: str, service_account_path: str, oauth_token_path: str | None
) -> str:
    return (
        str(service_account_path or "").strip()
        if auth_mode == "service_account"
        else str(oauth_token_path or "").strip()
    )


def _require_drive_auth(
    *,
    auth_mode: str,
    service_account_path: str,
    oauth_token_path: str | None,
) -> None:
    if auth_mode == "service_account":
        if not service_account_path:
            raise AppError(
                code="drive_sa_path_missing",
                message="Service account path is required when Drive auth mode is service_account",
                retryable=False,
            )
        return
    if not str(oauth_token_path or "").strip():
        raise AppError(
            code="drive_oauth_token_path_missing",
            message="OAuth token path is required when Drive auth mode is oauth_user",
            retryable=False,
        )


def _request_auth_mode(request) -> str:
    return _normalize_drive_auth_mode(getattr(request, "auth_mode", "service_account"))


def _md5_for_bytes(data: bytes) -> str:
    h = hashlib.md5()
    h.update(data)
    return h.hexdigest()


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
