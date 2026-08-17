# Private API Before Browser Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attempt selected, validated private-API playbooks before browser preflight or Browser Use while retaining strict validation and normal fallback.

**Architecture:** `download_report_with_browser_use` remains the canonical acquisition boundary. It selects existing playbooks immediately before the private-API attempt; a verified result returns through the existing finalizer, and every rejection continues through the unchanged browser budget, runtime validation, preflight, deterministic-playbook, and Browser Use flow.

**Tech Stack:** Python 3.12, pytest, existing HTTP acquisition service, Browser Use, existing browser-route playbook contracts.

## Global Constraints

- Do not weaken promotion thresholds, evidence validation, status/marker/JSON-pointer/PDF checks, or stale-playbook policy.
- Do not add fixtures: extend the existing private-API playbook regression coverage and helpers.
- A successful private-API route must create no browser preflight session and make no Browser Use call.
- A rejected private-API route must preserve normal browser acquisition fallback.
- Use the existing isolated profile for live validation; do not publish or create uncontrolled external writes.

---

### Task 1: Prove required ordering and fallback

**Files:**

- Modify: `tests/test_browser_report_download_service/test_private_api_playbook.py`

**Interfaces:**

- Consumes: `download_report_with_browser_use(request, ctx)` and the retained private-API playbook helper.
- Produces: regressions asserting successful HTTP acquisition avoids browser import/preflight and stale API evidence falls through to Browser Use.

- [x] **Step 1: Write a failing successful-private-API ordering test**

```python
assert response.outcome == "downloaded"
assert browser_preflight_calls == 0
assert browser_use_runtime_calls == 0
```

- [x] **Step 2: Run the targeted test and observe the pre-change failure**

Run: `python -m pytest tests/test_browser_report_download_service/test_private_api_playbook.py -q`

Expected: the ordering assertion fails because private-API execution occurs after browser preflight.

- [x] **Step 3: Keep the stale/status-rejection fallback test and assert browser execution remains reachable**

```python
assert browser_preflight_calls == 1
assert full_agent_loaded["value"] is True
assert response.outcome == "downloaded"
```

- [x] **Step 4: Re-run the targeted module after implementation**

Run: `python -m pytest tests/test_browser_report_download_service/test_private_api_playbook.py -q`

Expected: PASS.

### Task 2: Move only the ordering boundary

**Files:**

- Modify: `src/services/browser_report_download_service.py`

**Interfaces:**

- Consumes: `attach_browser_route_playbooks(...)` and `try_private_api_playbook_download(...)`.
- Produces: a completed private-API result before `apply_browser_route_budget`, `validate_browser_runtime_settings`, and `try_browser_preflight_probe_with_session`.

- [x] **Step 1: Attach existing route playbooks before the private-API attempt**

```python
request = attach_browser_route_playbooks(request=request, ctx=ctx, normalized_url=normalized_url)
private_api_result = try_private_api_playbook_download(...)
if private_api_result is not None:
    return _complete_browser_download_result(...)
```

- [x] **Step 2: Delete the former post-preflight private-API attempt without changing its implementation**

```python
# No private-API execution remains after browser preflight.
```

- [x] **Step 3: Run focused regression coverage**

Run: `python -m pytest tests/test_browser_report_download_service/test_private_api_playbook.py tests/test_browser_report_download_service/test_browser_preflight.py -q`

Expected: PASS.

### Task 3: Document and verify maintained behavior

**Files:**

- Modify: `docs/workflows/report-processing.md`
- Modify: `src/playbooks/browser_routes/README.md`

**Interfaces:**

- Produces: documentation that private-API validation runs before browser preflight/browser launch and rejected evidence preserves browser fallback.

- [x] **Step 1: Update the acquisition workflow and playbook guide**

```markdown
Selected private-API playbooks run before browser preflight. Only a fully validated PDF result suppresses browser work; every validation rejection uses the existing normal acquisition fallback.
```

- [x] **Step 2: Run affected tests and static validation**

Run: `python -m pytest tests/test_browser_report_download_service tests/test_browser_route_playbooks.py -q; python -m ruff check src/services/browser_report_download_service.py tests/test_browser_report_download_service/test_private_api_playbook.py`

Expected: changed test passes lint; any pre-existing service-file lint baseline is recorded separately and left outside this surgical change.

- [x] **Step 3: Run the repository-required isolated live sequence**

Run the current configured bounded discovery, acquisition, ingest, and guarded non-publishing publish stages with real provider/API calls where available. Inspect run resource telemetry and retained validation evidence; record `unavailable` only where an external prerequisite blocks the stage.

- [x] **Step 4: Review and integrate**

Run `git diff --check`, inspect the scoped diff and `git status --short`, verify no open matching backlog item remains, commit the scoped changes, then fast-forward merge only if all evidence passes.
