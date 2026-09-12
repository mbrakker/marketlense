# IAS First-Attempt Live Canary Implementation Plan

> **For agentic workers:** Execute the focused tasks in order, retaining the
> red/green test evidence for the runner's isolation and result contract.

**Goal:** Run one fresh IAS source through the normal frozen-cohort queue and
answer whether it reaches `awaiting_review` on its first workflow attempt.

**Architecture:** A small operational runner creates a one-off config beneath
a fresh root, uses the existing admission, frozen-cohort, queue-submission,
worker, validation-reliability, and usage services, then writes one JSON
result. It does not introduce a pipeline, telemetry schema, or repair path.

**Tech Stack:** Python 3, existing typed workflow queue, SQLite, PyYAML.

## Tasks

### Task 1: Prove isolated run preparation

- [ ] Write a failing test that expects a unique run root, all mutable paths
  under it, and no pre-existing database/artifact files.
- [ ] Implement only isolated config preparation.
- [ ] Run the focused test.

### Task 2: Drive the existing frozen-cohort queue once

- [ ] Write a failing runner-result test using only an external-boundary fake.
- [ ] Submit exactly one source through `submit_frozen_validation_cohort_to_queue`
  and drain only the report path through `publication_readiness`.
- [ ] Derive the result from existing queue, readiness, validation-reliability,
  and LLM usage records; do not add state or telemetry persistence.
- [ ] Run the focused tests.

### Task 3: Document and execute

- [ ] Add the one command and its strict pass conditions to the workflow
  procedure.
- [ ] Run the deterministic queue regression, then the live IAS command.
- [ ] Run the 20-report cohort immediately only if the IAS result passes.
