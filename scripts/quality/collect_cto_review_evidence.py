"""Deterministically collect retained local CTO evidence without external I/O."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvidencePaths:
    """Read-only evidence inputs and generated output location."""

    state_dir: Path
    artifact_dir: Path
    output_dir: Path


def _connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _exists(connection: sqlite3.Connection, table: str) -> bool:
    return bool(
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
    )


def _query(path: Path, table: str, sql: str) -> list[dict[str, object]]:
    if not path.exists():
        return []
    with _connection(path) as connection:
        return (
            [dict(row) for row in connection.execute(sql)]
            if _exists(connection, table)
            else []
        )


def _write(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = rows or [{"status": "unavailable", "detail": "No retained records found."}]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def collect(paths: EvidencePaths) -> list[Path]:
    """Read retained SQLite/artifact state and write stable aggregate evidence CSVs."""
    reports, usage = (
        paths.state_dir / "reports.sqlite",
        paths.state_dir / "llm_usage.sqlite",
    )
    index, ui = paths.state_dir / "index.sqlite", paths.state_dir / "ui_runs.sqlite"
    acquisition = _query(
        reports,
        "publisher_download_route_history",
        """
        SELECT 'unattributed' publisher,route_family,route_kind,outcome,route_status,
        COUNT(*) sample_size,SUM(attempts) attempts,SUM(verified_successes) successes,
        'route history has no publisher, duration or cost fields' limitation
        FROM publisher_download_route_history GROUP BY route_family,route_kind,outcome,route_status
        ORDER BY route_family,route_kind,outcome""",
    )
    browser = _query(
        reports,
        "publisher_download_route_history",
        """
        SELECT route_family,COUNT(*) acquisition_records,SUM(attempts) attempts,
        SUM(json_array_length(route_steps_json)) browser_steps,
        SUM(CASE WHEN browser_had_structured_result THEN 1 ELSE 0 END) structured_browser_records,
        SUM(CASE WHEN onsite_capture_path<>'' AND onsite_capture_path IS NOT NULL THEN 1 ELSE 0 END) onsite_capture_records,
        'launch/navigation/screenshot/network/duration fields not retained' limitation
        FROM publisher_download_route_history GROUP BY route_family ORDER BY route_family""",
    )
    llm = _query(
        usage,
        "llm_usage_events",
        """
        SELECT substr(timestamp_utc,1,10) date,provider,model,action,semantic_task,prompt_namespace,
        provider_call_status,COUNT(*) request_count,SUM(input_tokens) input_tokens,
        SUM(cached_input_tokens) cached_input_tokens,SUM(output_tokens) output_tokens,SUM(total_tokens) total_tokens,
        SUM(estimated_cost_usd) estimated_cost_usd,SUM(CASE WHEN estimated_cost_usd IS NULL THEN 1 ELSE 0 END) unknown_pricing_count
        FROM llm_usage_events GROUP BY date,provider,model,action,semantic_task,prompt_namespace,provider_call_status
        ORDER BY date,provider,model,action,semantic_task""",
    )
    ocr = _query(
        usage,
        "llm_usage_events",
        """
        SELECT action,semantic_task,provider,model,provider_call_status,COUNT(*) request_count,
        SUM(input_tokens) input_tokens,SUM(output_tokens) output_tokens,SUM(estimated_cost_usd) estimated_cost_usd
        FROM llm_usage_events WHERE lower(action||' '||semantic_task||' '||prompt_namespace) LIKE '%ocr%'
        OR lower(action||' '||semantic_task||' '||prompt_namespace) LIKE '%vision%'
        OR lower(action||' '||semantic_task||' '||prompt_namespace) LIKE '%crop%'
        GROUP BY action,semantic_task,provider,model,provider_call_status ORDER BY action,semantic_task""",
    )
    lineage = _query(
        reports,
        "artifact_lineage_records",
        """
        SELECT r.artifact_kind,s.state,r.producer,COUNT(*) artifact_count,COUNT(DISTINCT r.report_id) report_count,
        'persisted lineage; reuse-decision event count is not retained' limitation
        FROM artifact_lineage_records r JOIN artifact_lineage_states s USING(artifact_id)
        GROUP BY r.artifact_kind,s.state,r.producer ORDER BY r.artifact_kind,s.state,r.producer""",
    )
    failures = _query(
        index,
        "workflow_control_observations",
        """
        SELECT workflow,step_name stage,error_code,error_retryable,error_severity,outcome,COUNT(*) record_count,
        SUM(retry_count) retry_count,MIN(observed_at_utc) first_seen,MAX(observed_at_utc) last_seen
        FROM workflow_control_observations WHERE error_code<>''
        GROUP BY workflow,stage,error_code,error_retryable,error_severity,outcome ORDER BY record_count DESC""",
    )
    failures += _query(
        ui,
        "ui_runs",
        """
        SELECT run_type workflow,'ui_run' stage,error_code,error_retryable,error_severity,status outcome,COUNT(*) record_count,
        0 retry_count,MIN(finished_at_utc) first_seen,MAX(finished_at_utc) last_seen
        FROM ui_runs WHERE error_code<>'' GROUP BY run_type,error_code,error_retryable,error_severity,status""",
    )
    wordpress = _query(
        index,
        "workflow_control_observations",
        """
        SELECT workflow,step_name,outcome,error_code,COUNT(*) record_count,SUM(retry_count) retry_count,
        MIN(latency_ms) min_latency_ms,MAX(latency_ms) max_latency_ms
        FROM workflow_control_observations WHERE workflow LIKE '%publish%' OR step_name LIKE '%wordpress%'
        GROUP BY workflow,step_name,outcome,error_code ORDER BY workflow,step_name,outcome""",
    )
    crop: list[dict[str, object]] = []
    for path in sorted(paths.artifact_dir.rglob("crop_refine.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        results = data.get("results", [])
        crop.append(
            {
                "report": path.parent.parent.name,
                "refinement_records": len(results),
                "valid_candidates": sum(
                    bool(x.get("is_valid_candidate"))
                    for x in results
                    if isinstance(x, dict)
                ),
                "model": data.get("_cache", {}).get("model", ""),
                "limitation": "No .qa.json visual-defect sidecars retained.",
            }
        )
    return [
        _write(paths.output_dir / name, rows)
        for name, rows in [
            ("acquisition_metrics.csv", acquisition),
            ("browser_metrics.csv", browser),
            ("llm_usage_metrics.csv", llm),
            ("ocr_vision_metrics.csv", ocr),
            ("lineage_reuse_metrics.csv", lineage),
            ("failure_metrics.csv", failures),
            ("wordpress_metrics.csv", wordpress),
            ("crop_quality_metrics.csv", crop),
        ]
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", default="state")
    parser.add_argument("--artifact-dir", default="out")
    parser.add_argument("--output-dir", default="out/cto-review-evidence")
    args = parser.parse_args()
    for path in collect(
        EvidencePaths(
            Path(args.state_dir), Path(args.artifact_dir), Path(args.output_dir)
        )
    ):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
