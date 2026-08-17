# Browser Use No-Progress Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop Browser Use acquisition after several consecutive materially identical turn states while retaining a typed, evidence-backed terminal outcome that remains usable by route learning and suppression.

**Architecture:** Add a small deterministic detector at the MarketLense Browser Use adapter boundary, using Browser Use's supported per-turn callbacks rather than editing vendored upstream code. A canonical state fingerprint will combine the effective URL, actionable DOM/form representation, blocker state, and document/artifact/network evidence. The detector resets on any material progress, requests a clean Agent stop only after the configured consecutive-equivalence threshold, and converts that stop into a typed `blocked_no_progress` email-route terminal result through the existing artifact finalizer and route persistence flow.

**Tech Stack:** Python 3, existing Browser Use callbacks/history, existing browser artifact classifier, pytest, retained report corpus and guarded live integration.

## Global Constraints

- Do not modify vendored `tools/browser-use`; use its supported `register_new_step_callback` and `register_should_stop_callback` hooks from the canonical MarketLense browser service.
- Reuse existing artifact finalization, typed terminal evidence, route-memory persistence, route-suppression policy, structured logging, and Browser Use test builders; add no dependencies or synthetic fixtures.
- A single equivalent turn never stops the agent; only three consecutive equivalent observations may stop it.
- Any URL change, actionable DOM/form change, typed blocker change, new document candidate, download/attachment, network-document evidence, or confirmation evidence resets the consecutive counter.
- Add `blocked_no_progress` to canonical typed blocker classification and to configured empirical browser-route suppression classes, so it is retained and can be suppressed only after existing compatible-count/TTL/policy checks.
- Update the acquisition workflow reference and remove only the matching completed backlog entry after fresh tests and a safe live validation run pass.

---

### Task 1: Specify and prove no-progress state semantics

**Files:**

- Create: `src/services/_browser_report_download/_browser_runtime/no_progress.py`
- Modify: `tests/test_browser_report_download_runtime_decomposition.py`
- Modify: `tests/test_browser_report_download_service/test_post_action_verification.py`

**Interfaces:**

- Produces: `BrowserNoProgressDetector.observe(state, model_output) -> BrowserNoProgressObservation` and `BrowserNoProgressDetector.should_stop -> bool`.
- Consumes: Browser Use `BrowserStateSummary`, model output, and deterministic collection of visible actionable DOM/form, blocker, document-candidate, confirmation, downloaded-file, and network evidence.

- [ ] **Step 1: Write failing detector regressions using the existing Browser Use test helper types**

```python
detector.observe(equivalent_state, output)
second = detector.observe(equivalent_state, output)
third = detector.observe(equivalent_state, output)
assert second.should_stop is False
assert third.should_stop is True

for progressed_state in (
    url_changed, form_progressed, new_document_candidate,
    new_network_document, confirmation_observed,
):
    assert detector.observe(progressed_state, output).consecutive_equivalent_turns == 1
    assert detector.should_stop is False
```

- [ ] **Step 2: Run the new detector tests and observe the missing-module failure**

Run: `python -m pytest tests/test_browser_report_download_service/test_post_action_verification.py -k no_progress -q`

Expected: FAIL because the detector does not exist.

- [ ] **Step 3: Implement the minimal immutable fingerprint and detector**

```python
@dataclass(frozen=True)
class BrowserNoProgressObservation:
    state_fingerprint: str
    consecutive_equivalent_turns: int
    should_stop: bool

class BrowserNoProgressDetector:
    def observe(self, state: Any, model_output: Any) -> BrowserNoProgressObservation: ...
```

Hash only normalized scalar summaries; never persist raw DOM, form values, prompts, screenshots, or model prose. Track `last_progress_fingerprint`, count equivalent observations, reset on any constituent progress signal, and require `consecutive_equivalent_turns >= 3` before setting `should_stop`.

- [ ] **Step 4: Re-run the focused detector regressions**

Run: `python -m pytest tests/test_browser_report_download_service/test_post_action_verification.py -k no_progress -q`

Expected: PASS.

### Task 2: Stop the Agent cleanly and return a typed retained terminal result

**Files:**

- Modify: `src/services/_browser_report_download/browser.py`
- Modify: `src/services/_browser_report_download/_browser_runtime/_session_lifecycle/history.py`
- Modify: `src/services/_browser_report_download/_artifact/_classification/workflow.py`
- Modify: `src/services/_browser_report_download/_artifact/_classification/routes.py`
- Modify: `src/services/_browser_report_download/_artifact/_classification/evidence.py`
- Modify: `tests/test_browser_report_download_service/test_identity_and_blockers.py`
- Modify: `tests/test_browser_report_download_service/test_post_action_verification.py`

**Interfaces:**

- Consumes: the Task 1 detector and the existing Agent callback parameters.
- Produces: a normal `BrowserAgentRunResult` whose structured payload includes `route_kind="email_delivery"`, `blocked_reason="blocked_no_progress"`, bounded scalar detail, final page state, and existing terminal assets; artifact finalization returns an inferred `email_required` outcome that the report-download orchestrator persists.

- [ ] **Step 1: Write failing end-to-end service regressions**

```python
response = download_report_with_browser_use(request, run_context)
assert response.outcome == "email_required"
assert response.blocked_reason == "blocked_no_progress"
assert agent.turn_count == 3
assert no_progress_event["fields"]["consecutive_equivalent_turns"] == 3
```

Add a retained-success regression in the same existing suite where a URL, document candidate, form state, network evidence, or confirmation arrives before the threshold; assert it remains on the existing successful path and does not emit a no-progress terminal event.

- [ ] **Step 2: Run those tests and observe that the existing Agent consumes its normal step budget**

Run: `python -m pytest tests/test_browser_report_download_service/test_identity_and_blockers.py tests/test_browser_report_download_service/test_post_action_verification.py -k "no_progress or retained_success" -q`

Expected: FAIL because no-progress is not yet converted to a terminal acquisition result.

- [ ] **Step 3: Wire supported Browser Use callbacks and finalization**

```python
detector = BrowserNoProgressDetector()
agent = browser_use.Agent(
    **agent_kwargs,
    register_new_step_callback=detector.observe_callback,
    register_should_stop_callback=detector.should_stop_callback,
)
history_result = _run_agent_history_with_timeout(..., no_progress_detector=detector)
```

If the Agent stops because the detector tripped, return a `BrowserAgentHistoryResult` carrying that terminal signal and generate a typed structured payload from the detector's bounded state evidence. Preserve ordinary Agent stops, completed histories, timeout salvage, and existing final artifact capture behavior unchanged.

- [ ] **Step 4: Extend canonical terminal classification**

Add `blocked_no_progress` to the classifier's allowed blocker sets and resolve it directly without conflating it with form identity or CAPTCHA blockers. The typed terminal detail must disclose the equivalent-turn count and only hashed/scalar evidence summaries.

- [ ] **Step 5: Re-run focused service regressions**

Run: `python -m pytest tests/test_browser_report_download_service/test_identity_and_blockers.py tests/test_browser_report_download_service/test_post_action_verification.py -q`

Expected: PASS.

### Task 3: Retain learning/suppression and preserve corpus successes

**Files:**

- Modify: `src/contracts/_browser_download/identity.py`
- Modify: `src/config/app.yaml`
- Modify: `src/config/app.example.yaml`
- Modify: `tests/test_acquisition_resource_telemetry.py`
- Modify: `tests/test_report_download_route_memory_ttl.py`

**Interfaces:**

- Consumes: existing compatible route-suppression evaluation and route-memory records.
- Produces: `blocked_no_progress` records that count only under the existing three-compatible-terminal-failure threshold, with no impact on retained successful routes.

- [ ] **Step 1: Write failing route-memory and suppression regressions**

```python
assert record_route_outcome(no_progress_result).blocked_reason == "blocked_no_progress"
assert evaluate_acquisition_route_suppression(two_no_progress_attempts).suppressed is False
assert evaluate_acquisition_route_suppression(three_no_progress_attempts).suppressed is True
assert successful_retained_route.verified_successes == original_verified_successes
```

- [ ] **Step 2: Run the retention/suppression tests and observe missing policy eligibility**

Run: `python -m pytest tests/test_acquisition_resource_telemetry.py tests/test_report_download_route_memory_ttl.py -k no_progress -q`

Expected: FAIL because the new typed terminal class is not policy-eligible.

- [ ] **Step 3: Add the class to the existing policy defaults and YAML controls**

Extend only the existing `terminal_failure_classes` lists and descriptions. Do not change sample size, threshold, TTL, revalidation, or success-recording behavior.

- [ ] **Step 4: Re-run retention and existing success coverage**

Run: `python -m pytest tests/test_acquisition_resource_telemetry.py tests/test_report_download_route_memory_ttl.py -q`

Expected: PASS.

### Task 4: Document, validate live behavior, and integrate

**Files:**

- Modify: `docs/workflows/report-acquisition.md`
- Modify: `CONSOLIDATED_TODO.md`

**Interfaces:**

- Produces: operator documentation, current backlog state, committed change, and fresh evidence for a guarded real Browser Use run plus discovery → acquisition → ingest → publish validation.

- [ ] **Step 1: Update canonical documentation**

Document the three-equivalent-turn threshold, exact progress-reset conditions, typed terminal result, retention/suppression guardrails, and raw-evidence redaction rule.

- [ ] **Step 2: Run focused, affected, and static checks**

Run:

```powershell
python -m pytest tests/test_browser_report_download_service tests/test_browser_report_download_runtime_decomposition.py tests/test_browser_runtime_contract.py tests/test_acquisition_resource_telemetry.py tests/test_report_download_route_memory_ttl.py -q
python -m ruff check src/services/_browser_report_download src/contracts/_browser_download/identity.py tests/test_browser_report_download_service tests/test_acquisition_resource_telemetry.py tests/test_report_download_route_memory_ttl.py
python -m mypy src/services/_browser_report_download src/contracts/_browser_download/identity.py
```

Expected: PASS.

- [ ] **Step 3: Run real provider Browser Use integration and the approved safe end-to-end validation**

Run the existing guarded `tests/integration/test_browser_report_download_service.py::test_browser_report_download_service_local_guarded` with `RUN_BROWSER_DOWNLOAD_INTEGRATION=1` and actual configured provider credentials. Then discover and execute the repository's current safe discovery → acquisition → ingest → publish validation command/profile without public writes. Inspect terminal-resource telemetry and retained artifacts. If any attributable failure occurs, fix it and repeat the affected stage and downstream validation.

- [ ] **Step 4: Remove the completed backlog entry and integrate only after fresh evidence**

Remove the exact matching active task from `CONSOLIDATED_TODO.md`; inspect `git diff --check`, scoped diff, and secret exposure; rerun the relevant checks; commit the scoped files; merge the task branch into `main` only after the fresh suite and live validation evidence pass.
