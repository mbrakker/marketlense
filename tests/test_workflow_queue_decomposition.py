from __future__ import annotations

from pathlib import Path

from src.orchestrators.workflow_queue_orchestrator import (
    default_workflow_queue_registry,
)
from src.services.workflow_queue_service import (
    approve_publication_package,
    claim_next_workflow_job,
    complete_workflow_job,
    enqueue_workflow_job,
    materialize_workflow_outbox,
)


def test_queue_facades_remain_small_and_public_imports_remain_available() -> None:
    assert callable(enqueue_workflow_job)
    assert callable(claim_next_workflow_job)
    assert callable(complete_workflow_job)
    assert callable(materialize_workflow_outbox)
    assert callable(approve_publication_package)
    assert (
        len(Path("src/services/workflow_queue_service.py").read_text().splitlines())
        < 100
    )
    assert (
        len(
            Path("src/orchestrators/workflow_queue_orchestrator.py")
            .read_text()
            .splitlines()
        )
        < 100
    )


def test_fixed_queue_registration_and_allowed_downstream_sets_are_unchanged() -> None:
    registry = default_workflow_queue_registry()
    expected = {
        "publisher_discovery": ("report_acquisition.v1",),
        "report_acquisition": ("mailbox_delivery.v1", "source_ingest.v1"),
        "mailbox_delivery": ("source_ingest.v1",),
        "source_ingest": ("report_selection.v1",),
        "report_selection": ("report_analysis.v1",),
        "report_analysis": ("artifact_repair.v1", "report_render.v1"),
        "report_render": (
            "analytics_projection.v1",
            "cover_generation.v1",
            "publication_readiness.v1",
        ),
        "analytics_projection": (
            "claim_embedding.v1",
            "signal_candidate.v1",
            "briefing_opportunity.v1",
        ),
        "claim_embedding": (),
        "signal_candidate": ("signal_generation.v1",),
        "signal_generation": ("cover_generation.v1",),
        "briefing_opportunity": ("briefing_generation.v1",),
        "briefing_generation": ("cover_generation.v1",),
        "cover_generation": ("publication_readiness.v1",),
        "publication_readiness": ("wordpress_publish.v1",),
        "wordpress_publish": ("wordpress_projection.v1",),
        "wordpress_projection": (),
        "artifact_repair": ("report_analysis.v1",),
        "source_revalidation": ("report_acquisition.v1",),
        "malformed_pdf_revalidation": ("source_ingest.v1",),
        "recategorization": ("analytics_projection.v1",),
        "vector_retention": (),
        "wordpress_category_update": (),
        "public_render_repair": ("report_render.v1",),
        "cost_reconciliation": (),
        "release_evidence_generation": (),
    }
    assert tuple(item[0] for item in registry) == tuple(expected)
    assert {
        queue_name: registration.allowed_downstream_job_types
        for (queue_name, _job_type), registration in registry.items()
    } == expected
