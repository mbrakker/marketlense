---
name: speedup-proof
description: Prove or reject a focused MarketLense performance or cost optimization with explicit approval and equivalent deterministic measurements.
---

# Speedup proof

Use for an optimization or performance regression. This is the existing
optimization workflow, refined for MarketLense; do not create another
performance Skill.

## Trigger and approval

Inspect and measure first. Before editing project files, show one bounded
proposal: hotspot and evidence, exact files, preserved behavior, benchmark and
test plan, and main risk. Wait for explicit approval for that proposal.

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
and after the approved change; reuse an existing benchmark whenever it covers
the behavior. Run the affected tests and compare quality, median time, output
digest, and cost.

Record workload, environment, commands, samples, median/variation, output
comparison, cost, and retained artifacts. Keep the change only when correctness
passes and the measurement exceeds normal noise; otherwise report
`INCONCLUSIVE` or `REGRESSION`. Finish with the completion gate.
