"""Run a source-grounded Step 2 adversarial corpus through the shadow evaluator."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.quality.replay_verified_claims_step2 import (
    REPOSITORY_ROOT,
    _load_json,
    _resolve_repository_path,
    _safe_report_name,
    replay_live_explicit_cohort,
)


def _write_snapshot(
    *,
    corpus: dict[str, object],
    snapshot_root: Path,
) -> tuple[Path, dict[str, Path]]:
    cases_by_report: dict[str, list[dict[str, object]]] = defaultdict(list)
    for case in corpus.get("cases", []):
        if isinstance(case, dict):
            cases_by_report[str(case["report"])].append(case)

    artifact_paths: dict[str, Path] = {}
    report_entries: list[dict[str, object]] = []
    for report, cases in sorted(cases_by_report.items()):
        run_directory = snapshot_root / _safe_report_name(report)
        analysis_directory = run_directory / "output" / "report_analysis"
        analysis_directory.mkdir(parents=True, exist_ok=True)
        insights = []
        for case in cases:
            page = int(case["physical_pages"][0])
            insights.append(
                {
                    "id": case["candidate_id"],
                    "text": case["original_claim"],
                    "evidence_id": case["evidence_id"],
                    "evidence": case["source_anchor"],
                    "evidence_spans": [
                        {
                            "evidence_id": case["evidence_id"],
                            "source_pack": "findings",
                            "page": page,
                            "text": case["source_anchor"],
                        }
                    ],
                    "pages": list(case["physical_pages"]),
                    "_visual_replacement_policy": case["replacement_policy"],
                }
            )
        artifact_path = analysis_directory / "artifacts.json"
        artifact_path.write_text(
            json.dumps({"insights_final": insights}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        (analysis_directory / "doc_map.json").write_text(
            json.dumps({"sections": []}) + "\n", encoding="utf-8"
        )
        (analysis_directory / "findings.json").write_text(
            json.dumps({"findings": []}) + "\n", encoding="utf-8"
        )
        artifact_paths[report] = artifact_path
        report_entries.append(
            {
                "publisher_id": report,
                "git_sha": "adversarial-corpus",
                "run_directory": str(run_directory),
            }
        )

    cohort_path = snapshot_root / "cohort_result.json"
    cohort_path.write_text(
        json.dumps(
            {"git_sha": "adversarial-corpus", "reports": report_entries},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return cohort_path, artifact_paths


def replay_adversarial_corpus(
    *, corpus_path: Path, source_manifest_path: Path, output_path: Path
) -> dict[str, object]:
    corpus = _load_json(corpus_path)
    snapshot_root = output_path.parent / "input_snapshot"
    cohort_path, artifact_paths = _write_snapshot(
        corpus=corpus, snapshot_root=snapshot_root
    )
    result = replay_live_explicit_cohort(
        cohort_result_path=cohort_path,
        source_manifest_path=source_manifest_path,
        output_root=output_path.parent,
        artifact_paths=artifact_paths,
    )
    cases_by_id = {
        str(case["candidate_id"]): case
        for case in corpus.get("cases", [])
        if isinstance(case, dict)
    }
    for row in result.get("claims", []):
        case = cases_by_id.get(str(row.get("candidate_id") or ""))
        if case is None:
            continue
        row.update(
            {
                "adversarial_case_id": case["case_id"],
                "mutation": case["mutation"],
                "expected_terminal": case["expected_terminal"],
                "source_truth": case["source_truth"],
                "manual_factual_assessment": "pending_independent_review",
            }
        )
    result["adversarial_corpus"] = {
        "path": str(corpus_path),
        "case_count": len(cases_by_id),
        "expected_terminal_counts": {
            expected: sum(
                case["expected_terminal"] == expected for case in cases_by_id.values()
            )
            for expected in sorted(
                {case["expected_terminal"] for case in cases_by_id.values()}
            )
        },
        "manual_review_required": True,
        "canonical_mutation": False,
        "publication_write": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=REPOSITORY_ROOT
        / "docs/quality/verified-claims-step2-adversarial-corpus-20261020.json",
    )
    parser.add_argument("--sources-manifest", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus = _load_json(_resolve_repository_path(args.corpus))
    manifest_path = args.sources_manifest or corpus["source_manifest"]
    result = replay_adversarial_corpus(
        corpus_path=_resolve_repository_path(args.corpus),
        source_manifest_path=_resolve_repository_path(manifest_path),
        output_path=_resolve_repository_path(args.output),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
