# A21 First-Attempt Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the canonical validation reliability artifact with deterministic first-attempt conversion, recovery, per-report attribution, and a first-attempt failure Pareto.

**Architecture:** Build only from the persisted validation-run manifest and LLM usage ledger already consumed by `validation_reliability_service`. Keep `transitions`, `failed_transitions`, and `failure_pareto` unchanged; add typed first-attempt records to the same artifact and include them in its canonical hash.

**Tech Stack:** Python 3, frozen dataclass contracts, SQLite manifest/usage-ledger reads, pytest.

## Global Constraints

- Do not introduce provider, browser, Drive, mailbox, or WordPress calls in telemetry construction.
- A later successful attempt never changes `first_pass` from false to true.
- Missing retained attribution is represented as `unavailable`, never as zero.
- Preserve artifact schema version `1.0` and all existing fields/metrics.

---

### Task 1: Specify first-attempt artifact contracts and regression behavior

**Files:**
- Modify: `src/contracts/validation_reliability.py`
- Modify: `tests/test_validation_reliability_service.py`

**Interfaces:**
- Produces: `ValidationReliabilityFirstAttemptTransition`, `ValidationReliabilityFirstAttemptEntity`, and `ValidationReliabilityFirstAttemptParetoEntry` stored on `ValidationReliabilityArtifact`.

- [ ] **Step 1: Write the failing test**

```python
assert artifact.first_attempt_entities[0].first_pass is False
assert artifact.first_attempt_entities[0].eventual_success is True
assert artifact.first_attempt_entities[0].recovery_type == "bounded_recovery"
assert artifact.first_attempt_entities[0].attempts_required == 2
assert artifact.first_attempt_transitions[1].first_pass_conversion_rate == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validation_reliability_service.py -q`

Expected: FAIL because `ValidationReliabilityArtifact` has no first-attempt fields.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class ValidationReliabilityFirstAttemptEntity(SemanticIdContract):
    schema_version: str
    entity_key: str
    report_id: str
    first_pass: bool
    eventual_success: bool
    recovery_type: str
    attempts_required: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_validation_reliability_service.py -q`

Expected: PASS.

### Task 2: Derive first-attempt and recovery attribution from retained records

**Files:**
- Modify: `src/services/validation_reliability_service.py`
- Modify: `tests/test_validation_reliability_service.py`

**Interfaces:**
- Consumes: manifest attempts/stages and attribution-complete usage events.
- Produces: one ordered entity record per final validation entity, stage transition metrics, and deterministic first-attempt Pareto.

- [ ] **Step 1: Write the failing test**

```python
entity = artifact.first_attempt_entities[0]
assert entity.first_failure_code == "provider_timeout"
assert entity.first_failure_stage == "evidence_generation"
assert entity.provider_calls_before_recovery == 1
assert entity.total_tokens_before_recovery == 120
assert entity.estimated_cost_usd_before_recovery == 0.012
assert artifact.first_attempt_failure_pareto[0].failure_code == "provider_timeout"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validation_reliability_service.py -q`

Expected: FAIL because first-attempt attribution is absent.

- [ ] **Step 3: Write minimal implementation**

```python
first_attempt = min(entity_attempts, key=lambda row: int(row["attempt_number"]))
first_pass = _state_statuses(first_records)[to_state]
recovery_type = _recovery_type(first_attempt, later_attempts, stages_by_attempt)
usage = _usage_through(first_failure_completed_at)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_validation_reliability_service.py -q`

Expected: PASS.

### Task 3: Document, run canonical retained evidence, and close only on proof

**Files:**
- Modify: `docs/quality/evidence.md`
- Modify: `CONSOLIDATED_TODO.md` only after all A21 criteria are demonstrated.

- [ ] **Step 1: Add operational contract documentation**

Document the definitions, retained-only input boundary, unavailable attribution semantics, and artifact determinism in `docs/quality/evidence.md`.

- [ ] **Step 2: Run focused validation and static gates**

Run: `pytest tests/test_validation_reliability_service.py tests/test_validation_run_manifest.py -q` and the repository’s documented architecture/type/lint gates.

- [ ] **Step 3: Generate twice from an existing recovered validation run**

Run the canonical artifact build twice against one retained recovery run; compare output bytes and artifact hashes; retain the selected entity’s first-pass, eventual-success, recovery, Pareto, and usage attribution evidence.

- [ ] **Step 4: Run the fresh cohort only when prerequisites and operator authority permit**

Freeze twenty members before generation and use the governed validation procedure. If required credentials, retained fixtures, or explicit publication approval are unavailable, report that exact blocker and do not mark A21 closed.
