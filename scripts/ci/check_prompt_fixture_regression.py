from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import yaml

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

REGRESSION_METRICS = (
    "runtime_ms",
    "total_tokens",
    "expected_ocr_calls",
    "expected_browser_attempts",
    "estimated_cost_usd",
)
DEFAULT_TOLERANCES: dict[str, tuple[float, float]] = {
    "runtime_ms": (25.0, 0.35),
    "total_tokens": (0.0, 0.0),
    "expected_ocr_calls": (0.0, 0.0),
    "expected_browser_attempts": (0.0, 0.0),
    "estimated_cost_usd": (0.00005, 0.10),
}
TOTAL_RUNTIME_ABSOLUTE_TOLERANCE_MS = 75.0


@dataclass(frozen=True)
class PromptRegressionAllowlistEntry:
    pattern: str
    owner: str
    reason: str
    expires_on: date
    max_delta_absolute: float
    max_delta_percent: float | None


@dataclass(frozen=True)
class PromptRegressionFailure:
    metric_path: str
    baseline: float
    current: float
    delta: float
    delta_percent: float | None
    reason: str


def load_allowlist(path: Path) -> tuple[PromptRegressionAllowlistEntry, ...]:
    if not path.exists():
        return tuple()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = payload.get("allowlist", [])
    if not isinstance(entries, list):
        raise ValueError(
            "prompt fixture regression allowlist must contain an allowlist list"
        )
    parsed: list[PromptRegressionAllowlistEntry] = []
    for index, item in enumerate(entries, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"allowlist entry {index} must be a mapping")
        missing = [
            key
            for key in ("pattern", "owner", "reason", "expires_on")
            if not item.get(key)
        ]
        if missing:
            raise ValueError(
                f"allowlist entry {index} missing required fields: {', '.join(missing)}"
            )
        absolute = item.get("max_delta_absolute", 0.0)
        percent = item.get("max_delta_percent")
        if absolute in ("", None) and percent in ("", None):
            raise ValueError(
                f"allowlist entry {index} must set max_delta_absolute or max_delta_percent"
            )
        parsed.append(
            PromptRegressionAllowlistEntry(
                pattern=str(item["pattern"]).strip(),
                owner=str(item["owner"]).strip(),
                reason=str(item["reason"]).strip(),
                expires_on=date.fromisoformat(str(item["expires_on"])),
                max_delta_absolute=float(absolute or 0.0),
                max_delta_percent=None if percent in ("", None) else float(percent),
            )
        )
    return tuple(parsed)


def compare_prompt_fixture_metrics(
    *,
    baseline: dict[str, Any],
    current: dict[str, Any],
    allowlist: Iterable[PromptRegressionAllowlistEntry] = (),
    today: date | None = None,
) -> tuple[PromptRegressionFailure, ...]:
    current_date = today or date.today()
    failures: list[PromptRegressionFailure] = []

    baseline_namespaces = set((baseline.get("namespaces") or {}).keys())
    current_namespaces = set((current.get("namespaces") or {}).keys())
    if baseline_namespaces != current_namespaces:
        missing = sorted(baseline_namespaces - current_namespaces)
        added = sorted(current_namespaces - baseline_namespaces)
        delta = float(len(current_namespaces) - len(baseline_namespaces))
        if missing or not _is_allowlisted(
            metric_path="namespaces.set",
            delta=delta,
            delta_percent=None,
            allowlist=allowlist,
            today=current_date,
        ):
            failures.append(
                PromptRegressionFailure(
                    metric_path="namespaces.set",
                    baseline=float(len(baseline_namespaces)),
                    current=float(len(current_namespaces)),
                    delta=delta,
                    delta_percent=None,
                    reason=f"namespace set mismatch; missing={missing} added={added}",
                )
            )

    baseline_families = set((baseline.get("families") or {}).keys())
    current_families = set((current.get("families") or {}).keys())
    if baseline_families != current_families:
        missing = sorted(baseline_families - current_families)
        added = sorted(current_families - baseline_families)
        failures.append(
            PromptRegressionFailure(
                metric_path="families.set",
                baseline=float(len(baseline_families)),
                current=float(len(current_families)),
                delta=float(len(current_families) - len(baseline_families)),
                delta_percent=None,
                reason=f"family set mismatch; missing={missing} added={added}",
            )
        )

    for metric in REGRESSION_METRICS:
        baseline_totals = float(((baseline.get("totals") or {}).get(metric) or 0.0))
        current_totals = float(((current.get("totals") or {}).get(metric) or 0.0))
        failure = _compare_metric(
            metric_path=f"totals.{metric}",
            baseline_value=baseline_totals,
            current_value=current_totals,
            allowlist=allowlist,
            today=current_date,
        )
        if failure is not None:
            failures.append(failure)

    shared_families = sorted(baseline_families & current_families)
    for family in shared_families:
        baseline_family = (baseline.get("families") or {}).get(family) or {}
        current_family = (current.get("families") or {}).get(family) or {}
        if int(baseline_family.get("namespace_count") or 0) != int(
            current_family.get("namespace_count") or 0
        ):
            namespace_count_path = f"families.{family}.namespace_count"
            namespace_count_delta = float(
                int(current_family.get("namespace_count") or 0)
                - int(baseline_family.get("namespace_count") or 0)
            )
            if namespace_count_delta < 0 or not _is_allowlisted(
                metric_path=namespace_count_path,
                delta=namespace_count_delta,
                delta_percent=None,
                allowlist=allowlist,
                today=current_date,
            ):
                failures.append(
                    PromptRegressionFailure(
                        metric_path=namespace_count_path,
                        baseline=float(
                            int(baseline_family.get("namespace_count") or 0)
                        ),
                        current=float(int(current_family.get("namespace_count") or 0)),
                        delta=namespace_count_delta,
                        delta_percent=None,
                        reason="family namespace count changed",
                    )
                )
        for metric in REGRESSION_METRICS:
            failure = _compare_metric(
                metric_path=f"families.{family}.{metric}",
                baseline_value=float(baseline_family.get(metric) or 0.0),
                current_value=float(current_family.get(metric) or 0.0),
                allowlist=allowlist,
                today=current_date,
            )
            if failure is not None:
                failures.append(failure)

    return tuple(failures)


def _compare_metric(
    *,
    metric_path: str,
    baseline_value: float,
    current_value: float,
    allowlist: Iterable[PromptRegressionAllowlistEntry],
    today: date,
) -> PromptRegressionFailure | None:
    delta = round(current_value - baseline_value, 6)
    if delta <= 0:
        return None
    metric_name = metric_path.split(".")[-1]
    absolute_tolerance, percent_tolerance = DEFAULT_TOLERANCES.get(
        metric_name, (0.0, 0.0)
    )
    if metric_path == "totals.runtime_ms":
        absolute_tolerance = max(
            absolute_tolerance, TOTAL_RUNTIME_ABSOLUTE_TOLERANCE_MS
        )
    delta_percent = None
    if baseline_value > 0:
        delta_percent = delta / baseline_value
    if delta <= absolute_tolerance:
        return None
    if delta_percent is not None and delta_percent <= percent_tolerance:
        return None
    if _is_allowlisted(
        metric_path=metric_path,
        delta=delta,
        delta_percent=delta_percent,
        allowlist=allowlist,
        today=today,
    ):
        return None
    percent_text = "n/a" if delta_percent is None else f"{delta_percent * 100:.2f}%"
    return PromptRegressionFailure(
        metric_path=metric_path,
        baseline=baseline_value,
        current=current_value,
        delta=delta,
        delta_percent=delta_percent,
        reason=f"regression exceeds tolerance; delta={delta:.6f}, delta_percent={percent_text}",
    )


def _is_allowlisted(
    *,
    metric_path: str,
    delta: float,
    delta_percent: float | None,
    allowlist: Iterable[PromptRegressionAllowlistEntry],
    today: date,
) -> bool:
    for entry in allowlist:
        if today > entry.expires_on:
            continue
        if not fnmatch.fnmatch(metric_path, entry.pattern):
            continue
        if delta > entry.max_delta_absolute:
            if (
                entry.max_delta_percent is None
                or delta_percent is None
                or delta_percent > entry.max_delta_percent
            ):
                continue
        return True
    return False


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prompt fixture corpus performance and cost non-regression gate."
    )
    parser.add_argument(
        "--baseline",
        default="docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json",
        help="Committed prompt fixture corpus baseline JSON path.",
    )
    parser.add_argument(
        "--allowlist",
        default="docs/quality/prompt_fixture_corpus_allowlist.yaml",
        help="Time-bounded allowlist YAML path for approved prompt-corpus regressions.",
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
    baseline_path = ROOT / args.baseline
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    allowlist = load_allowlist(ROOT / args.allowlist)
    pricing = _load_pricing(args.config)
    current_metrics = collect_prompt_fixture_corpus_metrics(
        pricing=pricing,
        iterations=max(1, int(args.iterations)),
    )
    current = metrics_to_payload(current_metrics)
    failures = compare_prompt_fixture_metrics(
        baseline=baseline,
        current=current,
        allowlist=allowlist,
    )

    print("Prompt fixture corpus regression gate:")
    _print_section("Totals", baseline.get("totals") or {}, current.get("totals") or {})
    for family in sorted((current.get("families") or {}).keys()):
        print(f"Family: {family}")
        _print_section(
            "",
            ((baseline.get("families") or {}).get(family) or {}),
            ((current.get("families") or {}).get(family) or {}),
        )

    if failures:
        print("\nPrompt fixture corpus regression gate failed:")
        for item in failures:
            print(f"  - {item.metric_path}: {item.reason}")
        return 1

    print("\nPrompt fixture corpus regression gate passed.")
    return 0


def _print_section(
    label: str, baseline: dict[str, Any], current: dict[str, Any]
) -> None:
    if label:
        print(label + ":")
    for metric in REGRESSION_METRICS:
        baseline_value = float(baseline.get(metric) or 0.0)
        current_value = float(current.get(metric) or 0.0)
        delta = current_value - baseline_value
        print(
            f"  - {metric}: current={current_value:.6f} baseline={baseline_value:.6f} delta={delta:.6f}"
        )


def _load_pricing(config_path: str) -> dict[str, dict[str, float]]:
    return load_model_pricing(
        ConfigLoadRequest(schema_version="1.0", path=config_path),
        _ctx("prompt_fixture_regression_config"),
    )


def _ctx(span_id: str) -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="prompt-fixture-corpus-regression",
        task_id="quality-regression",
        span_id=span_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
