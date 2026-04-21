from __future__ import annotations

import json
import os
import random
import shutil
import sqlite3
import sys
import traceback
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.browser_download import ReportDownloadOrchestratorRequest
from src.contracts.config import ConfigLoadRequest
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
from src.contracts.run_context import RunContext
from src.orchestrators.report_download_orchestrator import run_report_download
from src.services.config_service import load_browser_download_settings
from src.utils.errors import AppError
from src.utils.url_utils import normalize_url

STATE_SOURCE_DB = ROOT / "state" / "reports.sqlite"
IDENTITY_SOURCE = ROOT / "src" / "config" / "browser_download_identity.yaml"
OUTPUT_ROOT = ROOT / "out" / "browser_downloads"
RUN_STAMP = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
RUN_LABEL = "".join(
    char if char.isalnum() or char in {"_", "-"} else "_"
    for char in os.environ.get("BROWSER_PROBE_RUN_LABEL", "random10").strip()
) or "random10"
RANDOM_SEED = int(
    os.environ.get(
        "BROWSER_PROBE_RANDOM_SEED",
        datetime.now(UTC).strftime("%Y%m%d%H%M%S"),
    )
)
STATE_DIR = OUTPUT_ROOT / f"verification_{RUN_LABEL}_state_{RUN_STAMP}"
DOWNLOAD_DIR = OUTPUT_ROOT / f"verification_{RUN_LABEL}_downloads_{RUN_STAMP}"
RESULT_PATH = OUTPUT_ROOT / f"browser_use_random_report_probe_{RUN_LABEL}_{RUN_STAMP}.json"
LATEST_PATH = OUTPUT_ROOT / f"browser_use_random_report_probe_{RUN_LABEL}_latest.txt"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_artifact(payload: dict[str, object]) -> None:
    RESULT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    LATEST_PATH.write_text(str(RESULT_PATH), encoding="utf-8")


def _select_random_domain_distinct_sample(db_path: Path) -> list[dict[str, object]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    id,
                    source_domain,
                    report_name,
                    landing_page_url,
                    normalized_landing_page_url,
                    source_status,
                    source_page_url,
                    publisher_name,
                    discovered_on_page_number
                FROM report_sources
                WHERE source_status = 'discovered'
                  AND landing_page_url <> ''
                  AND lower(landing_page_url) LIKE 'http%'
                  AND lower(landing_page_url) NOT LIKE '%.pdf%'
                ORDER BY id ASC
                """
            ).fetchall()
        ]
    rng = random.Random(RANDOM_SEED)
    rng.shuffle(rows)
    sample: list[dict[str, object]] = []
    seen_domains: set[str] = set()
    for row in rows:
        domain = str(row.get("source_domain") or "").strip().casefold()
        url = str(
            row.get("normalized_landing_page_url") or row.get("landing_page_url") or ""
        ).strip()
        if not domain or not url:
            continue
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        sample.append(row)
        if len(sample) == 10:
            return sample
    raise RuntimeError(
        f"Only found {len(sample)} domain-distinct non-PDF discovered candidates"
    )


def _build_trace(source_row: dict[str, object]) -> PublisherInventoryCandidateTrace:
    source_page_url = str(source_row.get("source_page_url") or "").strip()
    canonical_url = str(
        source_row.get("normalized_landing_page_url")
        or source_row.get("landing_page_url")
        or ""
    ).strip()
    return PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url=canonical_url,
        title=str(source_row.get("report_name") or "").strip(),
        discovered_on_page_number=int(source_row.get("discovered_on_page_number") or 1),
        source_page_urls=[source_page_url] if source_page_url else [],
        discovery_provenances=[],
        pdf_url=None,
        published_at_text=None,
        max_confidence=0.8,
    )


def _route_memory_count(db_path: Path, sample: list[dict[str, object]]) -> int:
    normalized_urls = [
        normalize_url(
            str(
                row.get("normalized_landing_page_url")
                or row.get("landing_page_url")
                or ""
            ).strip()
        )
        for row in sample
    ]
    normalized_urls = [url for url in normalized_urls if url]
    if not normalized_urls:
        return 0
    with sqlite3.connect(db_path) as conn:
        total = 0
        for normalized_url in normalized_urls:
            total += int(
                conn.execute(
                    "SELECT COUNT(*) FROM publisher_download_route_history WHERE normalized_url = ?",
                    (normalized_url,),
                ).fetchone()[0]
            )
    return total


def _settings_payload(settings: Any) -> dict[str, object]:
    return {
        "timeout_seconds": settings.timeout_seconds,
        "max_steps": settings.max_steps,
        "model": settings.model,
        "headed": settings.headed,
        "output_dir": settings.output_dir,
        "state_db": settings.state_db,
        "reports_db": settings.reports_db,
        "identity_config_path": settings.identity_config_path,
    }


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    reports_db = STATE_DIR / "reports.sqlite"
    identity_path = STATE_DIR / "browser_download_identity.yaml"
    shutil.copy2(STATE_SOURCE_DB, reports_db)
    shutil.copy2(IDENTITY_SOURCE, identity_path)

    sample = _select_random_domain_distinct_sample(reports_db)
    ctx = RunContext(
        schema_version="1.0",
        run_id=f"browser_use_random_probe_{RUN_LABEL}_{RUN_STAMP}",
        task_id=f"browser_use_random_probe_{RUN_LABEL}_setup",
        span_id="load_settings",
    )
    base_settings = load_browser_download_settings(
        ConfigLoadRequest(schema_version="1.0", path=""),
        ctx,
    )
    settings = replace(
        base_settings,
        timeout_seconds=120.0,
        max_steps=17,
        model="google/gemini-2.5-flash-lite",
        headed=True,
        output_dir=str(DOWNLOAD_DIR),
        state_db=str(STATE_DIR / "browser_download_state.sqlite"),
        reports_db=str(reports_db),
        identity_config_path=str(identity_path),
    )
    result_payload: dict[str, object] = {
        "schema_version": "1.0",
        "run_label": RUN_LABEL,
        "random_seed": RANDOM_SEED,
        "run_started_at_utc": _utc_now(),
        "run_finished_at_utc": None,
        "source_db": str(STATE_SOURCE_DB),
        "copied_reports_db": str(reports_db),
        "route_memory_history_rows_in_sample": _route_memory_count(reports_db, sample),
        "settings_override": _settings_payload(settings),
        "sample": sample,
        "runs": [],
    }
    _write_artifact(result_payload)
    for index, source_row in enumerate(sample, start=1):
        started = datetime.now(UTC)
        row = dict(source_row)
        host = str(row.get("source_domain") or "unknown").replace(".", "_")
        task_id = f"browser_use_random_probe_{RUN_LABEL}_{index:02d}_{host}"
        print(
            f"[{_utc_now()}] start {index}/10 "
            f"{row.get('source_domain')} {row.get('report_name')}",
            flush=True,
        )
        run_record: dict[str, object] = {
            "index": index,
            "task_id": task_id,
            "source_row": row,
            "started_at_utc": started.isoformat().replace("+00:00", "Z"),
            "finished_at_utc": None,
            "elapsed_seconds": None,
            "status": None,
            "result": None,
            "error": None,
        }
        try:
            result = run_report_download(
                ReportDownloadOrchestratorRequest(
                    schema_version="1.0",
                    url=str(row.get("landing_page_url") or "").strip(),
                    settings=settings,
                    state_db=settings.state_db,
                    reports_db=settings.reports_db,
                    delivery_email=None,
                    candidate_trace=_build_trace(row),
                    publisher_discovery_route_kind=None,
                    publisher_recommended_discovery_route_kind=None,
                ),
                ctx=RunContext(
                    schema_version="1.0",
                    run_id=f"browser_use_random_probe_{RUN_LABEL}_{RUN_STAMP}",
                    task_id=task_id,
                    span_id="run_report_download",
                ),
            )
            run_record["status"] = "result"
            run_record["result"] = asdict(result)
            print(
                f"[{_utc_now()}] result {index}/10 "
                f"{result.outcome} {result.route_kind} {result.route_family}",
                flush=True,
            )
        except AppError as exc:
            run_record["status"] = "app_error"
            run_record["error"] = {
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
                "severity": exc.severity,
                "context": exc.context,
            }
            print(
                f"[{_utc_now()}] app_error {index}/10 {exc.code}: {exc.message}",
                flush=True,
            )
        except Exception as exc:
            run_record["status"] = "exception"
            run_record["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
            print(
                f"[{_utc_now()}] exception {index}/10 {type(exc).__name__}: {exc}",
                flush=True,
            )
        finished = datetime.now(UTC)
        run_record["finished_at_utc"] = finished.isoformat().replace("+00:00", "Z")
        run_record["elapsed_seconds"] = round((finished - started).total_seconds(), 3)
        result_payload["runs"].append(run_record)
        _write_artifact(result_payload)
    result_payload["run_finished_at_utc"] = _utc_now()
    _write_artifact(result_payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
