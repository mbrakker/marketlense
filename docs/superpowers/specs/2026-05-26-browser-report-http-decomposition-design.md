# Browser Report HTTP Decomposition Design

## Goal

Decompose `src/services/_browser_report_download/http.py` into focused
private service-capability modules without changing browser-report download
behavior, quality, provider cost, latency-critical request ordering, or the
canonical service boundary.

## Current State

`http.py` currently contains `2,066` audited physical lines and owns several
distinct HTTP acquisition responsibilities:

- access-challenge and static email-gate probes
- report-page HTML PDF-link probing
- direct PDF transfer and PDF artifact validation
- direct onsite HTML capture and recovery classification
- shared HTML and embedded PDF evidence extraction

Existing internal callers import its functions through
`src.services._browser_report_download.http`, including the canonical
`src.services.browser_report_download_service` facade and private browser,
artifact, preflight, and private-API modules.

Before production edits, the affected synthetic baseline is:

```text
161 passed, 1 deselected
```

The deselected test is guarded integration coverage and is reserved for the
post-synthetic live gate.

## Selected Architecture

Keep `src/services/_browser_report_download/http.py` as the stable private
compatibility surface and move implementations into a focused package:

```text
src/services/_browser_report_download/
  http.py
  _http/
    __init__.py
    pdf_transfer.py
    page_pdf_probe.py
    gate_probe.py
    onsite_capture.py
    html_evidence.py
```

`http.py` remains the import target consumed by existing browser-download
modules. It reexports the existing functions and dataclass, avoiding caller
churn and preserving the single service-family entrypoint.

### Capability Ownership

`pdf_transfer.py` owns direct PDF transfer, downloaded-PDF recovery, MIME
resolution, PDF signature validation, and `try_direct_pdf_download`.

`page_pdf_probe.py` owns report-page HTML probing, relevant PDF candidate
filtering, and delegation to direct PDF transfer.

`gate_probe.py` owns bounded access-challenge detection and static email-gate
detection, including their typed evidence/result construction.

`onsite_capture.py` owns direct onsite capture, eligibility and recovery
classification, and capture-result construction.

`html_evidence.py` owns pure shared parsing helpers for response header
extraction, HTML title/text/excerpt handling, and embedded PDF URL extraction
shared by page probing and downloaded-wrapper recovery.

## Preserved Boundary And Behavior

The canonical service boundary remains
`src/services/browser_report_download_service.py`. The new `_http/` package is
private implementation detail within that service family; it is not a new
external-system boundary or deployable component.

The refactor must preserve:

- exported names currently available from `http.py`
- call order among direct probes, browser escalation, and recovery paths
- HTTP request URLs, headers, timeouts, response-policy limits, and redirect behavior
- structured event names and logged fields
- typed `AppError` behavior and retryability classification
- PDF signature and MIME validation rules
- route family and terminal-evidence results
- existing provider/model invocation count, prompt behavior, and settings
- external upload behavior, including no upload in the approved live gate

No new HTTP requests, browser/model calls, retries, or fallback branches may
be introduced solely by this decomposition.

## Options Considered

### Selected: Private `_http/` Capability Package With `http.py` Compatibility Surface

This provides semantic ownership while keeping existing imports and canonical
service discovery stable. It matches the existing `_artifact` and
`_browser_runtime` private-package pattern.

### Rejected: Flat Sibling Modules Beside `http.py`

The responsibilities can be separated, but flat sibling files would enlarge
an already broad private package namespace and make capability ownership less
obvious.

### Rejected: One Extracted Helper Module

A single extracted helper module would reduce the line count in `http.py`
without correcting the mixed responsibility boundary.

## Test And Verification Strategy

Implementation follows test-first extraction:

1. Add an AST-based decomposition test that requires the selected capability
   functions to move from `http.py` into `_http/` modules while preserving the
   compatibility exports; run it before production edits and observe failure.
2. Move implementation without intentionally changing behavior; run the new
   ownership test and the affected synthetic browser-report suite.
3. Run full repository synthetic and configured CI enforcement gates:
   formatting, typing, split-symbol, forbidden-patching, hygiene, coverage,
   mutation, and quality regression.
4. Run the approved guarded local-fixture integration only after synthetic
   checks pass. It uses real browser/OpenRouter and real HTTP acquisition with
   external uploads disabled.
5. If verification exposes a regression, capture it with an observable
   regression test where needed, fix it, and rerun all required gates.

The test and live evidence will be recorded in the associated architecture
review after execution.
