# E11 Structured-Output Recovery Effectiveness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make canonical structured-output recovery outcomes measurable from retained telemetry and remove one proven, semantics-preserving malformed-JSON repair cost.

**Architecture:** Retain one terminal `structured_output_recovery_outcome` event per execution beside existing per-attempt events. It carries only bounded attribution and scalar costs/timings; the existing service remains the sole recovery owner. A read-only quality script folds legacy and new events into output-level metrics, clearly separating unknown legacy attribution from retained values.

**Tech Stack:** Python 3.12, dataclasses, structured JSON logs, pytest.

## Global Constraints

- Keep canonical schema, semantic validation, grounding, and prompt outputs unchanged.
- Preserve the existing maximum of three provider calls and fail closed for ambiguous output.
- Never retain prompts, model output, or source evidence in telemetry or reports.
- Reuse the existing `structured_output_service`; add no repair framework or dependency.

---

### Task 1: Define output-level recovery telemetry

**Files:**
- Modify: `src/services/structured_output_service.py`
- Test: `tests/test_structured_output_service.py`

**Interfaces:**
- Produces: one `structured_output_recovery_outcome` structured event per completed or terminal execution, with workflow, prompt/model family, schema, provider/model, failure reason, strategy, attempts, repair token/cost totals, and elapsed milliseconds.
- Preserves: `StructuredOutputExecutionResult` and three-call limit.

- [ ] **Step 1: Write failing service tests** for first-pass, deterministic repair, model repair, and exhaustion events, including scalar attribution and a bounded retry assertion.
- [ ] **Step 2: Run the focused test** with `python -m pytest -q tests/test_structured_output_service.py` and confirm it fails because outcome telemetry does not exist.
- [ ] **Step 3: Add the minimal terminal-event helper** and call it from every terminal branch without changing validation or retry order.
- [ ] **Step 4: Re-run the focused test** and confirm it passes.

### Task 2: Add a proven deterministic transport repair

**Files:**
- Modify: `src/utils/json_recovery.py`
- Test: `tests/test_structured_output_service.py`

**Interfaces:**
- Produces: a deterministic repair of unescaped JSON control newlines inside quoted strings only.
- Rejects: incomplete JSON, wrong types, missing fields, extra unsupported properties, and semantic-invalid payloads through existing validators.

- [ ] **Step 1: Write a failing test** whose valid schema payload differs only by a literal newline inside a JSON string and succeeds without a model-repair call.
- [ ] **Step 2: Run it** and confirm the current parser reaches model repair.
- [ ] **Step 3: Add one stateful, quote-aware control-character escaping pass** before the existing curly-quote/trailing-comma repair.
- [ ] **Step 4: Run focused recovery tests** and confirm deterministic repair succeeds while invalid/semantic-invalid cases fail closed.

### Task 3: Produce the canonical read-only effectiveness view

**Files:**
- Create: `scripts/quality/structured_output_recovery_effectiveness.py`
- Create: `tests/test_structured_output_recovery_effectiveness.py`
- Create: `docs/quality/e11-structured-output-recovery-evidence-2026-08-28.md`

**Interfaces:**
- Consumes: newline-delimited standard logs containing the existing attempt event and new terminal outcome event.
- Produces: deterministic JSON with groups by workflow, prompt/model family, schema, provider/model, failure reason, repair strategy, and retry attempt; explicit availability states; and overall outcome/cost/timing metrics.

- [ ] **Step 1: Write failing script tests** using retained-style legacy events and typed current events, asserting exact output-level rates, costs, grouping, deterministic replay, and unavailable legacy attribution.
- [ ] **Step 2: Run them** and confirm module import fails.
- [ ] **Step 3: Implement a pure event parser/aggregator and CLI** that reads only supplied files, deduplicates outcome IDs, and writes bounded JSON.
- [ ] **Step 4: Run tests and a read-only retained-log report**; record observed facts, fixture-only proof, and unavailable dimensions in the evidence document.

### Task 4: Document and close E11

**Files:**
- Modify: `docs/ops/recovery.md`
- Modify: `CONSOLIDATED_TODO.md`

- [ ] **Step 1: Document operator invocation and retained-data limitations** without duplicating the detailed evidence.
- [ ] **Step 2: Mark E11 closed only with the exact observed metrics and evidence reference.**

### Task 5: Verify, review, and publish

- [ ] **Step 1: Run focused recovery, measurement, LLM fixture, semantic/grounding, E8/E9/P15 reuse, rendering, and publish-readiness tests.**
- [ ] **Step 2: Run the configured quality suite and bounded isolated discovery → acquisition → ingest → publish workflow; remediate attributable failures.**
- [ ] **Step 3: Review diff and secrets, generate exact-HEAD release-evidence review, commit only E11 files, and push `main`.**
