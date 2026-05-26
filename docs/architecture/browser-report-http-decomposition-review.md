# Browser Report HTTP Decomposition Architecture Review

## Trigger

This review is required because the decomposition of
`src/services/_browser_report_download/http.py` introduces more than three
private capability modules inside an existing service family.

## Capability And Current Bounded Context

Capability: bounded HTTP acquisition and HTTP-derived evidence for browser
report download.

Bounded context: the existing browser-report download service family exposed
canonically by `src/services/browser_report_download_service.py`.

## Boundary Decision

This change preserves the modular monolith. It introduces a private
implementation package under the existing service family:

```text
src/services/_browser_report_download/_http/
```

The existing `http.py` module remains the compatibility surface for internal
callers, and the canonical service entrypoint remains
`browser_report_download_service.py`.

No network/process boundary, new deployable unit, duplicated external-system
entrypoint, or independent runtime is introduced.

## Why The Boundary Is Semantic

The current HTTP module combines independent HTTP service capabilities:

- access and gate probes that produce terminal evidence
- report-page probing that resolves candidate PDF URLs
- binary PDF transfer and downloaded-artifact validation
- direct onsite HTML capture and recovery selection
- deterministic parsing and embedded-PDF extraction shared across those HTTP
  operations

The selected modules separate these capabilities by observable service
responsibility, not arbitrary size targets. Each module owns real decisions,
I/O adaptation, or deterministic evidence extraction; none exists only to
rename or pass arguments through.

## Fewer-Module Assessment

A two-module split would either combine probing with binary transfer or combine
onsite capture with gate classification, leaving unrelated responsibilities
together. A single extracted helper module would only relocate the monolith.

The focused private modules preserve low coupling:

- shared immutable HTTP acquisition headers and body-size limits have one
  owner in `_http/config.py`
- shared parsing and embedded-PDF extraction are deterministic and usable by
  probe, transfer-recovery, and capture capabilities
- report-page probing delegates successful transfer to the binary PDF owner
- `http.py` exposes the existing stable symbols to consumers

## Cognitive Load Assessment

Normal consumers continue to import one HTTP compatibility module. Engineers
changing a specific behavior can navigate directly to its capability owner:
transfer, PDF-page probe, gate probe, onsite capture, or shared parsing. This
reduces the amount of unrelated service code needed to reason about one
failure mode.

## Preservation Controls

The refactor is movement-only unless a failing regression test requires a
correction. It must preserve:

- HTTP request metadata, timeouts, limits, and redirects
- event names and structured fields
- error taxonomy
- route-result semantics and terminal evidence
- provider/model request count and prompt behavior
- upload behavior

## Verification Plan

Pre-edit affected synthetic baseline:

```text
161 passed, 1 deselected
```

Required completion evidence:

- AST ownership test fails before extraction and passes after extraction
- affected browser-report synthetic suite passes
- full default synthetic suite passes
- configured formatting, type, architecture, forbidden-patching, hygiene,
  coverage, mutation, and quality-regression gates pass
- guarded local-fixture live test passes after synthetic gates, using real
  browser/OpenRouter and real HTTP acquisition with external uploads disabled

Execution evidence will be added to this review when verification completes.

## Execution Status - 2026-05-26

Implementation ownership:

- `http.py` is now the `47`-line compatibility surface retained by current
  browser-download consumers.
- `_http/config.py` owns shared HTTP request headers and bounded body-size
  constants.
- `_http/html_evidence.py` owns deterministic HTML and embedded-PDF parsing.
- `_http/pdf_transfer.py` owns verified PDF transfer and artifact validation.
- `_http/page_pdf_probe.py` owns HTML report-page PDF-link probing.
- `_http/gate_probe.py` owns access-challenge and static email-gate probes.
- `_http/onsite_capture.py` owns direct onsite capture and recovery
  classification.

Detected and corrected during implementation:

- The first focused post-extraction run detected that mechanical source
  movement had omitted the `@dataclass(frozen=True)` decorator on
  `DirectOnsiteRecoveryDecision`, preventing recovery-decision construction.
  The original decorator/import were restored, and all subsequent synthetic
  and live checks passed.

Automated evidence:

- The new ownership test failed before extraction because `_http/pdf_transfer.py`
  did not exist, then passed after extraction.
- The expanded affected browser-report and report-download synthetic surface
  passed: `227` tests.
- The full default synthetic suite passed: `2,616` tests, with `16`
  integration tests deselected.
- Formatting, split-symbol, forbidden-patching, repository-hygiene, full
  `src` type checking, coverage, configured mutation, and quality-regression
  gates passed.
- Coverage results were `82.63%` globally and `82.02%` for `src/services`,
  above the configured thresholds.
- The configured mutation targets do not currently include the extracted
  private browser-report `_http` package.

Live-gate evidence:

- The existing guarded local fixture executed the real browser/OpenRouter and
  HTTP acquisition path using temporary output/state files; this browser
  service path performs no external upload action.
- With the OpenRouter credential loaded from `.env` without logging its value,
  running
  `RUN_BROWSER_DOWNLOAD_INTEGRATION=1 python -m pytest -m integration tests/integration/test_browser_report_download_service.py -q -rs`
  passed: `1` integration test passed with a verified PDF artifact and
  required structured service log fields.
- The live run emitted existing vendored-browser and `backoff` deprecation
  warnings. They remain visible as browser-runtime cleanup risk; this
  decomposition does not suppress or reinterpret them.
