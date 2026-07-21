from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from src.contracts.llm_usage import (
    LLMUsageExportRebuildRequest,
    LLMUsageLedgerAppendRequest,
    LLMUsageLedgerReconciliationRequest,
    LLMUsageSpendGuardrailRequest,
)
from src.services import llm_usage_ledger_service as svc
from src.utils.errors import AppError
from tests.test_llm_usage_ledger_service import _ctx, _entry


def test_concurrent_projection_generations_preserve_one_consistent_checkpoint(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    ledger_path = tmp_path / "cost-ledger.jsonl"
    daily_path = tmp_path / "cost-daily.json"
    for ordinal in (0, 1):
        svc.append_usage(
            LLMUsageLedgerAppendRequest(
                schema_version="1.0",
                db_path=str(db_path),
                entry=replace(_entry(), call_ordinal=ordinal),
            ),
            _ctx(),
        )

    request = LLMUsageExportRebuildRequest(
        schema_version="1.0",
        db_path=str(db_path),
        ledger_path=str(ledger_path),
        daily_path=str(daily_path),
    )

    def rebuild_one() -> tuple[str, int]:
        try:
            response = svc.rebuild_usage_exports(request, _ctx())
            return ("ok", response.generation_id)
        except AppError as exc:
            return (exc.code, 0)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: rebuild_one(), range(2)))

    assert any(result[0] == "ok" for result in results)
    assert all(result[0] in {"ok", "llm_usage_projection_busy"} for result in results)
    reconciled = svc.reconcile_usage_export(
        LLMUsageLedgerReconciliationRequest(
            schema_version="1.0",
            db_path=str(db_path),
            ledger_path=str(ledger_path),
            daily_path=str(daily_path),
        ),
        _ctx(),
    )
    assert reconciled.matches is True


def test_daily_spend_guardrail_initializes_a_missing_database_parent(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "new" / "ledger" / "usage.sqlite"

    response = svc.evaluate_daily_spend_guardrail(
        LLMUsageSpendGuardrailRequest(
            schema_version="1.0", db_path=str(db_path), warn_usd=1.0
        ),
        _ctx(),
    )

    assert db_path.is_file()
    assert response.canonical_spend_usd == 0.0
    assert response.decision == "allow"
