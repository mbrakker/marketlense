# Simplification Backlog

Last audited: 2026-06-13

This file captures the top simplification, decomplexification, reuse, and removal opportunities found in the current repository state. It intentionally mirrors the concise backlog style of `CONSOLIDATED_TODO.md`: ordered by leverage, measurable before implementation, and constrained by the architectural rules in `AGENTS.md`.

This is an analysis backlog, not an implementation approval. Before any item starts, the owner must confirm current behavior, define a baseline metric or regression fixture, and choose a movement-only or behavior-changing path explicitly.

## Backlog Rules

- Treat this file as a simplification intake list, not a second product backlog.
- Promote items into `CONSOLIDATED_TODO.md` only when they become active implementation work.
- Remove or close an item when current code proves it is already resolved.
- Merge overlapping simplification work into one scoped change instead of creating parallel refactors.
- Before implementation starts, every prioritized item must have an owner, baseline metric, target metric, affected tests, and review/expiry date.
- Keep changes compliant with `AGENTS.md`: no placeholder logic, no role mixing, no prompt text in code, no private-helper monkeypatching, and no new deployable boundary without architecture review.
- For movement-only refactors, preserve public imports through the existing facade unless an explicit public migration is approved.

Scoring:

- `Impact`: `1` low leverage, `5` highest leverage across reliability, quality, cost, speed, or architecture.
- `Effort`: `1` localized change, `5` broad refactor/migration with cross-module coordination.

## Current-State Evidence

- `src/services/openai_service.py` is a facade that delegates OpenAI operations to private `_openai_service` modules after synchronizing runtime patch points.
- `src/services/llm_service.py` owns retry, rate-limit, circuit-breaker, callable-adapter, and OpenAI-client construction behavior, creating a second OpenAI-adjacent service boundary.
- `src/services/vector_store_service.py` imports `llm_service`, aliases it as `openai_service`, and reads `OPENAI_API_KEY` directly from the process environment.
- Several generators perform file/cache/log/media operations through `Path`, `file_service`, JSON parsing, or PIL image processing.
- `src/orchestrators/ui_run_control_orchestrator.py` writes worker request files directly.
- Duplicate helper bodies or repeated helper names exist for string normalization, ordered de-duplication, JSON dumping, SQLite table checks, SQLite connection setup, HTTP session pool keys, contract required-field validation, and UI run-state path derivation.
- The PDF visual heuristics facade re-exports a large set of private helpers and retains production helper names containing `stub`.
- WordPress code still carries legacy compatibility and render-time intelligence derivation paths that should be verified, narrowed, or moved behind approved projection contracts.
- CI and quality scripts are comprehensive but fragmented across many individual entrypoints.

## Priority Order

1. Canonical service-boundary simplification.
2. Generator and orchestrator role-boundary cleanup.
3. Low-risk helper reuse and duplicate removal.
4. PDF/visual heuristics compatibility-surface reduction.
5. WordPress and CI/process simplification.

## 2026-06-13 Implementation Disposition

This section records why partially completed or deferred items remain open. Implemented items have been removed from the active simplification inventory.

### Open With Keep Rationale

- **Move HTML cache path and template-bundle hashing out of `report_render_generator.py`:** keep open. The cache path, template hash, render dependency dataclass, and golden render behavior are coupled; a safe change requires a coordinated dependency-contract migration and render-cache live equivalence run.
- **Move shared JSON cache reads/writes out of generator helpers:** keep open. `read_cache_json`/`write_cache_json` are injected through report-generation dependencies across OCR, source, selection, crop, and render tests. The measured scope exceeds an effort-3 localized change.
- **Move media optimization out of `publish_generator.py`:** keep open. No existing canonical media transformation service fits this responsibility. Adding one triggers an architecture review and needs real image corpus equivalence tests for alpha flattening, resize, JPEG quality, and not-smaller fallback.
- **Deduplicate PDF visual `TYPE_CHECKING` helper declarations:** keep open. Replacing the local declarations with explicit imports from the shared PDF owner creates a mypy placeholder/cycle failure; a safe solution requires restructuring the facade import cycle, which exceeds a localized effort-2 change.
- **Consolidate cache-read failure logging helpers:** keep open with the shared-cache extraction because moving logging alone would preserve the wrong ownership boundary.
- **Verify and retire obsolete WordPress legacy compatibility paths:** keep open. The identity and header migrations are dated June 6-7, 2026; removal on June 13, 2026 lacks deployment/readback evidence.
- **Consolidate WordPress provisioning and sync scripts:** keep open. Shell scripts use local WP-CLI/runtime access while Python scripts use authenticated REST; these are distinct operational capabilities, not interchangeable duplicate implementations.
- **Consolidate WordPress REST common behavior behind one CLI surface:** keep open for the same local-versus-remote operational distinction; a canonical wrapper would otherwise be pass-through indirection.
- **Review large theme CSS for reusable tokens and retired selectors:** keep open. Selector removal requires template/block usage inventory plus browser screenshots against a known WordPress target; neither deployment target nor approved visual baseline is available in-repo.
- **Consolidate decomposition and long-file gates into one refactor audit workflow:** keep open. `run_refactor_audit.py` now composes existing gates, but automatic AST movement-evidence validation still needs a defined evidence schema before the full acceptance criteria are met.
- **Add role-mixing and direct-I/O drift detection for generators and utilities:** keep open. Direct-I/O drift detection already exists and is now included in the canonical refactor audit, but reliable static role-mixing detection still needs an explicit rule set and allowlist for compatibility facades and capability packages.
- **Add service-boundary duplication detection for peer provider modules:** keep open. The broader OpenAI/LLM/vector-store canonical-boundary decision is an effort-4/5 prerequisite; encoding a static map before that decision would institutionalize the current ambiguity.
- **Identify unused compatibility exports after facade splits:** keep open. Repository import search is insufficient evidence for external/public consumers; removal needs documented API ownership and import-graph evidence.
- **Identify retired feature flags and default-on rollout controls:** keep open. Defaults are visible, but usage counts, owners, and production rollout state are not available locally.
- **Identify stale legacy data adapters that can be retired:** keep open. Render/report-store/WordPress adapters protect persisted historical shapes; fixture inventory and migration evidence are required before deletion.
- **Identify prompt/model configuration duplication across generators:** keep open. Prompt namespaces are intentionally use-case-local, while model resolution is already shared through prompt preparation; a complete inventory and logging audit is still required before further centralization.

### Verification Evidence

- Functional suite: `3073 passed, 23 deselected` with only `tests/test_long_test_file_ownership.py` excluded because the untouched `tests/test_publish_generator.py` is already 1,003 lines against a 1,000-line repository threshold.
- Real dashboard run: parsed the latest 250 structured events from the existing 154,812,236-byte June 13 log in 0.0076 seconds while reading at most 2,000,000 trailing bytes.
- Real grouped directory run: counted 407 HTML files, 346 validation files, and 193 top-level report directories from one `out/` root walk.
- Real report-context run: loaded existing golden evidence packs through typed JSON service contracts and produced a populated 1,800-character overview with six sections.
- Real PDF feature run: `python -m src.cli extract-candidates` processed an existing 123,763-byte downloaded PDF, produced one validated table candidate with zero degraded pages, and produced the same candidate JSON SHA-256 on a second run.
- OpenAI and WordPress live calls were not run because `OPENAI_API_KEY` and WordPress credentials were absent from the environment.

---

## 1. Canonical Service-Boundary Simplification

- **Title:** Consolidate OpenAI and LLM service boundaries [Impact: 5/5, Effort: 5/5]
  - Explanation: `openai_service.py` and `llm_service.py` both act as OpenAI-adjacent service boundaries. The first delegates provider operations; the second owns policy execution and client wrapping.
  - Pros: Restores one canonical provider boundary and reduces navigation across OpenAI, LLM, and private service modules.
  - Cons: Broad migration across generators, services, tests, and integration fixtures.
  - Acceptance Criteria:
    - One public OpenAI/LLM boundary owns provider selection, policy, retries that are truly transport-level, and response adaptation.
    - Callers no longer choose between `openai_service` and `llm_service` for OpenAI operations.
    - Provider responses still adapt into the same typed contracts.
    - Tests cover chat JSON, image JSON, OCR, vector-store response calls, retryable failure, non-retryable failure, and structured logs.

- **Title:** Clarify and enforce retry ownership between services and orchestrators [Impact: 5/5, Effort: 4/5]
  - Explanation: LLM policy code owns retry decisions, delay, jitter, rate limiting, and circuit breaker behavior, while architecture rules reserve workflow retries for orchestrators.
  - Pros: Prevents double retries, unexpected attempt counts, and timeout stacking.
  - Cons: Requires a precise split between transport resilience and workflow retry semantics.
  - Acceptance Criteria:
    - Transport-level retry, if retained, is documented as service-local and bounded below orchestration timeouts.
    - Workflow retry remains orchestrator-owned and observable through retry decision logs.
    - Tests assert attempt counts when service retry and orchestrator retry are both configured.

- **Title:** Reconcile vector-store access with the canonical OpenAI boundary [Impact: 5/5, Effort: 4/5]
  - Explanation: `vector_store_service.py` routes OpenAI vector-store operations through `llm_service` and aliases it as `openai_service`.
  - Pros: Makes vector-store ownership discoverable and removes misleading aliasing.
  - Cons: Requires deciding whether vector stores are an OpenAI capability or a domain-level service over OpenAI.
  - Acceptance Criteria:
    - Vector-store operations call the canonical provider boundary directly or become a documented capability inside it.
    - No alias makes `llm_service` appear to be `openai_service`.
    - Tests cover create, upload, attach, status, metadata update, delete, prune, and error adaptation through the chosen boundary.

- **Title:** Audit top-level service proliferation and demote internal capabilities [Impact: 4/5, Effort: 4/5]
  - Explanation: Many top-level service files appear to be internal capabilities rather than true external-system boundaries.
  - Pros: Makes service ownership easier to discover and reduces peer-boundary confusion.
  - Cons: Requires careful compatibility facades for public imports.
  - Acceptance Criteria:
    - Every top-level service is classified as an external system boundary, canonical service boundary, or candidate internal capability.
    - Internal capabilities move under private subpackages only when semantic ownership improves.
    - Public imports remain compatible or migration is explicitly approved.

---

## 2. Generator and Orchestrator Role-Boundary Cleanup

- **Title:** Move HTML cache path and template-bundle hashing out of `report_render_generator.py` [Impact: 5/5, Effort: 3/5]
  - Explanation: The generator resolves template filesystem paths, hashes templates, builds cache metadata, reads cache files, and writes cache files.
  - Pros: Keeps rendering/cache I/O behind services and leaves the generator focused on render-domain decisions.
  - Cons: Requires render/cache service contract updates.
  - Acceptance Criteria:
    - Template bundle hashing and HTML cache read/write move behind service contracts.
    - Generator receives typed cache/render responses.
    - Existing render cache-hit, stale, and miss behavior remains covered by tests.

- **Title:** Move shared JSON cache reads/writes out of generator helpers [Impact: 5/5, Effort: 3/5]
  - Explanation: `report_generation_shared.py` provides cache read/write helpers that call file dependencies and parse JSON.
  - Pros: Reuses cache behavior across generators and makes cache I/O observable in one service.
  - Cons: Requires service-level tests and dependency rewiring.
  - Acceptance Criteria:
    - A cache service owns JSON cache load/store contracts and typed errors.
    - Generators no longer parse cache files directly.
    - Tests cover file-not-found, invalid JSON, retryable file error propagation, and successful round trip.

- **Title:** Move media optimization out of `publish_generator.py` [Impact: 5/5, Effort: 3/5]
  - Explanation: The publish generator decodes image bytes, resizes images, flattens alpha, and writes JPEG payloads in memory.
  - Pros: Separates media binary transformation from publish-domain decisions.
  - Cons: Requires a media service contract and image fixture tests.
  - Acceptance Criteria:
    - A service prepares media upload payloads and returns typed optimization metadata.
    - Publish generator decides media inclusion but does not decode or transform image bytes.
    - Tests cover non-image input, decode failure, no-op small image, optimized image, and not-smaller fallback.

- **Title:** Centralize model-client construction outside generators [Impact: 5/5, Effort: 4/5]
  - Explanation: Multiple generators build OpenAI/LLM clients from settings or callables.
  - Pros: Keeps provider policy out of domain logic and simplifies model-backed generator tests.
  - Cons: Requires orchestrator/dependency bundle updates.
  - Acceptance Criteria:
    - Orchestrators or a service factory pass configured model clients into generators.
    - Generators no longer import provider-policy construction helpers.
    - Tests assert model parameters and prompt metadata are logged without generator-owned client construction.

- **Title:** Audit large orchestrators for domain-logic leakage [Impact: 4/5, Effort: 4/5]
  - Explanation: Several orchestrators approach 800-1,000 lines and may mix control flow with domain decisions.
  - Pros: Reduces future drift and improves test isolation.
  - Cons: Must avoid size-only splitting and preserve behavior.
  - Acceptance Criteria:
    - Each audited orchestrator has a role classification note and list of any domain decisions found.
    - Domain decisions move to generators only with red tests and movement audit evidence.
    - Pipeline tests prove retry counts, state transitions, and idempotency remain unchanged.

- **Title:** Consolidate publish orchestration surfaces [Impact: 5/5, Effort: 5/5]
  - Explanation: Publish workflow logic appears across publish orchestrator, publish queue/readiness, shared publish helpers, publish generator, and WordPress service paths.
  - Pros: Reduces duplicate validation and side-effect sequencing.
  - Cons: Broad workflow refactor with state and WordPress side effects.
  - Acceptance Criteria:
    - One canonical publish workflow owns state transitions and side-effect sequencing.
    - Queue/readiness/batch variants call the canonical workflow or are explicitly read-only.
    - Tests cover validation block, successful publish, duplicate publish, partial WordPress failure, and retry behavior.

- **Title:** Clarify report pipeline entrypoints across ingest, analysis, generation, and regeneration [Impact: 4/5, Effort: 4/5]
  - Explanation: Multiple orchestrators own adjacent report workflow stages and may overlap in control-plane responsibility.
  - Pros: Makes operational entrypoints and stage ownership clear.
  - Cons: Requires documentation and possibly compatibility facades.
  - Acceptance Criteria:
    - README or architecture docs name the canonical report workflow entrypoint and stage-specific entrypoints.
    - Each stage orchestrator has one clear responsibility and no duplicate sequencing path.
    - Tests cover end-to-end pipeline routing and direct stage invocation where supported.

---

## 3. Low-Risk Reuse and Duplicate Removal

- **Title:** Consolidate cache-read failure logging helpers [Impact: 3/5, Effort: 2/5]
  - Explanation: Several modules log cache/read failures through local helper variants.
  - Pros: Standardizes event names and fields.
  - Cons: Must preserve current observability expectations.
  - Acceptance Criteria:
    - Shared logging helper or cache service emits required fields consistently.
    - Tests assert `run_id`, `task_id`, `span_id`, `role`, `module`, and event fields.

---

## 4. PDF and Visual-Heuristics Simplification

- **Title:** Reduce PDF visual heuristics facade export surface [Impact: 4/5, Effort: 4/5]
  - Explanation: The visual heuristics facade re-exports many private helpers, making the compatibility surface large.
  - Pros: Shrinks private-helper coupling and makes semantic ownership clearer.
  - Cons: Tests and internal callers may currently rely on compatibility exports.
  - Acceptance Criteria:
    - Public facade exports only stable operations needed by external callers.
    - Internal callers import semantic owner modules directly where appropriate.
    - Compatibility exports are removed only after tests prove no external dependency.

- **Title:** Deduplicate PDF visual `TYPE_CHECKING` helper declarations [Impact: 3/5, Effort: 2/5]
  - Explanation: Panel text and panel geometry modules repeat helper declarations for type checking.
  - Pros: Reduces manual interface drift.
  - Cons: Must avoid import cycles.
  - Acceptance Criteria:
    - Shared type declarations or direct imports replace duplicate stubs.
    - Type check still passes.
    - Runtime imports remain acyclic.

- **Title:** Preserve PDF service as one canonical external/library boundary while reducing internals [Impact: 4/5, Effort: 4/5]
  - Explanation: PDF internals are already split into many private capability modules; further splits should reduce coupling, not just file size.
  - Pros: Prevents both monolith growth and fragmentation.
  - Cons: Requires architecture review if three or more peer modules are introduced.
  - Acceptance Criteria:
    - Any PDF simplification keeps `pdf_service.py` as the canonical boundary.
    - New private modules have semantic ownership and no pass-through-only wrappers.
    - Real PDF fixture outputs remain equivalent or approved deltas are documented.

---

## 5. WordPress and Frontend Simplification

- **Title:** Split or simplify the large WordPress shortcode class by semantic shortcode ownership [Impact: 4/5, Effort: 4/5]
  - Explanation: The shortcode class owns many archive and rendering surfaces, including legacy Signal and Briefing archive renderers.
  - Pros: Reduces PHP god-class risk and improves runtime testability.
  - Cons: Requires WordPress runtime harness coverage and compatibility preservation.
  - Acceptance Criteria:
    - Shortcode handlers are grouped by semantic public surface, not arbitrary file size.
    - Shared view-model logic moves to existing builder classes where appropriate.
    - Runtime tests prove current shortcode output remains compatible.

- **Title:** Verify and retire obsolete WordPress legacy compatibility paths [Impact: 3/5, Effort: 3/5]
  - Explanation: Plugin and theme code still include legacy project identity and header override migration behavior.
  - Pros: Removes permanent branches after migration completion.
  - Cons: Requires production/deployment evidence before removal.
  - Acceptance Criteria:
    - Each legacy path has a migration status, owner, and removal date or explicit keep rationale.
    - Removal is blocked unless fixtures prove current installs no longer need the path.
    - Tests cover retained compatibility paths or removal behavior.

- **Title:** Stop WordPress render-time intelligence synthesis where Python projections should own claims [Impact: 5/5, Effort: 4/5]
  - Explanation: WordPress still derives some intelligence/freshness/authority-style UI claims from local content state.
  - Pros: Keeps analytical claims reproducible from approved pipeline artifacts.
  - Cons: Requires projection contracts and neutral empty states.
  - Acceptance Criteria:
    - WordPress modules render approved projection data instead of deriving analytical claims from post counts or dates.
    - Missing projections fail closed with neutral UI or admin diagnostics.
    - Tests prove no intelligence claim is invented by WordPress runtime logic alone.

- **Title:** Consolidate WordPress provisioning and sync scripts [Impact: 3/5, Effort: 3/5]
  - Explanation: Shell and Python REST variants exist for provisioning, seeding, syncing publisher profiles, and building artifacts.
  - Pros: Reduces operational drift and duplicate configuration handling.
  - Cons: Must preserve developer convenience for local WordPress setup.
  - Acceptance Criteria:
    - One canonical REST-based admin/sync entrypoint owns provisioning behavior.
    - Shell scripts are thin launchers or removed if obsolete.
    - README documents the canonical path and required credentials without exposing secrets.

- **Title:** Consolidate WordPress REST common behavior behind one CLI surface [Impact: 3/5, Effort: 3/5]
  - Explanation: `wp_rest_common.py` is shared by multiple standalone scripts, but users still choose among several script entrypoints.
  - Pros: Improves discoverability and reduces argument/config duplication.
  - Cons: Requires script compatibility or migration notes.
  - Acceptance Criteria:
    - A single WordPress admin CLI exposes provision, seed, and sync subcommands.
    - Existing scripts either delegate to the CLI or are retired with docs.
    - Tests cover argument parsing and dry-run behavior.

- **Title:** Review large theme CSS for reusable tokens and retired selectors [Impact: 3/5, Effort: 3/5]
  - Explanation: The theme stylesheet is large and likely contains accumulated selectors across homepage iterations.
  - Pros: Reduces frontend drift and improves design-token reuse.
  - Cons: Visual regression risk requires screenshots.
  - Acceptance Criteria:
    - Unused selectors are identified through template/block inventory before removal.
    - Repeated spacing/color/typography values move to theme tokens or existing CSS variables.
    - Visual screenshots confirm no unintended regression on key templates.

---

## 6. CI, Quality, and Repository Process Simplification

- **Title:** Consolidate decomposition and long-file gates into one refactor audit workflow [Impact: 4/5, Effort: 3/5]
  - Explanation: Split-symbol checks, long-file inventory, architecture import checks, and movement-audit rules are related but separate.
  - Pros: Makes behavior-preserving refactors easier to validate correctly.
  - Cons: Needs careful output formatting so agents can act on failures.
  - Acceptance Criteria:
    - One refactor-audit command runs symbol links, architecture imports, long-file inventory, and movement evidence checks.
    - Output names required evidence files and failing symbols clearly.
    - README documents when to run the audit.

- **Title:** Add role-mixing and direct-I/O drift detection for generators and utilities [Impact: 5/5, Effort: 3/5]
  - Explanation: Current analysis found generator modules performing file/log/cache/media operations.
  - Pros: Prevents future violations after cleanup.
  - Cons: Requires allowlists for existing violations until refactored.
  - Acceptance Criteria:
    - Static gate flags direct filesystem, environment, network, subprocess, and binary media I/O in generators/utilities.
    - Allowlist entries include owner and expiry.
    - Tests prove new violations fail CI.

- **Title:** Add service-boundary duplication detection for peer provider modules [Impact: 4/5, Effort: 3/5]
  - Explanation: OpenAI/LLM/vector-store overlap shows that peer service boundaries can drift over time.
  - Pros: Keeps canonical external-system ownership enforceable.
  - Cons: Static detection needs a maintained map of external systems.
  - Acceptance Criteria:
    - Gate maps external systems to canonical service boundaries.
    - New peer service entrypoints for the same external system fail without explicit architecture review.
    - Private capability submodules remain allowed under the canonical boundary.

---

## 7. Contract and Schema Simplification

- **Title:** Reduce contract fragmentation inside bounded contexts [Impact: 3/5, Effort: 4/5]
  - Explanation: The contracts tree has many top-level modules and private bounded-context subpackages, which may increase navigation cost for simple capabilities.
  - Pros: Makes contract ownership easier to understand.
  - Cons: Contract moves require compatibility imports and round-trip tests.
  - Acceptance Criteria:
    - Each bounded context has a documented public contract surface.
    - Thin one-off contract files are merged only when semantic clarity improves.
    - Public import compatibility is preserved or migration is approved.

---

## 8. Active Investigation Items

- **Title:** Identify unused compatibility exports after facade splits [Impact: 3/5, Effort: 2/5]
  - Explanation: Several facades preserve legacy/private exports after decomposition.
  - Pros: Removes stale compatibility surface safely.
  - Cons: Needs import graph and test evidence.
  - Acceptance Criteria:
    - Import graph identifies zero-use exports.
    - Tests confirm removed exports are not part of documented public API.
    - Removed exports are listed in architecture review notes if the surface is public.

- **Title:** Identify retired feature flags and default-on rollout controls [Impact: 3/5, Effort: 2/5]
  - Explanation: Some rollout controls may remain after features have fully landed.
  - Pros: Removes dead branches and configuration burden.
  - Cons: Requires operational confirmation before deleting flags.
  - Acceptance Criteria:
    - Each candidate flag has current default, usage count, owner, and removal decision.
    - Removed flags update config examples, README, and tests.
    - Retained flags have a documented expiry or permanent rationale.

- **Title:** Identify stale legacy data adapters that can be retired [Impact: 3/5, Effort: 3/5]
  - Explanation: Legacy schema/readback adapters remain in report store, render normalization, and WordPress compatibility paths.
  - Pros: Reduces branch count and test matrix size.
  - Cons: Must not break existing persisted state.
  - Acceptance Criteria:
    - Persisted fixture inventory proves whether legacy shapes still exist.
    - Removal includes migration or explicit incompatibility note.
    - Tests cover retained adapters or migrated fixtures.

- **Title:** Identify prompt/model configuration duplication across generators [Impact: 4/5, Effort: 3/5]
  - Explanation: Model-backed generators may repeat namespace, model, and parameter setup logic.
  - Pros: Improves reproducibility and reduces prompt-call drift.
  - Cons: Must preserve prompt namespace isolation.
  - Acceptance Criteria:
    - Inventory lists each model-backed generator, prompt namespace, model settings, and call contract.
    - Shared setup is centralized without centralizing prompt text.
    - Tests assert prompt path/hash/rendered prompt/model parameters are logged per call.

---

## Near-Term Launch Plan

### Phase 1: Boundary Corrections

- Consolidate OpenAI/LLM/vector-store service ownership.
- Move remaining cache and media optimization I/O out of generators.
- Centralize model-client construction outside generators.

### Phase 2: Larger Workflow Simplification

- Consolidate publish orchestration surfaces.
- Clarify report pipeline entrypoints.
- Reduce PDF visual heuristics compatibility exports.
- Simplify WordPress shortcode/provisioning surfaces.
- Complete role-mixing and service-boundary duplication gates.

## Closed or Removed From Simplification Intake

- Implemented items are removed from this file after verification and closure in the consolidated backlog.
