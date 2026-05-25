from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repository_analysis_exclusions import (
    classify_repository_path,
    is_repository_analysis_traversal_parent,
    normalize_repository_path,
)

DEFAULT_MIN_LINES = 500
SECTION_SUFFIXES = {
    "src": (".py",),
    "tests": (".py",),
    "scripts": (".py", ".sh", ".ps1"),
    "wordpress": (".py", ".php", ".js", ".css", ".html", ".json", ".sh", ".ps1"),
}
SECTION_LABELS = {
    "src": "First-party src",
    "tests": "First-party tests",
    "scripts": "First-party scripts",
    "wordpress": "WordPress integration",
}
SECTION_ORDER = ("src", "tests", "scripts", "wordpress")


@dataclass(frozen=True)
class LongFileRecord:
    schema_version: str = field(metadata={"doc": "Long-file record schema version."})
    path: str = field(metadata={"doc": "Repository-relative path."})
    line_count: int = field(metadata={"doc": "Number of physical lines in the file."})


@dataclass(frozen=True)
class LongFileSection:
    schema_version: str = field(metadata={"doc": "Long-file section schema version."})
    section: str = field(metadata={"doc": "Stable first-party section identifier."})
    files: tuple[LongFileRecord, ...] = field(
        metadata={"doc": "Long files in this section, sorted descending by line count."}
    )


@dataclass(frozen=True)
class LongFileScanResult:
    schema_version: str = field(metadata={"doc": "Long-file scan result version."})
    min_lines: int = field(metadata={"doc": "Minimum line-count threshold."})
    scanned_count: int = field(
        metadata={"doc": "Count of source-like first-party files inspected."}
    )
    skipped_count: int = field(
        metadata={"doc": "Count of repository paths pruned by the shared policy."}
    )
    skipped_by_reason: dict[str, int] = field(
        metadata={"doc": "Pruned path counts grouped by stable exclusion reason."}
    )
    sections: tuple[LongFileSection, ...] = field(
        metadata={"doc": "First-party long-file sections."}
    )


def _source_like(path: Path, section: str, suffixes: Iterable[str] | None) -> bool:
    if suffixes is not None:
        return path.suffix.lower() in set(suffixes)
    return path.suffix.lower() in SECTION_SUFFIXES.get(section, ())


def _relative_path(root: Path, path: Path) -> str:
    return normalize_repository_path(path.relative_to(root))


def _line_count(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def collect_long_files(
    *,
    root: Path = ROOT,
    min_lines: int = DEFAULT_MIN_LINES,
    suffixes: Iterable[str] | None = None,
) -> LongFileScanResult:
    resolved_root = root.resolve()
    source_suffixes = tuple(suffix.lower() for suffix in suffixes) if suffixes else None
    scanned_count = 0
    skipped_count = 0
    skipped_by_reason: dict[str, int] = {}
    records_by_section: dict[str, list[LongFileRecord]] = {
        section: [] for section in SECTION_ORDER
    }

    for dirpath, dirnames, filenames in os.walk(resolved_root):
        current_dir = Path(dirpath)
        kept_dirnames: list[str] = []
        for dirname in dirnames:
            child_path = current_dir / dirname
            rel_path = _relative_path(resolved_root, child_path)
            classification = classify_repository_path(rel_path)
            if (
                classification.include
                or classification.reason == "repository root"
                or is_repository_analysis_traversal_parent(rel_path)
            ):
                kept_dirnames.append(dirname)
                continue
            skipped_count += 1
            skipped_by_reason[classification.reason] = (
                skipped_by_reason.get(classification.reason, 0) + 1
            )
        dirnames[:] = kept_dirnames

        for filename in filenames:
            file_path = current_dir / filename
            rel_path = _relative_path(resolved_root, file_path)
            classification = classify_repository_path(rel_path)
            if classification.include and not _source_like(
                file_path, classification.section, source_suffixes
            ):
                continue
            if not classification.include:
                if not _source_like(file_path, classification.section, source_suffixes):
                    continue
                skipped_count += 1
                skipped_by_reason[classification.reason] = (
                    skipped_by_reason.get(classification.reason, 0) + 1
                )
                continue
            try:
                line_count = _line_count(file_path)
            except OSError:
                skipped_count += 1
                skipped_by_reason["unreadable first-party file"] = (
                    skipped_by_reason.get("unreadable first-party file", 0) + 1
                )
                continue
            scanned_count += 1
            if line_count <= min_lines:
                continue
            records_by_section[classification.section].append(
                LongFileRecord(
                    schema_version="1.0",
                    path=rel_path,
                    line_count=line_count,
                )
            )

    sections = tuple(
        LongFileSection(
            schema_version="1.0",
            section=section,
            files=tuple(
                sorted(
                    records_by_section[section],
                    key=lambda item: item.line_count,
                    reverse=True,
                )
            ),
        )
        for section in SECTION_ORDER
    )
    return LongFileScanResult(
        schema_version="1.0",
        min_lines=min_lines,
        scanned_count=scanned_count,
        skipped_count=skipped_count,
        skipped_by_reason=skipped_by_reason,
        sections=sections,
    )


def render_long_file_report(result: LongFileScanResult) -> str:
    lines: list[str] = []
    for section in result.sections:
        label = SECTION_LABELS[section.section]
        lines.append(f"{label} files with more than {result.min_lines} lines:")
        if section.files:
            for item in section.files:
                lines.append(f"{item.line_count:6d}  {item.path}")
        else:
            lines.append("  none")
        lines.append("")
    lines.append(f"Total first-party source-like files scanned: {result.scanned_count}")
    lines.append(f"Skipped files: {result.skipped_count}")
    for reason, count in sorted(result.skipped_by_reason.items()):
        lines.append(f"  - {reason}: {count}")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Report long first-party source files while excluding generated, vendored, "
            "temp, cache, and local reproduction trees."
        )
    )
    parser.add_argument("--root", default=str(ROOT), help="Repository root to scan.")
    parser.add_argument(
        "--min-lines",
        type=int,
        default=DEFAULT_MIN_LINES,
        help="Only report files with more than this many physical lines.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = collect_long_files(root=Path(args.root), min_lines=args.min_lines)
    print(render_long_file_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
