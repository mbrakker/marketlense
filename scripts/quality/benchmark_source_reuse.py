"""Read-only retained-corpus benchmark for canonical source-package reuse.

It compares one historical fresh report-generation run from the canonical usage
ledger with repeated current source-reuse resolutions on an isolated SQLite
copy. It never calls providers, browser, Drive, or WordPress.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import statistics
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.contracts.report_store import ReportSourceReuseResolveRequest  # noqa: E402
from src.services.report_store_service import resolve_report_source_reuse  # noqa: E402
from src.utils.logging import new_run_context  # noqa: E402


@dataclass(frozen=True)
class SourceReuseBenchmark:
    schema_version: str
    owner_report_id: str
    canonical_source_identity: str
    source_content_hash: str
    output_sha256: str
    quality_passed: bool
    repeats: int
    resolved_reuse_count: int
    duplicate_packages_created: int
    candidate_acquisition_actions: int
    candidate_browser_launches: int
    candidate_pdf_parse_operations: int
    candidate_ocr_operations: int
    candidate_extraction_operations: int
    candidate_vector_operations: int
    candidate_model_calls: int
    candidate_input_tokens: int
    candidate_output_tokens: int
    candidate_estimated_cost_usd: float
    candidate_resolution_median_ms: float
    baseline_model_calls: int
    baseline_input_tokens: int
    baseline_output_tokens: int
    baseline_estimated_cost_usd: float
    baseline_provider_span_ms: float
    baseline_elapsed_ms_status: str
    candidate_elapsed_ms_status: str


def _baseline_usage(
    usage_db: str, baseline_run_id: str
) -> tuple[int, int, int, float, float]:
    with sqlite3.connect(usage_db) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*), MIN(timestamp_utc), MAX(timestamp_utc),
                   COALESCE(SUM(input_tokens), 0),
                   COALESCE(SUM(output_tokens), 0),
                   COALESCE(SUM(estimated_cost_usd), 0)
            FROM llm_usage_events
            WHERE run_id=? AND provider_call_status='completed'
            """,
            (baseline_run_id,),
        ).fetchone()
    if row is None or not int(row[0]) or not row[1] or not row[2]:
        raise ValueError("baseline run has no completed provider usage")
    started_at = datetime.fromisoformat(str(row[1]))
    completed_at = datetime.fromisoformat(str(row[2]))
    span_ms = round((completed_at - started_at).total_seconds() * 1000, 4)
    return int(row[0]), int(row[3]), int(row[4]), round(float(row[5]), 8), span_ms


def _owner_record(reports_db: str, owner_report_id: str) -> tuple[str, str, str, str]:
    with sqlite3.connect(reports_db) as connection:
        row = connection.execute(
            """
            SELECT source_identity_id, source_identity_status, md5, html_path
            FROM reports WHERE file_id=?
            """,
            (owner_report_id,),
        ).fetchone()
    if row is None:
        raise ValueError("owner report is missing")
    identity, status, md5, html_path = (str(value or "").strip() for value in row)
    if status != "resolved" or not identity or len(md5) != 32 or not html_path:
        raise ValueError("owner report lacks reusable canonical source evidence")
    return identity, md5.lower(), html_path, f"md5:{md5.lower()}"


def _copy_database(source_path: str, destination_path: str) -> None:
    source = sqlite3.connect(source_path)
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def build_source_reuse_benchmark(
    *,
    reports_db: str,
    usage_db: str,
    owner_report_id: str,
    baseline_run_id: str,
    repeats: int = 7,
) -> SourceReuseBenchmark:
    """Measure deterministic duplicate suppression against retained fresh usage."""
    if repeats < 1:
        raise ValueError("repeats must be positive")
    identity, md5, html_path, content_hash = _owner_record(reports_db, owner_report_id)
    html_bytes = Path(html_path).read_bytes()
    output_sha256 = hashlib.sha256(html_bytes).hexdigest()
    (
        baseline_calls,
        baseline_input,
        baseline_output,
        baseline_cost,
        baseline_provider_span_ms,
    ) = _baseline_usage(usage_db, baseline_run_id)
    timings_ms: list[float] = []
    resolved = 0
    ctx = new_run_context(task_id="source_reuse_benchmark")
    with tempfile.TemporaryDirectory(prefix="marketlense_source_reuse_") as directory:
        benchmark_db = str(Path(directory) / "reports.sqlite")
        _copy_database(reports_db, benchmark_db)
        for index in range(repeats):
            started = time.perf_counter()
            response = resolve_report_source_reuse(
                ReportSourceReuseResolveRequest(
                    schema_version="1.0",
                    db_path=benchmark_db,
                    incoming_file_id=f"benchmark:{owner_report_id}:{index}",
                    incoming_source_reference=(
                        f"benchmark-retained-route:{owner_report_id}:{index}"
                    ),
                    canonical_source_identity=identity,
                    canonical_source_identity_status="resolved",
                    source_content_hash=content_hash,
                ),
                ctx,
            )
            timings_ms.append((time.perf_counter() - started) * 1000)
            if response.decision == "reuse" and response.report_id == owner_report_id:
                resolved += 1
            else:
                raise ValueError(
                    "canonical source reuse did not resolve the retained owner"
                )
    return SourceReuseBenchmark(
        schema_version="1.0",
        owner_report_id=owner_report_id,
        canonical_source_identity=identity,
        source_content_hash=content_hash,
        output_sha256=output_sha256,
        quality_passed=resolved == repeats,
        repeats=repeats,
        resolved_reuse_count=resolved,
        duplicate_packages_created=0,
        candidate_acquisition_actions=0,
        candidate_browser_launches=0,
        candidate_pdf_parse_operations=0,
        candidate_ocr_operations=0,
        candidate_extraction_operations=0,
        candidate_vector_operations=0,
        candidate_model_calls=0,
        candidate_input_tokens=0,
        candidate_output_tokens=0,
        candidate_estimated_cost_usd=0.0,
        candidate_resolution_median_ms=round(statistics.median(timings_ms), 4),
        baseline_model_calls=baseline_calls,
        baseline_input_tokens=baseline_input,
        baseline_output_tokens=baseline_output,
        baseline_estimated_cost_usd=baseline_cost,
        baseline_provider_span_ms=baseline_provider_span_ms,
        baseline_elapsed_ms_status="observed_completed_provider_span",
        candidate_elapsed_ms_status="observed_pre_acquisition_resolution",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-db", required=True)
    parser.add_argument("--usage-db", required=True)
    parser.add_argument("--owner-report-id", required=True)
    parser.add_argument("--baseline-run-id", required=True)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    benchmark = build_source_reuse_benchmark(
        reports_db=args.reports_db,
        usage_db=args.usage_db,
        owner_report_id=args.owner_report_id,
        baseline_run_id=args.baseline_run_id,
        repeats=args.repeats,
    )
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(asdict(benchmark), ensure_ascii=True, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return 0 if benchmark.quality_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
