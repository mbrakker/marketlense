from __future__ import annotations

import json

from src.contracts.run_context import RunContext
from src.contracts.state import (
    WorkflowControlObservationListRequest,
    WorkflowControlObservationListResponse,
    WorkflowControlObservationWriteRequest,
    WorkflowControlObservationWriteResponse,
)
from src.contracts.workflow_control import WorkflowControlObservation
from src.services._state_service.common import _state_conn, logger
from src.utils.logging import log_event


def write_workflow_control_observation(
    request: WorkflowControlObservationWriteRequest,
    ctx: RunContext,
) -> WorkflowControlObservationWriteResponse:
    observation = request.observation
    logger.info(
        log_event(
            ctx,
            role="service",
            event="workflow_control_observation_write_start",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "run_id": observation.run_id,
                "workflow": observation.workflow,
                "step_name": observation.step_name,
                "route": observation.route,
                "outcome": observation.outcome,
            },
        )
    )
    with _state_conn(request.state_db, ctx) as conn:
        conn.execute(
            """
            INSERT INTO workflow_control_observations(
              observed_at_utc, run_id, workflow, step_name, route, publisher,
              report_key, outcome, error_code, error_retryable, error_severity,
              latency_ms, cost_usd, retry_count, resource_pressure_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.observed_at_utc,
                observation.run_id,
                observation.workflow,
                observation.step_name,
                observation.route,
                observation.publisher,
                observation.report_key,
                observation.outcome,
                observation.error_code,
                1 if observation.error_retryable else 0,
                observation.error_severity,
                int(observation.latency_ms),
                float(observation.cost_usd),
                int(observation.retry_count),
                json.dumps(
                    observation.resource_pressure,
                    sort_keys=True,
                    ensure_ascii=True,
                ),
            ),
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="workflow_control_observation_write_complete",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "run_id": observation.run_id,
                "workflow": observation.workflow,
            },
        )
    )
    return WorkflowControlObservationWriteResponse(
        schema_version="1.0",
        observation=observation,
    )


def list_workflow_control_observations(
    request: WorkflowControlObservationListRequest,
    ctx: RunContext,
) -> WorkflowControlObservationListResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="workflow_control_observation_list_start",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "workflow": request.workflow,
                "publisher": request.publisher,
                "observed_after_utc": request.observed_after_utc,
                "limit": request.limit,
            },
        )
    )
    where: list[str] = []
    params: list[object] = []
    if request.workflow.strip():
        where.append("workflow = ?")
        params.append(request.workflow.strip())
    if request.publisher.strip():
        where.append("publisher = ?")
        params.append(request.publisher.strip())
    if request.observed_after_utc.strip():
        where.append("observed_at_utc >= ?")
        params.append(request.observed_after_utc.strip())
    query = "SELECT * FROM workflow_control_observations"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY observed_at_utc DESC, id DESC LIMIT ?"
    params.append(max(1, int(request.limit or 200)))
    observations: list[WorkflowControlObservation] = []
    with _state_conn(request.state_db, ctx) as conn:
        conn.row_factory = None
        rows = conn.execute(query, tuple(params)).fetchall()
    for row in rows:
        pressure_raw = str(row[15] or "{}")
        try:
            pressure = json.loads(pressure_raw)
        except json.JSONDecodeError:
            pressure = {}
        observations.append(
            WorkflowControlObservation(
                schema_version="1.0",
                observed_at_utc=str(row[1] or ""),
                run_id=str(row[2] or ""),
                workflow=str(row[3] or ""),
                step_name=str(row[4] or ""),
                route=str(row[5] or ""),
                publisher=str(row[6] or ""),
                report_key=str(row[7] or ""),
                outcome=str(row[8] or ""),
                error_code=str(row[9] or ""),
                error_retryable=bool(int(row[10] or 0)),
                error_severity=str(row[11] or ""),
                latency_ms=int(row[12] or 0),
                cost_usd=float(row[13] or 0.0),
                retry_count=int(row[14] or 0),
                resource_pressure=pressure if isinstance(pressure, dict) else {},
            )
        )
    response = WorkflowControlObservationListResponse(
        schema_version="1.0",
        observations=observations,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="workflow_control_observation_list_complete",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "count": len(response.observations),
            },
        )
    )
    return response
