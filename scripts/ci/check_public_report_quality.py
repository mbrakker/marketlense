from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quality.public_advisory_render_benchmark import (  # noqa: E402
    PublicAdvisoryRenderBenchmarkReport,
    PublicAdvisoryRenderBenchmarkRow,
    build_public_advisory_render_benchmark,
    compare_public_advisory_benchmark,
)


def retained_artifact_paths(root: Path) -> list[str]:
    return [str(path) for path in sorted(root.glob("*/report_analysis/artifacts.json"))]


def run_public_report_quality_gate(
    *,
    artifact_root: str,
    output_dir: str,
    output_json: str,
    minimum_reports: int,
    baseline_json: str = "docs/quality/public_editorial_quality_baseline.json",
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
    baseline_path = Path(baseline_json).resolve()
    if not baseline_path.is_file():
        raise SystemExit(
            f"public_report_quality_baseline_missing: path={baseline_path}"
        )
    baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_payload.pop("comparison", None)
    baseline = PublicAdvisoryRenderBenchmarkReport(
        **{
            **baseline_payload,
            "screenshot_paths": tuple(baseline_payload.get("screenshot_paths", [])),
            "rows": [
                PublicAdvisoryRenderBenchmarkRow(**row)
                for row in baseline_payload.get("rows", [])
            ],
        }
    )
    comparison = compare_public_advisory_benchmark(baseline, report)
    payload["comparison"] = asdict(comparison)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 1 if report.remediation_targets or comparison.failures else 0


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
    parser.add_argument(
        "--baseline-json",
        default="docs/quality/public_editorial_quality_baseline.json",
        help="Committed retained-corpus benchmark used to block regressions.",
    )
    args = parser.parse_args()

    return run_public_report_quality_gate(
        artifact_root=args.artifact_root,
        output_dir=args.output_dir,
        output_json=args.output_json,
        minimum_reports=args.minimum_reports,
        baseline_json=args.baseline_json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
