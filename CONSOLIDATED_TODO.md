# Consolidated TODO

Last audited: 2026-06-02

This file is the single active backlog for this repository. It supersedes older backlog notes, archived planning docs, and ad hoc audit intake.

Items below were rechecked against the current repository state. Completed capabilities are listed as closed evidence and are not active backlog. Partially landed capabilities remain only when a concrete implementation gap is still visible in code, tests, README, or local WordPress assets.

## Backlog Rules

- Treat this file as the only active TODO source.
- Remove an item when all acceptance criteria are met.
- Merge overlapping work into one item instead of creating parallel tasks.
- Before implementation starts, every prioritized item must have an owner, baseline metric, target metric, and review/expiry date.
- Keep changes compliant with `AGENTS.md`: no placeholder logic, no role mixing, no prompt text in code, no private-helper monkeypatching, and no new deployable boundary without architecture review.

Scoring:

- `Impact`: `1` low leverage, `5` highest leverage across reliability, quality, cost, speed, or architecture.
- `Effort`: `1` localized change, `5` broad refactor/migration with cross-module coordination.

## Current-State Evidence

- CI currently runs formatting, risk classification, split-symbol linking, typing, architecture import, forbidden patching, repository hygiene, quality ledger, remediation runbook, backlog source, contract schema snapshot, WordPress subproject, default pytest with coverage, coverage gate, mutation gate, quality non-regression, and prompt fixture corpus regression through `.github/workflows/ci.yml`.
- Prompt dry-run validation and fixture-corpus regression are landed through `src/contracts/prompts.py`, `src/services/prompt_service.py`, `scripts/ci/check_prompt_fixture_regression.py`, `tests/test_prompt_dry_run_validation.py`, and `tests/test_prompt_fixture_corpus_regression.py`.
- OCR confidence gating and native-confidence-based OCR fallback controls are landed in `src/config/app.yaml`, `src/generators/report_source_generator.py`, and the quality ledger.
- Publisher discovery route memory, deferred recovery, direct-detail handling, KPI guardrail logging, and default-on rollout controls are landed. There is no active "publisher discovery rollout" backlog item unless a new measured gap is opened.
- Targeted validation regeneration and claim/evidence binding are landed through `src/generators/report_regeneration_generator.py`, `src/generators/validation/*`, and README validation docs.
- Idempotency service support is live in `src/services/idempotency_service.py` and backs publish, report-download, and publisher-inventory write paths documented in `README.md`.
- Candidate extraction already performs binary page triage and shared page-artifact/fingerprint caching through `src/services/_pdf/figures.py`, `src/services/_pdf/page_artifacts.py`, and `src/services/_pdf/fingerprint_cache.py`.
- Vector-store cleanup is no longer backlog: `src/services/vector_store_service.py` exposes delete/prune operations, `src/orchestrators/vector_store_retention_orchestrator.py` runs retention cleanup, and README documents `analysis.vector_store_retention_days`.
- The LLM boundary still logs `provider_decision="openai_primary"` and `budget_decision="not_configured"` in `src/services/llm_service.py`; dynamic provider routing and live spend policy remain open.
- `src/orchestrators/publish_queue_orchestrator.py` still builds a read-only publish snapshot. It does not enqueue durable publish jobs or a transactional outbox.
- Claim-level embedding persistence is live: `claim_embeddings` stores durable vectors/provider metadata/status/error taxonomy linked to `report_claims.claim_uid` and `vector_projection_queue.entity_uid`, and `claim_embedding_orchestrator` owns pending/stale embedding workflow execution.
- Cross-report Briefing and grounded Signal publish paths now reuse persisted claim embeddings for bounded semantic evidence preselection through `analytics_store_service.read_claim_embeddings`, while falling back to deterministic lexical/category ordering when embeddings are absent or stale. Durable Signal candidate extraction, ingestion-time Signal artifact-pack generation, separate Signal-store persistence, grouping, readback, and publish reuse are landed through `src/contracts/signal_candidates.py`, `src/generators/signal_candidate_generator.py`, `src/generators/report_signal_artifact_generator.py`, `src/orchestrators/signal_candidate_orchestrator.py`, `src/orchestrators/report_generation_orchestrator.py`, and `src/services/analytics_store_service.py`.
- The local bundled WordPress plugin registers `ml_report`, `ml_signal`, and `ml_briefing` with REST enabled. Remote WordPress exposure remains an external deployment/readback verification item.
- README/config drift remains: README still states report publishing uses core `posts` in one section, while `src/config/app.yaml` defaults `publish.wp.post_type` to `ml_report`.
- WordPress design token drift remains: README documents `settings.layout.wideSize` as `82rem`, while `Wordpress/wp-content/themes/marketlense/theme.json` currently uses `84rem`.

## Priority Order

1. Cost and LLM controls.
2. Analytics projection and embeddings.
3. Publish durability and WordPress/public entity alignment.
4. PDF/performance hotspots.
5. Architecture, schema compatibility, and observability gates.

---

## 1. Cost and LLM Controls

- **Title:** Enforce real-time spend guardrails across run/day/publisher budgets [Impact: 5/5, Effort: 2/5]
  - Explanation: Cost ledger append and rollup paths exist, but they are post-hoc reporting. There is still no pre-call policy that warns, pauses, or blocks expensive model/browser/OCR work based on live spend.
  - Pros: Prevents runaway spend and makes cost decisions operationally visible.
  - Cons: Needs a clear operator override path so legitimate runs are not blocked silently.
  - Acceptance Criteria:
    - YAML config defines thresholds for run, day, and publisher scopes.
    - Orchestrators check thresholds before model, browser, OCR, or other expensive calls.
    - Breaches emit typed events, structured logs, and explicit outcomes: `warn`, `pause`, `stop`, or `override`.
    - Tests cover warn, hard-stop, and operator-override paths with output contract and log assertions.

- **Title:** Implement budget-aware model routing with deterministic context compaction [Impact: 5/5, Effort: 4/5]
  - Explanation: Model resolution is still mostly static through configured OpenAI models and namespace matching. `llm_service` records budget policy as not configured.
  - Pros: Reduces cost, latency, timeout risk, and unreviewable ad hoc prompt trimming.
  - Cons: Requires careful evidence-retention tests and benchmark ownership.
  - Acceptance Criteria:
    - Policy table maps task families to model tier, max input budget, fallback tier, and quality threshold.
    - Routing decision, budget decision, compaction strategy, and reason are logged for each call.
    - Over-budget requests are compacted deterministically before model calls.
    - Regression tests protect evidence retention on a fixed prompt/output corpus.
    - Benchmarks show token/cost reduction without quality regression on that corpus.

- **Title:** Add provider failover behind the single LLM response contract [Impact: 4/5, Effort: 4/5]
  - Explanation: The canonical LLM boundary exists, but provider choice is still OpenAI-primary with no tested fallback path behind a stable response contract.
  - Pros: Improves resilience to provider outages and quota events without adding peer service entrypoints.
  - Cons: Requires contract-normalization tests across provider responses.
  - Acceptance Criteria:
    - One canonical LLM service boundary owns provider selection and response adaptation.
    - Failover is policy-driven, bounded, logged, and orchestrator-visible.
    - Provider-specific responses adapt into one typed contract before generators see them.
    - Tests cover primary success, retryable provider failure, fallback success, fallback exhaustion, and provider mismatch validation.

---

## 2. Analytics Projection, Signals, and Embeddings

- **Title:** Add claim embedding freshness, retention, and cost controls [Impact: 4/5, Effort: 2/5]
  - Explanation: Embedding records now persist locally, but operators need visibility into stale content, failed attempts, model-version drift, and avoidable re-embedding spend.
  - Pros: Prevents silent embedding drift and unnecessary provider calls while making retry/cleanup decisions operationally visible.
  - Cons: Needs concise reporting so this does not become another dashboard surface.
  - Acceptance Criteria:
    - A lightweight report summarizes embedded, pending, failed, stale, and model-version-mismatched claim counts by publisher/report/topic.
    - Retention policy documents and tests which historical embedding versions are kept or pruned.
    - The embedding workflow skips unchanged rows with a logged cost-avoidance count.
    - Tests cover stale-count reporting, failed retry visibility, retention pruning, and unchanged-row skip accounting.

- **Title:** Add semantic evidence preselection quality and cost benchmark [Impact: 4/5, Effort: 3/5]
  - Explanation: Briefing and Signal evidence preselection now uses persisted claim embeddings, but the cap and ranking policy should be measured against existing projected corpora so quality gains and prompt-size reductions stay explicit as reports accumulate.
  - Pros: Prevents silent recall loss, tunes prompt-size reduction with evidence, and gives operators a regression signal for embedding model/version changes.
  - Cons: Needs a stable corpus and clear citation-coverage metric to avoid noisy benchmark churn.
  - Acceptance Criteria:
    - A benchmark command compares deterministic fallback vs embedding-backed preselection on existing projected reports without synthesizing fixtures.
    - Output reports prompt character/token deltas, selected evidence overlap, source-report coverage, and citation coverage by Briefing/Signal run.
    - The benchmark fails or warns when semantic preselection reduces required citation/source coverage below a documented threshold.
    - Tests cover benchmark metric calculation, stale/no-embedding fallback metrics, and deterministic output ordering.

- **Title:** Complete public entity projection coverage or narrow the README entity contract [Impact: 5/5, Effort: 5/5]
  - Explanation: Reports, Briefings, and Signals have local publish paths, but README still describes a broader public entity model including Figures, Regions, and Time Periods. Those surfaces need either durable public projection contracts/routes or explicit README-scoped exclusions.
  - Pros: Gives publishing one typed source of truth for every public entity.
  - Cons: Broad schema, migration, and publish/readback work if all surfaces remain in scope.
  - Acceptance Criteria:
    - Figures, Regions, and Time Periods have documented public projection contracts or explicit README exclusions.
    - Implemented public entities map to stable WordPress route/template/readback semantics.
    - Empty-state behavior is deterministic and does not invent content.
    - Integration tests cover report-to-entity projection and WordPress publish/readback for each implemented entity.

---

## 3. Publish Durability and WordPress Alignment

- **Title:** Turn the publish snapshot into durable jobs or rename it as an ops readiness snapshot [Impact: 5/5, Effort: 5/5]
  - Explanation: `publish_queue_orchestrator.py` is live in UI/ops flows but only builds a read-only snapshot from HTML files and publish state. It does not enqueue durable publish intents or atomically couple publish side effects to state transitions.
  - Pros: Either creates a real reliable publish queue or removes misleading queue language.
  - Cons: Durable jobs require queue/outbox infrastructure; renaming requires UI/docs/API cleanup.
  - Acceptance Criteria:
    - If implemented as jobs: publish intents can be enqueued, persisted, retried, dead-lettered, and idempotently delivered.
    - If kept read-only: contracts, UI labels, docs, and logs stop using queue terminology for this feature.
    - Outbox records side-effect intents atomically with related state changes if job delivery is implemented.
    - Failure-injection tests cover restart, retry, duplicate dispatch, and partial WordPress failures.

- **Title:** Stop WordPress from synthesizing intelligence, freshness, and authority claims at render time [Impact: 5/5, Effort: 3/5]
  - Explanation: README says WordPress must assemble approved projections/artifacts, but current WordPress shortcode/stat code still computes weekly signals, strategic themes, freshness-style movement, and publisher authority from WordPress counts and dates.
  - Pros: Keeps analytical claims owned by the Python pipeline and reproducible from approved artifacts.
  - Cons: Homepage modules need replacement data contracts and fail-closed behavior when projections are absent.
  - Acceptance Criteria:
    - WordPress intelligence modules read approved projection/artifact data instead of deriving claims from live WP queries.
    - Missing projections fail closed with neutral UI or admin-visible diagnostics.
    - Tests prove no Signal, freshness, strategic-theme, or publisher-authority claim is generated solely from WordPress post counts.
    - README documents the projection source used by each WordPress intelligence module.

- **Title:** Verify/deploy WordPress REST exposure for Briefing and Signal publish entities [Impact: 5/5, Effort: 2/5]
  - Explanation: The local plugin registers `ml_briefing` and `ml_signal` with REST enabled. Live publish/readback still depends on the deployed WordPress site exposing the same routes.
  - Pros: Unblocks live end-to-end publish/readback validation for Briefings and Signals.
  - Cons: Requires coordinated WordPress deployment or plugin activation verification outside the Python repo.
  - Acceptance Criteria:
    - Remote `/wp-json/wp/v2/types` exposes `ml_briefing` and `ml_signal` with REST collection routes.
    - Live WordPress publish can create draft `ml_briefing` and `ml_signal` posts from generated artifacts.
    - Readback confirms post type, slug, title, permalink route, and publish metadata.
    - Deployment notes document the plugin/version state required for all public publish entities.

- **Title:** Resolve report post-type and entity naming drift between README, config, and WordPress [Impact: 4/5, Effort: 2/5]
  - Explanation: README still says publishing targets core `posts` in one section, while `src/config/app.yaml` defaults to `ml_report`. The plugin supports both `post` legacy digests and `ml_report`, and public copy mixes Report, Digest, Brief, and Briefing.
  - Pros: Prevents operators from publishing to the wrong content type.
  - Cons: Requires a deliberate compatibility decision and copy/test updates.
  - Acceptance Criteria:
    - README, YAML config, WordPress plugin behavior, and publish tests agree on the canonical report post type.
    - Compatibility behavior for old core `post` digests is explicitly documented or removed.
    - Public UI copy consistently uses Report for report entities and Briefing only for briefing entities.
    - Tests verify configured post type, WordPress payload post type, and resulting content type.

- **Title:** Make WordPress categories the canonical Topic surface with full topic semantics [Impact: 4/5, Effort: 3/5]
  - Explanation: WordPress categories already serve the public Topic path, but they publish mostly as labels. README defines Topics as controlled taxonomy entries with definitions plus inclusion/exclusion rules.
  - Pros: Reuses the existing category implementation while making taxonomy governance visible.
  - Cons: Requires term contract expansion and migration/update behavior.
  - Acceptance Criteria:
    - README explicitly states native WordPress categories are the canonical public Topic implementation, or documents a different canonical taxonomy.
    - Topic/category contract includes definition, inclusion rules, exclusion rules, and version metadata.
    - WordPress category creation/update writes approved topic descriptions or term meta through the service boundary.
    - Topic directory and category archive templates render approved topic semantics without ad hoc copy.
    - Tests assert term semantics survive publish and readback.

---

## 4. PDF, Dashboard, and Runtime Performance

- **Title:** Optimize measured PDF table/visual candidate hot paths without changing the public PDF boundary [Impact: 4/5, Effort: 3/5]
  - Explanation: PDF facade decomposition has landed, but `long_scripts.md` still identifies focused hot paths in table dedupe/screening, visual candidate extraction, panel detection, and crop refinement. The next work should be measured algorithmic improvement, not another size-only split.
  - Pros: Improves runtime on visually dense reports while preserving the canonical `pdf_service` boundary.
  - Cons: Needs careful real-PDF equivalence gates to avoid extraction regressions.
  - Acceptance Criteria:
    - Baseline and target metrics are captured on dense PDF fixtures before implementation.
    - Indexed table dedupe and/or precomputed per-page visual relationships reduce measured runtime or asymptotic scan cost.
    - Candidate output remains semantically equivalent unless a documented quality change is approved.
    - Tests cover near-duplicate/distinct tables, dense panels, multi-chart layouts, decorative images, wrappers, and crop boundaries.

## 5. Architecture, Schema Compatibility, and Observability

- **Title:** Extend CI gates into role-mixing and monolith-growth enforcement [Impact: 4/5, Effort: 3/5]
  - Explanation: The repo already has broad CI coverage. The remaining useful gap is automation for role mixing, direct-I/O drift, service integration coverage waivers, and first-party long-file growth.
  - Pros: Prevents architectural drift earlier and keeps the current rule set enforceable.
  - Cons: Requires careful allowlist design for legitimate edge cases.
  - Acceptance Criteria:
    - Gate logic flags role mixing, direct I/O drift, or monolith-growth violations on first-party files.
    - Allowlist entries require owner plus expiry date.
    - Missing per-service integration coverage requires a marked test or explicit temporary waiver.
    - README documents how to add and retire waivers.


---

## Closed or Removed From Active Backlog

- OCR confidence gating and native-confidence-based OCR fallback controls.
- Prompt dry-run namespace validation and prompt-fixture corpus regression baseline.
- Targeted artifact regeneration for mapped validation failures, including deterministic TOC repair.
- Claim/evidence span binding and validation-level evidence normalization.
- Core publisher-discovery memory, deferred recovery, direct-detail routing, and KPI rollout controls.
- Report-store, config-service, OpenAI-service, PDF-service, browser-download, report-download, cross-report-input, and report-generation dependency facade splits.
- UI-run dead-letter workflow, replay manifests, and operator triage surfaces.
- Vector-store delete/prune lifecycle and retention orchestration.
- Durable Signal candidate extraction, clustering, storage, readback, and publish reuse.
- Ingestion-time grounded Signal artifacts, separate Signal-store persistence, and publish workflow reuse from the Signal base.
- Claim-level embedding persistence beyond `vector_projection_queue`, including durable vector records, provider/model metadata, status/error taxonomy, idempotent/stale-aware workflow execution, and local claim/report/topic readback.
- Briefing and Signal evidence preselection using persisted claim embeddings, including bounded semantic claim selection, stale/no-embedding fallback, structured selection summaries, idempotency material updates, and local live-corpus prompt-size verification.
- Bounded Streamlit log reads and grouped directory-count walks through `file_service`.
- Generic "add more CI" wording. Active CI work must target specific drift that current gates do not catch.
- Empty audit sections from earlier consolidated TODO versions.

## Near-Term Launch Plan

### Phase 1: Highest-Leverage Controls

- Real-time spend guardrails at run/day/publisher scopes with explicit override flow.
- Budget-aware model routing with deterministic compaction.
- Durable publish snapshot decision: real jobs/outbox or explicit readiness-snapshot naming.
- WordPress report post-type naming cleanup.

### Phase 2: Intelligence Reuse and Public Entity Alignment

- Semantic evidence preselection benchmark and tuning.
- Public entity projection coverage for Figures, Regions, and Time Periods, or README narrowing.
- WordPress render-time intelligence synthesis replacement with approved projections.

### Phase 3: Resilience and Performance

- Provider failover behind the canonical LLM service contract.
- Measured PDF hot-path optimization.
- Contract compatibility matrix.
- Role-mixing/monolith-growth CI enforcement.
- End-to-end trace read model.

---

# Migrated Simplification Backlog

Migrated from `simplification.md`.

# Simplification Backlog

Last audited: 2026-06-15

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

- `llm_service.py` is the sole OpenAI, OpenRouter, generic LLM-policy, and vector-store provider boundary; the legacy `openai_service.py` facade has been removed.
- Model-client construction is centralized at orchestrator/service-factory boundaries and injected into model-backed generators.
- Large orchestrators, publish workflow surfaces, PDF facade exports, and WordPress render-time intelligence remain broad behavior-preserving refactors.
- Cross-report contract shared vocabulary now belongs to the `_cross_report_analysis` package owner, and `src/contracts/cross_report_analysis.py` remains the documented public contract surface.

## Priority Order

1. Canonical service-boundary simplification.
2. Generator and orchestrator role-boundary cleanup.
3. Low-risk helper reuse and duplicate removal.
4. PDF/visual heuristics compatibility-surface reduction.
5. WordPress and CI/process simplification.

## 2026-06-14 Verification Evidence

- Full functional suite: `3113 passed, 23 deselected`.
- Coverage: 83.11% global, 84.85% orchestrators, 87.27% generators, and 82.41% services.
- Mutation gate passed; the changed LLM vector-store target killed its sampled mutant.
- Architecture imports, service-boundary mapping, refactor movement evidence, forbidden patching, formatting, typing, and split-symbol gates passed.
- First-party test and script files contain no modules over 1,000 lines.
- Live OpenAI strict-JSON and OCR calls succeeded through `llm_service`; the OCR run used an existing project PDF and returned provider request metadata.
- A live persisted vector-store status call succeeded through `llm_service`.
- A live OpenRouter completion succeeded through `llm_service`, and the affected browser-download route completed with a structured `email_required` outcome after using the route's normal execution budget.
- After removing the legacy facade, fresh live OpenAI strict-JSON, existing-PDF OCR, persisted vector-store status, OpenRouter completion, and Consumer Edge browser-download checks all succeeded through `llm_service`.
- Existing HTML cache loaded through the typed cache service; template-bundle hashing was deterministic.
- Existing 18,900,061-byte generated image was prepared as a 298,814-byte upload payload, a 98.4% reduction.
- Real PDF candidate extraction processed an existing 1,159,172-byte PDF, produced three candidates with zero degraded pages, and produced byte-identical JSON on consecutive warm runs.
- WordPress provisioning ran successfully against the configured site; canonical and compatibility CLI dry runs then passed after argument-forwarding and import-path regressions were fixed.
- Investigation-only items were closed with retained-path evidence in `docs/quality/simplification-audit-2026-06-14.md`.
- The quality-regression gate's code coverage, mutation, and candidate metrics passed. Its unrelated docpack schema check remains red because existing golden artifacts predate required `cover_semantics` and `card_tldr_compact` fields; those fixtures and schemas were not changed or synthesized.

## 2026-06-15 Retry-Ownership Verification Evidence

- LLM services now perform exactly one provider attempt; OpenAI and OpenRouter SDK retries are explicitly disabled with `max_retries=0`.
- Orchestrators are the sole retry/backoff owner. Focused tests prove a retryable service error propagates after one call and an orchestrator performs the bounded second attempt.
- Nonzero `ingest.llm` retry, delay, backoff, or jitter settings fail configuration loading with typed `llm_service_retry_config_forbidden`.
- Known GPT-5 Responses API parameter incompatibilities are omitted before the first request; unknown unsupported parameters fail once as typed non-retryable bad requests.
- Full functional suite: `3113 passed, 23 deselected`; coverage passed at 83.13% global, 84.85% orchestrators, 87.27% generators, and 82.45% services.
- Mutation, formatting, typing, architecture imports, forbidden patching, repository hygiene, contract schema, and prompt fixture regression gates passed.
- Fresh live calls passed for OpenAI strict JSON, OCR on the existing Bain PDF, persisted vector-store status, vector-backed GPT-5 response, and OpenRouter completion.
- The Consumer Edge browser-download feature completed through the real OpenRouter/browser path as `email_delivery / email_required` with typed `blocked_unknown_required_enum`; its OpenRouter construction log recorded `max_retries=0`.
- The pre-existing quality-regression comparator remains red because its February baseline still names removed `openai_service.py` and committed golden artifact fixtures predate required `cover_semantics` and `card_tldr_compact` fields. No fixtures were synthesized or changed.

---

## 2026-06-16 Model-Client Boundary Verification Evidence

- Generators no longer import `llm_service` provider-policy construction helpers; `tests/test_model_client_injection_boundaries.py` enforces the boundary.
- Orchestrators and service-factory paths now build scoped model clients for report generation, report pipeline execution, cross-report synthesis, recategorization, publisher inventory screening, OCR fallback, and figure captions, then inject those clients into generators.
- Focused regression suite passed: `237 passed`.
- Live verification used existing project PDFs and golden report-analysis artifacts: full report generation produced HTML, OCR fallback produced a one-page OCR PDF, and cross-report synthesis produced a validated artifact with 8 sections.

---

## 1. Canonical Service-Boundary Simplification

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

- **Title:** Stop WordPress render-time intelligence synthesis where Python projections should own claims [Impact: 5/5, Effort: 4/5]
  - Explanation: WordPress still derives some intelligence/freshness/authority-style UI claims from local content state.
  - Pros: Keeps analytical claims reproducible from approved pipeline artifacts.
  - Cons: Requires projection contracts and neutral empty states.
  - Acceptance Criteria:
    - WordPress modules render approved projection data instead of deriving analytical claims from post counts or dates.
    - Missing projections fail closed with neutral UI or admin diagnostics.
    - Tests prove no intelligence claim is invented by WordPress runtime logic alone.

## Near-Term Launch Plan

### Phase 1: Boundary Corrections

- Audit top-level service proliferation and demote internal capabilities.

### Phase 2: Larger Workflow Simplification

- Consolidate publish orchestration surfaces.
- Reduce PDF visual heuristics compatibility exports.
- Simplify WordPress shortcode surfaces.

## Closed or Removed From Simplification Intake

- Implemented items are removed from this file after verification and closure in the consolidated backlog.
- Centralized model-client construction outside generators by moving scoped client construction to orchestrators/service-factory boundaries, adding a generator-boundary test, and verifying with focused tests plus live report-generation, OCR, and cross-report runs.
- Reduced cross-report contract fragmentation by deleting the private one-off `src/contracts/_cross_report_analysis/common.py` owner, moving shared vocabulary into `src/contracts/_cross_report_analysis/__init__.py`, preserving the public `src/contracts/cross_report_analysis.py` facade, and verifying with contract tests, schema/architecture gates, mutation gate, full regression suite, and a live model-backed cross-report generation run.
- Clarified report pipeline entrypoints by documenting the canonical batch, single-file, report-pipeline, report-generation, report-analysis, and `analysis_complete` restart entrypoints; removing the redundant ingest-level `report_generation_orchestrator` injection; and adding ownership tests for routing, direct stage invocation, and documentation. Verification used focused orchestrator tests plus a live existing-PDF report pipeline run and semantic restart canary.
