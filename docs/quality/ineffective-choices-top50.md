# Repository Analysis: Remaining Ineffective Choices From Top-50 Audit (Low Effort, High Impact)

Status: merged into `CONSOLIDATED_TODO.md` on 2026-03-08. Treat the consolidated todo as the actionable backlog; keep this file as the detailed source analysis behind those tasks. Resolved items were removed on 2026-03-13 after the PDF-service split, the report-generator phase split, the validation-generator rule split, and related config/test cleanup. Original audit numbering is preserved so consolidated references stay stable.

Method: static repository scan focused on maintainability, reliability, architecture boundaries, and test integrity. Prioritized by impact/effort ratio.

Format for each item:
- **Context**: why this is ineffective today.
- **Expected**: what should exist instead.
- **Success criteria**: measurable end-state to close the item.

## A) Monolithic modules (split-first wins)

### 3) `src/ui/streamlit_pages.py` is 2967 lines
- **Context:** UI logic for many screens lives in one file.
- **Expected:** Split by page/feature module with shared UI helpers.
- **Success criteria:** Per-page files with clear ownership; page-level tests can run independently.

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

### 12) `_render_structured_config_form` (~641 lines)
- **Context:** One UI function owns too many sections and widgets.
- **Expected:** Section renderers (core/paths/rank/publish/etc.).
- **Success criteria:** Section-specific UI edits do not require touching unrelated code.

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

### 26) `src/services/_pdf/*.py` broad `except Exception` usage remains elevated (56)
- **Context:** The PDF service split reduced module size, but broad catches still hide true fault classes across the new capability modules.
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

### 36) Repo-wide `monkeypatch.setattr` usage remains elevated (71)
- **Context:** Over-mocking still risks tests validating narratives instead of behavior, even after the hotspot reductions.
- **Expected:** Patch only external boundaries; keep core logic real.
- **Success criteria:** Removing core logic breaks tests that claim to cover it.

Resolved on 2026-03-09: former items 37-45 were removed after converting `tests/test_vector_pipeline_wiring.py` and `tests/test_ingest_parallel.py` to explicit dependency-injection seams plus log capture, converting the candidate-extraction, publish, OpenAI vector-store, WordPress, and candidate-refine tests to shared boundary fixtures/real execution paths, and removing the `sys.path.append(...)` import hack from `tests/test_vector_pipeline_wiring.py`.

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

### 49) Large branch-heavy control flow in UI + remaining generation flows
- **Context:** Deep branching in the Streamlit UI and the remaining oversized generation/validation modules raises onboarding and defect-localization cost.
- **Expected:** Strategy/policy helpers with names matching decisions.
- **Success criteria:** Branch coverage improves with lower cyclomatic complexity per function.

### 50) Operational log artifacts committed in `logs/`
- **Context:** Generated data in VCS adds churn/noise.
- **Expected:** Keep generated logs outside tracked source by default.
- **Success criteria:** `.gitignore`/retention policy defines what stays versioned and why.

---

## Prioritized execution plan

- **Do first (highest return):** 14, 20, 26, 36, 46.
- **Do next:** 3–10 (module decomposition), then 15, 19, 21, 23, 25 and the remaining test-integrity cleanup around item 36.
- **Program-level success criteria:** lower regression rate, faster PR review cycle, clearer error taxonomy, and stronger CI confidence.

---

## Appendix: Additional behavior-preserving code-reduction opportunities (2026-03-15)

These are supplemental to the original top-50 audit and intentionally use `R1`-`R20` identifiers so the preserved top-50 numbering above does not drift. Scope here is narrower: remove duplicated code and shrink modules without changing contracts, prompt behavior, logging requirements, or quality expectations.

Verification basis for this appendix:
- Static repository scan confirmed the duplication patterns before adding this list.
- `pytest -q` passed on the current tree during the review pass.
- `scripts/ci/check_forbidden_patching.py` passed on the current tree during the review pass.
- Existing repo-wide formatting and mypy gates already fail on unrelated current-state issues, so they cannot be used as a clean refactor baseline until the tree is stabilized.

### R1) Shared analysis-pack adapter helper is duplicated across generators
- **Context:** Pack path/store adaptation logic is repeated in `artifact_generator`, `evidence_pack_generator`, `taxonomy_generator`, and `validation/cache`.
- **Expected:** One pure helper for `pack_path` and one for `store_pack` request adaptation with the same typed fallback behavior.
- **Success criteria:** Duplicate adapter bodies are removed; pack path/store behavior and returned dataclass contracts stay unchanged.

### R2) Shared cached-pack loader logic is duplicated across generators
- **Context:** Several modules repeat the same resolve-path/read/decode/cache-key-check flow for cached analysis packs.
- **Expected:** One shared cached-pack loader utility with caller-supplied typed response adaptation.
- **Success criteria:** Cache-hit/miss behavior stays identical while the repeated JSON/load logic is reduced to one implementation.

### R3) JSON extraction from model text exists in more than one module
- **Context:** Fence stripping, JSON substring extraction, and fallback parsing are duplicated between OpenAI service logic and evidence-pack generation.
- **Expected:** One pure text-to-JSON utility used by all model-response recovery paths.
- **Success criteria:** The same malformed/partial response cases still parse or fail exactly as before, but there is only one parser implementation.

### R4) Prompt load/render/log/model-resolution setup is repeated across generators
- **Context:** Generators repeatedly do the same sequence: load prompt set, log hashes, render prompts, log rendered text, resolve model.
- **Expected:** A shared generator-side prompt preparation helper returning fully rendered prompts plus metadata.
- **Success criteria:** Prompt logging remains exact, namespace/model resolution stays deterministic, and duplicated setup code is removed.

### R5) Artifact normalization helpers should live outside `artifact_generator.py`
- **Context:** Artifact normalization and regeneration share logic, but the implementation currently lives in `artifact_generator.py` and is imported back into regeneration flow.
- **Expected:** Move the shared normalization/helpers into a dedicated pure module under generators or utils.
- **Success criteria:** `artifact_generator.py` shrinks materially, regeneration keeps using the same helpers, and no normalization behavior changes.

### R6) Public alias wrappers in `artifact_generator.py` add size without behavior
- **Context:** Multiple exported helpers are thin pass-through wrappers over internal implementations with identical signatures.
- **Expected:** Keep one canonical helper definition and export that directly.
- **Success criteria:** Wrapper-only functions are deleted, import sites stay readable, and behavior remains identical.

### R7) OpenAI chat completion flows repeat modern/legacy call orchestration
- **Context:** `analyze_report` and `openai_chat_json` each build nearly identical chat-completion call paths and fallback handling.
- **Expected:** Extract a shared chat-completion runner used by both typed service entry points.
- **Success criteria:** Error mapping, token extraction, request IDs, and parsed payloads remain unchanged while duplicate call orchestration disappears.

### R8) OpenAI cost-ledger persistence block is repeated across service operations
- **Context:** Estimating cost, appending a ledger entry, and rolling up daily totals is duplicated in multiple OpenAI service paths.
- **Expected:** One shared cost-recording helper that accepts the operation name, token counts, and request ID.
- **Success criteria:** Cost records remain identical in content, failures remain best-effort and logged, and the repeated ledger block is removed.

### R9) OpenAI response metadata parsing is repeated
- **Context:** Request ID, token counts, tool call counts, and parsed JSON handling are repeatedly reconstructed from provider responses.
- **Expected:** One response metadata adapter shared by JSON chat, image chat, and vector-store response flows.
- **Success criteria:** Returned service dataclasses remain identical while response adaptation code is centralized.

### R10) Vector-store CRUD-style operations in `openai_service.py` can share one operation runner
- **Context:** Create/upload/attach/status/update each repeat the same client init, log, call, ID extraction, and `AppError` mapping pattern.
- **Expected:** One generic vector-store operation runner with per-call payload and response extraction callbacks.
- **Success criteria:** Operation-specific request/response contracts stay explicit, but the common scaffolding is removed.

### R11) `load_settings` should use a declarative resolver table
- **Context:** Configuration parsing is a long inline chain of `_env_value`, `_to_int`, `_to_float`, `_as_bool`, defaults, and clamps.
- **Expected:** A field-spec table or section normalizers that define source path, env fallback, coercion, and default once.
- **Success criteria:** Adding a new config field becomes localized and default behavior stays exactly the same under tests.

### R12) Boolean and numeric coercion helpers are duplicated
- **Context:** Similar `_to_bool`, `_as_bool`, and related coercion helpers exist in config, rank, and UI code.
- **Expected:** Shared pure coercion helpers in `src/utils`.
- **Success criteria:** Truthy/falsy parsing behavior remains unchanged, but duplicate local parsing helpers are removed.

### R13) YAML loading/error wrapping should be centralized where semantics match
- **Context:** Several services reimplement “load YAML, validate root shape, map parse failure to typed error.”
- **Expected:** Shared YAML loader helpers with service-specific error-code mapping on top.
- **Success criteria:** File-not-found and invalid-YAML behavior remains explicit, with less repeated parsing boilerplate.

### R14) Evidence-pack strategies are mostly data-driven and can be factory-generated
- **Context:** Many list-like evidence-pack strategy modules repeat the same empty-payload builder, alias selection, normalization shell, and strategy declaration pattern.
- **Expected:** Factory helpers for common list-pack/scalar-pack strategy shapes, leaving only pack-specific field maps and transforms in each module.
- **Success criteria:** Strategy behavior remains schema-specific and explicit, but per-pack boilerplate shrinks substantially.

### R15) Evidence-pack generator should pass strategy objects directly
- **Context:** The generator currently carries `(pack_name, prompt_namespace_suffix, schema_name)` tuples and thin wrapper helpers around strategy behavior.
- **Expected:** Build execution steps directly from `EvidencePackStrategy` objects plus scheduling metadata.
- **Success criteria:** Registry behavior stays the same, pack ordering stays the same, and helper indirection is reduced.

### R16) Publish file-id mapping helpers are duplicated across two orchestrators
- **Context:** `publish_orchestrator` and `publish_queue_orchestrator` both implement the same HTML path canonicalization and reports-db file-id map loading.
- **Expected:** One shared publish-support helper module under orchestrators.
- **Success criteria:** Queue and publish flows resolve file IDs exactly as before while duplicate helper bodies are removed.

### R17) Local retry wrapper helpers should be removed in favor of the shared retry orchestrator API
- **Context:** Some orchestrators define tiny `_run_step_with_retry` wrappers that only forward fixed arguments to shared retry logic.
- **Expected:** Call the shared retry helper directly or create one common adapter in the retry orchestrator.
- **Success criteria:** Retry counts, sleep behavior, log fields, and retryable-error handling remain unchanged.

### R18) Dataclass-to-dict helper logic is duplicated across ops/dashboard/UI layers
- **Context:** UI and dashboard code repeats the same “if dataclass -> `asdict`, if dict -> keep, if object -> `__dict__`” conversion helper.
- **Expected:** One shared pure serialization helper for dashboard/UI table rows.
- **Success criteria:** Rendered tables and downstream filtering stay unchanged while the helper exists in one place only.

### R19) Tiny text/tag helpers are repeated and should be promoted to shared utilities
- **Context:** Helpers like `_norm_tag`, `_category_label`, `_s`, and `_dump_json` recur across services and generators with the same intent.
- **Expected:** Shared text/tag utility helpers where semantics are the same.
- **Success criteria:** Normalization/stringification behavior stays stable and helper duplication is removed without mixing business logic.

### R20) `report_regeneration_generator.py` should replace branch-heavy target dispatch with a handler registry
- **Context:** Regeneration currently uses a long `if/elif` chain keyed by `target.target_section`, even though each branch follows the same broad template.
- **Expected:** A registry of section handlers that each define namespace selection, variable assembly, normalization, and state update behavior.
- **Success criteria:** Regeneration output remains identical for each target section, but branching complexity and duplicated render-call structure are reduced.
