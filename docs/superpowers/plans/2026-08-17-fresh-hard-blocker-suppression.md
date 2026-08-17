# Fresh Hard-Blocker Suppression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Suppress an eligible fresh, exact, verified terminal browser blocker before browser preflight without weakening TTL, policy, revalidation, or manual CAPTCHA-handoff safeguards.

**Architecture:** Keep the decision in the report-download orchestrator, where route memory, runtime route policy, and CAPTCHA handoff configuration are already available. A small deterministic helper will require exact, fresh, verified, evidence-backed blockers that are permitted by the current suppression policy; the workflow will record avoided browser/model work and return its existing typed suppression error before the route planner or browser service is invoked.

**Tech Stack:** Python 3, dataclasses, pytest, SQLite-backed existing route history and resource telemetry.

## Global Constraints

- Reuse the existing route-memory TTL, route-suppression policy, typed `AppError`, resource telemetry, and manual CAPTCHA handoff contracts.
- No new dependencies, persistence schema, fixture data, browser automation, or model calls for the deterministic regression tests.
- Update `docs/workflows/report-acquisition.md` and remove the completed backlog entry only after fresh verification and live validation evidence.

---

### Task 1: Define exact hard-blocker eligibility

**Files:**
- Modify: `tests/test_report_download_route_memory_ttl.py`
- Modify: `src/orchestrators/_report_download_orchestrator/workflow.py`

**Interfaces:**
- Consumes: `PublisherDownloadRouteResponse`, `BrowserDownloadRouteSuppressionPolicy`, `BrowserDownloadCaptchaHandoffPolicy`, and `revalidate_route_policy`.
- Produces: `_fresh_remembered_hard_blocker_suppression_reason(...) -> str | None`.

- [x] **Step 1: Write failing tests**

```python
assert _fresh_remembered_hard_blocker_suppression_reason(
    fresh_verified_exact_blocker, ttl_seconds=120, policy=policy,
    captcha_handoff_policy=disabled_handoff, revalidate_route_policy=False,
    now_seconds=1_000,
) == "fresh_remembered_blocked_email_domain"

assert _fresh_remembered_hard_blocker_suppression_reason(
    stale_or_weak_or_policy_incompatible_blocker, ttl_seconds=120,
    policy=policy, captcha_handoff_policy=disabled_handoff,
    revalidate_route_policy=False, now_seconds=1_000,
) is None
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_download_route_memory_ttl.py -q`

Expected: FAIL because `_fresh_remembered_hard_blocker_suppression_reason` is not defined.

- [x] **Step 3: Write minimal implementation**

```python
def _fresh_remembered_hard_blocker_suppression_reason(... ) -> str | None:
    # Require current policy, exact fresh route memory, verified blocked terminal
    # evidence, and a matching enabled blocker class.  CAPTCHA handoff wins.
    ...
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_report_download_route_memory_ttl.py -q`

Expected: PASS.

### Task 2: Stop before route planning/browser preflight

**Files:**
- Modify: `tests/_test_report_download_orchestrator/cases_03_run_report_download_is_idempotent.py`
- Modify: `src/orchestrators/_report_download_orchestrator/workflow.py`

**Interfaces:**
- Consumes: eligibility reason from Task 1.
- Produces: `AppError(code="report_download_route_suppressed")` plus the existing resource summary with `browser_launch` and `browser_model_call` avoided.

- [x] **Step 1: Write failing test**

```python
with pytest.raises(AppError, match="suppressed"):
    run_report_download(request, ctx=ctx, dependencies=deps)
assert browser_download_calls == []
assert mailbox_preflight_calls == []
assert suppression_evaluation_calls == []
assert recorded_summary.avoided_operations == ("browser_launch", "browser_model_call")
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/_test_report_download_orchestrator/cases_03_run_report_download_is_idempotent.py -q`

Expected: FAIL because the browser dependency is still called.

- [x] **Step 3: Write minimal implementation**

```python
reason = _fresh_remembered_hard_blocker_suppression_reason(...)
if reason is not None:
    record_acquisition_resource_summary(..., terminal_reason=reason,
        avoided_operations=("browser_launch", "browser_model_call"))
    raise AppError(code="report_download_route_suppressed", ...)
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/_test_report_download_orchestrator/cases_03_run_report_download_is_idempotent.py -q`

Expected: PASS.

### Task 3: Document and validate the controlled behavior

**Files:**
- Modify: `docs/workflows/report-acquisition.md`
- Modify: `CONSOLIDATED_TODO.md`

**Interfaces:**
- Consumes: validated implementation and the repository’s existing live validation profile.
- Produces: current operational documentation and a removed completed backlog item.

- [x] **Step 1: Update documentation**

Describe the pre-browser exact-blocker check, required evidence, TTL/current-policy/revalidation guards, and CAPTCHA-handoff exception.

- [x] **Step 2: Run focused and affected regression tests**

Run: `pytest tests/test_report_download_route_memory_ttl.py tests/_test_report_download_orchestrator/cases_03_run_report_download_is_idempotent.py tests/test_acquisition_resource_telemetry.py -q`

Expected: PASS.

- [x] **Step 3: Run the approved live validation workflow**

Discover the repository command/profile from `docs/quality/testing.md` and execute the safe discovery → acquisition → ingest → publish validation flow using retained artifacts and configured live credentials. Capture actual browser/model-use evidence and investigate every attributable error.

- [ ] **Step 4: Remove the completed backlog item and commit**

Remove only the exact completed task entry from `CONSOLIDATED_TODO.md`; inspect the final diff, run the targeted checks again, commit the scoped change, and merge only if the repository’s current-branch merge workflow permits it.
