# Browser Action Evidence Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote browser route playbooks only from execution-layer action evidence, never from model-supplied route evidence.

**Architecture:** The browser service will record an action trace from Browser Use history and deterministic playbook execution. Each record pairs a successfully acted-on browser locator with the immediately subsequent URL or DOM state. The artifact classifier will retain that trace separately from model route prose, and promotion will use only the trace.

**Tech Stack:** Python, dataclasses, Browser Use runtime history, pytest.

## Global Constraints

- Do not persist configured identity values; retain `${identity.<key>}` references only.
- A missing, multi-action, failed, or unverified execution record is not promotable.
- Final terminal state may prove only the final executed action.
- Update the report-acquisition documentation and generated contract reference when contract fields change.

---

### Task 1: Capture execution-bound browser action evidence

**Files:**
- Modify: `src/services/_browser_report_download/models.py`
- Modify: `src/services/_browser_report_download/browser.py`
- Create: `src/services/_browser_report_download/_browser_runtime/action_evidence.py`
- Test: `tests/test_browser_report_download_service/test_post_action_verification.py`

- [ ] Write a failing test that supplies a completed Browser Use history with a resolved button and an immediate post-action browser state and asserts a browser-generated locator and URL/DOM evidence record.
- [ ] Run the focused test and observe its missing-capture failure.
- [ ] Implement the minimal history extractor: accept only a single successful executable action per history entry; derive a locator from `interacted_element`; bind the following history state to all non-terminal actions and the immediate browser snapshot only to the final action.
- [ ] Run the focused test and observe it pass.

### Task 2: Use only execution evidence for promotion

**Files:**
- Modify: `src/contracts/_browser_download/runtime.py`
- Modify: `src/services/_browser_report_download/_artifact/_classification/routes.py`
- Modify: `src/services/_browser_report_download/playbooks.py`
- Test: `tests/_test_browser_route_playbooks/cases_01_safe_promotion.py`

- [ ] Write failing promotion tests proving a fabricated model `locator_evidence` cannot promote and a fully execution-evidenced completed route can promote.
- [ ] Run the focused tests and observe the fabricated route incorrectly promoting or the execution trace being unavailable.
- [ ] Add a distinct execution-bound route-step collection to the browser result; promotion must reject absent/incomplete traces and build the playbook from that collection only.
- [ ] Run the focused tests and observe both pass.

### Task 3: Preserve contracts, documents, and validation evidence

**Files:**
- Modify: `docs/workflows/report-acquisition.md`
- Modify: `src/playbooks/browser_routes/README.md`
- Modify: `docs/quality/contract_schemas.json` (generated)
- Modify: `CONSOLIDATED_TODO.md` only if this work has an active matching item

- [ ] Regenerate contract/document references through `python scripts/docs/generate_references.py` if the generator reports a changed derived reference.
- [ ] Run the focused browser and playbook tests, then the prescribed safe live discovery → acquisition → ingest → publish validation workflow with real browser/LLM calls.
- [ ] Inspect the diff for scope and secret exposure, remove a matching completed backlog item if present, commit on the current branch, and merge only when a non-main integration branch is available.
