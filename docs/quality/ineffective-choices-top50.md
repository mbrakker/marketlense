# Repository Analysis: Top 50 Ineffective Choices (Low Effort, High Impact)

<<<<<<< ours
Status: merged into `CONSOLIDATED_TODO.md` on 2026-03-08. Treat the consolidated todo as the actionable backlog; keep this file as the detailed source analysis behind those tasks.

Method: static repository scan focused on maintainability, reliability, and architecture drift. Prioritized by expected impact/effort ratio.

## A) Monolithic modules (split-first wins)

1. `src/services/pdf_service.py` is 3698 lines (monolith risk; hard to test and reason about). **Low effort win:** split by capability (extract text, extract figures, crop, contents).  
2. `src/generators/report_generator.py` is 3468 lines and centralizes too many report responsibilities. **Low effort win:** extract candidate ranking/refinement/finalization sub-generators.  
3. `src/ui/streamlit_pages.py` is 2967 lines, creating high UI change risk. **Low effort win:** split by page/section modules.  
4. `src/generators/validation_generator.py` is 2500 lines; validations are bundled in one place. **Low effort win:** split checks into composable validators.  
5. `src/generators/evidence_pack_generator.py` is 1778 lines. **Low effort win:** split pack-specific logic into per-pack modules.  
6. `src/generators/artifact_generator.py` is 1598 lines. **Low effort win:** separate schema loading, model call handling, and post-processing.  
7. `src/services/openai_service.py` is 1474 lines and combines many OpenAI interaction patterns. **Low effort win:** split request-types into submodules while keeping one service facade.  
8. `src/services/config_service.py` is 968 lines with large inline normalization logic. **Low effort win:** move section-normalizers into private helpers.  
9. `src/orchestrators/ingest_orchestrator.py` is 755 lines. **Low effort win:** extract retry/state transition helpers.  
10. `src/services/state_service.py` is 693 lines. **Low effort win:** separate read/write/query concerns into smaller units.

## B) Oversized functions (highest refactor ROI)

11. `generate_report` spans ~1637 lines in `src/generators/report_generator.py` (starts around line 1832). **Low effort win:** split by phase with typed intermediate contracts.  
12. `_render_structured_config_form` spans ~641 lines in `src/ui/streamlit_pages.py` (starts around line 1901). **Low effort win:** section-level render helpers.  
13. `_select_refined_candidate_items` spans ~630 lines in `src/generators/report_generator.py`. **Low effort win:** isolate ranking, filtering, and crop-refine decision trees.  
14. `load_settings` spans ~500 lines in `src/services/config_service.py` (starts at line 341). **Low effort win:** table-driven field mapping with validators.  
15. `generate_artifacts` spans ~451 lines in `src/generators/artifact_generator.py`. **Low effort win:** split per artifact type.  
16. `run_publish` spans ~378 lines in `src/orchestrators/publish_orchestrator.py`. **Low effort win:** extract state transition pipeline.  
17. `run_ingest` spans ~373 lines in `src/orchestrators/ingest_orchestrator.py`. **Low effort win:** extract per-file execution function with retry wrapper.  
18. `run_ingest_file` spans ~372 lines in `src/orchestrators/ingest_file_orchestrator.py`. **Low effort win:** factor out setup/teardown/error mapping.  
19. `_generate_pack` spans ~341 lines in `src/generators/evidence_pack_generator.py`. **Low effort win:** split prompt-call/normalize/validate steps.  
20. `validate_report` spans ~319 lines in `src/generators/validation_generator.py`. **Low effort win:** compose validators via registry.  
21. `extract_taxonomy` spans ~259 lines in `src/generators/taxonomy_generator.py`. **Low effort win:** isolate extraction, cleanup, and validation passes.  
22. `_inject_theme` spans ~232 lines in `src/ui/streamlit_pages.py`. **Low effort win:** move CSS/template assets out of function body.  
23. `_run_grounding_check` spans ~231 lines in `src/generators/validation_generator.py`. **Low effort win:** split I/O from semantic scoring.  
24. `_render_settings_and_prompts` spans ~229 lines in `src/ui/streamlit_pages.py`. **Low effort win:** separate settings and prompt tabs into dedicated modules.  
25. `analyze_report` spans ~225 lines in `src/services/openai_service.py`. **Low effort win:** split request prep, API call, and response adaptation.

## C) Broad exception usage and hidden failure modes

26. `src/services/pdf_service.py` contains very high `except Exception` usage (56 matches), which can mask root causes. **Low effort win:** replace with typed AppError mapping per boundary.  
27. `src/services/openai_service.py` has 16 broad exception catches. **Low effort win:** isolate provider/parse/cost-ledger errors with specific codes.  
28. `src/ui/streamlit_pages.py` has 14 broad catches. **Low effort win:** centralize UI error rendering and preserve error taxonomy.  
29. `src/generators/report_generator.py` has 10 broad catches. **Low effort win:** narrow catches around only recoverable branches.  
30. `src/services/file_service.py` has 8 broad catches. **Low effort win:** map file-not-found/permission/encoding separately.  
31. `src/services/lock_service.py` has 5 broad catches. **Low effort win:** split lock contention vs filesystem failure paths.  
32. `src/services/drive_service.py` has 5 broad catches. **Low effort win:** preserve upstream API error details instead of generic exceptions.  
33. `src/orchestrators/ingest_orchestrator.py` has 5 broad catches. **Low effort win:** explicitly retry only retryable AppError types.  
34. `src/services/wordpress_service.py` includes broad catches around response parsing. **Low effort win:** strict response schema validation and typed errors.  
35. `src/services/report_store_service.py` has broad catches for DB edges. **Low effort win:** map sqlite operational/integrity errors explicitly.

## D) Test integrity and brittleness hotspots

36. Tests currently use `monkeypatch.setattr` heavily (189 total), increasing risk of mocked narratives over behavior validation. **Low effort win:** replace top mocked flows with boundary fakes + integration assertions.  
37. `tests/test_vector_pipeline_wiring.py` alone has 60 monkeypatches. **Low effort win:** introduce fixture-driven in-memory boundary adapters.  
38. `tests/test_ingest_parallel.py` has 15 monkeypatches. **Low effort win:** keep one true pipeline path and patch only network/time boundaries.  
39. `tests/test_candidate_extraction_orchestrator.py` has 14 monkeypatches. **Low effort win:** move repeated patches to reusable boundary fixtures.  
40. `tests/test_publish_orchestrator.py` has 11 monkeypatches. **Low effort win:** assert state transitions and retry counts on real orchestration path.  
41. `tests/test_openai_vector_store.py` has 10 monkeypatches. **Low effort win:** test with service-level fake transport instead of patching internals.  
42. `tests/test_candidate_refine_selection.py` has 10 monkeypatches. **Low effort win:** push deterministic inputs through real selection logic.  
43. `tests/test_wordpress_service.py` has 8 monkeypatches. **Low effort win:** replace with requests mock adapter fixture at HTTP boundary.  
44. `tests/test_publish_generator.py` has 8 monkeypatches. **Low effort win:** assert generated contract completeness plus one side effect.  
45. `tests/test_vector_pipeline_wiring.py` mutates import path via `sys.path.append(...)` (line 9), which is fragile and environment-dependent. **Low effort win:** rely on project packaging/pytest config only.

## E) Cross-role coupling and maintainability quick wins

46. `src/services/openai_service.py` performs cost-ledger writes (`append_cost_entry`, `rollup_daily`) inside model-call service path, coupling OpenAI and accounting concerns. **Low effort win:** emit cost event and let orchestrator/service subscriber persist ledger.  
47. `src/cli.py` includes 33 direct `console.print(...)` calls, causing duplicated status formatting logic. **Low effort win:** centralize console rendering utilities.  
48. `src/services/config_service.py` contains many hardcoded defaults inline (e.g., rank thresholds and content keywords), making behavior drift from YAML likely. **Low effort win:** keep defaults in config schema constants and generate docs from source.  
49. `src/ui/streamlit_pages.py` and `src/generators/report_generator.py` both contain very large control-flow branches, making onboarding and defect localization expensive. **Low effort win:** extract branch strategies into named policy helpers.  
50. Repository includes committed operational log artifacts under `logs/` (`long_events_30s.csv/json`), which are usually generated outputs and add noise/churn. **Low effort win:** move to ignored artifacts or docs snapshots with retention rationale.

---

## Notes on prioritization

- **Do first (highest return):** items 11, 14, 26, 36, 46.
- **Do next:** items 1–10 (module split plan), then 37–45 (test hardening).
- **Expected outcome:** lower defect rate, faster PR review, better CI trust, and easier role-boundary enforcement.
=======
Method: static repository scan focused on maintainability, reliability, architecture boundaries, and test integrity. Prioritized by impact/effort ratio.

Format for each item:
- **Context**: why this is ineffective today.
- **Expected**: what should exist instead.
- **Success criteria**: measurable end-state to close the item.

## A) Monolithic modules (split-first wins)

### 1) `src/services/pdf_service.py` is 3698 lines
- **Context:** One service file aggregates many PDF concerns, increasing regression blast radius.
- **Expected:** Keep one PDF service role, but split internal implementation by capability behind a stable facade.
- **Success criteria:** New submodules for text/figures/crop/contents; each submodule has targeted tests and no behavior regression.

### 2) `src/generators/report_generator.py` is 3468 lines
- **Context:** Many report-generation phases are coupled in one generator.
- **Expected:** Phase-oriented generator composition (selection, refinement, rendering, persistence signals).
- **Success criteria:** Main `generate_report` flow becomes an orchestrated sequence of smaller functions/contracts; complexity and review time drop.

### 3) `src/ui/streamlit_pages.py` is 2967 lines
- **Context:** UI logic for many screens lives in one file.
- **Expected:** Split by page/feature module with shared UI helpers.
- **Success criteria:** Per-page files with clear ownership; page-level tests can run independently.

### 4) `src/generators/validation_generator.py` is 2500 lines
- **Context:** Validation checks are tightly bundled, making incremental changes risky.
- **Expected:** Validator registry + composable rule modules.
- **Success criteria:** New check can be added without touching large control blocks; failures report check identity consistently.

### 5) `src/generators/evidence_pack_generator.py` is 1778 lines
- **Context:** Multiple pack types are mixed in one large implementation.
- **Expected:** One orchestration entry plus per-pack strategy modules.
- **Success criteria:** Pack-specific changes are isolated; schema validation remains green for all packs.

### 6) `src/generators/artifact_generator.py` is 1598 lines
- **Context:** Artifact creation, schema handling, and post-processing are deeply interleaved.
- **Expected:** Separate prepare/call/normalize/validate stages.
- **Success criteria:** Each stage unit-tested; error taxonomy preserved and easier to trace.

### 7) `src/services/openai_service.py` is 1474 lines
- **Context:** Many OpenAI interaction patterns are implemented in one file.
- **Expected:** Keep single OpenAI service contract, split internals by call type.
- **Success criteria:** Chat/image/vector-store call paths are isolated with shared error mapping utilities.

### 8) `src/services/config_service.py` is 968 lines
- **Context:** Configuration parsing and normalization are heavily inline.
- **Expected:** Table-driven parsing helpers and explicit section normalizers.
- **Success criteria:** Adding config fields requires localized changes and explicit validation tests.

### 9) `src/orchestrators/ingest_orchestrator.py` is 755 lines
- **Context:** Control-plane workflow, retry logic, and state transitions are hard to follow in one body.
- **Expected:** Extract explicit workflow step functions.
- **Success criteria:** Retries, transitions, and side effects are assertable per step in tests.

### 10) `src/services/state_service.py` is 693 lines
- **Context:** Read/write/query responsibilities are concentrated, raising coupling.
- **Expected:** Separate query/update/history concerns under one service interface.
- **Success criteria:** API surface grouped by concern; simpler integration tests for each path.

## B) Oversized functions (highest refactor ROI)

### 11) `generate_report` (~1637 lines)
- **Context:** Very large control flow combines many concerns.
- **Expected:** Phase decomposition with typed intermediate dataclasses.
- **Success criteria:** No single function >200 lines in the report generation critical path.

### 12) `_render_structured_config_form` (~641 lines)
- **Context:** One UI function owns too many sections and widgets.
- **Expected:** Section renderers (core/paths/rank/publish/etc.).
- **Success criteria:** Section-specific UI edits do not require touching unrelated code.

### 13) `_select_refined_candidate_items` (~630 lines)
- **Context:** Ranking/filtering/refinement branches are fused.
- **Expected:** Independent policy functions per decision stage.
- **Success criteria:** Deterministic tests exist per stage and branch coverage improves.

### 14) `load_settings` (~500 lines)
- **Context:** Large sequential parsing chain increases default drift risk.
- **Expected:** Declarative field map + coercion/validation utilities.
- **Success criteria:** Config defaults are centralized and documented from one source.

### 15) `generate_artifacts` (~451 lines)
- **Context:** Multi-artifact orchestration and handling is difficult to verify.
- **Expected:** Per-artifact executor functions and common adapter.
- **Success criteria:** Positive + failure tests per artifact type with AppError assertions.

### 16) `run_publish` (~378 lines)
- **Context:** Publish orchestration logic is dense and hard to reason about.
- **Expected:** Explicit step pipeline with state transition helpers.
- **Success criteria:** Tests assert retry counts and transition sequence, not only final status.

### 17) `run_ingest` (~373 lines)
- **Context:** File iteration, retry, and persistence concerns are intertwined.
- **Expected:** Split per-file execution from batch coordination.
- **Success criteria:** Idempotency and retry policy validated via pipeline tests.

### 18) `run_ingest_file` (~372 lines)
- **Context:** Setup/execution/error mapping live in one long function.
- **Expected:** Isolated setup and error-classification helpers.
- **Success criteria:** Negative-path tests assert `AppError.code/retryable/severity`.

### 19) `_generate_pack` (~341 lines)
- **Context:** Prompt call, normalization, and validation are tightly coupled.
- **Expected:** Separate generation and contract-validation stages.
- **Success criteria:** Schema-failure path emits typed errors and structured logs.

### 20) `validate_report` (~319 lines)
- **Context:** Too many checks in one procedural body.
- **Expected:** Rule pipeline with deterministic ordering.
- **Success criteria:** Rule-level test granularity and clearer failure localization.

### 21) `extract_taxonomy` (~259 lines)
- **Context:** Extraction and cleanup phases are not clearly isolated.
- **Expected:** Distinct extract/normalize/validate steps.
- **Success criteria:** Stable taxonomy outputs for equivalent inputs and better diffability.

### 22) `_inject_theme` (~232 lines)
- **Context:** Large style/template injection function hampers maintainability.
- **Expected:** Move static theme assets and small composition helpers.
- **Success criteria:** Theming changes require only style assets plus minimal wiring edits.

### 23) `_run_grounding_check` (~231 lines)
- **Context:** Mixed retrieval and semantic evaluation logic.
- **Expected:** Boundary call + pure scoring layer.
- **Success criteria:** Scoring logic unit-testable without external dependencies.

### 24) `_render_settings_and_prompts` (~229 lines)
- **Context:** Settings and prompts UX concerns are merged.
- **Expected:** Split tabs/views into dedicated page components.
- **Success criteria:** Prompt view changes do not affect settings rendering behavior.

### 25) `analyze_report` (~225 lines)
- **Context:** Request prep, provider call, and adaptation are packed together.
- **Expected:** Three explicit stages with typed contracts.
- **Success criteria:** Provider failure vs parse failure are separately logged and tested.

## C) Broad exception usage and hidden failure modes

### 26) `pdf_service.py` high `except Exception` usage (56)
- **Context:** Broad catches can hide true fault classes.
- **Expected:** Replace with typed, boundary-specific exception mapping.
- **Success criteria:** Error logs preserve actionable root-cause categories.

### 27) `openai_service.py` broad catches (16)
- **Context:** Provider/network/parsing failures may be conflated.
- **Expected:** Granular exceptions mapped to `AppError` taxonomy.
- **Success criteria:** Retries only occur for retryable categories.

### 28) `streamlit_pages.py` broad catches (14)
- **Context:** UI-level broad catches risk masking systemic defects.
- **Expected:** Centralized UI error handling with explicit user-safe messaging.
- **Success criteria:** Errors remain observable in logs with full context IDs.

### 29) `report_generator.py` broad catches (10)
- **Context:** Core generation failures may degrade silently.
- **Expected:** Narrow catches and explicit fail-fast semantics.
- **Success criteria:** Failure paths produce typed `IngestOutcome`/`AppError` with reason.

### 30) `file_service.py` broad catches (8)
- **Context:** Different I/O problems collapse into generic errors.
- **Expected:** Differentiate not-found, permission, encoding, and transient errors.
- **Success criteria:** Consumers can branch correctly on retryability.

### 31) `lock_service.py` broad catches (5)
- **Context:** Lock contention and filesystem faults can be misclassified.
- **Expected:** Separate contention outcome from hard I/O failure.
- **Success criteria:** Orchestrator retry/backoff behavior becomes deterministic.

### 32) `drive_service.py` broad catches (5)
- **Context:** Upstream API specifics may be lost.
- **Expected:** Preserve provider error metadata in typed errors.
- **Success criteria:** Incident triage can identify permission/quota/network root cause quickly.

### 33) `ingest_orchestrator.py` broad catches (5)
- **Context:** Retry policy risks becoming blanket retry.
- **Expected:** Retry strictly by error taxonomy.
- **Success criteria:** Tests assert attempt counts by retryable vs non-retryable errors.

### 34) `wordpress_service.py` broad parse catches
- **Context:** Response-shape defects can pass with weak handling.
- **Expected:** Strict response schema validation.
- **Success criteria:** Invalid responses fail fast with non-retryable contract errors.

### 35) `report_store_service.py` broad DB catches
- **Context:** Operational and integrity problems are not clearly separated.
- **Expected:** Specific sqlite error mapping.
- **Success criteria:** Recovery logic differs correctly between transient DB lock and permanent schema issues.

## D) Test integrity and brittleness hotspots

### 36) High total `monkeypatch.setattr` usage (189)
- **Context:** Over-mocking risks tests validating narratives instead of behavior.
- **Expected:** Patch only external boundaries; keep core logic real.
- **Success criteria:** Removing core logic breaks tests that claim to cover it.

### 37) `tests/test_vector_pipeline_wiring.py` uses 60 monkeypatches
- **Context:** Extensive internal patching obscures true pipeline behavior.
- **Expected:** Fixture-based fake boundaries with real orchestration path.
- **Success criteria:** Pipeline tests assert state/log side effects without patching internals.

### 38) `tests/test_ingest_parallel.py` uses 15 monkeypatches
- **Context:** Concurrency behavior may be under-validated.
- **Expected:** Real parallel path + controlled boundary fakes.
- **Success criteria:** Attempt counts, ordering/backoff, and outputs are asserted.

### 39) `tests/test_candidate_extraction_orchestrator.py` uses 14 monkeypatches
- **Context:** Core extraction flow may be bypassed in tests.
- **Expected:** Mock only service boundaries.
- **Success criteria:** Tests fail if extraction logic is stubbed out.

### 40) `tests/test_publish_orchestrator.py` uses 11 monkeypatches
- **Context:** State transition correctness may be weakly verified.
- **Expected:** Transition assertions on near-real pipeline execution.
- **Success criteria:** Retry/state/idempotency are explicit assertions.

### 41) `tests/test_openai_vector_store.py` uses 10 monkeypatches
- **Context:** Vector flow coverage may depend on implementation details.
- **Expected:** Service-level transport fake instead of function-internal patching.
- **Success criteria:** Tests remain stable when internals are refactored.

### 42) `tests/test_candidate_refine_selection.py` uses 10 monkeypatches
- **Context:** Selection logic correctness may be hidden by mocks.
- **Expected:** Deterministic input fixtures through real selection code.
- **Success criteria:** Edge cases fail when scoring/refinement logic is altered incorrectly.

### 43) `tests/test_wordpress_service.py` uses 8 monkeypatches
- **Context:** HTTP behavior is patched at ad hoc points.
- **Expected:** Unified HTTP boundary fixture/adapter.
- **Success criteria:** Request/response contracts are asserted consistently.

### 44) `tests/test_publish_generator.py` uses 8 monkeypatches
- **Context:** Generator internals may be overly simulated.
- **Expected:** Validate output contracts + one concrete side effect.
- **Success criteria:** Contract completeness and side-effect assertions exist in every behavior-change test.

### 45) `tests/test_vector_pipeline_wiring.py` uses `sys.path.append(...)`
- **Context:** Test import behavior depends on path mutation.
- **Expected:** Packaging/pytest configuration provides import resolution.
- **Success criteria:** Test suite runs without dynamic path modification hacks.

## E) Cross-role coupling and maintainability quick wins

### 46) OpenAI service also writes cost ledger
- **Context:** `openai_service.py` couples model calls with accounting persistence.
- **Expected:** Emit usage/cost event and persist ledger in dedicated cost service/orchestrator step.
- **Success criteria:** OpenAI service can run without cost sink; cost pipeline remains fully auditable.

### 47) `src/cli.py` has 33 direct `console.print(...)` calls
- **Context:** Output formatting is duplicated and inconsistent.
- **Expected:** Shared rendering helpers/components.
- **Success criteria:** CLI message style and table rendering become centrally managed.

### 48) Many inline hardcoded defaults in `config_service.py`
- **Context:** Defaults can drift from YAML docs and runtime expectation.
- **Expected:** Central defaults registry/schema constants.
- **Success criteria:** README/config docs are generated or validated against runtime defaults.

### 49) Large branch-heavy control flow in UI + report generator
- **Context:** Deep branching raises onboarding and defect-localization cost.
- **Expected:** Strategy/policy helpers with names matching decisions.
- **Success criteria:** Branch coverage improves with lower cyclomatic complexity per function.

### 50) Operational log artifacts committed in `logs/`
- **Context:** Generated data in VCS adds churn/noise.
- **Expected:** Keep generated logs outside tracked source by default.
- **Success criteria:** `.gitignore`/retention policy defines what stays versioned and why.

---

## Prioritized execution plan

- **Do first (highest return):** 11, 14, 26, 36, 46.
- **Do next:** 1–10 (module decomposition), then 37–45 (test integrity hardening).
- **Program-level success criteria:** lower regression rate, faster PR review cycle, clearer error taxonomy, and stronger CI confidence.
>>>>>>> theirs
