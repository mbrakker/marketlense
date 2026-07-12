from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.llm_usage import (
    LLMUsageExportRebuildRequest,
    LLMUsageLedgerAppendRequest,
    LLMUsageLedgerEntry,
)
from src.contracts.run_context import RunContext
from src.services.llm_usage_ledger_service import append_usage, rebuild_usage_exports


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a non-secret canonical LLM-accounting corpus from retained events."
    )
    parser.add_argument("--fixture-json", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--daily", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.fixture_json).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0" or not isinstance(
        payload.get("records"), list
    ):
        raise ValueError("Unsupported retained accounting corpus fixture")
    ctx = RunContext(
        schema_version="1.0",
        run_id="llm-accounting-corpus",
        task_id="build",
        span_id="retained-events",
    )
    responses = []
    for raw in payload["records"]:
        entry = LLMUsageLedgerEntry(
            schema_version="1.0",
            timestamp_utc=str(raw["timestamp_utc"]),
            provider=str(raw["provider"]),
            action=str(raw["action"]),
            run_id=str(raw["run_id"]),
            task_id=str(raw["task_id"]),
            span_id=str(raw["span_id"]),
            trace_id=str(raw["trace_id"]),
            model=str(raw["model"]),
            request_id=str(raw["request_id"]),
            publisher_name="",
            report_name="",
            source_url="",
            input_tokens=int(raw["input_tokens"]),
            output_tokens=int(raw["output_tokens"]),
            total_tokens=int(raw["total_tokens"]),
            cached_input_tokens=raw["cached_input_tokens"],
            tool_calls=int(raw["tool_calls"]),
            estimated_cost_usd=float(raw["estimated_cost_usd"]),
            prompt_namespace=str(raw["prompt_namespace"]),
            prompt_hash=str(raw["prompt_hash"]),
            provider_decision=str(raw["provider_decision"]),
            cache_decision=str(raw["cache_decision"]),
            temperature=None,
            seed=None,
            timeout_seconds=None,
            call_ordinal=int(raw["call_ordinal"]),
            parse_status=str(raw["parse_status"]),
            schema_validation_status=str(raw["schema_validation_status"]),
            error_stage=str(raw["error_stage"]),
            error_code=str(raw["error_code"]),
        )
        responses.append(
            append_usage(
                LLMUsageLedgerAppendRequest(
                    schema_version="1.0", db_path=args.db, entry=entry
                ),
                ctx,
            )
        )
    replay_index = int(payload["replay_record_index"])
    replay = responses[replay_index]
    replayed = append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=args.db,
            entry=LLMUsageLedgerEntry(
                **{
                    **payload["records"][replay_index],
                    "schema_version": "1.0",
                    "publisher_name": "",
                    "report_name": "",
                    "source_url": "",
                    "temperature": None,
                    "seed": None,
                    "timeout_seconds": None,
                    "metadata": {},
                }
            ),
        ),
        ctx,
    )
    if replayed.inserted or replayed.event_key != replay.event_key:
        raise RuntimeError("Retained accounting replay was not idempotently suppressed")
    rebuild_usage_exports(
        LLMUsageExportRebuildRequest(
            schema_version="1.0",
            db_path=args.db,
            ledger_path=args.ledger,
            daily_path=args.daily,
        ),
        ctx,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
