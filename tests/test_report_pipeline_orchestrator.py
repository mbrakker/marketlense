from __future__ import annotations

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.run_context import RunContext
from src.orchestrators import report_pipeline_orchestrator as orch
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _settings() -> IngestSettings:
    return IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-5",
        batch_limit=1,
        output_dir="./out",
        cache_dir="./cache",
        state_db="./state/index.sqlite",
        reports_db="./state/reports.sqlite",
        category_mapping_path="./src/config/category-mappings.yaml",
        cover_style_path="./src/config/cover-styles.yaml",
        ingest_lock_path="./state/ingest.lock",
        ingest_lock_ttl_seconds=7200.0,
        temperature=1.0,
    )


def test_run_report_pipeline_retries_retryable(monkeypatch) -> None:
    file = DriveFile(schema_version="1.0", file_id="f1", name="a.pdf", modified_time=None, md5_checksum="md5")
    outcome = IngestOutcome(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        md5="md5",
        html_path="./out/a.html",
        status="processed",
    )
    calls = {"count": 0}

    def _gen(file, local_pdf_path, settings, md5, ctx):
        calls["count"] += 1
        if calls["count"] < 3:
            raise AppError(code="openai_request_failed", message="retry", retryable=True)
        return outcome

    monkeypatch.setattr(orch.time, "sleep", lambda _: None)
    response = orch.run_report_pipeline(
        file,
        local_pdf_path="./cache/a.pdf",
        settings=_settings(),
        md5="md5",
        ctx=_ctx(),
        retries=2,
        generate_report_fn=_gen,
    )
    assert calls["count"] == 3
    assert response.status == "processed"
