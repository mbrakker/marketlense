from __future__ import annotations

from pathlib import Path

from scripts.ci.check_backlog_source import validate_backlog_sources


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
