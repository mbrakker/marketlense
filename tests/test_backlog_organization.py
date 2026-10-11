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
PROPOSAL = re.compile(r"^#### ((?:(?:ING|DISC|ACQ|SYS|CODE|CROP|ART|ANA|GRD|VER)-\d{2})|ARCH-[A-I]) —", re.M)
MAPPING = re.compile(r"^\| \[([A-Z][A-Z0-9-]+)\]\([^)]+\) \| \[([APERS]\d+)\]\([^)]+\) \|", re.M)


def test_canonical_register_preserved_and_active_ownership_unique() -> None:
    master = MASTER.read_text(encoding="utf-8")
    original = (ARCHIVE / "CONSOLIDATED_TODO-20261011-preconsolidation.md").read_text(encoding="utf-8")
    rows = REGISTER.findall(master)
    original_rows = REGISTER.findall(original)
    assert rows, "missing canonical work register"
    assert len({task_id for _, task_id in rows}) == len(rows), "duplicate canonical IDs"
    assert rows == original_rows, "documentation migration changed an existing task's status/ID"
    active_ids = {task_id for status, task_id in rows if status == "Active"}
    owners = [item for path in WORKSTREAMS for item in OWNER.findall(path.read_text(encoding="utf-8"))]
    assert len(owners) == len(set(owners)), "same outcome defined in multiple workstreams"
    assert set(owners) == active_ids, "every Active outcome must have exactly one owner spec"


def test_every_proposal_has_one_mapping_and_one_full_specification() -> None:
    content = INDEX.read_text(encoding="utf-8")
    mappings = MAPPING.findall(content)
    assert mappings, "missing technical proposal mapping"
    ids = [task_id for task_id, _ in mappings]
    assert len(ids) == len(set(ids)), "duplicate proposal mappings"
    declared = [
        item for path in WORKSTREAMS
        for item in PROPOSAL.findall(path.read_text(encoding="utf-8"))
    ]
    assert sorted(declared) == sorted(ids), "proposal-index and detailed slices disagree"
    active = {task_id for status, task_id in REGISTER.findall(MASTER.read_text(encoding="utf-8")) if status == "Active"}
    assert all(owner in active for _, owner in mappings), "technical slice has no Active canonical owner"
    for path in WORKSTREAMS:
        text = path.read_text(encoding="utf-8")
        assert text.count("Luna implementation prompt") >= len(OWNER.findall(text)), path


def test_preconsolidation_references_retained() -> None:
    catalogue = (ARCHIVE / "10improvements-20261011-preconsolidation.md").read_text(encoding="utf-8")
    assert len(re.findall(r"^### (?:ING|DISC|ACQ|SYS|CODE|CROP|ART|ANA|GRD|VER)-\d{2} —", catalogue, re.M)) == 100
    assert len(re.findall(r"^### Architecture follow-up [A-I] —", catalogue, re.M)) == 9
    assert "archived original" in (ROOT / "10improvements.md").read_text(encoding="utf-8").lower()


def test_proposal_links_are_local_and_have_explicit_targets() -> None:
    index = INDEX.read_text(encoding="utf-8")
    for technical_id, relative_name in re.findall(
        r"^\| \[([A-Z][A-Z0-9-]+)\]\(([^#)]+)#[^)]+\) \|", index, re.M
    ):
        assert "/" not in relative_name, "proposal links must be relative to docs/backlog"
        destination = INDEX.parent / relative_name
        assert destination in WORKSTREAMS
        text = destination.read_text(encoding="utf-8")
        assert f'<a id="{technical_id.lower()}"></a>' in text
