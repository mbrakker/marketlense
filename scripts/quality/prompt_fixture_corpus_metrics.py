from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from statistics import median
from typing import Any, Iterable

from src.contracts.prompts import PromptDryRunRequest, PromptDryRunResult
from src.contracts.run_context import RunContext
from src.services.prompt_service import validate_prompt_dry_run
from src.utils.costing import estimate_cost_usd, estimate_text_tokens


@dataclass(frozen=True)
class PromptFixtureNamespaceMetrics:
    schema_version: str = field(metadata={"doc": "Namespace metrics schema version."})
    namespace: str = field(metadata={"doc": "Prompt namespace."})
    family: str = field(metadata={"doc": "Prompt family label."})
    model: str = field(metadata={"doc": "Representative model identifier."})
    runtime_ms: float = field(
        metadata={"doc": "Median prompt render runtime in milliseconds."}
    )
    input_tokens: int = field(
        metadata={
            "doc": "Estimated input tokens for rendered system plus user prompts."
        }
    )
    expected_output_tokens: int = field(
        metadata={
            "doc": "Expected output-token budget from fixture benchmark metadata."
        }
    )
    total_tokens: int = field(
        metadata={"doc": "Estimated total tokens for the fixture benchmark."}
    )
    expected_tool_calls: int = field(
        metadata={"doc": "Expected tool-call count from fixture benchmark metadata."}
    )
    expected_browser_attempts: int = field(
        metadata={
            "doc": "Expected browser-attempt count from fixture benchmark metadata."
        }
    )
    expected_ocr_calls: int = field(
        metadata={"doc": "Expected OCR-call count from fixture benchmark metadata."}
    )
    estimated_cost_usd: float = field(
        metadata={"doc": "Estimated fixture cost based on configured model pricing."}
    )


@dataclass(frozen=True)
class PromptFixtureFamilyMetrics:
    schema_version: str = field(metadata={"doc": "Family metrics schema version."})
    family: str = field(metadata={"doc": "Prompt family label."})
    namespace_count: int = field(
        metadata={"doc": "Number of prompt namespaces in the family."}
    )
    runtime_ms: float = field(
        metadata={
            "doc": "Median prompt render runtime total for the family in milliseconds."
        }
    )
    input_tokens: int = field(metadata={"doc": "Estimated family input-token total."})
    expected_output_tokens: int = field(
        metadata={"doc": "Expected family output-token total."}
    )
    total_tokens: int = field(metadata={"doc": "Estimated family token total."})
    expected_tool_calls: int = field(
        metadata={"doc": "Expected family tool-call total."}
    )
    expected_browser_attempts: int = field(
        metadata={"doc": "Expected family browser-attempt total."}
    )
    expected_ocr_calls: int = field(metadata={"doc": "Expected family OCR-call total."})
    estimated_cost_usd: float = field(metadata={"doc": "Estimated family cost total."})


@dataclass(frozen=True)
class PromptFixtureCorpusMetrics:
    schema_version: str = field(
        metadata={"doc": "Fixture corpus metrics schema version."}
    )
    generated_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the metrics snapshot was generated."}
    )
    iterations: int = field(
        metadata={
            "doc": "Number of prompt dry-run iterations used for runtime medians."
        }
    )
    fixture_path: str = field(
        metadata={"doc": "Filesystem path to the prompt dry-run fixture registry."}
    )
    fixture_count: int = field(
        metadata={"doc": "Number of prompt namespaces included in the snapshot."}
    )
    families: dict[str, PromptFixtureFamilyMetrics] = field(
        metadata={
            "doc": "Per-family aggregated benchmark metrics keyed by family name."
        }
    )
    namespaces: dict[str, PromptFixtureNamespaceMetrics] = field(
        metadata={"doc": "Per-namespace benchmark metrics keyed by namespace."}
    )
    totals: PromptFixtureFamilyMetrics = field(
        metadata={"doc": "Corpus-wide aggregated metrics using family-metric shape."}
    )


def collect_prompt_fixture_corpus_metrics(
    *,
    pricing: dict[str, dict[str, float]],
    iterations: int = 3,
    namespaces: Iterable[str] = (),
    reload_if_changed: bool = True,
    force_reload: bool = False,
) -> PromptFixtureCorpusMetrics:
    runtime_iterations = max(1, int(iterations))
    requested_namespaces = tuple(
        str(item).strip() for item in namespaces if str(item).strip()
    )
    runtime_samples: dict[str, list[float]] = {}
    final_results: dict[str, PromptDryRunResult] = {}

    for index in range(runtime_iterations):
        response = validate_prompt_dry_run(
            PromptDryRunRequest(
                schema_version="1.0",
                namespaces=list(requested_namespaces),
                reload_if_changed=reload_if_changed,
                force_reload=force_reload,
            ),
            _ctx(f"prompt_fixture_corpus_metrics_{index + 1}"),
        )
        for result in response.results:
            runtime_samples.setdefault(result.namespace, []).append(
                float(result.render_runtime_ms)
            )
            final_results[result.namespace] = result

    namespace_metrics: dict[str, PromptFixtureNamespaceMetrics] = {}
    for namespace, result in sorted(final_results.items()):
        input_tokens = estimate_text_tokens(
            result.rendered_system_prompt
        ) + estimate_text_tokens(result.rendered_user_prompt)
        expected_output_tokens = int(result.benchmark.expected_output_tokens)
        expected_tool_calls = int(result.benchmark.expected_tool_calls)
        expected_browser_attempts = int(result.benchmark.expected_browser_attempts)
        expected_ocr_calls = int(result.benchmark.expected_ocr_calls)
        runtime_ms = round(median(runtime_samples.get(namespace) or [0.0]), 6)
        namespace_metrics[namespace] = PromptFixtureNamespaceMetrics(
            schema_version="1.0",
            namespace=namespace,
            family=result.family,
            model=result.model,
            runtime_ms=runtime_ms,
            input_tokens=input_tokens,
            expected_output_tokens=expected_output_tokens,
            total_tokens=input_tokens + expected_output_tokens,
            expected_tool_calls=expected_tool_calls,
            expected_browser_attempts=expected_browser_attempts,
            expected_ocr_calls=expected_ocr_calls,
            estimated_cost_usd=estimate_cost_usd(
                result.model,
                input_tokens,
                expected_output_tokens,
                expected_tool_calls,
                pricing=pricing,
            ),
        )

    family_metrics: dict[str, PromptFixtureFamilyMetrics] = {}
    for family in sorted({item.family for item in namespace_metrics.values()}):
        family_rows = [
            item for item in namespace_metrics.values() if item.family == family
        ]
        family_metrics[family] = _sum_family_metrics(
            family=family,
            rows=family_rows,
        )

    totals = _sum_family_metrics(
        family="totals",
        rows=namespace_metrics.values(),
    )
    fixture_path = ""
    if final_results:
        fixture_path = next(iter(final_results.values())).fixture_path
    return PromptFixtureCorpusMetrics(
        schema_version="1.0",
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        iterations=runtime_iterations,
        fixture_path=fixture_path,
        fixture_count=len(namespace_metrics),
        families=family_metrics,
        namespaces=namespace_metrics,
        totals=totals,
    )


def metrics_to_payload(metrics: PromptFixtureCorpusMetrics) -> dict[str, Any]:
    payload = asdict(metrics)
    return payload


def _sum_family_metrics(
    *,
    family: str,
    rows: Iterable[PromptFixtureNamespaceMetrics],
) -> PromptFixtureFamilyMetrics:
    materialized = list(rows)
    return PromptFixtureFamilyMetrics(
        schema_version="1.0",
        family=family,
        namespace_count=len(materialized),
        runtime_ms=round(sum(float(item.runtime_ms) for item in materialized), 6),
        input_tokens=sum(int(item.input_tokens) for item in materialized),
        expected_output_tokens=sum(
            int(item.expected_output_tokens) for item in materialized
        ),
        total_tokens=sum(int(item.total_tokens) for item in materialized),
        expected_tool_calls=sum(int(item.expected_tool_calls) for item in materialized),
        expected_browser_attempts=sum(
            int(item.expected_browser_attempts) for item in materialized
        ),
        expected_ocr_calls=sum(int(item.expected_ocr_calls) for item in materialized),
        estimated_cost_usd=round(
            sum(float(item.estimated_cost_usd) for item in materialized),
            6,
        ),
    )


def _ctx(span_id: str) -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="prompt-fixture-corpus",
        task_id="quality-regression",
        span_id=span_id,
    )
