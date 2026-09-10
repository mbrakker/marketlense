# A21 Readiness History and Queue Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve achieved A21 review readiness after approval and classify retained automatic publication-readiness queue recovery without changing legacy reliability metrics.

**Architecture:** Extend only the canonical `validation_reliability_service` read-only state snapshot. A report reaches the A21 boundary when its immutable readiness package and matching successful queue job prove `awaiting_review`; a subsequent matching approval may advance the mutable readiness status without erasing that historical success. Queue attempt and transition records provide deterministic automatic-retry versus explicit-operator provenance.

**Tech Stack:** Python 3.12+, SQLite, frozen dataclass contracts, pytest, canonical workflow queue service.

## Global Constraints

- Reuse `src/services/validation_reliability_service.py`; do not create telemetry, persistence, or provider boundaries.
- Preserve the legacy eventual/current-attempt lifecycle and artifact hash format.
- Read canonical SQLite records only; telemetry must make zero provider, browser, Drive, mailbox, or WordPress calls.
- `awaiting_review` success is fail-closed when package, job, approval, or queue provenance cannot establish the required relationship.
- Do not run a fresh 20-report benchmark or update the A21 TODO state.

---

### Task 1: Specify approval-preserving readiness evidence

**Files:**
- Modify: `tests/test_validation_reliability_service.py`
- Modify: `src/services/validation_reliability_service.py`

**Interfaces:**
- Consumes: canonical `workflow_publication_readiness`, `workflow_publication_approvals`, and `workflow_jobs` rows.
- Produces: `_A21StateEvidence.awaiting_review_report_ids` based on achieved package history rather than only current readiness status.

- [x] **Step 1: Write the failing test**

```python
def test_a21_approval_preserves_prior_durable_awaiting_review(tmp_path) -> None:
    _record_full_first_attempt(reports_db)
    package = _record_durable_awaiting_review(state_db)
    before = _build_with_state(...)
    approve_publication_package(state_db, package_checksum=package, ...)
    after = _build_with_state(...)
    assert before.first_attempt_entities[0].eventual_success is True
    assert after.first_attempt_entities[0].eventual_success is True
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validation_reliability_service.py::test_a21_approval_preserves_prior_durable_awaiting_review -q`

Expected: FAIL because the existing state query only accepts current `readiness_status='awaiting_review'`.

- [x] **Step 3: Write minimal implementation**

```python
# Accept a matching succeeded publication_readiness job when either:
# 1. its retained readiness row is still awaiting_review, or
# 2. its immutable package checksum has a retained approved action.
# Require the package/job checksum and report identity join in both cases.
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_validation_reliability_service.py::test_a21_approval_preserves_prior_durable_awaiting_review -q`

Expected: PASS. Add the negative approval-only case and verify it remains false.

### Task 2: Specify automatic queue retry recovery

**Files:**
- Modify: `tests/test_validation_reliability_service.py`
- Modify: `src/services/validation_reliability_service.py`

**Interfaces:**
- Consumes: canonical `workflow_job_attempts`, `workflow_job_transitions`, and `workflow_jobs` rows for the `publication_readiness` job.
- Produces: per-report automatic queue recovery evidence used in first-pass, recovery type, and causal Pareto classification.

- [x] **Step 1: Write the failing test**

```python
def test_a21_automatic_publication_readiness_retry_is_bounded_recovery(tmp_path) -> None:
    _record_full_first_attempt(reports_db)
    _record_durable_awaiting_review(state_db, automatic_retry=True)
    entity = _build_with_state(...).first_attempt_entities[0]
    assert entity.first_pass is False
    assert entity.eventual_success is True
    assert entity.bounded_recovery is True
    assert entity.operator_intervention is False
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validation_reliability_service.py::test_a21_automatic_publication_readiness_retry_is_bounded_recovery -q`

Expected: FAIL because existing A21 recovery logic cannot see queue attempts or `retry_wait` transitions.

- [x] **Step 3: Write minimal implementation**

```python
# Mark automatic recovery only when a matching publication_readiness job has a
# failed retained attempt, a retry_wait/redelivery/restart transition, and a
# later successful attempt/job. Keep operator_requeue as higher-priority
# operator provenance. Prefer the retained attempt error code, otherwise use
# automatic_queue_retry as the stable causal reason.
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_validation_reliability_service.py -q`

Expected: PASS, including existing targeted repair, queue requeue, replay, usage, and deterministic-hash cases.

### Task 3: Document and verify

**Files:**
- Modify: `docs/quality/evidence.md`
- Modify: `docs/quality/contract_schemas.json` only if a public contract changes.

**Interfaces:**
- Consumes: final canonical reliability artifact and retained P6 records.
- Produces: current A21 evidence semantics and repeatable validation evidence.

- [x] **Step 1: Update the canonical evidence documentation**

Document that approved packages preserve achieved review readiness only when the original checksum/job evidence exists, and that automatic queue retry is a bounded recovery distinct from `operator_requeue`.

- [x] **Step 2: Run focused and static validation**

Run: `pytest tests/test_validation_reliability_service.py tests/test_validation_run_manifest.py tests/test_workflow_queue_service.py tests/test_report_queue_publication.py -q`

Run: `python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json`, `python scripts/ci/run_type_check.py`, `python scripts/ci/check_formatting.py`, `python scripts/ci/check_ruff_lint.py`, `python scripts/ci/check_architecture_imports.py`, and `python scripts/ci/check_documentation.py --check-generated`.

- [x] **Step 3: Run retained P6 replay twice**

Run the service twice with the same P6 Batch 1 or Batch 4 reports, usage, and state SQLite paths. Compare canonical bytes and `artifact_hash`; report recovered entity classification and the retained state-evidence limitation if the historical run predates queue readiness.

**Result:** Batch 1 run `validation:22dca463b14045be841b46c4464a7392a3a2257cfb863c7361aa0d9723f913f0`
produced byte-identical artifacts with hash
`81577b76a23fe8a6ca9380c48d124d04c69947b2147efd9e218124719a06e072`.
Its retained targeted repairs remain first-pass failures and appear in the
Pareto, but every inspected P6 Batch 1/4 state database contains zero
`publication_readiness` jobs and zero readiness records. A21 correctly reports
no eventual `awaiting_review` success for that historic cohort; it cannot prove
the required production readiness-recovery scenario without retained state
provenance.

## Self-Review

- Approval preservation is covered by Task 1, including an approval-only negative case.
- Automatic retry, retained failure reasons, and operator requeue precedence are covered by Task 2.
- Legacy funnel preservation, deterministic output, provider-free construction, documentation, and retained replay are covered by Task 3.
- The plan contains no benchmark execution, provider call, status closure, or new telemetry subsystem.
