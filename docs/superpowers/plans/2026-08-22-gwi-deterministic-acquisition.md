# GWI Deterministic Acquisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reliably acquire the four retained failed GWI reports through their observed deterministic form routes, without weakening artifact verification or form-value safety.

**Architecture:** Replace the historical narrative GWI playbook with selector-backed executable routes for the two observed page states. Retain the existing standard-form and artifact verification boundaries; add only the configuration and tests needed to select required identity values and verify the intermediate or terminal state.

**Tech Stack:** Python 3, PyYAML route playbooks, pytest, Playwright CLI, existing isolated acquisition replay.

## Global Constraints

- Reuse the frozen four-report GWI cohort; do not substitute a different report.
- Do not run discovery, ingest, analysis, generation, publishing, or WordPress.
- A submitted form is not a verified acquisition; preserve canonical confirmation/direct-PDF verification.
- Never guess a required select value; use only configured identity values confirmed against rendered options.

---

### Task 1: Establish executable GWI routes

**Files:**

- Modify: `tests/test_browser_route_playbooks.py`
- Modify: `src/playbooks/browser_routes/learned-www-gwi-com-browser-email-form.yaml`

**Interfaces:**

- Consumes: `load_browser_route_playbooks()` and `execute_browser_route_playbook()`.
- Produces: active GWI routes in which every step has a supported action, locator, and URL/text postcondition.

- [ ] **Step 1: Write the failing test**

```python
def test_gwi_route_playbook_is_fully_deterministic() -> None:
    playbook = _load_playbook("learned-www-gwi-com-browser-email-form")
    assert all(step.selector_type and step.selector for step in playbook.steps)
    assert all(step.action in {"navigate", "click", "fill", "select", "submit", "verify"} for step in playbook.steps)
```

- [ ] **Step 2: Run test to verify it fails**

Run `pytest tests/test_browser_route_playbooks.py::test_gwi_route_playbook_is_fully_deterministic -q`; it must fail because the current GWI playbook has narrative steps.

- [ ] **Step 3: Write minimal implementation**

Use only selectors, controls, exact options, and postconditions observed through Playwright. Represent form values with `${identity.<key>}`. Split page states into separate playbooks if a single ordered route would be unsafe.

- [ ] **Step 4: Run test to verify it passes**

Run `pytest tests/test_browser_route_playbooks.py::test_gwi_route_playbook_is_fully_deterministic -q`; it must pass.

- [ ] **Step 5: Commit**

Commit the test and executable playbook with message `fix: execute GWI acquisition form route`.

### Task 2: Preserve safe Company-size resolution

**Files:**

- Modify: `src/config/browser_download_identity.yaml`
- Modify: `tests/test_browser_download_helpers.py`

**Interfaces:**

- Consumes: publisher-specific `BrowserDownloadIdentityField` overrides and rendered native select options.
- Produces: an exact GWI Company-size value/alias verified against the page, without default or fuzzy selection.

- [ ] **Step 1: Write the failing test**

```python
def test_gwi_company_size_override_matches_observed_native_option() -> None:
    field = _effective_identity_field("https://www.gwi.com/reports/ad-targeting-media-planning", "company_size")
    assert field.value == "<observed option>"
```

- [ ] **Step 2: Run test to verify it fails**

Run `pytest tests/test_browser_download_helpers.py -k gwi_company_size -q`; it must fail because the configured value did not resolve in the retained GWI browser run.

- [ ] **Step 3: Write minimal implementation**

Replace only the GWI publisher override's Company-size value or aliases with the exact visible option from Task 1. Do not change a global default or another publisher override.

- [ ] **Step 4: Run test to verify it passes**

Run `pytest tests/test_browser_download_helpers.py -k gwi_company_size -q`; it must pass.

- [ ] **Step 5: Commit**

Commit the exact GWI identity override and test with message `fix: match GWI required company-size option`.

### Task 3: Validate the retained GWI cohort

**Files:**

- Create: `docs/CTO_evidence/gwi_acquisition_validation_<timestamp>/`
- Modify: `docs/workflows/report-acquisition.md`

**Interfaces:**

- Consumes: frozen failure manifest and the existing per-candidate isolated replay.
- Produces: a retained four-report result table with route, terminal result, verification, Agent use, tokens, cost, and duration.

- [ ] **Step 1: Run focused regressions**

Run `pytest tests/test_browser_route_playbooks.py tests/test_browser_download_helpers.py tests/test_browser_acquisition_cache_and_autofill.py -q`; it must pass.

- [ ] **Step 2: Run the GWI-only isolated acquisition replay**

Use the remediation script and only candidate IDs `fac_3e630244e5c22fe8fa787255`, `fac_4da62bac17be2e7185090695`, `fac_c0e4c925c1ed4ce6149711b8`, and `fac_6f994caaf9a413e4038f18f1`. Retain configuration, manifest, commit SHA, and results under a new CTO evidence directory.

- [ ] **Step 3: Verify outcomes**

Use the normal artifact or email-confirmation verifier. Failed results remain in the denominator and are recorded without replacement.

- [ ] **Step 4: Update current documentation**

Document that GWI form variants need executable selector-backed routes and canonical terminal verification; unknown required enums remain blockers.

- [ ] **Step 5: Commit**

Commit the documentation and retained evidence with message `docs: retain GWI acquisition validation`.
