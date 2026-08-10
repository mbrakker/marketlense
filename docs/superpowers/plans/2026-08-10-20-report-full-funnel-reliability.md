# 20-Report Full-Funnel Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute and independently audit an isolated immutable 20-report production pipeline run, retaining safe CTO evidence and a commit-bound release record.

**Architecture:** Use the existing configuration service, immutable cohort/validation manifest, ingestion orchestrator, canonical WordPress publisher and evidence collector. A newly generated profile owns every state, output, cache, ledger, log, manifest, and evidence path; no historical cohort or state is reused. Only a demonstrated run-blocking implementation defect may change production code, and such a correction is test-first and separately attributable.

**Tech Stack:** Python 3.12, SQLite, YAML configuration, Drive/browser/mailbox acquisition services, configured model provider, WordPress REST boundary, pytest, Ruff, mypy, GitHub CLI.

## Global Constraints

- Run identity is unique for the actual date and a fresh UUID; do not reuse any named historical namespace, database, output, ledger, or cohort.
- Freeze exactly 20 deterministically admitted reports before expensive processing; failures remain in the denominator.
- No `--success-target`, validation weakening, source replacement after freeze, unbounded spend, or uncontrolled external writes.
- WordPress writes use the existing configured approved target and are accepted only after authenticated full readback; unchanged repeat publication must request and make zero writes.
- Standard logs and committed evidence contain bounded metadata only: no credentials, source text, rendered prompts, raw model output, private paths, or authorization headers.
- Preserve user worktree changes; use `apply_patch` for repository edits; use TDD before any implementation correction.

---

### Task 1: Establish producer and environment provenance

**Files:**
- Create: `docs/CTO_evidence/reliability_full_20260810_<uuid>/runtime_provenance.json`
- Create: `docs/CTO_evidence/reliability_full_20260810_<uuid>/model_policy_preflight.json`

**Interfaces:**
- Consumes: `git`, `.env`, canonical configuration service, `python -m src.cli`, WordPress service.
- Produces: exact commit, clean-worktree decision, runtime/version inventory, credential-presence-only result, paths, model-policy hash, and read-only WordPress preflight.

- [ ] **Step 1: Capture read-only producer provenance and clean-worktree state.**
- [ ] **Step 2: Run configuration/model-policy and credential-presence preflight without printing secrets.**
- [ ] **Step 3: Run the canonical read-only WordPress target preflight and runtime-path/log/evidence accessibility checks.**
- [ ] **Step 4: Store only bounded preflight metadata under the new evidence namespace.**

### Task 2: Create the isolated run profile

**Files:**
- Create: `src/config/app.reliability_full_20260810_<uuid>.yaml`
- Create: `docs/CTO_evidence/reliability_full_20260810_<uuid>/run_identity.json`

**Interfaces:**
- Consumes: `src/config/app.example.yaml`, active model policy, execution date, UUID.
- Produces: `MARKET_LENSE_CONFIG_PROFILE=reliability_full_20260810_<uuid>` and isolated output/cache/state/ledger/log paths.

- [ ] **Step 1: Generate a UUID and create a profile derived from the current application configuration.**
- [ ] **Step 2: Replace all run-owned paths with the unique isolated namespace and set budgets for at least 20 PDFs.**
- [ ] **Step 3: Calculate and record configuration and model-policy hashes before workflow execution.**
- [ ] **Step 4: Verify every configured path is inside the run namespace and absent before use.**

### Task 3: Validate the execution surface before live work

**Files:**
- Test: `tests/test_validation_run_manifest.py`
- Test: `tests/test_validation_reliability_service.py`
- Test: `tests/test_collect_cto_review_evidence.py`
- Test: `tests/test_publish_generator_card_validation.py`

**Interfaces:**
- Consumes: current CLI cohort, manifest, recovery, readiness, WordPress readback, and evidence collector contracts.
- Produces: focused baseline test results retained in `test_results.json`.

- [ ] **Step 1: Run focused cohort/admission/manifest/recovery/grounding/category/readiness/readback/evidence tests.**
- [ ] **Step 2: Record exact commands, exit codes, and counts without copying source or provider payloads.**
- [ ] **Step 3: Stop and classify any failed baseline gate before live mutation.**

### Task 4: Discover, acquire, admit, and freeze the cohort

**Files:**
- Create: `out/reliability_full_20260810_<uuid>/cohort_manifest.json`
- Create: `docs/CTO_evidence/reliability_full_20260810_<uuid>/acquisition_metrics.csv`
- Create: `docs/CTO_evidence/reliability_full_20260810_<uuid>/admission_metrics.csv`

**Interfaces:**
- Consumes: configured publisher discovery/acquisition services and immutable-cohort `ingest --cohort-size 20 --cohort-manifest` mode.
- Produces: frozen schema-1.1 cohort manifest and retained route/admission outcomes.

- [ ] **Step 1: Run authorized discovery/acquisition routes that naturally apply, retaining each candidate attempt and duplicate disposition.**
- [ ] **Step 2: Run deterministic admission for candidates until 20 are admitted, retaining rejected candidates outside the cohort denominator.**
- [ ] **Step 3: Atomically persist and re-read the 20-member manifest, hashes, selection reasons, and derived cohort/validation identities.**
- [ ] **Step 4: Verify no future selection command can alter membership.**

### Task 5: Execute processing, recovery, and publication

**Files:**
- Create: `state/reliability_full_20260810_<uuid>/reports.sqlite`
- Create: `state/reliability_full_20260810_<uuid>/llm_usage.sqlite`
- Create: `state/reliability_full_20260810_<uuid>/logs/market_lense_YYYY-MM-DD.log`
- Create: `out/reliability_full_20260810_<uuid>/validation-runs/<id>/reliability_telemetry.json`

**Interfaces:**
- Consumes: frozen cohort manifest, `ingest`, canonical recovery services, `publish-wp`, provider and WordPress service boundaries.
- Produces: current stage records and exactly one terminal state per admitted member.

- [ ] **Step 1: Execute the fixed cohort through ingestion and every applicable readiness gate with producer and validation identities injected.**
- [ ] **Step 2: For a typed failure, retain the failed attempt, select the narrowest valid checkpoint, and run only the approved recovery route.**
- [ ] **Step 3: If a general implementation defect blocks the run, first write and observe a focused failing regression test, make the smallest fix, then rerun the test and start a new validation-run ID without hiding earlier evidence.**
- [ ] **Step 4: Publish only frozen, publish-ready members through the canonical publisher and retain full authenticated readback outcomes.**
- [ ] **Step 5: Repeat publication unchanged with full manifest enforcement and record requested/actual writes and duplicate checks.**

### Task 6: Generate, audit, and validate the evidence pack

**Files:**
- Create: `docs/CTO_evidence/reliability_full_20260810_<uuid>/`
- Create: `docs/releases/2026-08-10-20-report-full-funnel-reliability.md`

**Interfaces:**
- Consumes: immutable cohort and validation manifests, isolated state databases, artifacts, run-owned logs, cost ledger, WordPress transactions/readbacks, exact commit and configuration hashes.
- Produces: required machine-readable evidence inventory, independent audit, release record, and safe snapshot manifest.

- [ ] **Step 1: Run the strict evidence collector against only the isolated namespace; do not use unavailable-log bypass.**
- [ ] **Step 2: Derive required funnel, failure, recovery, lineage, category, figure, final-HTML, publication, cost, runtime, intervention, and rerun artifacts from retained state.**
- [ ] **Step 3: Run a separate read-only audit that does not consume the release narrative and marks every target verified, verified-with-limitations, or not-verified.**
- [ ] **Step 4: Scan evidence and logs for prohibited leakage, then create the release record from audited data only.**

### Task 7: Run release checks and commit evidence

**Files:**
- Modify: generated evidence and release record only, unless Task 5 proved a run-blocking implementation defect.
- Test: full repository suite and configured quality scripts discovered from `docs/quality/release-gates.md`.

**Interfaces:**
- Consumes: finalized evidence directory and current repository revision.
- Produces: retained test/GitHub status artifacts and one intentional evidence/release commit.

- [ ] **Step 1: Run formatter, Ruff, mypy, schema/contract generation, dependency/architecture/documentation gates, focused tests, integration tests where credentials and opt-in permit, full pytest, and `git diff --check`.**
- [ ] **Step 2: Inspect the final diff for scope, generated-data safety, and secret exposure.**
- [ ] **Step 3: Commit the evidence and release record only after fresh validation evidence confirms all required checks actually ran.**
- [ ] **Step 4: Query GitHub checks for the exact committed SHA and record availability honestly.**

## Self-Review

- [ ] Cohort membership, terminal accounting, typed recovery, publication readback, repeat zero-write, cost attribution, and leakage checks each map to a retained data source rather than a narrative claim.
- [ ] The plan forbids replacement after freeze, success-target selection, log-availability bypass, and validation weakening.
- [ ] A correction path is explicitly scoped to a demonstrated general run-blocking defect and is test-first.
