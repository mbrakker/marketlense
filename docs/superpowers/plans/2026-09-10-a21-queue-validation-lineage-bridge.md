# A21 Queue Validation Lineage Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind a frozen validation run to one durable report-queue root and preserve that context through publication readiness.

**Architecture:** Extend the existing typed queue payload with optional frozen-validation identifiers; do not add a separate store. A canonical frozen-cohort queue submission owns the one root-workflow ID, creates the validation manifest using that exact ID, and enqueues source ingest with the retained identifiers. The report queue adapter projects those fields plus `job.root_workflow_id` into a report-only `RunContext`, so existing validation-manifest writers retain the same root lineage without redefining non-validation worker contexts.

**Tech Stack:** Python 3.12+, frozen dataclasses, SQLite report/state stores, canonical workflow queue, pytest.

## Global Constraints

- Reuse the canonical validation-reliability artifact, manifest, queue, and report pipeline; create no parallel telemetry or lineage persistence.
- Preserve `RunContext.run_id` outside the report queue-to-pipeline validation projection.
- Require both `validation_run_id` and `cohort_id` for a queue-backed validation job; fail closed on blank, altered, or root-mismatched lineage.
- Preserve queue root, immutable source reference/hash, and validation context through source ingest, selection, analysis, render, and publication readiness.
- Do not alter provider, browser, Drive, mailbox, or WordPress behavior solely to propagate lineage.
- Do not start the 20-report benchmark or close A21.

---

### Task 1: Specify the typed queue validation projection

**Files:**
- Modify: `src/contracts/workflow_queue.py`
- Modify: `tests/test_workflow_queue_registry.py`

**Interfaces:**
- Consumes: frozen `validation_run_id`, `cohort_id`, and the owning queue root.
- Produces: inherited `validation_run_id` and `cohort_id` on report queue payloads; queue root stays on `WorkflowJob`.

- [ ] **Step 1: Write the failing child-handoff test**

```python
def test_queue_report_stage_handoff_preserves_frozen_validation_context() -> None:
    child = _stage_child_submission(job=root_job, payload=SourceIngestPayload(
        validation_run_id="validation-a", cohort_id="cohort-a", ...
    ), next_queue="report_selection", next_payload=ReportSelectionPayload(...))
    assert child.payload.validation_run_id == "validation-a"
    assert child.payload.cohort_id == "cohort-a"
    assert child.root_workflow_id == root_job.root_workflow_id
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_workflow_queue_registry.py -k "frozen_validation_context" -q`

Expected: child payload loses the identifiers because they are not queue payload fields.

- [ ] **Step 3: Implement the minimal common payload fields and handoff copy**

```python
@dataclass(frozen=True)
class WorkflowQueuePayload:
    validation_run_id: str = ""
    cohort_id: str = ""

next_payload = replace(
    next_payload,
    validation_run_id=payload.validation_run_id,
    cohort_id=payload.cohort_id,
)
```

- [ ] **Step 4: Run the focused registry test**

Run: `pytest tests/test_workflow_queue_registry.py -k "frozen_validation_context" -q`

Expected: PASS.

### Task 2: Create the canonical frozen-cohort queue submission bridge

**Files:**
- Modify: `src/orchestrators/ingest_orchestrator.py`
- Modify: `tests/test_ingest_cohort.py`

**Interfaces:**
- Consumes: frozen cohort members, `IngestSettings`, and the existing manifest identifiers/configuration hashes.
- Produces: one `source_ingest` `WorkflowJobSubmission` per admitted report, all rooted in one generated root ID, plus a `validation_runs` record whose `workflow_run_id` is that root.

- [ ] **Step 1: Write the failing public bridge test**

```python
def test_submit_frozen_validation_cohort_to_queue_binds_manifest_to_root(tmp_path) -> None:
    submission = submit_frozen_validation_cohort_to_queue(...)
    root = get_workflow_job(state_db, submission.job_ids[0], ctx).root_workflow_id
    assert read_validation_run(...).workflow_run_id == root
    assert submission.validation_run_id
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_ingest_cohort.py -k "queue_binds_manifest_to_root" -q`

Expected: no production frozen-cohort queue bridge exists.

- [ ] **Step 3: Implement one bridge that creates the manifest and queues immutable sources**

```python
# Generate one root ID in the bridge, use it as WorkflowJobSubmission.root_workflow_id,
# create_validation_run_manifest(... workflow_run_id=RunId(root_id)), and include
# validation_run_id/cohort_id on SourceIngestPayload. Do not enqueue if either
# retained identity cannot be established.
```

- [ ] **Step 4: Run the bridge test**

Run: `pytest tests/test_ingest_cohort.py -k "queue_binds_manifest_to_root" -q`

Expected: PASS.

### Task 3: Project retained queue lineage into the report pipeline

**Files:**
- Modify: `src/orchestrators/_workflow_queue_handlers/report_pipeline.py`
- Modify: `src/orchestrators/_workflow_queue_handlers/acquisition.py`
- Modify: `src/orchestrators/acquisition_ingest_handoff_orchestrator.py`
- Test: `tests/test_workflow_queue_registry.py`

**Interfaces:**
- Consumes: typed payload validation fields and `WorkflowJob.root_workflow_id`.
- Produces: a report-only `RunContext` with validation IDs and `run_id=root_workflow_id`, and downstream payloads/readiness jobs retaining the same root.

- [ ] **Step 1: Write failing worker-boundary tests**

```python
def test_report_queue_validation_context_uses_job_root_without_changing_worker_context():
    result = handler(validation_job, validation_payload, worker_ctx)
    assert observed_pipeline_ctx.validation_run_id == validation_payload.validation_run_id
    assert observed_pipeline_ctx.cohort_id == validation_payload.cohort_id
    assert observed_pipeline_ctx.run_id == validation_job.root_workflow_id
    assert worker_ctx.run_id != validation_job.root_workflow_id
```

Add a failure case for one blank identifier and an acquisition-to-source-ingest handoff assertion.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_queue_registry.py tests/test_acquisition_ingest_handoff_orchestrator.py -k "validation_context or validation_lineage" -q`

Expected: the pipeline receives worker context and the acquisition handoff drops validation payload identifiers.

- [ ] **Step 3: Implement the narrow report-only projection**

```python
def _queue_report_context(job, payload, ctx):
    if not payload.validation_run_id and not payload.cohort_id:
        return ctx
    if not all((payload.validation_run_id, payload.cohort_id, job.root_workflow_id)):
        raise AppError(code="workflow_queue_validation_lineage_incomplete", ...)
    return replace(ctx, run_id=RunId(job.root_workflow_id),
                   validation_run_id=payload.validation_run_id,
                   cohort_id=payload.cohort_id)
```

Use only this projected context for report pipeline/admission calls and preserve the fields in all report child/readiness payloads.

- [ ] **Step 4: Run boundary tests**

Run: `pytest tests/test_workflow_queue_registry.py tests/test_acquisition_ingest_handoff_orchestrator.py -k "validation_context or validation_lineage" -q`

Expected: PASS.

### Task 4: Verify full canonical artifact behavior

**Files:**
- Modify: `tests/test_validation_reliability_service.py`
- Modify: `docs/quality/evidence.md`
- Modify: `docs/superpowers/plans/2026-09-10-a21-queue-validation-lineage-bridge.md`

**Interfaces:**
- Consumes: a real frozen-cohort bridge submission, canonical queue job state, retained manifest stages, and A21 builder input.
- Produces: integration evidence that a same-report second root cannot contaminate a successfully attributed A21 readiness result.

- [ ] **Step 1: Write the failing production-path integration test**

```python
def test_queue_backed_frozen_validation_run_reaches_a21_readiness_without_manual_ids(tmp_path):
    bridge = submit_frozen_validation_cohort_to_queue(...)
    execute_report_queue_chain_until("publication_readiness", bridge, ...)
    assert manifest.workflow_run_id == source_ingest.root_workflow_id
    assert all(stage.workflow_run_id == source_ingest.root_workflow_id for stage in stages)
    assert readiness_job.root_workflow_id == source_ingest.root_workflow_id
    assert build_validation_reliability_artifact(...).first_attempt_entities[0].eventual_success
```

Include second-root same-report readiness/retry/requeue evidence and assert it cannot alter the first artifact.

- [ ] **Step 2: Run the integration test to verify it fails**

Run: `pytest tests/test_validation_reliability_service.py -k "queue_backed_frozen_validation" -q`

Expected: the normal queue path lacks a unified frozen-run/root bridge.

- [ ] **Step 3: Update evidence documentation and run all gates**

Run: `pytest tests/test_validation_reliability_service.py tests/test_validation_run_manifest.py tests/test_workflow_queue_registry.py tests/test_workflow_queue_service.py tests/test_workflow_queue_worker_failures.py tests/test_report_queue_publication.py -q`

Run: `python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json`, `python scripts/ci/run_type_check.py`, `python scripts/ci/check_formatting.py`, `python scripts/ci/check_ruff_lint.py`, `python scripts/ci/check_architecture_imports.py`, and `python scripts/ci/check_documentation.py`.

- [ ] **Step 4: Replay retained evidence and run one safe queue-backed canary**

Run the retained P6 build twice and compare bytes/hash. Then run one fresh frozen, queue-backed report only through `awaiting_review` using the approved isolated/safe profile. Record state, manifest, A21 artifact, and any credential/provider blocker; do not begin the 20-report cohort.

## Self-Review

- Task 1 retains validation context in the existing typed queue payload, not a new store.
- Task 2 makes the durable root and validation manifest one production-owned identity.
- Task 3 limits `run_id` projection to queue-backed validation report execution.
- Task 4 proves readiness attribution, cross-root isolation, deterministic replay, and no benchmark closure.
