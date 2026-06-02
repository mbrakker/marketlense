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
    out_path.write_text(
        json.dumps(
            metrics_to_payload(metrics), ensure_ascii=False, indent=2, sort_keys=True
        ),
        encoding="utf-8",
    )
    print(f"Prompt fixture corpus baseline written: {out_path}")
    return 0


def _ctx(span_id: str) -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="prompt-fixture-corpus-baseline",
        task_id="quality-regression",
        span_id=span_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
