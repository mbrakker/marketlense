from __future__ import annotations

from scripts.quality.agent_completion_gate import (
    Check,
    CheckExecution,
    build_completion_report,
    classify_changes,
    run_selected_checks,
    select_checks,
)


def test_classifies_service_change_as_high_risk_and_escalates() -> None:
    changed_files = ("src/services/file_service.py",)

    classification = classify_changes(changed_files)
    checks = select_checks(classification, changed_files)

    assert classification.full_gate_required is True
    assert "service_boundary" in classification.subsystems
    assert checks[-1].command == ("python", "scripts/ci/run_quality_gate.py")


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
        executions=(CheckExecution(check=check, returncode=1, elapsed_ms=12),),
        working_tree_unchanged=True,
    )

    assert report["result"] == "FAIL"
    assert report["failures"] == ["focused_pytest failed with exit code 1"]
    assert report["tests_run"][0]["returncode"] == 1


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
