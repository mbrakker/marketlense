# CI Type Gate Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use inline execution task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the repository type gate without changing browser configuration or immutable-cohort replay behavior.

**Architecture:** Narrow JSON-derived optional numeric values before converting them, and preserve the validated reused HTML path as data rather than a derived boolean. This is a local type-safety correction; no workflow or external-boundary behavior changes.

**Tech Stack:** Python 3.12, mypy, pytest.

## Global Constraints

- Preserve all unrelated worktree changes.
- Do not update the mypy baseline.
- Retain the existing fail-closed replay rules.
- Run the same type gate used by CI before push.

---

### Task 1: Type browser-worker optional numeric configuration

**Files:**

- Modify: `src/services/_browser_report_download/browser_worker.py:275-280`
- Test: `tests/test_browser_report_download_service/_test_worker_and_recovery/cases_02_lookup_submission_assist_recovers_lookup.py`

- [ ] **Step 1: Use the current CI type gate as the failing test.**

Run: `python scripts/ci/run_type_check.py`

Expected: FAIL on `_optional_int` and `_optional_float` because unchecked JSON values have static type `object`.

- [ ] **Step 2: Narrow accepted scalar types before numeric conversion.**

```python
def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray, int, float)):
        return int(value)
    raise TypeError("optional integer configuration must be numeric")
```

Use the analogous accepted scalar set for `_optional_float`.

- [ ] **Step 3: Run the worker serialization test and type gate.**

Run: `pytest tests/test_browser_report_download_service/_test_worker_and_recovery/cases_02_lookup_submission_assist_recovers_lookup.py -q` then `python scripts/ci/run_type_check.py`.

Expected: worker serialization remains green and the browser-worker errors disappear.

### Task 2: Preserve the validated reused HTML path in cohort recording

**Files:**

- Modify: `src/orchestrators/ingest_orchestrator.py:1281-1326`
- Test: `tests/test_ingest_cohort.py`

- [ ] **Step 1: Use the existing validated-replay test as the behavioral guard.**

Run: `pytest tests/test_ingest_cohort.py::test_fixed_cohort_replay_supersedes_a_failure_with_validated_reuse -q`.

Expected: PASS before refactoring; it proves a skipped `html_exists` outcome with a path closes as publish-ready.

- [ ] **Step 2: Store the validated reused HTML path, not only its truth value.**

```python
reused_validated_html_path = (
    outcome.html_path
    if outcome and outcome.status == "skipped" and outcome.error == "html_exists"
    and outcome.html_path
    else None
)
```

Use this value for both the success decision and `_record_reused_cohort_stage_closure` call.

- [ ] **Step 3: Run the replay test and full type gate.**

Run: `pytest tests/test_ingest_cohort.py::test_fixed_cohort_replay_supersedes_a_failure_with_validated_reuse -q` then `python scripts/ci/run_type_check.py`.

Expected: replay remains publish-ready and all current unbaselined type errors are removed.

### Task 3: Publish and merge the scoped CI repair

**Files:**

- Modify: only the files in Tasks 1–2 and this plan.

- [ ] **Step 1: Inspect staged diff and run `git diff --check`.**
- [ ] **Step 2: Commit only scoped files and push PR #58.**
- [ ] **Step 3: Require GitHub checks to pass, then merge PR #58.**
