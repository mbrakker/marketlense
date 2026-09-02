from __future__ import annotations

from pathlib import Path

MAX_TEST_FILE_LINES = 1000
LONG_TEST_FILE_ALLOWLIST = {
    "tests/test_report_download_route_planner.py": {
        "owner": "quality/repository-hygiene",
        "reason": "Pre-existing route-planner case split remains pending.",
        "expires_on": "2026-08-31",
        "max_lines": 1085,
    },
    "tests/test_ingest_parallel.py": {
        "owner": "quality/repository-hygiene",
        "reason": "Pre-existing ingest parallelism and report-card cases remain colocated.",
        "expires_on": "2026-08-31",
        "max_lines": 1040,
    },
    "tests/test_report_pipeline_orchestrator.py": {
        "owner": "quality/repository-hygiene",
        "reason": "Pipeline retry, planning, and durable budget-defer cases remain colocated.",
        "expires_on": "2026-08-31",
        "max_lines": 1150,
    },
    "tests/test_render_service_artifacts.py": {
        "owner": "quality/repository-hygiene",
        "reason": "Pre-existing render artifact integration cases remain colocated.",
        "expires_on": "2026-09-30",
        "max_lines": 1390,
    },
    "tests/test_report_render_generator.py": {
        "owner": "quality/repository-hygiene",
        "reason": "Pre-existing report render generator cases remain colocated.",
        "expires_on": "2026-08-31",
        "max_lines": 1075,
    },
    "tests/_test_ingest_cohort/cases_01_cohort_admission_and_replay.py": {
        "owner": "quality/repository-hygiene",
        "reason": (
            "Frozen-cohort admission, canonical source identity, and replay "
            "cases require a follow-up split."
        ),
        "expires_on": "2026-09-30",
        "max_lines": 1280,
    },
    "tests/_test_report_render_generator/cases_01_render_output_and_cards.py": {
        "owner": "quality/repository-hygiene",
        "reason": "Render output and card cases require a follow-up split.",
        "expires_on": "2026-08-31",
        "max_lines": 1140,
    },
    "tests/_test_validation_generator/cases_01_validation_flags_metric_and_quote.py": {
        "owner": "quality/repository-hygiene",
        "reason": "Validation grounding and cache cases require a follow-up split.",
        "expires_on": "2026-09-30",
        "max_lines": 1056,
    },
    "tests/test_report_regeneration_generator.py": {
        "owner": "quality/repository-hygiene",
        "reason": "Targeted regeneration coverage requires a follow-up split.",
        "expires_on": "2026-09-30",
        "max_lines": 1338,
    },
}


def test_first_party_test_modules_stay_below_long_file_threshold() -> None:
    long_files: list[str] = []

    for path in sorted(Path("tests").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        line_count = sum(1 for _ in path.open(encoding="utf-8"))
        allowlist_entry = LONG_TEST_FILE_ALLOWLIST.get(path.as_posix())
        if allowlist_entry is not None and line_count <= int(
            allowlist_entry["max_lines"]
        ):
            continue
        if line_count > MAX_TEST_FILE_LINES:
            long_files.append(f"{path.as_posix()}:{line_count}")

    assert long_files == []


def test_long_test_file_allowlist_entries_have_owner_reason_and_expiry() -> None:
    assert LONG_TEST_FILE_ALLOWLIST
    for path, entry in LONG_TEST_FILE_ALLOWLIST.items():
        assert Path(path).exists()
        assert str(entry["owner"]).strip()
        assert str(entry["reason"]).strip()
        assert str(entry["expires_on"]).strip()
        assert int(entry["max_lines"]) > MAX_TEST_FILE_LINES
