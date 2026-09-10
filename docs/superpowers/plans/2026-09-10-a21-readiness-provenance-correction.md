# A21 Readiness and Provenance Correction Plan

> **Execution note:** This plan corrects the already-merged A21 telemetry implementation. It deliberately preserves the existing `validation_reliability_service` and its legacy eventual funnel.

## Objective

Make A21 first-attempt reliability measure the durable, immutable publication-readiness boundary (`awaiting_review`) from canonical retained validation, readiness, queue, and usage records. The implementation must be deterministic, provider-free, and must not alter existing eventual reliability metrics.

## Scope

- Extend `src/contracts/validation_reliability.py` only where the A21 artifact needs explicit provenance or causal fields.
- Extend `src/services/validation_reliability_service.py` to read canonical state-db readiness, queue-transition, repeat-publication, and usage evidence.
- Pass the canonical state database path from the existing reliability-builder call sites.
- Add focused behavioral tests, update the contract snapshot, and update the reliability evidence documentation.

## Design

1. Keep the legacy lifecycle and funnel unchanged. Add a distinct A21 lifecycle ending in `awaiting_review`; it requires both successful `publication_preflight` evidence and a durable canonical readiness record with status `awaiting_review`.
2. Define entity `first_pass` from the recovery-aware final A21 stage, not merely first-attempt completion. Earlier repair, targeted regeneration, a later attempt, or explicit operator action therefore makes the entity fail first pass.
3. Read `workflow_job_transitions` joined to canonical queue jobs. Treat explicit `operator_requeue` / `queue-requeue` provenance as operator intervention; automatic retry, redelivery, and restart remain bounded automatic recovery.
4. Assign every lost entity a single stable causal reason. Prefer the first canonical failure code; otherwise derive a typed generic repair, intervention, incomplete-transition, or missing-readiness reason. Build the Pareto from these retained entity reasons in a stable sort order.
5. Mark `verified_replay` only on a successful, explicitly retained `repeat_publication` zero-write/reuse verification. Never infer it from generic idempotency reuse.
6. Treat absence of run-scoped usage events as unavailable; emit null call/token/cost values instead of manufactured zeros.

## Test-first checkpoints

1. Add tests that ingestion without durable readiness fails A21 success while legacy ingestion metrics stay unchanged.
2. Add tests for an internal repair in attempt one, automatic later-attempt recovery, and explicit queue requeue provenance.
3. Add tests for typed repair-only Pareto reasons, generic reuse versus verified repeat-publication replay, and absent usage evidence.
4. Implement the smallest service and contract changes until these tests pass.
5. Run existing reliability, manifest, workflow queue/requeue, publication-readiness, and repeat-publication suites; then run schema, type, lint, architecture, and documentation gates.
6. Locate a retained P6 Batch 1/4 recovery run and build its scorecard twice, recording first-pass, eventual-readiness, repair Pareto, usage attribution, and byte/hash equivalence. Do not start a new 20-report cohort.

## Completion boundary

Do not mark A21 complete or edit its TODO status unless the retained-run validation demonstrates the corrected semantics. A new 20-report benchmark is explicitly out of scope for this correction.
