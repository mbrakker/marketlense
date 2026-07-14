# ruff: noqa: E501

import csv
import sqlite3
from pathlib import Path

from scripts.quality.collect_cto_review_evidence import EvidencePaths, collect


def test_collect_reads_local_state_and_writes_aggregate_csvs(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    with sqlite3.connect(state / "reports.sqlite") as db:
        db.execute(
            "CREATE TABLE publisher_download_route_history (route_family,route_kind,outcome,route_status,attempts,verified_successes,route_steps_json,browser_had_structured_result,onsite_capture_path)"
        )
        db.execute(
            "INSERT INTO publisher_download_route_history VALUES ('direct','pdf','downloaded','verified',2,2,'[]',0,'')"
        )
        db.execute(
            "CREATE TABLE artifact_lineage_records (artifact_id,artifact_kind,report_id,producer)"
        )
        db.execute("CREATE TABLE artifact_lineage_states (artifact_id,state)")
        db.execute(
            "INSERT INTO artifact_lineage_records VALUES ('a','source_pdf','r','selection')"
        )
        db.execute("INSERT INTO artifact_lineage_states VALUES ('a','active')")
    with sqlite3.connect(state / "llm_usage.sqlite") as db:
        db.execute(
            "CREATE TABLE llm_usage_events (timestamp_utc,provider,model,action,semantic_task,prompt_namespace,provider_call_status,input_tokens,cached_input_tokens,output_tokens,total_tokens,estimated_cost_usd)"
        )
        db.execute(
            "INSERT INTO llm_usage_events VALUES ('2026-01-01T00:00:00Z','openai','m','openai_ocr_pdf','ocr','','completed',1,0,2,3,0.1)"
        )
    output = tmp_path / "evidence"
    collect(EvidencePaths(state, tmp_path / "artifacts", output))
    with (output / "acquisition_metrics.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert next(csv.DictReader(handle))["attempts"] == "2"
    with (output / "ocr_vision_metrics.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert next(csv.DictReader(handle))["request_count"] == "1"
