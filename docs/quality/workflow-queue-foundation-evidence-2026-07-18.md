# Workflow queue foundation evidence — 2026-07-18

> **Implementation commit:** `dd6eab6d72901d7e774e6c3d6dc5c413be9452f4`  
> **Inspected baseline:** `d3b7ed830a4692d9e97ce3a69f73c17ced118282`  
> **State schema version:** `12`

## Implemented evidence

- One SQLite-backed durable queue store with `workflow_jobs`,
  `workflow_job_attempts`, `workflow_job_transitions`, `workflow_outbox`, and
  `workflow_queue_controls` (migration 11).
- Durable publication-readiness/approval and Briefing-opportunity state
  (migration 12).
- Registered typed logical queues: `publisher_discovery`,
  `report_acquisition`, `mailbox_delivery`, `source_ingest`,
  `report_selection`, `report_analysis`, `report_render`,
  `analytics_projection`, `claim_embedding`, `signal_candidate`,
  `signal_generation`, `briefing_opportunity`, `briefing_generation`,
  `cover_generation`, `publication_readiness`, `wordpress_publish`,
  `wordpress_projection`, plus the nine registered maintenance queues.
- Queue controls, deterministic enqueue deduplication, priority/due ordering,
  bounded leases and heartbeats, stale-worker rejection, outbox
  materialisation, health queries, reconciliation, queue CLI operations, and
  explicit report checkpoint worker adapters.
- One-host SQLite concurrent claim validation exposed an initial WAL setup
  race; it was fixed by configuring the connection inside the state connection
  lock before migration work.

## Validation

| Check | Result |
| --- | --- |
| Focused queue/report tests | `28 passed` |
| Contract, I/O-boundary, migration, docs, and queue tests | `18 passed` |
| Ruff for changed queue/test files | passed |
| Full pytest suite | `4441 passed, 25 deselected, 22 warnings` in `339.38s` |
| SQLite migration | configured state database at schema `12` |
| Queue health CLI | passed for `publisher_discovery` |

## Live durable-worker trace

A source-ingest job was submitted against the configured state database using
the existing `JULIUS BAER - Secular-outlook-2026_ACIG.pdf` repository fixture.
The real worker claimed the durable job and invoked the existing report
pipeline. The configured canonical PDF budget denied work with
`report_pipeline_pdf_budget_stop`. After correcting the classification, an
explicit requeue proved the outcome is retained as `budget_deferred`, with no
child work materialised and no lost job. This validates the safe budget path;
it is not evidence of a completed provider-backed report run.

## Remaining migration scope

This commit is a validated foundation, not completion of the entire programme.
The report checkpoint queues invoke existing pipeline orchestration. The other
registered queue types still use the fail-closed verified-reference
compatibility handler until their domain-specific adapters, UI submission
migration, deferred-work migration, and direct-chaining enforcement are
implemented. Accordingly, backlog items remain open and no completion claim is
made for acquisition-to-ingest automation, Signal/Briefing production work, or
WordPress publication migration.
