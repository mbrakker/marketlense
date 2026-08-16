# Pre-LLM Terminal Verification Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return from deterministic browser-email-form handling only after existing terminal evidence verifies the submit; otherwise retain the same live browser for Browser Use.

**Architecture:** The browser runner remains the sole browser lifecycle owner. The pre-LLM helper captures the post-submit terminal snapshot and evaluates it with the canonical confirmation-evidence rules. Typed unknown-identity blockers still return immediately, while failed, ambiguous, or unverified submits return `None` and let the outer runner construct Browser Use against the existing session.

**Tech Stack:** Python, existing Browser Use runtime, terminal-evidence classifier, pytest.

## Global Constraints

- A verified deterministic email submit constructs no Browser Use agent.
- Unknown required identity values remain typed blockers and never submit a guessed value.
- An unverified submit never causes a second form submit before Browser Use takes over.
- The handed-off preflight browser is not killed or replaced by deterministic handling.

---

### Task 1: Prove terminal-gated handoff behavior

**Files:**

- Modify: `tests/test_browser_report_download_service/test_browser_preflight.py`
- Modify: `src/services/_browser_report_download/browser.py`

**Interfaces:**

- Consumes: `BrowserHelperStandardFormSubmitResult` and `TerminalSnapshot`.
- Produces: `BrowserAgentRunResult` only when canonical confirmation evidence verifies email delivery; otherwise `None` for the existing Browser Use fallback.

- [x] **Step 1: Cover verified success, typed blockers, and async fallback**

```python
def test_pre_llm_form_autofill_submits_without_model_client(...):
    # assert no Agent construction, exactly one submit, and verified output

def test_pre_llm_form_autofill_returns_unknown_required_value_blocker(...):
    # assert no guessed select and no Agent construction

def test_async_unverified_deterministic_submit_preserves_preflight_browser_for_agent(...):
    # assert one browser, one deterministic submit, then Agent receives same cookie/page state
```

- [x] **Step 2: Run the three tests and verify the unverified-submit case fails**

Run: `python -m pytest tests/test_browser_report_download_service/test_browser_preflight.py -k "async_.*deterministic" -q`

Expected: the unverified submit currently returns before Agent construction.

- [x] **Step 3: Gate deterministic early return on canonical terminal verification**

Build confirmation evidence from the helper submission and captured terminal snapshot, then call the existing email-delivery verifier. Preserve blocker return behavior. For every non-verified result, log escalation and return `None`; do not call browser shutdown or construct another browser.

- [x] **Step 4: Re-run the focused tests and verify green**

Run: `python -m pytest tests/test_browser_report_download_service/test_browser_preflight.py -k "async_.*deterministic" -q`

Expected: verified success avoids Agent, blocker remains typed, and unverified submit reaches Agent with the retained browser.

### Task 2: Validate and integrate

**Files:**

- Modify: `docs/workflows/report-processing.md`

- [x] **Step 1: Document terminal-gated handoff**

State that the deterministic helper retains the preflight browser on every fallback and only returns success after canonical terminal verification.

- [x] **Step 2: Run affected regression and controlled live browser validation**

Run the browser preflight/form suites plus the repository's guarded live Browser
Use integration. Confirm one browser lifecycle in the async handoff regression,
terminal success without Browser Use, fallback session continuity for an
unverified submit, and real Browser Use/provider compatibility on the existing
safe local route.

- [x] **Step 3: Inspect, commit, and integrate**

Run formatting, lint, docs, contract, and diff checks. Commit scoped files and merge after fresh validation evidence.

## Execution evidence

- The submitted-but-unverified async form case failed before the gate because
  it returned `email_required` without constructing Browser Use; it passed
  after the gate forwarded the same browser object, cookies, storage marker,
  and transient HTML to the agent.
- Focused form/preflight/helper coverage passed (`30 passed`), and the broader
  affected browser surface passed (`173 passed`).
- The guarded live Browser Use integration passed against its existing local,
  non-publishing route in `54.65s` after exposing the repository's vendored
  Browser Use path to the test process. It made the bounded real provider call
  and reported only known upstream deprecation/reconnect teardown diagnostics.
