# Long-File Semantic Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use Planned markers for archival sequencing.

**Goal:** Decompose five long modules into focused private capability families while preserving public imports, behavior, runtime, logs, external calls, and costs.

**Architecture:** Keep every current module as the compatibility facade inside the existing modular monolith. Move implementation bodies without behavior changes into private sibling packages grouped by stable semantic ownership; add structural tests before movement and record AST/live comparison evidence.

**Tech Stack:** Python 3, dataclasses, sqlite3, asyncio, requests, browser-use/CDP, pytest, Ruff, mypy.

---

### Task 1: SQLite Migration Service

**Files:**
- Create: `tests/test_sqlite_migration_decomposition.py`
- Create: `src/services/_sqlite_migration/runner.py`
- Create: `src/services/_sqlite_migration/reports.py`
- Create: `src/services/_sqlite_migration/state.py`
- Create: `src/services/_sqlite_migration/ui_runs.py`
- Modify: `src/services/sqlite_migration_service.py`

- Planned: Add a structural test requiring shared migration execution, reports DB, state DB, and UI-run registry ownership modules while preserving `apply_reports_db_migrations`, `apply_state_db_migrations`, and `apply_ui_run_registry_migrations`.
- Planned: Run the structural test and confirm failure because the private owners do not exist.
- Planned: Move schema statements and migration functions by database family; keep only compatibility imports in the facade.
- Planned: Run `tests/test_sqlite_migration_service.py`, schema-authority tests, and the structural test.
- Planned: Compare fresh SQLite schemas and migration responses against `HEAD`.

### Task 2: Publisher Candidate Quality Generator

**Files:**
- Create: `tests/test_publisher_inventory_candidate_quality_decomposition.py`
- Create: `src/generators/_publisher_inventory_candidate_quality/classification.py`
- Create: `src/generators/_publisher_inventory_candidate_quality/evaluation.py`
- Create: `src/generators/_publisher_inventory_candidate_quality/workflow.py`
- Modify: `src/generators/publisher_inventory_candidate_quality_generator.py`

- Planned: Add a structural test requiring deterministic URL/title classifiers, observation evaluation/recovery, and generator workflow owners while preserving `qualify_publisher_inventory_candidates`.
- Planned: Run the structural test and confirm failure because the private owners do not exist.
- Planned: Move bodies without changing thresholds, branch order, reasons, logging, contracts, or candidate ordering.
- Planned: Run the complete candidate-quality suite and publisher-inventory orchestrator regressions.
- Planned: Compare canonical responses and runtime against `HEAD` on representative positive, rejection, and recovery fixtures.

### Task 3: Browser Download CDP Service

**Files:**
- Create: `tests/test_browser_report_download_cdp_decomposition.py`
- Create: `src/services/_browser_report_download/_cdp/models.py`
- Create: `src/services/_browser_report_download/_cdp/transport.py`
- Create: `src/services/_browser_report_download/_cdp/session.py`
- Create: `src/services/_browser_report_download/_cdp/dialogs.py`
- Create: `src/services/_browser_report_download/_cdp/operations.py`
- Modify: `src/services/_browser_report_download/cdp.py`

- Planned: Add a structural test requiring models, transport, session/target resolution, dialog policy, and public operation owners while preserving current CDP exports.
- Planned: Run the structural test and confirm failure because the private owners do not exist.
- Planned: Move bodies with unchanged timeout, attachment, target selection, dialog, screenshot, print, and network behavior.
- Planned: Run CDP and browser-download affected suites.
- Planned: Compare deterministic fake-client call sequences, results, and runtime against `HEAD`.

### Task 4: Publisher HTTP Fetch Service

**Files:**
- Create: `tests/test_publisher_inventory_fetch_decomposition.py`
- Create: `src/services/_publisher_inventory_service/_fetch/parsing.py`
- Create: `src/services/_publisher_inventory_service/_fetch/discovery.py`
- Create: `src/services/_publisher_inventory_service/_fetch/inspection.py`
- Create: `src/services/_publisher_inventory_service/_fetch/classification.py`
- Modify: `src/services/_publisher_inventory_service/fetch_service.py`

- Planned: Add a structural test requiring parser, discovery/AJAX, landing inspection, and classification owners while preserving `discover_inventory_via_http`, `inspect_inventory_landing_pages`, and `HTTP_BROWSER_HEADERS`.
- Planned: Run the structural test and confirm failure because the private owners do not exist.
- Planned: Move bodies with unchanged requests, URL ordering, parsing, provenance, classification, and response contracts.
- Planned: Run publisher-inventory HTTP/parsing and workflow suites.
- Planned: Compare local HTTP fixture outputs and runtime against `HEAD`.

### Task 5: Publisher Browser Flow

**Files:**
- Create: `tests/test_publisher_inventory_browser_flow_decomposition.py`
- Create: `src/services/_publisher_inventory_service/_browser_flow/traversal.py`
- Create: `src/services/_publisher_inventory_service/_browser_flow/collection.py`
- Create: `src/services/_publisher_inventory_service/_browser_flow/interactions.py`
- Create: `src/services/_publisher_inventory_service/_browser_flow/supplement.py`
- Modify: `src/services/_publisher_inventory_service/browser_flow.py`

- Planned: Add a structural test requiring traversal, collection, interaction/wait, and HTTP supplement owners while preserving all workflow imports.
- Planned: Run the structural test and confirm failure because the private owners do not exist.
- Planned: Move bodies with unchanged navigation order, timeout budgets, click/scroll behavior, candidate ordering, browser close behavior, and fallback HTTP calls.
- Planned: Run publisher-inventory browser traversal, workflow, service, and orchestrator suites.
- Planned: Compare deterministic browser fixtures and an approved real publisher run against `HEAD`.

### Task 6: Documentation, Audit, And Combined Verification

**Files:**
- Modify: `README.md`
- Modify: `long_scripts.md`
- Create: `docs/architecture/sqlite-migration-decomposition-review.md`
- Create: `docs/architecture/publisher-candidate-quality-decomposition-review.md`
- Create: `docs/architecture/browser-cdp-decomposition-review.md`
- Create: `docs/architecture/publisher-fetch-decomposition-review.md`
- Create: `docs/architecture/publisher-browser-flow-decomposition-review.md`

- Planned: Record per-target AST movement counts, changed-body explanations, facade-owned definitions, line counts, and dependency direction.
- Planned: Run Ruff, mypy, architecture/import gates, forbidden-patching gates, mutation/quality gates where configured, and the full default pytest suite.
- Planned: Run real affected-feature canaries using environment credentials only where the affected path actually requires them; do not call OpenAI or external APIs for paths that are deterministic/local.
- Planned: Commit the verified feature branch.
- Planned: Merge into `main` without staging, reverting, or committing the unrelated WordPress work already present there.
- Planned: Run post-merge verification on `main`.
