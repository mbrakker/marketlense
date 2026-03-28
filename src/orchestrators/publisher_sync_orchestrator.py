from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from src.contracts.publisher_profiles import (
    PublisherProfilesSnapshotLoadRequest,
    PublisherProfilesSnapshotLoadResponse,
    PublisherSyncRequest,
    PublisherSyncResponse,
)
from src.contracts.report_store import (
    PublishersReplaceRequest,
    PublishersReplaceResponse,
)
from src.contracts.run_context import RunContext
from src.generators.publisher_profiles_generator import (
    load_publisher_profiles_snapshot,
)
from src.services.report_store_service import replace_publishers
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_sync_orchestrator")


@dataclass(frozen=True)
class PublisherSyncDependencies:
    load_publisher_profiles_snapshot: Callable[
        [PublisherProfilesSnapshotLoadRequest, RunContext],
        PublisherProfilesSnapshotLoadResponse,
    ]
    replace_publishers: Callable[
        [PublishersReplaceRequest, RunContext],
        PublishersReplaceResponse,
    ]

    @classmethod
    def default(cls) -> "PublisherSyncDependencies":
        return cls(
            load_publisher_profiles_snapshot=load_publisher_profiles_snapshot,
            replace_publishers=replace_publishers,
        )


def run_publisher_sync(
    request: PublisherSyncRequest,
    *,
    ctx: RunContext,
    dependencies: PublisherSyncDependencies | None = None,
) -> PublisherSyncResponse:
    deps = dependencies or PublisherSyncDependencies.default()
    snapshot_path = request.snapshot_path.strip()
    reports_db = request.reports_db.strip()
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_sync_start",
            module=logger.name,
            fields={
                "snapshot_path": snapshot_path,
                "reports_db": reports_db,
            },
        )
    )
    snapshot = deps.load_publisher_profiles_snapshot(
        PublisherProfilesSnapshotLoadRequest(
            schema_version="1.0",
            snapshot_path=snapshot_path,
        ),
        ctx,
    )
    replace_response = deps.replace_publishers(
        PublishersReplaceRequest(
            schema_version="1.0",
            db_path=reports_db,
            source_page_url=snapshot.source_page_url,
            publishers=snapshot.publishers,
        ),
        ctx,
    )
    response = PublisherSyncResponse(
        schema_version="1.0",
        snapshot_path=snapshot.snapshot_path,
        reports_db=replace_response.db_path,
        source_page_url=replace_response.source_page_url,
        replaced_count=replace_response.replaced_count,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_sync_complete",
            module=logger.name,
            fields={
                "snapshot_path": response.snapshot_path,
                "reports_db": response.reports_db,
                "source_page_url": response.source_page_url,
                "replaced_count": response.replaced_count,
            },
        )
    )
    return response
