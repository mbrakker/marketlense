from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.llm import LLMContextCompactionPolicy
from src.contracts.openai import OpenAIJSONPromptRequest
from src.contracts.run_context import RunContext
from src.services._llm_service.context_compaction import (
    compact_prompt_request_if_needed,
)
from src.utils.model_resolver import (
    resolve_routing_policy,
    routing_policies_from_config,
)


_NAMESPACES = (
    "report_vs/artifacts/summary",
    "report_vs/evidence_packs/findings",
)


@dataclass(frozen=True)
class RetainedRoutingBenchmarkRow:
    """One real retained-artifact routing and evidence-retention result."""

    schema_version: str = field(metadata={"doc": "Benchmark row schema version."})
    report_id: str = field(metadata={"doc": "Retained report identifier."})
    namespace: str = field(metadata={"doc": "Routed prompt namespace."})
    model: str = field(metadata={"doc": "Configured provider-local model."})
    tier: str = field(metadata={"doc": "Configured routing tier."})
    policy_source: str = field(metadata={"doc": "Resolved longest-prefix policy."})
    same_provider_fallback: bool = field(
        metadata={"doc": "Provider fallback constraint."}
    )
    compacted: bool = field(
        metadata={"doc": "Whether the real policy compacted input."}
    )
    original_input_tokens_est: int = field(
        metadata={"doc": "Input estimate before compaction."}
    )
    compacted_input_tokens_est: int = field(
        metadata={"doc": "Input estimate after compaction."}
    )
    avoided_input_tokens_est: int = field(metadata={"doc": "Input tokens avoided."})
    retained_evidence_id_count: int = field(
        metadata={"doc": "Evidence identifiers in retained input."}
    )
    missing_evidence_ids: tuple[str, ...] = field(
        metadata={"doc": "Evidence IDs lost after compaction."}
    )


@dataclass(frozen=True)
class RetainedRoutingBenchmarkReport:
    """Deterministic retained-corpus evidence for LLM routing safety."""

    schema_version: str = field(metadata={"doc": "Benchmark report schema version."})
    report_count: int = field(metadata={"doc": "Distinct retained reports inspected."})
    routed_prompt_count: int = field(metadata={"doc": "Prompt namespaces evaluated."})
    compacted_prompt_count: int = field(
        metadata={"doc": "Prompts compacted by actual policy."}
    )
    avoided_input_tokens_est: int = field(
        metadata={"doc": "Aggregate estimated input tokens avoided."}
    )
    missing_evidence_ids: tuple[str, ...] = field(
        metadata={"doc": "Any lost retained evidence IDs."}
    )
    rows: list[RetainedRoutingBenchmarkRow] = field(
        metadata={"doc": "Stable per-report results."}
    )


def retained_artifact_paths(root: Path) -> list[Path]:
    """Return the checked-in corpus only; no fixture is generated at runtime."""
    return sorted(root.glob("*/report_analysis/artifacts.json"))


def build_retained_routing_benchmark(
    *, artifact_root: str, config_path: str
) -> RetainedRoutingBenchmarkReport:
    config = _load_mapping(Path(config_path))
    policies = routing_policies_from_config(
        config.get("llm_routing") or {},
        model_overrides=config.get("openai_models") or {},
    )
    default_model = str((config.get("openai") or {}).get("model") or "")
    ctx = RunContext(
        schema_version="1.0",
        run_id="llm-routing-retained-benchmark",
        task_id="retained-routing",
        span_id="benchmark",
    )
    rows: list[RetainedRoutingBenchmarkRow] = []
    paths = retained_artifact_paths(Path(artifact_root).resolve())
    for path in paths:
        artifacts = _load_mapping(path)
        report_id = str(artifacts.get("report_id") or path.parent.parent.name)
        for namespace in _NAMESPACES:
            decision = resolve_routing_policy(
                namespace, policies, default_model=default_model
            )
            user_prompt = _retained_prompt(artifacts, namespace=namespace)
            request = OpenAIJSONPromptRequest(
                schema_version="1.0",
                system_prompt="Retained source-backed routing benchmark.",
                user_prompt=user_prompt,
                model=decision.model,
                temperature=0.0,
                api_key="",
                context_compaction_policy=LLMContextCompactionPolicy(
                    schema_version="1.0",
                    enabled=decision.compaction_enabled,
                    max_input_tokens=decision.max_input_tokens or None,
                ),
            )
            compacted_request, result = compact_prompt_request_if_needed(
                request=request,
                ctx=ctx,
                operation="retained_routing_benchmark",
                logger=__import__("logging").getLogger(__name__),
            )
            evidence_ids = _evidence_ids(artifacts)
            compacted_prompt = str(compacted_request.user_prompt)
            missing = tuple(
                evidence_id
                for evidence_id in evidence_ids
                if evidence_id not in compacted_prompt
            )
            rows.append(
                RetainedRoutingBenchmarkRow(
                    schema_version="1.0",
                    report_id=report_id,
                    namespace=namespace,
                    model=decision.model,
                    tier=decision.tier,
                    policy_source=decision.policy_source,
                    same_provider_fallback=decision.same_provider_fallback,
                    compacted=result.compacted,
                    original_input_tokens_est=result.original_input_tokens_est,
                    compacted_input_tokens_est=result.compacted_input_tokens_est,
                    avoided_input_tokens_est=result.avoided_input_tokens_est,
                    retained_evidence_id_count=len(evidence_ids),
                    missing_evidence_ids=missing,
                )
            )
    missing_evidence_ids = tuple(
        sorted(
            {evidence_id for row in rows for evidence_id in row.missing_evidence_ids}
        )
    )
    return RetainedRoutingBenchmarkReport(
        schema_version="1.0",
        report_count=len(paths),
        routed_prompt_count=len(rows),
        compacted_prompt_count=sum(row.compacted for row in rows),
        avoided_input_tokens_est=sum(row.avoided_input_tokens_est for row in rows),
        missing_evidence_ids=missing_evidence_ids,
        rows=rows,
    )


def _load_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _retained_prompt(artifacts: dict[str, Any], *, namespace: str) -> str:
    if namespace.startswith("report_vs/evidence_packs"):
        payload = {
            "metric_spine": artifacts.get("metric_spine") or [],
            "claim_ledgers": artifacts.get("claim_ledgers") or [],
            "insights": artifacts.get("insights_final")
            or artifacts.get("insights")
            or [],
        }
    else:
        payload = {
            "summary": artifacts.get("summary") or {},
            "insights": artifacts.get("insights_final")
            or artifacts.get("insights")
            or [],
            "metric_spine": artifacts.get("metric_spine") or [],
        }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2)


def _evidence_ids(artifacts: dict[str, Any]) -> tuple[str, ...]:
    insights = artifacts.get("insights_final") or artifacts.get("insights") or []
    if not isinstance(insights, list):
        return ()
    return tuple(
        sorted(
            {
                str(item.get("evidence_id") or "").strip()
                for item in insights
                if isinstance(item, dict) and str(item.get("evidence_id") or "").strip()
            }
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify configured LLM routing preserves retained evidence IDs."
    )
    parser.add_argument("--artifact-root", default="tests/fixtures/docpacks/golden")
    parser.add_argument("--config-path", default="src/config/app.yaml")
    parser.add_argument(
        "--output-json", default="out/llm_routing_retained_benchmark.json"
    )
    parser.add_argument("--minimum-reports", type=int, default=1)
    args = parser.parse_args()
    report = build_retained_routing_benchmark(
        artifact_root=args.artifact_root, config_path=args.config_path
    )
    if report.report_count < max(1, args.minimum_reports):
        raise SystemExit(
            f"llm_routing_retained_corpus_insufficient: found={report.report_count} "
            f"minimum={max(1, args.minimum_reports)}"
        )
    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asdict(report), ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 1 if report.missing_evidence_ids else 0


if __name__ == "__main__":
    raise SystemExit(main())
