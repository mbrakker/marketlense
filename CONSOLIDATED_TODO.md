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
- `vector_projection_queue` persists `embedding_status` and `embedding_version`, but there is no stored embedding vector/provider reference or embedding workflow beyond queue staging.
- Cross-report Briefing and grounded Signal publish paths exist locally. Durable Signal candidate extraction, ingestion-time Signal artifact-pack generation, separate Signal-store persistence, grouping, readback, and publish reuse are landed through `src/contracts/signal_candidates.py`, `src/generators/signal_candidate_generator.py`, `src/generators/report_signal_artifact_generator.py`, `src/orchestrators/signal_candidate_orchestrator.py`, `src/orchestrators/report_generation_orchestrator.py`, and `src/services/analytics_store_service.py`.
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

- **Title:** Persist claim-level embeddings beyond the vector projection queue [Impact: 5/5, Effort: 4/5]
  - Explanation: Claims are projected into `report_claims` and queued in `vector_projection_queue`, but the system does not store actual embedding vectors, provider/vector-store references, embedding lifecycle timestamps, or completed/failed embedding records per claim.
  - Pros: Enables reusable semantic retrieval over claims and makes Signal/Briefing grounding cheaper and reproducible.
  - Cons: Requires a storage contract, migration, embedding workflow, and retention/versioning policy.
  - Acceptance Criteria:
    - A versioned embedding storage contract links each embedded claim to `report_claims.claim_uid` and `vector_projection_queue.entity_uid`.
    - An orchestrator-owned embedding workflow reads pending queue rows, calls the embedding service boundary, persists vectors or external vector IDs, and updates status.
    - `embedding_version`, `content_hash`, provider/model metadata, generated timestamp, and retry/error taxonomy are stored and logged.
    - Re-embedding behavior is deterministic when claim text, metadata, content hash, or embedding model version changes.
    - Tests cover successful embedding, failed status, idempotent reruns, stale-content re-embedding, and retrieval by claim/report/topic metadata.

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

- **Title:** Bring WordPress design tokens and CSS organization back in line with README [Impact: 3/5, Effort: 2/5]
  - Explanation: README documents `wideSize` as `82rem`, while `theme.json` uses `84rem`. The theme also has repeated CSS hooks and header styling that should be auditable against the documented design contract.
  - Pros: Reduces design drift and keeps styling centralized and testable.
  - Cons: Visual regressions are possible without screenshot review.
  - Acceptance Criteria:
    - README and `theme.json` agree on `wideSize` and other documented layout tokens.
    - Header-specific styling is either centralized in the theme stylesheet or explicitly documented as approved block markup styling.
    - Repeated CSS hooks are consolidated only when rendering is preserved.
    - WordPress static checks and at least one desktop/mobile visual review pass.

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

- **Title:** Bound Streamlit dashboard log and directory read-model work [Impact: 3/5, Effort: 2/5]
  - Explanation: `src/generators/streamlit_dashboard_generator.py` reads full log files before slicing and runs repeated recursive directory walks for dashboard count cards. UI cache helps reruns but cache misses still scale with full log size and repeated walks.
  - Pros: More predictable dashboard latency and memory use as logs and output directories grow.
  - Cons: Requires service-boundary changes so generators do not add direct filesystem optimizations.
  - Acceptance Criteria:
    - `file_service` exposes a bounded tail-read contract for text logs and the Streamlit generator uses it.
    - Directory counts use one grouped walk per root where possible, or a service-level multi-count operation with deterministic limits.
    - Tests cover large-log tail behavior, malformed log lines, overlapping directory patterns, and directory listing errors.
    - Dashboard read-model logs include bounded byte/line counts and grouped-walk metrics.

---

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

- **Title:** Build a backward/forward contract compatibility matrix [Impact: 4/5, Effort: 4/5]
  - Explanation: Contract round-trip tests and schema snapshots exist, but persisted artifacts and stored rows still lack a first-class compatibility matrix across schema versions.
  - Pros: Safer staged deploys and clearer breaking-change discipline.
  - Cons: Larger fixture surface and more adapter maintenance.
  - Acceptance Criteria:
    - Compatibility suites run in CI for representative current and previous contract versions.
    - Adapter or migration logic has positive and negative tests.
    - Breaking changes require explicit version-bump evidence.
    - Representative stored artifacts are covered by fixture snapshots.

- **Title:** Add end-to-end tracing across orchestrator/generator/service boundaries [Impact: 4/5, Effort: 3/5]
  - Explanation: Structured logs carry run/task/span fields, but there is no complete trace assembly view across a full report, publish, or cross-report workflow.
  - Pros: Faster incident analysis and better verification of control-plane/domain/service separation.
  - Cons: Needs trace correlation without creating new cross-role coupling.
  - Acceptance Criteria:
    - A trace read model reconstructs workflow stages from existing structured events.
    - Missing required log fields or broken parent/child span relationships are detectable in tests.
    - At least one report workflow, one publish workflow, and one cross-report workflow have trace coverage.
    - README documents trace inspection and common failure interpretation.

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
- Generic "add more CI" wording. Active CI work must target specific drift that current gates do not catch.
- Empty audit sections from earlier consolidated TODO versions.

## Near-Term Launch Plan

### Phase 1: Highest-Leverage Controls

- Real-time spend guardrails at run/day/publisher scopes with explicit override flow.
- Budget-aware model routing with deterministic compaction.
- Durable publish snapshot decision: real jobs/outbox or explicit readiness-snapshot naming.
- WordPress report post-type naming cleanup.

### Phase 2: Intelligence Reuse and Public Entity Alignment

- Claim-level embedding persistence and embedding workflow.
- Public entity projection coverage for Figures, Regions, and Time Periods, or README narrowing.
- WordPress render-time intelligence synthesis replacement with approved projections.

### Phase 3: Resilience and Performance

- Provider failover behind the canonical LLM service contract.
- Measured PDF hot-path optimization.
- Contract compatibility matrix.
- Role-mixing/monolith-growth CI enforcement.
- End-to-end trace read model.
