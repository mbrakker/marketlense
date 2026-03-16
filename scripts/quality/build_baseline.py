from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quality.quality_metrics import (
    collect_candidate_pack_metrics,
    collect_docpack_metrics,
    load_coverage_metrics,
    load_mutation_metrics,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build quality baseline snapshot for non-regression checks."
    )
    parser.add_argument(
        "--coverage-xml",
        default="coverage.xml",
        help="Coverage XML file path.",
    )
    parser.add_argument(
        "--mutation-json",
        default="mutation_results.json",
        help="Mutation summary JSON path (created automatically if missing).",
    )
    parser.add_argument(
        "--source-docpack-root",
        default="out/1",
        help="Source root containing <report>/report_analysis directories.",
    )
    parser.add_argument(
        "--source-candidate-root",
        default="out/1",
        help="Source root containing <report>/candidates/candidates.json directories.",
    )
    parser.add_argument(
        "--golden-docpack-root",
        default="tests/fixtures/docpacks/golden",
        help="Destination root for golden docpack corpus.",
    )
    parser.add_argument(
        "--golden-candidate-root",
        default="tests/fixtures/candidate_extraction/golden",
        help="Destination root for golden candidate-extraction corpus.",
    )
    parser.add_argument(
        "--baseline-out",
        default="docs/quality/baseline_2026-02-21.json",
        help="Baseline snapshot output file.",
    )
    parser.add_argument(
        "--copy-golden",
        action="store_true",
        help="Copy source docpack corpus into golden fixture directory before snapshot.",
    )
    return parser.parse_args()


def _copy_docpack_corpus(source_root: Path, golden_root: Path) -> int:
    report_dirs = sorted(source_root.glob("*/report_analysis"))
    if golden_root.exists():
        shutil.rmtree(golden_root)
    golden_root.mkdir(parents=True, exist_ok=True)
    copied = 0
    for report_analysis in report_dirs:
        report_dir = report_analysis.parent
        dest = golden_root / report_dir.name / "report_analysis"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(report_analysis, dest, dirs_exist_ok=True)
        copied += 1
    return copied


def _copy_candidate_corpus(source_root: Path, golden_root: Path) -> int:
    candidate_paths = sorted(source_root.glob("*/candidates/candidates.json"))
    if golden_root.exists():
        shutil.rmtree(golden_root)
    golden_root.mkdir(parents=True, exist_ok=True)
    copied = 0
    for candidate_path in candidate_paths:
        report_dir = candidate_path.parents[1]
        dest_dir = golden_root / report_dir.name / "candidates"
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate_path, dest_dir / "candidates.json")
        copied += 1
    return copied


def _ensure_mutation_json(path: Path) -> None:
    if path.exists():
        return
    cmd = [
        sys.executable,
        "scripts/ci/run_mutation_gate.py",
        "--json-out",
        str(path),
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    if result.returncode != 0:
        raise SystemExit(
            f"Mutation gate failed while building baseline ({result.returncode})."
        )


def main() -> int:
    args = _parse_args()
    coverage_path = ROOT / args.coverage_xml
    mutation_json_path = ROOT / args.mutation_json
    source_docpack_root = ROOT / args.source_docpack_root
    source_candidate_root = ROOT / args.source_candidate_root
    golden_docpack_root = ROOT / args.golden_docpack_root
    golden_candidate_root = ROOT / args.golden_candidate_root
    baseline_out = ROOT / args.baseline_out

    if args.copy_golden:
        copied = _copy_docpack_corpus(source_docpack_root, golden_docpack_root)
        print(f"Copied docpack fixture reports: {copied}")
        copied_candidates = _copy_candidate_corpus(
            source_candidate_root, golden_candidate_root
        )
        print(f"Copied candidate fixture reports: {copied_candidates}")

    _ensure_mutation_json(mutation_json_path)

    coverage_metrics = load_coverage_metrics(str(coverage_path))
    mutation_metrics = load_mutation_metrics(str(mutation_json_path))
    docpack_metrics = collect_docpack_metrics(str(golden_docpack_root))
    candidate_metrics = collect_candidate_pack_metrics(str(golden_candidate_root))

    baseline = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "coverage": coverage_metrics,
        "mutation": mutation_metrics,
        "docpacks": docpack_metrics,
        "candidate_extraction": candidate_metrics,
        "paths": {
            "coverage_xml": str(coverage_path.relative_to(ROOT)),
            "mutation_json": str(mutation_json_path.relative_to(ROOT)),
            "golden_docpack_root": str(golden_docpack_root.relative_to(ROOT)),
            "golden_candidate_root": str(golden_candidate_root.relative_to(ROOT)),
            "source_candidate_root": str(source_candidate_root.relative_to(ROOT)),
            "source_docpack_root": str(source_docpack_root.relative_to(ROOT)),
        },
    }

    baseline_out.parent.mkdir(parents=True, exist_ok=True)
    baseline_out.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Baseline written: {baseline_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
