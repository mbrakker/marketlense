from __future__ import annotations

from pathlib import Path

from scripts.ci.check_backlog_source import (
    validate_backlog_sources,
    validate_canonical_backlog,
)


def _canonical_backlog(*, register: str, details: str, recent: str = "") -> str:
    return "\n".join(
        (
            "# Consolidated TODO",
            "",
            "## Unified Work Register",
            "",
            "| Status | ID | Work item | Current outcome / merge target |",
            "| --- | --- | --- | --- |",
            register,
            "",
            "## Active Backlog",
            "",
            details,
            "",
            "## Recently Closed",
            "",
            recent,
        )
    )


def test_backlog_source_gate_accepts_current_repository() -> None:
    violations = validate_backlog_sources(
        (
            "README.md",
            "CONSOLIDATED_TODO.md",
            "docs/quality/deep-analysis-x10-plan-2026-04-15.md",
        ),
        root=Path("."),
    )

    assert violations == ()


def test_backlog_source_gate_rejects_active_backlog_markers_outside_canonical(
    tmp_path: Path,
) -> None:
    (tmp_path / "CONSOLIDATED_TODO.md").write_text(
        "# Consolidated TODO\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("See CONSOLIDATED_TODO.md\n", encoding="utf-8")
    archived = tmp_path / "docs" / "quality" / "deep-analysis-x10-plan-2026-04-15.md"
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_text(
        "The active items were consolidated into `CONSOLIDATED_TODO.md`.\n",
        encoding="utf-8",
    )
    rogue = tmp_path / "docs" / "quality" / "new_backlog.md"
    rogue.write_text(
        "- **Title:** A second active backlog item [Impact: 1/5, Effort: 1/5]\n",
        encoding="utf-8",
    )

    violations = validate_backlog_sources(
        (
            "README.md",
            "CONSOLIDATED_TODO.md",
            "docs/quality/deep-analysis-x10-plan-2026-04-15.md",
            "docs/quality/new_backlog.md",
        ),
        root=tmp_path,
    )

    assert [item.path for item in violations] == ["docs/quality/new_backlog.md"]


def test_backlog_source_gate_ignores_intake_and_execution_plan_documents(
    tmp_path: Path,
) -> None:
    (tmp_path / "CONSOLIDATED_TODO.md").write_text(
        "# Consolidated TODO\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("See CONSOLIDATED_TODO.md\n", encoding="utf-8")
    archived = tmp_path / "docs" / "quality" / "deep-analysis-x10-plan-2026-04-15.md"
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_text(
        "The active items were consolidated into `CONSOLIDATED_TODO.md`.\n",
        encoding="utf-8",
    )
    simplification = tmp_path / "simplification.md"
    simplification.write_text("- **Title:** Intake item\n", encoding="utf-8")
    x100tasks = tmp_path / "x100tasks.md"
    x100tasks.write_text("- **Title:** x100 intake item\n", encoding="utf-8")
    plan = tmp_path / "docs" / "superpowers" / "plans" / "implementation.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("- [ ] Execute implementation step\n", encoding="utf-8")

    violations = validate_backlog_sources(
        (
            "README.md",
            "CONSOLIDATED_TODO.md",
            "docs/quality/deep-analysis-x10-plan-2026-04-15.md",
            "simplification.md",
            "x100tasks.md",
            "docs/superpowers/plans/implementation.md",
        ),
        root=tmp_path,
    )

    assert violations == ()


def test_canonical_backlog_accepts_matching_active_register_and_detail() -> None:
    summary, violations = validate_canonical_backlog(
        _canonical_backlog(
            register="| Active | A10 | Budget deferred recovery | bounded outcome |",
            details=(
                "#### A10. Budget deferred recovery\n\n"
                "- **Title:** Budget deferred recovery"
            ),
        )
    )

    assert summary.active_register_items == 1
    assert summary.detailed_active_sections == 1
    assert violations == ()


def test_canonical_backlog_accepts_compact_active_detail_table() -> None:
    summary, violations = validate_canonical_backlog(
        _canonical_backlog(
            register=(
                "| Active | A10 | Budget deferred recovery | bounded outcome |\n"
                "| Active | A11 | Recurring failure review | bounded outcome |"
            ),
            details=(
                "### Remaining Active Outcomes\n\n"
                "| ID | Current baseline | Target / completion proof |\n"
                "| --- | --- | --- |\n"
                "| A10 | Recovery records exist. | Prove bounded replay. |\n"
                "| A11 | Failure groups exist. | Prove operator review. |"
            ),
        )
    )

    assert summary.active_register_items == 2
    assert summary.detailed_active_sections == 2
    assert violations == ()


def test_canonical_backlog_accepts_level_three_active_detail_heading() -> None:
    summary, violations = validate_canonical_backlog(
        _canonical_backlog(
            register="| Active | A10 | Budget deferred recovery | bounded outcome |",
            details=(
                "### A10. Budget deferred recovery\n\n"
                "- **Title:** Budget deferred recovery"
            ),
        )
    )

    assert summary.active_register_items == 1
    assert summary.detailed_active_sections == 1
    assert violations == ()


def test_canonical_backlog_reports_missing_detail_section() -> None:
    _, violations = validate_canonical_backlog(
        _canonical_backlog(
            register="| Active | A10 | Budget deferred recovery | bounded outcome |",
            details="",
        )
    )

    assert [item.reason for item in violations] == [
        "active unified-register ID missing detailed section: A10"
    ]


def test_canonical_backlog_reports_orphan_detail_and_duplicate_ids() -> None:
    _, violations = validate_canonical_backlog(
        _canonical_backlog(
            register=(
                "| Active | A10 | Budget deferred recovery | bounded outcome |\n"
                "| Active | A10 | Budget deferred recovery | bounded outcome |"
            ),
            details=(
                "#### A10. Budget deferred recovery\n\n"
                "- **Title:** Budget deferred recovery\n\n"
                "#### A11. Other recovery\n\n"
                "- **Title:** Other recovery\n\n"
                "#### A11. Other recovery\n\n"
                "- **Title:** Other recovery"
            ),
        )
    )

    assert [item.reason for item in violations] == [
        "detailed active ID missing unified-register row: A11",
        "duplicate active unified-register ID: A10",
        "duplicate detailed active ID: A11",
    ]


def test_canonical_backlog_rejects_title_drift_and_shared_title() -> None:
    _, violations = validate_canonical_backlog(
        _canonical_backlog(
            register=(
                "| Active | A10 | Budget deferred recovery! | bounded outcome |\n"
                "| Active | A11 | Budget deferred recovery | bounded outcome |"
            ),
            details=(
                "#### A10. Different title\n\n"
                "- **Title:** Different title\n\n"
                "#### A11. Budget deferred recovery\n\n"
                "- **Title:** Budget deferred recovery"
            ),
        )
    )

    assert [item.reason for item in violations] == [
        (
            "active title mismatch for A10: register='Budget deferred recovery!', "
            "detail='Different title'"
        ),
        (
            "same normalized active title under multiple IDs: "
            "'budget deferred recovery' (A10, A11)"
        ),
    ]


def test_canonical_backlog_ignores_closed_and_historical_identifiers() -> None:
    _, violations = validate_canonical_backlog(
        _canonical_backlog(
            register=(
                "| Active | A10 | Budget deferred recovery | bounded outcome |\n"
                "| Closed | A13 | Former recovery title | historical outcome |"
            ),
            details=(
                "#### A10. Budget deferred recovery\n\n"
                "- **Title:** Budget deferred recovery"
            ),
            recent="- **A13 — Former recovery title:** historical evidence.",
        )
    )

    assert violations == ()
