"""Shared publish-orchestrator helpers for HTML path normalization and file-id lookup."""

from __future__ import annotations

import logging
from pathlib import Path

from src.contracts.report_store import ReportMetadataListRequest
from src.contracts.run_context import RunContext
from src.services.report_store_service import list_metadata
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publish_shared")


def canonicalize_html_path(path: str) -> str:
    try:
        return str(Path(path).expanduser().resolve())
    except Exception:
        return str(Path(path))


def load_html_file_id_map(reports_db: str, ctx: RunContext) -> dict[str, str]:
    if not reports_db.strip():
        return {}
    response = list_metadata(
        ReportMetadataListRequest(schema_version="1.1", db_path=reports_db),
        ctx,
    )
    mapping: dict[str, str] = {}
    records = sorted(
        response.records,
        key=lambda row: int(getattr(row, "updated_at", 0) or 0),
        reverse=True,
    )
    for row in records:
        html_path = (row.html_path or "").strip()
        file_id = (row.file_id or "").strip()
        if not html_path or not file_id:
            continue
        key = canonicalize_html_path(html_path)
        if key not in mapping:
            mapping[key] = file_id
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publish_file_id_map_loaded",
            module=logger.name,
            fields={
                "reports_db": reports_db,
                "rows": len(response.records),
                "mapped": len(mapping),
            },
        )
    )
    return mapping
