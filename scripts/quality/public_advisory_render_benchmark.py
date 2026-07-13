from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.report_assets import RenderRequest
from src.contracts.run_context import RunContext
from src.services.render_service import render_report

_INTERNAL_ID_PATTERN = re.compile(
    r"\b(?:canonical_claim_id|report:[a-z0-9_.:-]+|[a-z]+-internal-\d+)\b",
    re.IGNORECASE,
)
_PLACEHOLDER_PATTERN = re.compile(
    r"\{\{[^{}]+\}\}|\[\[[^\[\]]+\]\]|\b(?:TODO|FIXME)\b"
)
_RAW_FRAGMENT_PATTERN = re.compile(
    r"\ufffd|(?:&lt;|&gt;){2,}|[\x00-\x08\x0b\x0c\x0e-\x1f]"
)
_IMAGE_SOURCE_PATTERN = re.compile(
    r"<img\b[^>]*\bsrc\s*=\s*(['\"])(?P<src>.*?)\1", re.IGNORECASE
)


@dataclass(frozen=True)
class PublicAdvisoryRenderBenchmarkRow:
    schema_version: str = field(metadata={"doc": "Benchmark row schema version."})
    report_id: str = field(metadata={"doc": "Report artifact identifier."})
    artifact_path: str = field(metadata={"doc": "Source artifact JSON path."})
    html_path: str = field(metadata={"doc": "Rendered HTML path."})
    advisory_available: bool = field(
        metadata={"doc": "Whether advisory decision brief is available."}
    )
    metric_spine_count: int = field(metadata={"doc": "Public metric spine count."})
    claim_support_count: int = field(metadata={"doc": "Public claim support count."})
    so_what_available: bool = field(
        metadata={"doc": "Whether any public insight has so_what."}
    )
    now_what_available: bool = field(
        metadata={"doc": "Whether any public insight has now_what."}
    )
    so_what_coverage: float = field(metadata={"doc": "Per-row so_what coverage."})
    now_what_coverage: float = field(metadata={"doc": "Per-row now_what coverage."})
    public_label_count: int = field(
        metadata={"doc": "Count of public support/confidence labels."}
    )
    internal_id_leak_count: int = field(
        metadata={"doc": "Internal identifier leak count in rendered HTML."}
    )
    placeholder_count: int = field(
        metadata={"doc": "Unresolved public template placeholder count."}
    )
    raw_fragment_count: int = field(
        metadata={"doc": "Malformed raw extraction fragment count in rendered HTML."}
    )
    broken_asset_count: int = field(
        metadata={"doc": "Locally referenced rendered image assets that are absent."}
    )
    remediation_targets: list[dict[str, str]] = field(
        metadata={
            "doc": "Benchmark failures with report, field, rule, and remediation."
        }
    )


@dataclass(frozen=True)
class PublicAdvisoryRenderBenchmarkReport:
    schema_version: str = field(metadata={"doc": "Benchmark report schema version."})
    report_count: int = field(metadata={"doc": "Rendered report count."})
    advisory_coverage: float = field(metadata={"doc": "Share with advisory brief."})
    so_what_coverage: float = field(metadata={"doc": "Share with so_what coverage."})
    now_what_coverage: float = field(metadata={"doc": "Share with now_what coverage."})
    internal_id_leak_count: int = field(
        metadata={"doc": "Total rendered internal ID leaks."}
    )
    placeholder_count: int = field(
        metadata={"doc": "Total unresolved public template placeholders."}
    )
    raw_fragment_count: int = field(
        metadata={"doc": "Total malformed raw extraction fragments."}
    )
    broken_asset_count: int = field(
        metadata={"doc": "Total missing locally referenced rendered image assets."}
    )
    screenshot_paths: tuple[str, ...] = field(
        metadata={"doc": "Optional Playwright screenshot paths retained for the run."}
    )
    rows: list[PublicAdvisoryRenderBenchmarkRow] = field(
        metadata={"doc": "Per-report benchmark rows."}
    )
    remediation_targets: list[dict[str, str]] = field(
        metadata={"doc": "Flattened remediation targets for failed fields."}
    )


def build_public_advisory_render_benchmark(
    *,
    artifact_paths: list[str],
    output_dir: str,
    screenshot_paths: tuple[str, ...] = (),
) -> PublicAdvisoryRenderBenchmarkReport:
    ctx = RunContext(
        schema_version="1.0",
        run_id="public-advisory-render-benchmark",
        task_id="render-benchmark",
        span_id="benchmark",
    )
    out_dir = Path(output_dir).resolve()
    rows: list[PublicAdvisoryRenderBenchmarkRow] = []
    for artifact_path in artifact_paths:
        path = Path(artifact_path).resolve()
        artifacts = _load_artifacts(path)
        report_id = str(
            artifacts.get("report_id") or path.parent.parent.name or path.stem
        )
        render_response = render_report(
            RenderRequest(
                schema_version="1.0",
                data=_render_data_from_artifacts(artifacts, report_id=report_id),
                doc_name=report_id,
                file_id=report_id,
                out_dir=str(out_dir),
            ),
            ctx,
        )
        html = Path(render_response.html_path).read_text(encoding="utf-8")
        row = _benchmark_row(
            artifacts=artifacts,
            artifact_path=str(path),
            html_path=render_response.html_path,
            html=html,
            report_id=report_id,
        )
        rows.append(row)
    report_count = len(rows)
    remediation_targets = [target for row in rows for target in row.remediation_targets]
    return PublicAdvisoryRenderBenchmarkReport(
        schema_version="1.0",
        report_count=report_count,
        advisory_coverage=_coverage(rows, lambda row: row.advisory_available),
        so_what_coverage=_coverage(rows, lambda row: row.so_what_available),
        now_what_coverage=_coverage(rows, lambda row: row.now_what_available),
        internal_id_leak_count=sum(row.internal_id_leak_count for row in rows),
        placeholder_count=sum(row.placeholder_count for row in rows),
        raw_fragment_count=sum(row.raw_fragment_count for row in rows),
        broken_asset_count=sum(row.broken_asset_count for row in rows),
        screenshot_paths=tuple(screenshot_paths),
        rows=rows,
        remediation_targets=remediation_targets,
    )


def _load_artifacts(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _render_data_from_artifacts(
    artifacts: dict[str, Any], *, report_id: str
) -> dict[str, Any]:
    summary = (
        artifacts.get("summary") if isinstance(artifacts.get("summary"), dict) else {}
    )
    return {
        "title": str(artifacts.get("title") or report_id),
        "publisher": str(artifacts.get("publisher") or "MarketBearing"),
        "region": str(artifacts.get("region") or ""),
        "time_period": str(artifacts.get("time_period") or ""),
        "tldr": str(
            summary.get("tldr")
            or artifacts.get("tldr")
            or "Source-backed public report benchmark."
        ),
        "commentary": str(
            summary.get("executive_summary") or artifacts.get("commentary") or ""
        ),
        "insights": artifacts.get("insights_final") or artifacts.get("insights") or [],
        "taxonomy": artifacts.get("taxonomy") or [],
        "artifacts": artifacts,
    }


def _benchmark_row(
    *,
    artifacts: dict[str, Any],
    artifact_path: str,
    html_path: str,
    html: str,
    report_id: str,
) -> PublicAdvisoryRenderBenchmarkRow:
    advisory = (
        artifacts.get("executive_advisory")
        if isinstance(artifacts.get("executive_advisory"), dict)
        else {}
    )
    decision = (
        advisory.get("decision_brief")
        if isinstance(advisory.get("decision_brief"), dict)
        else {}
    )
    metric_spine = (
        artifacts.get("metric_spine")
        if isinstance(artifacts.get("metric_spine"), list)
        else []
    )
    claim_support = (
        artifacts.get("claim_ledgers")
        if isinstance(artifacts.get("claim_ledgers"), list)
        else []
    )
    insights = (
        artifacts.get("insights_final")
        if isinstance(artifacts.get("insights_final"), list)
        else []
    )
    leaks = _INTERNAL_ID_PATTERN.findall(html)
    quality_issues = public_html_quality_issues(html=html, html_path=html_path)
    placeholders = quality_issues["placeholders"]
    raw_fragments = quality_issues["raw_fragments"]
    broken_assets = quality_issues["broken_assets"]
    targets: list[dict[str, str]] = []
    if leaks:
        targets.append(
            {
                "report_id": report_id,
                "field": "html",
                "rule": "public_render.internal_id_leak",
                "remediation": "Render public source labels instead of internal IDs.",
            }
        )
    if placeholders:
        targets.append(
            {
                "report_id": report_id,
                "field": "html",
                "rule": "public_render.unresolved_placeholder",
                "remediation": "Resolve template placeholders before public rendering.",
            }
        )
    if raw_fragments:
        targets.append(
            {
                "report_id": report_id,
                "field": "html",
                "rule": "public_render.raw_extraction_fragment",
                "remediation": (
                    "Repair or omit malformed extraction fragments before rendering."
                ),
            }
        )
    if broken_assets:
        targets.append(
            {
                "report_id": report_id,
                "field": "html",
                "rule": "public_render.broken_local_asset",
                "remediation": (
                    "Regenerate or remove missing locally referenced public assets."
                ),
            }
        )
    so_what_available = any(
        str(item.get("so_what") or "").strip()
        for item in insights
        if isinstance(item, dict)
    )
    now_what_available = any(
        str(item.get("now_what") or "").strip()
        for item in insights
        if isinstance(item, dict)
    )
    return PublicAdvisoryRenderBenchmarkRow(
        schema_version="1.0",
        report_id=report_id,
        artifact_path=artifact_path,
        html_path=html_path,
        advisory_available=str(decision.get("status") or "").casefold() == "generated",
        metric_spine_count=len(metric_spine),
        claim_support_count=len(claim_support),
        so_what_available=so_what_available,
        now_what_available=now_what_available,
        so_what_coverage=1.0 if so_what_available else 0.0,
        now_what_coverage=1.0 if now_what_available else 0.0,
        public_label_count=html.count("Source-backed") + html.count("Chart-backed"),
        internal_id_leak_count=len(leaks),
        placeholder_count=len(placeholders),
        raw_fragment_count=len(raw_fragments),
        broken_asset_count=len(broken_assets),
        remediation_targets=targets,
    )


def _broken_local_image_sources(*, html: str, html_path: str) -> list[str]:
    html_dir = Path(html_path).resolve().parent
    broken: list[str] = []
    for match in _IMAGE_SOURCE_PATTERN.finditer(html):
        source = str(match.group("src") or "").strip()
        if not source or source.startswith(("https://", "http://", "data:")):
            continue
        if not (html_dir / source).resolve().is_file():
            broken.append(source)
    return broken


def public_html_quality_issues(*, html: str, html_path: str) -> dict[str, list[str]]:
    """Return deterministic public-render defects without changing the rendered file."""
    return {
        "placeholders": _PLACEHOLDER_PATTERN.findall(html),
        "raw_fragments": _RAW_FRAGMENT_PATTERN.findall(html),
        "broken_assets": _broken_local_image_sources(html=html, html_path=html_path),
    }


def _coverage(
    rows: list[PublicAdvisoryRenderBenchmarkRow],
    predicate,
) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if predicate(row)) / len(rows), 6)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run public advisory render benchmark."
    )
    parser.add_argument("artifacts", nargs="+", help="Artifact JSON paths to render.")
    parser.add_argument(
        "--output-dir", default="./out/public-advisory-render-benchmark"
    )
    parser.add_argument("--screenshot", action="append", default=[])
    parser.add_argument("--json-output", default="")
    args = parser.parse_args()
    report = build_public_advisory_render_benchmark(
        artifact_paths=list(args.artifacts),
        output_dir=args.output_dir,
        screenshot_paths=tuple(args.screenshot),
    )
    payload = asdict(report)
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2)
    if args.json_output:
        Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 1 if report.remediation_targets else 0


if __name__ == "__main__":
    raise SystemExit(main())
