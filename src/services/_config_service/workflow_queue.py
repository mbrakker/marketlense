"""Configuration defaults for the single typed workflow-queue platform."""

from __future__ import annotations

from src.contracts.config import ConfigLoadRequest
from src.contracts.run_context import RunContext
from src.contracts.workflow_queue import WORKFLOW_QUEUE_NAMES, WorkflowQueuePolicy
from src.services._config_service.common import (
    _load_config,
    _resolve_bootstrap_config_path,
    _to_bool,
    _to_int,
)
from src.utils.errors import AppError

_CONSERVATIVE_DEFAULTS: dict[str, tuple[int, int, int, int, int, str]] = {
    "publisher_discovery": (1, 3, 900, 200, 100, "publisher_inventory"),
    "report_acquisition": (2, 3, 1200, 500, 5, "browser_acquisition"),
    "mailbox_delivery": (1, 3, 900, 100, 3, "mailbox_delivery"),
    "source_ingest": (1, 3, 1800, 300, 3, "report_ingest"),
    "report_selection": (1, 3, 1800, 150, 2, "report_ingest"),
    "report_analysis": (1, 2, 3600, 100, 5, "high_quality"),
    "report_render": (1, 3, 1200, 150, 5, "report_render"),
    "analytics_projection": (1, 3, 900, 200, 5, "analytics_projection"),
    "claim_embedding": (1, 3, 900, 500, 50, "embedding"),
    "signal_candidate": (1, 3, 900, 100, 10, "signal_candidate"),
    "signal_generation": (1, 2, 3600, 50, 5, "high_quality"),
    "briefing_opportunity": (1, 3, 600, 300, 1, "briefing_opportunity"),
    "briefing_generation": (1, 2, 3600, 25, 5, "cross_report_analysis"),
    "cover_generation": (1, 3, 1200, 100, 5, "cover_generation"),
    "publication_readiness": (1, 3, 600, 200, 2, "publishing"),
    "wordpress_publish": (1, 3, 900, 100, 10, "publishing"),
    "wordpress_projection": (1, 3, 900, 200, 5, "wordpress_projection"),
}


def default_workflow_queue_policies() -> dict[str, WorkflowQueuePolicy]:
    policies: dict[str, WorkflowQueuePolicy] = {}
    for queue_name in WORKFLOW_QUEUE_NAMES:
        workers, attempts, lease, pending, fanout, budget = _CONSERVATIVE_DEFAULTS.get(
            queue_name, (1, 3, 900, 100, 5, "maintenance")
        )
        policies[queue_name] = WorkflowQueuePolicy(
            queue_name=queue_name,
            max_workers=workers,
            max_attempts=attempts,
            lease_seconds=lease,
            maximum_pending=pending,
            maximum_fanout=fanout,
            budget_profile=budget,
        )
    return policies


def load_workflow_queue_policies(
    request: ConfigLoadRequest,
    ctx: RunContext,
) -> dict[str, WorkflowQueuePolicy]:
    """Load and validate defaults; durable controls remain operator-owned."""
    del ctx  # Config parsing is deterministic and has no queue side effect.
    data = _load_config(str(_resolve_bootstrap_config_path(request.path)))
    raw = data.get("workflow_queues", {}) or {}
    if not isinstance(raw, dict):
        raise AppError(
            code="workflow_queue_config_invalid",
            message="workflow_queues must be a mapping",
            retryable=False,
        )
    policies = default_workflow_queue_policies()
    unknown = sorted(set(raw) - set(WORKFLOW_QUEUE_NAMES))
    if unknown:
        raise AppError(
            code="workflow_queue_config_invalid",
            message="workflow_queues contains an unregistered logical queue",
            retryable=False,
            context={"unknown_queues": unknown},
        )
    for queue_name, defaults in policies.items():
        item = raw.get(queue_name, {})
        if not isinstance(item, dict):
            raise AppError(
                code="workflow_queue_config_invalid",
                message="Workflow queue configuration must be a mapping",
                retryable=False,
                context={"queue_name": queue_name},
            )
        policy = WorkflowQueuePolicy(
            schema_version=str(item.get("schema_version") or defaults.schema_version),
            queue_name=queue_name,
            enabled=_to_bool(item.get("enabled"), defaults.enabled),
            max_workers=max(1, _to_int(item.get("max_workers"), defaults.max_workers)),
            max_attempts=max(
                1, _to_int(item.get("max_attempts"), defaults.max_attempts)
            ),
            lease_seconds=max(
                1, _to_int(item.get("lease_seconds"), defaults.lease_seconds)
            ),
            maximum_pending=max(
                1, _to_int(item.get("maximum_pending"), defaults.maximum_pending)
            ),
            maximum_fanout=max(
                1, _to_int(item.get("maximum_fanout"), defaults.maximum_fanout)
            ),
            budget_profile=str(item.get("budget_profile") or defaults.budget_profile),
            retry_delay_seconds=max(
                1,
                _to_int(item.get("retry_delay_seconds"), defaults.retry_delay_seconds),
            ),
        )
        if not policy.budget_profile.strip():
            raise AppError(
                code="workflow_queue_config_invalid",
                message="Workflow queue budget profile is required",
                retryable=False,
                context={"queue_name": queue_name},
            )
        policies[queue_name] = policy
    return policies
