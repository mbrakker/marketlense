from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_BACKLOG = "CONSOLIDATED_TODO.md"
ARCHIVED_BACKLOG_DOCS = ("docs/quality/deep-analysis-x10-plan-2026-04-15.md",)
ACTIVE_BACKLOG_PATTERNS = (
    re.compile(r"^- \*\*Title:\*\* ", re.MULTILINE),
    re.compile(r"^\s*- \[ \] ", re.MULTILINE),
    re.compile(r"^\s*- Acceptance Criteria:", re.MULTILINE),
    re.compile(r"^## Priority Launch Plan$", re.MULTILINE),
)


@dataclass(frozen=True)
class BacklogSourceViolation:
    path: str
    reason: str


@dataclass(frozen=True)
class BacklogIntegritySummary:
    active_register_items: int
    detailed_active_sections: int
    duplicate_ids: int
    missing_detail_sections: int
    orphan_detail_sections: int
    title_mismatches: int


_UNIFIED_REGISTER_HEADING = "## Unified Work Register"
_RECENTLY_CLOSED_HEADING = "## Recently Closed"
_ACTIVE_BACKLOG_HEADING = "## Active Backlog"
_NEXT_LEVEL_TWO_HEADING = re.compile(r"^## (?!#)", re.MULTILINE)
_ACTIVE_REGISTER_ROW = re.compile(
    r"^\|\s*Active\s*\|\s*([A-Z]+\d+)\s*\|\s*([^|]+?)\s*\|",
    re.MULTILINE,
)
_ACTIVE_DETAIL_HEADING = re.compile(r"^####\s+([A-Z]+\d+)\.\s+(.+?)\s*$", re.MULTILINE)
_DETAIL_TITLE = re.compile(r"^- \*\*Title:\*\*\s*(.+?)\s*$", re.MULTILINE)


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def list_tracked_markdown() -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return tuple(
        _normalize(path)
        for path in result.stdout.decode("utf-8").split("\0")
        if path.strip()
    )


def _is_ignored(path: str) -> bool:
    return (
        path in {CANONICAL_BACKLOG, "simplification.md", "x100tasks.md"}
        or path.startswith("tools/")
        or path.startswith("docs/superpowers/plans/")
        or path.startswith("docs/superpowers/specs/")
    )


def _normalize_title(value: str) -> str:
    """Normalize only presentation differences in one canonical backlog title."""

    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return " ".join(normalized.split())


def _section_text(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    body_start = start + len(heading)
    next_heading = _NEXT_LEVEL_TWO_HEADING.search(text, body_start)
    return text[body_start : next_heading.start() if next_heading else len(text)]


def _detail_title(section_text: str, fallback: str) -> str:
    matched = _DETAIL_TITLE.search(section_text)
    return matched.group(1).strip() if matched else fallback.strip()


def validate_canonical_backlog(
    text: str,
) -> tuple[BacklogIntegritySummary, tuple[BacklogSourceViolation, ...]]:
    """Validate active register/detail correspondence in stable backlog Markdown.

    This intentionally understands only the canonical table and `#### ID. title`
    structure. It never treats historical prose or Recently Closed evidence as
    active definitions.
    """

    register_text = _section_text(text, _UNIFIED_REGISTER_HEADING)
    active_backlog_text = _section_text(text, _ACTIVE_BACKLOG_HEADING)
    # The active area can contain the following `## Recently Closed` heading in
    # files authored before the section helper was introduced; keep the boundary
    # explicit for deterministic migration compatibility.
    active_backlog_text = active_backlog_text.split(_RECENTLY_CLOSED_HEADING, 1)[0]
    register_rows = tuple(_ACTIVE_REGISTER_ROW.finditer(register_text))
    detail_headings = tuple(_ACTIVE_DETAIL_HEADING.finditer(active_backlog_text))

    register_by_id: dict[str, list[str]] = {}
    for row in register_rows:
        register_by_id.setdefault(row.group(1), []).append(row.group(2).strip())

    detail_by_id: dict[str, list[str]] = {}
    for index, heading in enumerate(detail_headings):
        section_end = (
            detail_headings[index + 1].start()
            if index + 1 < len(detail_headings)
            else len(active_backlog_text)
        )
        title = _detail_title(
            active_backlog_text[heading.end() : section_end], heading.group(2)
        )
        detail_by_id.setdefault(heading.group(1), []).append(title)

    violations: list[BacklogSourceViolation] = []
    duplicate_register_ids = sorted(
        item_id for item_id, titles in register_by_id.items() if len(titles) > 1
    )
    duplicate_detail_ids = sorted(
        item_id for item_id, titles in detail_by_id.items() if len(titles) > 1
    )
    for item_id in duplicate_register_ids:
        violations.append(
            BacklogSourceViolation(
                path=CANONICAL_BACKLOG,
                reason=f"duplicate active unified-register ID: {item_id}",
            )
        )
    for item_id in duplicate_detail_ids:
        violations.append(
            BacklogSourceViolation(
                path=CANONICAL_BACKLOG,
                reason=f"duplicate detailed active ID: {item_id}",
            )
        )

    register_ids = set(register_by_id)
    detail_ids = set(detail_by_id)
    missing_details = sorted(register_ids - detail_ids)
    orphan_details = sorted(detail_ids - register_ids)
    for item_id in missing_details:
        violations.append(
            BacklogSourceViolation(
                path=CANONICAL_BACKLOG,
                reason=(
                    "active unified-register ID missing detailed section: "
                    f"{item_id}"
                ),
            )
        )
    for item_id in orphan_details:
        violations.append(
            BacklogSourceViolation(
                path=CANONICAL_BACKLOG,
                reason=f"detailed active ID missing unified-register row: {item_id}",
            )
        )

    title_mismatches = 0
    for item_id in sorted(register_ids & detail_ids):
        register_title = register_by_id[item_id][0]
        detail_title = detail_by_id[item_id][0]
        if _normalize_title(register_title) != _normalize_title(detail_title):
            title_mismatches += 1
            violations.append(
                BacklogSourceViolation(
                    path=CANONICAL_BACKLOG,
                    reason=(
                        f"active title mismatch for {item_id}: "
                        f"register={register_title!r}, detail={detail_title!r}"
                    ),
                )
            )

    title_to_ids: dict[str, set[str]] = {}
    for item_id, titles in register_by_id.items():
        title_to_ids.setdefault(_normalize_title(titles[0]), set()).add(item_id)
    for normalized_title, item_ids in sorted(title_to_ids.items()):
        if len(item_ids) > 1:
            violations.append(
                BacklogSourceViolation(
                    path=CANONICAL_BACKLOG,
                    reason=(
                        "same normalized active title under multiple IDs: "
                        f"{normalized_title!r} ({', '.join(sorted(item_ids))})"
                    ),
                )
            )

    summary = BacklogIntegritySummary(
        active_register_items=len(register_rows),
        detailed_active_sections=len(detail_headings),
        duplicate_ids=len(duplicate_register_ids) + len(duplicate_detail_ids),
        missing_detail_sections=len(missing_details),
        orphan_detail_sections=len(orphan_details),
        title_mismatches=title_mismatches,
    )
    return summary, tuple(sorted(violations, key=lambda item: (item.path, item.reason)))


def validate_backlog_sources(
    paths: Iterable[str],
    *,
    root: Path,
) -> tuple[BacklogSourceViolation, ...]:
    violations: list[BacklogSourceViolation] = []
    canonical = root / CANONICAL_BACKLOG
    if not canonical.exists():
        violations.append(
            BacklogSourceViolation(
                path=CANONICAL_BACKLOG,
                reason="canonical backlog file is missing",
            )
        )
    readme = root / "README.md"
    if readme.exists() and CANONICAL_BACKLOG not in readme.read_text(encoding="utf-8"):
        violations.append(
            BacklogSourceViolation(
                path="README.md",
                reason="README does not point contributors to CONSOLIDATED_TODO.md",
            )
        )

    for archived_path in ARCHIVED_BACKLOG_DOCS:
        full_path = root / archived_path
        if not full_path.exists():
            violations.append(
                BacklogSourceViolation(
                    path=archived_path,
                    reason="archived backlog source is missing",
                )
            )
            continue
        header = "\n".join(full_path.read_text(encoding="utf-8").splitlines()[:12])
        if "consolidated into `CONSOLIDATED_TODO.md`" not in header:
            violations.append(
                BacklogSourceViolation(
                    path=archived_path,
                    reason="archived backlog source lacks consolidation notice",
                )
            )

    for raw_path in paths:
        path = _normalize(raw_path)
        if _is_ignored(path):
            continue
        full_path = root / path
        if not full_path.exists():
            continue
        text = full_path.read_text(encoding="utf-8", errors="ignore")
        for pattern in ACTIVE_BACKLOG_PATTERNS:
            if pattern.search(text):
                violations.append(
                    BacklogSourceViolation(
                        path=path,
                        reason=(
                            f"active backlog pattern found outside {CANONICAL_BACKLOG}"
                        ),
                    )
                )
                break
    if canonical.exists():
        _, integrity_violations = validate_canonical_backlog(
            canonical.read_text(encoding="utf-8")
        )
        violations.extend(integrity_violations)
    return tuple(sorted(violations, key=lambda item: (item.path, item.reason)))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enforce CONSOLIDATED_TODO.md as the only active backlog source."
    )
    return parser.parse_args()


def main() -> int:
    _parse_args()
    try:
        violations = validate_backlog_sources(list_tracked_markdown(), root=ROOT)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Backlog source gate failed to run: {exc}")
        return 2
    if not violations:
        summary, _ = validate_canonical_backlog(
            (ROOT / CANONICAL_BACKLOG).read_text(encoding="utf-8")
        )
        print(
            "Backlog source gate passed: "
            f"active_register_items={summary.active_register_items} "
            f"detailed_active_sections={summary.detailed_active_sections} "
            f"duplicate_ids={summary.duplicate_ids} "
            f"missing_detail_sections={summary.missing_detail_sections} "
            f"orphan_detail_sections={summary.orphan_detail_sections} "
            f"title_mismatches={summary.title_mismatches}."
        )
        return 0
    print("Backlog source gate failed:")
    for item in violations:
        print(f"  - {item.path}: {item.reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
