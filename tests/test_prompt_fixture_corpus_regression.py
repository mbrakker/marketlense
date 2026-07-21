from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts.ci.check_prompt_fixture_regression import (
    PromptRegressionAllowlistEntry,
    _load_pricing,
    compare_prompt_fixture_metrics,
)
from scripts.quality.prompt_fixture_corpus_metrics import (
    collect_prompt_fixture_corpus_metrics,
)
from src.services import prompt_service
from src.utils.costing import estimate_text_tokens


def _write_prompt_namespace(
    prompts_root: Path, namespace: str, system: str, user: str
) -> None:
    namespace_dir = prompts_root / namespace
    namespace_dir.mkdir(parents=True, exist_ok=True)
    (namespace_dir / "system.yaml").write_text(f'text: "{system}"\n', encoding="utf-8")
    (namespace_dir / "user.yaml").write_text(f'text: "{user}"\n', encoding="utf-8")


def test_collect_prompt_fixture_corpus_metrics_aggregates_runtime_tokens_and_cost(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    prompts_root = tmp_path / "prompts"
    _write_prompt_namespace(
        prompts_root,
        "alpha",
        "hello {{ required_name }}",
        "task {{ report_topic }}",
    )
    fixture_path = prompts_root / "_dry_run_fixtures.yaml"
    fixture_path.write_text(
        "\n".join(
            [
                'schema_version: "1.0"',
                "fixtures:",
                '  - namespace: "alpha"',
                '    family: "report"',
                '    model: "openai/gpt-5-mini"',
                "    test_only_execution_override: true",
                "    benchmark:",
                "      expected_output_tokens: 120",
                "      expected_browser_attempts: 1",
                "    system_variables:",
                '      required_name: "Ada"',
                "    user_variables:",
                '      report_topic: "wallets"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    external_boundary_mocks_only.setattr(prompt_service, "PROMPTS_ROOT", prompts_root)
    external_boundary_mocks_only.setattr(
        prompt_service,
        "PROMPT_DRY_RUN_FIXTURE_PATH",
        fixture_path,
    )

    metrics = collect_prompt_fixture_corpus_metrics(
        pricing={
            "gpt-5-mini": {
                "input_tokens_per_1k_usd": 0.00025,
                "output_tokens_per_1k_usd": 0.002,
                "tool_call_usd": 0.0,
            }
        },
        iterations=1,
        force_reload=True,
    )

    row = metrics.namespaces["alpha"]
    expected_input_tokens = estimate_text_tokens("hello Ada\n") + estimate_text_tokens(
        "task wallets\n"
    )

    assert metrics.fixture_count == 1
    assert row.input_tokens == expected_input_tokens
    assert row.expected_output_tokens == 120
    assert row.total_tokens == expected_input_tokens + 120
    assert row.expected_browser_attempts == 1
    assert row.estimated_cost_usd > 0.0
    assert metrics.families["report"].estimated_cost_usd == row.estimated_cost_usd
    assert metrics.totals.total_tokens == row.total_tokens
    assert row.runtime_ms >= 0.0


def test_prompt_fixture_regression_allowlist_requires_unexpired_bound() -> None:
    baseline = {
        "families": {
            "report": {
                "namespace_count": 1,
                "runtime_ms": 12.0,
                "total_tokens": 200.0,
                "expected_ocr_calls": 0.0,
                "expected_browser_attempts": 0.0,
                "estimated_cost_usd": 0.01,
            }
        },
        "namespaces": {"alpha": {"family": "report"}},
        "totals": {
            "runtime_ms": 12.0,
            "total_tokens": 200.0,
            "expected_ocr_calls": 0.0,
            "expected_browser_attempts": 0.0,
            "estimated_cost_usd": 0.01,
        },
    }
    current = {
        "families": {
            "report": {
                "namespace_count": 1,
                "runtime_ms": 12.0,
                "total_tokens": 260.0,
                "expected_ocr_calls": 0.0,
                "expected_browser_attempts": 0.0,
                "estimated_cost_usd": 0.01,
            }
        },
        "namespaces": {"alpha": {"family": "report"}},
        "totals": {
            "runtime_ms": 12.0,
            "total_tokens": 260.0,
            "expected_ocr_calls": 0.0,
            "expected_browser_attempts": 0.0,
            "estimated_cost_usd": 0.01,
        },
    }
    allowlist = (
        PromptRegressionAllowlistEntry(
            pattern="*.total_tokens",
            owner="quality",
            reason="intentional token budget increase",
            expires_on=date(2026, 5, 1),
            max_delta_absolute=100.0,
            max_delta_percent=None,
        ),
    )

    assert (
        compare_prompt_fixture_metrics(
            baseline=baseline,
            current=current,
            allowlist=allowlist,
            today=date(2026, 4, 25),
        )
        == ()
    )

    failures = compare_prompt_fixture_metrics(
        baseline=baseline,
        current=current,
        allowlist=allowlist,
        today=date(2026, 5, 2),
    )
    assert {item.metric_path for item in failures} == {
        "totals.total_tokens",
        "families.report.total_tokens",
    }


def test_prompt_fixture_regression_allowlists_bounded_namespace_addition() -> None:
    family_metrics = {
        "runtime_ms": 12.0,
        "total_tokens": 200.0,
        "expected_ocr_calls": 0.0,
        "expected_browser_attempts": 0.0,
        "estimated_cost_usd": 0.01,
    }
    totals = dict(family_metrics)
    baseline = {
        "families": {"report": {"namespace_count": 1, **family_metrics}},
        "namespaces": {"alpha": {"family": "report"}},
        "totals": totals,
    }
    current = {
        "families": {"report": {"namespace_count": 2, **family_metrics}},
        "namespaces": {
            "alpha": {"family": "report"},
            "beta": {"family": "report"},
        },
        "totals": totals,
    }
    allowlist = (
        PromptRegressionAllowlistEntry(
            pattern="namespaces.set",
            owner="quality",
            reason="approved prompt namespace",
            expires_on=date(2026, 7, 31),
            max_delta_absolute=1.0,
            max_delta_percent=None,
        ),
        PromptRegressionAllowlistEntry(
            pattern="families.report.namespace_count",
            owner="quality",
            reason="approved family namespace",
            expires_on=date(2026, 7, 31),
            max_delta_absolute=1.0,
            max_delta_percent=None,
        ),
    )

    assert (
        compare_prompt_fixture_metrics(
            baseline=baseline,
            current=current,
            allowlist=allowlist,
            today=date(2026, 6, 13),
        )
        == ()
    )


def test_prompt_fixture_regression_allowlists_bounded_family_addition() -> None:
    family_metrics = {
        "namespace_count": 1,
        "runtime_ms": 12.0,
        "total_tokens": 200.0,
        "expected_ocr_calls": 0.0,
        "expected_browser_attempts": 0.0,
        "estimated_cost_usd": 0.01,
    }
    baseline = {
        "families": {"report": family_metrics},
        "namespaces": {"alpha": {"family": "report"}},
        "totals": family_metrics,
    }
    current = {
        "families": {"report": family_metrics, "crop_qa": family_metrics},
        "namespaces": {"alpha": {"family": "report"}},
        "totals": family_metrics,
    }
    allowlist = (
        PromptRegressionAllowlistEntry(
            pattern="families.set",
            owner="quality",
            reason="approved prompt family",
            expires_on=date(2026, 7, 31),
            max_delta_absolute=1.0,
            max_delta_percent=None,
        ),
    )

    assert (
        compare_prompt_fixture_metrics(
            baseline=baseline,
            current=current,
            allowlist=allowlist,
            today=date(2026, 6, 13),
        )
        == ()
    )


def test_prompt_fixture_regression_uses_larger_total_runtime_tolerance() -> None:
    baseline = {
        "families": {
            "report": {
                "namespace_count": 1,
                "runtime_ms": 12.0,
                "total_tokens": 200.0,
                "expected_ocr_calls": 0.0,
                "expected_browser_attempts": 0.0,
                "estimated_cost_usd": 0.01,
            }
        },
        "namespaces": {"alpha": {"family": "report"}},
        "totals": {
            "runtime_ms": 70.0,
            "total_tokens": 200.0,
            "expected_ocr_calls": 0.0,
            "expected_browser_attempts": 0.0,
            "estimated_cost_usd": 0.01,
        },
    }
    current = {
        "families": {
            "report": {
                "namespace_count": 1,
                "runtime_ms": 12.0,
                "total_tokens": 200.0,
                "expected_ocr_calls": 0.0,
                "expected_browser_attempts": 0.0,
                "estimated_cost_usd": 0.01,
            }
        },
        "namespaces": {"alpha": {"family": "report"}},
        "totals": {
            "runtime_ms": 115.0,
            "total_tokens": 200.0,
            "expected_ocr_calls": 0.0,
            "expected_browser_attempts": 0.0,
            "estimated_cost_usd": 0.01,
        },
    }

    assert compare_prompt_fixture_metrics(baseline=baseline, current=current) == ()


def test_prompt_fixture_regression_loads_pricing_from_separate_yaml(
    tmp_path: Path,
) -> None:
    pricing = {
        "gpt-5-mini": {
            "input_tokens_per_1k_usd": 0.111,
            "output_tokens_per_1k_usd": 0.222,
            "tool_call_usd": 0.333,
        }
    }
    config_path = tmp_path / "app.yaml"
    costs_path = tmp_path / "llm-costs.yaml"
    config_path.write_text(
        "\n".join(
            [
                'schema_version: "1.0"',
                "cost:",
                '  pricing_path: "./llm-costs.yaml"',
                '  daily_path: "./out/cost-daily.json"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    costs_path.write_text(
        "\n".join(
            [
                'schema_version: "1.0"',
                "pricing:",
                "  gpt-5-mini:",
                "    input_tokens_per_1k_usd: 0.111",
                "    output_tokens_per_1k_usd: 0.222",
                "    tool_call_usd: 0.333",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert _load_pricing(str(config_path)) == pricing
