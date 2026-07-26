from __future__ import annotations

import hashlib

# ruff: noqa: F401
import json
import threading
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image

from src.contracts.publish import PublishRequest as _PublishRequest
from src.contracts.publish import PublishResolvedTerms
from src.contracts.publish_readiness import PublishReadinessArtifact
from src.contracts.report_store import ReportMetadataUpsertRequest
from src.generators import publish_generator as pg
from src.services.report_store_service import upsert_metadata
from src.utils.errors import AppError
from src.utils.html_utils import build_publish_html_snapshot
from src.utils.publication_projection import publication_projection_hash
from tests.support.fakes import FakeHttpResponse, RecordedHttpRequest
from tests.support.publish_fixtures import (
    add_card_media_responses,
    write_report_card_fixture,
)


def _ready_publish_readiness(html_text: str, file_id: str) -> PublishReadinessArtifact:
    created_at = datetime.now(UTC)
    artifact = PublishReadinessArtifact(
        report_id=file_id,
        status="pass",
        artifact_hashes={},
        rule_results=[],
        final_html_hash=hashlib.sha256(html_text.encode("utf-8")).hexdigest(),
        publication_projection_hash=publication_projection_hash(html_text),
        configuration_hash=hashlib.sha256(
            b"publish-readiness:configuration:unavailable"
        ).hexdigest(),
        policy_hash=hashlib.sha256(b"publish-readiness:policy:unavailable").hexdigest(),
        producer_revision="workspace",
        created_at_utc=created_at.isoformat(),
        expires_at_utc=(created_at + timedelta(hours=1)).isoformat(),
        staleness_conditions=["final_html_hash_changed"],
        provenance={},
    )
    signature_payload = asdict(replace(artifact, artifact_hash=""))
    signature = hashlib.sha256(
        json.dumps(
            signature_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return replace(artifact, artifact_hash=signature)


def PublishRequest(*args, **kwargs):  # noqa: N802
    """Create a request bound to its exact test HTML unless explicitly omitted."""
    request = _PublishRequest(*args, **kwargs)
    if "publish_readiness" in kwargs or request.publish_readiness is not None:
        return request
    html_text = request.html_text
    if html_text is None and request.html_snapshot is not None:
        html_text = request.html_snapshot.html_text
    if html_text is None:
        html_path = Path(request.html_path)
        if html_path.is_file():
            html_text = html_path.read_text(encoding="utf-8")
    file_id = request.file_id or (
        request.html_snapshot.file_id if request.html_snapshot is not None else None
    )
    if not file_id and html_text:
        file_id = build_publish_html_snapshot(html_text).file_id
    if not html_text or not file_id:
        return request
    return replace(
        request,
        publish_readiness=_ready_publish_readiness(html_text, str(file_id)),
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
