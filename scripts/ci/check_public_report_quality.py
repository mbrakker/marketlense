from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quality.public_advisory_render_benchmark import (
    build_public_advisory_render_benchmark,
)


def retained_artifact_paths(root: Path) -> list[str]:
    return [str(path) for path in sorted(root.glob("*/report_analysis/artifacts.json"))]


def run_public_report_quality_gate(
    *,
    artifact_root: str,
    output_dir: str,
    output_json: str,
    minimum_reports: int,
) -> int:
    root = Path(artifact_root).resolve()
    artifact_paths = retained_artifact_paths(root)
    if len(artifact_paths) < max(1, minimum_reports):
        raise SystemExit(
            "public_report_quality_corpus_insufficient: "
            f"found={len(artifact_paths)} minimum={max(1, minimum_reports)}"
        )
    report = build_public_advisory_render_benchmark(
        artifact_paths=artifact_paths,
        output_dir=output_dir,
    )
    payload = asdict(report)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 1 if report.remediation_targets else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate retained public-report rendering for identifier leakage."
    )
    parser.add_argument(
        "--artifact-root",
        default="tests/fixtures/docpacks/golden",
        help="Retained report-artifact corpus root.",
    )
    parser.add_argument("--output-dir", default="out/public_report_quality_ci")
    parser.add_argument("--output-json", default="out/public_report_quality_ci.json")
    parser.add_argument("--minimum-reports", type=int, default=1)
    args = parser.parse_args()

    return run_public_report_quality_gate(
        artifact_root=args.artifact_root,
        output_dir=args.output_dir,
        output_json=args.output_json,
        minimum_reports=args.minimum_reports,
    )


if __name__ == "__main__":
    raise SystemExit(main())
