from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quality.prompt_fixture_corpus_metrics import (  # noqa: E402
    collect_prompt_fixture_corpus_metrics,
    metrics_to_payload,
)
from src.contracts.config import ConfigLoadRequest  # noqa: E402
from src.contracts.run_context import RunContext  # noqa: E402
from src.services.config_service import load_model_pricing  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the prompt fixture corpus performance and cost baseline."
    )
    parser.add_argument(
        "--baseline-out",
        default="docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json",
        help="Baseline snapshot output file.",
    )
    parser.add_argument(
        "--config",
        default="src/config/app.yaml",
        help="Config YAML path used to resolve model pricing.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Prompt dry-run iteration count used for runtime medians.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    pricing = load_model_pricing(
        ConfigLoadRequest(schema_version="1.0", path=args.config),
        _ctx("prompt_fixture_baseline_config"),
    )
    metrics = collect_prompt_fixture_corpus_metrics(
        pricing=pricing,
        iterations=max(1, int(args.iterations)),
    )
    out_path = ROOT / args.baseline_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _preserve_runtime_reference(
        metrics_to_payload(metrics), baseline_path=out_path
    )
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Prompt fixture corpus baseline written: {out_path}")
    return 0


def _preserve_runtime_reference(
    payload: dict[str, object], *, baseline_path: Path
) -> dict[str, object]:
    """Keep the prior runtime reference while refreshing stable metrics.

    Prompt render runtime is still checked by the existing comparator, but its
    host-dependent sample must not rewrite a committed baseline on every
    regeneration. Token, cost, model, namespace, and coverage values remain
    sourced from the current corpus measurement.
    """

    if not baseline_path.exists():
        return payload
    try:
        prior = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return payload
    if not isinstance(prior, dict):
        return payload
    for group_name in ("families", "namespaces"):
        current_group = payload.get(group_name)
        prior_group = prior.get(group_name)
        if not isinstance(current_group, dict) or not isinstance(prior_group, dict):
            continue
        for key, current_item in current_group.items():
            prior_item = prior_group.get(key)
            if (
                isinstance(current_item, dict)
                and isinstance(prior_item, dict)
                and isinstance(prior_item.get("runtime_ms"), (int, float))
                and not isinstance(prior_item.get("runtime_ms"), bool)
            ):
                current_item["runtime_ms"] = prior_item["runtime_ms"]
    prior_totals = prior.get("totals")
    current_totals = payload.get("totals")
    if (
        isinstance(prior_totals, dict)
        and isinstance(current_totals, dict)
        and isinstance(prior_totals.get("runtime_ms"), (int, float))
        and not isinstance(prior_totals.get("runtime_ms"), bool)
    ):
        current_totals["runtime_ms"] = prior_totals["runtime_ms"]
    return payload


def _ctx(span_id: str) -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="prompt-fixture-corpus-baseline",
        task_id="quality-regression",
        span_id=span_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
