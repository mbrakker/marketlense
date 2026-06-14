# Effort-Under-Four Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement or evidence-close all simplification backlog items with
effort below 4, verify affected real workflows, and leave unsafe investigations
open with concrete rationale.

**Architecture:** Preserve existing canonical facades and move repeated or
misowned behavior to the nearest existing semantic owner. Combine overlapping
items into six bounded batches so each batch has one verification surface.

**Tech Stack:** Python 3.12, dataclasses, pytest, mypy, ruff, SQLite, Pillow,
OpenAI SDK, PHP/WordPress REST tooling.

---

### Task 1: Record Baseline And Item Disposition

**Files:**
- Modify: `simplification.md`
- Create: `docs/quality/simplification-effort-under-four-baseline-2026-06-13.md`
- Test: `tests/test_backlog_source_gate.py`

- [ ] Enumerate every effort 1-3 item and map it to an implementation batch,
  evidence closure, or investigation keep decision.
- [ ] Record current duplicate counts, direct-I/O findings, facade mutation,
  command count, and affected live artifacts.
- [ ] Run `python -m pytest tests/test_backlog_source_gate.py -q`.

### Task 2: Simplify OpenAI Dependency And Credential Ownership

**Files:**
- Modify: `src/services/openai_service.py`
- Modify: `src/services/_openai_service/base.py`
- Modify: `src/services/_openai_service/client.py`
- Modify: `src/services/llm_service.py`
- Modify: `src/services/vector_store_service.py`
- Modify: `src/services/config_service.py`
- Test: `tests/test_openai_chat_service.py`
- Test: `tests/test_openai_vector_store.py`
- Test: `tests/test_llm_service.py`
- Test: `tests/test_vector_store_service.py`

- [ ] Add failing tests proving provider calls do not depend on facade-to-child
  mutation and credentials resolve through the canonical config/provider path.
- [ ] Run the focused tests and confirm expected failures.
- [ ] Implement explicit provider dependency ownership and remove runtime sync.
- [ ] Replace callable adapter layering where it only forwards operations.
- [ ] Run focused tests and OpenAI integration smoke when configured.

### Task 3: Move Generator And Orchestrator I/O To Existing Services

**Files:**
- Modify: `src/contracts/files.py`
- Modify: `src/contracts/report_assets.py`
- Modify: `src/contracts/ui_run_control.py`
- Modify: `src/services/file_service.py`
- Modify: `src/services/render_service.py`
- Modify: `src/services/ui_run_replay_service.py`
- Modify: `src/generators/report_render_generator.py`
- Modify: `src/generators/report_generation_shared.py`
- Modify: `src/generators/report_context_generator.py`
- Modify: `src/generators/streamlit_dashboard_generator.py`
- Modify: `src/generators/publish_generator.py`
- Modify: `src/orchestrators/ui_run_control_orchestrator.py`
- Test: corresponding focused generator/service/orchestrator tests

- [ ] Add red tests for typed JSON loads, bounded tails, render cache handling,
  media preparation, and UI-run request persistence.
- [ ] Run focused tests and confirm failures are caused by missing service APIs.
- [ ] Implement the minimum service operations and rewire callers.
- [ ] Preserve current cache keys, output paths, image fallback, logs, and
  idempotency behavior.
- [ ] Run focused tests and existing render/dashboard/UI-run live paths.

### Task 4: Consolidate Identical Pure And Private Service Helpers

**Files:**
- Modify: existing files under `src/utils/`, `src/contracts/`, and private
  service-common packages selected by semantic ownership
- Modify: affected generator, SQLite, HTTP, and clock call sites
- Test: focused utility, contract, SQLite, HTTP, and orchestrator tests

- [ ] Add equivalence tests for normalization, ordered uniqueness, deterministic
  JSON, required-field semantics, UTC format, SQLite metadata/locking, and pool
  keys.
- [ ] Confirm each new test fails before moving its production helper.
- [ ] Reuse existing helpers where behavior already matches; leave divergent
  semantics local and document the reason.
- [ ] Add structured cleanup-failure logging and preserve original failures.
- [ ] Run focused tests plus architecture and forbidden-patching gates.

### Task 5: Simplify PDF Internals Without Output Changes

**Files:**
- Modify: `src/services/_pdf/visual_heuristics.py`
- Modify: `src/services/_pdf/_visual_heuristics/panel_text.py`
- Modify: `src/services/_pdf/_visual_heuristics/panel_geometry.py`
- Modify: `src/services/_pdf/table_heuristics.py`
- Modify: `src/services/_pdf/table_candidates.py`
- Modify: existing PDF-private common owner
- Test: PDF decomposition and fixture suites

- [ ] Add ownership/equivalence tests for renamed metric-caption helper, shared
  declarations, chunking/worker/reason helpers, and score/OCR-density helpers.
- [ ] Run tests red before movement.
- [ ] Move symbols without changing bodies or call ordering.
- [ ] Run AST movement audit and PDF fixture/golden tests.
- [ ] Run one existing real PDF candidate extraction and compare outputs.

### Task 6: Consolidate WordPress And Repository Quality Entry Points

**Files:**
- Create: `Wordpress/scripts/marketlense_admin.py`
- Modify: existing WordPress REST scripts into compatibility launchers
- Create: `scripts/quality_gate.py`
- Create: `scripts/refactor_audit.py`
- Create: `scripts/ci/check_role_io_boundaries.py`
- Create: `scripts/ci/check_service_boundary_map.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `docs/quality/repository-analysis-exclusions.md`
- Test: WordPress, gate, architecture, and repository-analysis tests

- [ ] Add red CLI routing and static-gate tests.
- [ ] Implement one WordPress admin CLI while preserving script compatibility.
- [ ] Implement canonical local quality/refactor commands with transparent
  command output and return codes.
- [ ] Promote existing direct-I/O logic into a CI script and add provider
  boundary mapping with owner/expiry allowlists.
- [ ] Document canonical commands and backlog promotion rules.
- [ ] Run WordPress subproject and new gate tests.

### Task 7: Investigation Evidence And Safe Closures

**Files:**
- Modify: `simplification.md`
- Modify: `CONSOLIDATED_TODO.md`
- Modify: `README.md` where current behavior needs clarification

- [ ] Audit compatibility exports, rollout flags, legacy adapters, directory
  walks, prompt/model setup, WordPress migrations, and CSS selectors.
- [ ] Remove only items with static plus runtime evidence of zero dependency.
- [ ] For every retained item, record keep rationale, risk, owner, and review
  date.
- [ ] Remove completed overlaps from the consolidated active TODO.

### Task 8: Full And Live Verification

**Files:**
- Modify only files required by diagnosed regressions

- [ ] Run focused suites for every changed boundary.
- [ ] Run formatting, typing, architecture, forbidden patching, repository
  hygiene, schema, WordPress, full pytest/coverage, mutation, quality regression,
  and prompt fixture commands through the canonical quality command.
- [ ] Run existing live render, dashboard, PDF, OpenAI/vector, and WordPress
  workflows applicable to changed code.
- [ ] Investigate every failure before fixing; add a failing regression test,
  implement the root-cause fix, and rerun.
- [ ] Re-read all 43 entries and confirm each is closed or has a documented
  evidence-based keep rationale.
