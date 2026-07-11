from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pymupdf as fitz

from src.utils.cache_utils import sha256_json

FINGERPRINT_RECORD_SCHEMA_VERSION = "1.0"
PAGE_CONTENT_FINGERPRINT_VERSION = "1.0"
PAGE_CONTENT_FINGERPRINT_DPI = 48
PREVIEW_ARTIFACT_VERSION = "1.0"
CROP_REFINE_PAGE_ARTIFACT_VERSION = "1.0"
# Crop cache acceptance now depends on the final strict-QA diagnostic sidecar.
# Bump only this artifact so pre-QA cache entries are rebuilt without
# invalidating unrelated preview/refinement artifacts.
CROP_REGION_ARTIFACT_VERSION = "1.1"


@dataclass(frozen=True)
class PdfArtifactFingerprintRecord:
    schema_version: str
    artifact_kind: str
    cache_key: str
    source_pdf_path: str
    output_rel_path: str
    page: int
    artifact_identity: str
    content_fingerprint: str
    settings_fingerprint: str
    parser_fingerprint: str
    artifact_version: str


@dataclass(frozen=True)
class PdfArtifactFingerprintDescriptor:
    artifact_kind: str
    source_pdf_path: str
    output_rel_path: str
    page: int
    artifact_identity: str
    content_fingerprint: str
    settings_payload: dict[str, Any]
    artifact_version: str

    def record(self) -> PdfArtifactFingerprintRecord:
        return PdfArtifactFingerprintRecord(
            schema_version=FINGERPRINT_RECORD_SCHEMA_VERSION,
            artifact_kind=self.artifact_kind,
            cache_key=self.cache_key,
            source_pdf_path=self.source_pdf_path,
            output_rel_path=self.output_rel_path,
            page=self.page,
            artifact_identity=self.artifact_identity,
            content_fingerprint=self.content_fingerprint,
            settings_fingerprint=sha256_json(self.settings_payload),
            parser_fingerprint=_parser_fingerprint(),
            artifact_version=self.artifact_version,
        )

    @property
    def cache_key(self) -> str:
        return sha256_json(
            {
                "artifact_kind": self.artifact_kind,
                "page": self.page,
                "artifact_identity": self.artifact_identity,
                "content_fingerprint": self.content_fingerprint,
                "settings_payload": self.settings_payload,
                "parser_fingerprint": _parser_fingerprint(),
                "artifact_version": self.artifact_version,
            }
        )


@dataclass(frozen=True)
class PdfArtifactCacheStatus:
    hit: bool
    reason: str
    cache_key: str
    sidecar_path: str
    output_rel_path: str


def build_page_content_fingerprint(
    page: fitz.Page,
    *,
    per_page_cache: dict[int, str] | None = None,
) -> str:
    page_number = int(page.number)
    if per_page_cache is not None and page_number in per_page_cache:
        return per_page_cache[page_number]
    zoom = PAGE_CONTENT_FINGERPRINT_DPI / 72.0
    pix = page.get_pixmap(
        matrix=fitz.Matrix(zoom, zoom),
        colorspace=fitz.csGRAY,
        alpha=False,
    )
    digest = hashlib.sha256()
    digest.update(PAGE_CONTENT_FINGERPRINT_VERSION.encode("utf-8"))
    digest.update(f"{pix.width}x{pix.height}".encode("utf-8"))
    digest.update(f"{page.rect.width:.4f}x{page.rect.height:.4f}".encode("utf-8"))
    digest.update(pix.samples)
    value = digest.hexdigest()
    if per_page_cache is not None:
        per_page_cache[page_number] = value
    return value


def resolve_artifact_cache(
    descriptor: PdfArtifactFingerprintDescriptor,
    artifact_path: Path,
) -> PdfArtifactCacheStatus:
    record = descriptor.record()
    sidecar_path = _sidecar_path(artifact_path)
    if not artifact_path.exists():
        return PdfArtifactCacheStatus(
            hit=False,
            reason="output_missing",
            cache_key=record.cache_key,
            sidecar_path=sidecar_path.as_posix(),
            output_rel_path=record.output_rel_path,
        )
    if not sidecar_path.exists():
        return PdfArtifactCacheStatus(
            hit=False,
            reason="sidecar_missing",
            cache_key=record.cache_key,
            sidecar_path=sidecar_path.as_posix(),
            output_rel_path=record.output_rel_path,
        )
    stored = _load_sidecar(sidecar_path)
    if stored is None:
        return PdfArtifactCacheStatus(
            hit=False,
            reason="sidecar_invalid",
            cache_key=record.cache_key,
            sidecar_path=sidecar_path.as_posix(),
            output_rel_path=record.output_rel_path,
        )
    if stored.get("artifact_kind") != record.artifact_kind:
        return _miss_status(record, sidecar_path, "artifact_kind_changed")
    if stored.get("artifact_identity") != record.artifact_identity:
        return _miss_status(record, sidecar_path, "artifact_identity_changed")
    if stored.get("artifact_version") != record.artifact_version:
        return _miss_status(record, sidecar_path, "version_changed")
    if stored.get("parser_fingerprint") != record.parser_fingerprint:
        return _miss_status(record, sidecar_path, "parser_changed")
    if stored.get("settings_fingerprint") != record.settings_fingerprint:
        return _miss_status(record, sidecar_path, "settings_changed")
    if stored.get("content_fingerprint") != record.content_fingerprint:
        return _miss_status(record, sidecar_path, "content_changed")
    if stored.get("cache_key") != record.cache_key:
        return _miss_status(record, sidecar_path, "cache_key_changed")
    return PdfArtifactCacheStatus(
        hit=True,
        reason="matched",
        cache_key=record.cache_key,
        sidecar_path=sidecar_path.as_posix(),
        output_rel_path=record.output_rel_path,
    )


def write_artifact_sidecar(
    descriptor: PdfArtifactFingerprintDescriptor,
    artifact_path: Path,
) -> str:
    record = descriptor.record()
    sidecar_path = _sidecar_path(artifact_path)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(record), ensure_ascii=True, sort_keys=True)
    temp_path = sidecar_path.with_name(f"{sidecar_path.name}.tmp-write-{os.getpid()}")
    temp_path.write_text(payload, encoding="utf-8")
    os.replace(temp_path, sidecar_path)
    return sidecar_path.as_posix()


def _sidecar_path(artifact_path: Path) -> Path:
    return artifact_path.with_name(f"{artifact_path.name}.fingerprint.json")


def _parser_fingerprint() -> str:
    return (
        f"pymupdf:{getattr(fitz, 'VersionFitz', '')}:"
        f"bind:{getattr(fitz, 'VersionBind', '')}:"
        f"page_fingerprint:{PAGE_CONTENT_FINGERPRINT_VERSION}:"
        f"dpi:{PAGE_CONTENT_FINGERPRINT_DPI}"
    )


def _load_sidecar(sidecar_path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _miss_status(
    record: PdfArtifactFingerprintRecord,
    sidecar_path: Path,
    reason: str,
) -> PdfArtifactCacheStatus:
    return PdfArtifactCacheStatus(
        hit=False,
        reason=reason,
        cache_key=record.cache_key,
        sidecar_path=sidecar_path.as_posix(),
        output_rel_path=record.output_rel_path,
    )
