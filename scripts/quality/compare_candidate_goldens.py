from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.pdf_context import PdfContextBuildRequest
from src.contracts.report_assets import CropRequest, ExtractCandidatesRequest
from src.contracts.report_models import CropItem
from src.contracts.run_context import RunContext
from src.services.pdf_service import build_pdf_context, collect_candidates, crop_regions


@dataclass(frozen=True)
class GoldenCandidate:
    id: str
    kind: str
    page: int
    bbox: tuple[float, float, float, float]
    crop_path: str


@dataclass(frozen=True)
class GoldenReport:
    report_name: str
    pdf_path: str
    charts: dict[str, GoldenCandidate]
    tables: dict[str, GoldenCandidate]


def _ctx(task_id: str) -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="candidate-golden-compare",
        task_id=task_id,
        span_id=task_id,
    )


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object payload in {path}")
    return payload


def _bbox_tuple(value: Any) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"Invalid bbox payload: {value!r}")
    return (
        float(value[0]),
        float(value[1]),
        float(value[2]),
        float(value[3]),
    )


def _load_candidate_map(path: Path) -> dict[str, GoldenCandidate]:
    payload = _load_json(path)
    candidates_value = payload.get("candidates")
    rows = candidates_value if isinstance(candidates_value, list) else []
    out: dict[str, GoldenCandidate] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("id") or "").strip()
        kind = str(row.get("kind") or row.get("type") or "").strip()
        crop_path = str(row.get("crop_path") or "").strip()
        if not candidate_id or not kind or not crop_path:
            continue
        out[candidate_id] = GoldenCandidate(
            id=candidate_id,
            kind=kind,
            page=int(row.get("page") or 0),
            bbox=_bbox_tuple(row.get("bbox") or []),
            crop_path=crop_path,
        )
    return out


def _load_golden_reports(golden_root: Path) -> list[GoldenReport]:
    reports: list[GoldenReport] = []
    for report_dir in sorted(path for path in golden_root.iterdir() if path.is_dir()):
        summary_path = report_dir / "summary.json"
        charts_path = report_dir / "charts_only" / "charts.json"
        tables_path = report_dir / "tables_only" / "tables.json"
        if not summary_path.exists() or not charts_path.exists() or not tables_path.exists():
            continue
        summary = _load_json(summary_path)
        reports.append(
            GoldenReport(
                report_name=str(summary.get("report_name") or report_dir.name),
                pdf_path=str(summary.get("pdf_path") or "").strip(),
                charts=_load_candidate_map(charts_path),
                tables=_load_candidate_map(tables_path),
            )
        )
    return reports


def _filter_reports(
    reports: list[GoldenReport],
    selected_names: set[str],
) -> list[GoldenReport]:
    if not selected_names:
        return reports
    return [
        report
        for report in reports
        if report.report_name in selected_names
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bbox_matches(
    expected: tuple[float, float, float, float],
    actual: tuple[float, float, float, float],
    *,
    tolerance: float,
) -> bool:
    return all(abs(left - right) <= tolerance for left, right in zip(expected, actual))


def _compare_kind(
    *,
    kind: str,
    expected: dict[str, GoldenCandidate],
    actual_candidates: list[Any],
    golden_root: Path,
    compare_output_dir: Path,
    pdf_path: str,
    report_name: str,
    pdf_context: Any,
    bbox_tolerance: float,
) -> dict[str, Any]:
    actual_by_id = {
        str(candidate.id or "").strip(): candidate
        for candidate in actual_candidates
        if str(candidate.kind or "").strip() == kind
    }
    expected_ids = sorted(expected)
    actual_ids = sorted(actual_by_id)
    matched_ids = sorted(candidate_id for candidate_id in expected_ids if candidate_id in actual_by_id)
    removed_ids = sorted(candidate_id for candidate_id in expected_ids if candidate_id not in actual_by_id)
    added_ids = sorted(candidate_id for candidate_id in actual_ids if candidate_id not in expected)

    bbox_changes: list[dict[str, Any]] = []
    crop_items: list[CropItem] = []
    crop_order: list[str] = []
    for candidate_id in matched_ids:
        expected_candidate = expected[candidate_id]
        actual_candidate = actual_by_id[candidate_id]
        actual_bbox = tuple(float(value) for value in actual_candidate.bbox)
        if not _bbox_matches(expected_candidate.bbox, actual_bbox, tolerance=bbox_tolerance):
            bbox_changes.append(
                {
                    "id": candidate_id,
                    "expected_bbox": list(expected_candidate.bbox),
                    "actual_bbox": list(actual_bbox),
                }
            )
        crop_items.append(
            CropItem(
                id=actual_candidate.id,
                type=actual_candidate.kind,
                score=0.0,
                page=int(actual_candidate.page),
                bbox=actual_bbox,
            )
        )
        crop_order.append(candidate_id)

    image_changes: list[dict[str, Any]] = []
    if crop_items:
        crop_response = crop_regions(
            CropRequest(
                schema_version="1.0",
                pdf_path=pdf_path,
                out_dir=compare_output_dir.as_posix(),
                report_name=report_name,
                subdir=f"{kind}s_compare",
                items=crop_items,
                mode="legacy",
                pdf_context=pdf_context,
            ),
            _ctx(f"crop:{report_name}:{kind}"),
        )
        for candidate_id, relative_path in zip(crop_order, crop_response.paths):
            actual_path = compare_output_dir / relative_path
            expected_path = golden_root / expected[candidate_id].crop_path
            if not actual_path.exists():
                image_changes.append(
                    {"id": candidate_id, "reason": "missing_actual_crop"}
                )
                continue
            if not expected_path.exists():
                image_changes.append(
                    {"id": candidate_id, "reason": "missing_expected_crop"}
                )
                continue
            if _sha256(actual_path) != _sha256(expected_path):
                image_changes.append(
                    {
                        "id": candidate_id,
                        "actual_crop_path": str(actual_path),
                        "expected_crop_path": str(expected_path),
                    }
                )

    expected_count = len(expected_ids)
    matched_count = len(matched_ids)
    recall = (matched_count / expected_count) if expected_count else 1.0
    return {
        "expected_count": expected_count,
        "actual_count": len(actual_ids),
        "matched_count": matched_count,
        "recall": round(recall, 6),
        "added_ids": added_ids,
        "removed_ids": removed_ids,
        "bbox_changes": bbox_changes,
        "image_changes": image_changes,
    }


def _compare_report(
    report: GoldenReport,
    *,
    golden_root: Path,
    compare_output_dir: Path,
    bbox_tolerance: float,
) -> dict[str, Any]:
    compare_output_dir.mkdir(parents=True, exist_ok=True)
    pdf_context = None
    try:
        pdf_context = build_pdf_context(
            PdfContextBuildRequest(
                schema_version="1.0",
                path=report.pdf_path,
                load_fitz=True,
                load_pypdf=False,
            ),
            _ctx(f"context:{report.report_name}"),
        ).context
        response = collect_candidates(
            ExtractCandidatesRequest(
                schema_version="1.0",
                pdf_path=report.pdf_path,
                out_dir=compare_output_dir.as_posix(),
                report_name=report.report_name,
                pdf_context=pdf_context,
            ),
            _ctx(f"extract:{report.report_name}"),
        )
        charts = _compare_kind(
            kind="chart",
            expected=report.charts,
            actual_candidates=response.candidates,
            golden_root=golden_root,
            compare_output_dir=compare_output_dir,
            pdf_path=report.pdf_path,
            report_name=report.report_name,
            pdf_context=pdf_context,
            bbox_tolerance=bbox_tolerance,
        )
        tables = _compare_kind(
            kind="table",
            expected=report.tables,
            actual_candidates=response.candidates,
            golden_root=golden_root,
            compare_output_dir=compare_output_dir,
            pdf_path=report.pdf_path,
            report_name=report.report_name,
            pdf_context=pdf_context,
            bbox_tolerance=bbox_tolerance,
        )
        return {
            "report_name": report.report_name,
            "pdf_path": report.pdf_path,
            "candidate_count": len(response.candidates),
            "charts": charts,
            "tables": tables,
        }
    finally:
        if pdf_context is not None:
            pdf_context.close()


def _summarize(compare_rows: list[dict[str, Any]], min_recall: float) -> dict[str, Any]:
    expected_total = 0
    matched_total = 0
    bbox_change_total = 0
    image_change_total = 0
    for row in compare_rows:
        for key in ("charts", "tables"):
            kind_row = row[key]
            expected_total += int(kind_row["expected_count"])
            matched_total += int(kind_row["matched_count"])
            bbox_change_total += len(kind_row["bbox_changes"])
            image_change_total += len(kind_row["image_changes"])
    recall = (matched_total / expected_total) if expected_total else 1.0
    passed = (
        recall >= min_recall
        and bbox_change_total == 0
        and image_change_total == 0
    )
    return {
        "expected_total": expected_total,
        "matched_total": matched_total,
        "recall": round(recall, 6),
        "bbox_change_total": bbox_change_total,
        "image_change_total": image_change_total,
        "min_recall": min_recall,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare current candidate extraction against golden candidate folders.",
    )
    parser.add_argument(
        "--golden-root",
        action="append",
        required=True,
        help="Golden comparison root containing per-report charts_only/tables_only folders.",
    )
    parser.add_argument(
        "--output-root",
        default="out/candidate_golden_compare_current",
        help="Directory for generated comparison crops and summary output.",
    )
    parser.add_argument(
        "--min-recall",
        type=float,
        default=0.95,
        help="Minimum global recall required across the full golden corpus.",
    )
    parser.add_argument(
        "--bbox-tolerance",
        type=float,
        default=0.25,
        help="Absolute tolerance in PDF points for bbox comparisons.",
    )
    parser.add_argument(
        "--report-name",
        action="append",
        default=[],
        help="Optional report-name filter; may be provided multiple times.",
    )
    args = parser.parse_args()

    output_root = (ROOT / args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    root_results: list[dict[str, Any]] = []
    all_compare_rows: list[dict[str, Any]] = []
    selected_names = {str(name or "").strip() for name in args.report_name if str(name or "").strip()}

    for golden_root_arg in args.golden_root:
        golden_root = Path(golden_root_arg).resolve()
        reports = _filter_reports(_load_golden_reports(golden_root), selected_names)
        compare_rows: list[dict[str, Any]] = []
        per_root_output = output_root / golden_root.name
        for report in reports:
            compare_rows.append(
                _compare_report(
                    report,
                    golden_root=golden_root,
                    compare_output_dir=per_root_output,
                    bbox_tolerance=float(args.bbox_tolerance),
                )
            )
        summary = _summarize(compare_rows, float(args.min_recall))
        root_results.append(
            {
                "golden_root": str(golden_root),
                "report_count": len(reports),
                "summary": summary,
                "compare": compare_rows,
            }
        )
        all_compare_rows.extend(compare_rows)

    aggregate = _summarize(all_compare_rows, float(args.min_recall))
    payload = {
        "schema_version": "1.0",
        "roots": root_results,
        "aggregate": aggregate,
    }
    summary_path = output_root / "summary.json"
    summary_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps({"summary_path": str(summary_path), "aggregate": aggregate}, ensure_ascii=True))
    return 0 if aggregate["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
