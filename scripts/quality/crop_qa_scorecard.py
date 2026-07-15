"""Read-only operator scorecards for retained final-crop QA sidecars."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


@dataclass(frozen=True)
class CropQaScorecardRow:
    """One retained crop QA observation; never a public-rendering contract."""

    schema_version: str = field(metadata={"doc": "Scorecard row schema version."})
    sidecar_path: str = field(metadata={"doc": "Resolved retained QA sidecar path."})
    report_id: str = field(
        metadata={"doc": "Report identifier inferred from artifact path."}
    )
    candidate_id: str = field(
        metadata={"doc": "Stable selected crop candidate identifier."}
    )
    candidate_type: str = field(metadata={"doc": "Crop candidate type."})
    quality_profile: str = field(metadata={"doc": "Final crop quality profile."})
    accepted: bool = field(
        metadata={"doc": "Whether deterministic QA accepted the crop."}
    )
    total_score: float = field(metadata={"doc": "Deterministic final-crop QA score."})
    defects: tuple[str, ...] = field(metadata={"doc": "Deterministic defect labels."})
    detector_confidence: dict[str, float] = field(
        metadata={"doc": "Detector confidence by detector name."}
    )
    render_dpi: int = field(metadata={"doc": "Final rendered crop DPI."})
    artifact_bytes: int = field(
        metadata={"doc": "Associated PNG byte size when present."}
    )


@dataclass(frozen=True)
class CropQaScorecard:
    """Aggregate quality, clipping, storage, and missing-evidence signals."""

    schema_version: str = field(metadata={"doc": "Scorecard schema version."})
    sidecar_count: int = field(metadata={"doc": "Readable sidecar count."})
    accepted_count: int = field(metadata={"doc": "Accepted deterministic crop count."})
    rejected_count: int = field(metadata={"doc": "Rejected deterministic crop count."})
    mean_total_score: float = field(metadata={"doc": "Mean deterministic score."})
    mean_render_dpi: float = field(metadata={"doc": "Mean final crop DPI."})
    artifact_bytes: int = field(metadata={"doc": "Total associated image bytes."})
    clipping_defect_count: int = field(
        metadata={"doc": "Count of clipping-labelled crops."}
    )
    defects: dict[str, int] = field(metadata={"doc": "Defect frequencies."})
    detector_confidence: dict[str, float] = field(
        metadata={"doc": "Mean detector confidence by detector name."}
    )
    missing_sidecars: tuple[str, ...] = field(
        metadata={"doc": "Requested sidecars that were absent or invalid."}
    )
    rows: tuple[CropQaScorecardRow, ...] = field(
        metadata={"doc": "Stable path-sorted retained observations."}
    )


@dataclass(frozen=True)
class CropQaSelectionTelemetry:
    """Operator-only selected-asset QA telemetry built from report figure assets."""

    schema_version: str = field(metadata={"doc": "Telemetry schema version."})
    candidate_id: str = field(metadata={"doc": "Selected figure candidate identifier."})
    quality_profile: str = field(metadata={"doc": "Chosen crop QA profile."})
    qa_sidecar_path: str = field(metadata={"doc": "Chosen crop QA sidecar path."})
    total_score: float = field(metadata={"doc": "Chosen deterministic QA score."})
    defects: tuple[str, ...] = field(metadata={"doc": "Chosen deterministic defects."})
    detector_confidence: dict[str, float] = field(
        metadata={"doc": "Chosen detector confidence summary."}
    )


@dataclass(frozen=True)
class CropQaScorecardComparison:
    """Deterministic quality-profile regression result for retained sidecars."""

    schema_version: str = field(metadata={"doc": "Comparison schema version."})
    accepted_rate_delta: float = field(
        metadata={"doc": "Current minus baseline acceptance rate."}
    )
    mean_score_delta: float = field(
        metadata={"doc": "Current minus baseline mean QA score."}
    )
    clipping_defect_delta: int = field(
        metadata={"doc": "Current minus baseline clipping defects."}
    )
    artifact_bytes_delta: int = field(
        metadata={"doc": "Current minus baseline crop bytes."}
    )
    mean_render_dpi_delta: float = field(
        metadata={"doc": "Current minus baseline crop DPI."}
    )
    warnings: tuple[str, ...] = field(
        metadata={"doc": "Non-blocking profile regressions."}
    )
    failures: tuple[str, ...] = field(metadata={"doc": "Blocking quality regressions."})


def build_crop_qa_scorecard(sidecar_paths: Iterable[str]) -> CropQaScorecard:
    """Aggregate existing sidecars without invoking models or changing artifacts."""
    rows: list[CropQaScorecardRow] = []
    missing: list[str] = []
    for raw_path in sorted({str(value) for value in sidecar_paths if str(value)}):
        row = _read_row(Path(raw_path))
        if row is None:
            missing.append(raw_path)
        else:
            rows.append(row)
    defects: dict[str, int] = {}
    detector_values: dict[str, list[float]] = {}
    for row in rows:
        for defect in row.defects:
            defects[defect] = defects.get(defect, 0) + 1
        for name, confidence in row.detector_confidence.items():
            detector_values.setdefault(name, []).append(confidence)
    clipping = sum(
        count for defect, count in defects.items() if "clipp" in defect.casefold()
    )
    return CropQaScorecard(
        schema_version="1.0",
        sidecar_count=len(rows),
        accepted_count=sum(row.accepted for row in rows),
        rejected_count=sum(not row.accepted for row in rows),
        mean_total_score=_mean([row.total_score for row in rows]),
        mean_render_dpi=_mean([float(row.render_dpi) for row in rows]),
        artifact_bytes=sum(row.artifact_bytes for row in rows),
        clipping_defect_count=clipping,
        defects=dict(sorted(defects.items())),
        detector_confidence={
            name: round(_mean(values), 6)
            for name, values in sorted(detector_values.items())
        },
        missing_sidecars=tuple(sorted(missing)),
        rows=tuple(sorted(rows, key=lambda row: row.sidecar_path)),
    )


def build_selection_telemetry(
    figure_assets: Iterable[dict[str, Any]],
) -> tuple[CropQaSelectionTelemetry, ...]:
    """Keep selected figure QA facts available to operators, never public HTML."""
    rows: list[CropQaSelectionTelemetry] = []
    for asset in figure_assets:
        if not isinstance(asset, dict):
            continue
        candidate_id = str(asset.get("candidate_id") or "").strip()
        sidecar_path = str(asset.get("crop_qa_sidecar_path") or "").strip()
        if not candidate_id or not sidecar_path:
            continue
        detector_summary = asset.get("crop_qa_detector_summary")
        detectors = (
            {
                str(name): float(value)
                for name, value in detector_summary.items()
                if isinstance(name, str) and isinstance(value, (int, float))
            }
            if isinstance(detector_summary, dict)
            else {}
        )
        raw_defects = asset.get("crop_qa_defects")
        rows.append(
            CropQaSelectionTelemetry(
                schema_version="1.0",
                candidate_id=candidate_id,
                quality_profile=str(asset.get("crop_quality_profile") or ""),
                qa_sidecar_path=sidecar_path,
                total_score=float(asset.get("crop_qa_score") or 0.0),
                defects=tuple(str(value) for value in raw_defects)
                if isinstance(raw_defects, list)
                else (),
                detector_confidence=dict(sorted(detectors.items())),
            )
        )
    return tuple(sorted(rows, key=lambda row: (row.candidate_id, row.qa_sidecar_path)))


def compare_crop_qa_scorecards(
    baseline: CropQaScorecard, current: CropQaScorecard
) -> CropQaScorecardComparison:
    """Flag material crop-quality regressions without changing selected assets."""
    baseline_rate = _share(baseline.accepted_count, baseline.sidecar_count)
    current_rate = _share(current.accepted_count, current.sidecar_count)
    accepted_rate_delta = round(current_rate - baseline_rate, 6)
    mean_score_delta = round(current.mean_total_score - baseline.mean_total_score, 6)
    clipping_delta = current.clipping_defect_count - baseline.clipping_defect_count
    bytes_delta = current.artifact_bytes - baseline.artifact_bytes
    dpi_delta = round(current.mean_render_dpi - baseline.mean_render_dpi, 6)
    failures: list[str] = []
    warnings: list[str] = []
    if accepted_rate_delta < -0.05:
        failures.append("accepted_rate_regressed")
    if mean_score_delta < -0.05:
        failures.append("mean_total_score_regressed")
    if clipping_delta > 0:
        failures.append("clipping_defects_increased")
    if baseline.artifact_bytes and bytes_delta > baseline.artifact_bytes * 0.25:
        warnings.append("artifact_bytes_increased")
    if dpi_delta < -10:
        warnings.append("mean_render_dpi_reduced")
    return CropQaScorecardComparison(
        schema_version="1.0",
        accepted_rate_delta=accepted_rate_delta,
        mean_score_delta=mean_score_delta,
        clipping_defect_delta=clipping_delta,
        artifact_bytes_delta=bytes_delta,
        mean_render_dpi_delta=dpi_delta,
        warnings=tuple(warnings),
        failures=tuple(failures),
    )


def _read_row(path: Path) -> CropQaScorecardRow | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("qa"), dict):
        return None
    qa = payload["qa"]
    raw_defects = qa.get("defect_labels")
    detectors = qa.get("detectors")
    detector_confidence = (
        {
            str(name): float(details.get("confidence"))
            for name, details in detectors.items()
            if isinstance(name, str)
            and isinstance(details, dict)
            and isinstance(details.get("confidence"), (int, float))
        }
        if isinstance(detectors, dict)
        else {}
    )
    image_path = Path(str(path)[: -len(".qa.json")])
    return CropQaScorecardRow(
        schema_version="1.0",
        sidecar_path=str(path.resolve()),
        report_id=path.parent.parent.name,
        candidate_id=str(payload.get("candidate_id") or ""),
        candidate_type=str(payload.get("candidate_type") or ""),
        quality_profile=str(payload.get("mode") or ""),
        accepted=bool(payload.get("accepted")) and bool(qa.get("accepted")),
        total_score=float(qa.get("total_score") or 0.0),
        defects=tuple(str(value) for value in raw_defects)
        if isinstance(raw_defects, list)
        else (),
        detector_confidence=dict(sorted(detector_confidence.items())),
        render_dpi=int(payload.get("render_dpi") or 0),
        artifact_bytes=image_path.stat().st_size if image_path.is_file() else 0,
    )


def _mean(values: list[float]) -> float:
    return round(float(mean(values)), 6) if values else 0.0


def _share(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sidecars", nargs="+", help="Existing .qa.json sidecars")
    parser.add_argument("--output-json", default="")
    parser.add_argument(
        "--baseline-json",
        default="",
        help="Prior scorecard JSON; compare without regenerating artifacts.",
    )
    args = parser.parse_args(argv)
    scorecard = build_crop_qa_scorecard(args.sidecars)
    result: dict[str, Any] = asdict(scorecard)
    comparison: CropQaScorecardComparison | None = None
    if args.baseline_json:
        baseline_payload = json.loads(
            Path(args.baseline_json).read_text(encoding="utf-8")
        )
        baseline = CropQaScorecard(
            **{
                **baseline_payload,
                "missing_sidecars": tuple(baseline_payload.get("missing_sidecars", [])),
                "rows": tuple(
                    CropQaScorecardRow(**row)
                    for row in baseline_payload.get("rows", [])
                ),
            }
        )
        comparison = compare_crop_qa_scorecards(baseline, scorecard)
        result["comparison"] = asdict(comparison)
    payload = json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return (
        0
        if not scorecard.missing_sidecars and not (comparison and comparison.failures)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
