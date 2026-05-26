# Browser Report HTTP Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the browser-report HTTP implementation into focused private capability modules while retaining its existing import surface and behavior.

**Architecture:** `src/services/_browser_report_download/http.py` becomes the stable private compatibility module for existing callers. New modules in `_browser_report_download/_http/` own PDF transfer, report-page probing, gate probing, onsite capture, and shared HTML evidence within the same browser-report service boundary.

**Tech Stack:** Python 3.14, dataclasses, `requests`, `pytest`, AST ownership checks, existing CI quality scripts

---

## File Structure

- Create: `src/services/_browser_report_download/_http/__init__.py` - marks the focused private implementation package.
- Create: `src/services/_browser_report_download/_http/config.py` - owns shared HTTP headers and bounded response-size constants.
- Create: `src/services/_browser_report_download/_http/html_evidence.py` - shared deterministic HTML/header/text and embedded-PDF extraction.
- Create: `src/services/_browser_report_download/_http/pdf_transfer.py` - binary PDF download, recovery, MIME resolution, validation, and direct PDF route.
- Create: `src/services/_browser_report_download/_http/page_pdf_probe.py` - report-page candidate PDF discovery and transfer selection.
- Create: `src/services/_browser_report_download/_http/gate_probe.py` - access-challenge and static email-gate probes.
- Create: `src/services/_browser_report_download/_http/onsite_capture.py` - onsite HTML-capture route and recovery classification.
- Modify: `src/services/_browser_report_download/http.py` - compatibility imports/reexports only.
- Create: `tests/test_browser_report_download_http_decomposition.py` - module-ownership and compatibility-surface regression check.
- Modify: `tests/integration/test_browser_report_download_service.py` only if the existing guarded live fixture requires a stronger direct assertion on HTTP-derived persistence or route output.
- Modify: `README.md` - record the private HTTP capability isolation.
- Modify: `long_scripts.md` - refresh the hotspot audit after extraction.
- Modify: `docs/architecture/browser-report-http-decomposition-review.md` - record execution and verification evidence.

### Task 1: Establish The Extraction Ownership Test

**Files:**
- Create: `tests/test_browser_report_download_http_decomposition.py`

- [x] **Step 1: Write the failing ownership and compatibility test**

```python
from __future__ import annotations

import ast
from pathlib import Path


PACKAGE = Path("src/services/_browser_report_download")
HTTP = PACKAGE / "http.py"
COMPATIBILITY_EXPORTS = {
    "DirectOnsiteRecoveryDecision",
    "download_pdf_from_url",
    "ensure_downloaded_pdf",
    "extract_embedded_pdf_urls",
    "fetch_html_from_url",
    "is_pdf_file",
    "resolve_downloaded_mime_type",
    "try_direct_onsite_capture",
    "try_direct_pdf_download",
    "try_http_access_challenge_probe",
    "try_report_page_pdf_link_download",
    "try_static_email_gate_probe",
    "validate_downloaded_pdf_artifact",
}
MODULE_FUNCTIONS = {
    "_http/pdf_transfer.py": {
        "try_direct_pdf_download",
        "ensure_downloaded_pdf",
        "resolve_downloaded_mime_type",
        "validate_downloaded_pdf_artifact",
        "is_pdf_file",
        "download_pdf_from_url",
    },
    "_http/page_pdf_probe.py": {
        "try_report_page_pdf_link_download",
    },
    "_http/gate_probe.py": {
        "try_http_access_challenge_probe",
        "try_static_email_gate_probe",
    },
    "_http/onsite_capture.py": {
        "DirectOnsiteRecoveryDecision",
        "try_direct_onsite_capture",
    },
    "_http/html_evidence.py": {
        "_extract_html_title",
        "_html_to_text",
        "_extract_text_excerpt",
        "_response_header_value",
        "extract_embedded_pdf_urls",
    },
}


def _owned_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_browser_report_http_uses_focused_private_capability_modules() -> None:
    coordinator_symbols = _owned_symbols(HTTP)
    for relative_path, expected_symbols in MODULE_FUNCTIONS.items():
        owned_symbols = _owned_symbols(PACKAGE / relative_path)
        assert expected_symbols <= owned_symbols
        assert not expected_symbols & coordinator_symbols

    source = HTTP.read_text(encoding="utf-8")
    for symbol in COMPATIBILITY_EXPORTS:
        assert symbol in source
```

- [x] **Step 2: Run the ownership test and confirm it fails before production edits**

Run:

```powershell
python -m pytest tests/test_browser_report_download_http_decomposition.py -q
```

Expected: `FAILED` because `src/services/_browser_report_download/_http/pdf_transfer.py` does not yet exist.

- [x] **Step 3: Commit the red test with the implementation after it turns green**

The test remains uncommitted through the extraction so the commit contains a verified test and its corresponding implementation.

### Task 2: Extract Shared HTML Evidence And Binary PDF Transfer

**Files:**
- Create: `src/services/_browser_report_download/_http/__init__.py`
- Create: `src/services/_browser_report_download/_http/config.py`
- Create: `src/services/_browser_report_download/_http/html_evidence.py`
- Create: `src/services/_browser_report_download/_http/pdf_transfer.py`
- Modify: `src/services/_browser_report_download/http.py`
- Test: `tests/test_browser_report_download_http_decomposition.py`
- Test: `tests/test_browser_report_download_doc_type_predictor.py`

- [x] **Step 1: Move deterministic shared evidence functions**

Move shared immutable request constants to `config.py` so request metadata
remains single-sourced:

| Source constants in `http.py` | Original lines |
| --- | ---: |
| `_PDF_FETCH_HEADERS`, `_HTML_FETCH_HEADERS` | 60-69 |
| `_HTML_FETCH_MAX_BYTES`, `_PDF_FETCH_MAX_BYTES` | 209-210 |

Move the original implementations from `http.py` into `html_evidence.py`,
keeping their original names and bodies:

| Source symbols in `http.py` | Original lines |
| --- | ---: |
| `_response_header_value` | 927-934 |
| `_extract_html_title`, `_html_to_text`, `_extract_text_excerpt` | 1957-1976 |
| `_extract_embedded_pdf_url`, `extract_embedded_pdf_urls`, `_append_pdf_candidate` | 2001-2066 |

Preserve their current bodies from `http.py`; export public compatibility
names through `http.py`, including `extract_embedded_pdf_urls`.

- [x] **Step 2: Move binary transfer implementations**

Move these original definitions into `pdf_transfer.py` without changing their
bodies:

| Source symbols in `http.py` | Original lines |
| --- | ---: |
| `try_direct_pdf_download` | 1013-1154 |
| `ensure_downloaded_pdf`, `fetch_html_from_url`, `resolve_downloaded_mime_type`, `validate_downloaded_pdf_artifact`, `is_pdf_file`, `download_pdf_from_url` | 1384-1689 |
| `_guess_mime_type`, `_read_text_if_small` | 1979-1998 |

Import deterministic dependencies from `html_evidence.py`. Retain identical
HTTP acquisition requests, headers, timeouts, maximum-body policies, log event
names, typed error behavior, route-family construction, and PDF validation.

- [x] **Step 3: Keep `http.py` as compatibility surface**

Replace moved definitions with direct imports:

```python
from src.services._browser_report_download._http.html_evidence import (
    _extract_embedded_pdf_url,
    _extract_html_title,
    _extract_text_excerpt,
    _html_to_text,
    _response_header_value,
    extract_embedded_pdf_urls,
)
from src.services._browser_report_download._http.pdf_transfer import (
    download_pdf_from_url,
    ensure_downloaded_pdf,
    fetch_html_from_url,
    is_pdf_file,
    resolve_downloaded_mime_type,
    try_direct_pdf_download,
    validate_downloaded_pdf_artifact,
)
```

Keep `requests` imported in `http.py` because existing external-boundary
tests patch `http_runtime.requests.get`, which refers to the shared imported
`requests` package object used by extracted service modules.

- [x] **Step 4: Run focused checks**

Run:

```powershell
python -m pytest tests/test_browser_report_download_http_decomposition.py tests/test_browser_report_download_doc_type_predictor.py -q
```

Expected: ownership test remains failing only for capability modules not yet
extracted; existing predictor tests pass without changed output semantics.

### Task 3: Extract Page PDF And Gate Probe Capabilities

**Files:**
- Create: `src/services/_browser_report_download/_http/page_pdf_probe.py`
- Create: `src/services/_browser_report_download/_http/gate_probe.py`
- Modify: `src/services/_browser_report_download/http.py`
- Test: `tests/test_browser_report_download_http_decomposition.py`
- Test: `tests/test_browser_report_download_service/test_prompt_and_probe.py`

- [x] **Step 1: Move report-page PDF probing**

Move the existing report-page probe and its candidate selection helpers from
their original source lines:

| Source symbols in `http.py` | Original lines |
| --- | ---: |
| `try_report_page_pdf_link_download` | 335-542 |
| `_should_try_report_page_pdf_link_probe`, `_html_pdf_link_probe_timeout_seconds` | 704-726 |
| `_filter_relevant_pdf_candidates`, `_pdf_candidate_matches_report_page`, `_report_relevance_tokens`, `_looks_like_pdf_url` | 874-924 |

Use `extract_embedded_pdf_urls` and `_response_header_value` from
`html_evidence.py`, and
`try_direct_pdf_download` from `pdf_transfer.py`. Preserve candidate order,
probe timeout choice, response-policy metadata, route steps, and log fields.

- [x] **Step 2: Move gate probing**

Move access-challenge and static email-gate definitions from their original
source lines:

| Source symbols in `http.py` | Original lines |
| --- | ---: |
| `try_http_access_challenge_probe` | 213-332 |
| `try_static_email_gate_probe` | 545-701 |
| `_looks_like_static_email_gate_html`, `_route_context_supports_static_email_gate`, `_build_static_email_gate_result` | 729-871 |
| `_build_access_challenge_result` | 937-1010 |

Use `_extract_html_title`, `_extract_text_excerpt`, `_html_to_text`, and
`_response_header_value` from `html_evidence.py`. Preserve markers, status codes,
timeouts, event names, terminal-evidence construction, and errors.

- [x] **Step 3: Reexport public probe functions from `http.py`**

```python
from src.services._browser_report_download._http.gate_probe import (
    try_http_access_challenge_probe,
    try_static_email_gate_probe,
)
from src.services._browser_report_download._http.page_pdf_probe import (
    try_report_page_pdf_link_download,
)
```

- [x] **Step 4: Run focused probe checks**

Run:

```powershell
python -m pytest tests/test_browser_report_download_http_decomposition.py tests/test_browser_report_download_service/test_prompt_and_probe.py tests/test_browser_report_download_doc_type_predictor.py -q
```

Expected: ownership test remains failing only for onsite capture until Task 4;
existing probe and prediction assertions pass.

### Task 4: Extract Onsite Capture And Complete The Compatibility Surface

**Files:**
- Create: `src/services/_browser_report_download/_http/onsite_capture.py`
- Modify: `src/services/_browser_report_download/http.py`
- Test: `tests/test_browser_report_download_http_decomposition.py`
- Test: `tests/test_browser_report_download_service/test_onsite_and_terminal.py`

- [x] **Step 1: Move onsite capture ownership**

Move the existing dataclass and onsite capture implementation from original
source lines:

```python
@dataclass(frozen=True)
class DirectOnsiteRecoveryDecision:
    schema_version: str
    allowed: bool
    recovery_class: str
    reason: str
```

| Source symbols in `http.py` | Original lines |
| --- | ---: |
| `DirectOnsiteRecoveryDecision` | 101-105 |
| `try_direct_onsite_capture` | 1157-1381 |
| `_should_try_direct_onsite_capture`, `_direct_onsite_recovery_decision`, `_looks_like_report_detail_candidate`, `_looks_like_mixed_content_hub_candidate`, `_url_surface_key`, `_looks_like_onsite_capture_html`, `_route_context_supports_direct_onsite_capture` | 1692-1954 |

Use `_extract_html_title`, `_extract_text_excerpt`, and `_html_to_text` from
`html_evidence.py`. Preserve capture request policy, recovery reasons, route
family decisions, and event fields.

- [x] **Step 2: Complete `http.py` reexports**

```python
from src.services._browser_report_download._http.onsite_capture import (
    DirectOnsiteRecoveryDecision,
    try_direct_onsite_capture,
)
```

The compatibility module must retain every external name consumed by current
browser-download modules and tests; it must contain no moved capability
definitions.

- [x] **Step 3: Run ownership and affected synthetic tests**

Run:

```powershell
python -m pytest tests/test_browser_report_download_http_decomposition.py tests/test_browser_report_download_service tests/test_browser_report_download_doc_type_predictor.py tests/test_browser_report_download_cdp.py tests/test_browser_download_helpers.py -q
```

Expected: all selected tests pass; the ownership test now observes each
capability in its designated module and not in `http.py`.

### Task 5: Document And Audit The Refactor

**Files:**
- Modify: `README.md`
- Modify: `long_scripts.md`
- Modify: `docs/architecture/browser-report-http-decomposition-review.md`

- [x] **Step 1: Record the stable boundary in README**

Add a concise architecture note adjacent to existing browser-report
decomposition documentation:

```markdown
- Browser-report HTTP isolation: `src/services/_browser_report_download/http.py` remains the private compatibility surface, while PDF transfer, page-PDF probing, gate probing, onsite capture, and shared HTML evidence live in `_http/` capability modules behind the canonical browser-report service boundary.
```

- [x] **Step 2: Refresh the long-file audit**

Run:

```powershell
python scripts/count_long_files.py --min-lines 500
```

Update `long_scripts.md` with the reported audited line counts and remove
`http.py` from the active hotspot table only if the audit output confirms it
is no longer above the threshold represented there.

- [x] **Step 3: Record implementation ownership and verification fields**

In `docs/architecture/browser-report-http-decomposition-review.md`, add an
execution-status section with extracted module ownership, test counts,
coverage figures, configured mutation-scope limitations where applicable, and
the final guarded live result.

### Task 6: Full Synthetic And Live Verification

**Files:**
- Modify: `docs/architecture/browser-report-http-decomposition-review.md` with actual evidence

- [x] **Step 1: Run affected synthetic and static verification**

Run:

```powershell
python -m pytest tests/test_browser_report_download_http_decomposition.py tests/test_browser_report_download_runtime_decomposition.py tests/test_browser_report_download_artifact_decomposition.py tests/test_browser_report_download_service tests/test_browser_report_download_doc_type_predictor.py tests/test_browser_report_download_cdp.py tests/test_browser_download_helpers.py tests/test_browser_developer_diagnostics.py tests/test_browser_use_local_browser_watchdog.py tests/test_report_download_workflow_decomposition.py tests/test_report_download_route_planner.py tests/test_report_download_orchestrator.py -q
python -m ruff check src/services/_browser_report_download/http.py src/services/_browser_report_download/_http tests/test_browser_report_download_http_decomposition.py tests/integration/test_browser_report_download_service.py
python scripts/ci/check_formatting.py
python scripts/ci/check_split_symbol_links.py
python scripts/ci/check_forbidden_patching.py
python scripts/ci/check_repository_hygiene.py
python scripts/ci/run_type_check.py
```

Expected: all commands exit `0`.

- [x] **Step 2: Run complete synthetic and configured quality gates**

Run:

```powershell
python -m pytest -q
python -m pytest --cov=src --cov-report=xml --cov-report=term-missing -q
python scripts/ci/check_coverage.py --coverage-xml coverage.xml
python scripts/ci/run_mutation_gate.py --json-out mutation_results.json
python scripts/ci/check_quality_regression.py --baseline docs/quality/baseline_2026-02-21.json --coverage-xml coverage.xml --mutation-json mutation_results.json --docpack-root tests/fixtures/docpacks/golden --candidate-root tests/fixtures/candidate_extraction/golden
```

Expected: all commands exit `0`, with actual totals recorded in the
architecture review.

- [x] **Step 3: Run the bounded live gate only after synthetic checks pass**

Load `OPENROUTER_API_KEY`, `BROWSER_DOWNLOAD_MODEL`, and
`OPENROUTER_HTTP_REFERER` from `.env` into the child process without printing
values. Run:

```powershell
$env:RUN_BROWSER_DOWNLOAD_INTEGRATION='1'
python -m pytest -m integration tests/integration/test_browser_report_download_service.py -q -rs
```

Expected: the guarded fixture downloads and verifies a PDF through real
browser/OpenRouter and HTTP acquisition with uploads disabled, and its
structured-log assertions pass.

- [x] **Step 4: Handle any detected regression test-first**

For a failed existing assertion or live behavior difference, add or refine a
test asserting the observable contract, event, artifact, or request side
effect; observe it fail; make the narrow production correction; rerun Steps 1
through 3 before recording completion.

- [x] **Step 5: Commit implementation and evidence**

Run:

```powershell
git add README.md long_scripts.md docs/architecture/browser-report-http-decomposition-review.md src/services/_browser_report_download/http.py src/services/_browser_report_download/_http tests/test_browser_report_download_http_decomposition.py tests/integration/test_browser_report_download_service.py
git commit -m "refactor: decompose browser report http service"
```

Only include `tests/integration/test_browser_report_download_service.py` if
it changed during implementation.
