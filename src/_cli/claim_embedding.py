from __future__ import annotations

"""Explicit, bounded operator commands for the claim-embedding queue."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import typer
from rich import box
from rich.table import Table

from src._cli.app import cli_app, console
from src.contracts.analytics_projection import (
    ClaimEmbeddingQueueHealthRequest,
    ClaimEmbeddingQueueReconcileRequest,
    ClaimEmbeddingWorkflowRequest,
    PROJECTION_SCHEMA_VERSION,
)
from src.contracts.config import ConfigLoadRequest
from src.contracts.files import WriteBytesRequest
from src.contracts.logging import LoggingSetupRequest
from src.orchestrators.claim_embedding_orchestrator import run_claim_embedding_workflow
from src.services.analytics_store_service import (
    read_claim_embedding_queue_health,
    reconcile_claim_embedding_queue,
)
from src.services.config_service import load_settings
from src.services.file_service import write_bytes
from src.services.logging_service import setup_logging
from src.utils.logging import new_run_context


def _health_request(
    *,
    reports_db: str,
    embedding_version: str,
    provider: str,
    model: str,
    report_ids: list[str],
    publishers: list[str],
    max_estimated_tokens: int = 0,
    max_estimated_cost_usd: float = 0.0,
    model_pricing: dict[str, Any] | None = None,
) -> ClaimEmbeddingQueueHealthRequest:
    return ClaimEmbeddingQueueHealthRequest(
        schema_version=PROJECTION_SCHEMA_VERSION,
        db_path=reports_db,
        embedding_version=embedding_version,
        provider=provider,
        model=model,
        report_ids=report_ids,
        publishers=publishers,
        max_estimated_tokens=max_estimated_tokens,
        max_estimated_cost_usd=max_estimated_cost_usd,
        model_pricing=model_pricing or {},
    )


def _health_item_payload(item) -> dict[str, object]:
    payload = asdict(item)
    payload.pop("text_payload", None)
    payload.pop("metadata", None)
    return payload


def _health_payload(health) -> dict[str, object]:
    """Emit queue identifiers and operational metadata, never payload text."""
    items: list[dict[str, object]] = []
    for item in health.items:
        items.append(_health_item_payload(item))
    return {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "classification_counts": health.classification_counts,
        "status_counts": health.status_counts,
        "total_pending": health.total_pending,
        "oldest_pending_age_seconds": health.oldest_pending_age_seconds,
        "age_percentiles_seconds": health.age_percentiles_seconds,
        "observed_throughput_per_hour": health.observed_throughput_per_hour,
        "completion_rate": health.completion_rate,
        "estimated_drain_seconds": health.estimated_drain_seconds,
        "retry_reason_counts": health.retry_reason_counts,
        "terminal_reason_counts": health.terminal_reason_counts,
        "content_hash_skip_count": health.content_hash_skip_count,
        "model_version_mismatch_count": health.model_version_mismatch_count,
        "items": items,
    }


def _write_json_artifact(path: str, payload: dict[str, object], ctx) -> None:
    if not path.strip():
        return
    write_bytes(
        WriteBytesRequest(
            schema_version="1.0",
            path=str(Path(path)),
            content=(
                json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8"),
        ),
        ctx,
    )


def _summary(title: str, values: dict[str, object]) -> None:
    table = Table(title=title, box=box.SIMPLE_HEAVY)
    table.add_column("Metric")
    table.add_column("Value")
    for name, value in values.items():
        table.add_row(name.replace("_", " "), str(value))
    console.print(table)


def _ctx(task_id: str):
    ctx = new_run_context(task_id=task_id)
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    return ctx


@cli_app.command("embedding-queue-health")
def embedding_queue_health(
    reports_db: str = typer.Option("state/reports.sqlite"),
    embedding_version: str = typer.Option("claim-embedding.v1"),
    provider: str = typer.Option("openai"),
    model: str = typer.Option("text-embedding-3-small"),
    report_id: list[str] | None = typer.Option(None),
    publisher: list[str] | None = typer.Option(None),
    output: str = typer.Option("out/claim-embedding-queue-health.json"),
) -> None:
    """Create a read-only, machine-readable queue-health artifact."""
    ctx = _ctx("cli_embedding_queue_health")
    health = read_claim_embedding_queue_health(
        _health_request(
            reports_db=reports_db,
            embedding_version=embedding_version,
            provider=provider,
            model=model,
            report_ids=report_id or [],
            publishers=publisher or [],
        ),
        ctx,
    )
    payload = _health_payload(health)
    _write_json_artifact(output, payload, ctx)
    _summary(
        "Claim Embedding Queue Health",
        {
            "rows": len(health.items),
            "total pending": health.total_pending,
            "oldest pending age seconds": health.oldest_pending_age_seconds,
            "estimated drain seconds": health.estimated_drain_seconds,
            "throughput per hour": health.observed_throughput_per_hour,
            "classifications": health.classification_counts,
            "artifact": output,
        },
    )


@cli_app.command("embedding-queue-reconcile")
def embedding_queue_reconcile(
    reports_db: str = typer.Option("state/reports.sqlite"),
    embedding_version: str = typer.Option("claim-embedding.v1"),
    provider: str = typer.Option("openai"),
    model: str = typer.Option("text-embedding-3-small"),
    report_id: list[str] | None = typer.Option(None),
    publisher: list[str] | None = typer.Option(None),
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    output: str = typer.Option("out/claim-embedding-queue-reconcile.json"),
) -> None:
    """Reconcile satisfied, stale, obsolete and orphaned rows without provider calls."""
    ctx = _ctx("cli_embedding_queue_reconcile")
    health_request = _health_request(
        reports_db=reports_db,
        embedding_version=embedding_version,
        provider=provider,
        model=model,
        report_ids=report_id or [],
        publishers=publisher or [],
    )
    result = reconcile_claim_embedding_queue(
        ClaimEmbeddingQueueReconcileRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            health_request=health_request,
            run_id=str(ctx.run_id),
            actor="cli_embedding_queue_reconcile",
            dry_run=dry_run,
        ),
        ctx,
    )
    _write_json_artifact(output, asdict(result), ctx)
    _summary(
        "Claim Embedding Queue Reconciliation",
        {
            "mode": "dry run" if dry_run else "apply",
            "transitions": len(result.transitioned_entity_uids),
            "provider calls avoided": result.provider_calls_avoided,
            "artifact": output,
        },
    )


@cli_app.command("embedding-queue-run")
def embedding_queue_run(
    reports_db: str = typer.Option("state/reports.sqlite"),
    embedding_version: str = typer.Option("claim-embedding.v1"),
    provider: str = typer.Option("openai"),
    model: str = typer.Option("text-embedding-3-small"),
    max_rows: int = typer.Option(25, min=1),
    max_reports: int = typer.Option(5, min=1),
    max_estimated_tokens: int = typer.Option(8_000, min=1),
    max_estimated_cost_usd: float = typer.Option(1.0, min=0.0),
    max_runtime_seconds: float = typer.Option(120.0, min=1.0),
    max_retries: int = typer.Option(3, min=1),
    max_concurrent_provider_calls: int = typer.Option(1, min=1, max=1),
    publisher_fairness_limit: int = typer.Option(3, min=1),
    report_id: list[str] | None = typer.Option(None),
    publisher: list[str] | None = typer.Option(None),
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    output: str = typer.Option("out/claim-embedding-queue-run.json"),
) -> None:
    """Run one conservative bounded batch; --apply is required for provider calls."""
    ctx = _ctx("cli_embedding_queue_run")
    api_key = ""
    model_pricing: dict[str, Any] = {}
    state_db = ""
    if not dry_run:
        settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
        if not settings.openai_api_key:
            raise typer.BadParameter(
                "OpenAI credentials are required for --apply; configure them through .env."
            )
        api_key = settings.openai_api_key
        model_pricing = getattr(settings, "model_pricing", {})
        state_db = settings.state_db
    response = run_claim_embedding_workflow(
        ClaimEmbeddingWorkflowRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=reports_db,
            api_key=api_key,
            provider=provider,
            model=model,
            embedding_version=embedding_version,
            limit=max_rows,
            timeout_seconds=None,
            ctx=ctx,
            model_pricing=model_pricing,
            max_reports=max_reports,
            max_estimated_tokens=max_estimated_tokens,
            max_estimated_cost_usd=max_estimated_cost_usd,
            max_runtime_seconds=max_runtime_seconds,
            max_retries=max_retries,
            max_concurrent_provider_calls=max_concurrent_provider_calls,
            publisher_fairness_limit=publisher_fairness_limit,
            report_ids=report_id or [],
            publishers=publisher or [],
            dry_run=dry_run,
            state_db=state_db,
        )
    )
    _write_json_artifact(output, asdict(response), ctx)
    _summary(
        "Claim Embedding Queue Batch",
        {
            "mode": "dry run" if dry_run else "apply",
            "embedded": response.embedded_count,
            "failed": response.failed_count,
            "provider calls avoided": response.provider_calls_avoided,
            "actual input tokens": response.actual_input_tokens,
            "actual estimated cost usd": response.actual_cost_usd,
            "artifact": output,
        },
    )


@cli_app.command("embedding-queue-failures")
def embedding_queue_failures(
    reports_db: str = typer.Option("state/reports.sqlite"),
    embedding_version: str = typer.Option("claim-embedding.v1"),
    provider: str = typer.Option("openai"),
    model: str = typer.Option("text-embedding-3-small"),
    report_id: list[str] | None = typer.Option(None),
    output: str = typer.Option("out/claim-embedding-queue-failures.json"),
) -> None:
    """Inspect terminal and retryable queue rows without writes or provider calls."""
    ctx = _ctx("cli_embedding_queue_failures")
    health = read_claim_embedding_queue_health(
        _health_request(
            reports_db=reports_db,
            embedding_version=embedding_version,
            provider=provider,
            model=model,
            report_ids=report_id or [],
            publishers=[],
        ),
        ctx,
    )
    payload = _health_payload(health)
    failure_items = [
        _health_item_payload(item)
        for item in health.items
        if item.classification in {"terminal_failure", "retryable_failure"}
    ]
    payload["items"] = failure_items
    _write_json_artifact(output, payload, ctx)
    _summary(
        "Claim Embedding Queue Failures",
        {"rows": len(failure_items), "artifact": output},
    )
