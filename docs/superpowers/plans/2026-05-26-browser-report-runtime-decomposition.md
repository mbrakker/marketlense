# Browser Report Runtime Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 4,004-line private browser-report runtime into focused internal capability modules while preserving browser-download behavior, costs, timing, and the existing public boundary.

**Architecture:** Keep `src/services/_browser_report_download/browser.py` as the runtime coordinator used by `browser_report_download_service.py` and `browser_worker.py`. Extract its existing function families byte-for-byte into `_browser_runtime/` modules, import them back for compatibility, and use existing boundary tests plus a guarded live fixture run to establish non-regression.

**Tech Stack:** Python 3, dataclasses, pytest, browser-use/OpenRouter integration, repository CI scripts.

---

### Task 1: Structural Ownership Test

**Files:**
- Create: `tests/test_browser_report_download_runtime_decomposition.py`

- [ ] **Step 1: Write the failing ownership test**

```python
from __future__ import annotations

import ast
from pathlib import Path


CAPABILITY_MODULE_FUNCTIONS = {
    "terminal_state.py": {
        "_capture_terminal_snapshot",
        "_stabilize_terminal_snapshot",
        "_assess_terminal_snapshot_quorum",
    },
    "terminal_assets.py": {
        "_materialize_external_artifacts",
        "_capture_terminal_assets",
        "_collect_network_events",
    },
    "timeout_recovery.py": {
        "_salvage_timed_out_browser_run",
        "_attempt_lookup_submission_assist_with_timeout",
    },
    "worker_protocol.py": {
        "_run_browser_report_download_agent_subprocess",
        "_deserialize_browser_agent_run_result",
    },
    "session_lifecycle.py": {
        "_run_agent_history_with_timeout",
        "_prepare_browser_for_shutdown",
        "_kill_browser",
    },
}


def _top_level_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_browser_runtime_uses_focused_private_capability_modules() -> None:
    package_dir = Path("src/services/_browser_report_download/_browser_runtime")
    coordinator_functions = _top_level_functions(
        Path("src/services/_browser_report_download/browser.py")
    )

    assert package_dir.joinpath("__init__.py").is_file()
    for file_name, owned_functions in CAPABILITY_MODULE_FUNCTIONS.items():
        module_path = package_dir / file_name
        assert module_path.is_file()
        assert owned_functions <= _top_level_functions(module_path)
        assert coordinator_functions.isdisjoint(owned_functions)
```

- [ ] **Step 2: Run test to verify it fails before extraction**

Run: `python -m pytest tests/test_browser_report_download_runtime_decomposition.py -q`

Expected: failure because `_browser_runtime/__init__.py` and the five capability modules do not exist.

### Task 2: Extract Stable Runtime Families

**Files:**
- Create: `src/services/_browser_report_download/_browser_runtime/__init__.py`
- Create: `src/services/_browser_report_download/_browser_runtime/terminal_state.py`
- Create: `src/services/_browser_report_download/_browser_runtime/terminal_assets.py`
- Create: `src/services/_browser_report_download/_browser_runtime/timeout_recovery.py`
- Create: `src/services/_browser_report_download/_browser_runtime/worker_protocol.py`
- Create: `src/services/_browser_report_download/_browser_runtime/session_lifecycle.py`
- Modify: `src/services/_browser_report_download/browser.py`

- [ ] **Step 1: Create the private capability package declaration**

```python
"""Internal runtime capabilities for browser-report acquisition.

The package isolates terminal inspection, evidence acquisition, bounded
recovery, worker transport, and browser lifecycle mechanics while preserving
``browser_report_download_service`` as the single external-system boundary.
"""
```

- [ ] **Step 2: Move existing function families without behavioral edits**

Move the current bodies and their local constants/classes exactly as follows:

```python
RUNTIME_OWNERSHIP = {
    "terminal_state.py": (
        "TerminalSnapshot",
        "TerminalStabilizationPolicy",
        "TerminalQuorumAssessment",
        "_capture_terminal_snapshot",
        "_stabilize_terminal_snapshot",
        "_terminal_stabilization_reason",
        "_resolve_terminal_stabilization_policy",
        "_assess_terminal_snapshot_quorum",
        "_assessment_meets_terminal_quorum",
        "_terminal_quorum_text",
        "_dedupe_labels",
        "_contains_transient_terminal_marker",
        "_merge_terminal_snapshots",
    ),
    "terminal_assets.py": (
        "_prefetch_structured_pdf_artifact",
        "_materialize_external_artifacts",
        "_parse_raw_model_response",
        "_capture_terminal_assets",
        "_capture_terminal_dialog_evidence",
        "_maybe_capture_print_pdf_fallback",
        "_capture_completed_history_terminal_assets",
        "_collect_network_resource_urls",
        "_collect_network_events",
        "_resolve_current_page",
        "_read_history_final_page_url",
        "_read_history_final_page_title",
        "_read_history_attachment_paths",
        "_copy_history_screenshot",
        "_write_terminal_html_snapshot",
        "_run_awaitable",
    ),
    "timeout_recovery.py": (
        "_salvage_timed_out_browser_run",
        "_build_cached_timed_out_browser_run",
        "_salvage_timed_out_browser_run_unbounded",
        "_should_attempt_lookup_submission_assist",
        "_attempt_lookup_submission_assist_with_timeout",
    ),
    "worker_protocol.py": (
        "BrowserAgentWorkerPayload",
        "BrowserAgentWorkerResponse",
        "_should_run_browser_agent_in_subprocess",
        "_run_browser_report_download_agent_subprocess",
        "_discard_browser_agent_worker_payload",
        "_normalize_browser_worker_output_excerpt",
        "_deserialize_browser_agent_run_result",
    ),
    "session_lifecycle.py": (
        "BrowserAgentHistoryResult",
        "_SyntheticAgentHistory",
        "_run_agent_history_with_timeout",
        "_resolve_agent_run_timeout_seconds",
        "_prepare_browser_for_shutdown",
        "_cleanup_browser_profile_dir",
        "_cleanup_stale_browser_use_temp_dirs",
        "_cleanup_new_browser_use_temp_dirs",
        "_kill_browser",
        "_kill_browser_with_timeout",
        "_force_stop_local_browser_process",
    ),
}
```

Include private supporting helpers adjacent to the family that calls them.
Do not change statements inside moved function/class bodies; only adjust
imports needed to resolve the same collaborators.

- [ ] **Step 3: Preserve coordinator and compatibility imports**

Keep the coordinator function and runtime loader/error mapping in
`browser.py`, and import current compatibility-visible names:

```python
from src.services._browser_report_download._browser_runtime.session_lifecycle import (
    _STALE_BROWSER_USE_TEMP_DIR_MIN_AGE_SECONDS,
    _kill_browser,
    _prepare_browser_for_shutdown,
)
from src.services._browser_report_download._browser_runtime.worker_protocol import (
    _BROWSER_AGENT_WORKER_ENV,
    BrowserAgentWorkerResponse,
    _run_browser_report_download_agent_subprocess,
)
```

`browser.py` also continues importing `psutil`, `subprocess`, `tempfile`, and
`time` so current external-boundary tests retain their supported patch surface
while the moved modules use the same shared module objects.

- [ ] **Step 4: Run the ownership and browser-download tests**

Run:

```powershell
python -m pytest tests/test_browser_report_download_runtime_decomposition.py tests/test_browser_report_download_artifact_decomposition.py tests/test_browser_report_download_service tests/test_browser_report_download_doc_type_predictor.py tests/test_browser_report_download_cdp.py tests/test_browser_download_helpers.py tests/test_browser_developer_diagnostics.py tests/test_browser_use_local_browser_watchdog.py -q
```

Expected: all selected tests pass.

### Task 3: Verify Adjacent Workflow Contracts

**Files:**
- Verify only: `tests/test_report_download_route_planner.py`
- Verify only: `tests/test_report_download_orchestrator.py`
- Verify only: `tests/integration/test_browser_report_download_service.py`

- [ ] **Step 1: Run affected workflow synthetic tests**

Run:

```powershell
python -m pytest tests/test_report_download_route_planner.py tests/test_report_download_orchestrator.py -q
```

Expected: all tests pass with unchanged result and retry/idempotency behavior.

- [ ] **Step 2: Run static and type validation**

Run:

```powershell
python scripts/ci/check_split_symbol_links.py
python scripts/ci/check_forbidden_patching.py
python scripts/ci/check_formatting.py
python scripts/ci/run_type_check.py
python scripts/ci/check_repository_hygiene.py
```

Expected: each command exits with status `0`, or an environmental blocker is
reported with its command output.

- [ ] **Step 3: Run the default synthetic regression suite**

Run: `python -m pytest -q`

Expected: all non-integration tests pass.

### Task 4: Document And Measure The Split

**Files:**
- Modify: `README.md`
- Modify: `long_scripts.md`

- [ ] **Step 1: Update the README boundary description**

Extend the existing browser-download architecture paragraph with:

```text
The browser runtime coordinator remains in `browser.py`; terminal-state
stabilization, terminal asset/evidence capture, bounded timeout recovery,
worker transport, and browser session lifecycle mechanics now live under
`_browser_report_download/_browser_runtime/` as private capabilities.
```

- [ ] **Step 2: Refresh long-file evidence**

Run: `python scripts/count_long_files.py --min-lines 500`

Update `long_scripts.md` to replace the prior `browser.py` count and identify
any extracted runtime module that remains above the review threshold.

- [ ] **Step 3: Check documentation diffs**

Run: `git diff --check -- README.md long_scripts.md`

Expected: exit status `0`.

### Task 5: Execute The Bounded Live Gate

**Files:**
- Verify only: `tests/integration/test_browser_report_download_service.py`

- [ ] **Step 1: Run the approved live fixture integration**

Run:

```powershell
$env:RUN_BROWSER_DOWNLOAD_INTEGRATION='1'
python -m pytest -m integration tests/integration/test_browser_report_download_service.py -q
```

Expected: pass when `OPENROUTER_API_KEY` and browser-use dependencies are
configured; otherwise record the explicit skip/blocker and do not claim live
verification.

- [ ] **Step 2: Report evidence**

Report the synthetic command outcomes, the live test outcome or explicit
configuration blocker, the new line counts, and any remaining risk without
claiming absolute proof of performance or quality equivalence beyond the
unchanged execution code and completed verification evidence.
