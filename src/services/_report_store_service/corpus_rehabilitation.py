"""Read-only retained-corpus rehabilitation classification service."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.contracts.corpus_rehabilitation import (
    CorpusRehabilitationCampaign,
    CorpusRehabilitationCampaignApprovalRequest,
    CorpusRehabilitationCampaignCreateRequest,
    CorpusRehabilitationCampaignItem,
    CorpusRehabilitationCampaignItemUpdateRequest,
    CorpusRehabilitationCampaignReadRequest,
    CorpusRehabilitationCampaignResponse,
    CorpusRehabilitationCandidate,
    CorpusRehabilitationPlanRequest,
    CorpusRehabilitationPlanResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

from .common import logger
from .connection import _metadata_conn


def read_corpus_rehabilitation_plan(
    request: CorpusRehabilitationPlanRequest,
    ctx: RunContext,
) -> CorpusRehabilitationPlanResponse:
    """Classify retained reports without source re-ingestion or provider calls."""
    if request.schema_version != "1.0" or not str(request.db_path).strip():
        raise AppError(
            code="corpus_rehabilitation_request_invalid",
            message="Corpus rehabilitation requires a reports database path",
            retryable=False,
        )
    path = Path(request.db_path)
    if not path.exists():
        return CorpusRehabilitationPlanResponse(schema_version="1.0")
    try:
        database_uri = f"file:{path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(database_uri, uri=True) as conn:
            reports_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reports'"
            ).fetchone()
            if reports_exists is None:
                return CorpusRehabilitationPlanResponse(schema_version="1.0")
            lineage_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='artifact_lineage_records'"
            ).fetchone()
            rows = conn.execute(
                "SELECT file_id, html_path, validation_status, text_not_available, "
                "md5, source_url, projection_status FROM reports "
                "ORDER BY file_id LIMIT ?",
                (max(1, min(500, int(request.limit))),),
            ).fetchall()
            reusable_artifacts = _read_reusable_artifacts(
                conn, lineage_exists is not None
            )
    except sqlite3.Error as exc:
        raise AppError(
            code="corpus_rehabilitation_read_failed",
            message=(
                "Corpus rehabilitation plan could not read retained report metadata"
            ),
            cause=exc,
            retryable=False,
        ) from exc
    candidates = [
        _classify(row, reusable_artifacts.get(str(row[0]), [])) for row in rows
    ]
    counts = dict(sorted(Counter(item.classification for item in candidates).items()))
    response = CorpusRehabilitationPlanResponse(
        schema_version="1.0", candidates=candidates, classification_counts=counts
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="corpus_rehabilitation_plan_read",
            module=logger.name,
            fields={
                "candidate_count": len(candidates),
                "classification_counts": counts,
                "provider_calls": 0,
                "source_reingestion": False,
            },
        )
    )
    return response


def _read_reusable_artifacts(conn, lineage_exists: bool) -> dict[str, list[str]]:
    if not lineage_exists:
        return {}
    columns = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(artifact_lineage_records)")
    }
    if "artifact_id" not in columns:
        return {}
    rows = conn.execute(
        "SELECT report_id, artifact_id FROM artifact_lineage_records "
        "ORDER BY report_id, artifact_id"
    ).fetchall()
    grouped: dict[str, list[str]] = {}
    for report_id, artifact_id in rows:
        grouped.setdefault(str(report_id), []).append(str(artifact_id))
    return grouped


def _classify(row: tuple[object, ...], reusable_artifact_ids: list[str]):
    (
        report_id,
        html_path,
        validation_status,
        text_unavailable,
        md5,
        source_url,
        projection,
    ) = (
        str(row[0]),
        str(row[1] or ""),
        str(row[2] or "").lower(),
        bool(row[3]),
        str(row[4] or ""),
        str(row[5] or ""),
        str(row[6] or "").lower(),
    )
    reusable_artifact_count = len(reusable_artifact_ids)
    if not md5 or not source_url:
        classification, disposition, reason = (
            "source_provenance_incomplete",
            "content_review",
            "source_provenance_missing",
        )
    elif not html_path:
        classification, disposition, reason = (
            "missing_rendered_report",
            "repair",
            "rendered_html_missing",
        )
    elif validation_status in {"fail", "failed", "error"}:
        classification, disposition, reason = (
            "validation_failed",
            "repair",
            "retained_validation_failed",
        )
    elif text_unavailable:
        classification, disposition, reason = (
            "source_text_unavailable",
            "content_review",
            "retained_source_text_unavailable",
        )
    elif projection == "failed":
        classification, disposition, reason = (
            "projection_failed",
            "repair",
            "analytics_projection_failed",
        )
    elif reusable_artifact_count:
        classification, disposition, reason = (
            "validated_artifacts_reusable",
            "recompute",
            "rebuild_from_validated_artifacts",
        )
    else:
        classification, disposition, reason = (
            "lineage_incomplete",
            "abstain",
            "validated_artifact_lineage_missing",
        )
    return CorpusRehabilitationCandidate(
        schema_version="1.0",
        report_id=report_id,
        classification=classification,
        disposition=disposition,
        reason=reason,
        reusable_artifact_count=reusable_artifact_count,
        estimated_provider_calls=None,
        estimated_cost_usd=None,
        estimate_status="unavailable",
        source_checksum=md5,
        retained_reference=html_path if reusable_artifact_count else "",
        reusable_artifact_ids=reusable_artifact_ids,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _campaign_hash(
    candidates: list[CorpusRehabilitationCandidate], batch_size: int
) -> str:
    payload = [
        {
            "report_id": item.report_id,
            "classification": item.classification,
            "disposition": item.disposition,
            "source_checksum": item.source_checksum,
            "retained_reference": item.retained_reference,
            "reusable_artifact_ids": item.reusable_artifact_ids,
        }
        for item in candidates
    ]
    return hashlib.sha256(
        json.dumps(
            {"schema_version": "1.0", "batch_size": batch_size, "candidates": payload},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _campaign_from_row(row: sqlite3.Row) -> CorpusRehabilitationCampaign:
    return CorpusRehabilitationCampaign(
        campaign_id=str(row["campaign_id"]),
        plan_hash=str(row["plan_hash"]),
        approval_hash=str(row["approval_hash"]),
        status=str(row["status"]),
        batch_size=int(row["batch_size"]),
        planned_provider_calls=int(row["planned_provider_calls"]),
        actual_provider_calls=int(row["actual_provider_calls"]),
        planned_cost_usd=row["planned_cost_usd"],
        actual_cost_usd=row["actual_cost_usd"],
        created_at_utc=str(row["created_at_utc"]),
        approved_at_utc=str(row["approved_at_utc"]),
        submitted_at_utc=str(row["submitted_at_utc"]),
    )


def _campaign_items(
    conn: sqlite3.Connection, campaign_id: str
) -> list[CorpusRehabilitationCampaignItem]:
    rows = conn.execute(
        "SELECT campaign_id, report_id, classification, disposition, source_checksum, "
        "retained_reference, reusable_artifact_ids_json, status, reason, queue_job_id "
        "FROM corpus_rehabilitation_campaign_items "
        "WHERE campaign_id=? ORDER BY report_id",
        (campaign_id,),
    ).fetchall()
    return [
        CorpusRehabilitationCampaignItem(
            campaign_id=str(row["campaign_id"]),
            report_id=str(row["report_id"]),
            classification=str(row["classification"]),
            disposition=str(row["disposition"]),
            source_checksum=str(row["source_checksum"]),
            retained_reference=str(row["retained_reference"]),
            reusable_artifact_ids=list(
                json.loads(str(row["reusable_artifact_ids_json"]))
            ),
            status=str(row["status"]),
            reason=str(row["reason"]),
            queue_job_id=str(row["queue_job_id"]),
        )
        for row in rows
    ]


def create_corpus_rehabilitation_campaign(
    request: CorpusRehabilitationCampaignCreateRequest, ctx: RunContext
) -> CorpusRehabilitationCampaignResponse:
    """Persist an operator-selected campaign; no queue or provider I/O occurs."""
    plan = read_corpus_rehabilitation_plan(
        CorpusRehabilitationPlanRequest(
            schema_version="1.0", db_path=request.db_path, limit=500
        ),
        ctx,
    )
    selected = set(request.report_ids)
    candidates = [
        item for item in plan.candidates if not selected or item.report_id in selected
    ]
    if not candidates:
        raise AppError(
            code="corpus_rehabilitation_campaign_empty",
            message="Campaign selection has no retained reports",
            retryable=False,
        )
    batch_size = max(1, min(100, int(request.batch_size)))
    plan_hash = _campaign_hash(candidates, batch_size)
    campaign_id = f"corpus_rehab_{plan_hash[:24]}"
    now = _utc_now()
    with _metadata_conn(request.db_path, ctx) as conn:
        existing = conn.execute(
            "SELECT * FROM corpus_rehabilitation_campaigns WHERE campaign_id=?",
            (campaign_id,),
        ).fetchone()
        created = existing is None
        if existing is None:
            conn.execute(
                "INSERT INTO corpus_rehabilitation_campaigns("
                "campaign_id,plan_hash,approval_hash,status,batch_size,"
                "planned_provider_calls,actual_provider_calls,planned_cost_usd,"
                "actual_cost_usd,created_at_utc,approved_at_utc,submitted_at_utc,"
                "created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    campaign_id,
                    plan_hash,
                    "",
                    "planned",
                    batch_size,
                    0,
                    0,
                    None,
                    None,
                    now,
                    "",
                    "",
                    request.created_by.strip() or "operator",
                ),
            )
            for item in candidates:
                status = (
                    "ready_for_approval"
                    if (
                        item.disposition == "recompute"
                        and item.source_checksum
                        and item.retained_reference
                        and item.reusable_artifact_ids
                    )
                    else "operator_held"
                )
                reason = (
                    "validated_reuse_queueable"
                    if status == "ready_for_approval"
                    else item.reason
                )
                conn.execute(
                    "INSERT INTO corpus_rehabilitation_campaign_items("
                    "campaign_id,report_id,classification,disposition,source_checksum,"
                    "retained_reference,reusable_artifact_ids_json,status,reason,"
                    "queue_job_id,actual_provider_calls,actual_cost_usd) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        campaign_id,
                        item.report_id,
                        item.classification,
                        item.disposition,
                        item.source_checksum,
                        item.retained_reference,
                        json.dumps(item.reusable_artifact_ids, separators=(",", ":")),
                        status,
                        reason,
                        "",
                        0,
                        None,
                    ),
                )
            existing = conn.execute(
                "SELECT * FROM corpus_rehabilitation_campaigns WHERE campaign_id=?",
                (campaign_id,),
            ).fetchone()
        assert existing is not None
        return CorpusRehabilitationCampaignResponse(
            campaign=_campaign_from_row(existing),
            items=_campaign_items(conn, campaign_id),
            created=created,
        )


def approve_corpus_rehabilitation_campaign(
    request: CorpusRehabilitationCampaignApprovalRequest, ctx: RunContext
) -> CorpusRehabilitationCampaignResponse:
    """Record immutable operator approval before any queue handoff."""
    if not request.approved_by.strip() or not request.reason.strip():
        raise AppError(
            code="corpus_rehabilitation_approval_invalid",
            message="Campaign approval requires an operator and reason",
            retryable=False,
        )
    now = _utc_now()
    with _metadata_conn(request.db_path, ctx) as conn:
        row = conn.execute(
            "SELECT * FROM corpus_rehabilitation_campaigns WHERE campaign_id=?",
            (request.campaign_id,),
        ).fetchone()
        if row is None:
            raise AppError(
                code="corpus_rehabilitation_campaign_missing",
                message="Campaign was not found",
                retryable=False,
            )
        campaign = _campaign_from_row(row)
        approval_hash = hashlib.sha256(
            f"{campaign.plan_hash}\x1f{request.approved_by}\x1f{request.reason}".encode(
                "utf-8"
            )
        ).hexdigest()
        if campaign.status == "planned":
            conn.execute(
                "UPDATE corpus_rehabilitation_campaigns SET approval_hash=?, "
                "status='approved', approved_at_utc=? WHERE campaign_id=?",
                (approval_hash, now, request.campaign_id),
            )
        refreshed = conn.execute(
            "SELECT * FROM corpus_rehabilitation_campaigns WHERE campaign_id=?",
            (request.campaign_id,),
        ).fetchone()
        assert refreshed is not None
        return CorpusRehabilitationCampaignResponse(
            campaign=_campaign_from_row(refreshed),
            items=_campaign_items(conn, request.campaign_id),
        )


def read_corpus_rehabilitation_campaign(
    request: CorpusRehabilitationCampaignReadRequest, ctx: RunContext
) -> CorpusRehabilitationCampaignResponse:
    with _metadata_conn(request.db_path, ctx) as conn:
        row = conn.execute(
            "SELECT * FROM corpus_rehabilitation_campaigns WHERE campaign_id=?",
            (request.campaign_id,),
        ).fetchone()
        if row is None:
            raise AppError(
                code="corpus_rehabilitation_campaign_missing",
                message="Campaign was not found",
                retryable=False,
            )
        return CorpusRehabilitationCampaignResponse(
            campaign=_campaign_from_row(row),
            items=_campaign_items(conn, request.campaign_id),
        )


def update_corpus_rehabilitation_campaign_item(
    request: CorpusRehabilitationCampaignItemUpdateRequest, ctx: RunContext
) -> None:
    if request.status not in {"queued", "completed", "operator_held"}:
        raise AppError(
            code="corpus_rehabilitation_item_status_invalid",
            message="Campaign item status is invalid",
            retryable=False,
        )
    with _metadata_conn(request.db_path, ctx) as conn:
        cursor = conn.execute(
            "UPDATE corpus_rehabilitation_campaign_items SET status=?, "
            "queue_job_id=?, actual_provider_calls=?, actual_cost_usd=? "
            "WHERE campaign_id=? AND report_id=?",
            (
                request.status,
                request.queue_job_id,
                max(0, int(request.actual_provider_calls)),
                request.actual_cost_usd,
                request.campaign_id,
                request.report_id,
            ),
        )
        if cursor.rowcount != 1:
            raise AppError(
                code="corpus_rehabilitation_campaign_item_missing",
                message="Campaign item was not found",
                retryable=False,
            )
        conn.execute(
            "UPDATE corpus_rehabilitation_campaigns SET status='submitted', "
            "submitted_at_utc=CASE WHEN submitted_at_utc='' THEN ? "
            "ELSE submitted_at_utc END, actual_provider_calls=(SELECT "
            "COALESCE(SUM(actual_provider_calls),0) FROM "
            "corpus_rehabilitation_campaign_items WHERE campaign_id=?), "
            "actual_cost_usd=(SELECT SUM(actual_cost_usd) FROM "
            "corpus_rehabilitation_campaign_items WHERE campaign_id=?) "
            "WHERE campaign_id=?",
            (_utc_now(), request.campaign_id, request.campaign_id, request.campaign_id),
        )
