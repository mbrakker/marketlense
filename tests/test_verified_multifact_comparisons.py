"""P1-B structural regressions and opt-in, retained-fact semantic canary.

Structural tests use synthetic fixtures and prove rejection before provider I/O.
Live tests require ML_MULTIFACT_LIVE=1 and ML_MULTIFACT_ARTIFACTS pointing to
retained artifacts.json. They never fabricate or modify canonical live facts.
"""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from src.contracts.config import ConfigLoadRequest
from src.contracts.validation import ValidationRequest
from src.generators.validation.grounding import run_grounding_check
from src.services import config_service, llm_service, prompt_service
from src.utils.errors import AppError
from src.utils.verified_facts import (
    validate_verified_artifact_bindings,
    validated_verified_facts,
)
from tests._test_validation_generator._shared import _ctx, _settings
from tests.test_verified_facts_validation_authority import _fact, _report


def _comparison(facts, text):
    ids = [f"verified-fact:{fact['fact_id']}" for fact in facts]
    return {
        "verified_facts": deepcopy(facts),
        "insights_final": [
            {
                "id": "comparison",
                "text": text,
                "evidence_id": ids[0],
                "evidence_ids": ids,
                "pages": sorted(
                    {p for f in facts for p in f["supporting_physical_pages"]}
                ),
                "evidence_spans": [
                    {
                        "evidence_id": eid,
                        "source_pack": "verified_facts",
                        "page": fact["supporting_physical_pages"][0],
                        "text": fact["statement"],
                        "source_identity": fact["source_identity"],
                    }
                    for eid, fact in zip(ids, facts, strict=True)
                ],
            }
        ],
        "summary": {},
        "quotes_final": [],
        "key_figures": [],
    }


def _request(artifacts, case):
    return ValidationRequest(
        schema_version="1.0",
        report_id=f"multifact-{case}",
        report=_report(),
        artifacts=artifacts,
        evidence_packs={},
        validation_mode="verified_facts",
        source_id=artifacts["verified_facts"][0]["source_identity"],
    )


class _NoProvider:
    def __getattr__(self, name):
        pytest.fail(f"Invalid secondary reached provider/prompt boundary: {name}")


@pytest.mark.parametrize("defect", ["missing", "quarantined", "wrong-page"])
def test_secondary_defect_rejected_before_grounding_provider(tmp_path, defect):
    first = _fact()
    second = deepcopy(first)
    second.update(fact_id="secondary", supporting_physical_pages=[7])
    second["provenance"] = {
        "inspected_physical_pages": [7],
        "source_truth_notes_by_page": {"7": second["statement"]},
    }
    artifacts = _comparison([first, second], "A comparison requiring both facts.")
    if defect == "missing":
        artifacts["verified_facts"].pop()
    elif defect == "quarantined":
        artifacts["verified_facts"][1]["verification_outcome"] = "quarantined"
    else:
        # Page 4 is valid for the primary and in the union, but not the secondary.
        artifacts["insights_final"][0]["evidence_spans"][1]["page"] = 4
    with pytest.raises(AppError) as caught:
        facts = validated_verified_facts(artifacts)
        validate_verified_artifact_bindings(artifacts, facts)
    assert caught.value.code == "verified_fact_snapshot_invalid"
    assert caught.value.retryable is False
    with pytest.raises(AppError) as grounded:
        run_grounding_check(
            request=_request(artifacts, defect),
            settings=_settings(tmp_path),
            grounding_use_vector_store=False,
            evidence_texts=[],
            evidence_windows=[],
            prompt_client=_NoProvider(),
            openai_client=_NoProvider(),
            ctx=_ctx(),
        )
    assert grounded.value.code == "verified_fact_snapshot_invalid"


FINANCE = "finance-global-growth-and-seasonality"
REGION = "finance-regional-growth-contrast"
ECOM = "ecommerce-install-session-divergence"
GAMING = "gaming-retention-all"
CPI = "ecommerce-cpi-subvertical-divergence"
CASES = [
    (
        "different-populations",
        (FINANCE, ECOM),
        "Global finance app installs fell 4% and 10% in 2025, giving a combined "
        "finance install decline of 14%.",
        False,
    ),
    (
        "incompatible-periods",
        (FINANCE, ECOM),
        "In February 2025, global finance and e-commerce app installs fell 14% "
        "and 10% year over year, respectively.",
        False,
    ),
    (
        "region-as-global",
        (REGION, ECOM),
        "Globally in 2025, finance app installs grew 76%, while e-commerce app "
        "installs fell 10% year over year.",
        False,
    ),
    (
        "installs-sessions-conflated",
        (REGION, ECOM),
        "LATAM finance app sessions grew 76% year over year in 2024-2025, "
        "while global e-commerce sessions increased 5% in 2025.",
        False,
    ),
    (
        "irrelevant-secondary",
        (ECOM, GAMING),
        "Global e-commerce installs fell 10% in 2025, while global finance "
        "installs fell 4% year over year.",
        False,
    ),
    (
        "compatible-comparison",
        (FINANCE, ECOM),
        "Global finance app installs fell 4% year over year in 2025, compared "
        "with a 10% decline for global e-commerce app installs in 2025.",
        True,
    ),
    (
        "false-causality",
        (CPI, ECOM),
        "The decline in global e-commerce app CPI from $1.00 in 2024 to $0.98 "
        "in 2025 caused global e-commerce app sessions to increase 5% in 2025.",
        False,
    ),
]


class _BoundedProductionClient:
    """Delegate real responses unchanged; count calls, including repair calls."""

    def __init__(self, client):
        self.client = client
        self.calls = 0

    def openai_chat_json(self, request, ctx):
        if self.calls >= 10:
            raise AppError(
                code="canary_call_budget",
                message="Ten-call cap reached",
                retryable=False,
                severity="error",
            )
        self.calls += 1
        return self.client.openai_chat_json(request, ctx)


@pytest.fixture(scope="module")
def live_runtime(tmp_path_factory):
    if os.environ.get("ML_MULTIFACT_LIVE") != "1":
        pytest.skip("Set ML_MULTIFACT_LIVE=1 for bounded provider verification")
    path = Path(os.environ.get("ML_MULTIFACT_ARTIFACTS", ""))
    if not path.is_file():
        pytest.skip("ML_MULTIFACT_ARTIFACTS must identify retained artifacts.json")
    from dotenv import load_dotenv

    load_dotenv(override=False)
    root = tmp_path_factory.mktemp("multifact-live")
    ctx = replace(_ctx(), run_id=root.name, task_id="p1-b")
    settings = config_service.load_settings(
        ConfigLoadRequest(schema_version="1.0", path="src/config/app.yaml"),
        ctx,
    )
    settings = replace(
        settings,
        output_dir=str(root / "out"),
        cache_dir=str(root / "cache"),
        state_db=str(root / "state.sqlite"),
        reports_db=str(root / "reports.sqlite"),
        signal_store_db=str(root / "signals.sqlite"),
        cost_ledger_path=str(root / "cost-ledger.jsonl"),
        cost_daily_path=str(root / "cost-daily.json"),
        usage_db_path=str(root / "usage.sqlite"),
    )
    facts = validated_verified_facts(json.loads(path.read_text(encoding="utf-8")))
    client = _BoundedProductionClient(
        llm_service.build_client_for_settings(
            settings,
            scope="validation",
            rate_limit_max_in_flight=settings.validation_grounding_global_max_in_flight,
            rate_limit_min_interval_ms=settings.validation_grounding_global_min_interval_ms,
        )
    )
    (root / "source.json").write_text(
        json.dumps(
            {
                "artifacts_path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "fact_ids": list(facts),
                "scope": "component grounding; no E2E or publication",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Live evidence directory: {root}")
    yield facts, settings, client, ctx, root
    (root / "calls.json").write_text(
        json.dumps({"calls": client.calls, "cap": 10}), encoding="utf-8"
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "case,ids,text,expected_pass", CASES, ids=[c[0] for c in CASES]
)
def test_retained_multifact_semantic_comparison(
    live_runtime, case, ids, text, expected_pass
):
    facts, settings, client, ctx, root = live_runtime
    artifacts = _comparison([facts[key] for key in ids], text)
    # Physical compatibility alone is deliberately not semantic evidence.
    validate_verified_artifact_bindings(artifacts, validated_verified_facts(artifacts))
    before = client.calls
    try:
        issues = run_grounding_check(
            request=_request(artifacts, case),
            settings=settings,
            grounding_use_vector_store=False,
            evidence_texts=[],
            evidence_windows=[],
            prompt_client=prompt_service,
            openai_client=client,
            ctx=replace(ctx, task_id=case),
        )
    except AppError as exc:
        (root / f"{case}.json").write_text(
            json.dumps(
                {
                    "error_code": exc.code,
                    "calls": client.calls - before,
                }
            ),
            encoding="utf-8",
        )
        raise
    (root / f"{case}.json").write_text(
        json.dumps(
            {
                "case": case,
                "fact_ids": ids,
                "claim": text,
                "expected_pass": expected_pass,
                "calls": client.calls - before,
                "issues": [asdict(issue) for issue in issues],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    assert client.calls > before, (
        "A cached or deterministic result is not live semantic evidence"
    )
    if expected_pass:
        assert issues == []
    else:
        assert any(
            issue.severity == "error"
            and "grounding" in issue.rule_id
            and issue.violation_type
            in {"contradicted", "not_established", "unsupported_factual_claim"}
            and "comparison" in issue.affected_section
            for issue in issues
        ), [asdict(issue) for issue in issues]
