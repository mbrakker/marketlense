"""Stable public facade for the fixed typed workflow queue graph."""

from __future__ import annotations

from src.contracts.workflow_queue import WorkflowStageResult
from src.orchestrators._workflow_queue_handlers.acquisition import (
    _mailbox_delivery_handler,
    _report_acquisition_handler,
)
from src.orchestrators._workflow_queue_handlers.analytics import (
    _claim_embedding_handler,
)
from src.orchestrators._workflow_queue_handlers.briefings import (
    _briefing_opportunity_handler,
)
from src.orchestrators._workflow_queue_handlers.publishing import (
    _cover_generation_handler,
    _cross_report_package_from_artifact,
    _package_checksum,
    _persist_queue_publish_package,
    _publication_readiness_handler,
    _wordpress_projection_handler,
    _wordpress_publish_handler,
)
from src.orchestrators._workflow_queue_handlers.registry import (
    default_workflow_queue_registry,
    execute_workflow_queue_handler,
    resolve_workflow_queue_handler,
)
from src.orchestrators._workflow_queue_handlers.report_pipeline import (
    _report_stage_handler,
    _stage_child_submission,
)
from src.orchestrators._workflow_queue_handlers.shared import (
    WorkflowQueueHandlerRegistration,
    WorkflowQueueHandlerResult,
    _boolean_attribute,
    _positive_float_attribute,
    _positive_int_attribute,
    _requested_budget_override,
    _string_list_attribute,
    _verified_reference_handler,
)
from src.orchestrators._workflow_queue_handlers.signals import (
    _signal_candidate_handler,
    _signal_generation_handler,
    _signal_publish_package,
)

__all__ = [
    "WorkflowQueueHandlerRegistration",
    "WorkflowQueueHandlerResult",
    "WorkflowStageResult",
    "_boolean_attribute",
    "_briefing_opportunity_handler",
    "_claim_embedding_handler",
    "_cover_generation_handler",
    "_cross_report_package_from_artifact",
    "_mailbox_delivery_handler",
    "_package_checksum",
    "_persist_queue_publish_package",
    "_positive_float_attribute",
    "_positive_int_attribute",
    "_publication_readiness_handler",
    "_report_acquisition_handler",
    "_report_stage_handler",
    "_requested_budget_override",
    "_signal_candidate_handler",
    "_signal_generation_handler",
    "_signal_publish_package",
    "_stage_child_submission",
    "_string_list_attribute",
    "_verified_reference_handler",
    "_wordpress_projection_handler",
    "_wordpress_publish_handler",
    "default_workflow_queue_registry",
    "execute_workflow_queue_handler",
    "resolve_workflow_queue_handler",
]
