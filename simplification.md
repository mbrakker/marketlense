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

- **Title:** Remove runtime patch-point synchronization from OpenAI service calls [Impact: 5/5, Effort: 3/5]
  - Explanation: The OpenAI facade mutates private submodules before each operation to synchronize `OpenAI`, `file_service`, and accounting dependencies.
  - Pros: Removes hidden mutable coupling and production accommodation for test patch points.
  - Cons: Requires tests to move to explicit external-boundary mocks or injected clients.
  - Acceptance Criteria:
    - OpenAI private modules receive dependencies through explicit construction or canonical module ownership, not repeated runtime mutation.
    - No production call path depends on facade-level mutable globals being copied into child modules.
    - Tests patch only the true external boundary or injected provider client.

- **Title:** Collapse callable OpenAI adapter layering [Impact: 4/5, Effort: 3/5]
  - Explanation: `LLMServiceClient` delegates methods to a base client, while `_CallableOpenAIAdapter` adapts callables back into a method-bearing object.
  - Pros: Reduces adapter-on-adapter indirection and repeated method names.
  - Cons: Test seams must remain explicit and compliant with external-boundary mock rules.
  - Acceptance Criteria:
    - One provider client contract or dataclass dependency replaces callable adapter layering.
    - Tests can inject fake external-provider behavior without patching private helpers.
    - Missing operation errors remain typed and covered by tests.

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

- **Title:** Centralize OpenAI credential resolution [Impact: 4/5, Effort: 2/5]
  - Explanation: `vector_store_service.py` reads `OPENAI_API_KEY` directly from the environment instead of using a central config/provider boundary.
  - Pros: Removes duplicated credential ownership and improves redaction/auditability.
  - Cons: Requires updating tests that currently set environment values for vector-store behavior.
  - Acceptance Criteria:
    - OpenAI credentials resolve through one config/provider path.
    - Missing credential errors remain typed and sanitized.
    - Tests prove secrets are not logged or exposed.

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

- **Title:** Move evidence-pack JSON loading out of `report_context_generator.py` [Impact: 4/5, Effort: 2/5]
  - Explanation: The generator reads evidence-pack files through a file client and parses JSON.
  - Pros: Removes filesystem parsing from domain logic.
  - Cons: Requires a small evidence-pack loading contract.
  - Acceptance Criteria:
    - Evidence-pack loading is service-owned and returns typed pack content or typed errors.
    - Generator accepts fully formed evidence-pack context.
    - Tests cover missing pack, invalid JSON, and valid pack behavior at the service boundary.

- **Title:** Move Streamlit log-file reads out of `streamlit_dashboard_generator.py` [Impact: 4/5, Effort: 3/5]
  - Explanation: The generator reads log files, slices lines, parses structured events, and sorts them.
  - Pros: Enables bounded tail reads and consistent observability-service behavior.
  - Cons: Requires dashboard read-model contract updates.
  - Acceptance Criteria:
    - A service loads bounded log events with byte/line limits.
    - The generator consumes typed log events and produces dashboard models.
    - Tests cover large logs, malformed lines, read errors, and required structured log fields.

- **Title:** Move Streamlit JSON payload reads out of `streamlit_dashboard_generator.py` [Impact: 3/5, Effort: 2/5]
  - Explanation: The generator also reads arbitrary JSON payloads through `file_service`.
  - Pros: Consolidates dashboard I/O and JSON parsing.
  - Cons: May overlap with the log-read service extraction.
  - Acceptance Criteria:
    - Dashboard JSON reads are service-owned.
    - Invalid JSON and missing files return typed errors or typed empty states.
    - Generator tests no longer mock file reads for primary dashboard behavior.

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

- **Title:** Move UI-run worker request file writes into a service [Impact: 4/5, Effort: 2/5]
  - Explanation: `ui_run_control_orchestrator.py` directly creates directories and writes worker request JSON.
  - Pros: Keeps the orchestrator focused on lifecycle/state transitions.
  - Cons: Requires a UI-run state/store service operation.
  - Acceptance Criteria:
    - Worker request persistence is service-owned with an explicit dataclass request/response.
    - Orchestrator logs state transitions and delegates file writes.
    - Tests cover persistence success, write failure, and idempotent rerun behavior.

- **Title:** Move persistent path derivation out of orchestrators where it affects idempotency [Impact: 4/5, Effort: 3/5]
  - Explanation: Several orchestrators derive output/state/cache paths directly.
  - Pros: Makes artifact location and idempotency policy consistent.
  - Cons: Pure path helpers must not become I/O utilities.
  - Acceptance Criteria:
    - Pure deterministic path derivation lives in utilities or typed path-policy modules.
    - Persisted path resolution and filesystem checks remain service-owned.
    - Tests cover same-input same-path and collision/normalization behavior.

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

- **Title:** Consolidate repeated `_s()` string-normalization helpers [Impact: 3/5, Effort: 1/5]
  - Explanation: Identical `_s()` helpers exist across several generator modules.
  - Pros: Low-risk cleanup and consistent string coercion.
  - Cons: Requires careful import placement to avoid reverse dependencies.
  - Acceptance Criteria:
    - One pure utility owns the behavior.
    - All replaced call sites preserve exact output.
    - Focused tests cover `None`, whitespace, numeric, and normal string inputs.

- **Title:** Consolidate repeated `_unique_ordered()` helpers [Impact: 3/5, Effort: 1/5]
  - Explanation: Ordered de-duplication appears in multiple generator modules.
  - Pros: Reuses a pure deterministic helper.
  - Cons: Small risk of type-specific behavior differences.
  - Acceptance Criteria:
    - One utility supports current call sites without broad abstraction.
    - Tests cover order preservation, duplicates, empty input, and non-string values where used.

- **Title:** Consolidate repeated JSON dumping helpers [Impact: 3/5, Effort: 2/5]
  - Explanation: `_dump_json` variants exist in artifact and regeneration paths.
  - Pros: Ensures deterministic serialization and schema-version consistency.
  - Cons: Must preserve current formatting where golden files depend on it.
  - Acceptance Criteria:
    - One deterministic JSON serialization utility is used by affected modules.
    - Golden artifacts remain unchanged or approved diffs are captured.
    - Tests cover ordering, ASCII/Unicode behavior, and unsupported object errors.

- **Title:** Consolidate cache-read failure logging helpers [Impact: 3/5, Effort: 2/5]
  - Explanation: Several modules log cache/read failures through local helper variants.
  - Pros: Standardizes event names and fields.
  - Cons: Must preserve current observability expectations.
  - Acceptance Criteria:
    - Shared logging helper or cache service emits required fields consistently.
    - Tests assert `run_id`, `task_id`, `span_id`, `role`, `module`, and event fields.

- **Title:** Consolidate SQLite table-existence helpers [Impact: 3/5, Effort: 2/5]
  - Explanation: `_table_exists` is duplicated across SQLite migration, analytics store, and report-store internals.
  - Pros: Reduces database metadata drift.
  - Cons: Shared helper must remain private to service/database internals.
  - Acceptance Criteria:
    - One SQLite metadata helper is reused by affected service modules.
    - Tests cover existing table, missing table, and invalid connection/error behavior.

- **Title:** Consolidate SQLite connection and lock-error helpers [Impact: 4/5, Effort: 2/5]
  - Explanation: State and report-store services duplicate connection configuration and lock-error detection.
  - Pros: Keeps timeout, row factory, pragma, and lock handling consistent.
  - Cons: Requires migration-sensitive database tests.
  - Acceptance Criteria:
    - One private SQLite common module owns connection configuration and lock detection.
    - Existing state/report-store behavior remains unchanged.
    - Tests cover lock error mapping and connection setup.

- **Title:** Consolidate HTTP session-pool-key logic [Impact: 3/5, Effort: 2/5]
  - Explanation: HTTP acquisition and WordPress transport duplicate session-pool-key behavior.
  - Pros: Keeps pooling semantics consistent across HTTP services.
  - Cons: Shared code must not blur service boundaries.
  - Acceptance Criteria:
    - A private HTTP transport helper owns pool-key derivation.
    - HTTP acquisition and WordPress transport call it without sharing business logic.
    - Tests cover scheme/host/port normalization and credential isolation.

- **Title:** Consolidate contract required-field validation helpers [Impact: 4/5, Effort: 3/5]
  - Explanation: Contract modules duplicate helpers for required-field detection, empty values, and value validation.
  - Pros: Makes dataclass completeness rules consistent.
  - Cons: Contract validation behavior is critical and needs broad tests.
  - Acceptance Criteria:
    - One contract-validation utility owns required-field semantics.
    - Existing contract round-trip tests still pass.
    - Negative-path tests assert typed `AppError` code, retryable flag, severity, and context.

- **Title:** Reuse UI run-state directory derivation [Impact: 3/5, Effort: 1/5]
  - Explanation: UI run control and replay paths duplicate run-state directory derivation.
  - Pros: Prevents path drift between launch and replay.
  - Cons: Must avoid moving filesystem I/O into a pure utility.
  - Acceptance Criteria:
    - One pure helper derives the run-state directory, or one service owns it.
    - Launch and replay tests use the same derivation path.

- **Title:** Consolidate UTC clock helpers [Impact: 3/5, Effort: 2/5]
  - Explanation: `_utc_now` and `_utc_now_iso` appear across CLI, service, and orchestrator modules.
  - Pros: Enables deterministic clock injection and consistent timestamps.
  - Cons: Some call sites may intentionally need local injection.
  - Acceptance Criteria:
    - One clock utility or injected clock dependency covers repeated call sites.
    - Tests cover deterministic time in state transitions and persisted records.

- **Title:** Replace silent cleanup `pass` blocks with structured logging or documented safe suppression [Impact: 3/5, Effort: 1/5]
  - Explanation: Atomic write cleanup code swallows temp-file unlink errors.
  - Pros: Aligns cleanup failures with event logging rules.
  - Cons: Excessive logging could add noise if not scoped.
  - Acceptance Criteria:
    - Cleanup suppression emits a structured low-severity event or is explicitly documented as safe.
    - Tests cover cleanup failure without masking the original write error.

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

- **Title:** Rename production PDF helper containing `stub` [Impact: 3/5, Effort: 2/5]
  - Explanation: `_panel_caption_looks_metric_stub` is production logic but uses placeholder-like terminology.
  - Pros: Removes misleading naming under the no-placeholder rule.
  - Cons: Requires compatibility alias or coordinated call-site migration.
  - Acceptance Criteria:
    - Helper receives a production-accurate name.
    - Any temporary compatibility alias has an expiry/removal plan.
    - Tests prove behavior is unchanged.

- **Title:** Deduplicate PDF visual `TYPE_CHECKING` helper declarations [Impact: 3/5, Effort: 2/5]
  - Explanation: Panel text and panel geometry modules repeat helper declarations for type checking.
  - Pros: Reduces manual interface drift.
  - Cons: Must avoid import cycles.
  - Acceptance Criteria:
    - Shared type declarations or direct imports replace duplicate stubs.
    - Type check still passes.
    - Runtime imports remain acyclic.

- **Title:** Consolidate PDF candidate chunking and reason-tally helpers [Impact: 3/5, Effort: 2/5]
  - Explanation: Table heuristics and visual heuristics duplicate chunking, worker resolution, and reason tally behavior.
  - Pros: Keeps performance helper behavior consistent.
  - Cons: Must preserve performance characteristics.
  - Acceptance Criteria:
    - One PDF-private helper module owns chunking, worker resolution, and reason tallying.
    - Tests cover chunk boundaries, worker limits, and reason counts.

- **Title:** Consolidate PDF candidate quality and OCR-density helpers [Impact: 3/5, Effort: 2/5]
  - Explanation: Table candidate and visual candidate code duplicate quality bounding and OCR-density helpers.
  - Pros: Aligns scoring semantics across candidate families.
  - Cons: Needs regression tests over representative fixtures.
  - Acceptance Criteria:
    - One PDF candidate scoring helper is reused.
    - Existing candidate scores remain unchanged on fixed fixtures unless an approved behavior change is documented.

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

- **Title:** Add one canonical local quality-gate command over existing CI scripts [Impact: 4/5, Effort: 2/5]
  - Explanation: CI is comprehensive but fragmented across many script entrypoints.
  - Pros: Makes local verification match CI order and reduces missed checks.
  - Cons: Must not hide detailed failure output.
  - Acceptance Criteria:
    - One command runs formatting, typing, architecture imports, forbidden patching, repository hygiene, tests, coverage, mutation, contract schemas, WordPress checks, and prompt fixture checks as configured.
    - Individual scripts remain callable for focused work.
    - README documents the canonical local command.

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

- **Title:** Consolidate repository analysis exclusions and backlog promotion rules [Impact: 3/5, Effort: 2/5]
  - Explanation: Repository analysis exclusions, consolidated TODO rules, and simplification intake need a clear relationship.
  - Pros: Prevents this file from becoming a competing active backlog.
  - Cons: Requires documentation discipline.
  - Acceptance Criteria:
    - README or docs state that `simplification.md` is intake and `CONSOLIDATED_TODO.md` is active backlog.
    - Promotion from simplification intake to active backlog requires owner, metric, target, and expiry.
    - CI backlog-source gate remains consistent with the active backlog policy.

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

- **Title:** Standardize schema-version constants per contract module [Impact: 3/5, Effort: 2/5]
  - Explanation: Request/response construction repeats literal `schema_version="1.0"` across modules.
  - Pros: Simplifies version bumps and schema snapshot review.
  - Cons: Requires broad but mechanical updates.
  - Acceptance Criteria:
    - Contract modules expose module-level schema-version constants where useful.
    - Builders/tests use the constants instead of repeated literals.
    - Contract round-trip and schema snapshot tests pass.

- **Title:** Consolidate schema validation and required-field completeness assertions [Impact: 4/5, Effort: 3/5]
  - Explanation: Contract validation logic appears in multiple places and should be one trustworthy path.
  - Pros: Strengthens anti-default/sentinel test integrity.
  - Cons: Requires careful negative-path coverage.
  - Acceptance Criteria:
    - Shared fixtures/utilities assert required fields are not empty/default/sentinel-filled.
    - Services validate incoming and outgoing contracts through the shared path where applicable.
    - Negative-path tests assert typed error taxonomy.

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

- **Title:** Identify repeated directory-walk and file-stat patterns for service-level batching [Impact: 3/5, Effort: 2/5]
  - Explanation: Dashboard and artifact workflows likely repeat directory listing/stat operations.
  - Pros: Reduces runtime cost and I/O chatter.
  - Cons: Needs measured baseline before batching.
  - Acceptance Criteria:
    - Baseline counts directory walks and file stats for dashboard/report workflows.
    - Service-level batch operation reduces repeated walks without changing outputs.
    - Tests cover overlapping patterns and listing errors.

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

### Phase 1: Low-Risk Cleanup

- Consolidate repeated `_s`, `_unique_ordered`, JSON dumping, SQLite, HTTP pool-key, and contract required-field helpers.
- Rename production PDF helper containing `stub`.
- Replace silent cleanup `pass` blocks with structured logging or documented safe suppression.

### Phase 2: Boundary Corrections

- Consolidate OpenAI/LLM/vector-store service ownership.
- Move cache, evidence-pack, dashboard log/JSON, media optimization, and UI-run persistence I/O out of generators/orchestrators.
- Centralize model-client construction outside generators.

### Phase 3: Larger Workflow Simplification

- Consolidate publish orchestration surfaces.
- Clarify report pipeline entrypoints.
- Reduce PDF visual heuristics compatibility exports.
- Simplify WordPress shortcode/provisioning surfaces.
- Add role-mixing/direct-I/O and service-boundary duplication gates.

## Closed or Removed From Simplification Intake

- None yet. This file is the initial simplification intake created from the 2026-06-13 repository analysis.
