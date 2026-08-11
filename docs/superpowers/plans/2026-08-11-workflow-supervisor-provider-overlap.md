# Workflow Supervisor Provider-Overlap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a bounded supervisor pass to overlap independent provider-waiting queue jobs without changing durable queue semantics.

**Architecture:** Keep all queue transitions inside the existing worker and queue-service boundaries. The supervisor will add a fair, bounded dispatcher that submits at most the configured global worker count and never permits the number of in-flight jobs to exceed the remaining total-job allowance. Serial execution remains the default and follows the existing scheduling path.

**Tech Stack:** Python 3.14, `ThreadPoolExecutor`, existing typed workflow-control contracts, SQLite durable queue, pytest, existing performance telemetry.

## Global Constraints

- Default behavior remains serial (`max_parallel_workers=1`).
- The tested provider-wait cap is three workers; configuration clamps higher values to three.
- Existing per-queue durable concurrency controls, total-job allowance, leases, retries, idempotency, outbox writes, approvals, and publication safeguards remain authoritative.
- No cache, model, prompt, quality threshold, or cost-policy change is included.
- Generated contract and documentation inventories are regenerated, never hand-edited.

---

### Task 1: Prove bounded supervisor dispatch with tests

**Files:**

- Create: `tests/test_workflow_supervisor_parallelism.py`
- Modify: `src/orchestrators/workflow_supervisor_orchestrator.py`

**Interfaces:**

- Consumes: `run_supervisor_once(request, ctx, dependencies=...)` and `WorkflowSupervisorSettings.max_parallel_workers`.
- Produces: bounded overlapping calls through the existing injected `run_worker` dependency.

- [x] **Step 1: Write failing tests.**

```python
def test_supervisor_overlaps_independent_workers_when_parallelism_is_enabled():
    # A barrier-backed injected worker records three simultaneous active calls.
    assert result.completed_job_count == 3
    assert max_active == 3


def test_supervisor_never_exceeds_total_job_cap_with_parallel_workers():
    assert result.completed_job_count == 2
    assert started_calls == 2
```

- [x] **Step 2: Verify red.**

Run: `python -m pytest tests/test_workflow_supervisor_parallelism.py -q`

Expected: failure because the serial supervisor does not accept or use the new worker cap.

- [x] **Step 3: Implement the minimal fair dispatcher.**

Add the contract field and a `ThreadPoolExecutor` path only when the cap exceeds one. Submit one work item per queue round; do not refill capacity when every remaining slot is already represented by an in-flight job. Aggregate results on the supervisor thread.

- [x] **Step 4: Verify green.**

Run: `python -m pytest tests/test_workflow_supervisor_orchestrator.py tests/test_workflow_supervisor_parallelism.py -q`

Expected: all pass.

### Task 2: Wire bounded configuration and current documentation

**Files:**

- Modify: `src/contracts/workflow_control.py`
- Modify: `src/services/_config_service/workflow_control.py`
- Modify: `src/config/app.yaml`
- Modify: `src/config/app.example.yaml`
- Modify: `docs/architecture/asynchronous-workflow-queue.md`

**Interfaces:**

- Consumes: `workflow_control.supervisor.max_parallel_workers`.
- Produces: a clamped `WorkflowSupervisorSettings.max_parallel_workers` value.

- [x] **Step 1: Add a failing configuration assertion.**

```python
assert settings.max_parallel_workers == 3
```

- [x] **Step 2: Implement field parsing and examples.**

Use a default of one and clamp configured values to `[1, 3]`; keep the supervisor disabled by default.

- [x] **Step 3: Verify configuration tests.**

Run: `python -m pytest tests/test_config_service.py tests/test_workflow_supervisor_parallelism.py -q`

Expected: all pass.

### Task 3: Benchmark and live validation

**Files:**

- Create: `scripts/quality/benchmark_workflow_supervisor_parallelism.py`
- Create: `scripts/quality/benchmark_workflow_supervisor_live_provider_overlap.py`
- Create: scoped JSON and Markdown evidence under `outputs/`

**Interfaces:**

- Consumes: production `run_supervisor_once` plus explicit dependency injection.
- Produces: redacted wall-time, queue-wait, provider-latency, quality, and cost comparisons.

- [x] **Step 1: Run deterministic SQLite-like baseline.**

Execute two warmups and seven measured serial samples with a provider-wait representative injected worker.

- [x] **Step 2: Run the exact capped-parallel matrix.**

Repeat with three workers and retain terminal-status/output digests, telemetry, median, p95, range, and CV.

- [x] **Step 3: Run a controlled live-provider scheduler canary.**

One JSON preflight then a maximum of 54 short calls validates real provider overlap, exact JSON output, equivalent cost, and the configured worker cap.

- [x] **Step 4: Reject or revert on any regression.**

Keep the implementation only if both deterministic and live comparisons pass quality and cost gates and show a material speed gain.

### Task 4: Regenerate and verify repository artifacts

**Files:**

- Modify: `docs/quality/contract_schemas.json`
- Modify: generated `docs/generated/*` inventories affected by the configuration/contract change.

- [ ] **Step 1: Regenerate inventories.**

Run: `python scripts/ci/check_contract_schemas.py --update` and `python scripts/docs/generate_references.py`.

- [ ] **Step 2: Run verification.**

Run focused tests, Ruff, contract-schema validation, generated-reference validation, the bounded queue workflow validation, and the required safe discovery → acquisition → ingest → publish validation sequence.

- [ ] **Step 3: Commit only validated scope.**

Use a path-limited commit so unrelated staged or unstaged work remains untouched.
