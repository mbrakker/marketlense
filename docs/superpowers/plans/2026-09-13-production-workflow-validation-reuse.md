# Production Workflow Validation Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make production orchestration the default execution path for live canary and frozen reliability validation.

**Architecture:** Extract the preselected-local frozen-cohort handoff from the existing ingest orchestration into a typed public production boundary. The quality runners retain only isolated state/configuration, bounded waiting, and evidence reads; the boundary owns source provenance, runtime and admission preflight, cohort freezing, and durable queue submission. The runner drives work with the production supervisor rather than a custom queue loop.

**Tech Stack:** Python, pytest, existing typed contracts, ingest orchestrator, workflow supervisor, SQLite evidence.

## Global Constraints

- Reuse production preflight, admission, cohort, queue, worker, and supervisor behavior; do not add validation-only workflow sequencing.
- Preserve `run_ingest` behavior, retry policy, prompts, models, validators, queue ordering, and result contracts.
- Validation may only choose local inputs, isolate mutable paths, bound execution, prevent publication through existing controls, and collect evidence.
- Component benchmarks remain component-scoped and must say so in their names or output.
- Do not use monkeypatching or replace private helpers in tests.

---

### Task 1: Define and prove the public preselected-source boundary

**Files:**
- Modify: `src/contracts/validation_run_manifest.py`
- Modify: `src/orchestrators/ingest_orchestrator.py`
- Modify: `tests/test_validation_queue_lineage.py`

**Interfaces:**
- Produces: a typed request for retained local sources and a response containing canonical validation and root-workflow identities.
- Consumes: `IngestSettings`, a local PDF source plus retained provenance, and the existing frozen-validation queue submitter.

- [ ] **Step 1: Write a failing integration regression**

```python
def test_preselected_frozen_validation_submission_uses_production_admission_and_queue(...):
    submission = submit_preselected_frozen_validation_cohort(request, ctx)
    assert submission.jobs[0].queue_name == "source_ingest"
    assert submission.root_workflow_id
```

- [ ] **Step 2: Verify it fails because the public boundary is unavailable**

Run: `python -m pytest tests/test_validation_queue_lineage.py -q`

- [ ] **Step 3: Implement the smallest production-owned boundary**

```python
def submit_preselected_frozen_validation_cohort(request, ctx):
    # record retained provenance, run canonical preflight/admission,
    # freeze admitted sources, and call submit_frozen_validation_cohort_to_queue
```

- [ ] **Step 4: Reuse the extracted cohort-freezing owner from `run_ingest`**

```python
files_to_process = freeze_admitted_validation_cohort(...)
```

- [ ] **Step 5: Run focused production-boundary tests**

Run: `python -m pytest tests/test_validation_queue_lineage.py tests/test_ingest_parallel.py -q`

### Task 2: Route validation runners through production control

**Files:**
- Modify: `scripts/quality/ias_live_canary_runner.py`
- Modify: `scripts/quality/run_frozen_reliability_cohort.py`
- Modify: `tests/test_ias_first_attempt_live_canary.py`
- Modify: `tests/test_frozen_reliability_cohort_runner.py`

**Interfaces:**
- Consumes: the public preselected-source submission boundary and `run_supervisor_once`.
- Produces: the unchanged JSON canary/cohort result records plus the canonical queue lineage.

- [ ] **Step 1: Write a failing runner integration test**

```python
def test_runner_submits_the_preselected_source_through_the_production_boundary(...):
    result = run_first_attempt_canary(...)
    assert result["workflow_root_id"]
```

- [ ] **Step 2: Verify it fails before runner refactoring**

Run: `python -m pytest tests/test_ias_first_attempt_live_canary.py tests/test_frozen_reliability_cohort_runner.py -q`

- [ ] **Step 3: Replace runner-owned preflight/cohort/queue and manual worker sequencing**

```python
submission = submit_preselected_frozen_validation_cohort(request, ctx)
run_supervisor_once(supervisor_request, ctx)
```

- [ ] **Step 4: Run runner tests**

Run: `python -m pytest tests/test_ias_first_attempt_live_canary.py tests/test_frozen_reliability_cohort_runner.py -q`

### Task 3: Record the invariant and audit runner scope

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/quality/testing.md`
- Modify: selected `scripts/quality` docstrings only where a component runner could be confused with full production validation.

- [ ] **Step 1: Add the validation-workflow-reuse invariant verbatim to repository policy and testing guidance**

- [ ] **Step 2: Mark intentional benchmark/component runners as not end-to-end production validation where their existing name/output is ambiguous**

- [ ] **Step 3: Run static and focused checks**

Run: `python -m pytest tests/test_validation_queue_lineage.py tests/test_ias_first_attempt_live_canary.py tests/test_frozen_reliability_cohort_runner.py -q`

### Task 4: Validate an isolated retained report and deliver

**Files:**
- Inspect: isolated run evidence under `docs/quality/reliability-cohort-20260913-retry-standard-flow/`

- [ ] **Step 1: Run one retained real-report member through the refactored path with normal safe configuration**

Run: `python scripts/quality/run_frozen_reliability_cohort.py --preflight-only ...`

- [ ] **Step 2: Inspect terminal JSON, state queue rows, validation-manifest stages, and retained artifacts**

- [ ] **Step 3: Run applicable fast tests and static checks, inspect the final diff, commit the focused change, and push the current branch**
