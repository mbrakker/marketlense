# Codex Review Follow-Ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the reproducible `chatgpt-codex-connector` review findings without expanding external side effects or changing successful workflow costs.

**Architecture:** Keep private-API candidate promotion as optional report-download orchestration, so ledger or promotion-marker persistence failures are logged and do not undo successful acquisition. Keep cross-report validation and selection within the existing contract/service/generator boundary: services preserve category IDs and publication-period dates, while generators consume the explicit contract fields.

**Tech Stack:** Python dataclasses, SQLite integration fixtures, pytest, existing structured `AppError` and logging utilities.

---

### Task 1: Optional Private-API Promotion Bookkeeping

**Files:**
- Modify: `tests/test_report_download_orchestrator.py`
- Modify: `src/orchestrators/_report_download_orchestrator/promotions.py`

- [x] **Step 1: Write failing orchestration regression tests**

Add tests that inject `ReportDownloadDependencies` whose external report-store callback raises a typed `AppError` from `record_publisher_private_api_candidate_observation` or `mark_publisher_private_api_candidate_promoted`. Each test must call the promotion evaluator and assert a structured event carrying `candidate_observation_app_error` or `promotion_mark_app_error`.

- [x] **Step 2: Prove red behavior**

Run: `py -3.12 -m pytest tests/test_report_download_orchestrator.py -k "private_api and app_error" -q`

Expected before implementation: both new tests fail because the report-store `AppError` escapes.

- [x] **Step 3: Make promotion bookkeeping fail-soft**

Wrap only the optional ledger-record and post-promotion marker callbacks in `try/except AppError`, logging `error_code` and `error_retryable` through `_log_private_api_promotion_event(...)` and continuing without raising:

```python
try:
    record = dependencies.record_publisher_private_api_candidate_observation(...)
except AppError as exc:
    _log_private_api_promotion_event(
        ctx=ctx,
        fields={**fields, "skip_reason": "candidate_observation_app_error",
                "error_code": exc.code, "error_retryable": exc.retryable},
    )
    continue
```

- [x] **Step 4: Prove green behavior**

Run: `py -3.12 -m pytest tests/test_report_download_orchestrator.py -k "private_api" -q`

Expected after implementation: the normal promotion path and both failure paths pass.

### Task 2: Cross-Report Validation and Configuration Gates

**Files:**
- Modify: `tests/test_cross_report_analysis_contracts.py`
- Modify: `tests/test_config_service.py`
- Modify: `src/contracts/cross_report_analysis.py`
- Modify: `src/services/_config_service/cross_report_analysis.py`

- [x] **Step 1: Write failing validation tests**

Add contract tests asserting `{}`, `[]`, and a scalar fail with `AppError(code="cross_report_contract_invalid")`. Add public config-load tests asserting explicit non-numeric limits and explicit blank `prompt_namespace` or `model` fail with `AppError(code="cross_report_analysis_config_invalid")`.

- [x] **Step 2: Prove red behavior**

Run: `py -3.12 -m pytest tests/test_cross_report_analysis_contracts.py tests/test_config_service.py -q`

Expected before implementation: the new fail-closed assertions fail because malformed values currently pass.

- [x] **Step 3: Implement boundary validation**

Require the top-level value passed to `validate_cross_report_contract(...)` to be a dataclass instance. In cross-report config parsing, apply defaults only when required string keys are absent, and parse explicitly provided integer limits with a typed error rather than coercing malformed values into defaults.

- [x] **Step 4: Prove green behavior**

Run: `py -3.12 -m pytest tests/test_cross_report_analysis_contracts.py tests/test_config_service.py -q`

Expected after implementation: all contract/config tests pass.

### Task 3: Cross-Report Date and Category-ID Selection Correctness

**Files:**
- Modify: `tests/integration/test_analytics_store_cross_report_reads.py`
- Modify: `tests/test_cross_report_analysis_input_generator.py`
- Modify: `src/contracts/cross_report_analysis.py`
- Modify: `src/services/analytics_store_service.py`
- Modify: `src/generators/cross_report_analysis_input_generator.py`

- [x] **Step 1: Write failing selection tests**

Extend the service integration fixture with report `time_period` inputs and assert a reprojected old report does not pass a recent publication-period filter. Add generator coverage asserting a source with `category_ids=["retail-media"]` and `category_labels=["Retail Media"]` is selected when the request filters by `retail-media`.

- [x] **Step 2: Prove red behavior**

Run: `py -3.12 -m pytest tests/integration/test_analytics_store_cross_report_reads.py tests/test_cross_report_analysis_input_generator.py -q`

Expected before implementation: the old reprojected report is selected and the category-ID-only filter rejects its valid source.

- [x] **Step 3: Preserve semantic source metadata**

Add optional `category_ids` lists to candidate and selected-source contracts. Populate them from projected category rows in `analytics_store_service`, use `time_period` as the report publication-period field instead of projection timestamp, and match generator filters/relevance against both IDs and display labels.

- [x] **Step 4: Prove green behavior**

Run: `py -3.12 -m pytest tests/integration/test_analytics_store_cross_report_reads.py tests/test_cross_report_analysis_input_generator.py -q`

Expected after implementation: both correctness paths pass with complete dataclass outputs.

### Task 4: Documentation and Validation

**Files:**
- Modify: `README.md`

- [x] **Step 1: Document the behavioral fixes**

Record that optional private-API promotion ledger failures no longer abort completed downloads, and that cross-report category-ID/date/config/contract validation is fail-closed and publication-period based.

- [x] **Step 2: Run synthetic validation**

Run focused tests for changed modules, repository formatting/lint/type/test gates available in the project, and the full default test suite.

- [x] **Step 3: Run bounded live validation**

Load the existing `.env` without emitting secrets and run the guarded local-fixture report-download orchestrator integration with `RUN_REPORT_DOWNLOAD_ORCHESTRATOR_INTEGRATION=1`; its settings explicitly disable Drive uploads. Run the SQLite-backed analytics cross-report integration to validate the affected selection service on real persisted rows.

- [x] **Step 4: Publish reviewable changes**

Commit the verified files on `codex/address-codex-review-followups`, push the branch, and open a follow-up PR referencing the review findings; do not mutate historical review threads without explicit instruction.
