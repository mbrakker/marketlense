from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from src.contracts.config import AppSettings
from src.contracts.run_context import RunContext
from src.contracts.state import StateCheckRequest, StateRecordRequest
from src.generators.evidence_pack_generator import generate_evidence_packs
from src.services import state_service, vector_store_service
from src.utils.logging import child_context, log_event, new_run_context

logger = logging.getLogger("market_lense.golden_set_orchestrator")


def _sha256_bytes(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _md5_bytes(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def run_golden_set_vector(
    settings: AppSettings,
    fixtures_dir: str,
    *,
    limit: Optional[int] = None,
    ctx: Optional[RunContext] = None,
) -> List[Dict[str, str]]:
    ctx = ctx or new_run_context(task_id="golden_set_vector")
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="golden_set_vector_start",
        module=logger.name,
        fields={"fixtures_dir": fixtures_dir, "limit": limit},
    ))
    paths = sorted(Path(fixtures_dir).glob("*.pdf"))
    outcomes: List[Dict[str, str]] = []
    max_n = limit if limit is not None else len(paths)
    processed = 0
    for path in paths:
        if processed >= max_n:
            break
        report_id = _sha256_bytes(path)
        md5 = _md5_bytes(path)
        file_ctx = child_context(ctx, task_id=report_id)
        if state_service.already_processed(
            StateCheckRequest(schema_version="1.0", state_db=settings.state_db, file_id=report_id, md5=md5),
            file_ctx,
        ):
            logger.info(log_event(
                file_ctx,
                role="orchestrator",
                event="golden_set_vector_skip",
                module=logger.name,
                fields={"report_id": report_id, "reason": "already_processed"},
            ))
            continue
        try:
            vs_resp = vector_store_service.create_vector_store(report_id, {"report_id": report_id}, file_ctx)
            upload_resp = vector_store_service.upload_file(str(path), file_ctx)
            vector_store_service.attach_file(vs_resp.vector_store_id, upload_resp.openai_file_id, file_ctx)
            status_resp = vector_store_service.wait_until_indexed(vs_resp.vector_store_id, ctx=file_ctx, timeout_s=600, poll_interval_s=5)
            packs = generate_evidence_packs(
                report_id=report_id,
                vector_store_id=vs_resp.vector_store_id,
                settings=settings,
                ctx=file_ctx,
            )
            _write_golden_outputs(settings.output_dir, report_id, packs, file_ctx)
            state_service.record(
                StateRecordRequest(
                    schema_version="1.0",
                    state_db=settings.state_db,
                    file_id=report_id,
                    md5=md5,
                    openai_file_id=upload_resp.openai_file_id,
                    vector_store_id=vs_resp.vector_store_id,
                    vector_store_status=status_resp.status,
                    indexed_at_utc=status_resp.indexed_at_utc,
                    last_error=status_resp.last_error,
                ),
                file_ctx,
            )
            outcomes.append({
                "report_id": report_id,
                "vector_store_id": vs_resp.vector_store_id,
                "status": status_resp.status,
            })
            processed += 1
        except Exception as exc:
            logger.info(log_event(
                file_ctx,
                role="orchestrator",
                event="golden_set_vector_error",
                module=logger.name,
                fields={"report_id": report_id, "error": str(exc)},
            ))
            continue

    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="golden_set_vector_complete",
        module=logger.name,
        fields={"processed": processed},
    ))
    return outcomes


def _write_golden_outputs(output_dir: str, report_id: str, packs: Dict[str, dict], ctx: RunContext) -> None:
    base = Path(output_dir) / "golden_set" / report_id / "packs"
    base.mkdir(parents=True, exist_ok=True)
    for name, payload in packs.items():
        path = base / f"{name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(log_event(
            ctx,
            role="orchestrator",
            event="golden_set_pack_written",
            module=logger.name,
            fields={"report_id": report_id, "pack": name, "path": str(path)},
        ))
