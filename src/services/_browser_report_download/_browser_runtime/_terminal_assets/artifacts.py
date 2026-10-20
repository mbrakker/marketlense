from __future__ import annotations

import json
import logging
import stat
from pathlib import Path
from typing import Any
from src.contracts.browser_download import (
    BrowserReportDownloadRequest,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download import http as http_runtime
from src.services._browser_report_download.artifact_materialization import (
    materialize_external_browser_artifact,
)
from src.services._browser_report_download.artifact_paths import (
    ensure_browser_directory,
    select_browser_pdf_destination_path,
    validate_browser_artifact_path,
    validate_browser_download_directory,
)
from src.services._browser_report_download.http import is_pdf_file
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")


def _parse_raw_model_response(raw_model_response: str) -> dict[str, Any]:
    token = str(raw_model_response or "").strip()
    if not token:
        return {}
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _prefetch_structured_pdf_artifact(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    raw_model_response: str,
    history_final_page_url: str,
) -> str:
    payload = _parse_raw_model_response(raw_model_response)
    if not payload:
        return ""
    route_kind = str(payload.get("route_kind") or "").strip()
    downloaded_name = str(payload.get("downloaded_file_name") or "").strip()
    downloaded_mime = str(payload.get("downloaded_mime_type") or "").strip().lower()
    if (
        route_kind != "pdf_download"
        and downloaded_mime != "application/pdf"
        and not downloaded_name.lower().endswith(".pdf")
    ):
        return ""
    for target_url in _structured_pdf_candidate_urls(
        payload=payload,
        history_final_page_url=history_final_page_url,
    ):
        destination_path = _pdf_prefetch_destination_path(
            download_dir=download_dir,
            target_url=target_url,
            downloaded_file_name=downloaded_name,
        )
        if destination_path.exists() and is_pdf_file(destination_path):
            return str(destination_path)
        committed_signature = None
        try:
            http_runtime.download_pdf_from_url(
                pdf_url=target_url,
                destination_path=destination_path,
                timeout_seconds=request.settings.timeout_seconds,
                ctx=ctx,
                normalized_url=normalized_url,
            )
            committed_signature = http_runtime.artifact_signature(destination_path)
        except AppError as exc:
            if exc.code == "browser_download_artifact_path_invalid":
                raise
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_pdf_prefetch_failed",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "target_url": target_url,
                        "error_code": exc.code,
                        "error_message": exc.message,
                    },
                )
            )
            http_runtime.cleanup_attempt_owned_pdf(
                destination_path,
                committed_signature=committed_signature,
            )
            continue
        if is_pdf_file(destination_path):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_pdf_prefetched",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "target_url": target_url,
                        "destination_path": str(destination_path),
                    },
                )
            )
            return str(destination_path)
        http_runtime.cleanup_attempt_owned_pdf(
            destination_path,
            committed_signature=committed_signature,
        )
    return ""


def _materialize_external_artifacts(
    *,
    raw_model_response: str,
    attachment_paths: list[str],
    downloaded_files: list[str],
    download_dir: Path,
    ctx: RunContext,
    normalized_url: str,
) -> list[str]:
    payload = _parse_raw_model_response(raw_model_response)
    candidate_paths = _local_artifact_candidate_paths(
        payload=payload,
        attachment_paths=attachment_paths,
        downloaded_files=downloaded_files,
    )
    if not candidate_paths:
        return []
    download_dir = validate_browser_download_directory(download_dir)
    ensure_browser_directory(download_dir)
    resolved_download_dir = _safe_resolve_path(download_dir)
    materialized_paths: list[str] = []
    seen_targets: set[str] = set()
    for source_path in candidate_paths:
        resolved_source = _safe_resolve_path(source_path)
        if resolved_source is None:
            continue
        if resolved_download_dir is not None and _is_within_directory(
            path=resolved_source,
            directory=resolved_download_dir,
        ):
            try:
                validate_browser_artifact_path(
                    resolved_source,
                    parent_dir=resolved_download_dir,
                    temporary_suffixes=(".part",),
                )
            except AppError as exc:
                if exc.code != "browser_download_artifact_path_invalid":
                    raise
            else:
                if _is_regular_readable_file(resolved_source):
                    token = str(resolved_source)
                    if token not in seen_targets:
                        seen_targets.add(token)
                        materialized_paths.append(token)
                    continue
        target_path = _copy_external_artifact(
            source_path=resolved_source,
            download_dir=download_dir,
        )
        if target_path is None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_external_artifact_copy_failed",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "source_path": str(resolved_source),
                    },
                )
            )
            continue
        token = str(target_path)
        if token in seen_targets:
            continue
        seen_targets.add(token)
        materialized_paths.append(token)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_external_artifact_materialized",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "source_path": str(resolved_source),
                    "destination_path": token,
                },
            )
        )
    return materialized_paths


def _local_artifact_candidate_paths(
    *,
    payload: dict[str, Any],
    attachment_paths: list[str],
    downloaded_files: list[str],
) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()

    def add(raw_value: Any) -> None:
        token = str(raw_value or "").strip()
        if not token or token.startswith(("http://", "https://")):
            return
        marker = token.casefold()
        if marker in seen:
            return
        path = Path(token).expanduser()
        if not path.exists() or not path.is_file():
            return
        seen.add(marker)
        candidates.append(path)

    add(payload.get("downloaded_file_path"))
    add(payload.get("onsite_capture_path"))
    for raw_path in attachment_paths:
        add(raw_path)
    for raw_path in downloaded_files:
        add(raw_path)
    return candidates


def _copy_external_artifact(
    *,
    source_path: Path,
    download_dir: Path,
) -> Path | None:
    return materialize_external_browser_artifact(
        source_path=source_path,
        download_dir=download_dir,
    )


def _is_regular_readable_file(path: Path) -> bool:
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            return False
        with path.open("rb"):
            return True
    except OSError:
        return False


def _safe_resolve_path(path: Path) -> Path | None:
    try:
        return path.expanduser().resolve()
    except OSError:
        return None


def _is_within_directory(*, path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _structured_pdf_candidate_urls(
    *,
    payload: dict[str, Any],
    history_final_page_url: str,
) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(raw_value: Any) -> None:
        token = str(raw_value or "").strip()
        if not _looks_like_pdf_resource_url(token):
            return
        marker = token.casefold()
        if marker in seen:
            return
        seen.add(marker)
        candidates.append(token)

    add(payload.get("resolved_target_url"))
    add(payload.get("final_page_url"))
    add(history_final_page_url)
    for raw_step in payload.get("route_steps", []):
        if isinstance(raw_step, dict):
            add(raw_step.get("target_url"))
    for raw_url in payload.get("traversed_page_urls", []):
        add(raw_url)
    return candidates


def _looks_like_pdf_resource_url(raw_url: str) -> bool:
    token = str(raw_url or "").strip()
    if not token:
        return False
    lowered = token.casefold()
    return lowered.startswith(("http://", "https://")) and (
        lowered.endswith(".pdf") or ".pdf?" in lowered
    )


def _pdf_prefetch_destination_path(
    *,
    download_dir: Path,
    target_url: str,
    downloaded_file_name: str,
) -> Path:
    return select_browser_pdf_destination_path(
        parent_dir=download_dir,
        source_name=downloaded_file_name,
        target_url=target_url,
    )


__all__ = [
    "_parse_raw_model_response",
    "_prefetch_structured_pdf_artifact",
    "_materialize_external_artifacts",
    "_local_artifact_candidate_paths",
    "_copy_external_artifact",
    "_safe_resolve_path",
    "_is_within_directory",
    "_structured_pdf_candidate_urls",
    "_looks_like_pdf_resource_url",
    "_pdf_prefetch_destination_path",
]
