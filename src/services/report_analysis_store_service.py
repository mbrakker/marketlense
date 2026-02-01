from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from src.contracts.run_context import RunContext
from src.utils.logging import log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.report_analysis_store_service")


def _legacy_base_dir(output_dir: str) -> Path:
    return Path(output_dir) / "report_analysis"


def _report_base_dir(output_dir: str, report_slug: str) -> Path:
    return Path(output_dir) / report_slug / "report_analysis"


def pack_path(output_dir: str, report_id: str, pack_name: str, *, report_slug: Optional[str] = None) -> Path:
    """
    Build the primary path where a pack should be written.
    When report_slug is provided, packs live under the report's folder inside `out/<slug>/report_analysis/`.
    Otherwise we fall back to the legacy layout `out/report_analysis/<file_id>/`.
    """
    if report_slug:
        slug = slugify(report_slug)
        return _report_base_dir(output_dir, slug) / f"{pack_name}.json"
    return _legacy_base_dir(output_dir) / report_id / f"{pack_name}.json"


def store_pack(
    output_dir: str,
    report_id: str,
    pack_name: str,
    payload: dict,
    ctx: RunContext,
    *,
    report_slug: Optional[str] = None,
    mirror_legacy: bool = True,
) -> str:
    logger.info(log_event(
        ctx,
        role="service",
        event="analysis_store_start",
        module=logger.name,
        fields={
            "report_id": report_id,
            "pack_name": pack_name,
            "report_slug": report_slug or "",
            "mirror_legacy": mirror_legacy,
        },
    ))

    primary_path = pack_path(output_dir, report_id, pack_name, report_slug=report_slug)
    primary_path.parent.mkdir(parents=True, exist_ok=True)
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    primary_path.write_text(payload_json, encoding="utf-8")

    legacy_path = None
    if report_slug and mirror_legacy:
        legacy_path = pack_path(output_dir, report_id, pack_name, report_slug=None)
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        if legacy_path != primary_path:
            legacy_path.write_text(payload_json, encoding="utf-8")

    logger.info(log_event(
        ctx,
        role="service",
        event="analysis_store_complete",
        module=logger.name,
        fields={
            "report_id": report_id,
            "pack_name": pack_name,
            "path": str(primary_path),
            "legacy_path": str(legacy_path) if legacy_path else "",
        },
    ))
    return str(primary_path)
