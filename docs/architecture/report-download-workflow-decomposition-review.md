# Report Download Workflow Decomposition Review

## Decision

`src/orchestrators/report_download_orchestrator.py` remains the public
report-download orchestrator facade. Its private coordinator remains
`run_report_download(...)` in
`src/orchestrators/_report_download_orchestrator/workflow.py`, while focused
post-acquisition and policy capability families move to sibling modules in the
same private package.

This preserves the modular monolith and introduces no service boundary,
deployable unit, prompt namespace, configuration field, or public workflow.

## Review Trigger

The change extracts more than three private peer modules from the existing
2,554-line workflow module. This triggers the architecture review required by
`AGENTS.md`.

## Required Review Answers

### Is this preserving a modular monolith, or drifting toward fragmentation?

It preserves the modular monolith. The public orchestrator facade, one private
workflow coordinator, existing service boundaries, and existing route planner
remain in place.

### Is the new boundary semantic, or only structural?

It is semantic. Candidate screening, failure-forensics persistence,
playbook/private-API promotion, idempotent workflow persistence, and optional
Drive archival are existing orchestration capabilities with different effects
and failure semantics.

### Can the same outcome be achieved with fewer modules and the same testability?

A smaller split would leave `workflow.py` owning multiple substantial
post-acquisition behaviors or would combine local/state persistence with
external Drive archival. The proposed modules correspond to independently
testable existing behavior families while leaving route sequencing in one
coordinator.

### Does this reduce total cognitive load for the next engineer?

Yes. Engineers continue to follow one coordinator for the ordinary flow, then
enter one focused module for readiness screening, forensic failure evidence,
promotion, persistence, or archival behavior instead of searching a
multi-thousand-line workflow file.

## Preserved Behavior

- Public exports, result contracts, retry/fallback decisions, typed errors,
  event names, idempotency keys/checksums, provider use, and Drive side-effect
  settings remain unchanged.
- The existing browser-download service remains the only browser/OpenRouter
  external interaction boundary.
- The live verification uses real orchestration and browser/provider execution
  against a local fixture, with Drive disabled to avoid external document
  writes.

## Verification Gate

The implementation is accepted only after:

- a structure test proves private ownership boundaries and coordinator
  retention
- affected and full synthetic test suites pass
- repository formatting, typing, split-symbol, forbidden-patching, hygiene,
  coverage, mutation, and quality gates pass or a concrete local blocker is
  recorded
- a guarded local live orchestrator run obtains a verified PDF artifact and
  records local workflow side effects without Drive upload

## Execution Status - 2026-05-26

Completed automated evidence:

- The decomposition ownership test failed before extraction because the new
  private capability modules did not exist, then passed after extraction.
- The affected report-download and browser-download synthetic surface passed:
  `226` tests.
- The full default synthetic suite passed: `2,615` tests, with `16`
  integration tests deselected.
- Formatting, split-symbol, forbidden-patching, repository-hygiene, full
  `src` type checking, coverage, configured mutation, and quality-regression
  gates passed. The configured mutation targets do not currently include the
  extracted private report-download package.
- Coverage results were `82.60%` global and `84.27%` for
  `src/orchestrators`, above the configured thresholds.

Live-gate status:

- The guarded local orchestrator fixture uses a browser-only click-to-PDF
  path, real browser/OpenRouter execution, temporary SQLite/files, a real
  temporary identity configuration, and `drive_upload_enabled=False`.
- With the OpenRouter credential loaded from the local environment without
  logging its value, running
  `RUN_REPORT_DOWNLOAD_ORCHESTRATOR_INTEGRATION=1 python -m pytest -m integration tests/integration/test_report_download_orchestrator.py -q -rs`
  passed: `1` integration test passed with a verified PDF artifact,
  persisted route/source state, required orchestrator log fields, and zero
  Drive uploads.
- The successful final live run emitted existing vendored-browser deprecation
  warnings. They remain visible as residual browser-runtime cleanup risk; this
  workflow decomposition does not suppress or reinterpret them.
