"""Structural integrity checks for the canonical backlog and its detailed slices."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "CONSOLIDATED_TODO.md"
WORKSTREAMS = (
    ROOT / "docs/backlog/A-autonomy.md",
    ROOT / "docs/backlog/P-publication.md",
    ROOT / "docs/backlog/E-evidence.md",
    ROOT / "docs/backlog/R-engineering.md",
    ROOT / "docs/backlog/S-simplification.md",
)
INDEX = ROOT / "docs/backlog/proposal-index.md"
ARCHIVE = ROOT / "docs/backlog/archive"
REGISTER = re.compile(r"^\| (Active|Closed|Deferred|Excluded) \| ([A-Z]\d+) \|", re.M)
OWNER = re.compile(r"^## ([APERS]\d+)\. ", re.M)
ACTIVE_OWNER_STATUS = re.compile(r"^\*\*Canonical status:\*\* Active\b", re.M)
PROPOSAL = re.compile(
    r"^#### ((?:(?:ING|DISC|ACQ|SYS|CODE|CROP|ART|ANA|GRD|VER|"
    r"PATH)-\d{2})|ARCH-[A-I]) —",
    re.M,
)
MAPPING = re.compile(
    r"^\| \[([A-Z][A-Z0-9-]+)\]\([^)]+\) \| \[([APERS]\d+)\]\([^)]+\) \|", re.M
)


def test_canonical_register_preserved_and_active_ownership_unique() -> None:
    master = MASTER.read_text(encoding="utf-8")
    original = (ARCHIVE / "CONSOLIDATED_TODO-20261011-preconsolidation.md").read_text(
        encoding="utf-8"
    )
    rows = REGISTER.findall(master)
    original_rows = REGISTER.findall(original)
    assert rows, "missing canonical work register"
    assert len({task_id for _, task_id in rows}) == len(rows), "duplicate canonical IDs"
    expected_historic_rows = [
        ("Closed", "R6") if row == ("Active", "R6") else row for row in original_rows
    ]
    remaining = iter(rows)
    for historic_row in expected_historic_rows:
        assert any(row == historic_row for row in remaining), (
            "historic canonical task statuses/IDs or ordering changed"
        )
    assert rows.count(("Closed", "R6")) == 1
    assert rows.count(("Deferred", "D13")) == 1
    active_ids = {task_id for status, task_id in rows if status == "Active"}
    active_owners: list[str] = []
    for path in WORKSTREAMS:
        text = path.read_text(encoding="utf-8")
        headings = list(OWNER.finditer(text))
        for index, heading in enumerate(headings):
            section_end = (
                headings[index + 1].start() if index + 1 < len(headings) else len(text)
            )
            section = text[heading.start() : section_end]
            if ACTIVE_OWNER_STATUS.search(section):
                active_owners.append(heading.group(1))
    assert len(active_owners) == len(set(active_owners)), (
        "same Active outcome defined in multiple workstreams"
    )
    assert set(active_owners) == active_ids, (
        "every Active outcome must have exactly one owner spec"
    )
    assert (
        "## R6. Review bounded-log reduction telemetry and remediate recurring callers"
        in (WORKSTREAMS[3].read_text(encoding="utf-8"))
    )
    assert "Canonical status:** Closed in" in WORKSTREAMS[3].read_text(encoding="utf-8")


def test_every_proposal_has_one_mapping_and_one_full_specification() -> None:
    content = INDEX.read_text(encoding="utf-8")
    mappings = MAPPING.findall(content)
    assert mappings, "missing technical proposal mapping"
    ids = [task_id for task_id, _ in mappings]
    assert len(ids) == len(set(ids)), "duplicate proposal mappings"
    declared = [
        item
        for path in WORKSTREAMS
        for item in PROPOSAL.findall(path.read_text(encoding="utf-8"))
    ]
    assert sorted(declared) == sorted(ids), (
        "proposal-index and detailed slices disagree"
    )
    active = {
        task_id
        for status, task_id in REGISTER.findall(MASTER.read_text(encoding="utf-8"))
        if status == "Active"
    }
    assert all(owner in active for _, owner in mappings), (
        "technical slice has no Active canonical owner"
    )
    for path in WORKSTREAMS:
        text = path.read_text(encoding="utf-8")
        assert text.count("Luna implementation prompt") >= len(OWNER.findall(text)), (
            path
        )


def test_deferred_responses_migration_has_one_canonical_owner_spec() -> None:
    master = MASTER.read_text(encoding="utf-8")
    engineering = (ROOT / "docs/backlog/R-engineering.md").read_text(encoding="utf-8")
    assert (
        "[Evaluate direct OpenAI Responses migration]"
        "(docs/backlog/R-engineering.md#deferred-initiative-d13-evaluate-direct-openai-responses-migration)"
        in master
    )
    assert engineering.count('<a id="d13-openai-responses-migration"></a>') == 1
    assert "### Luna implementation prompt — D13" in engineering
    assert "## D13." not in engineering  # remains deferred; not an active owner


def test_preconsolidation_references_retained() -> None:
    catalogue = (ARCHIVE / "10improvements-20261011-preconsolidation.md").read_text(
        encoding="utf-8"
    )
    assert (
        len(
            re.findall(
                r"^### (?:ING|DISC|ACQ|SYS|CODE|CROP|ART|ANA|GRD|VER)-\d{2} —",
                catalogue,
                re.M,
            )
        )
        == 100
    )
    assert len(re.findall(r"^### Architecture follow-up [A-I] —", catalogue, re.M)) == 9
    assert (
        "archived original"
        in (ROOT / "10improvements.md").read_text(encoding="utf-8").lower()
    )


def test_proposal_links_resolve_to_real_section_headings() -> None:
    index = INDEX.read_text(encoding="utf-8")
    mappings = re.findall(
        r"^\| \[([A-Z][A-Z0-9-]+)\]\(([^#)]+)#([a-z0-9-]+)\) \|",
        index,
        re.M,
    )
    assert len(mappings) == 115
    for technical_id, relative_name, anchor in mappings:
        assert "/" not in relative_name
        destination = INDEX.parent / relative_name
        assert destination in WORKSTREAMS
        sections = re.findall(
            r"^#### ([A-Z][A-Z0-9-]+) — ([^\n]+)$",
            destination.read_text(encoding="utf-8"),
            re.M,
        )
        headings = dict(sections)
        assert technical_id in headings
        display_title = technical_id + " — " + headings[technical_id]
        expected = re.sub(
            r"[\s-]+",
            "-",
            re.sub(r"[^\w\s-]", "", display_title.lower()),
        ).strip("-")
        assert anchor == expected


def test_master_remains_compatible_with_existing_backlog_validator() -> None:
    from scripts.ci.check_backlog_source import validate_canonical_backlog

    summary, violations = validate_canonical_backlog(MASTER.read_text(encoding="utf-8"))
    assert not violations, violations
    assert summary.active_register_items == 33
    assert summary.detailed_active_sections == 33


def test_migrated_quality_links_are_relative_to_workstream() -> None:
    for path in WORKSTREAMS:
        assert "](docs/quality/" not in path.read_text(encoding="utf-8"), path
