from __future__ import annotations

from pathlib import Path

from scripts.ci import check_public_report_quality


def test_public_report_quality_gate_checks_retained_corpus(tmp_path: Path) -> None:
    output = tmp_path / "quality.json"

    exit_code = check_public_report_quality.run_public_report_quality_gate(
        artifact_root="tests/fixtures/docpacks/golden",
        output_dir=str(tmp_path / "rendered"),
        output_json=str(output),
        minimum_reports=15,
    )

    assert exit_code == 0
    assert output.is_file()
    assert '"internal_id_leak_count": 0' in output.read_text(encoding="utf-8")
