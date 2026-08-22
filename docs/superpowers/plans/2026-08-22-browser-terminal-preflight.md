# Browser Terminal Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop an acquisition attempt before Browser Use when a bounded rendered-page probe confirms the requested report is a terminal 404 or 410 page, while retaining task-scoped diagnostics for Browser Use preflight failures.

**Architecture:** Keep `browser_report_download_service.py` as the canonical orchestration boundary. Add a narrowly scoped deterministic Chromium probe behind the existing browser preflight package; invoke it only after HTTP has classified the exact report URL as an access-layer response that requires browser rendering. The probe reports only a confirmed HTTP 404/410 plus terminal-page marker and never performs form actions, downloads, Agent calls, or retries.

**Tech Stack:** Python, existing browser runtime, task resource telemetry, pytest, retained Markdown evidence.

## Global Constraints

- Preserve all current acquisition fixes, including rendered on-site PDF recovery and process-isolated terminal behavior.
- Do not run discovery, ingestion, analysis, extraction, generation, publishing, or WordPress during validation.
- Do not classify a generic HTTP 403 as a missing report.
- Do not reintroduce generic Browser Use context-reduction behavior.
- Keep browser launches in the existing task-scoped budget and telemetry path.

---

### Task 1: Specify deterministic rendered-terminal classification

**Files:**

- Create: `tests/test_browser_report_download_service/test_rendered_terminal_preflight.py`
- Create: `src/services/_browser_report_download/rendered_terminal_preflight.py`

**Interfaces:**

- Produces: `try_rendered_terminal_preflight(...) -> BrowserPreflightProbeResponse | None`
- Consumes: `BrowserReportDownloadRequest`, `RunContext`, existing terminal page marker rules.

- [ ] **Step 1: Write the failing test**

```python
def test_rendered_terminal_preflight_stops_only_confirmed_404_marker(...):
    response = try_rendered_terminal_preflight(...)
    assert response.probe.status == "terminal_static_archive"
    assert "preflight_terminal_not_found" in response.probe.evidence_labels

def test_rendered_terminal_preflight_does_not_classify_403_as_missing(...):
    assert try_rendered_terminal_preflight(...) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_browser_report_download_service/test_rendered_terminal_preflight.py -q`

Expected: FAIL because `try_rendered_terminal_preflight` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def try_rendered_terminal_preflight(...):
    observation = _observe_page_in_bounded_chromium(...)
    if observation.status_code not in {404, 410}:
        return None
    if not _is_terminal_not_found_page(title=observation.title, html=observation.html):
        return None
    return _terminal_not_found_response(observation)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_browser_report_download_service/test_rendered_terminal_preflight.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_browser_report_download_service/test_rendered_terminal_preflight.py src/services/_browser_report_download/rendered_terminal_preflight.py
git commit -m "fix: detect rendered terminal report pages"
```

### Task 2: Integrate terminal result and retain bounded preflight diagnostics

**Files:**

- Modify: `src/services/browser_report_download_service.py`
- Modify: `src/services/_browser_report_download/preflight.py`
- Modify: `scripts/quality/acquisition_failure_remediation.py`
- Test: `tests/test_browser_report_download_service/test_browser_preflight.py`
- Test: `tests/test_acquisition_failure_remediation.py`

**Interfaces:**

- Consumes: `try_rendered_terminal_preflight(...)` from Task 1.
- Produces: a normal `email_required` terminal-static-archive result before Browser Use; a scalar-only `preflight_diagnostics` record for failed escalation.

- [ ] **Step 1: Write the failing test**

```python
def test_access_layer_probe_terminal_404_returns_before_browser_use(...):
    response = download_report_with_browser_use(...)
    assert response.blocked_reason == "blocked_static_archive"
    assert full_agent_loaded["value"] is False

def test_remediation_retains_scalar_preflight_diagnostics(...):
    assert record["acquisition_error"]["preflight_diagnostics"]["phase"] == "browser_start"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_browser_report_download_service/test_browser_preflight.py tests/test_acquisition_failure_remediation.py -q`

Expected: FAIL because the rendered probe is not invoked and diagnostics are not retained.

- [ ] **Step 3: Write minimal implementation**

```python
if force_browser_preflight:
    rendered_terminal = try_rendered_terminal_preflight(...)
    if rendered_terminal is not None:
        return _preflight_terminal_static_archive_result(...)
```

```python
preflight_diagnostics = {
    "phase": phase,
    "status": status,
    "duration_seconds": duration_seconds,
    "final_url": final_url,
    "html_size": html_size,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_browser_report_download_service/test_browser_preflight.py tests/test_acquisition_failure_remediation.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/browser_report_download_service.py src/services/_browser_report_download/preflight.py scripts/quality/acquisition_failure_remediation.py tests/test_browser_report_download_service/test_browser_preflight.py tests/test_acquisition_failure_remediation.py
git commit -m "fix: retain browser preflight terminal diagnostics"
```

### Task 3: Document and validate acquisition-only behavior

**Files:**

- Modify: `docs/workflows/report-acquisition.md`
- Create: `docs/CTO_evidence/browser_terminal_preflight_<timestamp>/README.md`

**Interfaces:**

- Consumes: the retained baseline cohort and configuration.
- Produces: a Criteo canary and, if it passes, the exact 15-report acquisition-only replay evidence.

- [ ] **Step 1: Update the canonical workflow document**

```markdown
For an HTTP access-layer response, the service may launch one bounded deterministic
rendered-page probe. Only a rendered HTTP 404/410 with the terminal marker stops the
attempt; any other observation falls through to existing Browser Use preflight.
```

- [ ] **Step 2: Run focused regression checks**

Run: `pytest tests/test_browser_report_download_service/test_rendered_terminal_preflight.py tests/test_browser_report_download_service/test_browser_preflight.py tests/test_browser_report_download_service/test_post_action_verification.py tests/test_acquisition_failure_remediation.py -q`

Expected: PASS.

- [ ] **Step 3: Run the Criteo acquisition-only canary**

Run: `python scripts/quality/acquisition_failure_remediation.py --manifest <one-report-manifest> --config <isolated-config> --output-dir <timestamped-dir>`

Expected: the Criteo record is a terminal static archive with no Browser Use Agent call.

- [ ] **Step 4: Run the exact retained 15-report acquisition-only cohort**

Run: `python scripts/quality/acquisition_failure_remediation.py --manifest docs/CTO_evidence/browser_isolated_timeout_15_20260822_144500/manifest.json --config <isolated-config> --output-dir docs/CTO_evidence/browser_terminal_preflight_15_<timestamp>`

Expected: retained per-report results and task-scoped acquisition resources only; no downstream stages.

- [ ] **Step 5: Commit**

```bash
git add docs/workflows/report-acquisition.md docs/CTO_evidence/browser_terminal_preflight_15_<timestamp>
git commit -m "docs: retain terminal preflight acquisition validation"
```

