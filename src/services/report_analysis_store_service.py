from __future__ import annotations

import json
import logging
from pathlib import Path

from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.report_analysis_store_service")


def _base_dir(output_dir: str) -> Path:
    return Path(output_dir) / "report_analysis"


def store_pack(output_dir: str, report_id: str, pack_name: str, payload: dict, ctx: RunContext) -> str:
    logger.info(log_event(
        ctx,
        role="service",
        event="analysis_store_start",
        module=logger.name,
        fields={"report_id": report_id, "pack_name": pack_name},
    ))
    base = _base_dir(output_dir)
    base.mkdir(parents=True, exist_ok=True)
    report_dir = base / report_id
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{pack_name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(log_event(
        ctx,
        role="service",
        event="analysis_store_complete",
        module=logger.name,
        fields={"report_id": report_id, "pack_name": pack_name, "path": str(path)},
    ))
    return str(path)
