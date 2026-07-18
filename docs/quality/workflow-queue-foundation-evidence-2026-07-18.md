# Workflow queue foundation evidence — 2026-07-18

> **Foundation commit:** `dd6eab6d72901d7e774e6c3d6dc5c413be9452f4`
> **Final implementation commit:** recorded as a Git note on the final one-commit implementation HEAD
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
| Final focused queue/UI/control/architecture suite | `60 passed` in `16.23s` |
| Full pytest suite with coverage | completed successfully in the final canonical gate; `84.55%` global coverage and `85.30%` orchestrator coverage |
| Final queue registry, worker-failure, and ownership suite | `24 passed` in `143.80s`, including retained-PDF source-ingest → selection execution and the durable `report_analysis` handoff |
| Final static gates | formatting, Ruff, mypy, documentation, contract-schema snapshot, and diff check passed |
| Final mutation and quality regression | passed; every tracked mutation target met its baseline and all coverage baselines passed |
| Prompt fixture corpus regression | passed with three deterministic iterations |
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

## Completion scope

All critical queue types have registered production handlers; the
verified-reference bridge is excluded from critical execution by architecture
tests. Existing report checkpoint orchestration, mailbox/acquisition state,
embedding state, deferred-work migration, remediation, and WordPress service
boundaries remain canonical. Signal, Briefing, cover, publication readiness,
WordPress publication, and WordPress projection use typed handlers and the
shared worker lifecycle. UI Strategy Outputs submit durable queue roots rather
than owning a major workflow subprocess.

## Follow-on evidence — 2026-07-18

The later compatibility handoff (`queue-migrate-deferred-work --yes`) reads
pending legacy ledger records, verifies a retained report PDF, and creates a
deduplicated `source_ingest` job with the legacy due time, plan hash, remaining
attempt allowance, root workflow correlation, and work-key trigger. The ledger
row remains readable; unsupported workflows and missing inputs are surfaced as
unresolved. Focused adapter, legacy-recovery, and queue-service tests passed
(`17 passed`). This is a migration adapter, not evidence that all legacy
workflows or the remaining production queue adapters have been completed.

The `claim_embedding` adapter now invokes the existing canonical embedding
queue rather than a reference-only compatibility handler. It retains canonical
embedding rows and provider metadata, while the workflow attempt records only
bounded usage summaries. The `signal_candidate` adapter invokes the existing
source-linked candidate extractor and creates deduplicated generation jobs for
approved groups. Focused registry plus embedding/candidate suites passed (`30
passed`) after malformed queue-limit tests were added.

Approval now binds the generated approval ID into the retained WordPress outbox
submission. The `wordpress_publish` worker validates that approval and the
immutable Briefing package checksum before it invokes the existing idempotent
publisher; stale approvals block before package read or external I/O. Focused
queue, registry, and publication suites passed (`38 passed`).

The later queue-adapter increment replaces the critical Signal, Briefing,
cover, and WordPress-projection compatibility bridges. Signal generation uses
the canonical deterministic source-linked projection and persists a shared
publish package; Briefing generation constrains the analytics read to the
opportunity's frozen source-content hashes and suppresses inline card rendering.
Both flows enqueue `cover_generation`, which readbacks a checksum-bearing final
package before `publication_readiness`. Signal and Briefing publish workers use
the same approval/recheck/idempotent WordPress path; verified posts enqueue the
existing WordPress intelligence projection orchestrator. The Streamlit
Publisher Discovery, Report Download, Signal Candidate Extraction, Signal Post,
and Cross-Report Analysis controls now submit durable queue jobs and poll their
states without spawning a UI-owned worker. Architecture tests
require non-compatibility handlers for all critical queues, preserve approval
outbox-only behavior, and reject UI subprocess ownership. Focused queue,
cross-report, Signal, WordPress, and UI suites passed (`62 passed` and `27
passed` in their respective commands).

## Controlled live validation — 2026-07-18

Using real persisted projected evidence from two distinct publishers, a
Streamlit Cross-Report Analysis submission created root workflow
`18ff57b6-a419-4dbe-831c-d736d756230a`. The opportunity worker produced frozen
source membership and materialised Briefing job
`c7ba575e-5d63-4165-9578-879eb44bd2d4`. With the explicitly lifted, bounded
30,000-character prompt cap, the live model call succeeded in 38.5 seconds and
recorded `8,796` input tokens, `3,460` output tokens, and a sanitized provider
request ID. It retained a validated package (112,741 bytes at readback), then
independently completed cover generation and publication readiness with package
checksum `8631…c81a` in `awaiting_review` state.

The same persisted projections drove real Streamlit Signal Post root workflow
`7796c10d-c9a0-4586-8d4a-734169c24695`: one candidate job, eight independent
Signal generation jobs, eight covers, and eight readiness jobs all completed.
All eight packages remain `awaiting_review`; no publication was auto-enqueued.

An explicit, recorded approval then materialised WordPress job
`8238a084-3338-41d4-8a27-71f49037caaa` with `--dry-run`. It rechecked approval,
checksum, and publish preflight and completed with status `dry_run`, producing
no WordPress write and no fabricated publication projection. Live WordPress
writes and projection mutations remain intentionally untested because the
feature gate remains disabled and an external public write requires a real
human production approval. Unit/integration coverage exercises verified-post
projection behavior without bypassing that gate.

The live run also exposed two deterministic safeguards that were corrected:
an immutable prompt-policy overflow now dead-letters rather than entering
`budget_deferred`, and Briefing idempotency now includes its full bounded
generation configuration. Re-running a frozen opportunity restores an absent
outbox event without changing the frozen source manifest; materialisation
records the resulting child job on the opportunity.

## Final quality-gate record — 2026-07-19

The canonical 21-step quality sequence was executed against the frozen final
worktree. Its single wrapper exceeded the 30-minute outer command window only
after the full pytest/coverage and mutation commands had completed; retained
`coverage.xml` and `mutation_results.json` demonstrate those completed steps.
The remaining quality-regression and prompt-fixture commands were then run
individually with the same inputs and both passed. Final coverage was `60,289 /
71,308` executable lines (`84.55%` global); `src/orchestrators` was `7,820 /
9,168` (`85.30%`), above the `84.80%` non-regression baseline. This document's
final implementation SHA is recorded as a Git note immediately after the one
commit is created, so the evidence remains bound to the exact tested tree
without embedding an unknown self-referential SHA in a committed file.
