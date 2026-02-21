from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quality.quality_metrics import (
    collect_docpack_metrics,
    load_coverage_metrics,
    load_mutation_metrics,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Quality non-regression gate against committed baseline snapshot."
    )
    parser.add_argument(
        "--baseline",
        default="docs/quality/baseline_2026-02-21.json",
        help="Baseline snapshot JSON path.",
    )
    parser.add_argument(
        "--coverage-xml",
        default="coverage.xml",
        help="Coverage XML path.",
    )
    parser.add_argument(
        "--mutation-json",
        default="mutation_results.json",
        help="Mutation summary JSON path.",
    )
    parser.add_argument(
        "--docpack-root",
        default="tests/fixtures/docpacks/golden",
        help="Docpack corpus root path.",
    )
    return parser.parse_args()


def _get_rate(obj: dict, key: str) -> float:
    return float(obj.get(key) or 0.0)


def main() -> int:
    args = _parse_args()
    baseline_path = ROOT / args.baseline
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    current_coverage = load_coverage_metrics(str(ROOT / args.coverage_xml))
    current_mutation = load_mutation_metrics(str(ROOT / args.mutation_json))
    current_docpacks = collect_docpack_metrics(str(ROOT / args.docpack_root))

    failures: list[str] = []
    print("Quality regression gate:")

    baseline_coverage = baseline.get("coverage") or {}
    print("Coverage:")
    for key, baseline_value in baseline_coverage.items():
        current_value = float(current_coverage.get(key) or 0.0)
        status = "PASS" if current_value >= float(baseline_value) else "FAIL"
        print(
            f"  - {key}: current={current_value:.4f} baseline={float(baseline_value):.4f} [{status}]"
        )
        if status == "FAIL":
            failures.append(
                f"coverage {key}: {current_value:.4f} < baseline {float(baseline_value):.4f}"
            )

    baseline_mutation = baseline.get("mutation") or {}
    print("Mutation:")
    for module, baseline_info in baseline_mutation.items():
        if module not in current_mutation:
            failures.append(f"mutation {module}: missing from current mutation report")
            print(f"  - {module}: missing [FAIL]")
            continue
        baseline_score = float((baseline_info or {}).get("score") or 0.0)
        current_score = float(current_mutation[module].get("score") or 0.0)
        status = "PASS" if current_score >= baseline_score else "FAIL"
        print(
            f"  - {module}: current={current_score:.4f} baseline={baseline_score:.4f} [{status}]"
        )
        if status == "FAIL":
            failures.append(
                f"mutation {module}: {current_score:.4f} < baseline {baseline_score:.4f}"
            )

    baseline_docpacks = baseline.get("docpacks") or {}
    print("Docpacks:")
    for key in (
        "pack_presence_rate",
        "pack_non_empty_rate",
        "schema_valid_rate",
        "evidence_reference_integrity_rate",
    ):
        baseline_value = _get_rate(baseline_docpacks, key)
        current_value = _get_rate(current_docpacks, key)
        status = "PASS" if current_value >= baseline_value else "FAIL"
        print(
            f"  - {key}: current={current_value:.6f} baseline={baseline_value:.6f} [{status}]"
        )
        if status == "FAIL":
            failures.append(
                f"docpacks {key}: {current_value:.6f} < baseline {baseline_value:.6f}"
            )

    baseline_pack_stats = baseline_docpacks.get("packs") or {}
    current_pack_stats = current_docpacks.get("packs") or {}
    for pack_name, baseline_stats in baseline_pack_stats.items():
        current_stats = current_pack_stats.get(pack_name) or {}
        for key in ("present_rate", "non_empty_rate", "schema_valid_rate"):
            baseline_value = _get_rate(baseline_stats, key)
            current_value = _get_rate(current_stats, key)
            status = "PASS" if current_value >= baseline_value else "FAIL"
            print(
                f"  - packs.{pack_name}.{key}: current={current_value:.6f} "
                f"baseline={baseline_value:.6f} [{status}]"
            )
            if status == "FAIL":
                failures.append(
                    f"docpacks packs.{pack_name}.{key}: "
                    f"{current_value:.6f} < baseline {baseline_value:.6f}"
                )

    if failures:
        print("\nQuality regression gate failed:")
        for issue in failures:
            print(f"  - {issue}")
        return 1

    print("\nQuality regression gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
