# Benchmarks

> **Documentation type:** Current reference
> **Canonical topic:** Benchmark methodology
> **Update trigger:** Benchmark corpus, baseline, comparator, or threshold change.

MarketLense uses retained fixture corpora and generated outputs to detect regressions in candidate extraction, crop refinement, prompt fixtures, public rendering, and selected routing paths. Baseline and allowlist files under `docs/quality/` are inputs to their corresponding scripts; generated result payloads belong in runtime output or CI artifacts.

Benchmark commands and current enforcement are maintained by the CI workflow and the non-regression policy. Do not paste benchmark result tables into the root README or release summaries. Record approved exceptions in the policy-controlled allowlist or release-evidence mechanism.

## Archived Phase-1 evidence

The [agent-engineering directory](../../benchmarks/agent-engineering/README.md)
is retained as frozen historical evidence only. It has no active script, Skill,
CI gate, or operating workflow. Its ten-case pre-Phase-1 baseline recorded 9/10
evaluator-correct cases and 85% required-verification success. The exact six
holdouts, evaluator payloads, and historical records remain untouched.

The final Phase-1 candidate completed the same ten frozen cases at 8/10
evaluator-correct and 75% required-verification success. It did not improve on
the baseline, so all Phase-1 controls were rejected and removed. See the
[`phase1-final-rejection.json`](../../benchmarks/agent-engineering/baselines/phase1-final-rejection.json)
record. CodeGraph and final-engineering-review artifacts remain rejection
evidence only; neither has an active integration or workflow.

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

## Evidence-pack worker matrix

`scripts/quality/benchmark_evidence_pack_parallelism.py` exercises the real
evidence-pack generator for one, five, and ten reports. It evaluates every
combination of one to five per-report workers and one to five shared in-flight
model slots. The model boundary has deterministic latency and complete,
schema-valid responses, while the generator, prompt preparation, pack
normalization, persistence calls, and rate-cap contention remain real. Each
profile must produce an identical output digest, complete family statuses, no
rate-cap breach, and no estimated cost increase. The selector retains the
current `5x5` baseline unless a candidate's median gain exceeds both 3% and
twice the greater coefficient of variation. This proves local scheduler and
rate-cap behavior only; a controlled live-provider canary is required before
changing production limits.

## Artifact worker matrix

`scripts/quality/benchmark_artifact_parallelism.py` exercises the real artifact
step-batch executor for one, five, and ten reports. It evaluates every
combination of one to five configured workers and one to five shared in-flight
renderer slots across both the three-task stage-one batch and the two-task
distribution batch. The benchmark requires matching task-output digests,
complete step coverage, shared-cap compliance, and no estimated cost increase.
It retains the `5x5` baseline unless an alternative's median improves by at
least 3% and by more than twice the greater coefficient of variation. The
renderer is deterministic and local, so a live-provider canary remains
required before changing production model-concurrency settings.

## PDF candidate worker matrix

`scripts/quality/benchmark_pdf_candidate_parallelism.py` measures the real PDF
visual-candidate extractor on the committed three-PDF golden corpus. It
compares every supported worker count from one through eight against the
five-worker report-pipeline baseline, with two warmups and seven retained
samples per profile. A profile is eligible only when every source PDF retains
its exact hash, candidate count, candidate signature, and degraded-page count.
The selector requires a median improvement of at least 3% and more than twice
the greater coefficient of variation; otherwise it retains the five-worker
baseline. This corpus measures visual-candidate extraction only, so other PDF
stages require their own worker matrices.

See [non-regression policy](non-regression-policy.md) and [release gates](release-gates.md).
