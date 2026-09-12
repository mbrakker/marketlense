"""Run the frozen representative cohort through one isolated queue attempt each."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.quality.ias_live_canary_runner import (
    run_first_attempt_canary,
    summarize_frozen_cohort_results,
)


def _load_member_paths(manifest_path: Path) -> list[Path]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    members = payload.get("members") if isinstance(payload, dict) else None
    if not isinstance(members, list) or len(members) != 20:
        raise ValueError("Frozen reliability cohort must contain exactly 20 members")
    root = Path(__file__).resolve().parents[2]
    paths = [root / str(item.get("source_path") or "") for item in members]
    if any(not path.is_file() for path in paths):
        raise ValueError("Frozen reliability cohort has a missing source artifact")
    return paths


def run_frozen_reliability_cohort(
    *,
    sources_manifest: Path,
    runs_root: Path,
    max_duration_seconds: int = 7_200,
) -> dict[str, Any]:
    """Freeze and execute all listed members once, retaining every result."""

    paths = _load_member_paths(sources_manifest)
    runs_root.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="frozen-reliability-", dir=runs_root))
    root.joinpath("frozen_cohort.json").write_text(
        sources_manifest.read_text(encoding="utf-8"), encoding="utf-8"
    )
    results = [
        run_first_attempt_canary(
            runs_root=root / "members",
            source_path=path,
            max_duration_seconds=max_duration_seconds,
        )
        for path in paths
    ]
    result = {
        "schema_version": "1.0",
        "cohort_size": len(results),
        "cohort_directory": str(root),
        "reports": results,
        "summary": summarize_frozen_cohort_results(results),
    }
    root.joinpath("cohort_result.json").write_text(
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
    args = parser.parse_args()
    try:
        result = run_frozen_reliability_cohort(
            sources_manifest=args.sources_manifest,
            runs_root=args.runs_root,
            max_duration_seconds=args.max_duration,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"terminal_failure_code": "frozen_cohort_input_invalid"}))
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
