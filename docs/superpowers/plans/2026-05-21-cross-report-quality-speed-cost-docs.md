# Cross-Report Quality Speed Cost Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the cross-report quality, speed, cost, and documentation hardening items.

**Architecture:** Stay inside the existing modular monolith and reuse the existing cross-report contracts, generators, services, orchestrator, prompt namespace, and publish path. Add only focused tests and a control-plane budget gate in the orchestrator so model calls are skipped when bounded evidence input already exceeds the configured cap.

**Tech Stack:** Python dataclasses, pytest, SQLite-backed analytics fixtures, existing Market Lense services, Typer CLI.

---

### Task 1: Quality Regression Tests

**Files:**
- Modify: `tests/test_cross_report_analysis_contracts.py`
- Modify: `tests/test_cross_report_analysis_orchestrator.py`

- [x] **Step 1: Add contract fixture coverage and JSON payload round-trip tests**

Add tests that compare the fixture contract set with every `CrossReport*` dataclass in `src.contracts.cross_report_analysis`, then serialize each fixture through JSON and compare the decoded payload to `asdict(contract)`.

- [x] **Step 2: Add orchestrator cache invalidation test**

Add a pipeline test that runs the same request twice with a changed selected projection content hash and asserts the second run does not reuse idempotency and makes a second model-boundary call.

- [x] **Step 3: Verify targeted tests**

Run:

```bash
pytest tests\test_cross_report_analysis_contracts.py::test_cross_report_contract_fixtures_cover_every_dataclass tests\test_cross_report_analysis_contracts.py::test_cross_report_contract_payloads_round_trip_through_json -q --basetemp .pytest_tmp_contracts
pytest tests\test_cross_report_analysis_orchestrator.py::test_cross_report_orchestrator_projection_hash_change_invalidates_cache -q --basetemp .pytest_tmp
```

Expected: all targeted tests pass.

### Task 2: Budget Gate

**Files:**
- Modify: `tests/test_cross_report_analysis_orchestrator.py`
- Modify: `src/orchestrators/cross_report_analysis_orchestrator.py`

- [x] **Step 1: Write the failing pre-model budget test**

Add a test that sets `max_prompt_chars` below assembled input size and asserts `AppError(code="cross_report_prompt_budget_exceeded")`, operator context, no model calls, and no persisted analysis artifact.

- [x] **Step 2: Run test and confirm RED**

Run:

```bash
pytest tests\test_cross_report_analysis_orchestrator.py::test_cross_report_orchestrator_blocks_prompt_budget_before_model_call -q --basetemp .pytest_tmp
```

Expected before implementation: failure with `cross_report_analysis_validation_failed`, proving the model path was still reached.

- [x] **Step 3: Implement the orchestrator guard**

Add `_enforce_prompt_budget` in the orchestrator, log `cross_report_prompt_budget_exceeded`, and raise non-retryable `AppError` before prompt loading/model generation. Include prompt size, max size, evidence cap, request id, and operator action in the error context.

- [x] **Step 4: Expand cache fingerprint**

Include timeout, seed, and cache-enabled values in the generation-relevant config fingerprint already used inside idempotency material.

- [x] **Step 5: Verify GREEN**

Run:

```bash
pytest tests\test_cross_report_analysis_orchestrator.py::test_cross_report_orchestrator_blocks_prompt_budget_before_model_call -q --basetemp .pytest_tmp
```

Expected: pass.

### Task 3: Documentation And Backlog Cleanup

**Files:**
- Modify: `README.md`
- Modify: `crossreport.md`

- [x] **Step 1: Document cost and cache behavior**

Update the cross-report README section with config keys, cache fingerprint inputs, pre-model prompt budget behavior, artifact/log outputs, failure modes, and a link to the analytics projection foundation section.

- [x] **Step 2: Remove completed backlog items**

Remove the completed `Quality, Speed, Cost & Documentation` items from `crossreport.md` so the backlog no longer advertises implemented work.

### Task 4: Verification, Live Run, And PR

**Files:**
- No source files owned by this task.

- [x] **Step 1: Run regression checks**

Run formatting, type checks, contract schema checks, prompt fixture regression, focused unit tests, and projected-data integration tests.

- [x] **Step 2: Run live cross-report feature**

Run `python -m src.cli generate-cross-report-analysis` with real project configuration in `publish_dry_run` mode, then rerun unchanged inputs to confirm idempotency reuse.

- [x] **Step 3: Commit, push, and open PR**

Commit only the cross-report source/test/doc changes, leave unrelated ZIP deletions unstaged, push the branch, and open a GitHub PR with verification notes.
