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

## Queue publication authority correction — 2026-11-01

**Implementation commit:** `4128db48`
**Scope:** provider-free Signal and Briefing queue/publication authority only.

The existing Signal projection adapter now owns the package authorization
metadata used by both direct and queued generation. Queued packages retain their
queue-specific HTML/JSON paths, cover fingerprint, content checksum and
idempotency inputs while carrying the approved candidate-group identity and
immutable manifest SHA. Signal readiness replays that manifest through the
existing candidate store and source/evidence projection read before automatic
approval; missing, changed, held, overridden, or contradictory state stays
manual. The HTML entity metadata is derived from the same eligibility decision
as package metadata, and contradictory embedded metadata is rejected before any
WordPress lookup or write.

Briefing publication keeps source-report, distinct-publisher and factual-
evidence minima hard. Explicit overrides remain limited to soft policy issues;
in that prior implementation, metric-normalization telemetry was retained as a
manual `semantic_authority_missing` outcome when no semantic verdict was
present. The package checksum and Signal
validation identity are now produced and consumed consistently across direct,
queued, readiness, and preflight paths without changing the retained package
schema.

| Verification | Result |
| --- | --- |
| Signal/Briefing/analytics-store/queue/readiness/publication boundary suite | `120 passed, 9 deselected` |
| Focused authority/readiness regression group | `42 passed` |
| Formatting, Ruff `E9/F/I`, schema snapshot, architecture imports | passed |
| Full-repository mypy | passed; 786 source files, 0 tracked errors |
| Local default pytest | `8,381 passed, 2 skipped, 48 deselected`; one expected CPython 3.14 wheelhouse guard failure remains because the test requires CPython 3.12 |
| Hosted Python 3.12 CI / release evidence | [Run 41360189272](https://github.com/mbrakker/marketlense/actions/runs/41360189272) passed at `06fcfe6a`: `8,383 passed, 1 skipped`, `85.43%` line coverage, both mutation partitions passed across 17 targets (minimum target score `75`), release manifest/review passed with zero issues |
| Live providers, acquisition, PDF/report execution, WordPress I/O | not run by design |

The hosted run confirms the repository gates on CPython 3.12; neither local nor
hosted provider-free checks are evidence of real-report semantic/editorial
quality. The remaining product prerequisite is the already-required real-report
semantic/editorial gates. E18 remains Active/PARTIAL, Step 2 remains
PARTIAL/NO-GO, and Step 3 is unstarted/not ready.

## Final publication freshness and semantic authority corrections — 2026-11-02

This provider-free correction slice closes the demonstrated final-boundary
authority gaps without live reports, provider/model requests, acquisition,
canonical artifact mutation, publication, or WordPress I/O. The queued
`wordpress_publish` handler now performs the mandatory current-state replay
after approval/package-checksum validation and before live configuration,
WordPress lookup, idempotency readback, or write. Signal replay reuses the
immutable manifest and current candidate/evidence projections; Briefing replay
reloads only the exact selected report IDs and compares current source
eligibility, content hash, authority mode, qualified identity, PDF SHA, and
verified-fact digest against the package and approval snapshot. Manual and
automatic approvals therefore share the same final hard checks.

The existing cross-report synthesis call now retains a structured
`metric_comparison_assessment` with model-owned statuses (`none`,
`source_specific`, `supported_comparison`, or `unresolved`), exact retained
metric/evidence IDs, rationale, and uncertainty. Deterministic code checks only
the contract envelope and IDs; lexical normalization phrases remain telemetry
only. The additive cross-report idempotency material version is `2.3`, so old
cached artifacts cannot bypass the new authority. Missing or unresolved
assessment data remains non-publishable. The crop-refine executor now waits for
running workers before test/process teardown, fixing the observed closed-stream
logging race without reducing parallelism.

| Verification | Result |
| --- | --- |
| Focused cross-report/publication authority suite | `186 passed` |
| Crop-refine lifecycle regression suite | `31 passed`; the full run reproduced no closed-stream logging error after the wait-on-shutdown fix |
| Full local CPython 3.12 suite | `8,396 passed, 2 skipped` in `531.68s` |
| Local coverage gate | global `85.49%`, generators `87.18%`, orchestrators `86.05%`, services `84.34%`, control-plane `90.60%`; all configured floors passed |
| Local quality non-regression | passed; generators `87.1794%` is above retained `87.1763%` baseline |
| Mutation partitions | both passed; `17` targets merged, minimum target score `75%`, critical worker `772.040s` |
| Prompt fixture baseline/gate | regenerated through repository tooling: total `113,900 → 114,247` tokens (`+0.30%`), `$0.025043 → $0.025078` (`+$0.000035`, `+0.14%`); only `cross_report_analysis` changed, `2,468 → 2,815` tokens (`+14.06%`) and `$0.000607 → $0.000642` (`+$0.000035`, `+5.77%`) to carry structured semantic authority; gate passed with unchanged thresholds |
| Contract, formatting, scoped Ruff, mypy, architecture, role/I/O gates | passed; mypy reports 786 source files with 0 tracked errors |
| Hosted final-SHA evidence | [Run 41409138503](https://github.com/mbrakker/marketlense/actions/runs/41409138503) at `57c32e99`: tests, both mutation partitions, and `release_evidence` passed; the release bundle is [artifact 13124703789](https://github.com/mbrakker/marketlense/actions/runs/41409138503/artifacts/13124703789). The run produced no provider, acquisition, canonical-publication, or WordPress write evidence. |
| Step 3 Signal autonomy prerequisite | not satisfied: extraction deliberately stores groups as `blocked` / `held` with `signal_semantic_review_pending`; no LLM-owned approval transition was found, so no approval was fabricated |
| Hosted crop-refine logging observation | reproduced once in the pre-fix local CPython 3.12 full suite, traced to `shutdown(wait=False)`, and not reproduced after the surgical `wait=True` lifecycle fix |

This evidence proves deterministic publication freshness, structured semantic
authority retention, cache invalidation, and provider-free replay safety only.
It does not establish current-SHA real-report semantic/editorial acceptance.
E18 remains **Active/PARTIAL**, Step 2 remains **PARTIAL/NO-GO**, and Step 3
remains **unstarted/not ready** pending the missing Signal semantic-review
transition and fresh source-report quality evidence.
