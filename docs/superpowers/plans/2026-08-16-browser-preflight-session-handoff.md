# Browser Preflight Session Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the browser instance opened by preflight when acquisition escalates to Browser Use, while retaining current acquisition outcomes and cleanup guarantees.

**Architecture:** The browser-download service remains the canonical acquisition boundary. Preflight will return a process-local lease for a live browser only on an escalation path; the Browser Use runner consumes that lease in-process and owns its final cleanup/accounting. A successful preflight closes its lease after the direct download and never constructs an agent.

**Tech Stack:** Python 3.12, browser-use, pytest, existing browser acquisition contracts and lifecycle helpers.

## Global Constraints

- Preserve all existing result contracts, terminal verification, artifact handoff, and route-policy behavior.
- Reuse the existing browser profile/session-reuse lifecycle and browser shutdown helpers.
- Do not serialize a live browser object into contracts or worker payloads.
- The handoff path must bypass the subprocess worker because an in-memory browser cannot cross the process boundary.
- The test suite must prove one browser construction and session continuity on escalation, plus no Browser Use invocation on successful preflight.

---

### Task 1: Add failing preflight lifecycle regression tests

**Files:**
- Modify: `tests/test_browser_report_download_service/test_browser_preflight.py`

**Interfaces:**
- Consumes: `download_report_with_browser_use(request, ctx)`.
- Produces: regression evidence for direct preflight success and preflight-to-agent session continuity.

- [x] **Step 1: Write the failing tests**

```python
def test_browser_preflight_success_does_not_construct_browser_use_agent(...):
    response = service.download_report_with_browser_use(request, run_context)
    assert response.outcome == "downloaded"
    assert agent_calls == 0


def test_browser_preflight_escalation_reuses_the_open_browser_session(...):
    response = service.download_report_with_browser_use(request, run_context)
    assert response.outcome == "downloaded"
    assert browser_construction_count == 1
    assert agent_browser_ids == preflight_browser_ids
    assert agent_observed_cookie == "session=retained"
```

- [x] **Step 2: Run the focused test module to verify failure**

Run: `python -m pytest tests/test_browser_report_download_service/test_browser_preflight.py -q`

Expected: the escalation assertion fails because preflight stops its browser and the agent creates another instance.

### Task 2: Transfer and clean up the browser lease

**Files:**
- Modify: `src/services/_browser_report_download/preflight.py`
- Modify: `src/services/_browser_report_download/browser.py`
- Modify: `src/services/browser_report_download_service.py`
- Modify: `docs/workflows/report-acquisition.md`
- Test: `tests/test_browser_report_download_service/test_browser_preflight.py`

**Interfaces:**
- Consumes: the existing `BrowserPreflightProbeResponse`, browser session-reuse policy, and `run_browser_report_download_agent`.
- Produces: a process-local preflight lease passed only to the in-process Browser Use invocation, with exactly one owner responsible for shutdown and launch accounting.

- [x] **Step 1: Implement the smallest handoff**

```python
browser_run = run_browser_report_download_agent(
    request=request,
    ctx=ctx,
    normalized_url=normalized_url,
    execution_url=execution_url,
    download_dir=download_dir,
    prompt_bundle=prompt_bundle,
    preflight_session=browser_preflight_response.session,
)
```

Keep the live browser out of the persisted response; close it in the service when an escalated branch returns before Browser Use, and let the runner close it after the agent has completed or failed.

- [x] **Step 2: Run focused tests to verify green**

Run: `python -m pytest tests/test_browser_report_download_service/test_browser_preflight.py -q`

Expected: PASS, including exactly one launch/session handoff and direct preflight short-circuit coverage.

- [x] **Step 3: Update the current workflow documentation**

Document that eligible browser preflight retains its browser only for an escalated Browser Use attempt; direct preflight results close without an agent.

- [x] **Step 4: Run broader affected validation**

Run: `python -m pytest tests/test_browser_report_download_service tests/test_browser_report_download_runtime_decomposition.py tests/test_browser_acquisition_cache_and_autofill.py tests/test_browser_route_budgets.py -q`

Expected: PASS with acquisition contracts and browser lifecycle behavior unchanged outside the handoff.

- [x] **Step 5: Run the approved isolated live validation sequence**

Run the repository’s configured bounded discovery, acquisition, ingest, and guarded publish commands against existing retained/live state; retain the resulting IDs and resource telemetry. Confirm the acquisition event envelope records one browser launch on a forced escalation.

- [x] **Step 6: Review, commit, and integrate**

Run `git diff --check`, inspect `git diff --check` and `git diff -- <changed files>`, then commit only the scoped files. Merge the completed branch only after all validation commands pass.
