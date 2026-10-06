# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


def test_pdf_budget_stop_prevents_report_generation_call(tmp_path) -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="budgeted-pdf",
        name="budgeted.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    settings = replace(
        _settings(),
        run_budget_max_pdfs=0,
        usage_db_path=str(tmp_path / "pdf_budget.sqlite"),
    )
    calls = {"count": 0}

    def _generate(*_args, **_kwargs):
        calls["count"] += 1
        raise AssertionError("PDF budget must stop before report generation")

    with pytest.raises(AppError) as exc_info:
        orch.run_report_pipeline(
            file,
            local_pdf_path="./cache/budgeted.pdf",
            settings=settings,
            md5="md5",
            ctx=_ctx(),
            retries=0,
            generate_report_fn=_generate,
            execution_plan_mode="disabled",
        )

    assert exc_info.value.code == "report_pipeline_pdf_budget_stop"
    assert exc_info.value.retryable is False
    assert calls["count"] == 0


def test_pdf_budget_defer_persists_resumable_report_work_without_generation(
    tmp_path,
) -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="deferred-pdf",
        name="deferred.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    settings = replace(
        _settings(),
        state_db=str(tmp_path / "state.sqlite"),
        run_budget_max_pdfs=0,
        run_budget_limit_decision="defer",
        usage_db_path=str(tmp_path / "pdf_budget.sqlite"),
    )
    calls = {"count": 0}

    def _generate(*_args, **_kwargs):
        calls["count"] += 1
        raise AssertionError("Deferred PDF work must not start report generation")

    with pytest.raises(AppError) as exc_info:
        orch.run_report_pipeline(
            file,
            local_pdf_path=str(tmp_path / "retained.pdf"),
            settings=settings,
            md5="md5",
            ctx=_ctx(),
            retries=0,
            generate_report_fn=_generate,
            execution_plan_mode="disabled",
        )

    assert exc_info.value.code == "report_pipeline_pdf_budget_defer"
    assert exc_info.value.context["retry_decision"] == "defer"
    assert calls["count"] == 0
    records = list_deferred_work(
        DeferredWorkListRequest(
            schema_version="1.0", usage_db_path=settings.usage_db_path, limit=10
        ),
        _ctx(),
    ).records
    assert len(records) == 1
    assert records[0].status == "pending"
    assert records[0].stage == "source_prepared"
    assert records[0].report_id == file.file_id
    assert records[0].source_id == ""
    assert records[0].reusable_artifacts[0].reference == str(tmp_path / "retained.pdf")
