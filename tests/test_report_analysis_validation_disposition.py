from __future__ import annotations

from src.orchestrators.report_analysis_orchestrator import (
    _validation_repair_disposition,
)


def test_failed_validation_without_repair_is_not_marked_not_required() -> None:
    assert _validation_repair_disposition("failed", 0) == "no_actionable_repair"


def test_passed_validation_without_repair_remains_not_required() -> None:
    assert _validation_repair_disposition("succeeded", 0) == "not_required"


def test_repaired_validation_keeps_targeted_repair_disposition() -> None:
    assert _validation_repair_disposition("failed", 1) == "targeted_repair"
