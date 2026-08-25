---
name: speedup-proof
description: Prove or reject a focused MarketLense performance or cost optimization through one reversible, evidence-backed experiment.
---

# Speedup proof

Use for an optimization or performance regression. This is the existing
optimization workflow, refined for MarketLense; do not create another
performance Skill.

## Trigger and bounded experiment

For repository-local, reversible work, proceed autonomously with one bounded
experiment: baseline, one explicit hypothesis, one change, identical
measurement, then keep or revert. Stop for authority when the proposed change
is externally consequential, irreversible, credential-gated, or materially
expands scope. State the hotspot, evidence, exact files, preserved behavior,
benchmark/test plan, and main risk before the change.

## MarketLense entrypoints and invariants

Use retained telemetry and the existing benchmark that matches the changed
stage: `scripts/quality/performance_telemetry_baseline.py`,
`benchmark_ingest_parallelism.py`, `benchmark_evidence_pack_parallelism.py`,
`benchmark_artifact_parallelism.py`, or `benchmark_pdf_candidate_parallelism.py`.
Preserve exact output digests, schema/provenance, bounded concurrency and rate
caps, side effects, cache validity, and estimated-cost behavior. Never remove
validation, logging, or retry bounds to manufacture a gain.

## Inspect, validate, and complete

Read the relevant telemetry/benchmark baseline, changed subsystem contract, and
focused regression tests. Measure equivalent warmups and repeated runs before
and after the one bounded change; reuse an existing benchmark whenever it
covers the behavior. Run the affected tests and compare quality, median time,
output digest, and cost.

Record workload, environment, commands, samples, median/variation, output
comparison, cost, and retained artifacts. Keep the change only when correctness
passes and the measurement exceeds normal noise; otherwise report
`INCONCLUSIVE` or `REGRESSION` and revert it. Before keeping a result, check
that the apparent win did not weaken validation, shrink the workload, alter
fixtures, hide failures, skip side effects, or substitute an incomparable
quality/cost metric. Finish with the ordinary aggregate quality gate when the
change is high risk.
