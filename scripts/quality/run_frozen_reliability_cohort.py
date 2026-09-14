"""Run the frozen representative cohort through one isolated queue attempt each."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.quality.ias_live_canary_runner import (
    preflight_frozen_cohort_member,
    run_frozen_cohort_once,
    summarize_frozen_cohort_results,
)


def _load_members(manifest_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    members = payload.get("members") if isinstance(payload, dict) else None
    if not isinstance(members, list) or len(members) != 20:
        raise ValueError("Frozen reliability cohort must contain exactly 20 members")
    root = Path(__file__).resolve().parents[2]
    required = {
        "source_path",
        "content_md5",
        "source_domain",
        "report_name",
        "landing_page_url",
        "source_page_url",
        "publisher_name",
        "downloaded_at_utc",
    }
    if any(not isinstance(item, dict) or required - set(item) for item in members):
        raise ValueError("Frozen reliability cohort has incomplete source provenance")
    if any(not str(item[key]).strip() for item in members for key in required):
        raise ValueError("Frozen reliability cohort has blank source provenance")
    if any(
        len(str(item["content_md5"])) != 32
        or any(
            character not in "0123456789abcdefABCDEF"
            for character in str(item["content_md5"])
        )
        for item in members
    ):
        raise ValueError("Frozen reliability cohort has an invalid source checksum")
    paths = [root / str(item["source_path"]) for item in members]
    if any(not path.is_file() for path in paths):
        raise ValueError("Frozen reliability cohort has a missing source artifact")
    if any(
        hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()
        != str(item["content_md5"]).lower()
        for path, item in zip(paths, members, strict=True)
    ):
        raise ValueError("Frozen reliability cohort source checksum changed")
    return [
        {**item, "resolved_source_path": str(path)}
        for item, path in zip(members, paths, strict=True)
    ]


def run_frozen_reliability_cohort(
    *,
    sources_manifest: Path,
    runs_root: Path,
    max_duration_seconds: int = 7_200,
    run_cohort_once: Callable[..., dict[str, Any]] = run_frozen_cohort_once,
) -> dict[str, Any]:
    """Freeze and execute all listed members once, retaining every result."""

    members = _load_members(sources_manifest)
    runs_root.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="frozen-reliability-", dir=runs_root))
    root.joinpath("frozen_cohort.json").write_text(
        sources_manifest.read_text(encoding="utf-8"), encoding="utf-8"
    )
    execution = run_cohort_once(
        runs_root=root / "members",
        sources=members,
        max_duration_seconds=max_duration_seconds,
    )
    results = list(execution["reports"])
    if len(results) != len(members):
        raise RuntimeError("Frozen reliability cohort execution omitted a member")
    git_sha = str(execution.get("git_sha") or "")
    if len(git_sha) != 40 or any(
        character not in "0123456789abcdef" for character in git_sha
    ):
        raise RuntimeError("Frozen reliability cohort execution lacks a clean git SHA")
    result = {
        "schema_version": "1.0",
        "git_sha": git_sha,
        "cohort_size": len(results),
        "cohort_directory": str(root),
        "production_run_directory": str(execution.get("run_directory") or ""),
        "cohort_metrics": dict(execution.get("cohort_metrics") or {}),
        "reports": results,
        "summary": summarize_frozen_cohort_results(
            results, cohort_metrics=execution.get("cohort_metrics")
        ),
    }
    root.joinpath("cohort_result.json").write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    return result


def preflight_frozen_reliability_cohort(
    *, sources_manifest: Path, runs_root: Path
) -> dict[str, Any]:
    """Validate frozen provenance and production admission before live work."""
    members = _load_members(sources_manifest)
    runs_root.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="frozen-reliability-preflight-", dir=runs_root))
    results = [
        preflight_frozen_cohort_member(
            runs_root=root / "members",
            source_path=Path(str(member["resolved_source_path"])),
            source_metadata=member,
        )
        for member in members
    ]
    result = {
        "schema_version": "1.0",
        "cohort_size": len(results),
        "admitted_count": sum(
            item["admission_outcome"] == "admitted" for item in results
        ),
        "cohort_admission_rate": sum(
            item["admission_outcome"] == "admitted" for item in results
        )
        / len(results),
        "cohort_directory": str(root),
        "reports": results,
    }
    root.joinpath("cohort_preflight.json").write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sources-manifest",
        type=Path,
        default=Path(__file__).with_name("frozen_reliability_cohort_20.json"),
    )
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--max-duration", type=int, default=7_200)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    try:
        result = (
            preflight_frozen_reliability_cohort(
                sources_manifest=args.sources_manifest, runs_root=args.runs_root
            )
            if args.preflight_only
            else run_frozen_reliability_cohort(
                sources_manifest=args.sources_manifest,
                runs_root=args.runs_root,
                max_duration_seconds=args.max_duration,
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"terminal_failure_code": "frozen_cohort_input_invalid"}))
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
