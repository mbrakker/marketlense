from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.llm_usage import LLMUsageLedgerReconciliationRequest
from src.contracts.run_context import RunContext
from src.services.llm_usage_ledger_service import reconcile_usage_export


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile canonical LLM accounting with its derived exports."
    )
    parser.add_argument("--db", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--daily", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()
    ctx = RunContext(
        schema_version="1.0",
        run_id="llm-accounting-reconciliation",
        task_id="release-evidence",
        span_id="canonical-ledger",
    )
    response = reconcile_usage_export(
        LLMUsageLedgerReconciliationRequest(
            schema_version="1.0",
            db_path=args.db,
            ledger_path=args.ledger,
            daily_path=args.daily,
            repair=args.repair,
        ),
        ctx,
    )
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "passed" if response.matches else "failed",
        "reconciliation": asdict(response),
    }
    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    return 0 if response.matches else 1


if __name__ == "__main__":
    raise SystemExit(main())
