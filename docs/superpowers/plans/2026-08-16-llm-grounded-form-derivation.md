# LLM-Grounded Form Derivation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve a required standard-form choice with one bounded model call only when the answer is grounded in configured identity values and a live visible option.

**Architecture:** The browser service keeps deterministic handling first. When it receives the existing typed unknown-required-field blocker, it captures the visible required control labels/options, asks the canonical LLM service to map configured identity evidence to one exact observed option, validates that the returned option is observed and supported by the cited configured field, then reuses the existing deterministic helper to fill and submit. Invalid, unsupported, or unavailable model answers preserve the typed blocker; unsupported DOM/runtime errors still use the Browser Use fallback.

**Tech Stack:** Python, existing LLM service and usage ledger, prompt service, Browser Use/CDP helpers, pytest.

## Global Constraints

- Only configured identity values may ground the selected form option; no generated identity data.
- The model must return a single exact option from the live form plus its configured evidence key/value.
- Code validates model schema, configured evidence, and observed option membership before form interaction.
- At most one bounded derivation call occurs per deterministic form attempt.
- Existing terminal verification remains the only success authority.
- Existing Browser Use fallback remains available only for DOM/runtime drift, not for unresolved identity guesses.

---

### Task 1: Specify safe model-derived selection

**Files:**

- Modify: `tests/test_browser_acquisition_cache_and_autofill.py`
- Modify: `src/services/_browser_report_download/browser.py`

**Interfaces:**

- Consumes `BrowserHelperStandardFormSubmitResult.unresolved_fields`, configured identity entries, and form-option evidence.
- Produces an additional authorized identity field only when its value exactly matches a visible required option.

- [x] **Step 1: Write failing tests**

```python
def test_pre_llm_form_uses_grounded_llm_choice_for_required_select(...):
    # configured company profile supports one observed Industry option
    # assert one derivation request, deterministic submit, and no Browser Use agent

def test_pre_llm_form_rejects_uncited_or_unobserved_llm_choice(...):
    # model returns a choice not present in the observed options
    # assert typed blocker and no field submission
```

- [x] **Step 2: Run the focused tests and observe RED**

Run: `python -m pytest tests/test_browser_acquisition_cache_and_autofill.py -q`

- [x] **Step 3: Implement the minimal derivation boundary**

Use a canonical `OpenAIJSONPromptRequest` and `llm_service.openai_chat_json`; accept only a parsed object with `field_label`, `option_value`, `evidence_key`, and exact configured `evidence_value`. Pass only configured identity entries and observed label/option evidence. Re-run the existing standard-form helper with the validated derived entry.

- [x] **Step 4: Run the focused tests and observe GREEN**

Run: `python -m pytest tests/test_browser_acquisition_cache_and_autofill.py -q`

### Task 2: Document, validate, and integrate

**Files:**

- Modify: `docs/workflows/report-processing.md`
- Modify: `docs/superpowers/plans/2026-08-16-llm-grounded-form-derivation.md`

- [x] **Step 1: Document the grounding and validation boundary**

Describe the one-call cap, configured-evidence-only rule, observed-option validation, blocker preservation, and terminal verification.

- [x] **Step 2: Run regression and live validation**

Run the affected browser suite and a safe real Browser Use local-form canary that uses an allowed provider call to select a configured-data-derived option. Confirm the usage ledger records one derivation call and zero Browser Use agent calls.

- [x] **Step 3: Inspect and integrate**

Run `git diff --check`, targeted Ruff, inspect the final diff for secrets, commit the intentional changes, and merge after fresh evidence.

## Execution evidence

- The original helper test failed before `unresolved_options` existed, then passed
  after the observed-option contract was added.
- The forced live browser route initially preserved its typed blocker when the
  120-token model cap exhausted before JSON output. The bounded cap was raised
  to 400 tokens and the strict schema was made consistent with the empty
  no-selection response.
- The rerun (`live-derived-form-v4`) completed the real local browser route
  with a verified terminal confirmation. Its usage ledger recorded exactly one
  valid `browser_report_download:form_value_derivation` call (320 input, 238
  output, 558 total tokens) and zero Browser Use model calls.
