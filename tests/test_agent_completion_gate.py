from __future__ import annotations

import sys

from scripts.quality.agent_completion_gate import (
    Check,
    CheckExecution,
    _redact_sensitive_output,
    build_completion_report,
    classify_changes,
    run_selected_checks,
    select_checks,
    snapshot_working_tree,
)


def test_classifies_ordinary_service_change_as_focused_without_aggregate_gate() -> None:
    changed_files = ("src/services/file_service.py",)

    classification = classify_changes(changed_files)
    checks = select_checks(classification, changed_files)

    assert classification.full_gate_required is False
    assert "service_boundary" in classification.subsystems
    assert all(check.name != "canonical_quality_gate" for check in checks)


def test_contract_change_escalates_without_repeating_pytest_before_aggregate() -> None:
    changed_files = ("src/contracts/report.py",)

    classification = classify_changes(changed_files)
    checks = select_checks(classification, changed_files)

    assert classification.full_gate_required is True
    assert "public_contract" in classification.subsystems
    assert checks[-1].name == "canonical_quality_gate"
    assert all("pytest" not in check.command for check in checks[:-1])


def test_persisted_schema_change_escalates() -> None:
    classification = classify_changes(
        ("src/services/_sqlite_migration/add_report_revision.py",)
    )

    assert classification.full_gate_required is True
    assert "persisted_schema" in classification.subsystems


def test_selects_documentation_check_without_aggregate_gate_for_docs_only_change() -> (
    None
):
    changed_files = ("docs/quality/testing.md",)

    classification = classify_changes(changed_files)
    checks = select_checks(classification, changed_files)

    assert classification.full_gate_required is False
    assert tuple(check.name for check in checks) == ("documentation",)


def test_failed_required_check_prevents_pass_and_records_failure() -> None:
    changed_files = ("tests/test_file_service.py",)
    classification = classify_changes(changed_files)
    check = Check("focused_pytest", ("python", "-m", "pytest", "-q", *changed_files))

    report = build_completion_report(
        changed_files=changed_files,
        classification=classification,
        selected_checks=(check,),
        executions=(
            CheckExecution(
                check=check,
                returncode=1,
                elapsed_ms=12,
                stdout="one useful line\n",
                stderr="failure detail\n",
            ),
        ),
        working_tree_unchanged=True,
    )

    assert report["result"] == "FAIL"
    assert report["failures"] == ["focused_pytest failed with exit code 1"]
    assert report["tests_run"][0]["returncode"] == 1
    assert report["check_diagnostics"][0]["stderr"] == "failure detail"


def test_changed_worktree_after_checks_prevents_pass() -> None:
    changed_files = ("docs/quality/testing.md",)
    classification = classify_changes(changed_files)
    check = select_checks(classification, changed_files)[0]

    report = build_completion_report(
        changed_files=changed_files,
        classification=classification,
        selected_checks=(check,),
        executions=(CheckExecution(check=check, returncode=0, elapsed_ms=5),),
        working_tree_unchanged=False,
    )

    assert report["result"] == "FAIL"
    assert "working tree changed while checks ran" in report["failures"]


def test_stops_execution_after_first_required_check_failure() -> None:
    first = Check("first", ("first",))
    second = Check("second", ("second",))
    executed_names: list[str] = []

    def execute(check: Check) -> CheckExecution:
        executed_names.append(check.name)
        return CheckExecution(check=check, returncode=1, elapsed_ms=1)

    executions = run_selected_checks((first, second), execute=execute)

    assert tuple(execution.check.name for execution in executions) == ("first",)
    assert executed_names == ["first"]


def test_execution_decodes_bounded_failure_diagnostics() -> None:
    check = Check(
        "fails",
        (
            sys.executable,
            "-c",
            "import sys; print('stdout evidence'); "
            "print('stderr evidence', file=sys.stderr); sys.exit(1)",
        ),
    )

    execution = run_selected_checks((check,))[0]

    assert execution.returncode == 1
    assert execution.stdout == "stdout evidence"
    assert execution.stderr == "stderr evidence"
    assert execution.raw_evidence_path == ""


def test_optional_failure_evidence_redacts_credential_shaped_values() -> None:
    redacted = _redact_sensitive_output("api_key=not-for-output token:also-hidden")

    assert "not-for-output" not in redacted
    assert "also-hidden" not in redacted


def test_content_snapshot_detects_changed_bytes_when_porcelain_is_unchanged(
    tmp_path,
) -> None:
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    before = snapshot_working_tree(root=tmp_path, diff_bytes=b"same status\x00one")
    tracked.write_text("after\n", encoding="utf-8")
    after = snapshot_working_tree(root=tmp_path, diff_bytes=b"same status\x00two")

    assert before != after
