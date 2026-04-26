from __future__ import annotations

import json
import logging

import pytest

from src.contracts.idempotency import (
    OrchestratorIdempotencyGetRequest,
    OrchestratorIdempotencyRecordRequest,
)
from src.contracts.run_context import RunContext
from src.services import idempotency_service


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="run",
        task_id="task",
        span_id="span",
    )


def _events(caplog) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != "market_lense.idempotency_service":
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def test_idempotency_service_records_and_reuses_outcome(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    db_path = str(tmp_path / "idempotency.sqlite")
    caplog.set_level(logging.INFO, logger="market_lense.idempotency_service")

    recorded = idempotency_service.record_outcome(
        OrchestratorIdempotencyRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            scope="publish_html",
            idempotency_key="ml_report:file-1",
            input_checksum="checksum-1",
            outcome_payload={"schema_version": "1.0", "status": "published"},
            artifact_references={"post_id": 42},
        ),
        _ctx(),
    )
    lookup = idempotency_service.get_outcome(
        OrchestratorIdempotencyGetRequest(
            schema_version="1.0",
            db_path=db_path,
            scope="publish_html",
            idempotency_key="ml_report:file-1",
            input_checksum="checksum-1",
        ),
        _ctx(),
    )

    assert recorded.scope == "publish_html"
    assert lookup.found is True
    assert lookup.record is not None
    assert lookup.record.outcome_payload["status"] == "published"
    assert lookup.record.artifact_references["post_id"] == 42
    assert_logs_have_required_fields(_events(caplog))


def test_idempotency_service_rejects_checksum_mismatch(
    tmp_path,
    assert_app_error,
) -> None:
    db_path = str(tmp_path / "idempotency.sqlite")
    idempotency_service.record_outcome(
        OrchestratorIdempotencyRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            scope="publish_html",
            idempotency_key="ml_report:file-1",
            input_checksum="checksum-1",
            outcome_payload={"schema_version": "1.0", "status": "published"},
            artifact_references={},
        ),
        _ctx(),
    )

    with pytest.raises(Exception) as exc_info:
        idempotency_service.get_outcome(
            OrchestratorIdempotencyGetRequest(
                schema_version="1.0",
                db_path=db_path,
                scope="publish_html",
                idempotency_key="ml_report:file-1",
                input_checksum="checksum-2",
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="idempotency_checksum_mismatch",
        retryable=False,
    )
