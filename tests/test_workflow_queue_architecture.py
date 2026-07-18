from __future__ import annotations

import inspect
from pathlib import Path

from src.orchestrators.workflow_queue_orchestrator import (
    default_workflow_queue_registry,
)
from src.services.workflow_queue_service import approve_publication_package

CRITICAL_QUEUE_NAMES = {
    "publisher_discovery",
    "report_acquisition",
    "mailbox_delivery",
    "source_ingest",
    "report_selection",
    "report_analysis",
    "report_render",
    "analytics_projection",
    "claim_embedding",
    "signal_candidate",
    "signal_generation",
    "briefing_opportunity",
    "briefing_generation",
    "cover_generation",
    "publication_readiness",
    "wordpress_publish",
    "wordpress_projection",
}


def test_every_critical_queue_has_a_production_handler() -> None:
    registry = default_workflow_queue_registry()

    registrations = {
        queue_name: registration
        for (queue_name, _job_type), registration in registry.items()
        if queue_name in CRITICAL_QUEUE_NAMES
    }

    assert set(registrations) == CRITICAL_QUEUE_NAMES
    assert all(
        registration.handler.__name__ != "_verified_reference_handler"
        for registration in registrations.values()
    )


def test_ui_surfaces_do_not_own_workflow_subprocesses() -> None:
    ui_root = Path("src/ui")
    ui_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in ui_root.rglob("*.py")
        if "__pycache__" not in path.parts
    )

    assert "launch_process(" not in ui_source
    assert "subprocess." not in ui_source
    assert "workflow_queue_submit" in Path("src/ui/run_control.py").read_text(
        encoding="utf-8"
    )


def test_approval_only_schedules_durable_work_and_never_calls_wordpress() -> None:
    source = inspect.getsource(approve_publication_package)

    assert "workflow_outbox" in source
    assert "publish_cross_report_package" not in source
    assert "wordpress_service" not in source
