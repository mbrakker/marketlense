"""Queue only proof-complete rehabilitation work after explicit campaign approval."""

from __future__ import annotations

import hashlib

from src.contracts.corpus_rehabilitation import (
    CorpusRehabilitationCampaignItemUpdateRequest,
    CorpusRehabilitationCampaignReadRequest,
    CorpusRehabilitationCampaignResponse,
    CorpusRehabilitationPlanRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.workflow_queue import MaintenancePayload, WorkflowJobSubmission
from src.services.report_store_service import (
    read_corpus_rehabilitation_campaign,
    read_corpus_rehabilitation_plan,
    update_corpus_rehabilitation_campaign_item,
)
from src.services.workflow_queue_service import enqueue_workflow_job
from src.utils.errors import AppError


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def submit_corpus_rehabilitation_campaign(
    *,
    reports_db: str,
    state_db: str,
    campaign_id: str,
    ctx: RunContext,
    limit: int = 10,
) -> CorpusRehabilitationCampaignResponse:
    """Queue a bounded approved batch through the existing maintenance queue.

    The queue handoff is idempotent.  It contains only a retained rendered
    reference and source checksum; the worker's normal controls remain the
    only path to subsequent work.  Incomplete candidates stay operator-held.
    """
    campaign = read_corpus_rehabilitation_campaign(
        CorpusRehabilitationCampaignReadRequest(
            schema_version="1.0", db_path=reports_db, campaign_id=campaign_id
        ),
        ctx,
    )
    if (
        campaign.campaign.status not in {"approved", "submitted"}
        or not campaign.campaign.approval_hash
    ):
        raise AppError(
            code="corpus_rehabilitation_campaign_unapproved",
            message=(
                "Campaign must have a retained operator approval before queue handoff"
            ),
            retryable=False,
        )
    current = {
        item.report_id: item
        for item in read_corpus_rehabilitation_plan(
            CorpusRehabilitationPlanRequest(
                schema_version="1.0", db_path=reports_db, limit=500
            ),
            ctx,
        ).candidates
    }
    submitted = 0
    for item in campaign.items:
        if submitted >= max(1, min(100, limit)):
            break
        if item.status not in {"ready_for_approval", "queued"}:
            continue
        observed = current.get(item.report_id)
        if observed is None or (
            observed.disposition != item.disposition
            or observed.source_checksum != item.source_checksum
            or observed.retained_reference != item.retained_reference
            or observed.reusable_artifact_ids != item.reusable_artifact_ids
        ):
            update_corpus_rehabilitation_campaign_item(
                CorpusRehabilitationCampaignItemUpdateRequest(
                    schema_version="1.0",
                    db_path=reports_db,
                    campaign_id=campaign_id,
                    report_id=item.report_id,
                    status="operator_held",
                ),
                ctx,
            )
            continue
        if not (
            item.disposition == "recompute"
            and item.source_checksum
            and item.retained_reference
            and item.reusable_artifact_ids
        ):
            update_corpus_rehabilitation_campaign_item(
                CorpusRehabilitationCampaignItemUpdateRequest(
                    schema_version="1.0",
                    db_path=reports_db,
                    campaign_id=campaign_id,
                    report_id=item.report_id,
                    status="operator_held",
                ),
                ctx,
            )
            continue
        job, _created = enqueue_workflow_job(
            state_db,
            WorkflowJobSubmission(
                schema_version="1.0",
                queue_name="artifact_repair",
                job_type="artifact_repair.v1",
                payload=MaintenancePayload(
                    subject_id=item.report_id,
                    maintenance_policy_version="corpus-rehabilitation.v1",
                    input_reference=item.retained_reference,
                    input_content_hash=item.source_checksum,
                    processing_version="corpus-rehabilitation.v1",
                    attributes={
                        "campaign_id": campaign_id,
                        "campaign_plan_hash": campaign.campaign.plan_hash,
                        "reusable_artifact_ids": item.reusable_artifact_ids,
                    },
                ),
                idempotency_key=_digest(
                    "corpus-rehabilitation",
                    campaign_id,
                    item.report_id,
                    item.source_checksum,
                    campaign.campaign.plan_hash,
                ),
                deduplication_scope="corpus-rehabilitation-campaign",
                root_workflow_id=campaign_id,
                trigger_event_id=f"campaign:{campaign_id}",
                correlation_id=campaign_id,
                entity_type="report",
                entity_id=item.report_id,
                report_id=item.report_id,
                budget_profile="maintenance",
                execution_plan_hash=campaign.campaign.plan_hash,
            ),
            ctx,
        )
        update_corpus_rehabilitation_campaign_item(
            CorpusRehabilitationCampaignItemUpdateRequest(
                schema_version="1.0",
                db_path=reports_db,
                campaign_id=campaign_id,
                report_id=item.report_id,
                status="queued",
                queue_job_id=job.job_id,
                actual_provider_calls=0,
                actual_cost_usd=0.0,
            ),
            ctx,
        )
        submitted += 1
    return read_corpus_rehabilitation_campaign(
        CorpusRehabilitationCampaignReadRequest(
            schema_version="1.0", db_path=reports_db, campaign_id=campaign_id
        ),
        ctx,
    )
