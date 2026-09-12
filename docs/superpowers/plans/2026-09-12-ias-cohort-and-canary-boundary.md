# IAS Cohort and Canary Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the frozen representative 20-report cohort through the production queue and restore the canary runner to the repository I/O boundary.

**Architecture:** Move only canary operational filesystem, SQLite, and process work to the quality-script boundary or an existing service, leaving production workflow orchestration unchanged. Use the same queue submission and workers for every cohort member, recording each durable terminal outcome without rescue or replacement.

**Tech Stack:** Python 3.14, pytest, SQLite, existing workflow queue, existing configuration/report-store/usage services.

## Global Constraints

- Do not alter A21 telemetry, thresholds, report-processing behavior, retries, or validators before evidence shows a product defect.
- Keep the IAS command and JSON result contract stable.
- Use fresh isolated mutable state and retain all admitted cohort members in the denominator.
- Commit and push code plus retained cohort evidence only after verification.

---

### Task 1: Restore canary I/O boundaries

**Files:**
- Move: `src/orchestrators/ias_live_canary_orchestrator.py` to
  `scripts/quality/ias_live_canary_runner.py`
- Modify: `scripts/quality/run_ias_first_attempt_canary.py`
- Modify: `tests/test_ias_first_attempt_live_canary.py`

**Interfaces:**
- Preserves: `prepare_isolated_canary_run(*, runs_root: Path) -> IsolatedCanaryRun`
- Preserves: `run_ias_first_attempt_canary(...) -> dict[str, Any]`

- [ ] **Step 1: Write a failing I/O-boundary regression test**

```python
def test_ias_canary_orchestrator_has_no_direct_io_violations():
    assert _scan_role("orchestrator", ROOT / "src" / "orchestrators") == []
```

- [ ] **Step 2: Run the role-I/O gate and record the expected failure**

Run: `python -m pytest tests/test_io_boundaries.py -q`

Expected: FAIL naming `ias_live_canary_orchestrator.py` direct I/O.

- [ ] **Step 3: Move only quality-run filesystem/process work to the script or an I/O-capable service**

```python
# The production orchestrator receives prepared paths/result readers and calls
# existing queue/config/report-store/usage boundaries; Path, sqlite3,
# tempfile, and subprocess calls stay outside src/orchestrators.
```

- [ ] **Step 4: Run canary contract and I/O tests**

Run: `python -m pytest tests/test_ias_first_attempt_live_canary.py tests/test_io_boundaries.py -q`

Expected: PASS.

### Task 2: Run and summarize the frozen cohort

**Files:**
- Modify: `scripts/quality/run_ias_first_attempt_canary.py` or add a narrowly scoped adjacent quality script
- Create: ignored isolated run output under `tmp/ias-first-attempt-live-canaries/`
- Create: versioned compact cohort evidence only if the repository’s evidence policy accepts it

**Interfaces:**
- Consumes: frozen representative cohort and the stable IAS queue runner.
- Produces: one JSON result per admitted member and aggregate metrics.

- [ ] **Step 1: Add a failing provider-free test for all-member terminal accounting**

```python
def test_cohort_summary_keeps_failed_member_in_denominator():
    assert summary["typed_terminal_rate"] == 1.0
    assert summary["failure_rate"] == 0.05
```

- [ ] **Step 2: Run the test and observe the missing cohort runner**

Run: `python -m pytest tests/test_ias_first_attempt_live_canary.py -q`

Expected: FAIL until the cohort entrypoint exists.

- [ ] **Step 3: Implement the smallest queue-backed 20-member loop**

```python
for member in frozen_members:
    result = run_one_fresh_isolated_member(member)
    results.append(result)  # retain failures; no requeue or substitution
```

- [ ] **Step 4: Verify provider-free cohort accounting**

Run: `python -m pytest tests/test_ias_first_attempt_live_canary.py -q`

Expected: PASS.

- [ ] **Step 5: Run the live frozen 20-report cohort once**

Run: `python scripts/quality/<cohort-runner>.py`

Expected: compact machine-readable member results and aggregates, with every submitted member terminally classified.

### Task 3: Exact-head verification and delivery

**Files:**
- Modify: applicable workflow documentation for the boundary/cohort command

- [ ] **Step 1: Run focused and architecture checks**

Run: `python -m pytest tests/test_ias_first_attempt_live_canary.py tests/test_io_boundaries.py -q`

- [ ] **Step 2: Run aggregate CI**

Run: `python scripts/ci/run_quality_gate.py`

- [ ] **Step 3: Push exact HEAD and verify GitHub Actions**

```bash
git push origin main
gh run list --commit "$(git rev-parse HEAD)" --workflow ci.yml
```

- [ ] **Step 4: Report the SHA, retained 20-row result table, metrics, Pareto, targets, and CI state**
