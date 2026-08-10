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

See [non-regression policy](non-regression-policy.md) and [release gates](release-gates.md).
