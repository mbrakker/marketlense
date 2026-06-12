# Runtime Long Module Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use Planned markers for archival sequencing.

**Goal:** Split the requested long runtime modules into semantic private owner modules while preserving public imports, behavior, costs, call ordering, and external side effects.

**Architecture:** Existing public modules stay as compatibility facades or canonical private-family entrypoints. Extracted modules remain inside the same bounded context and do not create new external service boundaries or alternate workflow paths.

**Tech Stack:** Python, pytest, Ruff, existing contract/service/generator/orchestrator architecture.

---

### Task 1: Red Ownership Guard

**Files:**
- Modify: `tests/test_long_script_decomposition.py`

- Planned: Add the seven requested runtime files to the long-script decomposition guard with expected semantic owner modules.
- Planned: Run `pytest -q tests/test_long_script_decomposition.py` and confirm it fails because the requested files still exceed the facade threshold or expected owner modules do not exist.

### Task 2: Movement-Only Splits

**Files:**
- Modify facades:
  - `src/services/_browser_report_download/_browser_runtime/terminal_assets.py`
  - `src/orchestrators/_report_download_orchestrator/route_planner.py`
  - `src/orchestrators/report_generation_orchestrator.py`
  - `src/services/wordpress_service.py`
  - `src/services/render_service.py`
  - `src/services/_pdf/_visual_candidates/extraction.py`
  - `src/services/_browser_report_download/_artifact/classification.py`
- Create private owner modules under existing capability families only.

- Planned: Move contiguous top-level functions/classes into semantically named private modules.
- Planned: Preserve original module import paths as compatibility facades.
- Planned: Do not change thresholds, ordering, retry behavior, prompt/model usage, logging event names, cache keys, artifact paths, or external call counts.

### Task 3: Synthetic Verification

**Files:**
- No production behavior edits unless tests expose a movement error.

- Planned: Run targeted tests for WordPress, render, report-generation, route planner, browser download runtime/artifact classification, and PDF visual candidates.
- Planned: Run changed-file Ruff checks and formatting checks.
- Planned: Run full `pytest -q`.
- Planned: Run repository split/import guard scripts that cover changed files.

### Task 4: Live Verification

**Files:**
- No code edits expected.

- Planned: Load local `.env` into the process without printing secrets.
- Planned: Run available live/integration checks for affected external boundaries and real local fixtures.
- Planned: Record any unavailable live path explicitly rather than substituting dummy tests.

### Task 5: Audit, Docs, Commit

**Files:**
- Modify: `long_scripts.md`
- Modify: `README.md`

- Planned: Refresh the long-file audit from `python scripts/count_long_files.py --min-lines 500`.
- Planned: Record AST movement audit counts against `HEAD`.
- Planned: Update README architecture notes for the new internal splits.
- Planned: Commit the verified movement-only decomposition.
