# Browser Report Runtime Decomposition Review

## Decision

`src/services/browser_report_download_service.py` remains the sole public
browser-download service boundary. The internal runtime keeps
`run_browser_report_download_agent(...)` in
`src/services/_browser_report_download/browser.py`, while focused browser
execution behavior families move under
`src/services/_browser_report_download/_browser_runtime/`.

This is an internal modular-monolith decomposition. It introduces no new
deployable component, network/process boundary, external-system entrypoint,
prompt path, orchestrator path, or contract version.

## Review Trigger

The change extracts more than three private peer modules from the current
4,004-line browser runtime module. That triggers the architecture review
required by `AGENTS.md`, even though all new modules remain inside the
existing browser-download capability boundary.

## Required Review Answers

### Is this preserving a modular monolith, or drifting toward fragmentation?

It preserves the modular monolith. One canonical browser-download service
continues to own all browser-use interaction, and `browser.py` continues to
provide its single internal execution entrypoint.

### Is the new boundary semantic, or only structural?

It is semantic. The extracted capabilities separately own terminal-state
stabilization, terminal evidence acquisition, timeout recovery, subprocess
transport, and browser lifecycle cleanup. Each already has distinct failure
and validation behavior in the current module.

### Can the same outcome be achieved with fewer modules and the same testability?

A smaller extraction leaves either terminal inspection coupled to external
artifact acquisition or timeout/subprocess recovery coupled to browser
shutdown mechanics. Those concerns have independent existing regression
coverage and different failure modes. Five private modules are the smallest
split that isolates the identified stable capabilities without creating
pass-through forwarding layers.

### Does this reduce total cognitive load for the next engineer?

Yes. The ordinary flow remains one service entrypoint plus one runtime
coordinator, while investigation of evidence, recovery, worker, or cleanup
behavior can be performed within one focused module rather than navigating a
single 4,004-line mixed implementation.

## Preserved Behavior

- Public service entrypoints, call ordering, prompt/model settings, browser
  operations, external acquisition behavior, timeout and polling constants,
  route outcomes, artifact validation, event names, typed error codes, and
  result contracts remain unchanged.
- `browser_worker.py` retains the same subprocess role and compatibility
  imports.
- Extracted code uses existing browser-download HTTP, CDP, helper, and
  session-reuse boundaries; it does not add a competing boundary.

## Verification Gate

The implementation is accepted only after:

- a structure test confirms capability ownership and coordinator retention
- affected browser-download, lifecycle, CDP, route, and orchestrator
  synthetic tests pass
- applicable formatting, typing, split-symbol, forbidden-patching, coverage,
  mutation, and quality gates are executed or any local blocker is recorded
- the guarded local browser-download integration run executes with real
  browser-use/model configuration against its local PDF fixture and records
  the validated downloaded-artifact outcome

## Execution Status - 2026-05-26

Completed automated evidence:

- The decomposition ownership test failed before extraction because the
  `_browser_runtime` package did not exist, then passed after extraction.
- The affected browser-download, terminal, lifecycle, CDP, route-planner,
  and report-download orchestrator suite passed: `225` tests.
- The full default synthetic suite passed: `2,614` tests, with `15`
  integration tests deselected.
- Formatting, split-symbol, forbidden-patching, repository-hygiene, full
  `src` type checking, coverage, mutation, and quality-regression gates
  passed.
- Coverage results were `82.58%` global and `81.97%` for `src/services`,
  above the configured thresholds.

Live-gate status:

- The guarded local integration fixture was tightened to require the
  browser-agent click path and assert canonical service start/complete events,
  rather than allowing the direct HTTP link shortcut to satisfy the check.
- With the OpenRouter credential loaded from the local environment without
  logging its value, running
  `RUN_BROWSER_DOWNLOAD_INTEGRATION=1 python -m pytest -m integration tests/integration/test_browser_report_download_service.py -q -rs`
  passed: `1` integration test passed and a verified PDF artifact was
  downloaded through the browser route.
- The successful live run emitted existing vendored-browser deprecation
  warnings and post-completion CDP/event-loop teardown diagnostics. Those
  diagnostics remain visible as residual live-runtime cleanup risk; this
  decomposition does not suppress them or change the extracted lifecycle
  behavior.
