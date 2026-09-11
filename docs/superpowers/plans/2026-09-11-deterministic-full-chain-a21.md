# Deterministic Full-Chain A21 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate live A21 canaries on deterministic, queue-backed clean and bounded-repair report fixtures that reach durable `awaiting_review` and produce byte-identical A21 evidence.

**Architecture:** Extend the existing frozen-cohort queue-lineage integration test rather than introducing a parallel harness. The test creates its real cohort and queue job, drives the registered workers and outbox through every report stage, and reads the real report/state/manifest databases through `build_validation_reliability_artifact`; OpenAI and publication-provider edges remain the only faked boundaries.

**Tech Stack:** Python 3, pytest, SQLite, existing fake OpenAI fixture, durable workflow queue.

## Global Constraints

- Use actual cohort creation, submission, workers, handlers, outbox, manifest, checkpoints, report/state DBs, regeneration, validation, rendering, readiness, and A21 builder.
- Mock only true provider/browser/Drive/WordPress boundaries.
- Assert clean and repair fixture lineage, canonical source/publisher identity, isolation, no operator requeue, and repeatable canonical A21 bytes/SHA.
- Update the workflow/evidence documentation with the deterministic gate before live A21 canaries.

---

### Task 1: Add failing end-to-end fixture assertions

**Files:**
- Modify: `tests/test_validation_queue_lineage.py`

**Interfaces:**
- Consumes: `submit_frozen_validation_cohort_to_queue`, `run_workflow_worker_once`, `materialize_workflow_outbox`, `build_validation_reliability_artifact`.
- Produces: clean and soft-copy repair A21 entity assertions.

- [ ] **Step 1: Write the failing clean-chain test**

```python
for queue_name in ("source_ingest", "report_selection", "report_analysis", "report_render", "publication_readiness"):
    assert run_workflow_worker_once(..., queue_name=queue_name, ...).terminal_status == "succeeded"
    materialize_workflow_outbox(...)
entity = build_validation_reliability_artifact(request, _ctx()).first_attempt_entities[0]
assert (entity.first_pass, entity.eventual_success, entity.bounded_recovery, entity.operator_intervention) == (True, True, False, False)
```

Name the break: deleting a queue handoff, validation/readiness record, or root-lineage propagation prevents durable A21 success.

- [ ] **Step 2: Run the focused test to verify red**

Run: `python -m pytest -q tests/test_validation_queue_lineage.py`

Expected: it stops before readiness or exposes an incomplete provider fixture; it must not pass before the full chain is asserted.

- [ ] **Step 3: Add failing bounded-repair assertions**

```python
assert repaired_claim_ids == ["unsupported-soft-copy-claim"]
assert sibling_claim_bytes_before == sibling_claim_bytes_after
assert entity.bounded_recovery is True
assert not operator_requeue_rows
```

Name the break: an unsupported soft-copy claim leaks through, repairs a valid sibling, or requires an operator requeue.

### Task 2: Make only exposed production handoff corrections

**Files:**
- Modify only if red tests require it: `src/orchestrators/_workflow_queue_handlers/report_pipeline.py`

**Interfaces:**
- Consumes: queue job/payload frozen identity and lineage.
- Produces: child stage contexts and readiness submission retaining immutable provenance.

- [ ] **Step 1: Correct the single failing handoff**

Preserve the canonical `_stage_child_submission` and `_report_publication_readiness_submission` mechanisms; populate only the missing frozen source/publisher or root workflow field revealed by the test.

- [ ] **Step 2: Re-run both integration fixtures**

Run: `python -m pytest -q tests/test_validation_queue_lineage.py`

Expected: both fixtures reach durable `awaiting_review`; repair is bounded and provider-free.

### Task 3: Establish deterministic evidence and canary gate documentation

**Files:**
- Modify: `tests/test_validation_queue_lineage.py`
- Modify: `docs/workflows/validation-and-regeneration.md`
- Modify: `docs/quality/evidence.md`

**Interfaces:**
- Consumes: canonical A21 artifact serialization and SHA.
- Produces: two byte-identical artifact builds and documented pre-live gate.

- [ ] **Step 1: Assert same-run identity and isolation**

```python
assert canonical_json_bytes(first) == canonical_json_bytes(second)
assert first.artifact_hash == second.artifact_hash
assert {row.root_workflow_id for row in queue_rows} == {response.root_workflow_id}
assert {row["source_identity_id"] for row in manifest_rows} == {member["source_identity_id"]}
```

- [ ] **Step 2: Document the gate**

State that the deterministic clean and repair fixtures must pass before any live A21 canary, and that they do not authorize publication.

- [ ] **Step 3: Run proportionate verification**

Run: `python -m pytest -q tests/test_validation_queue_lineage.py tests/test_validation_reliability_service.py tests/test_workflow_queue_registry.py`

Expected: pass with no external calls, and a repeated full-chain run proves identical A21 payload bytes/SHA.
