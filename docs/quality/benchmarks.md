# Benchmarks

> **Documentation type:** Current reference
> **Canonical topic:** Benchmark methodology
> **Update trigger:** Benchmark corpus, baseline, comparator, or threshold change.

MarketLense uses retained fixture corpora and generated outputs to detect regressions in candidate extraction, crop refinement, prompt fixtures, public rendering, and selected routing paths. Baseline and allowlist files under `docs/quality/` are inputs to their corresponding scripts; generated result payloads belong in runtime output or CI artifacts.

Benchmark commands and current enforcement are maintained by the CI workflow and the non-regression policy. Do not paste benchmark result tables into the root README or release summaries. Record approved exceptions in the policy-controlled allowlist or release-evidence mechanism.

## Performance telemetry

The canonical state database retains bounded stage spans and scalar resource
measurements. The run artifact reports stage wall time plus any explicitly
recorded queue, database, LLM, browser, cache, worker-capacity, and total-run
metrics. Missing data is retained as `unavailable`, not as zero.

CI writes `out/test_telemetry_ci.json`, with one node ID, outcome, and wall-time
measurement for every executed test. Resource values are `unavailable` until
the test itself exercises a persisted telemetry span; the artifact never
infers cache or cost data from test duration. Use
`scripts/quality/performance_telemetry_baseline.py` to compare compatible
before/after run artifacts. It only proves a speed improvement when the profile
matches and neither quality nor estimated cost regresses.

CI also measures each existing standalone coverage, mutation,
quality-regression, PDF, public-render, retained-LLM-routing,
workflow-evidence, and prompt-fixture gate once.
`out/ci_performance_benchmark.json` combines those stage wall times with the
full pytest session wall time. It sets `quality_passed` only when the test
suite and every measured gate passed. Its estimated provider cost is zero
because CI makes no live provider call; that is not evidence of live-pipeline
cost.

The shared browser-download test runtime represents a completed onsite report
with both report text and a navigation network event. This lets ordinary tests
meet the production terminal-evidence quorum immediately. Tests that need to
exercise bounded polling must provide deliberately incomplete or transient
terminal evidence. The browser suite has a regression test that asserts the
normal fixture takes zero stabilization polls.

## Ingest worker matrix

`scripts/quality/benchmark_ingest_parallelism.py` measures the real bounded
ingest batch scheduler with deterministic local work for one, five, and ten
reports. It compares the current `5x5` worker profile with bounded outer/inner
alternatives, performs two warmups and seven measured runs per profile, and
retains only scalar timings and outcome digests. It neither calls providers nor
publishes or writes outside its temporary namespace. Use it to reject a worker
setting unless an eligible profile has the same outcome digest, passes quality,
and has no higher cost. It selects the lowest measured median; exact ties use
the lower-concurrency profile. This is a scheduler benchmark; browser and
live-provider saturation require a separate controlled canary.

See [non-regression policy](non-regression-policy.md) and [release gates](release-gates.md).
