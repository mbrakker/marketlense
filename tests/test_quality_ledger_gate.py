from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.check_quality_ledger import validate_quality_ledger


def test_quality_ledger_validates_committed_initiatives() -> None:
    ids = validate_quality_ledger(Path("docs/quality/initiative_ledger.yaml"))

    assert "repository-hygiene" in ids
    assert len(ids) >= 5


def test_quality_ledger_rejects_stalled_item_without_replan_or_descope(
    tmp_path: Path,
) -> None:
    agenda_path = tmp_path / "agenda.md"
    agenda_path.write_text("agenda", encoding="utf-8")
    ledger_path = tmp_path / "ledger.yaml"
    ledger_path.write_text(
        f"""
schema_version: "1.0"
review:
  cadence: "monthly"
  owner: "quality"
  agenda_path: "{agenda_path.as_posix()}"
  next_review_date: "2026-05-25"
initiatives:
  - id: "stalled-work"
    title: "Stalled work"
    owner: "quality"
    status: "stalled"
    review_date: "2026-05-25"
    baseline_metric: "baseline"
    current_metric: "current"
    target_metric: "target"
    decision: "continue"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be replanned or descoped"):
        validate_quality_ledger(ledger_path)
