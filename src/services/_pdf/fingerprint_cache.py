from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pymupdf as fitz

from src.contracts.pdf_utils import (
    CropPublicationProofRequest,
    CropPublicationProofResponse,
)
from src.utils.cache_utils import sha256_json

FINGERPRINT_RECORD_SCHEMA_VERSION = "2.0"
PAGE_CONTENT_FINGERPRINT_VERSION = "1.0"
PAGE_CONTENT_FINGERPRINT_DPI = 48
PREVIEW_ARTIFACT_VERSION = "1.0"
CROP_REFINE_PAGE_ARTIFACT_VERSION = "1.0"
# Crop cache acceptance now depends on the final strict-QA diagnostic sidecar.
# Bump only this artifact so pre-QA cache entries are rebuilt without
# invalidating unrelated preview/refinement artifacts.
CROP_REGION_ARTIFACT_VERSION = "1.3"


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
    output_sha256: str = ""
    qa_sidecar_sha256: str = ""


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
    if stored.get("schema_version") != record.schema_version:
        return _miss_status(record, sidecar_path, "schema_version_changed")
    if stored.get("output_sha256") != _file_sha256(artifact_path):
        return _miss_status(record, sidecar_path, "output_hash_changed")
    qa_sidecar_path = _qa_sidecar_path(artifact_path)
    actual_qa_hash = _file_sha256(qa_sidecar_path) if qa_sidecar_path.exists() else ""
    if stored.get("qa_sidecar_sha256") != actual_qa_hash:
        return _miss_status(record, sidecar_path, "qa_sidecar_hash_changed")
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
    # Crop callers may supply paths rooted at the workspace rather than an
    # absolute path. Resolve once so tempfile and os.replace always address
    # the same directory on Windows.
    artifact_path = artifact_path.resolve()
    record = descriptor.record()
    sidecar_path = _sidecar_path(artifact_path)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    payload_data = asdict(record)
    payload_data["output_sha256"] = _file_sha256(artifact_path)
    qa_sidecar_path = _qa_sidecar_path(artifact_path)
    payload_data["qa_sidecar_sha256"] = (
        _file_sha256(qa_sidecar_path) if qa_sidecar_path.exists() else ""
    )
    payload = json.dumps(payload_data, ensure_ascii=True, sort_keys=True)
    # Several crop workers can materialize the same cached artifact at once.
    # A PID-only temporary name collides within a worker process, allowing one
    # writer to move the other's file before it reaches ``os.replace``.
    file_descriptor, temp_name = tempfile.mkstemp(
        # Keep the temporary filename short: on Windows the final sidecar can
        # fit while repeating its full name in the temporary prefix exceeds
        # the legacy path limit under parallel test/work directories.
        prefix=".tmp-write-",
        dir=sidecar_path.parent,
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
        _replace_sidecar(temp_path, sidecar_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return sidecar_path.as_posix()


def verify_crop_publication_proof(
    request: CropPublicationProofRequest,
) -> CropPublicationProofResponse:
    def rejected(reason: str) -> CropPublicationProofResponse:
        return CropPublicationProofResponse(
            schema_version="1.0", accepted=False, reason=reason
        )

    if request.schema_version != "1.0":
        return rejected("proof_schema_unsupported")
    root = Path(request.output_dir)
    image_rel = Path(request.image_path)
    qa_rel = Path(request.qa_sidecar_path)
    if image_rel.is_absolute() or qa_rel.is_absolute():
        return rejected("proof_path_not_relative")
    try:
        root = root.resolve()
        image_path = (root / image_rel).resolve()
        qa_path = (root / qa_rel).resolve()
        image_path.relative_to(root)
        qa_path.relative_to(root)
    except (OSError, ValueError):
        return rejected("proof_path_outside_output")
    expected_qa_rel = image_rel.with_suffix(image_rel.suffix + ".qa.json")
    if qa_rel.as_posix() != expected_qa_rel.as_posix():
        return rejected("qa_sidecar_path_mismatch")
    if not image_path.is_file():
        return rejected("crop_image_missing")
    if not qa_path.is_file():
        return rejected("qa_sidecar_missing")

    image_sha256 = _file_sha256(image_path)
    expected_image_sha256 = str(request.expected_image_sha256 or "").strip().casefold()
    if (
        not re.fullmatch(r"[0-9a-f]{64}", expected_image_sha256)
        or image_sha256 != expected_image_sha256
    ):
        return rejected("crop_image_hash_mismatch")

    qa_record = _load_sidecar(qa_path)
    if qa_record is None:
        return rejected("qa_sidecar_invalid")
    if qa_record.get("schema_version") != "1.0":
        return rejected("qa_schema_mismatch")
    if str(qa_record.get("candidate_id") or "") != request.candidate_id:
        return rejected("qa_candidate_mismatch")
    if qa_record.get("page") != request.page:
        return rejected("qa_page_mismatch")
    if (
        str(qa_record.get("candidate_type") or "").casefold()
        != str(request.item_type or "").casefold()
    ):
        return rejected("qa_candidate_type_mismatch")
    expected_effective_mode = {
        "chart": "chart_strict",
        "table": "table_strict",
    }.get(str(request.item_type or "").casefold(), "publication_strict")
    if (
        qa_record.get("mode") != "publication_strict"
        or qa_record.get("effective_mode") != expected_effective_mode
    ):
        return rejected("qa_profile_mismatch")
    if qa_record.get("render_dpi") != request.render_dpi:
        return rejected("qa_dpi_mismatch")
    qa_result = qa_record.get("qa")
    defects = qa_result.get("defect_labels") if isinstance(qa_result, dict) else None
    if (
        qa_record.get("accepted") is not True
        or not isinstance(qa_result, dict)
        or qa_result.get("accepted") is not True
        or not isinstance(defects, list)
        or defects
    ):
        return rejected("qa_not_accepted")

    fingerprint_record = _load_sidecar(_sidecar_path(image_path))
    if fingerprint_record is None:
        return rejected("fingerprint_sidecar_missing_or_invalid")
    if fingerprint_record.get("schema_version") != FINGERPRINT_RECORD_SCHEMA_VERSION:
        return rejected("fingerprint_schema_mismatch")
    if (
        fingerprint_record.get("artifact_kind") != "crop_region"
        or fingerprint_record.get("artifact_version") != CROP_REGION_ARTIFACT_VERSION
    ):
        return rejected("fingerprint_artifact_version_mismatch")
    if (
        fingerprint_record.get("output_rel_path") != image_rel.as_posix()
        or fingerprint_record.get("page") != request.page
    ):
        return rejected("fingerprint_artifact_identity_mismatch")
    actual_qa_sha256 = _file_sha256(qa_path)
    if (
        fingerprint_record.get("output_sha256") != image_sha256
        or fingerprint_record.get("qa_sidecar_sha256") != actual_qa_sha256
    ):
        return rejected("fingerprint_content_hash_mismatch")
    artifact_identity = fingerprint_record.get("artifact_identity")
    if not isinstance(artifact_identity, str):
        return rejected("fingerprint_artifact_identity_invalid")
    try:
        parsed_identity = json.loads(artifact_identity)
    except (TypeError, json.JSONDecodeError):
        return rejected("fingerprint_artifact_identity_invalid")
    if not isinstance(parsed_identity, dict) or (
        parsed_identity.get("item_id") != request.candidate_id
        or str(parsed_identity.get("item_type") or "").casefold()
        != str(request.item_type or "").casefold()
        or parsed_identity.get("page") != request.page
    ):
        return rejected("fingerprint_artifact_identity_mismatch")

    return CropPublicationProofResponse(
        schema_version="1.0", accepted=True, reason="verified"
    )


def _sidecar_path(artifact_path: Path) -> Path:
    return artifact_path.with_name(f"{artifact_path.name}.fingerprint.json")


def _qa_sidecar_path(artifact_path: Path) -> Path:
    return artifact_path.with_name(f"{artifact_path.name}.qa.json")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _replace_sidecar(temp_path: Path, sidecar_path: Path) -> None:
    """Tolerate a bounded Windows replace race between cache writers."""

    for attempt in range(5):
        try:
            os.replace(temp_path, sidecar_path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.01 * (attempt + 1))


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
