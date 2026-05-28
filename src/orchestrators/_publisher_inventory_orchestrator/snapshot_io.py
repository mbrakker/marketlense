from __future__ import annotations

"""Snapshot loading and naming for publisher-inventory orchestration.

This module owns previous-snapshot discovery through the injected Drive
boundary and deterministic snapshot filename construction.
"""

import hashlib
import logging
from datetime import datetime, timezone

from src.contracts.drive import (
    DriveDownloadRequest,
    DriveFile,
    DriveFolderFileListRequest,
)
from src.contracts.publisher_inventory import PublisherInventorySnapshot
from src.contracts.report_store import PublisherInventoryStateResponse
from src.contracts.run_context import RunContext
from src.orchestrators._publisher_inventory_orchestrator.dependencies import (
    PublisherInventoryDependencies,
)
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.publisher_inventory_orchestrator")


_SNAPSHOT_PREFIX = "publisher_inventory_snapshot__"

_SNAPSHOT_LOOKBACK_LIMIT = 10


def _load_previous_snapshot(
    *,
    publisher_state: PublisherInventoryStateResponse,
    folder_id: str,
    settings,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> tuple[PublisherInventorySnapshot | None, str | None, str | None, str | None]:
    file_id = publisher_state.inventory_snapshot_drive_file_id
    file_name = publisher_state.inventory_snapshot_drive_file_name
    snapshot_sha256 = publisher_state.inventory_snapshot_sha256
    candidates: list[tuple[str, str | None, str | None]] = []
    if file_id:
        candidates.append((file_id, file_name, snapshot_sha256))
    if not file_id:
        listed = dependencies.list_files_in_folder(
            DriveFolderFileListRequest(
                schema_version="1.0",
                folder_id=folder_id,
                service_account_path=settings.google_sa_path,
                auth_mode=settings.drive_auth_mode,
                oauth_client_path=settings.google_oauth_client_path,
                oauth_token_path=settings.google_oauth_token_path,
                name_prefix=_SNAPSHOT_PREFIX,
                order_by="modifiedTime desc",
                limit=_SNAPSHOT_LOOKBACK_LIMIT,
                supports_all_drives=True,
                include_items_from_all_drives=True,
            ),
            ctx,
        )
        candidates.extend((file.file_id, file.name, None) for file in listed.files)
    if not candidates:
        return None, None, None, None

    for candidate_file_id, candidate_file_name, candidate_sha256 in candidates:
        download_response = dependencies.download_pdf(
            DriveDownloadRequest(
                schema_version="1.0",
                file=DriveFile(
                    schema_version="1.0",
                    file_id=candidate_file_id,
                    name=candidate_file_name,
                    modified_time=None,
                    md5_checksum=None,
                    mime_type="application/json",
                ),
                service_account_path=settings.google_sa_path,
                auth_mode=settings.drive_auth_mode,
                oauth_client_path=settings.google_oauth_client_path,
                oauth_token_path=settings.google_oauth_token_path,
            ),
            ctx,
        )
        snapshot_payload = download_response.content.decode("utf-8")
        resolved_sha256 = (
            candidate_sha256
            or hashlib.sha256(snapshot_payload.encode("utf-8")).hexdigest()
        )
        try:
            snapshot = dependencies.parse_publisher_inventory_snapshot(
                snapshot_payload,
                f"drive:{candidate_file_id}",
                ctx,
            )
        except AppError as exc:
            if exc.code != "publisher_inventory_snapshot_invalid_payload":
                raise
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_previous_snapshot_skipped",
                    module=logger.name,
                    fields={
                        "publisher_name": publisher_state.publisher_name,
                        "snapshot_drive_file_id": candidate_file_id,
                        "snapshot_drive_file_name": candidate_file_name or "",
                        "snapshot_sha256": resolved_sha256,
                        "code": exc.code,
                    },
                )
            )
            continue
        if normalize_url(snapshot.normalized_insights_url) != normalize_url(
            publisher_state.normalized_url
        ):
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_previous_snapshot_skipped",
                    module=logger.name,
                    fields={
                        "publisher_name": publisher_state.publisher_name,
                        "snapshot_drive_file_id": candidate_file_id,
                        "snapshot_drive_file_name": candidate_file_name or "",
                        "snapshot_sha256": resolved_sha256,
                        "code": "publisher_inventory_snapshot_publisher_mismatch",
                        "snapshot_normalized_url": snapshot.normalized_insights_url,
                        "expected_normalized_url": publisher_state.normalized_url,
                    },
                )
            )
            continue
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_previous_snapshot_loaded",
                module=logger.name,
                fields={
                    "publisher_name": publisher_state.publisher_name,
                    "snapshot_drive_file_id": candidate_file_id,
                    "snapshot_drive_file_name": candidate_file_name or "",
                    "snapshot_sha256": resolved_sha256,
                    "item_count": len(snapshot.items),
                },
            )
        )
        return snapshot, candidate_file_id, candidate_file_name, resolved_sha256
    return None, None, None, None


def _snapshot_file_name() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{_SNAPSHOT_PREFIX}{timestamp}.json"


__all__ = [name for name in globals() if not name.startswith("__")]
