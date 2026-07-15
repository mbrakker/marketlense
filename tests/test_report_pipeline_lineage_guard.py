from __future__ import annotations

import pytest

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestSettings
from src.contracts.pipeline_preflight import PipelinePreflightReport
from src.contracts.run_context import RunContext
from src.orchestrators.report_pipeline_orchestrator import run_report_pipeline
from src.utils.errors import AppError


def test_report_pipeline_fails_closed_when_selective_lineage_is_missing() -> None:
    settings = IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-5-mini",
        batch_limit=1,
        output_dir="./out",
        cache_dir="./cache",
        state_db="./state.sqlite",
        reports_db="./reports.sqlite",
        category_mapping_path="./categories.yaml",
        cover_style_path="./covers.yaml",
        ingest_lock_path="./ingest.lock",
        temperature=0.0,
    )
    report = PipelinePreflightReport(
        schema_version="1.0",
        workflow="report_pipeline",
        planned_side_effects=[],
        passed=True,
        expensive_side_effects_allowed=True,
        blocker_count=0,
        warning_count=0,
        auto_fixed_count=0,
        checks=[],
        blockers=[],
        warnings=[],
        auto_fixable_issues=[],
        next_actions=[],
    )

    with pytest.raises(AppError) as exc_info:
        run_report_pipeline(
            DriveFile("1.0", "report", "report.pdf", None, "md5"),
            "./cache/report.pdf",
            settings,
            "md5",
            RunContext("1.0", "run", "task", "span"),
            retries=0,
            preflight_fn=lambda *_args, **_kwargs: report,
            lineage_change_kind="template",
            lineage_available=False,
        )

    assert exc_info.value.code == "lineage_regeneration_lineage_missing"
    assert exc_info.value.retryable is False
