"""Run one isolated IAS first-attempt live canary and print its JSON result."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.quality.ias_live_canary_runner import run_ias_first_attempt_canary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=Path("tmp") / "ias-first-attempt-live-canaries",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=(
            Path("tests")
            / "fixtures"
            / "pdf_benchmark"
            / "golden"
            / "IAS - Industry_Pulse_Report_2026_ACIG.pdf"
        ),
    )
    parser.add_argument("--max-duration-seconds", type=int, default=7_200)
    args = parser.parse_args()
    result = run_ias_first_attempt_canary(
        runs_root=args.runs_root,
        source_path=args.source,
        max_duration_seconds=args.max_duration_seconds,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if _passes(result) else 1


def _passes(result: dict[str, object]) -> bool:
    return all(
        (
            bool(result["report_id"]),
            int(result["workflow_attempt_count"]) == 1,
            result["isolated_fresh_state"] is True,
            result["operator_intervention"] is False,
            result["validation"] == "pass",
            result["publication_readiness"] == "pass",
            result["final_state"] == "awaiting_review",
            result["awaiting_review"] is True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
