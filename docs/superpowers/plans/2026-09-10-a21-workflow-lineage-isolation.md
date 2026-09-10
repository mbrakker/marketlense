# A21 Workflow Lineage Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict canonical A21 readiness and recovery evidence to the validation run's exact root workflow lineage.

**Architecture:** Retain the existing `validation_reliability_service` and its read-only SQLite snapshot. Pass the immutable `validation_runs.workflow_run_id` into the A21 state query and require it to equal the matched `workflow_jobs.root_workflow_id`, in addition to the existing report identity and immutable package checksum join. The queue job remains the provenance anchor for approval, retry, and operator evidence; absent lineage is no evidence.

**Tech Stack:** Python 3.12+, SQLite, frozen contracts, canonical workflow queue service, pytest.

## Global Constraints

- Modify only canonical A21 evidence construction; do not create parallel telemetry or change the legacy funnel.
- Read retained SQLite state only; telemetry makes no provider, browser, Drive, mailbox, or WordPress calls.
- Require package checksum, report ID, and exact root workflow lineage for all state-derived A21 signals.
- Fail closed when state or manifest lineage is blank, missing, or mismatched.
- Do not run a 20-report benchmark or alter the A21 TODO state.

---

### Task 1: Specify cross-workflow contamination regressions

**Files:**
- Modify: `tests/test_validation_reliability_service.py`

**Interfaces:**
- Consumes: two validation manifests sharing `report_id` but using `workflow-a` and `workflow-b`, plus queue jobs with matching root-workflow IDs.
- Produces: public artifact assertions showing A cannot consume B's readiness, automatic retry, operator requeue, or approval evidence.

- [x] **Step 1: Write the failing tests**

```python
def test_a21_state_evidence_is_isolated_to_validation_workflow_lineage(tmp_path) -> None:
    _create_run(reports_db, validation_run_id="validation-a", workflow_run_id="workflow-a")
    _create_run(reports_db, validation_run_id="validation-b", workflow_run_id="workflow-b")
    _record_full_first_attempt(reports_db, validation_run_id="validation-a", workflow_run_id="workflow-a")
    _record_full_first_attempt(reports_db, validation_run_id="validation-b", workflow_run_id="workflow-b")
    _record_durable_awaiting_review(state_db, root_workflow_id="workflow-b")
    assert _build("validation-a").first_attempt_entities[0].eventual_success is False
    assert _build("validation-b").first_attempt_entities[0].eventual_success is True
```

Add separate public-artifact assertions that B's retry and B's `operator_requeue` leave A's `bounded_recovery` and `operator_intervention` false, and that B's approval preserves readiness only for B.

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_validation_reliability_service.py -k "workflow_lineage" -q`

Expected: A incorrectly receives B's state evidence because the current query filters only `job.report_id`.

### Task 2: Bind canonical state evidence to root lineage

**Files:**
- Modify: `src/services/validation_reliability_service.py`

**Interfaces:**
- Consumes: `run["workflow_run_id"]` from `_read_manifest_rows` and `workflow_jobs.root_workflow_id`.
- Produces: `_A21StateEvidence` whose readiness, approval, operator requeue, retry, and retained automatic failure codes are all constrained to that lineage.

- [x] **Step 1: Implement the smallest query constraint**

```python
state_evidence = _read_a21_state_evidence(
    request=request,
    report_ids=report_ids,
    workflow_run_id=str(run["workflow_run_id"]),
)

# In the shared package/job base predicate:
# AND job.root_workflow_id=?
# Return no evidence if workflow_run_id is empty.
```

All downstream approval, transition, and attempt subqueries must remain correlated to this already-constrained job.

- [x] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_validation_reliability_service.py -k "workflow_lineage or a21" -q`

Expected: A is fail-closed; B retains same-workflow semantics for readiness, approval, retry, and requeue.

### Task 3: Document and validate deterministic behavior

**Files:**
- Modify: `docs/quality/evidence.md`
- Modify: `docs/superpowers/plans/2026-09-10-a21-workflow-lineage-isolation.md`

**Interfaces:**
- Consumes: canonical artifact bytes from a retained P6 run.
- Produces: explicit lineage semantics and repeatable validation evidence without changing A21 completion status.

- [x] **Step 1: Update evidence documentation**

Document that report ID and package checksum are insufficient on their own: the validation run's `workflow_run_id` and queue job's `root_workflow_id` must match; ambiguous lineage produces no A21 state evidence.

- [x] **Step 2: Run focused and static gates**

Run: `pytest tests/test_validation_reliability_service.py tests/test_validation_run_manifest.py tests/test_workflow_queue_service.py tests/test_workflow_queue_worker_failures.py tests/test_report_queue_publication.py -q`

Run: `python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json`, `python scripts/ci/run_type_check.py`, `python scripts/ci/check_formatting.py`, `python scripts/ci/check_ruff_lint.py`, `python scripts/ci/check_architecture_imports.py`, and `python scripts/ci/check_documentation.py`.

- [x] **Step 3: Replay retained P6 evidence twice**

Run the canonical builder twice with identical P6 Batch 1 reports, usage, and state SQLite inputs. Compare serialized bytes and `artifact_hash`; record that missing historical readiness queue lineage remains fail-closed if the run predates state retention.

**Result:** Batch 1 run `validation:22dca463b14045be841b46c4464a7392a3a2257cfb863c7361aa0d9723f913f0`
produced byte-identical artifacts with hash
`86cfe3cb21dfc403ea9092dcef36a4e3d5c4ce75fbb8a431ec63daf09b85194c`.
The first-attempt Pareto remains `targeted_repair=3` and
`awaiting_review_not_reached=2`. Its P6 state database retains no matching
publication-readiness evidence, so A21 readiness remains correctly fail-closed.

## Self-Review

- Task 1 covers same-report, two-root-workflow contamination for readiness, retry, requeue, and approval.
- Task 2 applies one shared lineage predicate, preserving immutable checksum/job joins and fail-closed behavior.
- Task 3 covers documentation, legacy compatibility through the existing full reliability suite, deterministic replay, and all requested gates.
- The plan adds neither a provider boundary nor a new telemetry subsystem.
