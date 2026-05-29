"""Artifact-step batch scheduling for report analysis.

This module owns bounded artifact task execution and scheduler logging; the
public orchestrator decides when artifact generation runs.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict

from src.contracts.artifact_generation import ArtifactRenderTask
from src.orchestrators._report_analysis_orchestrator.shared import logger
from src.utils.coercion import coerce_int
from src.utils.logging import log_event

__all__ = [
    "ArtifactTaskRenderer",
    "_artifact_batch_workers",
    "_execute_artifact_step_batch",
]


ArtifactTaskRenderer = Callable[[ArtifactRenderTask], Dict[str, Any]]


def _execute_artifact_step_batch(
    settings,
    tasks: Sequence[ArtifactRenderTask],
    render_task: ArtifactTaskRenderer,
    ctx,
    batch_name: str,
) -> Dict[str, Dict[str, Any]]:
    max_workers, configured_workers, global_max = _artifact_batch_workers(
        settings, len(tasks)
    )
    task_names = [task.step_name for task in tasks]
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="artifact_step_batch_start",
            module=logger.name,
            fields={
                "batch_name": batch_name,
                "steps": task_names,
                "step_count": len(task_names),
                "max_workers": max_workers,
                "configured_parallel_workers": configured_workers,
                "global_max_in_flight": global_max,
                "scheduling_policy": "bounded_thread_pool",
            },
        )
    )
    results: Dict[str, Dict[str, Any]] = {}
    if max_workers <= 1 or len(tasks) <= 1:
        for task in tasks:
            try:
                results[task.step_name] = render_task(task)
            except Exception as exc:
                logger.info(
                    log_event(
                        ctx,
                        role="orchestrator",
                        event="artifact_step_failed",
                        module=logger.name,
                        fields={
                            "batch_name": batch_name,
                            "step": task.step_name,
                            "error": str(exc),
                        },
                    )
                )
                raise
    else:
        first_error: Exception | None = None
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(render_task, task): task for task in tasks}
            for future in as_completed(futures):
                task = futures[future]
                try:
                    results[task.step_name] = future.result()
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
                    logger.info(
                        log_event(
                            ctx,
                            role="orchestrator",
                            event="artifact_step_failed",
                            module=logger.name,
                            fields={
                                "batch_name": batch_name,
                                "step": task.step_name,
                                "error": str(exc),
                            },
                        )
                    )
            if first_error is not None:
                for future in futures:
                    future.cancel()
                raise first_error
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="artifact_step_batch_complete",
            module=logger.name,
            fields={
                "batch_name": batch_name,
                "steps": task_names,
                "max_workers": max_workers,
            },
        )
    )
    return results


def _artifact_batch_workers(settings, step_count: int) -> tuple[int, int, int]:
    configured = coerce_int(
        getattr(settings, "artifact_parallel_workers", 4), 4, min_value=1
    )
    global_max = coerce_int(
        getattr(settings, "artifact_global_max_in_flight", configured),
        configured,
        min_value=1,
    )
    return max(1, min(configured, global_max, step_count)), configured, global_max
