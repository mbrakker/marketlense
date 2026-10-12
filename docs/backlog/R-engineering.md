# Architecture, engineering, release, and disaster recovery

Canonical owner IDs: R1, R2, R3, R6, R7, R8, R9. This document contains **Active outcome specifications and their retained technical proposal slices**. Status belongs to [CONSOLIDATED_TODO.md](../../CONSOLIDATED_TODO.md), not to individual proposal sections. The complete source texts are preserved unchanged in the [historical backlog](archive/CONSOLIDATED_TODO-20261011-preconsolidation.md) and [historical proposal catalogue](archive/10improvements-20261011-preconsolidation.md).

Before implementing a slice, verify its historic diagnosis at current HEAD; use its **Luna implementation prompt** together with the full evidence and criteria immediately above it. Proposed thresholds are acceptance targets, not current results. Closed parent milestones are not reopened by a proposal's historical wording.

---
 
## R1. Publish release-evidence reviews where reviewers work

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `VER-10`.

- **Baseline:** The strict CTO collector retains finite representative/smoke/not-declared scope, freshness and producer provenance. The existing GitHub job summary compares release-review and deterministic queue evidence with the exact tested SHA/build, reports their canonical validation separately from runtime representativeness and artifact-upload completeness, and emits fixed metadata only. It marks absent, stale, incompatible, contradictory, and mismatched review evidence non-green. The summary runs after the existing bundle upload and distinguishes upload-step success from configured required-file completeness. Checked-in runtime evidence from another SHA is historical/unmatched; representative scope remains operator-declared rather than proof that representative processing ran. Do not rebuild collection/taxonomy or change release approval gates to address these distinctions.
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
 
<a id="ver-10"></a>
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
 
<a id="code-04"></a>
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
 
<a id="code-05"></a>
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

**Canonical status:** Closed in [the unified register](../../CONSOLIDATED_TODO.md). This specification and its implementation evidence are retained for historical reference. **Mapped technical slices:** none; outcome specification stands alone.

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

**Implementation and verification (2026-10-11):** The CTO evidence collector
emits the versioned `log_reduction_scorecard.json` artifact and bounded totals
in its executive summary. It reuses the full structured-event parser pass when
`--fresh-after` is supplied and reports `unavailable` when that pass is not
available. The scorecard uses nearest-rank size percentiles, compares retained
serialized JSON message bytes with the recorded maximum, flags three or more
reductions for a validated module/event pair, and routes review to the module
owner and this R6 item. Its persisted remediation reference uses the canonical
R6 heading anchor. It lists at most 100 caller groups and reports an explicit
partial state and overflow reference when more groups exist. It does not alter
runtime logging or release approval checks.

The exact-HEAD fixture produced an available scorecard and executive summary
for three reductions, one recurring `src.services.example/bounded_event`
group, and p50/p90/p95/p99/max attempted sizes of 24,000/40,000/40,000/40,000/
40,000 bytes. The actual read-only scan of
`logs/market_lense_2026-10-08.log` found zero reductions in 20,444 structured
events; all 20,444 module/event identities fit the safe grammar (75 distinct
module names), timestamps were available, and producer build identity was
unavailable. This was one retained log file, not a full retained-corpus audit.
The fixture output was inspected for metadata-only content, and separate
sensitive-content fixtures verify that unsafe identities and payload text do
not enter the scorecard.

Focused verification:

```text
python -m pytest -q --cov=src.contracts.log_reduction --cov-report=term-missing tests/test_log_reduction_scorecard.py tests/test_log_reduction_contract.py tests/test_collect_cto_review_evidence.py tests/test_logging_schema.py tests/test_gui_utils.py tests/test_release_evidence_summary.py tests/test_release_evidence_review.py
162 passed; new scorecard contract coverage 100% (9 ResourceWarnings from SQLite-backed evidence fixtures)
python -m ruff check src/contracts/log_reduction.py scripts/quality/_cto_review_evidence/log_reduction_scorecard.py scripts/quality/_cto_review_evidence/log_content_leakage.py scripts/quality/collect_cto_review_evidence.py tests/test_log_reduction_scorecard.py tests/test_log_reduction_contract.py tests/_test_collect_cto_review_evidence/cases_02_strict_collection_and_leakage.py
All checks passed
python -m ruff format --check src/contracts/log_reduction.py scripts/quality/_cto_review_evidence/log_reduction_scorecard.py scripts/quality/_cto_review_evidence/log_content_leakage.py scripts/quality/collect_cto_review_evidence.py tests/test_log_reduction_scorecard.py tests/test_log_reduction_contract.py tests/_test_collect_cto_review_evidence/cases_02_strict_collection_and_leakage.py
All seven files already formatted
python scripts/ci/check_contract_schemas.py
Contract schema snapshot gate passed
python scripts/ci/check_architecture_imports.py
Architecture import gate passed
python scripts/ci/check_bounded_logging.py
Bounded logging gate passed
$env:TYPECHECK_CHANGED_ONLY='true'; python scripts/ci/run_type_check.py
Changed contract type check passed; tracked repository baseline matched
```

`python scripts/ci/check_documentation.py --check-generated` still reports ten
pre-existing missing heading anchors in the R-engineering backlog links. The
scorecard and its local fixture collector made no external provider calls or
writes; evidence artifacts were written only to temporary test output. R6
implementation acceptance is complete; caller remediation remains a
review-driven action when a scanned corpus flags an actual recurring caller.

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
 
<a id="code-10"></a>
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


<a id="r8-harden-windows-artifact-path-construction-and-reuse"></a>
## R8. Harden Windows artifact path construction and reuse

**Canonical status:** Active. **Priority:** P1, with residual inventory PATH-06 at P2. **Added:** 2026-10-11. **Evidence baseline:** targeted static inspection at observed main HEAD e389f3c3796d4cfc59fdd273a26684812790b82c; it was not a reproduced production incident or exhaustive repository-wide audit. PATH-01, including its filename-collision correction, was verified on native Windows at producer commit `08756d0740023b1c480b7789c9359a1018780a9d`; PATH-02..PATH-06 remain open R8 implementation slices, not new canonical outcomes.

- **Baseline:** Mailbox attachment and ZIP paths use sanitized but unbounded message IDs and filenames; browser artifact copies retain source filenames, append unbounded collision counters, and nest under host/hash download roots; candidate extraction caches use long Drive titles; OCR chunk filenames append page ranges to the full PDF stem; crop-refinement outputs use unbounded report-name directories and generate fingerprint sidecars; cover fingerprint lookup reconstructs slug-based analysis paths and can miss compacted analysis-store paths. Browser profile/capture paths, cover image temporary writes, cache/checkpoint compaction fallbacks and isolated canary roots merit scoped follow-up. These are code-observed vulnerabilities, not verified failures.
- **Existing protection to reuse:** src/utils/path_utils.py provides bounded filenames; src/services/file_service.py bounds atomic temp names; src/services/report_analysis_store_service.py compacts persisted report packs; PDF crop-region and preview outputs compact paths. Preserve these where already sufficient; avoid duplicate systems or universal path rewriting.
- **Target outcome:** Valid reports can acquire, persist, split for OCR, crop, resume, render and generate covers on reasonably deep standard Windows roots, without depending on opt-in long-path support. File paths and their temporary/sidecar variants stay within supported full-path and component budgets; compact naming remains deterministic and collision-resistant, while original filenames, identities, hashes, lineage, cache and persisted references remain correct. For impossible operator-supplied roots, fail with typed actionable non-retryable errors before expensive side effects where practical; never silently skip or accept missing artifacts.
- **Execution order:** Reinspect current HEAD; PATH-01 mailbox is implemented and verified. Continue with PATH-02 browser, PATH-03 candidate cache/OCR, PATH-04 crop refinement, PATH-05 cover paths, then PATH-06 residual checks. Implement and verify one meaningful slice per commit; no new service/framework, blanket retry, generic filesystem abstraction, unnecessary renaming, or extra model calls.
- **Outcome acceptance:** Focused Windows/portable tests prove long-root, Unicode, long-name, collision and impossible-root cases, including direct and ZIP PDFs, browser downloads, OCR chunk re-open, crop/fingerprint and cover readback, deterministic replay and safe failure. Verify that compacted names are consumed via canonical persisted references, historical paths still read, and checkpoints/cache identities are not broken. Run a native Windows test for high-risk paths when available; state explicitly if unavailable. Record exact SHA, checks/results, scope, residual gaps and rollback. Close R8 only after a scoped scan of remaining routine path producers and end-to-end affected artifact readback, not on documentation alone.

### Luna implementation prompt — R8

~~~text
Implement the next unverified R8 / PATH-NN Windows-path reliability slice at current MarketLense HEAD.
Inspect AGENTS.md, the owning R8/PATH specification, actual producer/consumer code, tests and path contracts.
Fix the earliest verified path-production or reference mismatch using existing utilities/services.
Preserve identities, original names in metadata, source hashes, cache/checkpoint compatibility,
atomic writes, path traversal/ZIP safeguards, validation and publication gates.
Test long/deep and normal paths, deterministic collision behavior, impossible roots, and downstream readback.
Report exact test results, native Windows coverage or its absence, remaining gaps and producer SHA.
Update R8/proposal disposition with evidence; do not close the parent early. Commit and push.
~~~

### Linked technical implementation slices — Windows path-length review

**Technical status:** PATH-01 is implemented and verified below. PATH-02..PATH-06 remain proposals from 2026-10-11 source inspection; recheck each at implementation HEAD and reconcile any protection already present.

<a id="path-01"></a>
#### PATH-01 — Bound mailbox PDF and ZIP attachment destinations (P1)

- **Modules:** src/services/mailbox_acquisition_service.py — _safe_file_name, _artifact_path, _materialize_attachment and ZIP staging.
- **Problem:** Unbounded provider-message directory and direct/ZIP PDF basename can exceed full-path or component limits; sanitization alone is insufficient.
- **Implementation:** Bound full destination and staging paths; preserve original names/provider IDs/archive provenance separately; derive stable names from lossy filename identities, plan direct-PDF collisions before writing, and reject ZIP output identities that collide within or across attachments while retaining ZIP safety limits.
- **Acceptance:** Long IDs, long filenames, ZIP members with nearly identical names, repeated writes and nested usable roots persist distinct readable PDFs; impossible roots yield typed errors, never overwrite or silently lose a candidate.
- **Codex guidance:** Fix the producer using existing path helpers; test direct and ZIP readback plus collisions and error handling, then commit/push.
- **Verified evidence (2026-10-12; producer commit `08756d0740023b1c480b7789c9359a1018780a9d`):** Native Windows 11 / CPython 3.14.2. `python -m pytest -q tests/test_mailbox_acquisition_zip.py tests/test_mailbox_acquisition_config.py tests/test_mailbox_imap_protocol.py tests/test_mailbox_preflight_call_count.py tests/test_mail_report_acquisition_orchestrator.py tests/test_acquisition_ingest_handoff_orchestrator.py tests/contracts/test_contract_roundtrip.py tests/test_contract_schema_gate.py` — 2,374 passed. Regression tests confirm distinct `A?B.pdf` / `A*B.pdf` destinations and same-name/different-payload direct destinations, exact byte readback, stable repeat paths, distinct Unicode ZIP member paths, genuine ZIP duplicate rejection, and rejection of a ZIP/direct cross-attachment collision before staging. ZIP staging cleanup, long near-identical names/message IDs, short ASCII compatibility, and non-retryable impossible-root errors remain covered; the existing acquisition-to-ingest handoff consumed the persisted artifact successfully. A native deep-root probe persisted and reopened both direct collision outputs and both Unicode ZIP outputs at 204 UTF-16 path units each. All destinations and ZIP temp paths remain within the 240-unit budget. Windows long-path policy was not explicitly disabled.
- **Quality checks:** `python scripts/ci/check_formatting.py`, `python scripts/ci/check_ruff_lint.py`, `python scripts/ci/run_type_check.py`, `python scripts/ci/check_architecture_imports.py`, `python scripts/ci/check_role_io_boundaries.py`, `python scripts/ci/check_service_boundary_map.py`, and `python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json` all passed. The full-repo type gate matched 0 tracked errors across 775 source files.

<a id="path-02"></a>
#### PATH-02 — Bound browser download, copied artifact, capture and profile paths (P1)

- **Modules:** src/services/_browser_report_download/request.py; _browser_runtime/_terminal_assets/artifacts.py and capture.py; _browser_runtime/_session_lifecycle/cleanup.py.
- **Problem:** Host/hash download subdirectories, original filenames/collision suffixes, URL-derived rendered PDFs and managed profile names are not validated against one complete budget.
- **Implementation:** Bound destination names at their owning producer; retain canonical URL/cache identity, session cleanup and verified PDF semantics. Do not treat a failed materialization as successful acquisition or trigger extra browser/model work.
- **Acceptance:** Long host, downloaded name, repeated collisions and deep roots are handled deterministically; captured PDFs and profiles create and clean up or fail explicitly, with correct stored artifact paths.
- **Codex guidance:** Trace actual browser file creation/readback and cleanup; fix verified gaps with small changes, run focused paths and commit/push.

<a id="path-03"></a>
#### PATH-03 — Bound candidate PDF caches and OCR chunk names (P1)

- **Modules:** src/orchestrators/candidate_extraction_orchestrator.py; src/services/_pdf/text.py.
- **Problem:** Candidate cache derives its name from an unbounded Drive filename; OCR chunk suffixes extend the entire source PDF stem.
- **Implementation:** Use stable identity/content-aware compact filenames within the resolved cache/chunk root. Preserve Drive file identity, MD5, OCR source/chunk lineage, chunk order and cache/resume behavior; do not unnecessarily rework the main file-ID cache.
- **Acceptance:** Long source names yield correct, reopenable OCR chunks and distinct cache entries; replay hits the intended source; unfit roots fail explicitly without repeated work.
- **Codex guidance:** Verify cache/OCR contracts and downstream consumers, implement a focused naming fix and test roundtrip/reuse before commit/push.

<a id="path-04"></a>
#### PATH-04 — Bound crop-refinement images and fingerprint paths (P1)

- **Modules:** src/services/_pdf/_crop/refine.py and its sidecar writer; compare already protected _crop/regions.py and _crop/preview.py.
- **Problem:** The report-derived crop_refine_pages directory and longer image fingerprint/QA sidecars can breach Windows budgets.
- **Implementation:** Reuse existing report-name/path compaction, budget all output/sidecar/temp variants, preserve relative references, page identity and crop QA.
- **Acceptance:** Long report names render and reopen page images with verified fingerprint sidecars, while ordinary paths, crop semantics and source provenance remain unchanged. Unfit roots fail explicitly.
- **Codex guidance:** Reuse existing crop naming patterns, verify downstream sidecar proof, then commit/push.

<a id="path-05"></a>
#### PATH-05 — Resolve compacted analysis artifacts and bound cover assets (P1)

- **Modules:** src/orchestrators/cover_image_orchestrator.py; src/utils/cover_path_utils.py; src/services/cover_image_service.py; canonical src/services/report_analysis_store_service.py.
- **Problem:** Reconstructed report_analysis/artifacts.json may not match stored compacted slug/pack paths; cover asset paths are only component-bounded; cover temporary filename appends .tmp.
- **Implementation:** Reuse actual persisted/authoritative analysis artifact path, not a manually reconstructed slug; bound full cover/card and temporary paths while retaining existing references, cover style identity and idempotent reuse.
- **Acceptance:** Long titles that compact both analysis slug and pack remain cover-generatable/replayable with correct fingerprint; existing legacy paths still read; near-limit .tmp outputs succeed or fail typed.
- **Codex guidance:** Trace report-analysis write -> saved reference -> cover read -> cover output; fix producer and consumer at the correct boundaries, test readback/reuse, commit/push.

<a id="path-06"></a>
#### PATH-06 — Recheck compact fallbacks and residual nested paths (P2)

- **Modules:** src/services/file_service.py checkpoint fallback; src/generators/report_generation_shared.py cache fallback; scripts/quality/ias_live_canary_runner.py nested roots; other credible path producers discovered by focused inventory.
- **Problem:** Some compact fallbacks return paths without checking the final compact candidate; nested canary/test roots can exhaust the remaining path budget.
- **Implementation:** Measure final path, component, temp and sidecar lengths; fix only actual remaining high-likelihood gaps, and surface genuinely impossible roots as typed actionable diagnostics.
- **Acceptance:** Checkpoint/cache replay and isolated work roots survive realistic Windows depth; impossible roots fail predictably; final report identifies areas inspected and untested native Windows behavior.
- **Codex guidance:** Inventory only credible remaining paths after PATH-01..05, avoid building broad new infrastructure, verify focused cases and commit/push.


<a id="r9-accelerate-ci-validation-fivefold-without-weakening-release-gates"></a>
## R9. Accelerate CI validation fivefold without weakening release gates

**Canonical status:** Active. **Priority:** P1 engineering efficiency; independent of intelligence-output critical-path priorities. **Added:** 2026-10-11. **Mapped technical slices:** none. R9.1–R9.4 below are phases of one new outcome, not additional legacy proposal IDs. R9.1 and R9.2 are complete; R9.3–R9.4 remain. No fivefold speedup is claimed.

- **Observed baseline:** The full workflow is a sequential Ubuntu job covering Python/PHP setup, static and policy checks, eight-worker pytest/coverage, mutation, PDF/prompt/public-report quality and release-evidence assembly. Three successful main push runs share workflow blob `8dfb596604fbc41adb4a3483eaa4cc14963a1be5`, lock blob `c8e84edddde48a4d2f7fb8f3c10dca7f8a92ebda`, Ubuntu 24.04, CPython 3.12.15, 7,229 collected pytest cases with the same 7,205 unique node IDs (SHA-256 `70f8bff047c9fa54a0fda0b494d14b0afa88b27567ec888327c69d5d3e0edbef`), 17 mutation targets / 68 mutants with 67 killed, 86.21% coverage, and complete release evidence. GitHub run and job timestamps provide wall and stage durations; all three runs passed.

  | Baseline run | Exact source SHA | Workflow / job | Setup through locked install / pip step | Pytest step / cases | Mutation step / results |
  | --- | --- | ---: | ---: | ---: | ---: |
  | [38174895618](https://github.com/mbrakker/marketlense/actions/runs/38174895618) | `7b56f0e8403008a7dfb64de511ab39bf8b430715` | 15:48 / 15:45 | 2:32 / 2:22 | 4:21 / 7,229 | 7:39 / 67 of 68 killed |
  | [38176147143](https://github.com/mbrakker/marketlense/actions/runs/38176147143) | `b3464bc5bbdb3d03149d9285506af69d8555d4e6` | 23:09 / 23:05 | 3:16 / 3:00 | 7:04 / 7,229 | 11:02 / 67 of 68 killed |
  | [38176419426](https://github.com/mbrakker/marketlense/actions/runs/38176419426) | `96a383f50cd776eb981f13a33ec6452c34924782` | 15:13 / 15:10 | 2:19 / 2:11 | 4:19 / 7,229 | 7:22 / 67 of 68 killed |

  The medians are 15:48 full-workflow wall time, 15:45 active job time, 2:32 from Python setup through dependency install, 2:22 for pip installation alone, 4:21 pytest, and 7:39 mutation. The observed ranges are wide: 15:13–23:09 workflow wall time, 4:19–7:04 pytest, and 7:22–11:02 mutation. Each uploaded a 17-file bundle; the release review passed all 11 required evidence entries with zero unwaived issues. The optional WordPress staging REST gate was skipped by its existing opt-in guard.

- **R9.1 measured change and result (2026-10-12):** Commit `878063ca62f5ee6adbdf43977171040dbd1cf9d2` adds native `setup-python` pip caching keyed by `requirements.lock` and one config regression test. The install remains `python -m pip install --require-hashes -r requirements.lock`; the lock, package versions, hashes, test selection, coverage threshold, mutation targets/scores and release checks did not change. The cache was 4.36 GB. The cold path missed, completed, and saved the cache; both warm paths restored the exact key and completed.

  | Same-SHA run attempt | Cache | Workflow / job | Setup through locked install / pip step | Pytest / cases | Mutation / result | Release review |
  | --- | --- | ---: | ---: | ---: | ---: | --- |
  | [38177811842 attempt 1](https://github.com/mbrakker/marketlense/actions/runs/38177811842/attempts/1) | Cold miss | 24:47 / 24:44 | 2:37 / 2:27 | 7:53 / 7,230 | 11:58 / 67 of 68 | 11/11, 0 issues |
  | [38177811842 attempt 2](https://github.com/mbrakker/marketlense/actions/runs/38177811842/attempts/2) | Warm hit | 23:56 / 23:50 | 2:24 / 1:40 | 7:53 / 7,230 | 11:45 / 67 of 68 | 11/11, 0 issues |
  | [38177811842 attempt 3](https://github.com/mbrakker/marketlense/actions/runs/38177811842/attempts/3) | Warm hit | 23:47 / 23:42 | 2:15 / 1:39 | 7:54 / 7,230 | 11:47 / 67 of 68 | 11/11, 0 issues |

  For this table, setup-through-install runs from `setup-python` start through the end of dependency installation and includes PHP setup. The full-cohort median fell from 2:32 to 2:24 (8 seconds, 5.3%); the two warm runs had a 2:19.5 median (12.5 seconds below baseline). Pip installation alone fell from a 2:22 baseline median to a 1:39.5 warm median, while cache restoration took 25–34 seconds. This is a measured but modest setup gain; the cold path took 2:37. The three post-change jobs used 72.27 active runner-minutes versus 54.00 for the three baseline jobs. GitHub reported zero billable milliseconds for these public-repository Ubuntu jobs.

  All three post-change runs used exact SHA `878063ca62f5ee6adbdf43977171040dbd1cf9d2` and passed the full workflow. Their 7,230 test cases retain every baseline node ID and add only `tests/test_dependency_consistency.py::test_ci_caches_pip_against_the_hash_locked_dependency_manifest`; collection has no omissions. Mutation results are identical per target (17 targets, 68 mutants, 67 killed, same scores and thresholds). Coverage remains 86.21% across 96,929 valid lines. Each exact-attempt release review bound the manifest to its run attempt and SHA, passed 11/11 required entries with zero unwaived issues, uploaded all 17 bundle files, and passed the release-evidence checks.

  Full-CI median job time was 23:50 after the change versus 15:45 before it, so no end-to-end speedup is demonstrated. The post-change pytest median was 7:53 versus 4:21 before, and mutation was 11:47 versus 7:39; these dominate the observed full-job difference and remain the actual critical path in the sequential workflow. The cache experiment does not establish why those stages ran longer. The focused command `python -m pytest tests/test_dependency_consistency.py tests/test_ci_quality_gate_wiring.py tests/test_build_hash_locked_wheelhouse.py` passed (13 tests). No CI timing script was changed: `build_ci_performance_benchmark.py` covers pytest/quality task telemetry, while GitHub job and step timestamps provide actual sequential wall time. Revisit that telemetry when R9.4 introduces multiple jobs.

  The locked environment still contains PyTorch, Triton and NVIDIA/CUDA distributions, but there are no direct PyTorch imports or direct requirements proving they can be removed safely. The existing R5 hash-verified wheelhouse tooling remains unchanged; no production dependency was removed or replaced.

- **R9.2 parallel execution and verification (2026-10-12):** Commit `1d78865d0c4b3c9e43a5a03dc4dfe267a78d62d4` moves the full pytest/coverage and existing quality gates into the `tests` job, runs two isolated mutation partitions concurrently with that job, and makes exact-attempt release evidence depend on successful tests and both mutation workers. The merger accepts each configured target exactly once, checks worker status, run ID and SHA, then writes the existing `mutation_results.json` schema and applies the unchanged score floors. The test selection, eight-worker `--dist=worksteal`, coverage and mutation thresholds, quality checks, and release manifest/review requirements are unchanged. Each job installs the same hash-locked requirements; R5 wheelhouse tooling and `requirements.lock` are unchanged.

  The install command remains `python -m pip install --upgrade pip` followed by `python -m pip install --require-hashes -r requirements.lock`. All four job environments on attempt 4 restored the native `setup-python` pip cache keyed by `requirements.lock`; the test job restored the 4.36 GB cache in about 26 seconds, and locked pip installation took 1:33–1:42 across jobs (the release job took 1:39). This preserves the exact locked environment and hash checks. Cold-miss and warm-hit installation paths were both verified in R9.1; no dependency was removed or replaced. The existing dependency consistency check passed.

  | Successful exact-SHA attempt | Workflow wall | Tests job / pytest | Mutation jobs 0 / 1; longest measured partition | Release-evidence job | Summed active runner time | Result |
  | --- | ---: | ---: | ---: | ---: | ---: | --- |
  | [38213012092 attempt 1](https://github.com/mbrakker/marketlense/actions/runs/38213012092/attempts/1) | 12:52 | 9:26 / 5:47 | 8:45 / 9:09; 6:17 | 3:15 | 30.63 min | Full pass |
  | [38213012092 attempt 2](https://github.com/mbrakker/marketlense/actions/runs/38213012092/attempts/2) | 13:51 | 9:53 / 5:48 | 8:23 / 8:46; 6:25 | 3:41 | 30.77 min | Full pass |
  | [38213012092 attempt 4](https://github.com/mbrakker/marketlense/actions/runs/38213012092/attempts/4) | 15:27 | 11:38 / 8:07 | 6:20 / 6:57; 4:18 | 3:36 | 28.55 min | Full pass |

  All three successful attempts ran exact source SHA `1d78865d0c4b3c9e43a5a03dc4dfe267a78d62d4` on Ubuntu 24.04 / CPython 3.12.15. Their median full-workflow wall time is 13:51; the median test-job time is 9:53 and median pytest time is 5:48. Each completed 7,264 tests. Telemetry contains 7,288 report rows because 24 subtest reports repeat existing node IDs; this same shape was present in the baseline telemetry. Coverage passed at 86.19% (83,802 of 97,227 lines). Each mutation result contains all 17 targets and 68 mutants, kills 67, and retains the baseline per-target scores and minimums. The partition workers finished before the test job in all three passes, so mutation is no longer on the observed wall-clock critical path. The observed critical path is the full test job followed by release-evidence assembly (median release job 3:36). GitHub API job timestamps sum to a 30.63-minute median active runner usage per successful run, up 6.54 minutes (27.2%) from R9.1's 24.09-minute median. The public-repository API reports zero billable milliseconds; runner use still increased.

  Against the immediately preceding hash-cached, sequential workflow median of 23:56, the measured wall-time improvement is 10:05 (42.1%, or 1.73×). Against R9's original 15:48 baseline, the current median is 1:57 faster (12.3%, or 1.14×). The 5× target of about 3:10 remains unmet by 10:41. One four-partition pilot ([run 38211776311](https://github.com/mbrakker/marketlense/actions/runs/38211776311), SHA `29fb1fb9f401f9a914b4c3298558f59a5ee6f872`) passed in 11:20 and consumed 32.90 active runner-minutes, but its single sample had a much shorter pytest stage (4:37); it is not a comparable cohort and does not establish a four-versus-two worker speedup. Two mutation partitions were retained based on that resource use and the three-run two-partition cohort.

  The same-SHA attempts were not uniformly green: attempt 3 failed one timing-sensitive test, `tests/test_workflow_supervisor_parallelism.py::test_source_ingest_backlog_progresses_before_deeper_report_stages` (7,263 passed, 1 failed). The failure was `source_progress_overtaken.is_set()`; the unchanged production supervisor/test files predate R9.2. The release-evidence job correctly failed closed and produced no approved bundle. The isolated test passed six consecutive local Windows runs, but that does not establish Linux reliability or the root cause. Attempt 4 then passed the full workflow; report the observed failure as 1 of 4 attempts (25%), not as a proven pre-existing flake. The optional WordPress staging REST check was skipped by its existing opt-in guard. Two earlier implementation pilots ([38210594042](https://github.com/mbrakker/marketlense/actions/runs/38210594042), [38210843960](https://github.com/mbrakker/marketlense/actions/runs/38210843960)) failed on mutation classification and workflow compatibility defects that were corrected before the measured SHA; neither is included in the timing cohort.

  Attempt 4's final release bundle contains 17 files. Its manifest binds release ID `38213012092-4` to the exact source SHA; all 11 required entries and the review passed with zero issues. The downloaded files' SHA-256 values match all 11 manifest entries. The release review passed 11/11, and the mutation and test telemetry identify the same SHA and attempt. The default `out/ci_performance_benchmark.json` reports 793,027 ms as its additive stage total, not the observed 927,000 ms workflow wall time; GitHub workflow/job timestamps were used for wall and critical-path comparisons. R9.4 owns correcting that telemetry for parallel execution. No PR failure-feedback timing cohort was available.

  Exact command evidence from the attempt 4 manifest: `python scripts/quality/run_pytest_with_telemetry.py --output-json out/test_telemetry_ci.json --repository-commit-sha 1d78865d0c4b3c9e43a5a03dc4dfe267a78d62d4 --evidence-run-id 38213012092-4 -- -n 8 --dist=worksteal --cov=src --cov-report=xml --cov-report=term-missing`; mutation merge: `python scripts/ci/merge_mutation_partitions.py --partition-dir out/mutation-partitions --partition-count 2 --expected-sha 1d78865d0c4b3c9e43a5a03dc4dfe267a78d62d4 --expected-run-id 38213012092-4 --worker-conclusion success --quality-command-telemetry out/quality_command_telemetry_ci.json --output-json mutation_results.json`. Attempt 4 was started with `gh run rerun 38213012092`.

  The pushed evidence commit `39f6b12c8f8244cae78cbdbd17e8a7241dfcfe28` then passed a separate documentation-SHA full workflow ([38219179455](https://github.com/mbrakker/marketlense/actions/runs/38219179455)): 15:31 wall, 8:16 pytest (7,264 passed), 6:29 longest mutation partition, 3:11 release-evidence job, and 32.53 summed active runner-minutes; GitHub billed zero milliseconds. Its exact-SHA manifest and mutation/test telemetry identify the documentation commit, all 11 required artifacts pass with matching hashes, and the 17-file review passes with zero issues. This follow-up is validation of the committed docs, not a fourth sample in the implementation timing cohort.

  Focused verification on the implementation SHA: `py -3.12 -m pytest -q tests/test_mutation_ci.py tests/test_release_evidence_workflow.py tests/test_control_plane_quality_gates.py tests/test_quality_metrics.py tests/test_ci_quality_gate_wiring.py tests/test_dependency_consistency.py tests/test_build_hash_locked_wheelhouse.py` — 52 passed; `py -3.12 scripts/ci/check_dependency_consistency.py` — passed; `py -3.12 -m ruff check scripts/ci/run_mutation_gate.py scripts/ci/merge_mutation_partitions.py scripts/quality/quality_metrics.py tests/test_mutation_ci.py tests/test_quality_metrics.py tests/test_release_evidence_workflow.py` — passed; matching `py -3.12 -m ruff format --check` — passed. The full workflow passed on attempts 1, 2 and 4 with unchanged gates and complete exact-SHA bundles.

- **R9.1 parallel-CI pip-cache follow-up (2026-10-12; decision: remove cache):** The controlled candidate commit `64d291f3a768823fd7cfeee5bf635d6e621e9f93` removes `cache: pip` and `cache-dependency-path: requirements.lock` from all three `setup-python` steps (four runner jobs after mutation matrix expansion). Python 3.12, all locked packages/hashes, `python -m pip install --require-hashes -r requirements.lock`, the `-n 8 --dist=worksteal` pytest command, two mutation partitions, thresholds and release-evidence gates are unchanged. The dependency tests now assert there are no pip cache inputs; hash-required install checks remain. `requirements.lock` has the same Git blob `c8e84edddde48a4d2f7fb8f3c10dca7f8a92ebda` as the cached baseline. Existing R5 wheelhouse audit/build tooling remains unchanged and is not wired into these CI install steps. PyTorch, Triton and NVIDIA/CUDA distributions remain in the lock; no dependency was removed or replaced because compatibility was not established.

  The cached comparison reuses the three successful same-SHA runs in the R9.2 cohort (`1d78865d0c4b3c9e43a5a03dc4dfe267a78d62d4`, Ubuntu 24.04 / CPython 3.12.15). The uncached candidate is a later SHA because it includes the intervening R8 mailbox-PDF implementation/tests and documentation; eight mailbox regression node IDs were added and the cache-specific test ID was renamed to test the new configuration. The default pytest command is identical; telemetry had 7,264 unique cached node IDs and 7,272 unique candidate IDs, with no prior node omitted other than the renamed configuration assertion. Both SHAs use the same lock blob, runner family, job topology and mutation configuration. Wall time below is measured consistently from the earliest job start to final release-job completion; active runner time is the sum of job durations.

  | Configuration | Successful attempt | Workflow wall | Tests job / pytest | Longest mutation step | Release job | Active runner-min | Sum setup + install |
  | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
  | Cached, SHA `1d78865d` | [1](https://github.com/mbrakker/marketlense/actions/runs/38213012092/attempts/1) | 12:49 | 9:26 / 5:50 | 6:16 | 3:15 | 30.63 | 9:59 |
  | Cached, SHA `1d78865d` | [2](https://github.com/mbrakker/marketlense/actions/runs/38213012092/attempts/2) | 13:45 | 9:53 / 5:52 | 6:25 | 3:41 | 30.77 | 9:59 |
  | Cached, SHA `1d78865d` | [4](https://github.com/mbrakker/marketlense/actions/runs/38213012092/attempts/4) | 15:23 | 11:38 / 8:12 | 4:18 | 3:36 | 28.55 | 9:19 |
  | Uncached, SHA `64d291f3` | [1](https://github.com/mbrakker/marketlense/actions/runs/38231139338/attempts/1) | 12:26 | 9:09 / 5:37 | 6:20 | 3:08 | 30.30 | 9:30 |
  | Uncached, SHA `64d291f3` | [2](https://github.com/mbrakker/marketlense/actions/runs/38231139338/attempts/2) | 16:16 | 12:15 / 8:10 | 6:16 | 3:52 | 33.50 | 9:50 |
  | Uncached, SHA `64d291f3` | [3](https://github.com/mbrakker/marketlense/actions/runs/38231139338/attempts/3) | 12:18 | 7:26 / 4:24 | 6:15 | 3:22 | 27.13 | 8:51 |

  The cached and uncached medians are 13:45 vs 12:26 wall (79 seconds, 9.6%) and 30.63 vs 30.30 active runner-minutes (20 seconds lower). GitHub reported zero billable milliseconds for both public-repository cohorts. Wall values are recomputed for both cohorts from first job start through final release-job completion; they differ from the earlier R9.2 summary by at most six seconds. The 79-second wall difference is observed, not fully attributable to caching: pytest medians were 5:52 cached and 5:37 uncached, and test-job durations varied substantially on the same uncached SHA (7:26–12:15). The clearer setup comparison is the median sum across all four dependency installs: 9:59 cached vs 9:30 uncached, 29 seconds lower; on the serial tests-plus-release path, the per-run median setup-plus-install sum is 4:53 vs 4:28, 25 seconds lower. Median longest mutation time was 6:16 in both cohorts, and mutation was off the critical path in all cached runs and two of three uncached runs. Thus the repeatable setup evidence favors removing the 4.36 GB cache restore, while the full-workflow wall result should not be presented as a 79-second cache-only speedup.

  Cached `setup-python` steps took 0:26–1:02 and locked installs took 1:33–1:45 per job. With caching removed, `setup-python` completed in 0 seconds at API timestamp resolution and the 12 locked installs took 2:00–2:46 (per attempt, tests / mutation 0 / mutation 1 / release: 2:22 / 2:18 / 2:44 / 2:06; 2:02 / 2:46 / 2:17 / 2:45; 2:12 / 2:33 / 2:06 / 2:00). Every install and dependency-consistency step passed under `--require-hashes`; no package-download, install or hash failure occurred in the three uncached attempts. R9.1's earlier sequential cold-miss and warm-hit measurements remain useful: the cold install took 2:27, warm installs 1:40 and 1:39, and cache restoration took 25–34 seconds. The current no-cache experiment therefore trades faster setup totals for higher variability in individual downloads, without observed installation failure; the sample is too small to infer a reliability-rate change.

  All three uncached attempts passed the full workflow on exact SHA `64d291f3a768823fd7cfeee5bf635d6e621e9f93`: 7,296 report rows / 7,272 unique node IDs, 86.19% line coverage (83,909–83,910 of 97,353 lines), all 17 mutation targets / 68 mutants / 67 killed, and no dependency-integrity failures. Each exact-attempt release bundle had 17 files; its manifest identified the same SHA and run-attempt, all 11 required entries passed, all 11 downloaded SHA-256 values matched, and review passed with zero unwaived issues. The cached cohort's successful attempts were 1, 2 and 4; its excluded attempt 3 failed only the scheduler-fairness test, not dependency installation. This small, cross-SHA sample does not establish a reliability improvement for either configuration.

  Verification commands: `py -3.12 -m pytest -q tests/test_dependency_consistency.py tests/test_ci_quality_gate_wiring.py tests/test_mutation_ci.py tests/test_build_hash_locked_wheelhouse.py` — 39 passed; `py -3.12 scripts/ci/check_dependency_consistency.py` — passed; `py -3.12 -m ruff check tests/test_dependency_consistency.py tests/test_mutation_ci.py` — passed; `py -3.12 -m ruff format --check tests/test_dependency_consistency.py tests/test_mutation_ci.py` — passed; `git push -u origin experiment/r9-pip-cache` started [run 38231139338](https://github.com/mbrakker/marketlense/actions/runs/38231139338), and `gh run rerun 38231139338` produced attempts 2 and 3 on the same candidate SHA. Release bundles were downloaded with `gh run download 38231139338 --name release-evidence-bundle --dir <attempt-specific-temp-directory>` and their manifest hashes checked against all 11 required files. No CI timing telemetry was changed.

  **Decision:** Keep the simpler no-cache CI configuration. It measured a 25-second lower median setup time along the serial test/release path, no meaningful runner-minute or billable-cost increase, three complete green attempts, and no installation failure. The 79-second end-to-end median reduction is reported as observed but not credited wholly to cache removal because the candidate SHA and pytest/static-stage timings differ. The actual bottlenecks remain pytest and release assembly; the next R9.3 investigation should profile the telemetry's longest cases, led by `test_first_attempt_canary_uses_production_submission_and_supervisor_path` (217,216 ms) and `test_source_ingest_checkpoint_hands_off_to_report_selection` (131,893 ms), before changing xdist settings or introducing shards.

  **Merged-main verification and R9.3 follow-ups (2026-10-12):** The no-cache configuration passed the complete push workflow on main SHA `291886c9f7b03edd32985a132ab70552fe4afeeb` ([run 38236442840](https://github.com/mbrakker/marketlense/actions/runs/38236442840)). Measured from first job start to final job completion, wall time was 18:49 and active runner use summed to 37.10 minutes; GitHub reported zero billable milliseconds for this public-repository run. Tests took 11:42 (pytest 8:21; 7,296 telemetry reports / 7,272 unique node IDs), the mutation jobs took 15:14 and 6:43, and release assembly took 3:24. Coverage was 86.19% (83,909/97,353 lines); mutation retained all 17 targets and 68 mutants with 67 killed. The uploaded 17-file bundle binds release `38236442840-1` to this exact SHA; all 11 required entries passed, every manifest SHA-256 matched its downloaded file, and review reported zero issues. All four dependency-installing jobs used the unchanged `--require-hashes` install, with no pip cache configured.

  This verification run had a separate Git checkout outlier: `actions/checkout@v4` in `mutation (0)` took 6:40 (10:27:43–10:34:23); the mutation step itself took 5:41, and the job took 15:14. The cause is unknown, so this observation is not attributed to dependency caching and is not added to either comparison cohort. R9.3 should investigate this checkout delay before treating it as a stable stage cost.

  The scheduler-fairness failure recorded under the R9.2 cohort was investigated in R9.3c below. The test now runs against durable queue claims and the production outbox materializer; no production supervisor or checkout behavior changed. The Git checkout delay remains unexplained and open for R9.3.

- **R9.3a — Profile and optimize the two slowest tests (2026-10-12):** The focused fixture optimization is complete; the broader R9.3 and R9.4 phases remain open. The changed test keeps its real source-preparation, durable checkpoint/resume, vector-store boundary, candidate/figure selection, strict crop, sidecar/hash, and queue-handoff assertions. It now uses the existing 540,430-byte, 15-page Capgemini fixture (8 unique embedded-image xrefs) in `test_source_ingest_checkpoint_hands_off_to_report_selection`; the test still exercises both source-ingest and report-selection handlers. The separate production-queue canary `test_first_attempt_canary_uses_production_submission_and_supervisor_path` still processes the 2,168,193-byte, 33-page IAS PDF (36 unique embedded-image xrefs). Selection assertions now require a nonempty candidate set, gallery, accepted publication-strict crop with a SHA-256, image and QA sidecar files, and matching image bytes.

  Temporary monotonic stage markers, removed after profiling, isolated the Test B source-ingest handler's PDF preparation/checkpoints and the report-selection handler's vector indexing/candidate extraction/ranking/cropping/selection checkpoint. On the same local runner, changing only the PDF fixture yielded:

  | Test B stage | IAS fixture | Capgemini fixture | Change |
  | --- | ---: | ---: | ---: |
  | Source-ingest handler: PDF preparation | 0.441 s | 0.530 s | +0.089 s |
  | Source checkpoint write | 0.110 s | 0.049 s | -0.061 s |
  | Validated checkpoint read | 0.057 s | 0.027 s | -0.030 s |
  | Checkpoint restore | 0.0001 s | 0.0001 s | no material change |
  | Vector indexing | 0.103 s | 0.102 s | no material change |
  | Candidate extraction | 8.238 s | 2.308 s | -5.930 s (-72.0%) |
  | Candidate ranking | 0.0001 s | 0.0001 s | no material change |
  | Fallback crop generation | 11.128 s | 9.745 s | -1.383 s (-12.4%) |
  | Report-selection handler total | 19.392 s | 12.075 s | -7.317 s (-37.7%) |
  | Selection checkpoint write | 0.070 s | 0.036 s | -0.034 s |

  The directly measured bottleneck was PDF candidate extraction, followed by fallback crop generation; source preparation and vector indexing did not improve. Four isolated post-change Test B executions were 14.23, 13.64, 13.65, and 14.02 seconds (median 13.835 s). A single pre-change paired local run recorded 20.51 seconds for Test B, so that end-to-end pair is supporting evidence only; it is not a repeated matched baseline. The focused stage comparison supports the 7.317-second selection-phase reduction without attributing unrelated phases to the smaller PDF.

  Test A was profiled separately and left unchanged. One local monotonic trace measured isolation at 0.184 s, admission at 0.440 s, source freeze at 0.018 s, durable queue submission at 0.107 s, supervisor drain at 36.683 s, terminal-state verification at 0.026 s, and total test time at 37.844 s. Persisted report-stage timings were source ingest 1.344 s, report selection 19.922 s, report analysis 7.687 s, report rendering 2.313 s, analytics projection 2.109 s, and each remaining stage no more than 0.609 s. Report selection is the largest locally observed production stage. The test's `max_duration_seconds=60` is not an end-to-end wall timeout: `_run_preselected_canary` performs isolation, settings/source setup and durable submission before starting `_drain_report_path`, then reads terminal state and writes its result afterward. Within the drain, `_drain_report_paths` checks the deadline before each synchronous `run_supervisor_once` dispatch and cannot preempt a dispatch already in progress. Thus the value bounds when another supervisor pass may start, not total test duration. Hosted per-test times vary widely below; no hard-deadline correctness defect was established and production deadline behavior was not changed.

  **Full-CI comparison.** Both cohorts used Ubuntu `ubuntu-latest`, CPython 3.12, the same R9.2 four-job/two-mutation-partition topology, and eight-worker pytest with `--dist=worksteal`. Wall time is from first job start to release-evidence completion; active runner time sums `ci_start`, tests, both mutation jobs, and release-evidence job durations. Per-test telemetry durations are concurrent-worker test call times and are not additive CI wall time.

  | Cohort / exact SHA | Attempt | Workflow wall | Tests job / pytest telemetry | Test A / Test B | Mutation jobs 0 / 1 | Release job | Active runner-min |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
  | Baseline `03e7f26370c835b0f3fd22793d051a2c9e9e9254` | [1](https://github.com/mbrakker/marketlense/actions/runs/38247162732/attempts/1) | 13:38 | 10:00 / 5:59 | 2:30 / 1:15 | 8:28 / 6:45 | 3:27 | 28.73 |
  | Baseline `03e7f26370c835b0f3fd22793d051a2c9e9e9254` | [2](https://github.com/mbrakker/marketlense/actions/runs/38247162732/attempts/2) | 16:40 | 13:22 / 8:17 | 4:09 / 2:28 | 8:33 / 8:40 | 3:07 | 33.77 |
  | Baseline `03e7f26370c835b0f3fd22793d051a2c9e9e9254` | [4](https://github.com/mbrakker/marketlense/actions/runs/38247162732/attempts/4) | 15:03 | 11:42 / 8:08 | 3:57 / 2:14 | 8:56 / 8:53 | 3:11 | 32.77 |
  | Candidate `e968a3f0e96e7278020f66557feb9004d97c300f` | [1](https://github.com/mbrakker/marketlense/actions/runs/38264311659/attempts/1) | 17:20 | 13:59 / 9:46 | 4:50 / 2:45 | 8:23 / 8:49 | 3:11 | 34.45 |
  | Candidate `e968a3f0e96e7278020f66557feb9004d97c300f` | [2](https://github.com/mbrakker/marketlense/actions/runs/38264311659/attempts/2) | 12:41 | 7:51 / 4:31 | 1:56 / 1:03 | 8:59 / 7:50 | 3:25 | 28.23 |
  | Candidate `e968a3f0e96e7278020f66557feb9004d97c300f` | [3](https://github.com/mbrakker/marketlense/actions/runs/38264311659/attempts/3) | 15:08 | 11:40 / 8:01 | 3:59 / 2:12 | 8:27 / 6:52 | 3:19 | 30.35 |

  The three successful baseline attempts have a 15:03 wall median and 32.77 active runner-minutes median; the three successful candidate attempts have a 15:08 wall median and 30.35 active runner-minutes median. The observed wall difference is five seconds slower after the change and is not a demonstrated CI speedup. The active-runner difference is -2.42 minutes/run, but this cross-SHA six-run sample has substantial job variance and does not establish a cost reduction. GitHub reported zero billable milliseconds for these public-repository jobs. Median test-job time was 11:42 baseline versus 11:40 candidate; median pytest telemetry was 8:08 versus 8:01. Median Test A was 3:57 versus 3:59, and Test B was 2:14 versus 2:12. The per-test hosted medians therefore do not independently demonstrate the local fixture savings. In the baseline cohort the tests job was the longest parallel job on all three green attempts; in the candidate cohort, tests were longest on attempts 1 and 3, while mutation partition 0 was longest on attempt 2. Release assembly then added 3:07–3:27. These jobs, rather than either individual test alone, define the measured end-to-end critical path.

  Every successful attempt reported 7,473 pytest reports / 7,447 unique node IDs, with no failed tests; the final candidate node-ID set exactly equals the baseline set. Baseline coverage was 84,678–84,681 of 98,151 valid lines (86.27–86.28%); candidate coverage was 84,758–84,760 of 98,151 lines (86.35–86.36%). All six green attempts retained 17 mutation targets / 68 mutants / 67 killed, with each configured per-target floor passing. Each of the three final candidate bundles contained 17 files, bound its manifest, telemetry, and mutation result to the exact candidate SHA and attempt, passed 11/11 required release-evidence entries, matched all 11 downloaded artifact hashes, and had zero review issues.

  One baseline same-SHA attempt ([attempt 3](https://github.com/mbrakker/marketlense/actions/runs/38247162732/attempts/3)) passed tests, coverage, mutation, and static gates but failed release review because the existing PDF candidate benchmark warned that one median rose from 1.150 s to 1.455 s (+26.5%). Its 17-file bundle was not approved and is excluded from the green timing cohort. Re-running the same benchmark command locally produced 1.202 s for that PDF (+4.5%, no warning); the rerun did not modify the repository or baseline. This is observed gate variability, not a source change or proven root cause. The baseline had 3 successful full-CI attempts in 4; the final candidate SHA passed 3/3. An earlier implementation SHA `2806016687a1a922b3eaa4210d255e6d8419a0ef` exposed an xdist SQLite collision in an unrelated browser-download test: a helper inherited the shared default usage-ledger DB despite using `tmp_path` for other state. The test now sets its usage DB under `tmp_path`; the affected module passed all four tests under eight workers. This fixture-isolation correction is included in final SHA `e968a3f0e96e7278020f66557feb9004d97c300f`; no production migration or test selection changed.

  Focused verification commands: `py -3.12 -m pytest -q --durations=2 tests/test_frozen_reliability_cohort_runner.py::test_first_attempt_canary_uses_production_submission_and_supervisor_path tests/test_workflow_queue_registry.py::test_source_ingest_checkpoint_hands_off_to_report_selection` — 2 passed in 76.60 s (fresh run: 40.89 s / 18.56 s); `py -3.12 -m pytest -q --durations=2 tests/test_workflow_queue_registry.py::test_source_ingest_checkpoint_hands_off_to_report_selection` — four isolated passes (14.23, 13.64, 13.65, and 14.02 s); `py -3.12 -m pytest -q -n 8 --dist=worksteal tests/test_browser_report_download_doc_type_predictor.py` — 4 passed; `py -3.12 -m pytest -q tests/test_backlog_organization.py tests/test_backlog_source_gate.py` — 15 passed; Ruff check, Ruff format check and `git diff --check` passed. To inspect the baseline PDF-gate variance, the local command was `$outputRoot = Join-Path $env:TEMP 'marketlense-r93a-pdf-candidate-benchmark-attempt3'; py -3.12 scripts/ci/check_pdf_candidate_benchmark.py --baseline docs/quality/pdf_candidate_extraction_benchmark_baseline.json --output-root (Join-Path $outputRoot 'artifacts') --output-json (Join-Path $outputRoot 'pdf_candidate_benchmark_ci.json')`. Three complete full-CI attempts passed on candidate SHA `e968a3f0e96e7278020f66557feb9004d97c300f`. Test selection, coverage threshold, mutation partitions and floors, quality gates, and release-evidence checks were not changed. No timing framework or permanent instrumentation was added.

  **Result and next slice:** Keep the smaller Capgemini fixture for Test B; it reduced the measured selection handler by 37.7% without dropping integration assertions. R9.3a alone did not demonstrate a full-CI speedup: its wall median was effectively unchanged and stage variance masked the isolated saving. The separate worker-count result is recorded below. R9.3 remains open for the residual Test A long tail and unexplained Git checkout delay; R9.4 still owns accurate elapsed critical-path telemetry. The supervisor-fairness fixture correction is recorded in R9.3c.

  **R9.3b — Hosted pytest worker count (2026-10-12):** Compared the existing `-n 8 --dist=worksteal` configuration with `-n 4 --dist=worksteal`. The control cohort is the three green attempts on exact SHA `e968a3f0e96e7278020f66557feb9004d97c300f` in the R9.3a table above; the candidate is three green attempts on exact SHA `07084b52e2c3e88c289cc6c8fc00ba6ac22e823a`. All runs used Ubuntu `ubuntu-latest`, CPython 3.12, the same hash-locked dependencies, four-job/two-mutation-partition CI topology and complete quality/release gates. The candidate changed pytest's worker count and its wiring assertion. Its experiment SHA also included a temporary resource sampler; that measurement-only sampler was removed before final integration. Because the control cohort did not run the sampler, its small overhead was not isolated; candidate timings include it and therefore may be conservative.

  | Four-worker candidate attempt | Workflow wall | Tests job / pytest | Test A / Test B | Mutation jobs 0 / 1 | Release job | Active runner-min |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: |
  | [1](https://github.com/mbrakker/marketlense/actions/runs/38285673784/attempts/1) | 13:52 | 10:27 / 6:52 | 1:50 / 1:13 | 6:39 / 9:02 | 3:15 | 29.45 |
  | [2](https://github.com/mbrakker/marketlense/actions/runs/38285673784/attempts/2) | 14:33 | 10:53 / 7:32 | 2:03 / 1:22 | 8:12 / 8:13 | 3:31 | 30.87 |
  | [3](https://github.com/mbrakker/marketlense/actions/runs/38285673784/attempts/3) | 13:19 | 7:17 / 4:04 | 1:00 / 0:38 | 6:03 / 9:49 | 3:20 | 26.53 |
  | **Median** | **13:52** | **10:27 / 6:52** | **1:50 / 1:13** | **6:39 / 9:02** | **3:20** | **29.45** |

  Compared with the existing eight-worker cohort medians (15:08 workflow wall, 11:40 tests job, 8:01 pytest, 3:59 / 2:12 for Test A / Test B, 8:27 / 7:50 for mutation jobs, 3:19 release, and 30.35 active runner-minutes), four workers reduced median full-CI wall by 1:16 (8.4%), test-job wall by 1:13 (10.4%), and pytest by 1:09 (14.4%). Test A's median call time fell 54% and Test B's fell 45%; these concurrent test-call savings are not added together as serial CI time. Active runner usage fell 0.90 minutes per run (3.0%); GitHub reports zero billable milliseconds for this public repository, so there is no billed-dollar saving to claim. The median mutation-job split and release duration were 6:39 / 9:02 and 3:20 after the change; those jobs run independently of pytest, and their variance is not attributed to worker count. The existing locked-install step in the test job took 2:18, 2:05, and 2:20 across the three attempts and was not changed.

  The test job was the critical prerequisite in candidate attempts 1 and 2. In attempt 3, it completed in 7:17 while mutation partition 1 took 9:49, shifting the critical path to that mutation job before the unchanged 3:20 release assembly. The end-to-end median improvement is observed across the full runs, but its precise share from pytest versus runner variability is not identifiable from these three cross-SHA attempts. The candidate's full-wall range was 13:19–14:33 versus 12:41–17:20 for the eight-worker cohort; the ranges overlap and the cohorts use different SHAs.

  **Resource diagnosis:** A temporary same-format sampler recorded cgroup CPU statistics, Linux CPU/memory/I/O pressure, process/thread counts, and `/usr/bin/time -v` on the four-visible-CPU hosted runner. On the eight-worker diagnostic run ([run 38284060835](https://github.com/mbrakker/marketlense/actions/runs/38284060835), sampler SHA `895a001ad239be77976d40c5a6cff683eea1d098`), pytest used 374% average CPU but sampled CPU-pressure `some avg60` averaged 71.74 and `avg10` peaked at 95.8; memory pressure was negligible and cgroup CPU throttling was zero. That run failed on the already-known `source_progress_overtaken` supervisor-fairness assertion and is excluded from the successful timing cohort. With four workers, average CPU use remained 332–358%, while the three sampled `some avg60` means were 18.87, 18.80, and 11.87, with `avg10` maxima 47.05, 42.52, and 33.97; memory pressure and cgroup CPU throttling remained negligible. Samples showed four pytest worker processes each using about one CPU; sampled Python workers had 2–8 threads each, with no evidence of a large native-thread pool. This supports xdist worker oversubscription and CPU run-queue contention on a four-CPU runner as the main hosted pytest cause; it does not show CPU-quota throttling or memory pressure.

  As a limited worker-occupancy proxy, summed test-call time divided by configured worker slots × pytest wall was 61.7% in the recovered eight-worker baseline trace and 73.3–75.0% across the three four-worker attempts. This excludes setup and collection and is not per-worker assignment or utilization data; existing telemetry does not identify each node's worker, so individual worker imbalance remains unmeasured. The prior and new supervisor-fairness failures also mean the three green runs per configuration do not prove a reliability-rate improvement: the eight-worker baseline was 3/3 green, the four-worker candidate was 3/3 green, and the additional instrumented eight-worker diagnostic failed. No assertion, node selection, coverage threshold, mutation target, or quality/release gate changed.

  All candidate attempts reported 7,473 test records / 7,447 unique node IDs, zero failed tests, coverage 84,760 / 98,151 lines (86.36%), and 17 mutation targets / 68 mutants / 67 killed. Candidate node-ID/outcome multisets matched the recovered baseline telemetry exactly. Each candidate release bundle was tied to its exact SHA and attempt and passed 11/11 required evidence checks; the final attempt's 17-file bundle had zero review issues and every manifest artifact's SHA-256 and byte count matched the downloaded file. Focused verification on the candidate was `py -3.12 -m pytest -q tests/test_mutation_ci.py::test_mutation_ci_workflow_overlaps_tests_with_two_isolated_workers tests/test_ci_quality_gate_wiring.py` (4 passed), and `py -3.12 -m pytest -q -n 4 --dist=worksteal tests/test_frozen_reliability_cohort_runner.py::test_first_attempt_canary_uses_production_submission_and_supervisor_path tests/test_workflow_queue_registry.py::test_source_ingest_checkpoint_hands_off_to_report_selection` (2 passed in 61.35 s). The final main-branch run validates the retained workflow after removing the temporary sampler; its URL is reported separately.

  **Decision:** Retain `-n 4 --dist=worksteal`. It produced a repeatable median full-workflow and pytest improvement without a material active-runner increase, while preserving exact test telemetry and all evidence gates. Do not add sharding or another scheduler profile in this slice. The supervisor-fairness test-fixture mismatch is recorded below; next, investigate the residual Test A long tail and the unexplained Git checkout delay, then let R9.4's critical-path measurements guide any further performance change.

  **R9.3c — Supervisor fairness regression fidelity (2026-10-12):** The same failure, `assert not source_progress_overtaken.is_set()`, occurred on SHA `1d78865d0c4b3c9e43a5a03dc4dfe267a78d62d4` in [run 38213012092 attempt 3](https://github.com/mbrakker/marketlense/actions/runs/38213012092/attempts/3) and sampler SHA `895a001ad239be77976d40c5a6cff683eea1d098` in [run 38284060835](https://github.com/mbrakker/marketlense/actions/runs/38284060835). Both logs showed the third report-analysis callback start before the fifth source-ingest callback; run 38213012092 attempt 4 passed on the same SHA. On the pre-change synthetic fixture, local tracing reproduced the same ordering. That fixture modeled worker starts, queue capacity, child submissions and outbox materialization with independent counters and did not execute durable job claims or the real outbox lifecycle. The event therefore measured an ordering in the fake state machine; repeated current-code executions through real queue claims did not reproduce starvation. The actual production scheduler and its documented round-robin/downstream preference were not changed.

  The production contract requires bounded round-robin progress across eligible queues while respecting global and per-queue limits; it does not promise a wall-clock deadline. A test-local trace of the real queue path showed source jobs 1–3 start and complete, selection job 1 starts, then source jobs 4 and 5 start before analysis job 3. In the old fake, by contrast, the callback counter could advance independently of durable claims, leases, downstream payloads and capacity state. Supplying the real child-queue hints to that fake did not remove its intermittent ordering.

  Replaced the simulation with five durable source-ingest jobs, `run_workflow_worker_once`, the production outbox materializer, and source-ingest → report-selection → report-analysis submissions. The test waits until three source handlers have claimed work, releases them with an `Event`, and preserves the source-before-deep-stage assertion against actual job starts. Queue controls and supervisor limits remain three. It also asserts all 15 jobs succeed once, the five source IDs are exactly the ones processed, lineage links connect each stage, each job has one attempt, source enqueue replay is idempotent, and active worker calls remain within the three-per-queue cap. No production scheduler code, queue limits, CI topology, test selection, coverage, mutation target or release gate changed.

  **Verification and measured impact:** The real-queue regression passed 20 direct repetitions, three focused `py -3.12 -m pytest -q -n 4 --dist=worksteal tests/test_workflow_supervisor_parallelism.py::test_source_ingest_backlog_progresses_before_deeper_report_stages` runs, and the 117-test supervisor/queue suite. Ruff, format and backlog ownership checks passed. A broad local-suite attempt exposed four unrelated PDF image-test errors under local Pillow 12.0.0 versus locked Pillow 12.3.0; two unrelated browser cases passed on rerun. This is not treated as a product or hosted-CI result.

  The first post-change full CI passed on exact SHA `e152fb57880579688d8627fb50dcc46baabf4831` in [run 38299415181 attempt 1](https://github.com/mbrakker/marketlense/actions/runs/38299415181/attempts/1): 13:57 workflow wall, 10:18 tests job, 6:54.64 pytest telemetry, and 30.58 active runner-minutes. Its release job took 3:25; pytest was the critical prerequisite, followed by release assembly. The accepted R9.3b four-worker cohort on SHA `07084b52e2c3e88c289cc6c8fc00ba6ac22e823a` measured 13:52 median workflow wall, 6:52 median pytest, and 29.45 median active runner-minutes across three green attempts. This single post-change run is +5 seconds wall, +2.64 seconds pytest and +1.13 runner-minutes from that different-SHA median; it does not demonstrate a speedup or a material cost regression. The run reported 7,447 unique node IDs (7,473 passing reports), 84,760/98,151 covered lines (86.36%), and 17 mutation targets / 68 mutants / 67 killed. The hash-locked install steps took 2:09 in tests, 2:06 in mutation partition 0, 2:02 in partition 1, and 2:18 in release assembly. All four jobs completed without dependency errors.

  The exact-SHA `38299415181-1` release bundle contained 17 files. Its manifest bound all 11 required entries to SHA `e152fb57…` and passed; review reported 11/11 required checks, zero issues and zero waivers. I downloaded the bundle and independently verified that each of the 11 manifest paths existed and matched its recorded SHA-256 and byte count.

  **Three-run hosted comparison on implementation SHA `ebd3bed3739e981594e6338bda675b338d80f069`:** The same Ubuntu `ubuntu-latest`, CPython 3.12, `-n 4 --dist=worksteal`, locked dependencies, two mutation partitions, test selection and release gates passed on all three attempts. Each attempt reported 7,447 unique passing node IDs, 84,760/98,151 covered lines (86.36%), 17 mutation targets / 68 mutants / 67 killed with all target floors passing, and a 17-file release bundle. Each exact-SHA manifest passed 11/11 required checks with zero issues/waivers; downloaded files matched all recorded hashes and byte counts.

  | Attempt | Workflow wall | Tests job / pytest telemetry | Mutation jobs 0 / 1 | Release job | Active runner-min | Install: tests / mut. 0 / mut. 1 / release |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: |
  | [1](https://github.com/mbrakker/marketlense/actions/runs/38301470970/attempts/1) | 13:08 | 7:14 / 4:02 | 5:37 / 9:04 | 3:49 | 25.78 | 2:13 / 2:05 / 2:38 / 2:43 |
  | [2](https://github.com/mbrakker/marketlense/actions/runs/38301470970/attempts/2) | 15:23 | 11:31 / 7:32 | 8:13 / 6:54 | 3:37 | 30.32 | 2:43 / 2:10 / 2:15 / 2:33 |
  | [3](https://github.com/mbrakker/marketlense/actions/runs/38301470970/attempts/3) | 13:06 | 9:16 / 5:38 | 8:13 / 8:57 | 3:38 | 30.10 | 2:24 / 2:10 / 2:13 / 2:38 |
  | **Median** | **13:08** | **9:16 / 5:38** | **8:13 / 8:57** | **3:38** | **30.10** | **2:24 / 2:10 / 2:15 / 2:38** |

  Relative to the accepted R9.3b four-worker cohort on a different SHA (`07084b52e2c3e88c289cc6c8fc00ba6ac22e823a`), the observed medians were 13:52 wall, 6:52 pytest and 29.45 active runner-minutes. This cohort's wall median is 44 seconds lower and pytest median 74 seconds lower, while active runner time is 0.65 minutes higher. The wall ranges overlap (13:06–15:23 versus 13:19–14:33), and one candidate attempt was 15:23. These are cross-SHA observations with substantial runner/test variance; the test-fixture correction is not credited with a speedup. The critical prerequisite was mutation partition 1 on attempt 1 and the test job on attempts 2 and 3; release assembly then took 3:37–3:49. Across the three runs, the fairness regression itself took 0.66, 2.39 and 1.13 seconds (median 1.13). Test A took 57.90–116.16 seconds and Test B 38.31–81.45 seconds; those concurrent per-test calls vary and are not added as serial CI time. Median locked-install time for the test job was 2:24, six seconds above the R9.3b cohort's 2:18 median; no dependency installation failed. GitHub billed $0 for these public-repository runs. The 3/3 pass result is observed repeatability, not a statistical claim of zero future failures. The Git checkout outlier remains an open R9.3 investigation; R9.4 still owns accurate critical-path telemetry.

- **Desired outcome:** At least **5× shorter median elapsed full-CI time** than the measured comparable baseline (15:48, implying about 3:10), plus prompt reliable PR failure feedback, without reducing required gate scope, editorial/grounding safeguards, test coverage, mutation assurance or release-evidence completeness. This remains a **stretch goal**, not a forecast.

**Implementation stages (one verified stage per implementation slice):**

1. **R9.1 — Baseline and setup (complete; evidence above):** Record at least three comparable successful full workflows before changing topology: source SHA, runner/runtime, trigger, elapsed/step timing, eligible pytest node IDs, coverage, mutation target scores, artifact completeness, and total billed runner-minutes. Profile cold/warm installation and compare cache behavior on the current topology; retain the simpler no-pip-cache setup based on the measured 25-second median reduction along the serial test/release setup path. Keep deterministic hash-locked installation. Investigate the heavy torch/CUDA dependency graph before attempting removal; keep the verified locked environment. Avoid redundant superseded-work execution only where the applicable required event and SHA release gates remain satisfied.
2. **R9.2 — Parallelize mutation and independent gates (complete; evidence above):** Run full pytest/coverage and existing quality gates concurrently with two isolated mutation partitions; release evidence waits on both and merges exact-SHA results. The merger rejects absent, duplicate, failed, mismatched-SHA or mismatched-run partitions and retains the existing `mutation_results.json` schema and score floors. Three successful exact-SHA runs measured a 13:51 median versus 23:56 immediately before parallelization, with one scheduler-fairness test failure in a fourth attempt; no gates were weakened.
  3. **R9.3 — Profile and optimize pytest (active; R9.3a fixture, R9.3b worker-count, and R9.3c fairness-test-fidelity slices verified, evidence above):** Retained per-test telemetry and the hosted resource experiment identified oversubscribed xdist workers as the main pytest pressure; the measured candidate uses `-n 4 --dist=worksteal`. Keep the complete suite and exact node-ID union, consistent outcomes, coverage, and release evidence. Do not shard unless simpler changes later prove insufficient. The fairness assertion now uses the durable queue/outbox lifecycle and retains its source-before-deep-stage condition; the local broad-suite Pillow mismatch is recorded in R9.3c. Investigate the unexplained 6:40 checkout step (runs 38213012092 attempt 3 and 38236442840), then re-profile Test A and the mutation-partition critical path before proposing another optimization. R9.3 remains open.
4. **R9.4 — Reassemble release evidence and measure actual speed:** Use established GitHub artifact and `needs` dependency mechanisms for exact-SHA stage outputs and final checks. Preserve release manifest, summary, review, upload/completeness checks, freshness/start-time semantics, coverage, mutation, PDF, prompt, public-report quality and conditional WordPress staging checks. A missing, failed, stale or mixed-commit input must never produce an approved release bundle. Update CI performance telemetry to report actual elapsed wall-clock/critical path rather than summing parallel stages. Risk-classified PR feedback can be fast, but only a genuinely complete required-gate run is full-release green.

- **Acceptance / verification:**
  - Compare at least **three comparable successful runs per version**, recording median full-workflow wall-clock, fastest PR failure feedback, individual stage timing, GitHub billed runner-minutes, and flake/failure rates; report achieved speedup and gap to ≥5× without cherry-picking.
  - Full-suite pytest collected/executed node IDs have no omissions/duplicates; results and aggregate coverage meet all existing gates. Mutation reports contain **all configured targets exactly once**, original selection/max-mutant and per-target/global minimum score requirements, and identical pass/fail/non-regression semantics.
  - Injected test failures, mutation failures, missing/duplicate target results, missing release artifacts and wrong-SHA/stale evidence all fail closed, including multi-job or partial-completion paths.
  - Exact-commit release manifest/review, upload bundle and summary remain complete and trustworthy; static, WordPress, public-report and LLM/prompt/PDF quality protections do not silently disappear from full release validation.
  - Use existing CI tooling, telemetry, contracts and tests; do not build a generic scheduler, an elaborate change-based test-selection framework, new infrastructure or speculative optimizations solely to chase fivefold speed.

### Luna implementation prompt — R9

~~~text
Work on the next unverified R9 CI acceleration stage at current HEAD.
Start with .github/workflows/ci.yml, scripts/ci/run_mutation_gate.py, existing
pytest/quality telemetry, release-evidence builders/contracts and recent green run logs.
Implement one measured, coherent improvement using existing mechanisms. Preserve every
applicable test, mutant, threshold, coverage/quality gate and exact-SHA release artifact.
Prove correct aggregation and fail-closed behavior across parallel jobs. Compare
comparable green workflows for elapsed wall-clock and billed runner-minutes; distinguish
measured gains from the 5x stretch goal. Update the R9 canonical status/evidence only
when verified. Run focused checks, record gaps, then commit and push the scoped change.
~~~

---

<a id="d13-openai-responses-migration"></a>
## Deferred initiative D13 — Evaluate direct OpenAI Responses migration

**Canonical status:** Deferred; P2, not an autonomous-MVP blocker. **Added:** 2026-10-11. **Status authority:** [D13 in the unified register](../../CONSOLIDATED_TODO.md). This is a new scoped initiative, **not** one of the 109 historical catalogue proposals, and does not alter A15's existing model-policy completion criteria.

- **Observed implementation baseline (not measured performance):** `src/services/_llm_service/openai_chat.py` sends `openai_chat_json` and `analyze_report` through `chat.completions.create`, with an older compatibility fallback. The image+JSON method in that file and `openai_ocr_pdf` / `openai_respond_with_vector_store` in `openai_responses.py` already use `responses.create`. `src/services/_llm_service/openrouter.py` uses a Chat Completions-compatible OpenRouter route. Shared policy, adapters, caching and usage accounting already exist. There is **no retained MarketLense A/B evidence** in this task establishing a quality, latency or cost improvement from changing the endpoint.
- **Objective:** Determine whether using Responses for **direct OpenAI text/JSON generation** improves editorial quality, reasoning reliability, latency or total cost enough to justify replacing its Chat Completions path. Retain the present route if the benefits are not demonstrated. Do not change file search, OCR, image routes or OpenRouter merely for endpoint uniformity.
- **Execution order / tasks:**
  1. **Compatibility inventory:** Reinspect all direct OpenAI text/JSON call sites, policy resolution and legacy `TypeError` fallback at current HEAD; verify current official API/SDK/model support. Map Chat/Responses request and response fields (system instructions, messages, strict JSON schema versus JSON-object mode, reasoning effort, supported sampling settings, max-token limits, completion status and refusals).
  2. **Small reversible A/B switch:** Route `openai_chat_json` and `analyze_report` through a selectable Responses transport at the existing LLM service boundary, defaulting to the current Chat Completions behavior during the experiment. Reuse canonical model policy, contracts, error classification, bounded orchestrator retries, audit and usage accounting; do not create a parallel LLM service or an automatic per-call retry across endpoints.
  3. **Parity and isolation:** Verify schema parsing/validation, provenance/evidence, cache-key separation and legitimate cache reuse, prompt hashes, reasoning/output token reporting, cached-token and any cache-write cost attribution, request IDs, redacted audit fields, provider timing, rate limits/budgets, timeout and failure handling. Preserve OpenRouter's Chat Completions-compatible fallback; keep existing Responses-based vector search/OCR/images unchanged.
  4. **Frozen comparison:** Run both transports on the **same previously frozen five-report cohort**, including its known difficult/failed cases and unchanged source-file identities. Keep models, reasoning efforts, prompts, schemas, tool use, validation policy and publish-disabled environment equivalent. Use enough repeat runs to distinguish endpoint effects from LLM variance. Inspect real generated artifacts, not only JSON/schema success, and compare factual fidelity, grounding, analytical depth, report specificity, first-pass validation, retry/regeneration and quarantine rates, total report wall-clock time/critical path, calls, input/output/reasoning/cached tokens, cache hits/writes, tool charges and total cost. Report incompatible/unknown measurements explicitly.
  5. **Decision and rollout:** Produce an exact-SHA, cohort-linked baseline/candidate evidence summary with qualitative editorial review. Promote Responses only if factual/editorial quality and operational reliability are non-regressing, and wall-clock/cost outcomes provide a defensible overall benefit (or a clearly justified quality benefit at acceptable cost). Otherwise record **no change**. Roll out behind the existing policy/configuration boundary, with rollback, only after the decision.
  6. **Conditional cleanup:** Only after proven promotion and verification of live callers, remove obsolete Chat Completions-specific compatibility code that has become unreachable. Do not remove the OpenRouter-compatible transport or introduce speculative abstractions.
  7. **Separate optional optimization:** If retained call traces show substantial repeated context/reasoning across related steps, *independently* benchmark Responses reasoning-state reuse or improved prompt-cache reuse. Prove source/report isolation, cache identity, grounding, failure recovery, quality, time and full cost before adopting. Do not chain independent report tasks, add hidden state or force stateful reasoning merely because Responses supports it.
- **Acceptance criteria / verification:**
  - Transport selection changes only the intended direct OpenAI text/JSON calls; default route and unrelated OpenRouter, file-search, OCR, image and embedding behavior remain unchanged.
  - Representative faked boundary tests cover both endpoint payloads, strict/loose JSON, valid/invalid responses, unsupported parameters, refusal/incomplete output, accounting, cache isolation, retry/error ownership and explicit rollback.
  - Five-report paired results include actual reviewed output and full-cost/speed/validation accounting, with prior failures and stochastic variance documented; no publication writes.
  - The decision is evidence-based: no automatic promotion, no invented percentage improvement, no lower factual/grounding or editorial standard to achieve savings. Negative results explicitly close the investigation with no migration.
  - Optional reasoning-context reuse has a **separate** quality/cost/latency decision; it is not required for the endpoint parity experiment.

### Luna implementation prompt — D13

```text
Investigate D13 — Evaluate direct OpenAI Responses migration at current MarketLense HEAD.
Source: CONSOLIDATED_TODO.md and docs/backlog/R-engineering.md (deferred D13).
First verify current actual code/API support; do not assume switching endpoints improves results.
Implement only the smallest reversible OpenAI text/JSON transport A/B seam, preserving
existing public contracts, policies, OpenRouter fallback, schemas, caching and accounting.
Benchmark the same frozen five-report cohort (including prior failure cases) on both
transports with equivalent inputs/configuration and publication disabled. Review actual
artifacts, factual fidelity, editorial quality, full latency/cost/cache and failure rates.
Keep Chat Completions unless the evidence supports migration; treat context/reasoning reuse
as a separate optional experiment, not part of initial parity.
Run relevant boundary/frozen-cohort checks, document exact commands, SHA, outputs,
uncertainties, acceptance decision and rollback. Update the canonical backlog with
verified status and evidence; commit and push only the scoped changes.
```

---


<a id="d14-subscription-debug-inference-adapter"></a>
## Deferred initiative D14 — Evaluate ChatGPT-plan debugging inference adapter

**Canonical status:** Deferred; P2, debugging-only; not an autonomous-MVP blocker. **Added:** 2026-10-11. **Status authority:** [D14 in the unified register](../../CONSOLIDATED_TODO.md). Separate from D13's evaluation of API-billed Chat Completions versus Responses. This is a proposal, not an implemented capability or evidence of savings.

- **Inspected baseline:** `src/services/_llm_service/client.py` defines shared provider operations; `openai_chat.py` sends ordinary JSON through Chat Completions and image+JSON through Responses; `openai_responses.py` owns OCR and hosted file search; embeddings and vector-store management have separate OpenAI API operations. `openai_shared.py` semantic-cache identity has no billing/backend discriminator. Reverify behavior at implementation HEAD.
- **Eligibility restriction:** Official [Sign in with ChatGPT plan usage](https://developers.openai.com/siwc/token-sharing-open-source) currently covers eligible open-source and locally hosted clients. Paid or remotely hosted deployment requires separate approval. Model, reasoning controls, regional/account permissions and quotas must be confirmed with the selected account, not inferred from MarketLense's API configuration. Preview [Responses limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations) require `store=false` and `stream=true`, exclude `temperature`, `max_output_tokens`, hosted `file_search`, Files uploads and several other tools; embeddings and vector-store lifecycle remain API-only.
- **Objective:** Add, only if feasible, an explicitly opted-in **local debugging** inference backend using official subscription-authorized Responses. Convert supported calls and normalize results at the *existing* LLM service boundary, without rewriting generators, creating a generic HTTP proxy, touching production defaults, or falsely claiming full API compatibility. Never use unofficial ChatGPT endpoints or scrape client credentials.

**Implementation slices (one deferred initiative; not separate active outcomes):**

1. **D14.1 — Feasibility gate.** Verify current official policy, open-source/local eligibility, PKCE OAuth consent/scopes, model catalogue and exact debugging requirements. Probe one permitted text/strict-JSON call on a selected account with bounded usage and inspect stream events. If unauthorized, or acceptable same-model/same-effort support is absent, report the limitation and stop; an explicitly different debug model must be labelled non-parity.
2. **D14.2 — Shared transport selector.** Default to the unchanged API; add opt-in `chatgpt_plan_debug` at `LLMServiceClient`/provider-operations boundary. Translate supported Chat Completions text/JSON requests to Responses and preserve current typed `OpenAIResponseResult`, model policy, schema validation, errors, service timing, orchestrator-owned retries and audit. Only extend to images/PDF inference after explicit capability verification. Do not monkeypatch the SDK, fork the pipeline or silently implement D13's API endpoint migration.
3. **D14.3 — OAuth and streaming compatibility.** Use official local OAuth with state, PKCE, nonce/ID-token/scope checks, stable issued client/host identifiers, secure local credential storage, serialized refresh and revocation handling. Map accepted instructions/input and JSON schema; set `store=false`/`stream=true`; treat only `response.completed` as success. Normalize text/parsed JSON, model, token usage, request ID and typed failure. Reject refusal, incomplete/interrupted/error streams and unsupported parameters without manufacturing output or token totals.
4. **D14.4 — Explicit hybrid and spend policy.** Hosted file search/grounding, vector-store operations, uploads and embeddings must **fail before provider I/O** unless the operator separately permits API-billed unsupported operations. Do not automatically fall back after subscription quota/eligibility errors or substitute models without consent. Separate semantic/replay caches by backend and actual model/config; distinguish real API spend, subscription usage and unknown costs in audit/budget reporting (unknown is not zero). Preserve existing API budget guardrails, evidence provenance and publication-disabled debug scope.
5. **D14.5 — Verification and decision.** Unit/contract tests with recorded responses cover request adaptation, strict/loose JSON, incomplete/refused streams, auth expiry/denial, unsupported operations, budget/fallback policy, cache isolation, failures and metadata. Run an explicitly opted-in bounded local live smoke, then a previously frozen difficult report; expand to the frozen five-report cohort only if useful and compatible. Inspect actual artifacts, schema/grounding and editorial quality, number of eligible versus API-billed calls, total spend and wall clock. Document exact SHA, limitations, rollback and a go/no-go decision. Retain API-only routing if benefit is insufficient.

**Acceptance criteria:**

- Default/production API, OpenRouter, hosted file-search provenance, embeddings/vector stores, validation, queue retry ownership and publication behavior are unchanged.
- One explicit switch controls supported debug inference. The existing downstream contracts receive accurately normalized, schema-valid responses with truthful model, usage and backend metadata.
- Unsupported operation, unavailable same-model access, denied/expired consent, quota error, or incomplete stream fails explicitly; no secret leakage or surprise paid API call.
- Backend-isolated caches and accounting, bounded local opt-in verification and a documented quality/cost comparison substantiate any claimed debugging savings. No automatic promotion to production.

### Luna implementation prompt — D14

```text
Evaluate deferred D14 at current MarketLense HEAD: optional local ChatGPT-plan debug inference.
Read canonical backlog and R-engineering D14; verify current official OpenAI eligibility,
OAuth/model catalogue and request constraints before implementing more than a bounded
local proof of concept. If feasible, route supported inference behind one opt-in debug
switch at the existing LLM service boundary. Keep API production/default, preserve typed
responses, schemas, evidence, auditing, retry/budget ownership and downstream behavior.
Use official PKCE/OAuth and streaming Responses only; normalize completed results.
For hosted file_search, embeddings, Files and vector-store work, require separate explicit
permission for billed API use or fail before calling. No silent model/fallback substitution,
cross-backend cache reuse, invented token totals, unofficial endpoints or publication.
Verify recorded boundary tests, opt-in local live smoke, then representative frozen report
output and eligible-call/API-spend comparison; state exact checks, gaps and go/no-go.
Update canonical status only with verified evidence; commit and push scoped changes.
```

---
