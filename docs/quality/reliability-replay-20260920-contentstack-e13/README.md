# Targeted real-report replay — Contentstack E13 verification — 2026-09-20

## Measurement identity

- Source: the immutable, checksum-validated Contentstack member from
  `scripts/quality/frozen_reliability_cohort_20.json`.
- Canonical path: `scripts.quality.ias_live_canary_runner.run_first_attempt_canary`.
  It creates fresh isolated state, submits through the production queue, and
  drains the normal supervisor. The run did not publish to WordPress.
- Revision: `c2df11a5c9c28749cd243bcc4a7727ca50580691`.
- Scope: one fresh real-report measurement after the provenance/E13 changes;
  no member substitution, manual requeue, publisher-specific handling,
  validation waiver, or retry-limit adjustment.

## Outcome

The sanitized terminal result is in [result.json](result.json). It records
`awaiting_review`, validation and publication-readiness pass, one workflow
attempt, no automatic repair, and no operator intervention. This establishes
that the Contentstack source is not a proven source-invalid or non-repairable
pipeline/model-contract failure on the current shared mechanism.

The file intentionally retains identifiers, state transitions, bounded usage,
and outcome fields only. It contains neither source prose, prompts, provider
responses, nor credentials.
