"""Select bounded evidence-pack concurrency from comparable benchmark samples."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median, pstdev
from threading import BoundedSemaphore, Lock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.config import ConfigLoadRequest  # noqa: E402
from src.contracts.openai import OpenAIResponseResult  # noqa: E402
from src.contracts.prompts import (  # noqa: E402
    PromptDependency,
    PromptDependencyManifest,
    PromptSet,
    PromptTemplate,
)
from src.generators.evidence_pack_generator import generate_evidence_packs  # noqa: E402
from src.services.config_service import load_settings  # noqa: E402
from src.utils.logging import new_run_context  # noqa: E402


@dataclass(frozen=True)
class EvidencePackWorkerProfile:
    parallel_workers: int
    max_in_flight: int


@dataclass(frozen=True)
class EvidencePackBenchmarkResult:
    report_count: int
    profile: EvidencePackWorkerProfile
    samples_ms: tuple[int, ...]
    quality_passed: bool
    estimated_cost_usd: str
    outcome_digest: str
    maximum_observed_in_flight: int


@dataclass(frozen=True)
class EvidencePackRecommendation:
    report_count: int
    baseline_profile: EvidencePackWorkerProfile
    selected_profile: EvidencePackWorkerProfile
    baseline_median_ms: int
    selected_median_ms: int
    speedup_ratio: float


_BASELINE_PROFILE = EvidencePackWorkerProfile(parallel_workers=5, max_in_flight=5)
_DEFAULT_PROFILES = (_BASELINE_PROFILE,) + tuple(
    EvidencePackWorkerProfile(parallel_workers=parallel_workers, max_in_flight=cap)
    for parallel_workers in range(1, 6)
    for cap in range(1, 6)
    if (parallel_workers, cap) != (5, 5)
)
_DEFAULT_REPORT_COUNTS = (1, 5, 10)
_BATCH_WORKER_LIMIT = 5
_PACK_REGISTRY = (
    "doc_map",
    "scope",
    "methods",
    "findings",
    "limitations",
    "quote_candidates",
)


class _DeterministicPromptClient:
    def load_prompt_set(self, request, ctx):
        del ctx
        system = PromptTemplate(
            schema_version="1.0",
            path="benchmark-system",
            text="system",
            sha256="a" * 64,
        )
        user = PromptTemplate(
            schema_version="1.0", path="benchmark-user", text="user", sha256="b" * 64
        )
        return PromptSet(
            schema_version="1.0",
            system=system,
            user=user,
            dependency_manifest=PromptDependencyManifest(
                schema_version="1.0",
                namespace=request.namespace,
                system_root=PromptDependency(
                    schema_version="1.0",
                    path=system.path,
                    sha256=system.sha256,
                    kind="system_root",
                ),
                user_root=PromptDependency(
                    schema_version="1.0",
                    path=user.path,
                    sha256=user.sha256,
                    kind="user_root",
                ),
            ),
            prompt_content_hash="c" * 64,
        )

    def render_prompt(self, request, ctx):
        del ctx
        return SimpleNamespace(text=request.template.text)


class _DeterministicAnalysisStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self.stored: list[tuple[str, str]] = []

    def store_pack(
        self, output_dir, report_id, pack_name, payload, ctx, report_slug=None
    ):
        del output_dir, payload, ctx, report_slug
        with self._lock:
            self.stored.append((report_id, pack_name))
        return f"benchmark://{report_id}/{pack_name}"


class _BoundedDeterministicModelClient:
    def __init__(self, *, max_in_flight: int, latency_ms: int) -> None:
        self._slots = BoundedSemaphore(max_in_flight)
        self._latency_seconds = latency_ms / 1_000
        self._lock = Lock()
        self.calls = 0
        self._active = 0
        self.maximum_observed_in_flight = 0

    def openai_respond_with_vector_store(self, request, ctx):
        del ctx
        with self._slots:
            with self._lock:
                self.calls += 1
                self._active += 1
                self.maximum_observed_in_flight = max(
                    self.maximum_observed_in_flight, self._active
                )
            try:
                time.sleep(self._latency_seconds)
                payload = _payload_for(str(request.artifact_family))
                return OpenAIResponseResult(
                    schema_version="1.0",
                    text=json.dumps(payload, ensure_ascii=True, sort_keys=True),
                    parsed_json=payload,
                    input_tokens=1,
                    output_tokens=1,
                    tool_calls=0,
                    model=request.model,
                )
            finally:
                with self._lock:
                    self._active -= 1


def run_evidence_pack_worker_matrix(
    *,
    report_counts: tuple[int, ...] = _DEFAULT_REPORT_COUNTS,
    profiles: tuple[EvidencePackWorkerProfile, ...] = _DEFAULT_PROFILES,
    warmups: int = 2,
    runs: int = 7,
    model_latency_ms: int = 30,
) -> list[EvidencePackBenchmarkResult]:
    """Measure the real evidence-pack generator with deterministic model latency."""
    _validate_matrix_inputs(
        report_counts=report_counts,
        profiles=profiles,
        warmups=warmups,
        runs=runs,
        model_latency_ms=model_latency_ms,
    )
    results: list[EvidencePackBenchmarkResult] = []
    with tempfile.TemporaryDirectory(
        prefix="marketlense-evidence-pack-matrix-"
    ) as root:
        root_path = Path(root)
        for report_count in report_counts:
            for profile in profiles:
                for _ in range(warmups):
                    _run_evidence_pack_sample(
                        root_path=root_path,
                        report_count=report_count,
                        profile=profile,
                        model_latency_ms=model_latency_ms,
                    )
                samples: list[int] = []
                outcome_digests: set[str] = set()
                quality_passed = True
                maximum_observed_in_flight = 0
                for _ in range(runs):
                    elapsed_ms, digest, quality, observed = _run_evidence_pack_sample(
                        root_path=root_path,
                        report_count=report_count,
                        profile=profile,
                        model_latency_ms=model_latency_ms,
                    )
                    samples.append(elapsed_ms)
                    outcome_digests.add(digest)
                    quality_passed = quality_passed and quality
                    maximum_observed_in_flight = max(
                        maximum_observed_in_flight, observed
                    )
                if len(outcome_digests) != 1:
                    quality_passed = False
                results.append(
                    EvidencePackBenchmarkResult(
                        report_count=report_count,
                        profile=profile,
                        samples_ms=tuple(samples),
                        quality_passed=quality_passed,
                        estimated_cost_usd="0",
                        outcome_digest=next(iter(outcome_digests), ""),
                        maximum_observed_in_flight=maximum_observed_in_flight,
                    )
                )
    return results


def build_worker_matrix_artifact(
    results: list[EvidencePackBenchmarkResult],
    *,
    warmups: int,
    runs: int,
    model_latency_ms: int,
) -> dict[str, object]:
    """Build a bounded, scalar-only benchmark artifact."""
    recommendations = select_optimal_profiles(results)
    return {
        "schema_version": "1.0",
        "measurement_profile_hash": _measurement_profile_hash(
            results=results,
            warmups=warmups,
            runs=runs,
            model_latency_ms=model_latency_ms,
        ),
        "batch_worker_limit": _BATCH_WORKER_LIMIT,
        "pack_registry": list(_PACK_REGISTRY),
        "warmups": warmups,
        "runs": runs,
        "model_latency_ms": model_latency_ms,
        "results": [asdict(result) for result in results],
        "recommendations": [
            asdict(recommendations[report_count])
            for report_count in sorted(recommendations)
        ],
    }


def select_optimal_profiles(
    results: list[EvidencePackBenchmarkResult],
) -> dict[int, EvidencePackRecommendation]:
    """Choose the fastest quality- and cost-equivalent profile per batch size."""
    recommendations: dict[int, EvidencePackRecommendation] = {}
    for report_count in sorted({result.report_count for result in results}):
        cohort = [result for result in results if result.report_count == report_count]
        baseline = _baseline_for(cohort)
        baseline_cost = _cost(baseline.estimated_cost_usd)
        eligible = [
            result
            for result in cohort
            if result.quality_passed
            and result.outcome_digest == baseline.outcome_digest
            and result.maximum_observed_in_flight <= result.profile.max_in_flight
            and _cost(result.estimated_cost_usd) <= baseline_cost
        ]
        if not eligible:
            continue
        selected = min(
            eligible,
            key=lambda result: (_median_ms(result), _selection_key(result)),
        )
        if selected != baseline and not _is_proven_faster(
            baseline=baseline, candidate=selected
        ):
            selected = baseline
        baseline_median = _median_ms(baseline)
        selected_median = _median_ms(selected)
        recommendations[report_count] = EvidencePackRecommendation(
            report_count=report_count,
            baseline_profile=baseline.profile,
            selected_profile=selected.profile,
            baseline_median_ms=baseline_median,
            selected_median_ms=selected_median,
            speedup_ratio=round(baseline_median / selected_median, 4),
        )
    return recommendations


def _run_evidence_pack_sample(
    *,
    root_path: Path,
    report_count: int,
    profile: EvidencePackWorkerProfile,
    model_latency_ms: int,
) -> tuple[int, str, bool, int]:
    settings = _settings_for_sample(root_path=root_path, profile=profile)
    prompt_client = _DeterministicPromptClient()
    analysis_store = _DeterministicAnalysisStore()
    model_client = _BoundedDeterministicModelClient(
        max_in_flight=profile.max_in_flight,
        latency_ms=model_latency_ms,
    )

    def generate(index: int) -> dict[str, dict]:
        report_id = f"benchmark-{index:02d}"
        return generate_evidence_packs(
            report_id=report_id,
            report_name=f"Benchmark report {index:02d}",
            vector_store_id=f"vs-{index:02d}",
            settings=settings,
            ctx=new_run_context(task_id=f"evidence-pack-matrix:{report_id}"),
            openai_client=model_client,
            prompt_client=prompt_client,
            analysis_store=analysis_store,
        )

    started_ns = time.monotonic_ns()
    with ThreadPoolExecutor(
        max_workers=min(report_count, _BATCH_WORKER_LIMIT)
    ) as executor:
        packs_by_report = list(executor.map(generate, range(report_count)))
    elapsed_ms = round((time.monotonic_ns() - started_ns) / 1_000_000)
    digest = hashlib.sha256(
        json.dumps(packs_by_report, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()
    quality_passed = (
        all(_packs_are_complete(packs) for packs in packs_by_report)
        and model_client.calls == report_count * len(_PACK_REGISTRY)
        and model_client.maximum_observed_in_flight <= profile.max_in_flight
    )
    return elapsed_ms, digest, quality_passed, model_client.maximum_observed_in_flight


def _settings_for_sample(*, root_path: Path, profile: EvidencePackWorkerProfile):
    settings = load_settings(
        ConfigLoadRequest(
            schema_version="1.0", path=str(ROOT / "src" / "config" / "app.yaml")
        ),
        new_run_context(task_id="evidence-pack-matrix-config"),
    )
    return replace(
        settings,
        output_dir=str(root_path / "out"),
        cache_dir=str(root_path / "cache"),
        state_db=str(root_path / "state.sqlite"),
        reports_db=str(root_path / "reports.sqlite"),
        cost_ledger_path=str(root_path / "cost-ledger.jsonl"),
        cost_daily_path=str(root_path / "cost-daily.json"),
        evidence_pack_registry=list(_PACK_REGISTRY),
        evidence_pack_parallel_workers=profile.parallel_workers,
        vector_store_keep=False,
    )


def _payload_for(pack_name: str) -> dict:
    payloads = {
        "doc_map": {
            "doc_id": "benchmark-doc",
            "title": "Retail Measurement Outlook",
            "summary": "Examines cross-channel retail measurement methods.",
            "sections": [
                {
                    "id": "measurement-methods",
                    "title": "Measurement methods",
                    "summary": "Connects retail media and commerce measurement.",
                    "key_points": ["Comparable campaign signals are required."],
                }
            ],
        },
        "scope": {"scope": "Cross-channel retail measurement."},
        "methods": {"methods": ["Survey", "Transaction analysis"]},
        "findings": {
            "findings": [
                {
                    "id": "finding-1",
                    "text": "Measurement is fragmented.",
                    "evidence": "Page 2",
                }
            ]
        },
        "limitations": {
            "limitations": ["Results depend on available source evidence."]
        },
        "quote_candidates": {
            "quote_candidates": [
                {
                    "id": "quote-1",
                    "text": "Measurement needs a common view.",
                    "source": "Research lead",
                    "page": 2,
                }
            ]
        },
    }
    try:
        return json.loads(json.dumps(payloads[pack_name], ensure_ascii=True))
    except KeyError as exc:
        raise ValueError(
            f"unsupported evidence-pack benchmark payload: {pack_name}"
        ) from exc


def _packs_are_complete(packs: dict[str, dict]) -> bool:
    if tuple(packs) != _PACK_REGISTRY:
        return False
    return all(
        packs[pack_name].get("family_status", {}).get("status") == "generated"
        for pack_name in _PACK_REGISTRY
    )


def _baseline_for(
    cohort: list[EvidencePackBenchmarkResult],
) -> EvidencePackBenchmarkResult:
    for result in cohort:
        if result.profile == _BASELINE_PROFILE:
            return result
    raise ValueError("each report-count cohort requires the current 5x5 baseline")


def _median_ms(result: EvidencePackBenchmarkResult) -> int:
    if not result.samples_ms or any(sample < 0 for sample in result.samples_ms):
        raise ValueError("benchmark samples must be non-negative")
    return round(median(result.samples_ms))


def _cost(value: str) -> Decimal:
    try:
        cost = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("estimated_cost_usd must be a decimal") from exc
    if not cost.is_finite() or cost < 0:
        raise ValueError("estimated_cost_usd must be non-negative")
    return cost


def _selection_key(result: EvidencePackBenchmarkResult) -> tuple[int, int, int]:
    profile = result.profile
    return (
        profile.parallel_workers * profile.max_in_flight,
        profile.parallel_workers,
        profile.max_in_flight,
    )


def _is_proven_faster(
    *,
    baseline: EvidencePackBenchmarkResult,
    candidate: EvidencePackBenchmarkResult,
) -> bool:
    baseline_median = _median_ms(baseline)
    candidate_median = _median_ms(candidate)
    if candidate_median >= baseline_median:
        return False
    maximum_cv = max(
        _coefficient_of_variation(baseline),
        _coefficient_of_variation(candidate),
    )
    if maximum_cv > 0.15:
        return False
    improvement = (baseline_median - candidate_median) / baseline_median
    return improvement >= max(0.03, 2 * maximum_cv)


def _coefficient_of_variation(result: EvidencePackBenchmarkResult) -> float:
    samples = result.samples_ms
    average = sum(samples) / len(samples)
    if average <= 0:
        return 0.0
    return pstdev(samples) / average


def _validate_matrix_inputs(
    *,
    report_counts: tuple[int, ...],
    profiles: tuple[EvidencePackWorkerProfile, ...],
    warmups: int,
    runs: int,
    model_latency_ms: int,
) -> None:
    if not report_counts or any(value < 1 for value in report_counts):
        raise ValueError("report_counts must contain positive values")
    if _BASELINE_PROFILE not in profiles:
        raise ValueError("profiles must include the current 5x5 baseline")
    if any(
        profile.parallel_workers < 1 or profile.max_in_flight < 1
        for profile in profiles
    ):
        raise ValueError("worker counts must be positive")
    if warmups < 0 or runs < 1 or model_latency_ms < 1:
        raise ValueError("warmups, runs, and model_latency_ms must be positive")


def _measurement_profile_hash(
    *,
    results: list[EvidencePackBenchmarkResult],
    warmups: int,
    runs: int,
    model_latency_ms: int,
) -> str:
    payload = {
        "report_counts": sorted({result.report_count for result in results}),
        "profiles": [
            (result.profile.parallel_workers, result.profile.max_in_flight)
            for result in results
        ],
        "batch_worker_limit": _BATCH_WORKER_LIMIT,
        "pack_registry": _PACK_REGISTRY,
        "warmups": warmups,
        "runs": runs,
        "model_latency_ms": model_latency_ms,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--model-latency-ms", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--runs", type=int, default=7)
    args = parser.parse_args(argv)
    results = run_evidence_pack_worker_matrix(
        warmups=args.warmups,
        runs=args.runs,
        model_latency_ms=args.model_latency_ms,
    )
    artifact = build_worker_matrix_artifact(
        results,
        warmups=args.warmups,
        runs=args.runs,
        model_latency_ms=args.model_latency_ms,
    )
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(artifact, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(artifact, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
