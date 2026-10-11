# Architecture, engineering, release, and disaster recovery

Canonical owner IDs: R1, R2, R3, R6, R7. This document contains **Active outcome specifications and their retained technical proposal slices**. Status belongs to [CONSOLIDATED_TODO.md](../../CONSOLIDATED_TODO.md), not to individual proposal sections. The complete source texts are preserved unchanged in the [historical backlog](archive/CONSOLIDATED_TODO-20261011-preconsolidation.md) and [historical proposal catalogue](archive/10improvements-20261011-preconsolidation.md).

Before implementing a slice, verify its historic diagnosis at current HEAD; use its **Luna implementation prompt** together with the full evidence and criteria immediately above it. Proposed thresholds are acceptance targets, not current results. Closed parent milestones are not reopened by a proposal's historical wording.

---
 
## R1. Publish release-evidence reviews where reviewers work

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `VER-10`.

- **Baseline:** The strict CTO collector already retains finite representative/smoke/not-declared scope, freshness and producer provenance. GitHub's bounded summary reports review/queue disposition and names an artifact, but does not expose a canonical bundle link or propagate runtime scope to PR/release reviewers. Remaining work is surface integration and truthful mismatch/unavailable disposition, not rebuilding collection/taxonomy.
- **Target behaviour:** The PR/release surface directly exposes exact-tested-HEAD evidence status, link/reference to the archived bundle, final approval/unwaived result, and declared runtime-corpus scope without copying unbounded evidence into comments/summaries.
- **What to implement, in order:**
  1. Define a small release-review surface contract: tested SHA, build/release run ID, review status, unwaived issue count, queue/runtime evidence status, corpus scope label, and stable artifact/reference link.
  2. Extend current CI/release automation to publish that bounded contract on the relevant PR/release surface while keeping the existing job summary/artifact as source of detail.
  3. Reuse the collector's finite corpus-scope/freshness/provenance contract and propagate it to reviewers. Keep collector/runtime producer identities separate; smoke, missing capture or an operator declaration is not representative workflow proof.
  4. Fail/mark unavailable on exact-HEAD mismatch, missing canonical evidence, expired/unavailable artifact, or unwaived failure rather than showing a green summary. Consume canonical review disposition/provenance rather than treating renderer-local HEAD or missing scope as approval.
  5. Update README/release docs and tests for bounds, mismatch, scope labels and issue retention.
- **Acceptance criteria:**
  - A reviewer can see the exact tested SHA, final evidence disposition, unwaived issue count and canonical bundle reference without opening raw CI logs.
  - Mismatch/unavailable evidence is explicitly non-green and cannot be mistaken for approval.
  - Runtime evidence clearly states whether it is smoke-only or representative; the label is retained with provenance.
  - Surface content is bounded and does not duplicate raw evidence/private diagnostics; all unwaived issues remain accessible in the canonical bundle.
  - Tests cover exact-HEAD match/mismatch, unavailable evidence, representative/smoke labels and bounded summary behavior.

### Luna implementation prompt — R1

```text
Work on R1 — Publish release-evidence reviews where reviewers work at the current MarketLense HEAD.
Owner specification: docs/backlog/R-engineering.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
### Linked technical implementation slices

Technical IDs below are **subtasks or investigations**, not additional canonical Active outcomes. Status notes are historical catalogue/reconciliation claims and require current-HEAD verification.
 
#### VER-10 — Gate verifier behavior changes with output replay, not prompt-size estimates alone

**Primary canonical owner:** [R1](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / VER-05/06; extends R1/C5 and existing E13 replay, not another token-cost benchmark.
- **Evidence / diagnosis:** `scripts/ci/check_prompt_fixture_regression.py:26–39,104–173` gates render runtime, estimated tokens, expected tools/OCR/browser work and estimated cost. `scripts/quality/prompt_fixture_corpus_metrics.py:142–189` renders fixture prompts and obtains expected output/tool counts from fixture metadata; it does not execute/judge generated output. That gate is valuable but cannot prove semantic correctness of a changed verifier/prompt. Existing migration evidence explicitly says lower cost alone does not meet acceptance (`gpt6-luna-evaluation-20260923.md:42–47`), and current repair replay already pins identities. Remaining improvement is a canonical behavioral regression disposition tied to those retained outputs, not replacement of dry-run coverage.
- **Luna implementation:** Extend the existing zero-provider replay/diff route to compare verifier dispositions on pinned source/output/verdict packages, retaining prompt/policy/schema/validator/model/input hashes. Include approved positive/negative holdout cases from VER-05/06. Report resolved, persisting and newly introduced rejection/acceptance changes with rule/item identities, rather than byte equality of prose. An intentional behavior change requires a bounded reviewed rationale linked to evidence; newly accepted critical invalid cases fail. Keep baseline and holdout membership immutable during a candidate comparison. Real-model sensitivity, when needed, uses a separate opt-in budgeted canary; replay is not claimed to measure fresh provider accuracy.
- **Success criteria:** A smaller/cheaper prompt cannot pass behavioral release evidence while introducing a critical false accept. Missing/incompatible outputs or changed cohort identities invalidate comparison. CI replay makes zero external calls, and changed expected labels require independent adjudication rather than automatic baseline refresh. Estimated economics and measured model behavior remain clearly separated.
- **Validation:** Extend `tests/test_prompt_fixture_corpus_regression.py`, `tests/test_replay_validation_repair_benchmark.py` and the proposed mutation suite for missing cases, changed identities, accepted-negative regression and legitimate reviewed fixes. Run those plus the existing `check_prompt_fixture_regression.py` command documented in the LLM skill. Capture exact-SHA replay results and, only when fixtures cannot establish provider behavior, a marked bounded no-public-write live canary.

**Luna implementation prompt — VER-10 (copy/paste)**

```text
Implement VER-10 — Gate verifier behavior changes with output replay, not prompt-size estimates alone.
Objective: Deliver the verified behavior specified immediately above under canonical R1.
Source: docs/backlog/R-engineering.md, technical slice VER-10.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update R1 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
 
## R2. Enforce role boundaries, direct-I/O discipline, and controlled module growth

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `CODE-04`, `CODE-05`.

- **Baseline:** CI enforces imports, external-library ownership, role-I/O, movement evidence and quality floors. Role-I/O allowlists already validate exact path/rule, owner/expiry and reject expiration; no entries currently exist. Named behavior-coverage gaps and consistent reason/creation/symbol scope across facade/waiver exceptions remain open. Reconcile policy `expires_on` versus gate `expires` semantics rather than create another waiver system.
- **Target behaviour:** New first-party architecture drift fails before merge unless covered by a narrowly scoped, documented, expiring waiver with an owner/reason. Pure/inaccessible boundaries are not forced into meaningless integration tests, and no generic governance layer is added.
- **What to implement, in order:**
  1. Audit current architecture/service-boundary coverage and identify only concrete uncovered first-party boundaries with external/stateful behavior or high drift risk.
  2. Extend/reconcile existing waiver/allowlist records: preserve exact path/rule owner/expiry checks, add missing reason/creation and symbol scope where relevant, and align canonical expiry field semantics; no parallel waiver mechanism.
  3. Extend the existing CI architecture gate so a targeted uncovered boundary or new exception fails unless a valid narrow waiver exists.
  4. Reuse expired/missing-owner failures and add only currently uncovered broader-scope/reason/facade behavior cases, without demanding meaningless tests for pure/inaccessible helpers.
  5. Add docs/tests using representative violations, valid waivers, expiry and pure-boundary exclusions.
- **Acceptance criteria:**
  - A known targeted service-boundary coverage gap fails CI without a valid waiver.
  - Every new waiver has owner, reason, exact scope and expiry; expired or widened scope fails.
  - Pure or genuinely inaccessible boundaries are not required to add fake integration tests solely for coverage.
  - Existing public facades/external-effect ownership remain unchanged unless separately approved.
  - Tests prove target violations, valid exceptions, expiry and deterministic diagnostics.

### Luna implementation prompt — R2

```text
Work on R2 — Enforce role boundaries, direct-I/O discipline, and controlled module growth at the current MarketLense HEAD.
Owner specification: docs/backlog/R-engineering.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
### Linked technical implementation slices

Technical IDs below are **subtasks or investigations**, not additional canonical Active outcomes. Status notes are historical catalogue/reconciliation claims and require current-HEAD verification.
 
#### CODE-04 — Distinguish corrupt lock files from active lock owners and repair safe orphan cases

**Primary canonical owner:** [R2](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

- **Status/evidence:** Implemented and locally verified on Windows. `get_lock` preserves typed `lock_file_corrupt` diagnostics, while `acquire_lock` obtains the per-path OS coordination lock before recovering a malformed abandoned record. New records are written to a unique sibling temporary file and atomically replaced only after serialization completes. Truncated JSON, arrays, scalars, invalid fields, and nonfinite timestamps are covered in `tests/test_lock_service.py`; a subprocess crash with a partial record is covered in `tests/test_lock_service_concurrency.py`.
- **Trigger/impact:** Crash or disk-write error between exclusive file creation and payload completion. Ingest can remain blocked indefinitely; operators see a fictitious active run rather than an actionable integrity failure.
- **Luna implementation:** The existing service validates JSON shape, owner/PID/TTL fields, and finite timestamps. Reads return typed corruption; acquisition recovers malformed records only while holding the exclusive sidecar guard. Lock records are staged and atomically replaced; failed writes remove only their own temporary file. Valid legacy records remain readable and malformed payload details are not logged.
- **Success criteria:** Invalid/truncated/scalar/array lock payloads never produce an untyped exception or false active-owner diagnosis. Failed initial writes do not leave a new permanent blocker; a proven abandoned corrupt lock can be recovered safely.
- **Validation:** `python -m pytest -q tests/test_lock_service.py tests/test_lock_service_concurrency.py tests/test_ingest_orchestrator_decomposition.py` — passed on Windows. Coverage includes truncated/object/array/scalar/nonfinite records, atomic write failure cleanup, a reader blocked during another process's partial write, process-crash recovery, and live-owner protection.
- **Priority/effort/dependencies/backlog:** P1 / S–M / safe automated reclaim depends on CODE-05; explicit diagnosis can land first. Concrete R3/A20/A21 extension.

**Luna implementation prompt — CODE-04 (copy/paste)**

```text
Implement CODE-04 — Distinguish corrupt lock files from active lock owners and repair safe orphan cases.
Objective: Deliver the verified behavior specified immediately above under canonical R2.
Source: docs/backlog/R-engineering.md, technical slice CODE-04.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update R2 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
#### CODE-05 — Fence filesystem lock eviction and release against replacement owners

**Primary canonical owner:** [R2](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

- **Status/evidence:** Implemented and locally verified on Windows with simultaneous subprocess tests. Every current service read/acquire/stale-eviction/release operation is serialized through a persistent sibling coordination file (`flock` on POSIX, `LockFileEx` on Windows). New lock records carry unique generations; release requires exact owner, PID, and generation. Legacy records remain readable and can be released only by matching owner/PID without a generation, while tokenless callers cannot remove a new record.
- **Trigger/impact:** Concurrent restart/recovery or release racing reacquisition. Two expensive ingest runs can both believe they own the singleton lock, leading to duplicate provider work and conflicting persisted outputs. The existing dead-PID and tiny-request-TTL tests cover sequential behavior only.
- **Luna implementation:** The canonical service now uses one blocking cross-process OS guard for inspection, acquisition, eviction, recovery, and release. Stale/dead-owner checks and unlink/write transitions occur inside that guard. The sidecar is persistent and must not be deleted. Existing TTL behavior is unchanged; tokenless release is restricted to legacy records.
- **Success criteria:** At most one live generation is granted under competing acquisitions; a stale release cannot delete a replacement; incomplete locks are recoverable only while holding exclusive coordination. Supported Windows and Ubuntu semantics agree.
- **Validation:** The focused lock suite passed on Windows, including two simultaneous acquisitions, simultaneous dead-owner eviction, mid-write inspection, crash recovery, and stale-generation release. The Ubuntu `flock` branch is exercised by the repository CI run for the pushed commit; report its result only after that run completes.
- **Priority/effort/dependencies/backlog:** P1 / M / audit lock contract call sites and coordinate CODE-04. Specific A21/R3 safety work; do not introduce a generic distributed lock system.

**Luna implementation prompt — CODE-05 (copy/paste)**

```text
Implement CODE-05 — Fence filesystem lock eviction and release against replacement owners.
Objective: Deliver the verified behavior specified immediately above under canonical R2.
Source: docs/backlog/R-engineering.md, technical slice CODE-05.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update R2 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
 
## R3. Restore service quality coverage above the retained baseline

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** none; outcome specification stands alone.

- **Baseline:** `docs/quality/baseline_2026-02-21.json`, generated July 12 under a legacy filename, records services 82.5763%. CI enforces this historical threshold alongside the separate 75% floor. The artifact lacks producer SHA, command/environment and passing-run provenance; no current coverage/regression was measured here. Preserve the enforced threshold and obtain one attributable exact-commit full-suite/gate baseline with meaningful behavior coverage. Focused behavior coverage now also protects exact-nanosecond checksum-sidecar freshness, corrupt-lock diagnosis, and atomic same-key idempotency checksum conflicts; these checks do not refresh the exact-commit full-suite coverage baseline.
- **Target behaviour:** Behavior-focused tests protect high-risk stateful/external paths; passing exact-commit CI retains at least the enforced historical service threshold and supplies a fully attributable baseline without other domain regressions.
- **What to implement, in order:**
  1. Run/inspect exact current coverage by service module and rank uncovered behavior by operational risk, focusing first on ledger/recovery, browser-worker lifecycle, artifact lineage and other durable external/stateful paths.
  2. Add tests that assert returned contracts, persisted state, retries/idempotency/failure handling or boundary calls—not lines executed solely for coverage.
  3. Re-run focused suites and then the full CI/coverage command on one exact commit; retain the measured global/contracts/generators/orchestrators/services/control-plane values.
  4. Fix real regressions exposed by the tests without adding exemptions or lowering the 75% floor.
  5. Refresh the baseline only from passing exact-commit suite/gates with producer SHA, commands/environment, domain values and input artifact hashes. The historical threshold remains enforced until a justified attributable replacement passes.
- **Acceptance criteria:**
  - `src/services` coverage is **not below 82.5763%** on the retained passing exact-commit full-suite measurement and increases where the selected behavior tests add meaningful protection.
  - Global/generator/orchestrator coverage does not regress from its retained release baseline.
  - Added tests cover observable contracts/state/failure behavior; no coverage-only dead paths, exclusions, or lowered thresholds are introduced.
  - Baseline artifact records exact SHA, command/environment and measured values and is updated only after all relevant tests/gates pass.

### Luna implementation prompt — R3

```text
Work on R3 — Restore service quality coverage above the retained baseline at the current MarketLense HEAD.
Owner specification: docs/backlog/R-engineering.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
---
 
## R6. Review bounded-log reduction telemetry and remediate recurring callers

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** none; outcome specification stands alone.

- **Baseline:** Python logging bounds payloads and retains reduction metadata under `fields.log_payload_reduced` in the original reduced event (`src/utils/logging.py`), not a separate event. Recurring-caller percentile/grouping/remediation aggregation remains absent. Use metadata-only evidence without reconstructing discarded values; P2 owns PHP emission safety.
- **Target behaviour:** Release/operator evidence shows where bounded-log reduction is occurring, how large attempted events are, and which modules/events repeatedly trigger reduction, without retaining/reconstructing discarded content. Recurring callers become explicit remediation work.
- **What to implement, in order:**
  1. Define a read-only aggregation contract for reduction count, module/event, attempted-size percentiles, retained-size/budget status, time window/build identity and bounded caller identity.
  2. Aggregate only fields.log_payload_reduced metadata plus bounded original event/module/run/build identity. Derive retained size from the safe serialized event only if needed and document it; never reconstruct dropped values.
  3. Add deterministic thresholds for “recurring caller” and map threshold breaches to an owner/existing backlog/remediation reference rather than auto-mutating logging code.
  4. Integrate the scorecard into release evidence/operator review with explicit zero-event state.
  5. Add redaction/content tests using source/prompt/browser/model-like payloads and verify the aggregate cannot contain them.
- **Acceptance criteria:**
  - Release evidence reports reduction count, event/module grouping and attempted-size percentiles with explicit zero state.
  - Scorecard contains no source text, prompts, model output, browser terminal text, credentials or discarded raw values.
  - Recurring callers above threshold are linked to an owner/remediation item and remain reviewable; no automatic weakening of event bounds occurs.
  - Aggregation is deterministic for the same retained log set and tests prove redaction preservation.

### Luna implementation prompt — R6

```text
Work on R6 — Review bounded-log reduction telemetry and remediate recurring callers at the current MarketLense HEAD.
Owner specification: docs/backlog/R-engineering.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
---
 
## R7. Prove recoverable backups and full-state disaster restoration

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `CODE-10`.

- **Baseline:** Process recovery exists. The strict evidence collector already uses SQLite backup, hashes/provenance and atomic evidence-bundle finalization. These are review primitives, not an operational cross-store backup set, runtime restorable marker, empty-target restore or lost-host drill. Reuse suitable primitives while proving independent operational consistency and safe resume. The idempotency read boundary now rejects malformed or wrongly shaped retained outcomes with a typed nonretryable integrity error and preserves the row; the cross-store backup and restore drill remains unproven.
- **Target behaviour:** A backup is considered restorable only when one manifest proves a consistent, complete, integrity-checked snapshot of all required state. Restore occurs into an empty isolated target, validates schema/lineage/artifact closure before activation, and produces a reviewable resume plan. It never silently overwrites live state or replays WordPress, Drive, browser, mailbox, or model side effects.
- **What to implement, in order:**
  1. Inventory the canonical databases, WAL/sidecar requirements, artifact/source roots, queue/checkpoint/idempotency state, configuration/schema identities, and publication references required for each supported recovery profile. Classify sensitive/source material, retention, ownership, and dependencies; exclude reproducible caches only when the manifest records how they are safely rebuilt.
  2. Define a versioned backup-set manifest with snapshot ID/time, producer SHA, profile, schema versions, queue/checkpoint watermarks, database and artifact hashes/sizes, referential dependencies, retention/access-control metadata, and a final completeness marker. Standard logs retain only bounded identifiers/counts/hashes, never backed-up content or secrets.
  3. Implement consistent snapshot creation behind the existing filesystem/database service boundaries: coordinate writers, use SQLite's supported online backup/transaction semantics, copy immutable files only after referenced state is fixed, verify each member, and write the completeness marker last. Any interruption leaves an identifiable non-restorable set rather than a plausible partial backup. Reuse suitable SQLite snapshot/hash/atomic-finalization primitives while separately proving coordinated operational referential closure; do not turn the review collector into a recovery manager.
  4. Add offline verification for SQLite integrity/foreign keys, hashes, schema compatibility, artifact/source referential closure, queue/checkpoint/idempotency coherence, manifest authenticity, retention, and destination access controls. Reject truncated, tampered, mixed-snapshot, missing-member, stale-schema, or unsupported-version sets with typed remediation.
  5. Implement restore only to an empty isolated target. Re-run approved migrations where required, verify the restored state again, and emit a deterministic resume/read-only reconciliation plan showing held/runnable work and external records that require authoritative readback. Activation or replacement of a live installation remains an explicit operator procedure with a documented rollback.
  6. Run retained disaster drills from a representative in-flight cohort, including crash points during snapshot, corrupted/truncated members, missing artifacts, WAL activity, and restoration followed by the bounded discovery-to-publish validation workflow in zero-write mode. Document the operator procedure, storage protection, declared objectives, evidence path, and recurring drill responsibility without adding an in-process scheduler.
- **Acceptance criteria:**
  - The supported single-host profile declares an **RPO of no more than 24 hours and an RTO of no more than 4 hours**, and a retained exact-SHA drill restores a representative in-flight state within those objectives.
  - After restore, all database integrity/foreign-key checks pass; every required source/artifact/lineage reference resolves to the declared hash; queue, lease, checkpoint, budget, remediation, and idempotency states reconcile to the manifest with no orphaned or cross-snapshot records.
  - An incomplete, interrupted, truncated, tampered, mixed, or unsupported backup never receives a restorable marker and fails closed with a typed, actionable reason before activation.
  - Restore to a non-empty/live target is blocked by default. The drill performs no provider, Drive, mailbox, browser, or WordPress write, and resuming/replaying restored publication work produces no duplicate public side effect.
  - Backup and restore logs, manifests, tests, and retained evidence expose no credential, prompt/model payload, source text, email content, or personal data; backup storage containing sensitive material uses the documented access-control and encryption-at-rest mechanism.
  - Focused tests cover consistent SQLite/WAL snapshotting, writer interruption, missing/tampered artifacts, cross-snapshot mixing, schema migration/compatibility, empty-target enforcement, lineage/idempotency reconciliation, and zero-write resume; the documented full drill is repeatable from one canonical command.

### Luna implementation prompt — R7

```text
Work on R7 — Prove recoverable backups and full-state disaster restoration at the current MarketLense HEAD.
Owner specification: docs/backlog/R-engineering.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
### Linked technical implementation slices

Technical IDs below are **subtasks or investigations**, not additional canonical Active outcomes. Status notes are historical catalogue/reconciliation claims and require current-HEAD verification.
 
#### CODE-10 — Fail closed with typed errors on corrupt persisted idempotency outcomes

**Primary canonical owner:** [R7](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

- **Status/evidence:** Confirmed and locally reproduced. `src/services/idempotency_service.py:99–113`, `_row_to_record`, silently replaces valid JSON with wrong shape (e.g. `[]`) by `{}` and still returns a completed record; malformed JSON escapes as untyped `JSONDecodeError`. Replacing both persisted payloads by `[]` yielded `found=True, outcome_payload={}, artifact_references={}`. Publish `_load_publish_idempotency` reconstructs `PublishOutcome(**payload)`, so empty replay data produces an unrelated construction error instead of a clear retained-state integrity failure.
- **Trigger/impact:** Bad migration/manual restoration, storage corruption, or incompatible producer shape. Recovery cannot distinguish a completed side effect with missing proof from legitimate empty data; error classification and safe replay are undermined.
- **Luna implementation:** Validate persisted JSON object shape and mandatory record fields at the service boundary. Convert decode/shape failures into one nonretryable canonical integrity AppError with safe key/hash context, never payload contents. Leave the row intact for diagnosis and block regeneration/external side effects until an explicit repair has re-established provenance. Workflow-specific outcome reconstruction should also wrap schema incompatibility in its own stable typed code.
- **Success criteria:** Malformed JSON, array/scalar outcomes, invalid artifact refs, and missing mandatory record identities cannot return a valid `found=True` completion. Valid legitimately empty dictionaries remain permitted only where their documented workflow outcome schema allows them. Logs expose no retained payload content.
- **Validation:** Public service calls against real temporary databases with corrupt JSON, wrong shapes, incomplete fields, and valid fixtures; run downstream publish/acquisition replay tests with external boundaries replaced by recorded fixtures and assert zero external writes on corrupted proof. Verify exact AppError code/retryability and preserved row.
- **Priority/effort/dependencies/backlog:** P1 / S / compatible with CODE-08 but independently implementable. Specific R3/R7 integrity acceptance criterion; completed idempotency/readback milestones do not cover corrupt persisted payloads.

**Luna implementation prompt — CODE-10 (copy/paste)**

```text
Implement CODE-10 — Fail closed with typed errors on corrupt persisted idempotency outcomes.
Objective: Deliver the verified behavior specified immediately above under canonical R7.
Source: docs/backlog/R-engineering.md, technical slice CODE-10.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update R7 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
