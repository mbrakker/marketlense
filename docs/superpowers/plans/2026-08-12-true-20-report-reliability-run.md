# True 20-Report Reliability Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute a fresh, isolated, immutable 20-report production run from configured discovery through authenticated WordPress readback and unchanged repeat publication, then independently audit and commit safe evidence.

**Architecture:** A generated application profile isolates all state, artifacts, budgets, and logs. The existing canonical discovery/acquisition, cohort, processing, readiness, WordPress, and evidence boundaries are used unchanged. A code correction is allowed only after retained run evidence proves a general implementation defect; it requires a focused regression test and a separate commit before a new validation-run attempt.

**Tech Stack:** Python 3.12, YAML application configuration, SQLite run state, configured Drive/browser/mailbox services, model provider, WordPress REST API, pytest, quality-gate scripts, and GitHub CLI.

## Global Constraints

- Use branch `agent/reliability-full-20260812`, the producer revision recorded before external work, and a fresh `reliability_full_20260812_<uuid>` namespace.
- Start from the configured publisher/source universe, not pre-existing Drive content; retain discovery and route-selection evidence.
- Acquire and admit exactly 20 reports, with no more than three from one publisher; freeze and re-read a schema-1.1 cohort manifest before processing.
- After freeze, never replace a member. A failure remains in the 20-member denominator and every member receives one typed terminal state.
- Do not use `--success-target`, unavailable-log bypasses, validation weakening, implicit source substitution, or non-sandbox publication.
- Check WordPress authentication, schema, and writability without a write before publication. Pause two minutes between each report publish. Publish the frozen subset that is actually ready only after preflight; do not count partial publication as a passed 20-report run.
- Retain only bounded metadata in committed evidence: no credentials, source text, prompts, model outputs, private URLs, or authorization headers.

---

### Task 1: Record producer and preflight evidence

**Files:**
- Create: `docs/CTO_evidence/reliability_full_20260812_<uuid>/runtime_provenance.json`
- Create: `docs/CTO_evidence/reliability_full_20260812_<uuid>/model_policy_preflight.json`
- Create: `docs/CTO_evidence/reliability_full_20260812_<uuid>/test_results.json`

**Interfaces:**
- Consumes: `git`, process-scoped `.env` credentials, canonical configuration/publish services, and focused tests.
- Produces: producer SHA, clean-worktree record, runtime inventory, credential-presence-only checks, configuration/policy hashes, canonical paths, log/evidence retention checks, and a non-mutating WordPress preflight.

- [ ] Run targeted cohort, admission, recovery, readiness, readback, and evidence tests; retain commands, status, and duration.
- [ ] Load `.env` only into the process environment and verify required credential names are non-empty without printing values.
- [ ] Record Python, PHP, browser/runtime, operating-system, Git, configuration hash, model-policy hash, canonical path, and log/evidence access evidence.
- [ ] Invoke the canonical WordPress preflight and stop any future write if installation/setup, authentication, target-schema, or writability checks fail.

### Task 2: Create and validate a fresh isolated profile

**Files:**
- Create: `src/config/app.reliability_full_20260812_<uuid>.yaml`
- Create: `docs/CTO_evidence/reliability_full_20260812_<uuid>/run_identity.json`

**Interfaces:**
- Consumes: `src/config/app.yaml`, current run UUID, and generated browser identity configuration.
- Produces: a `MARKET_LENSE_CONFIG_PROFILE` whose output, cache, databases, browser outputs, ledgers, and logs are all beneath the fresh namespace; at least a 20-PDF budget.

- [ ] Create the profile from existing reliability-profile conventions, changing only run-owned paths and bounded budgets.
- [ ] Validate YAML and resolve settings through the canonical configuration service.
- [ ] Assert all run-owned paths are new and lie beneath the new namespace before discovery starts.

### Task 3: Discover, acquire, admit, and freeze exactly 20 reports

**Files:**
- Create: `out/reliability_full_20260812_<uuid>/cohort_manifest.json`
- Create: `docs/CTO_evidence/reliability_full_20260812_<uuid>/acquisition_metrics.csv`
- Create: `docs/CTO_evidence/reliability_full_20260812_<uuid>/admission_metrics.csv`

**Interfaces:**
- Consumes: configured publisher inventory, canonical acquisition route selection, Drive archival, and immutable `ingest --cohort-size 20 --cohort-manifest` controls.
- Produces: a verified 20-member immutable cohort with source/publisher identities, checksums, route evidence, configuration/policy/build provenance, and no publisher represented more than three times.

- [ ] Run normal source-universe discovery and persist all candidate records before Drive persistence is used as workflow input.
- [ ] Acquire candidates using naturally applicable routes, retaining route family, attempts, retry/failure outcome, checksum, archive outcome, and duplicate disposition.
- [ ] Continue only until 20 deterministic admission decisions are eligible; retain each rejection and ensure `publisher_id` and `source_identity_id` are resolved for every admitted member.
- [ ] Freeze and re-read exactly 20 members; record cohort and derived validation-run IDs and reject any freeze that violates publisher diversity or identity constraints.

### Task 4: Process the frozen cohort and recover narrowly

**Files:**
- Create: `state/reliability_full_20260812_<uuid>/reports.sqlite`
- Create: `state/reliability_full_20260812_<uuid>/index.sqlite`
- Create: `out/reliability_full_20260812_<uuid>/validation-runs/<validation-run-id>/reliability_telemetry.json`

**Interfaces:**
- Consumes: frozen cohort manifest and canonical ingest/recovery/checkpoint boundaries.
- Produces: retained per-stage attempts, structured-output recovery evidence, grounding/regeneration lineage, category/figure/final-HTML results, readiness decisions, costs, and one current terminal state per report.

- [ ] Invoke ingest only with the frozen manifest and preserve all stage records and run-owned logs.
- [ ] For each failure, classify the typed error, choose the narrowest supported checkpoint, retain parent/child attempt evidence, and rerun only the affected downstream stages.
- [ ] If a general implementation defect is proven, preserve failed evidence, add a focused failing regression test, apply the smallest correction, rerun focused tests, commit it separately, and create a new validation-run attempt without modifying the cohort.
- [ ] Reject closure if any member is running, partial, unknown, or missing, or if outputs fail canonical readiness.

### Task 5: Publish, authenticated readback, and idempotent repeat

**Files:**
- Create: `docs/CTO_evidence/reliability_full_20260812_<uuid>/wordpress_transactions.csv`
- Create: `docs/CTO_evidence/reliability_full_20260812_<uuid>/wordpress_readback.csv`
- Create: `docs/CTO_evidence/reliability_full_20260812_<uuid>/repeat_publication.csv`

**Interfaces:**
- Consumes: canonical publish-readiness artifact, frozen manifest, verified sandbox WordPress boundary, and canonical publisher.
- Produces: write/match transaction proofs, authenticated full readback outcomes, and repeat-publication requested/actual write counts.

- [ ] Recheck the non-mutating WordPress preflight immediately before any publishing workflow.
- [ ] Publish only publish-ready frozen members through the canonical CLI/boundary, pacing report write attempts by at least two minutes.
- [ ] Verify post identity, type/status, content hash, canonical/OpenGraph URLs, rendered content, attribution, taxonomy, media, and report-card assets using authenticated readback.
- [ ] Repeat unchanged publication against the same frozen manifest and require zero requested writes, zero actual writes, and zero duplicate active posts.

### Task 6: Generate strict evidence, independently audit, validate, and commit

**Files:**
- Create: `docs/CTO_evidence/reliability_full_20260812_<uuid>/`
- Create: `docs/releases/2026-08-12-20-report-full-funnel-reliability.md`

**Interfaces:**
- Consumes: the cohort/validation manifests, isolated state and artifact directories, run-owned logs, cost ledgers, WordPress proofs, and exact producer/configuration/policy identities.
- Produces: all required CTO evidence views, a read-only audit verdict, safe release record, test and GitHub-status evidence, and an intentional evidence commit.

- [ ] Run the strict collector without `--allow-unavailable-run-logs`; run the scoped reliability exporter and validate all required artifact names, terminal accounting, and reconciled cost/funnel metrics.
- [ ] Run a separate read-only audit that derives findings from retained databases, artifacts, logs, transaction/readback records, and manifests—not the narrative release record.
- [ ] Scan logs and evidence for secrets, source/prompt/raw-model leakage, private URLs, authorization headers, and personally identifying data; correct unsafe evidence before it is staged.
- [ ] Run the applicable local release gates, full test suite, and `git diff --check`; record any unavailable/nonterminal GitHub check without calling it passed.
- [ ] Commit code corrections separately (if any), then commit only final safe evidence and release material. Do not push or merge; if remote checks are available, snapshot their status for the exact evidence commit.

## Self-Review

- [ ] No state, cohort, artifact directory, cost ledger, or evidence namespace is reused from previous runs.
- [ ] Discovery begins from configured sources; Drive is only a persistence/output boundary during this run.
- [ ] Every one of the 20 frozen members has complete attempts and exactly one current terminal outcome.
- [ ] The audit labels each target `verified`, `verified_with_limitations`, or `not_verified`; it never converts partial funnel success into a completed 20-report claim.
