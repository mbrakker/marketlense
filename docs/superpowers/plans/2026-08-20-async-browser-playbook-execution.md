# Async Browser Playbook Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute every supported deterministic browser-route playbook action through a reused asynchronous Browser Use session, with safe same-session Agent fallback on route drift.

**Architecture:** Keep `run_deterministic_browser_route_playbook` as the browser-download service boundary and preserve the existing synchronous executor as the contract authority. Replace the async subset implementation with an async page-driver adapter that exposes the same locator/action methods to `execute_browser_route_playbook`; a non-completed execution returns `None`, so the existing service handoff constructs Browser Use's Agent with the original preflight lease rather than another browser.

**Tech Stack:** Python 3.12, vendored Browser Use runtime, pytest, existing browser-route contracts and browser preflight lifecycle.

## Global Constraints

- Reuse the existing Browser Use browser and current page; do not construct, start, or serialize a second browser session.
- Support only the existing safe declarative actions: `click`, `submit`, `fill`, `type`, `select`, `navigate`, `open`, and `verify`.
- Resolve form values only through existing `${identity.<key>}` references; do not persist, infer, or guess identity values.
- Require each action's existing URL/text postcondition and return the existing fallback signal on locator, control, or postcondition drift.
- Extend existing browser-playbook test modules and existing local fake browser patterns; add no fixture assets or dependencies.
- Update the report-acquisition workflow reference and remove the matching backlog item only after fresh tests and a guarded live validation run.

---

### Task 1: Prove the async execution gap with failing behavioral tests

**Files:**
- Modify: `tests/test_browser_acquisition_cache_and_autofill.py`

**Interfaces:**
- Consumes: `run_deterministic_browser_route_playbook(...)`, `try_deterministic_browser_route_playbooks(...)`, and existing Browser Use module injection.
- Produces: regression cases for async click/download, fill/select/submit, drift, and same-session Agent handoff.

- [x] **Step 1: Write the failing click/download test**

```python
result = run_deterministic_browser_route_playbook(..., browser=async_browser, playbook=click_playbook)
assert result is not None
assert async_browser.agent_calls == 0
assert async_browser.page.clicked_selectors == ["a.download"]
```

- [x] **Step 2: Run it and verify the expected failure**

Run: `python -m pytest tests/test_browser_acquisition_cache_and_autofill.py -k async_deterministic_playbook -q`

Expected: FAIL because the current async executor rejects `click`.

- [x] **Step 3: Add the failing form and drift/handoff cases**

```python
assert async_browser.page.values["email"] == "ops@example.com"
assert async_browser.page.selected["industry"] == "retail"
assert async_browser.page.submitted is True
assert agent_browser_ids == [id(preflight_browser)]
assert browser_launches == 1
```

- [x] **Step 4: Run the focused cases and verify expected failures**

Run: `python -m pytest tests/test_browser_acquisition_cache_and_autofill.py -k async_deterministic_playbook -q`

Expected: form action and same-session fallback assertions fail because the async subset returns fallback before executing them.

### Task 2: Adapt the current Browser Use page to the existing deterministic executor

**Files:**
- Modify: `src/services/_browser_report_download/browser.py`
- Test: `tests/test_browser_acquisition_cache_and_autofill.py`

**Interfaces:**
- Consumes: `execute_browser_route_playbook(BrowserRoutePlaybookExecutionRequest, ctx)` and `resolve_effective_identity_fields(request)`.
- Produces: `_AsyncDeterministicPlaybookPageDriver` and a complete `BrowserAgentRunResult | None` from `_run_async_deterministic_browser_route_playbook(...)`.

- [x] **Step 1: Implement the minimal async page-driver action methods**

```python
execution = execute_browser_route_playbook(
    BrowserRoutePlaybookExecutionRequest(
        schema_version="1.0",
        playbook=playbook,
        normalized_url=normalized_url,
        page_driver=_AsyncDeterministicPlaybookPageDriver(browser=browser, page=page),
        identity_values=identity_values,
    ),
    ctx,
)
if execution.status != "completed":
    return None
```

The adapter implements CSS, text, role/name, label, `name`, and data-attribute operations with the same DOM expressions as the synchronous driver, checks supported select controls/options, and awaits only the reused browser/page methods.

- [x] **Step 2: Run the focused async playbook cases**

Run: `python -m pytest tests/test_browser_acquisition_cache_and_autofill.py -k async_deterministic_playbook -q`

Expected: PASS; successful deterministic cases make zero Agent calls and drift cases preserve the original browser identity for Agent construction.

- [x] **Step 3: Refactor shared result construction only if it removes duplicate behavior without changing output**

Run: `python -m pytest tests/test_browser_acquisition_cache_and_autofill.py -k "deterministic_playbook or async_deterministic_playbook" -q`

Expected: PASS with sync behavior unchanged.

### Task 3: Document, validate, and integrate the completed behavior

**Files:**
- Modify: `docs/workflows/report-acquisition.md`
- Modify: `CONSOLIDATED_TODO.md`
- Modify: `docs/superpowers/plans/2026-08-20-async-browser-playbook-execution.md`

**Interfaces:**
- Consumes: passing focused suite and guarded integration/live workflow evidence.
- Produces: current operator documentation, completed-backlog state, and a scoped commit on `main`.

- [x] **Step 1: Update the acquisition workflow reference**

Document that the async preflight handoff runs the same declarative deterministic action set against the existing Browser Use page, requires action-level URL/text postconditions, and falls through to an Agent on the same browser state for any drift.

- [x] **Step 2: Run focused and affected regression checks**

Run: `python -m pytest tests/test_browser_route_playbooks.py tests/test_browser_acquisition_cache_and_autofill.py tests/test_browser_report_download_service -q`

Expected: PASS.

- [x] **Step 3: Run the guarded real Browser Use integration**

Run: `$env:RUN_BROWSER_DOWNLOAD_INTEGRATION='1'; python -m pytest tests/integration/test_browser_report_download_service.py::test_browser_report_download_service_local_guarded -m integration -q`

Expected: a real configured provider/browser invocation passes or reports its exact unavailable prerequisite without treating it as success.

- [ ] **Step 4: Run the repository-safe discovery-to-publish validation workflow**

Discover the current isolated no-publication command/profile from repository configuration, execute discovery, acquisition, ingest, and guarded publish in order, and rerun the affected/downstream stages after any attributable error.

Outcome: the configured isolated profile was prepared with the committed publisher
snapshot (83 publishers), then stopped at its intended
`publisher_inventory_google_folder_parent_missing` guard because no Drive parent
is configured. The profile permits zero WordPress writes, so acquisition, ingest,
and publish cannot be truthfully marked as executed without external configuration
authority.

- [x] **Step 5: Remove the matching completed backlog item, verify scope, commit, and merge**

Run: `git diff --check; git status --short; git diff -- src/services/_browser_report_download/browser.py tests/test_browser_acquisition_cache_and_autofill.py docs/workflows/report-acquisition.md CONSOLIDATED_TODO.md`

Expected: only scoped changes, no secrets, and fresh verification evidence before `git add`, `git commit`, and the requested integration into `main`.

## Self-Review

- Spec coverage: Tasks 1–2 cover every requested action, locator family, identity-only value resolution, postconditions, zero-Agent deterministic success, drift, and same-session fallback. Task 3 covers documentation, the requested real validation, backlog removal, commit, and merge.
- Placeholder scan: no placeholders remain; each implementation and verification step names concrete files, commands, or interface calls.
- Type consistency: the plan retains the existing `BrowserRoutePlaybookExecutionRequest`, `BrowserAgentRunResult | None`, and `execute_browser_route_playbook` interfaces without adding a public contract.
