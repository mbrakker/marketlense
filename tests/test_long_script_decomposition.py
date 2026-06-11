from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_FACADE_LINES = 1_000

TARGET_FACADES = (
    "src/services/drive_service.py",
    "src/ui/app_pages/publisher_operations.py",
    "src/services/_pdf/visual_heuristics.py",
    "src/orchestrators/ui_run_execution_orchestrator.py",
    "src/services/_pdf/_visual_heuristics/chart_layout.py",
    "src/generators/report_source_generator.py",
)

EXPECTED_OWNER_MODULES = (
    "src/services/_drive_service/auth.py",
    "src/services/_drive_service/client_cache.py",
    "src/services/_drive_service/listing.py",
    "src/services/_drive_service/write.py",
    "src/ui/app_pages/_publisher_operations/requests.py",
    "src/ui/app_pages/_publisher_operations/report_download.py",
    "src/services/_pdf/_visual_heuristics/shared.py",
    "src/services/_pdf/_visual_heuristics/_chart_layout/geometry.py",
    "src/orchestrators/_ui_run_execution_orchestrator/validation.py",
    "src/orchestrators/_ui_run_execution_orchestrator/requests.py",
    "src/orchestrators/_ui_run_execution_orchestrator/workflow.py",
    "src/generators/_report_source_generator/cache_io.py",
    "src/generators/_report_source_generator/source_loading.py",
    "src/generators/_report_source_generator/text_validation.py",
    "src/generators/_report_source_generator/workflow.py",
)


def _line_count(relative_path: str) -> int:
    return len((ROOT / relative_path).read_text(encoding="utf-8").splitlines())


def test_long_runtime_scripts_are_logically_split_under_existing_boundaries() -> None:
    too_long = {
        relative_path: _line_count(relative_path)
        for relative_path in TARGET_FACADES
        if _line_count(relative_path) > MAX_FACADE_LINES
    }

    assert too_long == {}
    for relative_path in EXPECTED_OWNER_MODULES:
        assert (ROOT / relative_path).is_file(), relative_path
