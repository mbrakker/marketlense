# Browser Report Artifact Finalization Decomposition Review

## Decision

`src/services/browser_report_download_service.py` remains the sole public
browser-download service boundary. The internal artifact adapter keeps
`finalize_browser_report_download_result(...)` in
`src/services/_browser_report_download/artifact.py`, while focused behavior
families live under `src/services/_browser_report_download/_artifact/`.

This change preserves the modular monolith. It does not introduce another
external-system boundary, deployable unit, route, retry policy, prompt path,
or contract version.

## Boundary Rationale

The former `artifact.py` combined finalization coordination with five
substantial capabilities: PDF materialization, on-site capture, terminal
classification, evidence construction, and fallback recovery. These are
semantic units with independently testable failure paths, not layers that
merely rename or forward calls.

A smaller split would retain mixed terminal classification/recovery and
artifact-I/O logic in a multi-thousand-line module. Five internal modules keep
each decision family discoverable while leaving the normal call path at one
service boundary, one finalizer, and one HTTP acquisition boundary.

## Preserved Behavior

- Result contracts, schema versions, typed `AppError` outcomes, event names,
  logger names, timeouts, prompt/model behavior, and artifact paths are
  unchanged.
- External PDF and terminal HTML calls remain owned by
  `src/services/_browser_report_download/http.py`; extracted capabilities call
  that boundary directly.
- Tests assert that recovery does not add PDF or terminal HTML requests and
  that route-step verification retains required structured log fields.

## Verification

Automated acceptance covers finalization behavior, browser-download service
flows, route/orchestrator behavior, architecture imports, forbidden patching,
formatting, typing, coverage, and CI-equivalent test execution. A guarded live
`download-report` feature run must also be recorded after automated checks,
capturing outcome, artifact validation, terminal evidence, duration, and
available external/browser/model call evidence.
