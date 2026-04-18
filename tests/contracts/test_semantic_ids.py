from __future__ import annotations

import pytest

from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import ReportId, RunId, TaskId


def test_run_context_coerces_string_ids_to_typed_wrappers() -> None:
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-1",
        task_id="task-1",
        span_id="span-1",
    )

    assert isinstance(ctx.run_id, RunId)
    assert isinstance(ctx.task_id, TaskId)
    assert str(ctx.run_id) == "run-1"
    assert str(ctx.task_id) == "task-1"


def test_run_context_rejects_mixed_semantic_id_types() -> None:
    with pytest.raises(TypeError, match="RunContext.run_id"):
        RunContext(
            schema_version="1.0",
            run_id=TaskId("task-1"),
            task_id="task-1",
            span_id="span-1",
        )


def test_report_contract_rejects_non_report_identifier_types() -> None:
    with pytest.raises(TypeError, match="AnalysisStorePackRequest.report_id"):
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir="./out",
            report_id=RunId("run-1"),
            pack_name="taxonomy",
            payload={"schema_version": "1.0", "taxonomy": []},
            report_slug="report-slug",
        )


def test_report_contract_coerces_plain_string_to_report_id() -> None:
    request = AnalysisStorePackRequest(
        schema_version="1.0",
        output_dir="./out",
        report_id="report-1",
        pack_name="taxonomy",
        payload={"schema_version": "1.0", "taxonomy": []},
        report_slug="report-slug",
    )

    assert isinstance(request.report_id, ReportId)
    assert str(request.report_id) == "report-1"
