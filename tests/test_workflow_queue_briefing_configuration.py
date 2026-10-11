from __future__ import annotations

from dataclasses import replace

from src.contracts.workflow_queue import (
    BriefingGenerationPayload,
    WorkflowJobSubmission,
)
from src.services.workflow_queue_service import (
    freeze_briefing_opportunity,
    materialize_workflow_outbox,
    upsert_briefing_opportunity,
)
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="workflow-queue-briefing-test")


def test_frozen_briefing_allows_a_new_generation_configuration_once(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    opportunity = upsert_briefing_opportunity(
        db,
        topic="retail",
        geography="EU",
        rolling_window="30d",
        briefing_policy_version="v1",
        source_hashes=["a", "b"],
        publisher_ids=["publisher-a", "publisher-b"],
        minimum_distinct_reports=2,
        minimum_publisher_diversity=2,
        ctx=_ctx(),
    )
    generation = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="briefing_generation",
        job_type="briefing_generation.v1",
        payload=BriefingGenerationPayload(
            opportunity_id=opportunity.opportunity_id,
            frozen_source_manifest="manifest:retail:30d",
            selected_topic="retail",
            sorted_source_hashes=["a", "b"],
            generation_configuration_hash="prompt-cap-12000",
            input_reference="manifest:retail:30d",
            input_content_hash="manifest-hash",
        ),
        idempotency_key="briefing:retail:a:b:prompt-cap-12000",
        deduplication_scope="briefing_generation",
    )
    freeze_briefing_opportunity(
        db,
        opportunity_id=opportunity.opportunity_id,
        frozen_source_manifest="manifest:retail:30d",
        generation_submission=generation,
        ctx=_ctx(),
    )
    lifted = replace(
        generation,
        idempotency_key="briefing:retail:a:b:prompt-cap-30000",
        payload=replace(
            generation.payload,
            generation_configuration_hash="prompt-cap-30000",
        ),
    )
    repeat = freeze_briefing_opportunity(
        db,
        opportunity_id=opportunity.opportunity_id,
        frozen_source_manifest="manifest:retail:30d",
        generation_submission=lifted,
        ctx=_ctx(),
    )

    materialised = materialize_workflow_outbox(db, "outbox-worker", _ctx())
    persisted = upsert_briefing_opportunity(
        db,
        topic="retail",
        geography="EU",
        rolling_window="30d",
        briefing_policy_version="v1",
        source_hashes=["a", "b"],
        publisher_ids=["publisher-a", "publisher-b"],
        minimum_distinct_reports=2,
        minimum_publisher_diversity=2,
        ctx=_ctx(),
    )

    assert repeat.status == "frozen"
    assert len(materialised) == 2
    assert persisted.generation_job_id in materialised
