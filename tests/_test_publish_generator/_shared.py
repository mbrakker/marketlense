from __future__ import annotations

# ruff: noqa: F401

import json
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image
import pytest

from src.contracts.publish import PublishRequest, PublishResolvedTerms
from src.contracts.report_store import ReportMetadataUpsertRequest
from src.generators import publish_generator as pg
from src.services.report_store_service import upsert_metadata
from src.utils.errors import AppError
from src.utils.html_utils import build_publish_html_snapshot
from tests.support.fakes import FakeHttpResponse, RecordedHttpRequest
from tests.support.publish_fixtures import (
    add_card_media_responses,
    write_report_card_fixture,
)


class _WordPressPublishStubHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    active_uploads = 0
    max_active_uploads = 0
    upload_headers: list[str] = []
    media_patch_headers: list[str] = []
    post_headers: list[str] = []
    next_media_id = 100
    lock = threading.Lock()

    @classmethod
    def reset(cls) -> None:
        with cls.lock:
            cls.active_uploads = 0
            cls.max_active_uploads = 0
            cls.upload_headers = []
            cls.media_patch_headers = []
            cls.post_headers = []
            cls.next_media_id = 100

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        auth_header = str(self.headers.get("Authorization") or "")
        content_length = int(self.headers.get("Content-Length") or "0")
        if content_length > 0:
            self.rfile.read(content_length)
        if self.path == "/wp-json/wp/v2/media":
            with self.lock:
                type(self).upload_headers.append(auth_header)
                type(self).active_uploads += 1
                if type(self).active_uploads > type(self).max_active_uploads:
                    type(self).max_active_uploads = type(self).active_uploads
                media_id = type(self).next_media_id
                type(self).next_media_id += 1
            try:
                time.sleep(0.35)
                self._send_json(
                    {
                        "id": media_id,
                        "source_url": f"http://127.0.0.1:{self.server.server_port}/media/{media_id}.png",
                    },
                    status=201,
                )
            finally:
                with self.lock:
                    type(self).active_uploads -= 1
            return
        if self.path.startswith("/wp-json/wp/v2/media/"):
            with self.lock:
                type(self).media_patch_headers.append(auth_header)
            media_id = int(self.path.rsplit("/", 1)[-1])
            self._send_json({"id": media_id}, status=200)
            return
        if self.path == "/wp-json/wp/v2/ml_report":
            with self.lock:
                type(self).post_headers.append(auth_header)
            self._send_json(
                {"id": 42, "link": "http://127.0.0.1/post/42", "status": "publish"},
                status=201,
            )
            return
        self._send_json({"error": "not found"}, status=404)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
    }
]
