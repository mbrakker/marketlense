# Longest Python files (>500 lines)

Generated: 2026-02-22

Files with more than 500 lines (sorted by length):

- 3698 src/services/pdf_service.py
- 3467 src/generators/report_generator.py
- 2958 src/ui/streamlit_pages.py
- 2500 src/generators/validation_generator.py
- 1778 src/generators/evidence_pack_generator.py
- 1571 src/generators/artifact_generator.py
- 1474 src/services/openai_service.py
- 1243 tests/test_artifact_generator.py
- 961 src/services/config_service.py
- 930 tests/test_validation_generator.py
- 915 tests/test_evidence_pack_generator.py
- 807 tests/test_vector_pipeline_wiring.py
- 755 src/orchestrators/ingest_orchestrator.py
- 693 src/services/state_service.py
- 632 src/utils/quantity.py
- 559 src/generators/streamlit_dashboard_generator.py
- 552 src/generators/taxonomy_generator.py
- 543 src/services/report_store_service.py
- 532 src/services/file_service.py
- 514 src/services/wordpress_service.py

Total .py files scanned: 166

## Implementation plans

### 1. Split pdf_service (non-breaking)

TL;DR — Create focused service modules and keep a shim so existing imports keep working. Move I/O, candidate heuristics, cropping, previewing, and figure-selection into separate modules; keep behavior identical and run tests after each step.

Steps

Create modules: add new files src/services/pdf_io_service.py, src/services/pdf_candidate_service.py, src/services/pdf_crop_service.py, src/services/pdf_preview_service.py, src/services/pdf_figure_service.py. — Effort: Low
Add shim: update __init__.py and leave pdf_service.py as a thin shim that re-exports names from the new modules. This preserves current imports/tests. — Effort: Low
Move I/O helpers: extract check_pdf_eof, build_pdf_context, extract_pdf_info, extract_pdf_text, sample_pdf_text + related small helpers into pdf_io_service. Keep dataclass contracts in src/contracts. — Effort: Low
Extract candidate logic (generator role): move collect_candidates and all chart/table heuristics (_extract_charts*, _extract_tables*, validation/dedupe, scoring) into pdf_candidate_service and expose a single collect_candidates API. Keep heavy heuristics and parallel-worker logic together. — Effort: High
Move cropping/refine: move crop_regions, _crop_regions, render_page_for_crop_refine, apply_crop_refine_bbox, strict trimming helpers into pdf_crop_service. — Effort: Medium
Move preview/thumbnail I/O: move render_preview, _page_png, _save_thumb into pdf_preview_service. — Effort: Low
Move figure-selection: move extract_best_figure and helpers into pdf_figure_service (can be thin wrapper calling candidate/preview APIs). — Effort: Low
Constants and utils: either move module tuning constants into a single src/services/pdf_constants.py or localize them in target modules; migrate utility geometry helpers to pdf_utils.py if shared. — Effort: Medium
Run tests and iterate: run full test suite; fix failures by adding temporary re-exports in the shim or updating test imports progressively. Prefer shim-first so most tests pass immediately. Repeat until green. — Effort: Medium
Deprecation cleanup: once stable, convert the shim to a deprecation wrapper or remove it and update imports/tests fully. — Effort: Low
Verification

Run tests after each major move:
Targeted: pytest tests/test_pdf_crop_service.py::... and tests/test_candidate_extraction_generator.py::...
Full: pytest -q
Spot-check integration: ingest flow that calls check_pdf_eof and collect_candidates.
Run a sample ingest on a local PDF to ensure no behavior regressions (manual smoke).
Decisions

Non-breaking approach (shim-first) to preserve existing imports and monkeypatch targets used by tests.
Keep domain heuristics in pdf_candidate_service (generator role) to respect AGENTS.md separation of I/O services vs generators.
Keep contracts in src/contracts to avoid circular imports.
Risks & Mitigations

Risk: import churn and circular imports. Mitigation: keep contracts in src/contracts and use shim re-exports while migrating call sites gradually.
Risk: tests that monkeypatch internal helpers. Mitigation: keep exported names available on shim or update tests to mock the new module paths after migration.
Risk: constants split across modules. Mitigation: centralize constants in pdf_constants or move them with the functions that use them.
Risk: behavioral regressions due to subtle ordering or doc ownership of fitz.Document. Mitigation: maintain doc ownership semantics and add unit tests for PdfContext behavior.
Files to change (minimal first-pass)

add: src/services/pdf_io_service.py, src/services/pdf_candidate_service.py, src/services/pdf_crop_service.py, src/services/pdf_preview_service.py, src/services/pdf_figure_service.py
update: __init__.py (re-exports), keep pdf_service.py as shim initially
optional: src/services/pdf_constants.py or move constants into target modules
Next actions I can take for you

Implement the shim-first split (create new modules and move a first group of functions, run tests). Estimated implementation time: ~3–6 hours iterative (move I/O + shim + tests), full split ~1–2 days.
Or, if you prefer, I can start by extracting pdf_io_service and adding the shim so we can run tests and iterate.

## 2. Split Report Generator

TL;DR — Reduce report_generator.py size by extracting distinct generator responsibilities into focused generator modules and pure utils, keep a shim that preserves generate_report() API, and iterate with tests after each small move. This keeps generator responsibilities (domain assembly/validation) while delegating I/O and side-effects to services per AGENTS.md.

Steps

Create new generator modules (pure domain logic):
src/generators/report_payload_generator.py — build/merge ReportPayload, title/metadata resolution, `_base_payload`, `_merge_artifacts_into_payload`, `_resolve_publisher`, payload validation.
src/generators/report_candidate_selector.py — candidate prefiltering, ranking, `_candidate_*` helpers, `_rank_candidates_batch`, `_split_candidates_by_kind`, `_select_refined_candidate_items`.
src/generators/report_indexing_generator.py — vector-store indexing orchestration (`_start_vector_store_indexing`, `_await_vector_store_indexing`, `_ensure_vector_store` and related state helpers/`_VectorStoreIndexingState`).
src/generators/report_assets_generator.py — wrap calls that create artifacts/evidence packs/cover images: calls to `generate_artifacts`, `generate_evidence_packs`, `generate_cover_images`, and merging results into payload.
src/generators/report_cache_generator.py — cache key helpers and read/write cache helpers (`_cache_dir`, `_read_cache_json`, `_write_cache_json`, `_template_sha256`, `_html_cache_key`).
Extract pure helpers & utils:
Move small pure helpers (slug/title derivation, pick-non-empty text, coercion wrappers) into src/generators/report_utils.py or utils if shared.
Replace large internal classes with dataclass contracts where appropriate:
Move `_VectorStoreIndexingState`, `_TaxonomyCategoryState`, `_RankBatchResult` definitions into either contracts (if shared) or into new generator modules.
Make `generate_report()` a thin coordinator in report_generator.py:
Keep signature unchanged (shim).
Call the new generators in clear sequence (build pdf context → candidate selection → assets → indexing → validation → render/persist).
Reduce direct side-effects in generators:
Ensure file/IO/persistence remains in `src/services/*` (use existing file_service, render_service, report_store_service, rank_service, pdf_service).
If generator currently performs any direct file writes/reads or HTTP calls, replace with calls to the appropriate `src/services/*` function.
Add compatibility shim and incremental migration strategy:
Keep public helper names exported from report_generator.py (re-exports) so tests and callers keep working.
Migrate callers one-by-one if necessary; prefer shim-first to avoid breaking tests that monkeypatch.
Tests & verification after each move:
After step moves, run targeted tests: test_candidate_extraction_generator.py, tests/test_report_generator.py (or related tests), and crop/candidate-related tests.
Full suite: pytest -q when the shim is in place.
Cleanups:
Consolidate constants used by these helpers into src/generators/report_constants.py (or keep them with the module that uses them).
When green, remove re-export shim and update imports to the new modules.
Verification

After moving helpers to report_utils and report_cache_generator, run:
pytest tests/test_candidate_extraction_generator.py::...
pytest tests/test_pdf_crop_service.py::... (spot-check interactions)
Once coordinator shim exists and targeted tests pass, run full suite:
pytest -q
Manual smoke: run ingest for a sample PDF that exercises generate_report() and confirm outputs (HTML + artifacts) match baseline.
Decisions

Non-breaking, shim-first migration to preserve existing import paths and tests.
Keep domain logic in generators (assembly/validation); keep I/O and API calls in `src/services/*` (follow AGENTS.md).
Centralize shared constants where cross-module use appears.
Risks & Mitigations

Risk: import churn / circular imports. Mitigation: keep contracts in contracts and move dataclasses first; use local imports in functions to avoid cycles.
Risk: tests that monkeypatch symbols. Mitigation: keep re-exported names on the original module until tests are updated.
Risk: behavioral regressions in concurrency/indexing order. Mitigation: add unit tests for _VectorStoreIndexingState flows and run integration smoke on ingest after each major change.
Files to change (minimal-first)

Add: src/generators/report_payload_generator.py, src/generators/report_candidate_selector.py, src/generators/report_indexing_generator.py, src/generators/report_assets_generator.py, src/generators/report_cache_generator.py, src/generators/report_utils.py
Update: report_generator.py (make thin coordinator + re-exports)
Optional: src/generators/report_constants.py (centralize constants)

## 3. Split Streamlit Pages

TL;DR — Break streamlit_pages.py into focused UI modules (routing, page renderers, helpers/components, data adapters) while keeping all data access in `src/services/*` and contracts in `src/contracts/*`. Use a shimmed entry `main()` to preserve how Streamlit imports the module. Migrate incrementally with targeted UI tests and manual smoke checks.

Steps

Create focused UI modules under ui:
src/ui/pages/__init__.py — registry of pages and exported main() entrypoint (shim).
src/ui/pages/shell.py — _page_shell, _render_stepper, _inject_theme, layout chrome and global UI pieces.
src/ui/pages/dashboard.py — cockpit overview page and small data views (_render_cockpit_overview).
src/ui/pages/ingest.py — ingest control page and helpers (_render_ingest_control).
src/ui/pages/candidate_extraction.py — candidate extraction UI (_render_candidate_extraction).
src/ui/pages/reports.py — report command center and report-related controls (_render_report_command_center).
src/ui/pages/cover_images.py — cover image page (_render_cover_images).
src/ui/pages/analysis.py — analysis & evidence and taxonomy views (_render_analysis_and_evidence).
src/ui/pages/validation.py — validation center (_render_validation_center).
src/ui/pages/publishing.py — publishing control (_render_publishing_control).
src/ui/pages/category_manager.py — category manager (_render_category_manager).
src/ui/pages/costs.py — cost & usage (_render_cost_and_usage).
src/ui/pages/logs.py — logs & terminal (`_render_logs_and_terminal`, `_append_terminal`, terminal panel).
src/ui/pages/settings.py — settings & prompts, structured config form (`_render_settings_and_prompts`, `_render_structured_config_form`).
src/ui/pages/system.py — system & storage and developer tools (`_render_system_and_storage`, `_render_developer_tools`).
Extract helpers/components into src/ui/components.py:
UI utilities: `_chip_html`, `_tip`, `_to_dicts`, `_ctx`, and small conversion functions (`_as_int`, `_as_str`, `_as_bool`, `_as_utc`).
Small HTML/CSS injection helpers and the terminal widget.
Move data-adapter and file helpers (non-UI logic) into src/ui/adapters.py:
Wrap calls to `src.services.*` and `src.generators.*` used only by UI (e.g., `load_report_rows`, `collect_directory_counts`, `discover_log_files`, `load_mappings`, `list_prompt_namespaces`) so pages call thin adapters returning plain dicts/contract objects. Keep adapters small and pure; they call contracts and services.
Keep all business logic and I/O in existing `src/services/*`, `src/generators/*`, and `src/orchestrators/*`:
Replace any direct file-reading/writing in streamlit_pages.py with calls into adapters or services.
Add a shim entry and incremental migration:
Make streamlit_pages.py a thin shim that imports and calls pages.__init__.main() and re-exports any public helpers tests might import.
Migrate pages one-by-one: pick low-risk pages (theme/shell, dashboard) first.
Test and verification after each move:
Run targeted UI utility tests: pytest tests/test_gui_utils.py and any page-specific tests that exist.
Manual smoke: run the Streamlit app (streamlit run src/ui/streamlit_app.py) and navigate the moved pages verifying no regressions.
Cleanup:
Once all pages are moved and shim is removed, delete large original streamlit_pages.py and update imports across repo.
Optionally split very large page modules (e.g., logs or settings) further into subcomponents.
Verification

After extracting components.py and adapters.py, run:
pytest [test_gui_utils.py](http://_vscodecontentref_/69) -q
Start Streamlit locally:
Click through main pages: Cockpit → Ingest → Candidate Extraction → Logs.
After each page migration, run the targeted generator/orchestrator tests that UI triggers (e.g., ingestion orchestration tests) to ensure adapters didn't change behavior.
Decisions

UI-only code lives in src/ui/*; data access stays in src/services/* / src/generators/* per AGENTS.md.
Shim-first migration to avoid breaking existing imports and tests that may monkeypatch streamlit_pages.
Adapters normalize contract objects for UI consumption so pages remain simple.
Risks & Mitigations

Risk: tests or external code import specific helpers from src.ui.streamlit_pages. Mitigation: keep re-exports on shim module until tests updated.
Risk: circular imports between pages and services. Mitigation: keep adapters as the single call-layer; use local imports inside functions.
Risk: visual regressions (CSS/HTML). Mitigation: keep `_inject_theme` intact and run manual UI smoke-checks.
Files to change (minimal-first)

Add: src/ui/pages/__init__.py, src/ui/pages/shell.py, src/ui/pages/dashboard.py, src/ui/components.py, src/ui/adapters.py
Update: streamlit_pages.py (make shim), src/ui/streamlit_app.py (point to new pages if needed)

## 4. Split Validation Generator

TL;DR — Break validation_generator.py into focused generator modules (validation orchestration, individual validators, caching/adapters, and utils). Preserve public API with a shim in validation_generator.py, keep I/O in `src/services/*` and contracts in `src/contracts/*`, and migrate incrementally with targeted tests (shim-first, low-risk).

Steps

Create new generator modules
src/generators/validation_orchestrator.py — top-level coordinator originally running full validation flows (keeps public entrypoints).
src/generators/validation_rules.py — collection of independent validators (schema checks, asset presence, text quality, figure/table checks) implemented as small functions returning standardized results.
src/generators/validation_pipeline.py — pipeline wiring: composing validators into stages, concurrency control, batch processing helpers, `_RankBatchResult`-style state if present.
src/generators/validation_adapters.py — thin adapters that call `src/services/*` and `src/contracts/*` to fetch artifacts (report rows, files, pdf contexts); normalize outputs for validators.
src/generators/validation_cache.py — cache key helpers, read/write cache and caching policy functions.
Extract pure helpers & types
Move helper functions (coercion, small transforms, result normalization) into src/generators/validation_utils.py or into utils if shared.
Move internal state dataclasses (if reusable) into validation.py so adapters/generators share stable contracts and reduce circular imports.
Keep I/O and side-effects in services
Replace any direct file/DB/network I/O inside the generator with calls to `src/services/*` (`file_service`, `report_store_service`, `pdf_service`, etc.) via the adapters module.
Make validation_generator.py a thin shim
Keep original public functions (and names) exported from validation_generator.py by re-exporting from new modules. This preserves tests and monkeypatch targets.
Migrate incrementally (shim-first)
Move low-risk pieces first: helpers, cache functions, adapters.
Move individual validators next (group by independence, e.g., schema -> assets -> content quality).
Finally move orchestration/parallel logic into validation_orchestrator.py.
After each move, run targeted tests and fix callsites.
Tests & verification
Targeted: pytest [test_validation_generator.py](http://_vscodecontentref_/18) -q and any tests asserting specific validator behavior.
Integration: pytest tests/test_vector_pipeline_wiring.py / other suite tests that invoke validation flows.
Full: pytest -q after shim covers all exports.
Manual smoke: run ingest/validation on one sample report to verify same results.
Cleanup
Once stable and tests pass, remove the shim and update internal imports to new modules.
Consolidate shared constants into src/generators/validation_constants.py if cross-module.
Verification commands

Targeted tests:
Full suite:
Decisions

Shim-first migration to avoid breaking tests that import or monkeypatch validation_generator.
Keep domain validation logic in generators; keep I/O and persistence in services per AGENTS.md.
Promote reusable state/dataclass contracts to contracts to prevent circular imports.
Risks & Mitigations

Import churn / circular imports — Mitigate by moving dataclasses to contracts first and using adapters with local imports.
Tests that monkeypatch internal helpers — Mitigate by keeping re-exported names on the shim until tests are updated.
Behavioral regressions in ordering/concurrency — Add unit tests for pipeline stages and run manual smoke tests after orchestration migration.
Files to add/update (minimal-first)

Add: src/generators/validation_orchestrator.py, src/generators/validation_rules.py, src/generators/validation_pipeline.py, src/generators/validation_adapters.py, src/generators/validation_cache.py, src/generators/validation_utils.py
Update: validation_generator.py (thin shim + re-exports)
Optional: validation.py, src/generators/validation_constants.py

## 5. Split Evidence Pack Generator

TL;DR — Break evidence_pack_generator.py into focused generator modules (I/O adapters, pack assembly, asset rendering, validation, utils), keep a shim so generate_evidence_packs() API and tests keep working, and migrate incrementally with targeted tests after each step. Respect AGENTS.md: generators stay domain logic, `src/services/*` keep I/O and external calls, contracts remain in `src/contracts/*`.

Steps

Add small modules (single-responsibility):
src/generators/evidence_pack_assembly.py — core pack composition: entrypoint orchestration, pack metadata, ordering of evidence items.
src/generators/evidence_pack_assets.py — create/collect evidence assets (screenshots, cropped images, snippets) by calling services; asset metadata.
src/generators/evidence_pack_io.py — cache/key helpers, read/write pack JSON/ZIP via file_service (adapters only; no raw file logic inside main generator).
src/generators/evidence_pack_validation.py — validators that assert pack completeness/consistency (schema, asset presence, size limits).
src/generators/evidence_pack_utils.py — pure helpers: text normalization, hashing, slug/title helpers, small dataclass transforms.
Create thin adapters that call services:
Keep calls to OpenAI, PDF helpers, rendering, and storage in `src/services/*`. Add small adapter functions if the generator previously inlined service logic.
Keep public API via shim:
Replace evidence_pack_generator.py with a thin shim that re-exports generate_evidence_packs and any helper names tests import. This preserves monkeypatch/import targets.
Migrate incrementally (shim-first):
Move pure helpers and cache functions first.
Move asset-collection functions next (they call services heavily).
Move orchestration last (so tests see stable API).
After each small move, run targeted tests and fix imports.
Tests & verification:
Targeted tests: pytest [test_evidence_pack_generator.py](http://_vscodecontentref_/12) -q and any artifact/evidence-related tests.
Integration: run pytest tests/test_artifact_generator.py and related end-to-end checks that use evidence packs.
Manual smoke: generate an evidence pack for one sample report and verify produced ZIP/JSON matches baseline.
Safety rules (per AGENTS.md):
Do not move service-level I/O into generators — call `src/services/*` only.
Move dataclass/state types into contracts if shared to avoid circular imports.
Use local imports inside functions when needed to prevent cycles.
Clean-up:
When stable and tests green, remove shim and update callers to import new modules if desired.
Optionally centralize constants into src/generators/evidence_pack_constants.py.
Rollout plan and effort estimate:
Step 1 (helpers + shim): Low (30–60 mins).
Step 2 (assets adapters): Medium (1–3 hours).
Step 3 (orchestration move + tests): Medium–High (2–6 hours).
Full split and cleanup: 1–2 days depending on test fixes.
Decisions

Shim-first migration to avoid breaking tests and monkeypatch targets.
Keep domain composition in generators; all I/O/external API calls remain in services.
Promote shared dataclasses to contracts before moving orchestrator state.
Risks & Mitigations

Tests monkeypatch generator internals — keep re-exports on shim until tests updated.
Circular imports — mitigate with contracts and local imports.
Behavioral regressions (ordering, rate-limited API calls) — add unit tests for orchestration ordering and run manual smoke with sample data.
Files to add/update (minimal-first)

Add: src/generators/evidence_pack_assembly.py, src/generators/evidence_pack_assets.py, src/generators/evidence_pack_io.py, src/generators/evidence_pack_validation.py, src/generators/evidence_pack_utils.py
Update: evidence_pack_generator.py → thin shim
Optional: src/generators/evidence_pack_constants.py, move dataclasses to contracts if necessary

## 6. Split Artifact Generator

TL;DR — Break artifact_generator.py into focused generator modules (asset assembly, rendering/adapters, caching/IO, validation, utils), keep a shim so the public API and test monkeypatch targets remain stable, and migrate incrementally with tests after each small move. Respect AGENTS.md: keep domain composition in generators, keep I/O/external calls in `src/services/*`, and put shared dataclasses/contracts in `src/contracts/*`.

Steps

Create focused generator modules:
src/generators/artifact_assembly.py — core orchestration and pack composition, public entrypoints (thin orchestration).
src/generators/artifact_renderers.py — calls that convert asset specs into images/files (wraps service calls; minimal logic).
src/generators/artifact_adapters.py — adapters that call `src/services/*` (file_service, render_service, openai_service, pdf_service) and normalize results for assembly.
src/generators/artifact_io.py — cache/key helpers, read/write artifact payloads and ZIP packaging via file_service (no raw file-system logic inside generators).
src/generators/artifact_validation.py — validators for artifact completeness, size limits, schema checks.
src/generators/artifact_utils.py — pure helpers (slug, hashing, small transforms, dataclass -> dict).
Move types & contracts:
Promote any shared dataclasses/state types to contracts (e.g., ArtifactItem, ArtifactPayload) before moving code to avoid circular imports.
Shim-first migration:
Keep artifact_generator.py as a shim that re-exports generate_artifacts and any helper names tests or other modules import.
Migrate code in small batches (utils + adapters → renderers → assembly → io → validation).
Minimize behavior change:
Preserve function signatures and concurrency behavior while migrating.
Replace any direct I/O in the generator with adapter/service calls.
Concurrency & error handling:
If the file contains thread/async orchestration, extract that orchestration into artifact_assembly.py with clear retry/error taxonomy and unit tests for failure modes.
Tests & verification after each move:
Targeted tests: pytest [test_artifact_generator.py](http://_vscodecontentref_/14) -q and pytest tests/test_artifact_* related.
Integration: run suites that call artifact code (artifact/evidence pack/report tests).
Full suite: pytest -q once shim covers all exports.
Manual smoke: produce artifacts for a sample report and compare expected outputs.
Cleanup:
Once green, remove the shim and update callers to import new modules if desired.
Consolidate cross-module constants into src/generators/artifact_constants.py or leave with the module that uses them.
Verification

Run targeted tests after small moves:
pytest [test_artifact_generator.py](http://_vscodecontentref_/16) -q
Run integration/manual:
produce artifacts for a sample report; verify ZIP/paths match baseline.
Full:
pytest -q
Decisions

Shim-first, non-breaking migration to avoid breaking imports/monkeypatches.
Generators keep domain logic; services keep I/O (per AGENTS.md).
Promote shared dataclasses to contracts before moving orchestration to avoid circular imports.
Risks & Mitigations

Import churn / circular imports — Mitigate by moving dataclasses to contracts and using local imports where needed.
Tests that monkeypatch internals — Keep re-exports on the shim until tests are updated.
Behavioral regressions (ordering, batching, rate-limits) — Add unit tests for orchestration ordering and run manual smoke with representative inputs.
Files to add/update (minimal-first)

Add: src/generators/artifact_assembly.py, src/generators/artifact_renderers.py, src/generators/artifact_adapters.py, src/generators/artifact_io.py, src/generators/artifact_validation.py, src/generators/artifact_utils.py
Update: artifact_generator.py → thin shim
Optional: src/generators/artifact_constants.py, promote types to contracts

## 7. Split OpenAI Service

TL;DR — Reduce openai_service.py by extracting a low-level SDK client, response/formatting helpers, caching, and batching/rate-limit logic into focused modules. Keep a shim in openai_service.py to preserve existing public API and tests, and migrate incrementally with targeted tests and careful secret redaction.

Steps

Add low-level client wrapper
Create src/services/openai_client.py: single-responsibility wrapper that constructs the SDK client, performs raw calls, handles retries/backoff, and centralizes request/response logging (sanitized).
Move direct SDK usage from openai_service.py into this file.
Extract response parsing & JSON/schema helpers
Create src/services/openai_formatting.py: JSON-mode parsing, strict schema validation helpers, normalization/coercion, and defensive fallbacks currently inline in openai_service.py.
Extract caching & deduplication
Create src/services/openai_cache.py: request hashing, memoization, TTL policy, and cache key helpers used by expensive prompt calls.
Extract batching / concurrency / rate-limiting
Create src/services/openai_batching.py: worker pool orchestration, batching logic, per-model rate limit handling; keep implementation small and testable.
Keep prompt rendering / prompt text out of service
Ensure prompt text loading/rendering remains the responsibility of the existing prompt service (prompt_service.py) — openai_* modules should accept rendered prompt strings or prompt request contracts.
Make openai_service.py a thin compatibility shim
Re-export top-level public functions and names from the new modules so existing imports and tests (including any monkeypatches) keep working during migration.
Move shared dataclasses / contracts if needed
If any request/response dataclasses are currently defined inside openai_service.py, promote them to contracts to avoid circular imports.
Tests & verification after each step
After extracting openai_client.py and making the shim: run targeted tests that reference OpenAI behavior.
Targeted: pytest [test_openai_vector_store.py](http://_vscodecontentref_/3) -q and any tests that import openai_service.
Full: pytest -q once the shim covers all exports.
Cleanup
When green, remove the shim and update call sites to import the smaller modules directly.
Verification

Run targeted tests after first move:
pytest test_openai_vector_store.py -q
pytest test_prompt_service.py -q (if prompt integration exists)
Run full suite once migration is complete:
pytest -q
Manual smoke: run a known flow that calls the service (e.g., a small ingest or vector-index flow) and confirm outputs and logged request IDs.
Decisions

Shim-first non-breaking migration to preserve import/monkeypatch stability.
Keep prompt rendering and prompt-version logging inside prompt_service.
Centralize secret redaction and structured logging in openai_client.py.
Risks & Mitigations

Risk: secrets/keys logged. Mitigation: centralize and enforce redaction in openai_client.py.
Risk: circular imports. Mitigation: move request/response dataclasses into contracts and use local imports inside functions when needed.
Risk: tests that monkeypatch internals. Mitigation: keep re-exports on the shim until tests are updated.
Risk: changed model-selection semantics. Mitigation: keep resolve_model() usage and model-mapping stable; add unit tests for model resolution behavior.
Files to add/update (minimal-first)

Add: src/services/openai_client.py, src/services/openai_formatting.py, src/services/openai_cache.py, src/services/openai_batching.py
Update: openai_service.py → thin shim re-exporting public API
Optional: promote dataclasses to openai.py
