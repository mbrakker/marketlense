# Pre-LLM Browser Form Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete configured standard browser email forms deterministically before constructing Browser Use, while preserving terminal verification and typed safety blockers.

**Architecture:** Keep DOM interaction in the canonical browser service helper. The browser runner converts a deterministic unknown-required-value result into the existing structured browser result and only escalates runtime/drift failures to Browser Use. Finalization remains the single existing terminal-evidence authority.

**Tech Stack:** Python, browser-use/CDP helper JavaScript, pytest.

## Global Constraints

- Only configured identity or policy-authorized consent values may be entered.
- Required unknown fields must remain typed blockers; no generated or first-option values.
- Browser Use is constructed only after deterministic handling cannot safely complete the form.
- Existing terminal verification decides whether a deterministic submit is accepted.
- Reuse the existing browser runtime, identity, helper, artifact-finalization, and test infrastructure.

---

### Task 1: Specify deterministic results

**Files:**
- Modify: `tests/test_browser_acquisition_cache_and_autofill.py`
- Modify: `src/services/_browser_report_download/_helpers/interaction.py`
- Modify: `src/services/_browser_report_download/browser.py`

**Interfaces:**
- Produces `BrowserHelperStandardFormSubmitResult` with an explicit typed unknown-required-field blocker.
- Consumes `BrowserReportDownloadRequest` and configured effective identity fields.

- [ ] Add a failing browser-run test proving a verified standard submit does not instantiate a Browser Use model client and retains actual terminal HTML.
- [ ] Run the focused test and confirm it fails because the deterministic early return lacks terminal evidence.
- [ ] Add a failing browser-run test proving an unresolved required configured/unknown select returns `blocked_unknown_required_enum` without constructing a model client.
- [ ] Run the focused test and confirm it fails because the current implementation escalates to Browser Use.
- [ ] Make the minimal helper/runner changes: classify observed unresolved required controls as a typed blocker; capture the real post-submit terminal snapshot; leave failed/unsupported helper execution as the Browser Use fallback.
- [ ] Re-run focused tests and confirm both pass.

### Task 2: Preserve existing terminal authority and document behavior

**Files:**
- Modify: `tests/test_browser_acquisition_cache_and_autofill.py`
- Modify: `docs/workflows/report-processing.md`
- Modify: `CONSOLIDATED_TODO.md`

**Interfaces:**
- Consumes deterministic raw structured result and `finalize_browser_report_download_result`.
- Produces verified email delivery only through existing terminal confirmation evidence.

- [ ] Add a failing finalization test proving a submit with no terminal confirmation is not classified as verified email delivery.
- [ ] Run it and confirm it fails only if the deterministic path fabricates confirmation flags.
- [ ] Ensure the deterministic raw result reflects the actual terminal state rather than fabricated URL/form signals; update the workflow documentation to prohibit guessed select values and describe fallback/blocker behavior.
- [ ] Remove the delivered backlog item only after targeted and live validation evidence is retained.
- [ ] Run the browser form regression suite and record exact results.

### Task 3: Verify, live validate, and integrate

**Files:**
- Modify: no source files unless validation exposes an attributable defect.

- [ ] Inspect `git diff --check`, secret exposure, and focused changes.
- [ ] Run the configured discovery → acquisition → ingest → publish validation profile with safe/no-publication controls and real configured provider/browser calls.
- [ ] If an attributable error occurs, add a reproducing test, fix it, then rerun affected and downstream stages.
- [ ] Run the relevant fast regression/quality commands, commit the intentional diff, and merge only after all required evidence is fresh.
