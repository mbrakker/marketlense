import json
import subprocess
import sys
from pathlib import Path

from scripts.quality.ias_live_canary_runner import (
    prepare_isolated_canary_run,
    run_ias_first_attempt_canary,
)


def test_prepare_isolated_canary_run_creates_fresh_root_with_only_rooted_mutable_paths(
    tmp_path: Path,
) -> None:
    run = prepare_isolated_canary_run(runs_root=tmp_path)

    assert run.root.is_dir()
    assert run.root.parent == tmp_path
    assert run.config_path.is_file()
    assert run.mutable_paths
    assert all(path.is_relative_to(run.root) for path in run.mutable_paths)
    assert not any(path.exists() for path in run.mutable_paths)


def test_live_canary_records_a_typed_terminal_input_failure(tmp_path: Path) -> None:
    result = run_ias_first_attempt_canary(
        runs_root=tmp_path,
        source_path=tmp_path / "missing-ias.pdf",
    )

    assert result["final_state"] == "failed"
    assert result["awaiting_review"] is False
    assert result["workflow_attempt_count"] == 0
    assert result["terminal_failure_code"] == "ias_canary_source_missing"
    assert (Path(result["run_directory"]) / "result.json").is_file()


def test_live_canary_script_prints_one_json_result_for_a_typed_failure(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/quality/run_ias_first_attempt_canary.py",
            "--runs-root",
            str(tmp_path),
            "--source",
            str(tmp_path / "missing-ias.pdf"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert (
        json.loads(completed.stdout)["terminal_failure_code"]
        == "ias_canary_source_missing"
    )
