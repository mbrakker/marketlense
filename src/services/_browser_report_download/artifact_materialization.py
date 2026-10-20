"""Bounded, idempotent materialization of browser-owned artifact files."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Literal

from src.services._browser_report_download.artifact_paths import (
    ensure_browser_directory,
    resolve_browser_artifact_path,
    validate_browser_artifact_path,
    validate_browser_download_directory,
)
from src.utils.errors import AppError

_COPY_CHUNK_BYTES = 1024 * 1024
_MAX_MATERIALIZATION_ATTEMPTS = 100
_PublishResult = Literal["published", "conflict", "failed"]


def materialize_external_browser_artifact(
    *,
    source_path: Path,
    download_dir: Path,
) -> Path | None:
    """Copy one external artifact below the browser root without clobbering it."""

    download_dir = validate_browser_download_directory(download_dir)
    ensure_browser_directory(download_dir)
    source = _resolve_source(source_path)
    if source is None:
        return None

    source_identity = str(source)
    candidates: list[Path] = []
    normal_path = resolve_browser_artifact_path(
        parent_dir=download_dir,
        source_name=source.name,
        identity=source_identity,
        temporary_suffixes=(".part",),
    )
    candidates.append(normal_path)
    identity_path = resolve_browser_artifact_path(
        parent_dir=download_dir,
        source_name=source.name,
        identity=source_identity,
        force_identity_hash=True,
        temporary_suffixes=(".part",),
    )
    if identity_path not in candidates:
        candidates.append(identity_path)

    content_digest: str | None = None
    for attempt_index in range(_MAX_MATERIALIZATION_ATTEMPTS):
        if attempt_index < len(candidates):
            target_path = candidates[attempt_index]
        else:
            if content_digest is None:
                content_digest = _sha256_file(source)
                if content_digest is None:
                    return None
            target_path = resolve_browser_artifact_path(
                parent_dir=download_dir,
                source_name=source.name,
                identity=(
                    f"{source_identity}|sha256:{content_digest}"
                    f"|collision:{attempt_index}"
                ),
                force_identity_hash=True,
                temporary_suffixes=(".part",),
            )

        target_state = _existing_target_state(
            source_path=source,
            target_path=target_path,
            download_dir=download_dir,
        )
        if target_state == "identical":
            return target_path
        if target_state == "invalid":
            raise AppError(
                code="browser_download_artifact_path_invalid",
                message="Browser artifact destination is not safely contained",
                retryable=False,
                context={
                    "path_role": "external browser artifact",
                    "next_action": "Choose a safe browser output directory",
                },
            )
        if target_state == "different":
            if content_digest is None:
                content_digest = _sha256_file(source)
                if content_digest is None:
                    return None
            continue

        publish_result = _copy_and_publish(
            source_path=source,
            target_path=target_path,
        )
        if publish_result == "published":
            if (
                _existing_target_state(
                    source_path=source,
                    target_path=target_path,
                    download_dir=download_dir,
                )
                == "identical"
            ):
                return target_path
            _unlink_owned_file(target_path)
            return None
        if publish_result == "failed":
            return None

    raise AppError(
        code="browser_download_artifact_collision_exhausted",
        message="External browser artifact destinations remain ambiguous",
        retryable=False,
        context={
            "path_role": "external browser artifact",
            "next_action": (
                "Remove stale duplicate artifacts or choose a shorter "
                "browser output directory"
            ),
        },
    )


def _resolve_source(source_path: Path) -> Path | None:
    try:
        source = Path(source_path).expanduser().resolve()
        source_stat = source.stat()
        if not stat.S_ISREG(source_stat.st_mode):
            return None
        with source.open("rb"):
            pass
    except OSError:
        return None
    return source


def _existing_target_state(
    *,
    source_path: Path,
    target_path: Path,
    download_dir: Path,
) -> Literal["missing", "identical", "different", "invalid"]:
    try:
        validate_browser_artifact_path(
            target_path,
            parent_dir=download_dir,
            temporary_suffixes=(".part",),
        )
    except AppError:
        return "invalid"
    try:
        target_stat = target_path.lstat()
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "different"
    if not stat.S_ISREG(target_stat.st_mode):
        return "different"
    if not _is_readable(target_path):
        return "different"
    return "identical" if _files_equal(source_path, target_path) else "different"


def _copy_and_publish(*, source_path: Path, target_path: Path) -> _PublishResult:
    temp_path = target_path.with_name(f"{target_path.name}.part")
    try:
        with source_path.open("rb") as source, temp_path.open("xb") as target:
            while True:
                chunk = source.read(_COPY_CHUNK_BYTES)
                if not chunk:
                    break
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
    except FileExistsError:
        return "conflict"
    except OSError:
        _unlink_owned_file(temp_path)
        return "failed"

    try:
        if os.name == "nt":
            os.rename(temp_path, target_path)
        else:
            os.link(temp_path, target_path)
            temp_path.unlink()
    except FileExistsError:
        _unlink_owned_file(temp_path)
        return "conflict"
    except OSError:
        _unlink_owned_file(temp_path)
        return "failed"
    return "published"


def _files_equal(left: Path, right: Path) -> bool:
    try:
        left_stat = left.stat()
        right_stat = right.stat()
        if not stat.S_ISREG(left_stat.st_mode) or not stat.S_ISREG(right_stat.st_mode):
            return False
        if left_stat.st_size != right_stat.st_size:
            return False
        with left.open("rb") as left_handle, right.open("rb") as right_handle:
            while True:
                left_chunk = left_handle.read(_COPY_CHUNK_BYTES)
                right_chunk = right_handle.read(_COPY_CHUNK_BYTES)
                if left_chunk != right_chunk:
                    return False
                if not left_chunk:
                    return True
    except OSError:
        return False


def _sha256_file(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(_COPY_CHUNK_BYTES)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _is_readable(path: Path) -> bool:
    try:
        with path.open("rb"):
            return True
    except OSError:
        return False


def _unlink_owned_file(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        return


__all__ = ["materialize_external_browser_artifact"]
