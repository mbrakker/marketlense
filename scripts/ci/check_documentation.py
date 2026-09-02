"""Validate first-party Markdown links, ownership metadata, and README hygiene."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

README_PATH = Path("README.md")
README_MAX_LINES = 600
FIRST_PARTY_EXCLUDED_DIRECTORIES = frozenset(
    {
        ".github",
        ".git",
        ".venv",
        "cache",
        "logs",
        "out",
        "output",
        "state",
        "temp",
        "tools",
    }
)
RUNTIME_ARTIFACT_LINK_DIRECTORIES = frozenset(
    {"cache", "logs", "out", "output", "state", "temp"}
)
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
CANONICAL_TOPIC = re.compile(r"^> \*\*Canonical topic:\*\* (.+?)\s*$", re.MULTILINE)
REQUIRED_CANONICAL_DOCUMENTS = (
    Path("docs/product/overview.md"),
    Path("docs/product/report-lifecycle.md"),
    Path("docs/product/editorial-output.md"),
    Path("docs/architecture/overview.md"),
    Path("docs/architecture/repository-structure.md"),
    Path("docs/architecture/data-and-artifact-model.md"),
    Path("docs/architecture/workflow-control.md"),
    Path("docs/architecture/external-system-boundaries.md"),
    Path("docs/workflows/report-processing.md"),
    Path("docs/ops/local-development.md"),
    Path("docs/quality/testing.md"),
    Path("docs/quality/release-gates.md"),
    Path("README_WORDPRESS.md"),
)
README_PROHIBITED_PATTERNS = (
    (re.compile(r"\b20\d{2}-\d{2}-\d{2}\b"), "dated implementation detail"),
    (re.compile(r"\blive verification\b", re.IGNORECASE), "live verification ledger"),
    (
        re.compile(r"\b\d+\s+(?:tests?|test cases?)\b", re.IGNORECASE),
        "test-count narrative",
    ),
    (
        re.compile(
            r"\b(?:benchmark|performance)\s+(?:result|results|output|measurement)\b",
            re.IGNORECASE,
        ),
        "benchmark result narrative",
    ),
    (re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+", re.MULTILINE), "backlog item"),
    (
        re.compile(r"^#{1,6}\s+Active Backlog\b", re.MULTILINE | re.IGNORECASE),
        "active backlog heading",
    ),
)


@dataclass(frozen=True)
class DocumentationViolation:
    """A deterministic documentation validation failure."""

    path: Path
    reason: str


def _first_party_markdown(root: Path) -> tuple[Path, ...]:
    """List tracked and untracked Markdown without scanning runtime trees."""
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            "*.md",
        ],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    paths: list[Path] = []
    for raw_path in result.stdout.decode("utf-8").split("\0"):
        if not raw_path:
            continue
        relative = Path(raw_path)
        if any(part in FIRST_PARTY_EXCLUDED_DIRECTORIES for part in relative.parts):
            continue
        paths.append(relative)
    return tuple(sorted(paths))


def _stale_generated_documents(root: Path) -> tuple[Path, ...]:
    from scripts.docs.generate_references import stale_generated_documents

    return stale_generated_documents(root)


def _heading_slug(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[`*_~]", "", normalized)
    normalized = re.sub(r"[^\w\s-]", "", normalized)
    return re.sub(r"[\s-]+", "-", normalized).strip("-")


def _heading_ids(path: Path) -> set[str]:
    headings: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            headings.add(_heading_slug(match.group(1)))
    return headings


def _link_target(raw_target: str) -> tuple[str, str]:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    target = target.split(maxsplit=1)[0]
    decoded = unquote(target)
    if "#" not in decoded:
        return decoded, ""
    path, anchor = decoded.split("#", maxsplit=1)
    return path, anchor


def _is_external_target(target: str) -> bool:
    normalized = target.lower()
    return normalized.startswith(("http://", "https://", "mailto:", "tel:"))


def _is_ignored_runtime_artifact(destination: Path, root: Path) -> bool:
    try:
        relative = destination.relative_to(root)
    except ValueError:
        return False
    return any(part in RUNTIME_ARTIFACT_LINK_DIRECTORIES for part in relative.parts)


def validate_markdown_links(root: Path) -> tuple[DocumentationViolation, ...]:
    """Validate first-party relative Markdown links and known heading anchors."""
    violations: list[DocumentationViolation] = []
    anchor_cache: dict[Path, set[str]] = {}
    for relative_path in _first_party_markdown(root):
        source = root / relative_path
        for raw_target in MARKDOWN_LINK.findall(source.read_text(encoding="utf-8")):
            target, anchor = _link_target(raw_target)
            if not target and not anchor:
                continue
            if _is_external_target(target) or target.startswith("/"):
                continue
            destination = source if not target else (source.parent / target).resolve()
            if not destination.exists():
                if _is_ignored_runtime_artifact(destination, root):
                    continue
                violations.append(
                    DocumentationViolation(
                        relative_path, f"missing link target: {raw_target}"
                    )
                )
                continue
            if anchor:
                headings = anchor_cache.setdefault(
                    destination, _heading_ids(destination)
                )
                if anchor not in headings:
                    violations.append(
                        DocumentationViolation(
                            relative_path,
                            f"missing heading anchor '{anchor}' in {raw_target}",
                        )
                    )
    return tuple(violations)


def validate_canonical_ownership(root: Path) -> tuple[DocumentationViolation, ...]:
    """Require stable ownership metadata and reject duplicated canonical topics."""
    violations: list[DocumentationViolation] = []
    owners: dict[str, Path] = {}
    for relative_path in REQUIRED_CANONICAL_DOCUMENTS:
        path = root / relative_path
        if not path.exists():
            violations.append(
                DocumentationViolation(relative_path, "canonical document is missing")
            )
            continue
        match = CANONICAL_TOPIC.search(path.read_text(encoding="utf-8"))
        if match is None:
            violations.append(
                DocumentationViolation(
                    relative_path, "canonical topic metadata is missing"
                )
            )
            continue
        topic = match.group(1).strip().lower()
        existing = owners.get(topic)
        if existing is not None:
            reason = (
                f"duplicate canonical topic '{topic}' also owned by "
                f"{existing.as_posix()}"
            )
            violations.append(
                DocumentationViolation(
                    relative_path,
                    reason,
                )
            )
        owners[topic] = relative_path
    return tuple(violations)


def validate_readme_hygiene(root: Path) -> tuple[DocumentationViolation, ...]:
    """Keep the root README an orientation document instead of a change ledger."""
    path = root / README_PATH
    if not path.exists():
        return (DocumentationViolation(README_PATH, "README is missing"),)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    violations: list[DocumentationViolation] = []
    if len(lines) > README_MAX_LINES:
        violations.append(
            DocumentationViolation(
                README_PATH,
                f"README has {len(lines)} lines; maximum is {README_MAX_LINES}",
            )
        )
    for pattern, label in README_PROHIBITED_PATTERNS:
        if pattern.search(text):
            violations.append(DocumentationViolation(README_PATH, f"contains {label}"))
    if "CONSOLIDATED_TODO.md" not in text:
        violations.append(
            DocumentationViolation(README_PATH, "does not link the canonical backlog")
        )
    return tuple(violations)


def validate_documentation(
    root: Path, *, check_generated: bool
) -> tuple[DocumentationViolation, ...]:
    """Run all local documentation validation checks."""
    violations = [
        *validate_markdown_links(root),
        *validate_canonical_ownership(root),
        *validate_readme_hygiene(root),
    ]
    if check_generated:
        violations.extend(
            DocumentationViolation(path, "generated reference is stale or missing")
            for path in _stale_generated_documents(root)
        )
    return tuple(violations)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate MarketLense documentation links, ownership, and hygiene."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--check-generated",
        action="store_true",
        help="Fail when CLI/configuration/capability references are stale.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    violations = validate_documentation(
        args.root.resolve(), check_generated=args.check_generated
    )
    if not violations:
        print("Documentation checks passed.")
        return 0
    print("Documentation checks failed:")
    for violation in violations:
        print(f"  - {violation.path.as_posix()}: {violation.reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
