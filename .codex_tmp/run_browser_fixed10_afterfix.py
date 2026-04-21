from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import traceback
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

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


SOURCE_ARTIFACT = ROOT / "out" / "browser_downloads" / "browser_use_random_report_probe_20260421_fixed10.json"
STATE_SOURCE_DB = ROOT / "state" / "reports.sqlite"
IDENTITY_SOURCE = ROOT / "src" / "config" / "browser_download_identity.yaml"
OUTPUT_ROOT = ROOT / "out" / "browser_downloads"
RUN_STAMP = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
RUN_LABEL = "".join(
    char
    if char.isalnum() or char in {"_", "-"}
    else "_"
    for char in os.environ.get("BROWSER_PROBE_RUN_LABEL", "afterfix").strip()
)
RUN_LABEL = RUN_LABEL or "afterfix"
STATE_DIR = OUTPUT_ROOT / f"verification_fixed10_{RUN_LABEL}_state_{RUN_STAMP}"
DOWNLOAD_DIR = OUTPUT_ROOT / f"verification_fixed10_{RUN_LABEL}_downloads_{RUN_STAMP}"
RESULT_PATH = OUTPUT_ROOT / f"browser_use_random_report_probe_20260421_{RUN_LABEL}_{RUN_STAMP}.json"
LATEST_PATH = OUTPUT_ROOT / f"browser_use_random_report_probe_20260421_{RUN_LABEL}_latest.txt"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _build_trace(source_row: dict[str, object]) -> PublisherInventoryCandidateTrace:
    source_page_url = str(source_row.get("source_page_url") or "").strip()
    return PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url=str(
            source_row.get("normalized_landing_page_url")
            or source_row.get("landing_page_url")
            or ""
        ).strip(),
        title=str(source_row.get("report_name") or "").strip(),
        discovered_on_page_number=int(source_row.get("discovered_on_page_number") or 1),
        source_page_urls=[source_page_url] if source_page_url else [],
        discovery_provenances=[],
        pdf_url=None,
        published_at_text=None,
        max_confidence=0.8,
    )


def _write_artifact(payload: dict[str, object]) -> None:
    RESULT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    LATEST_PATH.write_text(str(RESULT_PATH), encoding="utf-8")


def _parse_index_filter() -> set[int] | None:
    raw = os.environ.get("BROWSER_PROBE_INDICES", "").strip()
    if not raw:
        return None
    indexes: set[int] = set()
    for token in raw.replace(";", ",").split(","):
        value = token.strip()
        if not value:
            continue
        indexes.add(int(value))
    return indexes


def _clear_route_memory(db_path: Path, rows: list[dict[str, object]]) -> dict[str, int]:
    target_urls = {
        normalize_url(
            str(
                row.get("normalized_landing_page_url")
                or row.get("landing_page_url")
                or ""
            ).strip()
        )
        for row in rows
        if str(row.get("normalized_landing_page_url") or row.get("landing_page_url") or "").strip()
    }
    target_urls.discard("")
    if not target_urls:
        return {"history_deleted": 0, "legacy_publishers_cleared": 0}
    with sqlite3.connect(db_path) as conn:
        history_deleted = 0
        for normalized_url in sorted(target_urls):
            cursor = conn.execute(
                "DELETE FROM publisher_download_route_history WHERE normalized_url = ?",
                (normalized_url,),
            )
            history_deleted += int(cursor.rowcount or 0)
        publisher_rows = conn.execute(
            "SELECT id, insights_url FROM publishers WHERE insights_url <> ''"
        ).fetchall()
        publisher_ids = [
            int(row_id)
            for row_id, insights_url in publisher_rows
            if normalize_url(str(insights_url or "").strip()) in target_urls
        ]
        legacy_cleared = 0
        for publisher_id in publisher_ids:
            cursor = conn.execute(
                """
                UPDATE publishers
                SET
                    download_route_kind = NULL,
                    download_route_summary = NULL,
                    download_route_outcome = NULL,
                    download_route_last_downloaded_file_path = NULL,
                    download_route_last_final_page_url = NULL,
                    download_route_updated_at = NULL
                WHERE id = ?
                """,
                (publisher_id,),
            )
            legacy_cleared += int(cursor.rowcount or 0)
        conn.commit()
    return {
        "history_deleted": history_deleted,
        "legacy_publishers_cleared": legacy_cleared,
    }


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STATE_SOURCE_DB, STATE_DIR / "reports.sqlite")
    shutil.copy2(IDENTITY_SOURCE, STATE_DIR / "browser_download_identity.yaml")
    source_payload = json.loads(SOURCE_ARTIFACT.read_text(encoding="utf-8"))
    index_filter = _parse_index_filter()
    full_sample = list(source_payload["sample"])
    if index_filter is None:
        selected_sample = full_sample
    else:
        selected_sample = [
            row
            for index, row in enumerate(full_sample, start=1)
            if index in index_filter
        ]
    route_memory_cleanup = _clear_route_memory(
        STATE_DIR / "reports.sqlite",
        [dict(row) for row in selected_sample],
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id=f"browser_use_random_probe_20260421_{RUN_LABEL}_{RUN_STAMP}",
        task_id="browser_use_random_probe_afterfix_setup",
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
        reports_db=str(STATE_DIR / "reports.sqlite"),
        identity_config_path=str(STATE_DIR / "browser_download_identity.yaml"),
    )
    result_payload: dict[str, object] = {
        "schema_version": "1.0",
        "run_started_at_utc": _utc_now(),
        "run_finished_at_utc": None,
        "source_artifact": str(SOURCE_ARTIFACT),
        "run_label": RUN_LABEL,
        "index_filter": sorted(index_filter) if index_filter is not None else None,
        "route_memory_cleanup": route_memory_cleanup,
        "settings_override": {
            "timeout_seconds": settings.timeout_seconds,
            "max_steps": settings.max_steps,
            "model": settings.model,
            "headed": settings.headed,
            "output_dir": settings.output_dir,
            "reports_db": settings.reports_db,
            "identity_config_path": settings.identity_config_path,
        },
        "sample": selected_sample,
        "runs": [],
    }
    _write_artifact(result_payload)
    for run_index, source_row in enumerate(selected_sample, start=1):
        started = datetime.now(UTC)
        row = dict(source_row)
        host = str(row.get("source_domain") or "unknown").replace(".", "_")
        original_index = full_sample.index(source_row) + 1
        task_id = f"browser_use_random_probe_20260421_{RUN_LABEL}_{original_index:02d}_{host}"
        print(
            f"[{_utc_now()}] start {run_index}/{len(selected_sample)} "
            f"(sample {original_index}/10) {row.get('source_domain')} {row.get('report_name')}",
            flush=True,
        )
        run_record: dict[str, object] = {
            "index": original_index,
            "run_index": run_index,
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
                    run_id=f"browser_use_random_probe_20260421_{RUN_LABEL}_{RUN_STAMP}",
                    task_id=task_id,
                    span_id="run_report_download",
                ),
            )
            run_record["status"] = "result"
            run_record["result"] = asdict(result)
            print(
                f"[{_utc_now()}] result {run_index}/{len(selected_sample)} "
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
                f"[{_utc_now()}] app_error {run_index}/{len(selected_sample)} "
                f"{exc.code}: {exc.message}",
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
                f"[{_utc_now()}] exception {run_index}/{len(selected_sample)} "
                f"{type(exc).__name__}: {exc}",
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
