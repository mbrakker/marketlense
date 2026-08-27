from __future__ import annotations

from pathlib import Path

from scripts.ci import check_coverage, run_mutation_gate


def test_control_plane_modules_have_stricter_coverage_gate() -> None:
    source = Path("scripts/ci/check_coverage.py").read_text(encoding="utf-8")

    assert "src/orchestrators/pipeline_preflight_orchestrator.py" in source
    assert "src/orchestrators/retry_telemetry_orchestrator.py" in source
    assert "src/orchestrators/workflow_control_orchestrator.py" in source
    assert "src/contracts/workflow_control.py" in source
    assert "COVERAGE_CONTROL_PLANE_MIN" in source
    assert check_coverage._threshold("COVERAGE_CONTROL_PLANE_MIN", 85.0) == 85.0


def test_control_plane_modules_are_targeted_by_mutation_gate() -> None:
    targets = list(run_mutation_gate._targets())
    module_paths = {target.module_path.as_posix() for target in targets}

    assert any(
        path.endswith("pipeline_preflight_orchestrator.py") for path in module_paths
    )
    assert any(
        path.endswith("retry_telemetry_orchestrator.py") for path in module_paths
    )
    assert any(
        path.endswith("workflow_control_orchestrator.py") for path in module_paths
    )


def test_report_pipeline_mutation_target_covers_p15_refresh_tests() -> None:
    target = next(
        target
        for target in run_mutation_gate._targets()
        if target.module_path.as_posix().endswith("report_pipeline_orchestrator.py")
    )

    assert target.test_paths == (
        "tests/test_report_pipeline_orchestrator.py",
        "tests/test_publish_readiness_refresh.py",
    )
