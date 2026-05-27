# Browser Report Runtime Decomposition Design

## Goal

Reduce the mixed-responsibility concentration in
`src/services/_browser_report_download/browser.py` without changing browser
download behavior, cost controls, model inputs, timeouts, public entrypoints,
or external-system ownership.

## Scope

`src/services/browser_report_download_service.py` remains the sole public
browser-download service boundary. Its existing internal call to
`run_browser_report_download_agent(...)` remains valid through
`src/services/_browser_report_download/browser.py`.

The change extracts existing browser-runtime behavior into one private
capability package:

```text
src/services/_browser_report_download/
  browser.py
  _browser_runtime/
    __init__.py
    terminal_state.py
    terminal_assets.py
    timeout_recovery.py
    worker_protocol.py
    session_lifecycle.py
```

No new public service, orchestrator route, external API, prompt namespace,
contract version, configuration field, retry policy, or deployable unit is in
scope.

## Boundary Design

### Coordinator: `browser.py`

`browser.py` retains `run_browser_report_download_agent(...)`. It constructs
the browser and agent for one service invocation, invokes the extracted
runtime capabilities in the current order, translates unexpected runtime
failures into the existing typed `AppError` outcomes, emits the existing
request/response/failure events, and returns `BrowserAgentRunResult`.

The coordinator is intentionally not replaced with another facade. It is the
private entrypoint already used by the canonical service boundary and by
`browser_worker.py`.

### Terminal State: `_browser_runtime/terminal_state.py`

This module owns page-state capture and stabilization:

- `TerminalSnapshot`, `TerminalStabilizationPolicy`, and
  `TerminalQuorumAssessment`
- terminal snapshot capture and merging
- stabilization policy resolution
- terminal quorum assessment and text/transient-signal evaluation

Its responsibility is deciding whether a captured browser terminal state is
stable enough to inspect. It does not start or stop browser processes, issue
HTTP downloads, or determine orchestration retries.

### Terminal Assets: `_browser_runtime/terminal_assets.py`

This module owns post-action browser evidence acquisition:

- materializing browser-produced artifacts into the managed download folder
- prefetching a structured PDF artifact through the existing HTTP service
- HTML snapshot and screenshot capture
- dialog, resource URL, network-event, and DOM candidate collection
- rendered-page print-to-PDF fallback checks

It retains the current use of `http.py`, `cdp.py`, and browser helper
boundaries. It does not change whether an external acquisition occurs or add
new requests.

### Timeout Recovery: `_browser_runtime/timeout_recovery.py`

This module owns bounded recovery after agent-history stalls:

- cached and live terminal-state salvage
- lookup submission-assistance eligibility and execution
- bounded recovery worker timeout handling

It is invoked only from the existing coordinator and lifecycle flow. It does
not introduce retries or alter the configured agent execution budget.

### Worker Protocol: `_browser_runtime/worker_protocol.py`

This module owns the subprocess transport used outside unit-test execution:

- worker request/response dataclasses
- worker dispatch decision
- payload serialization and secure deletion
- sanitized output excerpt normalization
- `BrowserAgentRunResult` deserialization

It preserves the existing `browser_worker.py` module command, environment
variables, outer timeout calculation, logging events, and error codes.

### Session Lifecycle: `_browser_runtime/session_lifecycle.py`

This module owns browser-runtime lifecycle mechanics:

- `browser_use` import loading
- bounded history execution and partial-history interpretation
- timeout calculation and stop signaling
- managed profile and browser-use temporary-directory cleanup
- browser shutdown and forced local process termination

It does not own terminal evidence semantics or route/result adaptation.

## Data And Control Flow

1. The canonical service calls `browser.run_browser_report_download_agent`.
2. The coordinator logs the current request metadata and loads browser-use.
3. When required, `worker_protocol.py` dispatches the same worker process and
   returns the same typed runtime result.
4. In an in-process execution, `session_lifecycle.py` prepares the runtime and
   bounds agent execution.
5. The coordinator requests terminal-state and asset inspection from
   `terminal_state.py` and `terminal_assets.py`.
6. On the existing timeout error path, `timeout_recovery.py` attempts the same
   bounded salvage/lookup-assistance behavior.
7. Lifecycle cleanup occurs in the existing finalization order and the
   coordinator emits the existing response event and result contract.

## Compatibility Constraints

- Existing public imports from `src/services/browser_report_download_service.py`
  remain unchanged.
- `src/services/_browser_report_download/browser_worker.py` continues to
  import `run_browser_report_download_agent(...)` and the worker response
  dataclass through the compatibility exports in `browser.py`.
- Existing tests that refer to runtime internals may continue through
  compatibility imports from `browser.py` during this refactor; new tests
  assert capability ownership without patching extracted private helpers.
- Logger names, event names, `AppError` codes, retryability/severity,
  artifact paths, cleanup order, prompt rendering, model parameters, and
  session-reuse behavior remain unchanged.

## Quality, Speed, And Cost Controls

This is a movement-only refactor. It does not alter:

- prompt text, selected namespace, or prompt variables
- model name, temperature, token behavior, or call count
- direct HTTP, CDP, or browser-use operations and their triggering conditions
- timeout constants, polling schedules, subprocess budget, or cleanup timing
- terminal quorum thresholds, route classification, artifact validation, or
  fallback ordering

The split must therefore preserve the same observable calls and results under
existing synthetic tests. The guarded live integration confirms that the
real browser/model path still acquires and validates a PDF from the local
fixture after the movement.

## Testing And Verification

Implementation begins with a failing structure test proving that the intended
private capability modules own their function families and `browser.py`
retains only its coordinator and compatibility imports for them.

After the split, verification includes:

- targeted browser-download service tests covering terminal inspection,
  worker/timeout recovery, prompt/probe behavior, identity blockers, and
  private API/preflight flow
- browser CDP, browser helper, browser developer-diagnostic, local watchdog,
  route-planner, and report-download orchestrator tests where runtime
  ownership can affect integration
- static split-link, forbidden-patching, formatting, type, and repository
  hygiene checks applicable to the modified files
- the default synthetic test suite or the repository CI-equivalent test
  command available locally
- the guarded live run
  `RUN_BROWSER_DOWNLOAD_INTEGRATION=1 python -m pytest -m integration
  tests/integration/test_browser_report_download_service.py -q`, subject to
  the configured `OPENROUTER_API_KEY` and installed browser-use environment

The live run is deliberately limited to the local served PDF fixture. It can
exercise real browser-use and a real configured model call without adding an
unbounded publisher-site probe or altering stored route memory.

## Documentation Deliverables

The implementation updates:

- `docs/architecture/browser-report-runtime-decomposition-review.md`
- `README.md` to name the new private runtime capability package
- `long_scripts.md` after rerunning `scripts/count_long_files.py`

