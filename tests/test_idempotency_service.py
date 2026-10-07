from __future__ import annotations

import json
import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.contracts.idempotency import (
    OrchestratorIdempotencyGetRequest,
    OrchestratorIdempotencyRecordRequest,
)
from src.contracts.run_context import RunContext
from src.services import idempotency_service
from src.utils.errors import AppError


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


@pytest.mark.parametrize(
    ("column", "corrupt_value"),
    [
        pytest.param("outcome_json", "{malformed-private-payload", id="bad-json"),
        pytest.param("outcome_json", '["private-outcome-marker"]', id="array-outcome"),
        pytest.param("outcome_json", '"scalar"', id="scalar-outcome"),
        pytest.param("artifact_refs_json", "[]", id="array-artifact-references"),
        pytest.param("scope", "", id="missing-scope"),
        pytest.param("idempotency_key", "", id="missing-idempotency-key"),
        pytest.param("input_checksum", "", id="missing-input-identity"),
        pytest.param("recorded_at_utc", "", id="missing-record-time"),
    ],
)
def test_lookup_fails_closed_on_corrupt_persisted_records(
    tmp_path, column: str, corrupt_value: str
) -> None:
    db_path = str(tmp_path / "idempotency.sqlite")
    idempotency_service.record_outcome(
        OrchestratorIdempotencyRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            scope="publish_html",
            idempotency_key="report:1",
            input_checksum="checksum-1",
            outcome_payload={"status": "published"},
            artifact_references={"post_id": 42},
        ),
        _ctx(),
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"UPDATE orchestrator_idempotency SET {column}=? "
            "WHERE scope=? AND idempotency_key=?",
            (corrupt_value, "publish_html", "report:1"),
        )

    with pytest.raises(AppError) as exc_info:
        idempotency_service.get_outcome(
            OrchestratorIdempotencyGetRequest(
                schema_version="1.0",
                db_path=db_path,
                scope="publish_html",
                idempotency_key="report:1",
                input_checksum="checksum-1",
            ),
            _ctx(),
        )

    error = exc_info.value
    assert error.code == "idempotency_record_corrupt"
    assert error.retryable is False
    assert "private-outcome-marker" not in str(error)
    assert "private-outcome-marker" not in json.dumps(error.context)
    with sqlite3.connect(db_path) as conn:
        retained_value = conn.execute(
            f"SELECT {column} FROM orchestrator_idempotency"
        ).fetchone()[0]
    assert retained_value == corrupt_value


def test_empty_persisted_outcome_objects_remain_valid(tmp_path) -> None:
    db_path = str(tmp_path / "idempotency.sqlite")
    idempotency_service.record_outcome(
        OrchestratorIdempotencyRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            scope="test_empty_allowed",
            idempotency_key="empty-outcome",
            input_checksum="checksum-empty",
            outcome_payload={},
            artifact_references={},
        ),
        _ctx(),
    )

    lookup = idempotency_service.get_outcome(
        OrchestratorIdempotencyGetRequest(
            schema_version="1.0",
            db_path=db_path,
            scope="test_empty_allowed",
            idempotency_key="empty-outcome",
            input_checksum="checksum-empty",
        ),
        _ctx(),
    )

    assert lookup.found is True
    assert lookup.record is not None
    assert lookup.record.outcome_payload == {}
    assert lookup.record.artifact_references == {}


def test_lookup_fails_closed_when_both_persisted_identity_fields_are_missing(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "idempotency.sqlite")
    idempotency_service.record_outcome(
        OrchestratorIdempotencyRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            scope="publish_html",
            idempotency_key="report:1",
            input_checksum="checksum-1",
            outcome_payload={"status": "published"},
            artifact_references={},
        ),
        _ctx(),
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE orchestrator_idempotency SET scope='',idempotency_key=''")

    with pytest.raises(AppError) as exc_info:
        idempotency_service.get_outcome(
            OrchestratorIdempotencyGetRequest(
                schema_version="1.0",
                db_path=db_path,
                scope="publish_html",
                idempotency_key="report:1",
                input_checksum="checksum-1",
            ),
            _ctx(),
        )

    assert exc_info.value.code == "idempotency_record_corrupt"
    assert exc_info.value.retryable is False
    with sqlite3.connect(db_path) as conn:
        retained_identity = conn.execute(
            "SELECT scope,idempotency_key FROM orchestrator_idempotency"
        ).fetchone()
    assert retained_identity == ("", "")


def test_concurrent_conflicting_checksums_are_serialized_before_upsert(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "idempotency.sqlite")
    idempotency_service.record_outcome(
        OrchestratorIdempotencyRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            scope="publish_html",
            idempotency_key="setup",
            input_checksum="setup-checksum",
            outcome_payload={},
            artifact_references={},
        ),
        _ctx(),
    )

    def record_conflict(key: str, checksum: str, barrier: threading.Barrier):
        barrier.wait(timeout=5)
        try:
            idempotency_service.record_outcome(
                OrchestratorIdempotencyRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    scope="publish_html",
                    idempotency_key=key,
                    input_checksum=checksum,
                    outcome_payload={"input": checksum},
                    artifact_references={},
                ),
                _ctx(),
            )
        except AppError as exc:
            return ("error", exc.code)
        return ("written", checksum)

    with ThreadPoolExecutor(max_workers=2) as executor:
        for index in range(20):
            key = f"report:{index}"
            barrier = threading.Barrier(2)
            futures = [
                executor.submit(record_conflict, key, "checksum-a", barrier),
                executor.submit(record_conflict, key, "checksum-b", barrier),
            ]
            outcomes = [future.result(timeout=10) for future in futures]

            assert sum(result[0] == "written" for result in outcomes) == 1
            assert (
                sum(
                    result[0] == "error"
                    and result[1] == "idempotency_checksum_mismatch"
                    for result in outcomes
                )
                == 1
            ), outcomes
            with sqlite3.connect(db_path) as conn:
                stored_checksum = conn.execute(
                    "SELECT input_checksum FROM orchestrator_idempotency "
                    "WHERE scope=? AND idempotency_key=?",
                    ("publish_html", key),
                ).fetchone()[0]
            assert stored_checksum in {"checksum-a", "checksum-b"}
