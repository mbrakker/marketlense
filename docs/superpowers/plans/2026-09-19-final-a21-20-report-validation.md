# Final A21 20-Report Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a commit-bound, non-publishing final reliability measurement for the immutable A21 20-report cohort and compare it honestly with baseline `bfab37bbd1e4c194c027f14dd54817fb61f940a6`.

**Architecture:** The existing frozen-cohort runner is the only execution path: it validates source hashes, creates isolated state, submits one production cohort through the normal queue and supervisor, then retains the resulting terminal evidence. The existing reliability exporter derives all evidence views from that one retained result; the documentation records facts rather than changing workflow behavior.

**Tech Stack:** Python production queue/orchestrator, SQLite state and usage ledgers, JSON/CSV evidence artifacts, pytest, GitHub Actions.

## Global Constraints

- Reuse `scripts/quality/frozen_reliability_cohort_20.json` unchanged; no member substitution or source-hash change.
- Run one clean, exact 40-character SHA only after its GitHub CI is green.
- Use `scripts/quality/run_frozen_reliability_cohort.py` only; no stage command, operator requeue, database edit, or validation-only sequencing.
- Start with fresh isolated state and never reuse derived editorial artifacts.
- Do not invoke WordPress publication or any external publication command.
- Retain all 20 terminal outcomes, including failures; do not rerun members.
- Record aggregate provider usage, tokens, cost, repair, intervention, duration, source hashes, and typed-failure evidence.

---

### Task 1: Establish immutable measurement preconditions

**Files:**
- Read: `scripts/quality/frozen_reliability_cohort_20.json`
- Read: `scripts/quality/run_frozen_reliability_cohort.py`
- Read: `scripts/quality/ias_live_canary_runner.py`
- Read: `docs/quality/reliability-cohort-20260914-bfab37bb/README.md`

**Interfaces:**
- Consumes: exact `HEAD`, clean worktree, green GitHub CI, and the frozen source manifest.
- Produces: recorded run SHA and a preflight artifact proving all 20 immutable inputs are present and admissible.

- [ ] **Step 1: Confirm source-member identity and content hashes**

Run: `python scripts/quality/run_frozen_reliability_cohort.py --preflight-only --runs-root tmp/a21-final-preflight`

Expected: 20 member records and `admitted_count=20`; no source artifact or checksum failure.

- [ ] **Step 2: Confirm revision immutability and CI status**

Run: `git status --porcelain; git rev-parse HEAD; gh run list --commit <HEAD> --limit 20`

Expected: an empty status result, one 40-character SHA, and completed successful required CI runs for that SHA.

### Task 2: Execute the one canonical cohort workflow

**Files:**
- Read: `scripts/quality/run_frozen_reliability_cohort.py`
- Runtime output: `tmp/a21-final-live/`

**Interfaces:**
- Consumes: unchanged immutable manifest and the precondition evidence from Task 1.
- Produces: one `cohort_result.json` containing all 20 production-workflow member outcomes and cohort-scoped telemetry.

- [ ] **Step 1: Run the sole allowed cohort submission**

Run: `python scripts/quality/run_frozen_reliability_cohort.py --runs-root tmp/a21-final-live --max-duration 7200`

Expected: exactly 20 results sharing one workflow root; each is `awaiting_review` or typed `failed`; no WordPress publication is submitted.

- [ ] **Step 2: Preserve the unmodified source result**

Run: `Get-ChildItem tmp/a21-final-live -Recurse -Filter cohort_result.json`

Expected: exactly one retained `cohort_result.json`; it is copied intact into the new committed quality-evidence bundle.

### Task 3: Export, inspect, and document the measurement

**Files:**
- Create: `docs/quality/reliability-cohort-20260919-a21-final/`
- Modify: `docs/quality/evidence.md`
- Modify: `docs/quality/reliability-cohort-20260919-a21-final/README.md`

**Interfaces:**
- Consumes: unmodified Task 2 `cohort_result.json` and frozen manifest.
- Produces: derived evidence-export views, integrity hashes, an explicit baseline comparison, editorial inspection findings, and stated residual root causes.

- [ ] **Step 1: Generate read-only evidence projections**

Run: `python scripts/quality/export_reliability_run_evidence.py --cohort-result <cohort_result.json> --output-dir docs/quality/reliability-cohort-20260919-a21-final/evidence-export`

Expected: terminal outcomes, A21 funnel, stage conversion, typed failure Pareto, repair/regeneration, intervention, readiness, and usage artifacts derived from the exact retained result.

- [ ] **Step 2: Inspect successful and failed rendered/validation outputs**

Run: `python scripts/ci/check_public_report_quality.py`

Expected: no unreported factual/editorial regression in inspectable retained outputs; unavailable output must be labeled unavailable rather than inferred clean.

- [ ] **Step 3: Record the outcome and compare to the official baseline**

Expected documentation values: baseline 2/20 (10%) first-attempt `awaiting_review` and readiness, 18 failures; current numerator/denominator, A21 target attainment, all typed codes, and every remaining root cause.

### Task 4: Verify retained evidence and publish the documentation commit

**Files:**
- Read: `docs/quality/reliability-cohort-20260919-a21-final/`
- Modify: `docs/quality/evidence.md`

**Interfaces:**
- Consumes: complete evidence bundle and final documentation.
- Produces: one reviewable commit pushed to `origin/main`.

- [ ] **Step 1: Verify final scope and provenance**

Run: `git diff --check; git diff -- docs/quality; python -m pytest -q tests/test_frozen_reliability_cohort_runner.py tests/test_a21_bfab37bb_evidence_closure.py tests/test_validation_queue_lineage.py -k "a21_full_chain"`

Expected: no whitespace errors; evidence files bind the measured SHA, unchanged member hashes, and 20 terminal results; targeted validation passes.

- [ ] **Step 2: Commit and push retained evidence only**

Run: `git add docs/quality docs/superpowers/plans/2026-09-19-final-a21-20-report-validation.md; git commit -m "docs: retain final A21 cohort validation"; git push origin main`

Expected: the commit contains evidence and documentation only; no runtime/configuration remediation is included.

## Self-Review

- Spec coverage: Tasks 1–2 enforce the immutable cohort, clean SHA, green CI, isolated canonical workflow, no publication, and no intervention; Task 3 retains all requested measurement dimensions plus outcome inspection and baseline comparison; Task 4 verifies and pushes the evidence.
- Placeholder scan: no TODO/TBD or unspecified implementation steps remain.
- Type consistency: the runner produces `cohort_result.json`, which is the only input to the exporter and documentation bundle.

## Execution Handoff

This plan is being executed inline because the request is a single controlled operational run and no independent implementation tasks are being delegated.
