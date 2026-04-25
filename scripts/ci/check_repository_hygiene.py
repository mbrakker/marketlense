from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[2]

RUNTIME_DIR_NAMES = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "cache",
    "htmlcov",
    "logs",
    "out",
    "state",
}
RUNTIME_FILE_NAMES = {
    ".coverage",
    "coverage.xml",
    "mutation_results.json",
    "google_oauth_client.json",
    "google_oauth_token.json",
    "sa.json",
}
LOCAL_SECRET_NAMES = {".env"}
GENERATED_SUFFIXES = {".log", ".tmp", ".bak", ".pyc", ".pyo"}
SECRET_KEYWORDS = ("secret", "token", "credential", "credentials", "oauth")
MAX_GENERATED_FILE_BYTES = 2_000_000


@dataclass(frozen=True)
class HygieneAllowlistEntry:
    pattern: str
    owner: str
    reason: str
    max_size_bytes: int
    expires_on: date


@dataclass(frozen=True)
class HygieneViolation:
    path: str
    reason: str
    size_bytes: int


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def load_allowlist(path: Path) -> tuple[HygieneAllowlistEntry, ...]:
    if not path.exists():
        return tuple()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = payload.get("allowlist", [])
    if not isinstance(entries, list):
        raise ValueError("repository hygiene allowlist must contain an allowlist list")
    parsed: list[HygieneAllowlistEntry] = []
    for index, item in enumerate(entries, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"allowlist entry {index} must be a mapping")
        missing = [
            key
            for key in ("pattern", "owner", "reason", "max_size_bytes", "expires_on")
            if not item.get(key)
        ]
        if missing:
            raise ValueError(
                f"allowlist entry {index} missing required fields: {', '.join(missing)}"
            )
        expires_on = date.fromisoformat(str(item["expires_on"]))
        parsed.append(
            HygieneAllowlistEntry(
                pattern=_normalize(str(item["pattern"])),
                owner=str(item["owner"]),
                reason=str(item["reason"]),
                max_size_bytes=int(item["max_size_bytes"]),
                expires_on=expires_on,
            )
        )
    return tuple(parsed)


def list_tracked_files() -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
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


def classify_path(path: str, *, size_bytes: int) -> str | None:
    normalized = _normalize(path)
    parts = normalized.split("/")
    name = parts[-1]
    lower_name = name.lower()
    lower_path = normalized.lower()

    if any(part.startswith("tmp_") for part in parts):
        return "tracked temporary runtime artifact"
    if any(part in RUNTIME_DIR_NAMES for part in parts[:-1]):
        return "tracked runtime/cache/output artifact"
    if lower_name in RUNTIME_FILE_NAMES or lower_name in LOCAL_SECRET_NAMES:
        return "tracked local runtime, credential, or coverage file"
    if Path(lower_name).suffix in GENERATED_SUFFIXES:
        return "tracked generated log/temp/cache file"
    if any(keyword in lower_name for keyword in SECRET_KEYWORDS) and Path(
        lower_name
    ).suffix in {".json", ".yaml", ".yml", ".txt", ".env"}:
        return "tracked credential or token-like file"
    if size_bytes > MAX_GENERATED_FILE_BYTES and not lower_path.startswith(
        ("templates/", "docs/", "tests/fixtures/")
    ):
        return "tracked oversized generated-looking file"
    return None


def _allowlist_match(
    path: str,
    *,
    size_bytes: int,
    allowlist: Iterable[HygieneAllowlistEntry],
    today: date,
) -> HygieneAllowlistEntry | None:
    for entry in allowlist:
        if not fnmatch.fnmatch(path, entry.pattern):
            continue
        if today > entry.expires_on:
            continue
        if size_bytes > entry.max_size_bytes:
            continue
        return entry
    return None


def scan_tracked_paths(
    paths: Iterable[str],
    *,
    root: Path,
    allowlist: Iterable[HygieneAllowlistEntry] = (),
    today: date | None = None,
) -> tuple[HygieneViolation, ...]:
    current_date = today or date.today()
    violations: list[HygieneViolation] = []
    for raw_path in paths:
        path = _normalize(raw_path)
        file_path = root / path
        size_bytes = file_path.stat().st_size if file_path.exists() else 0
        reason = classify_path(path, size_bytes=size_bytes)
        if reason is None:
            continue
        if _allowlist_match(
            path,
            size_bytes=size_bytes,
            allowlist=allowlist,
            today=current_date,
        ):
            continue
        violations.append(
            HygieneViolation(path=path, reason=reason, size_bytes=size_bytes)
        )
    return tuple(violations)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reject tracked runtime artifacts, local credentials, and generated outputs."
    )
    parser.add_argument(
        "--allowlist",
        default="docs/quality/repository_hygiene_allowlist.yaml",
        help="YAML allowlist path with owner, reason, max size, and expiry per entry.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        allowlist = load_allowlist(ROOT / args.allowlist)
        violations = scan_tracked_paths(
            list_tracked_files(),
            root=ROOT,
            allowlist=allowlist,
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Repository hygiene gate failed to run: {exc}")
        return 2

    if not violations:
        print("Repository hygiene gate passed.")
        return 0

    print("Repository hygiene gate failed:")
    for item in violations:
        print(f"  - {item.path}: {item.reason} ({item.size_bytes} bytes)")
    print(
        "\nMove intentional fixtures under tests/fixtures or add a time-bounded "
        "allowlist entry with owner, reason, max_size_bytes, and expires_on."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
