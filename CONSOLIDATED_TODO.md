# Consolidated TODO

Last compiled: 2026-04-25

This file is the single source of truth for open backlog items. It now includes the remaining consolidated backlog plus the moved items from `docs/quality/deep-analysis-x10-plan-2026-04-15.md`.

Items are grouped by workstream. Duplicates were merged. Each task includes: title, explanation (what & why), pros & cons, and acceptance criteria.

Completed items are removed from this backlog once their acceptance criteria are met. Prefer adding new tasks under the most relevant workstream instead of creating new append-only audit sections.

Deep-analysis evidence used for this consolidation:

- Architecture import gate passes: `python scripts/ci/check_architecture_imports.py`.
- Forbidden patching gate passes: `python scripts/ci/check_forbidden_patching.py`.
- Long-file concentration remains high in `src/services/report_store_service.py`, `src/services/_pdf/visual_heuristics.py`, `src/services/_browser_report_download/artifact.py`, `src/services/config_service.py`, `src/ui/streamlit_pages.py`, `src/services/_browser_report_download/browser.py`, `src/services/publisher_inventory_service.py`, `src/generators/report_selection_generator.py`, and large paired tests.
- Additional hotspots from the 2026-04-25 scan: `src/generators/report_generation_dependencies.py` imports 37 internal dependencies, several model-call paths mix `openai_service` and `llm_service`, SQLite DDL/migrations are embedded in service startup paths, and tracked `tmp_*` artifacts still exist despite ignore rules.
- Current x10 opportunities concentrate around cost-aware LLM routing, PDF/OCR triage, resumable orchestration, browser acquisition stability, publish durability, and regression gates.

How to use this backlog:

- Treat this file as the only active TODO source.
- Remove items once their acceptance criteria are fully met.
- Keep overlapping work merged into one item with explicit source notes in the explanation when needed.
- Every prioritized item must get an owner, baseline metric, target metric, and expiry/review date before implementation starts.

Scoring rubric:

- `Impact`: `1` low leverage, `5` highest leverage across reliability, quality, cost, speed, or architecture.
- `Effort`: `1` localized change, `5` broad refactor/migration with cross-module coordination.

Suggested priority order:

1. `10. Bugs & Defects`
2. `1. LLM, Prompts, Cost & Provider Policy`
3. `3. PDF, OCR, Candidate Extraction & Ranking`
4. `5. Orchestration, State, Idempotency & Scheduling`
5. `6. Publishing & WordPress`
6. `8. CI, Observability, Governance & Release Safety`
7. `9. Architecture Simplification & Code Reduction`

---

## 1. LLM, Prompts, Cost & Provider Policy

- **Title:** Upgrade prompt namespaces and add repository-wide prompt dry-run validation [Impact: 4/5, Effort: 3/5]
  - Explanation: Merge the existing prompt-upgrade work with a CI dry-run that renders every active prompt namespace against declared fixture inputs. This prevents prompt drift, missing variables, and unlogged prompt changes before runtime.
  - Pros: Better output quality, safer generation, clearer audit trail, faster failures.
  - Cons: Requires maintaining representative fixture inputs for each prompt family.
  - Acceptance Criteria:
    - All active prompt namespaces render successfully in CI.
    - Missing variables and template syntax errors fail before runtime.
    - Prompt file paths, version/hash, exact rendered prompts, and model parameters are logged for each model call.
    - Fixture coverage exists for report, validation, ranking, browser-download, and publishing prompt families.

- **Title:** Build a prompt namespace manifest and stop full-tree prompt scans on steady-state reads [Impact: 3/5, Effort: 3/5]
  - Explanation: `src/services/prompt_service.py` discovers namespaces by recursively scanning `src/prompts/**`. Add a manifest or cached namespace inventory so UI/tooling can list prompts without repeated traversal and hashing.
  - Pros: Faster settings/prompt screens, less filesystem churn, simpler prompt discovery behavior.
  - Cons: Manifest invalidation and regeneration must be reliable.
  - Acceptance Criteria:
    - Prompt namespace listing no longer requires full recursive scans for steady-state reads.
    - Manifest/cache invalidation occurs when prompt files change.
    - Prompt listing tests cover add, remove, rename, and stale-manifest scenarios.

- **Title:** Add prompt variant/A-B harness with offline scored corpora [Impact: 4/5, Effort: 4/5]
  - Explanation: Merge multi-prompt variants and the deep-analysis A/B harness into one capability: config-driven variants, deterministic selection, fixed corpora, and scorecards for schema validity, grounding, and cost.
  - Pros: Higher-quality outputs, safer prompt iteration, data-driven rollout decisions.
  - Cons: Increases evaluation cost and requires benchmark ownership.
  - Acceptance Criteria:
    - Config accepts multiple variants per prompt namespace.
    - Per-variant prompt hashes, rendered prompts, model parameters, costs, and scores are logged.
    - Offline scorecards include schema-valid, grounding, latency, and token/cost metrics.
    - Promotion policy defines when a variant can become default.

- **Title:** Implement budget-aware model routing with deterministic context compaction [Impact: 5/5, Effort: 4/5]
  - Explanation: Merge adaptive model routing and prompt-budget planning. Route low-risk steps to cheaper/faster models, preserve premium models for high-risk tasks, and compact over-budget context by deterministic policy rather than ad hoc trimming.
  - Pros: Major cost and latency reduction, fewer timeout risks, explicit quality/cost tradeoffs.
  - Cons: Requires quality guardrails, fallback policy, and careful evidence-retention tests.
  - Acceptance Criteria:
    - Policy table maps task families to model tiers, max input budget, fallback tier, and quality threshold.
    - Routing decision, budget decision, compaction strategy, and reason are logged per call.
    - Over-budget requests are trimmed by deterministic policy.
    - Regression tests protect key-evidence retention.
    - Benchmark shows material token/cost reduction without quality regression on a fixed corpus.

- **Title:** Add provider failover behind one compatible LLM response contract [Impact: 5/5, Effort: 5/5]
  - Explanation: Add a secondary provider path and normalize provider responses into one contract. Keep provider-specific details at the service boundary, while generators consume one typed response shape.
  - Pros: Higher availability during provider incidents and cleaner provider isolation.
  - Cons: Multi-provider complexity, cost variance, and more integration tests.
  - Acceptance Criteria:
    - Primary/secondary fallback policy exists and is tested.
    - Error taxonomy is normalized across providers.
    - Generator contracts do not depend on provider-specific response shapes.
    - Disaster-recovery test demonstrates failover success with logged provider decisions.

- **Title:** Make LLM policy enforcement the single model-call path [Impact: 5/5, Effort: 4/5]
  - Explanation: Several generators and services still mix direct `openai_service` calls with `llm_service` policy wrappers. Consolidate retries, rate limits, circuit breakers, budget checks, semantic cache policy, and provider selection behind one canonical model-call boundary so every model request follows the same controls.
  - Pros: Simpler mental model, consistent cost/retry behavior, less duplicated model-call plumbing.
  - Cons: Requires migrating call sites and preserving existing test seams.
  - Acceptance Criteria:
    - All production model calls go through one canonical LLM/OpenAI service boundary.
    - Direct `openai_service` imports outside the canonical boundary are removed or explicitly allowlisted with expiry.
    - Retry, circuit-breaker, rate-limit, budget, cache, and provider decisions are logged on every model call.
    - Tests prove generators can still mock only the public service boundary.

- **Title:** Move browser-download task prompts into prompt-service namespaces [Impact: 3/5, Effort: 2/5]
  - Explanation: Browser-download instructions currently live in service-side prompt construction. Move them into dedicated prompt namespaces so they are versioned, hash-logged, dry-run validated, and maintained with the rest of the prompt system.
  - Pros: Better prompt observability, easier iteration, less service-level string assembly.
  - Cons: Requires explicit prompt-variable contracts and fixture updates.
  - Acceptance Criteria:
    - Browser-download task text is loaded and rendered only through prompt service.
    - Prompt paths, hashes, rendered text, and model parameters are logged for browser-download runs.
    - Existing browser-download tests cover prompt rendering and missing-variable failures.

---

## 2. Cost, Resource Lifecycle & Artifact Durability

- **Title:** Enforce real-time spend guardrails across run/day/publisher budgets [Impact: 5/5, Effort: 2/5]
  - Explanation: Merge existing cost-limit work with the deep-analysis spend-guardrail item. Add hard and soft caps by run, day, and publisher, with policy outcomes such as warn, pause, stop, or explicit override.
  - Pros: Prevents runaway spend and makes cost decisions operationally visible.
  - Cons: May block valid runs without a clear override path.
  - Acceptance Criteria:
    - Configurable thresholds exist in YAML for run, day, and publisher scopes.
    - Orchestrators check thresholds before model or expensive browser/OCR calls.
    - Breaches emit typed events, state updates, and structured logs.
    - Tests cover warn, pause, hard-stop, and operator override behavior.

- **Title:** Add vector store deletion and lifecycle cleanup [Impact: 3/5, Effort: 3/5]
  - Explanation: Extend vector-store service boundaries with delete/prune APIs and add orchestrator hooks to remove remote assets when retention is disabled or expiry is reached.
  - Pros: Avoids orphaned storage and repeated remote costs.
  - Cons: Risk of deleting useful artifacts if policies are wrong; requires idempotency.
  - Acceptance Criteria:
    - Delete/prune APIs exist and return typed dataclass results.
    - Cleanup policies are driven by config and orchestrated with idempotency keys.
    - Cleanup logs include run/task/span identifiers and outcomes.
    - Tests cover missing remote assets, duplicate cleanup calls, and retention-disabled runs.

- **Title:** Make analysis packs, HTML renders, semantic caches, and ledger artifacts atomic on write [Impact: 4/5, Effort: 3/5]
  - Explanation: Several services write directly to final paths. Use temp-file plus atomic replace semantics for analysis packs, rendered HTML, OpenAI semantic cache files, cost ledgers, and replay/forensic artifacts.
  - Pros: Better durability and fewer corrupted artifacts after interrupted runs.
  - Cons: Slight write-path complexity and temp cleanup requirements.
  - Acceptance Criteria:
    - Target write paths use atomic replace semantics.
    - Interrupted writes cannot leave partial final artifacts.
    - Tests cover overwrite, failure-mid-write, and stale temp cleanup scenarios.

- **Title:** Add performance and cost regression gate for fixture corpus [Impact: 5/5, Effort: 3/5]
  - Explanation: Add CI or scheduled regression checks for runtime, token usage, OCR usage, browser attempts, and generated cost per fixture corpus. This prevents slow/cost creep after optimization work lands.
  - Pros: Sustains speed/cost gains and catches regressions early.
  - Cons: Benchmarks need stable fixtures and variance handling.
  - Acceptance Criteria:
    - Baseline budgets are stored as versioned artifacts.
    - CI or nightly checks fail on unapproved regressions.
    - Reports include per-stage deltas for runtime, tokens, OCR calls, browser attempts, and cost.
    - Allowlist entries require explicit justification and expiry.

---

## 3. PDF, OCR, Candidate Extraction & Ranking

- **Title:** Add page-level triage before expensive PDF extraction [Impact: 5/5, Effort: 4/5]
  - Explanation: Score pages for likely information value before visual extraction, table extraction, cropping, and OCR. Appendix-heavy documents can avoid large amounts of waste while preserving recall through conservative thresholds.
  - Pros: Major throughput and cost gain on large reports.
  - Cons: False negatives are risky if triage is too aggressive.
  - Acceptance Criteria:
    - Triage score is computed per page and logged.
    - Skip policy is configurable and conservative by default.
    - Evaluation set confirms required recall threshold.
    - Stage metrics show extraction/crop/OCR work avoided.

- **Title:** Add OCR confidence gating with native-first selective fallback [Impact: 5/5, Effort: 2/5]
  - Explanation: Use native text extraction first and call OCR only when text confidence, density, or page-quality thresholds fail. This can cut OCR spend substantially on mixed corpora.
  - Pros: Lower cost and latency with clearer OCR rationale.
  - Cons: Thresholds need calibration and ongoing monitoring.
  - Acceptance Criteria:
    - Native text confidence metric is defined and logged per page/document.
    - OCR is called only when the threshold fails or policy explicitly requires it.
    - Negative tests prove weak native text triggers OCR.
    - Cost report shows reduced OCR usage on fixture corpus.

- **Title:** Add deterministic per-page/per-figure fingerprint cache [Impact: 5/5, Effort: 3/5]
  - Explanation: Cache expensive intermediate PDF outputs at sub-document granularity. Fingerprints must include content, page/figure identity, parser versions, settings, and prompt/model versions where relevant.
  - Pros: High rerun speedups and lower CPU/model cost.
  - Cons: Adds cache lifecycle and invalidation complexity.
  - Acceptance Criteria:
    - Fingerprint includes content plus parser/settings/version components.
    - Cache invalidation is tied to version changes.
    - Partial-change rerun benchmark demonstrates speedup.
    - Cache-hit logs include key, source artifact, and validity reason.

- **Title:** Fix O(n^2) table dedupe hotspot [Impact: 4/5, Effort: 3/5]
  - Explanation: Replace the O(n^2) table dedupe algorithm in candidate extraction with a hash/index-assisted approach that preserves conservative merge behavior.
  - Pros: Better performance on large PDFs.
  - Cons: Requires careful tests to avoid false merges and missed duplicates.
  - Acceptance Criteria:
    - Dedupe algorithm is updated and benchmarked with large PDFs.
    - Correctness tests cover near-duplicate, overlapping, and distinct-table cases.
    - No regression in candidate quality on fixture reports.

- **Title:** Pre-filter and compress candidate payload before LLM ranking [Impact: 4/5, Effort: 3/5]
  - Explanation: Reduce ranking prompt size by applying conservative deterministic filters and compact payload representations before LLM ranking.
  - Pros: Lower cost and faster ranking.
  - Cons: Risk of discarding rare but valuable candidates; thresholds must be conservative.
  - Acceptance Criteria:
    - A deterministic pre-filter step exists with safe defaults.
    - Prompt payload size and ranking cost are measured before/after.
    - Held-out ranking quality does not regress.
    - Filter decisions are logged with reason codes.

- **Title:** Refactor PDF visual/table heuristics around stable semantic sub-capabilities [Impact: 4/5, Effort: 4/5]
  - Explanation: Long-file analysis shows very large PDF heuristic modules. Reduce complexity by extracting only true semantic sub-capabilities, such as geometry normalization, panel detection, legend handling, table-grid scoring, and candidate merge policy. Avoid pass-through helper layers.
  - Pros: Simpler defect isolation, easier targeted tests, lower cognitive load.
  - Cons: Refactor risk is high because heuristic behavior is fragile.
  - Acceptance Criteria:
    - Each extracted module has one semantic responsibility and no pass-through-only wrapper role.
    - Public PDF service entrypoints remain canonical and unchanged for callers.
    - Golden fixture outputs are unchanged except for explicitly approved improvements.
    - Long-file report shows reduced concentration in PDF heuristic hotspots.

---

## 4. Browser Acquisition & Publisher Inventory

- **Title:** Add DOM-event quorum stabilization for browser terminal states [Impact: 4/5, Effort: 3/5]
  - Explanation: Replace brittle fixed sleeps with route-family stabilization policies based on URL, DOM markers, network/download events, page text, and button state. Browser services currently include explicit waits and terminal-state polling that should become evidence-based.
  - Pros: More deterministic browser automation and lower flake rate.
  - Cons: Requires route-family instrumentation and careful timeout tuning.
  - Acceptance Criteria:
    - Stabilization policy is codified per route family.
    - Terminal-state logs include quorum evidence.
    - Fixed sleeps are removed or justified by explicit browser boundary constraints.
    - Flake rate is measured before/after in CI or integration runs.

- **Title:** Persist failure forensics packs for failed acquisition attempts [Impact: 3/5, Effort: 3/5]
  - Explanation: Standardize HAR, DOM snapshot, screenshots, terminal evidence, route plan, and classified error metadata for failed HTTP/browser acquisition attempts.
  - Pros: Faster root-cause analysis and better replay evidence.
  - Cons: Storage and retention policy overhead.
  - Acceptance Criteria:
    - Failed attempts attach forensic bundle metadata.
    - Logs include artifact links, route family, terminal evidence, and error class.
    - Retention policy controls sensitive or large artifacts.
    - Triage playbook uses the bundle consistently.

- **Title:** Introduce shared HTTP acquisition executor with session pooling and response policy [Impact: 4/5, Effort: 4/5]
  - Explanation: Browser-download and publisher-inventory HTTP paths issue repeated raw `requests.get` calls with similar timeout, header, redirect, error, and capture handling. Add one internal HTTP acquisition executor per acquisition boundary with pooled sessions, optional HEAD/range probes, response-size caps, retry classification, and sanitized response metadata.
  - Pros: Faster repeated HTTP acquisition, fewer duplicated request branches, clearer error taxonomy.
  - Cons: Must preserve route-specific behavior and avoid hiding useful failure evidence.
  - Acceptance Criteria:
    - HTTP acquisition calls use a shared executor/session helper inside the acquisition service boundary.
    - Executor logs request metadata, response metadata, byte caps, redirect chain, and error taxonomy.
    - Tests cover timeout, redirect, oversized response, partial download, retryable failure, and permanent failure cases.
    - Benchmark shows reduced connection overhead on repeated publisher/report acquisition.

- **Title:** Externalize publisher-inventory browser scripts and traversal state [Impact: 3/5, Effort: 4/5]
  - Explanation: `src/services/publisher_inventory_service.py` embeds large JavaScript snippets with repeated selector, visibility, and normalization helpers. Move browser action/state extraction into named internal script builders or assets, reuse one helper bundle, and model traversal-state updates through explicit typed helpers.
  - Pros: Smaller service surface, less duplicated browser logic, easier targeted tests.
  - Cons: Requires careful script-loading and browser-test updates.
  - Acceptance Criteria:
    - Inline browser action/state scripts are replaced by named internal script builders or assets.
    - Shared selector, visibility, and normalization logic is defined once and reused.
    - Traversal state/metrics updates use explicit helpers instead of repeated manual dataclass reconstruction.
    - Browser-inventory tests cover the extracted script/runtime contract.

- **Title:** Add deferred acquisition recovery recipes for high-confidence failures [Impact: 4/5, Effort: 3/5]
  - Explanation: Existing discovery docs identify second-pass recovery opportunities. Implement typed, bounded recovery recipes for strong candidates rejected due to recoverable landing-page/browser failures, without bypassing quality gates.
  - Pros: Higher acquisition yield on difficult publishers.
  - Cons: Adds recovery policy complexity and can increase browser cost.
  - Acceptance Criteria:
    - Recovery recipe contract defines trigger, retry limit, route, and stop conditions.
    - Orchestrators schedule recovery only for high-confidence, recoverable failures.
    - Recovery never bypasses artifact validation or landing-page quality gates.
    - Metrics compare recovered candidates against added cost.

---

## 5. Orchestration, State, Idempotency & Scheduling

- **Title:** Introduce durable, checkpointed pipeline stages with semantic restart [Impact: 5/5, Effort: 5/5]
  - Explanation: Merge durable pipeline checkpoints and checkpoint/restart into one program. Store stage-level checkpoints with artifact references so failed runs can resume from semantic boundaries instead of full reruns.
  - Pros: Faster recovery, lower rerun cost, better operator control.
  - Cons: Requires state modeling, migration, and checkpoint versioning.
  - Acceptance Criteria:
    - Checkpoint contracts are defined per major stage.
    - Stage-level checkpoints are stored with artifact references and schema versions.
    - Resume command supports selected stage restart.
    - Consistency tests compare full run vs resumed run output.

- **Title:** Add idempotency checksum per side-effecting orchestrator step [Impact: 5/5, Effort: 3/5]
  - Explanation: Persist stable idempotency keys and prior outcomes for side-effecting steps so retries cannot duplicate files, DB rows, vector stores, Drive uploads, WordPress posts, or notifications.
  - Pros: Retry safety and cleaner failure handling.
  - Cons: Requires careful key semantics and migration of existing side effects.
  - Acceptance Criteria:
    - Side-effecting steps persist idempotency key, input checksum, outcome, and artifact references.
    - Duplicate invocation returns prior outcome or fails with a typed mismatch error.
    - Tests validate no duplicate rows, remote assets, files, or publications.
    - Idempotency decisions are logged with run/task/span fields.

- **Title:** Add event-sourced state transitions with immutable audit log [Impact: 5/5, Effort: 5/5]
  - Explanation: Record lifecycle transitions as immutable events so state can be reconstructed, replayed, and audited after failures.
  - Pros: Strong auditability, deterministic replay, better debugging.
  - Cons: Migration complexity and storage growth.
  - Acceptance Criteria:
    - Transition events are stored append-only with run/task/span IDs.
    - Current state can be reconstructed from the event stream.
    - Replay tooling reproduces lifecycle transitions.
    - Tests cover migration from current state snapshots to event-backed reconstruction.

- **Title:** Move SQLite schema changes into explicit migration ledgers [Impact: 5/5, Effort: 4/5]
  - Explanation: `report_store_service`, `analytics_store_service`, `state_service` internals, and run-registry services embed `CREATE TABLE`, `ALTER TABLE`, and table rebuild logic in runtime service initialization. Replace ad hoc startup migrations with versioned migration ledgers per database boundary.
  - Pros: Safer upgrades, faster startup, clearer rollback/replay behavior, easier schema review.
  - Cons: Requires migration tooling and careful conversion of existing inline migrations.
  - Acceptance Criteria:
    - Each SQLite database has a schema version table and ordered migration ledger.
    - Service startup applies only pending migrations and logs migration IDs/durations.
    - Migration tests cover fresh DB, old DB upgrade, failed migration rollback, and idempotent re-run.
    - Inline `ALTER TABLE`/table-rebuild logic is removed from normal service code paths.

- **Title:** Add dead-letter workflow with typed triage categories [Impact: 4/5, Effort: 3/5]
  - Explanation: Route irrecoverable runs into dead-letter states with structured diagnosis metadata instead of leaving them as ambiguous failures.
  - Pros: Keeps primary queues healthy and improves human triage throughput.
  - Cons: Requires process ownership and dashboard support.
  - Acceptance Criteria:
    - Dead-letter states and categories are defined.
    - Auto-triage metadata includes error taxonomy, stage, publisher/report identity, and last artifact links.
    - Ops dashboards expose dead-letter backlog and age trends.
    - Recovery or discard actions are logged.

- **Title:** Move vector-store wait loops into orchestrator retry policy [Impact: 4/5, Effort: 3/5]
  - Explanation: Service boundaries should expose status fetches, while polling/backoff/wait policy belongs in orchestrators. Keep OpenAI/vector service calls focused on one external interaction.
  - Pros: Cleaner role boundaries, easier retry testing, reusable status checks.
  - Cons: Requires touching vector-store orchestration and dependent tests.
  - Acceptance Criteria:
    - Service layer exposes status fetch without internal wait loops.
    - Polling/backoff lives in orchestrators or retry helpers with structured logging.
    - Vector-store timeout/failure behavior is preserved by pipeline tests.

- **Title:** Promote MD5 sidecar handling into a dedicated typed file-cache service [Impact: 3/5, Effort: 3/5]
  - Explanation: `src/orchestrators/ingest_orchestrator.py` owns sidecar path construction, JSON parsing, stat reconciliation, and fallback logic. Move it behind a service/contract pair so ingest orchestration consumes typed cache answers.
  - Pros: Smaller orchestrator surface and fewer ad hoc cache behaviors.
  - Cons: Requires moving a well-tested but intertwined path across layers.
  - Acceptance Criteria:
    - Sidecar pathing, load, validation, and write logic live behind a service boundary.
    - Ingest orchestration no longer parses sidecar JSON directly.
    - Existing cache-hit/cache-miss behavior is preserved by tests.

- **Title:** Add dynamic concurrency controller with capacity-aware publisher fairness [Impact: 5/5, Effort: 4/5]
  - Explanation: Merge dynamic concurrency and fair scheduling. Adjust concurrency based on queue depth, failure budget, cost budget, browser capacity, and publisher cohort fairness.
  - Pros: Better throughput stability, less starvation, safer burst handling.
  - Cons: Control-loop tuning complexity.
  - Acceptance Criteria:
    - Controller reads queue depth, recent failure metrics, browser capacity, and budget state.
    - Scheduling policy includes per-cohort quotas or weights.
    - Concurrency and fairness decisions are logged with rationale.
    - Load/simulation tests show improved stability and no cohort starvation.

- **Title:** Add per-stage feature flags for controlled rollout [Impact: 3/5, Effort: 3/5]
  - Explanation: Add feature flags at stage boundaries for controlled rollouts, A/B tests, emergency disable switches, and cost containment.
  - Pros: Safer deployments and operational control.
  - Cons: Adds configuration surface and flag governance.
  - Acceptance Criteria:
    - Per-stage flags are configurable in YAML and read by orchestrators.
    - Disabled stages fail explicitly, skip explicitly, or use a documented fallback policy.
    - Tests validate enabling/disabling key stages.

---

## 6. Publishing & WordPress

- **Title:** Turn publish queue into durable jobs with transactional outbox, retry, and idempotency [Impact: 5/5, Effort: 5/5]
  - Explanation: Merge publish-queue durability and transactional outbox. Persist publish intents, commit state and side-effect intents atomically, dispatch with retry/backoff, and make delivery idempotent.
  - Pros: More reliable publishing, fewer partial-commit inconsistencies, easier retry handling.
  - Cons: Adds queue/outbox infrastructure and operational behavior.
  - Acceptance Criteria:
    - Publish jobs can be enqueued, persisted, retried, and dead-lettered.
    - Outbox table records side-effect intents atomically with state changes.
    - Delivery attempts are idempotent and logged.
    - Failure-injection tests cover restart, retry, duplicate dispatch, and partial WordPress failures.

- **Title:** Parallelize WordPress media uploads and resolve auth once [Impact: 4/5, Effort: 3/5]
  - Explanation: Speed up publishing by parallelizing media uploads and passing the resolved auth header through the publish request flow. Avoid deriving auth independently in both orchestrator and generator paths.
  - Pros: Faster publish time and simpler auth flow.
  - Cons: Requires concurrency and rate-limit handling.
  - Acceptance Criteria:
    - Media uploads run in parallel with bounded concurrency and rate-limit handling.
    - Auth header is resolved once at the orchestration boundary.
    - No duplicate auth derivation remains in the publish path.

- **Title:** Introduce shared WordPress request executor with pooled sessions and error adaptation [Impact: 4/5, Effort: 4/5]
  - Explanation: `src/services/wordpress_service.py` repeats request setup, SSL handling, error parsing, and JSON adaptation. Centralize REST execution behind one internal executor backed by a pooled `requests.Session`.
  - Pros: Less duplicated HTTP code, lower connection overhead, consistent error taxonomy.
  - Cons: Requires careful migration of per-endpoint behavior and logging details.
  - Acceptance Criteria:
    - WordPress REST calls go through one shared executor/session helper.
    - Request/response logging and error taxonomy remain intact.
    - Connection reuse is covered by service tests or instrumentation.

- **Title:** Batch WordPress preflight, taxonomy, and tag resolution [Impact: 3/5, Effort: 3/5]
  - Explanation: Merge batch preflight and taxonomy/tag ensure work. Resolve publish state, validation status, existing posts, terms, and tag creation plans once per publish run instead of one file or term at a time.
  - Pros: Fewer repeated service calls and clearer skip/error decisions.
  - Cons: Adds a precomputed snapshot that must remain consistent.
  - Acceptance Criteria:
    - Publish preflight data is loaded in batch for the selected HTML set.
    - Term lookup and creation planning happens per taxonomy/tag set.
    - Per-file publish decisions consume the batch snapshot.
    - Tests verify parity with current skip, existing-post, mixed existing/new term, and failure behavior.

- **Title:** Remove duplicate HTML reads and parses from publish path [Impact: 3/5, Effort: 2/5]
  - Explanation: Publish orchestration can read HTML once to extract metadata and then process the same HTML again downstream. Carry loaded HTML and parsed metadata through the publish request path.
  - Pros: Less file I/O, simpler publish control flow, fewer parsing inconsistencies.
  - Cons: Requires request/contract changes between orchestrator and generator.
  - Acceptance Criteria:
    - Publish flow reads each HTML artifact at most once per attempt.
    - File ID extraction, validation lookup, and publish generation reuse the same loaded HTML payload.
    - Publish tests cover preloaded and non-preloaded entry paths.

---

## 7. Schema, Validation, Output Quality & Rendering

- **Title:** Build backward/forward contract compatibility matrix [Impact: 4/5, Effort: 4/5]
  - Explanation: Add compatibility tests for current and previous contract versions, including adapter/migration paths, so rolling runs and stored artifacts survive contract evolution.
  - Pros: Safer phased deploys and clearer breaking-change discipline.
  - Cons: Larger fixture and test surface.
  - Acceptance Criteria:
    - Contract compatibility suites run in CI.
    - Adapter logic has positive and negative tests.
    - Breaking changes require explicit version bump evidence.
    - Serialized fixture snapshots cover representative stored artifacts.

- **Title:** Split oversized contract modules by semantic contract families [Impact: 4/5, Effort: 4/5]
  - Explanation: Contract files such as `publisher_inventory.py`, `browser_download.py`, and `report_store.py` are over 1k lines and mix many request/response families. Split them only by stable semantic families while keeping dataclasses as the single source of truth and preserving public import compatibility where needed.
  - Pros: Easier contract review, smaller schema-diff blast radius, clearer ownership.
  - Cons: Import migration can be noisy if compatibility shims are not handled carefully.
  - Acceptance Criteria:
    - Oversized contract modules are split by semantic families, not arbitrary file size.
    - Public compatibility imports remain during migration with documented removal dates.
    - Contract round-trip and schema snapshot tests cover every moved dataclass.
    - No generator/service logic is introduced into contract modules.

- **Title:** Add confidence and abstain mode for evidence/artifact families [Impact: 5/5, Effort: 3/5]
  - Explanation: Generated artifact families should emit confidence and abstain when evidence is too weak, routing to targeted regeneration or explicit omission instead of shipping unsupported output.
  - Pros: Higher trust profile and fewer factual defects.
  - Cons: Adds fallback states and policy decisions.
  - Acceptance Criteria:
    - Confidence score is emitted per generated artifact family.
    - Low-confidence policy routes to regeneration or explicit abstain.
    - Validation metrics show reduced unsupported claims.
    - HTML/publish flows handle abstained artifacts explicitly.

- **Title:** Add ensemble validation with schema, deterministic rules, and LLM verifier [Impact: 5/5, Effort: 4/5]
  - Explanation: Combine orthogonal validators to catch failure modes that one validator misses. Aggregate conflicts into a typed validation report instead of hiding disagreement.
  - Pros: Higher robustness and better defect detection.
  - Cons: Additional compute and orchestration complexity.
  - Acceptance Criteria:
    - Multi-validator pipeline emits an aggregated validation report.
    - Conflicts between validators are surfaced explicitly.
    - Regression suite demonstrates improved defect detection on known bad fixtures.

- **Title:** Bind every non-trivial claim to evidence spans and render citation micro-lines [Impact: 5/5, Effort: 4/5]
  - Explanation: Merge claim-span binding with existing citation/quote formatting work. Claims should carry evidence references tied to doc_map/page offsets, and rendered artifacts should expose concise citation micro-lines.
  - Pros: Better auditability, lower hallucination risk, clearer reader trust signals.
  - Cons: Requires robust span extraction and mapping.
  - Acceptance Criteria:
    - Claim contracts include evidence/span references for non-trivial claims.
    - Validation rejects unsupported claims.
    - HTML renders citation micro-lines with evidence ID and page where available.
    - `Unknown` quote speaker labels become `Unattributed in report`.

- **Title:** Add deterministic failure-to-fix planner for targeted regeneration [Impact: 4/5, Effort: 4/5]
  - Explanation: Map known validation failure classes to deterministic repair recipes before full regeneration, reducing expensive broad reruns.
  - Pros: Fewer full reruns and clearer repair behavior.
  - Cons: Rule maintenance burden.
  - Acceptance Criteria:
    - Failure taxonomy maps to repair actions.
    - Repair attempts log before/after diffs and exact regenerated artifacts.
    - Benchmarks show lower regeneration volume.

- **Title:** Modernize report HTML rendering and editorial data visibility [Impact: 4/5, Effort: 4/5]
  - Explanation: Merge HTML template refactor, responsive assets, and editorial visibility improvements into one rendering program. Extract repeated template blocks into macros/partials, externalize stable CSS, pass image dimensions, add responsive variants, and surface report focus year, fieldwork dates, ordered chapters, methodology, coverage, findings, limitations, contact info, and improved TL;DR/executive-summary structure.
  - Pros: Better readability, lower template duplication, improved Core Web Vitals, clearer report provenance.
  - Cons: Touches rendering contracts, templates, and golden outputs.
  - Acceptance Criteria:
    - No duplicated preview/figure branches remain in `templates/report.html.j2`.
    - Templates use shared CSS/macros while preserving relative asset conventions.
    - Images render width/height plus `srcset`/`sizes` where variants exist.
    - Metadata appears below TL;DR; summary renders as concise bullets.
    - Methodology, coverage, findings, limitations, contact, semantic section labels, and ordered chapters render when data exists, with explicit empty states where required.
    - Golden render tests approve only intentional changes.

- **Title:** Add infographic asset generation for HTML and LinkedIn [Impact: 2/5, Effort: 4/5]
  - Explanation: Create a generator/service pair that produces simple infographic SVG/PNG assets from highlights, persists metadata, and exposes assets to HTML and publishing flows.
  - Pros: Richer publishable artifacts and better social sharing.
  - Cons: Additional generation cost and pipeline complexity.
  - Acceptance Criteria:
    - Infographic assets are generated per report and stored with metadata.
    - HTML rendering includes generated infographic references where available.
    - Publish artifacts contain asset links.

---

## 8. CI, Observability, Governance & Release Safety

- **Title:** Harden architecture and test-integrity gates beyond current import/patch checks [Impact: 4/5, Effort: 3/5]
  - Explanation: Current import and forbidden-patching gates pass. Extend enforcement to role-mixing heuristics, direct I/O drift, monolithic-module growth, missing integration tests per service, required log-field checks, and contract round-trip coverage.
  - Pros: Prevents architectural drift and keeps tests hard to fake.
  - Cons: Requires curated exemptions for legitimate edge cases.
  - Acceptance Criteria:
    - Existing import and forbidden-patching gates remain in CI.
    - Gates report role mixing, direct I/O violations, and missing service integration coverage.
    - At least one marked integration test exists per service boundary or an explicit allowlist entry with expiry exists.
    - Required structured log fields are asserted for each orchestrator and service.
    - Contract round-trip tests cover every added/modified dataclass contract.

- **Title:** Add repository artifact and secret hygiene gate [Impact: 5/5, Effort: 2/5]
  - Explanation: The scan found tracked temporary JSON/JSONL artifacts even though `.gitignore` blocks local outputs and secrets. Add a CI gate that rejects committed runtime artifacts, local credentials, token files, coverage outputs, probe downloads, and oversized generated files unless explicitly allowlisted.
  - Pros: Lower security risk, smaller repository, faster clone/search/test cycles.
  - Cons: Requires one-time cleanup and an allowlist for intentional fixtures.
  - Acceptance Criteria:
    - CI fails on tracked files matching runtime artifact, credential, token, cache, log, coverage, or probe-output patterns.
    - Existing tracked `tmp_*` artifacts are removed or moved into documented fixtures if still needed.
    - Allowlist entries require owner, reason, max size, and expiry.
    - Pre-commit or local script provides the same check before CI.

- **Title:** Decompose mega-tests into behavior suites with shared fixture builders [Impact: 4/5, Effort: 4/5]
  - Explanation: Tests such as `test_browser_report_download_service.py`, `test_pdf_figures_service.py`, and `test_publisher_inventory_service.py` are thousands of lines long. Split them by externally observable behavior and introduce shared builders that keep assertions semantic rather than broad mock narratives.
  - Pros: Faster review, easier targeted test runs, clearer failure localization.
  - Cons: Refactor can accidentally weaken tests if assertions are not preserved.
  - Acceptance Criteria:
    - Mega-tests are split by behavior family with stable fixture builders.
    - Each split file keeps positive, negative, log-field, and remove-the-logic sentinel coverage where applicable.
    - No new private-helper monkeypatching or tautological assertions are introduced.
    - Test runtime and failure localization metrics improve or remain neutral.

- **Title:** Add end-to-end tracing across orchestrator, generator, and service boundaries [Impact: 4/5, Effort: 3/5]
  - Explanation: Add trace spans for major pipeline boundaries and correlate them with run/task/span IDs to make critical-path timing and dependencies visible.
  - Pros: Faster bottleneck localization and stronger observability.
  - Cons: Telemetry overhead and storage planning.
  - Acceptance Criteria:
    - Trace spans are created for major orchestrator/generator/service boundaries.
    - Trace IDs correlate with run/task/span IDs in logs.
    - Dashboard or report surfaces critical-path timing.

- **Title:** Add failure taxonomy anomaly detection [Impact: 4/5, Effort: 4/5]
  - Explanation: Monitor error distributions for unusual spikes by stage, provider, route family, and publisher cohort.
  - Pros: Earlier reliability regression detection.
  - Cons: False positives during calibration.
  - Acceptance Criteria:
    - Baseline failure distributions are established.
    - Drift detector alerts on significant deviations.
    - Alert payload includes likely affected modules and recent change context.

- **Title:** Add flaky test detector and quarantine workflow [Impact: 4/5, Effort: 3/5]
  - Explanation: Detect intermittently failing tests and separate them from stable merge gates with explicit owner accountability and SLA.
  - Pros: Cleaner CI signal and better merge velocity.
  - Cons: Requires process enforcement.
  - Acceptance Criteria:
    - Flake detector records reproducibility rate.
    - Quarantined tests are tracked with owner, reason, and SLA.
    - Merge gate excludes quarantined tests only with explicit reporting.

- **Title:** Add nightly chaos/retry/idempotency stress suite [Impact: 4/5, Effort: 4/5]
  - Explanation: Validate transient failures, lock contention, retry storms, provider failures, browser timeouts, and duplicate side-effect attempts outside the normal fast CI path.
  - Pros: Stronger reliability under realistic failure modes.
  - Cons: Extra runtime and infrastructure cost.
  - Acceptance Criteria:
    - Stress suite includes failure-injection scenarios.
    - Attempt counts, backoff decisions, state transitions, and idempotency outcomes are asserted.
    - Results feed a reliability dashboard or summary artifact.

- **Title:** Add PR quality bot for schema, coverage, mutation, cost, and risk diffs [Impact: 4/5, Effort: 3/5]
  - Explanation: Post a high-signal PR summary with changed contracts, schema snapshots, coverage deltas, mutation score deltas, cost/performance benchmark deltas, and architecture-gate risk.
  - Pros: Faster, higher-quality reviews for complex changes.
  - Cons: Bot maintenance and noise tuning.
  - Acceptance Criteria:
    - Bot comment includes risk summary and key quality deltas.
    - Links to failing gates and artifacts are present.
    - Noise threshold is tuned with review feedback.

- **Title:** Add canary ingestion/release train with automatic rollback gates [Impact: 5/5, Effort: 4/5]
  - Explanation: Ship risky pipeline changes progressively with health checks and rollback on validation, cost, latency, or error SLO breach.
  - Pros: Smaller blast radius and safer production changes.
  - Cons: Deployment orchestration effort.
  - Acceptance Criteria:
    - Canary cohorts and rollback thresholds are defined.
    - Rollback triggers on validation, cost, latency, or error SLO breaches.
    - Post-deploy report records canary outcomes.

- **Title:** Add operational runbooks and auto-remediation hooks for top failures [Impact: 4/5, Effort: 2/5]
  - Explanation: Pair top typed failure classes with remediation scripts, runbooks, and dashboard/alert links.
  - Pros: Lower MTTR and reduced manual triage.
  - Cons: Needs disciplined upkeep.
  - Acceptance Criteria:
    - Top failure classes map to remediation actions.
    - Runbooks are linked in alerts/dashboard.
    - Monthly drill verifies runbook freshness.

- **Title:** Run monthly quality ledger review and prune low-ROI initiatives [Impact: 3/5, Effort: 1/5]
  - Explanation: Track each x10 initiative with baseline/current/target metrics and remove or re-plan work that fails to show measurable impact.
  - Pros: Sustained governance discipline and less roadmap sprawl.
  - Cons: Requires recurring ownership.
  - Acceptance Criteria:
    - Monthly review agenda and owners are established.
    - Each initiative reports baseline/current/target metrics.
    - Stalled items are de-scoped or re-planned explicitly.

---

## 9. Architecture Simplification & Code Reduction

- **Title:** Split long-file hotspots only along real capability boundaries [Impact: 5/5, Effort: 5/5]
  - Explanation: Long-file analysis identifies concentration in report store, PDF heuristics, browser-download artifact handling, config service, Streamlit pages, publisher inventory, and report selection. Refactor only where module boundaries reduce real coupling, improve test isolation, or clarify ownership; do not create pass-through layers.
  - Pros: Higher simplicity, lower cognitive load, better defect containment.
  - Cons: Large refactors can add fragmentation if boundaries are artificial.
  - Acceptance Criteria:
    - Each split has a documented semantic responsibility and concrete reason.
    - Canonical service/generator/orchestrator entrypoints remain discoverable.
    - No new pass-through wrapper modules are introduced.
    - Long-file report shows reduced concentration in the named hotspots.
    - Golden and behavior tests prove parity or explicitly approved improvements.

- **Title:** Replace report-generation mega dependency bundle with capability-scoped dependency contracts [Impact: 4/5, Effort: 4/5]
  - Explanation: `src/generators/report_generation_dependencies.py` imports dozens of services, generators, and contracts, making report-generation flows hard to understand and easy to over-couple. Split dependency bundles by capability boundary such as source preparation, vector/evidence, artifact generation, validation/regeneration, rendering, and metadata persistence.
  - Pros: Smaller dependency surfaces, easier tests, clearer generator/orchestrator wiring.
  - Cons: Requires careful migration to avoid pass-through wrappers and duplicate configuration.
  - Acceptance Criteria:
    - Capability-specific dependency dataclasses replace the single broad dependency bundle.
    - Each generator receives only dependencies it actually uses.
    - Orchestrators remain responsible for wiring and retry policy.
    - Tests fail if unused or cross-capability dependencies are reintroduced.

- **Title:** Persist normalized publisher lookup keys and replace Python-side table scans [Impact: 4/5, Effort: 4/5]
  - Explanation: `src/services/report_store_service.py` repeatedly loads publisher rows and normalizes `insights_url` in Python for route and inventory lookups/updates. Persist normalized lookup keys in the database, index them, and query/update rows directly in SQL.
  - Pros: Faster publisher-state lookups, less repeated normalization logic, smaller service methods.
  - Cons: Requires schema migration and collision handling.
  - Acceptance Criteria:
    - Normalized publisher lookup columns are stored and backfilled.
    - Indexed SQL lookups replace `fetchall()` plus Python filtering paths.
    - Collision behavior is defined and tested.
    - Existing route/inventory tests pass against the migrated schema.

- **Title:** Stream Drive listings and bound Drive client/scope caches [Impact: 3/5, Effort: 3/5]
  - Explanation: Merge Drive pagination streaming, recursive folder-scope caching, and bounded thread-scoped client caches. Large-folder operations should yield incrementally, reuse stable folder topology, and evict stale clients.
  - Pros: Lower memory usage, fewer Drive API calls, cleaner long-lived process behavior.
  - Cons: Partial-failure and invalidation semantics need care.
  - Acceptance Criteria:
    - Drive file listing yields results incrementally across pages.
    - Recursive folder-scope expansion is cached with explicit TTL or invalidation.
    - Thread-scoped client cache has bounded size/lifetime.
    - Tests cover partial completion, folder changes, reuse, eviction, and concurrent access.

- **Title:** Simplify config editing into smaller capability-owned paths [Impact: 4/5, Effort: 4/5]
  - Explanation: `src/services/config_service.py` is one of the largest services and likely owns multiple config capabilities. Split only stable semantic areas, such as app settings, identity settings, publisher profiles, validation policy, and UI-safe redaction, while preserving one canonical config service boundary.
  - Pros: Easier config changes, clearer tests, smaller blast radius.
  - Cons: Risk of unnecessary layering if split too aggressively.
  - Acceptance Criteria:
    - One canonical config service boundary remains for callers.
    - Internal capability modules each own a distinct config concern.
    - No duplicate constants or competing config entrypoints are introduced.
    - Config tests are grouped by capability and preserve current behavior.

- **Title:** Decompose Streamlit UI pages by workflow without nested card/layout drift [Impact: 3/5, Effort: 4/5]
  - Explanation: `src/ui/streamlit_pages.py` is a long UI coordination file. Move workflow-specific views into existing `src/ui/app_pages/**` modules when that reduces coupling and improves scanability.
  - Pros: Easier UI maintenance and clearer page ownership.
  - Cons: Streamlit session-state behavior can regress during moves.
  - Acceptance Criteria:
    - `streamlit_pages.py` becomes navigation/composition only.
    - Workflow views live in capability-owned page modules.
    - Session-state contracts remain explicit and tested.
    - UI tests cover navigation and representative page rendering.

- **Title:** Keep supplemental code-reduction intake merged into concrete workstream tasks [Impact: 2/5, Effort: 1/5]
  - Explanation: Avoid reintroducing append-only audit backlogs. Any remaining code-reduction ideas from older docs must be converted into concrete workstream items with acceptance criteria before implementation.
  - Pros: Prevents TODO sprawl and duplicate planning.
  - Cons: Requires backlog discipline.
  - Acceptance Criteria:
    - No active TODO source exists outside this file.
    - New audit findings are merged into existing items or added as concrete workstream tasks.
    - Duplicate titles or overlapping acceptance criteria are removed during review.

---

## 10. Bugs & Defects

- **Title:** Fix type-check gate blind spot and current full-repo mypy failures [Impact: 5/5, Effort: 4/5]
  - Explanation: `python scripts/ci/run_type_check.py` currently skips when no changed Python files are detected, but a direct `python -m mypy src` run reports 270 errors across 70 files. The failures include UI run branch type confusion, optional dict access, branded ID/string mismatches, and platform-specific process-service typing.
  - Pros: Restores trust in the type gate and catches real regressions earlier.
  - Cons: Broad cleanup touches many modules and may require a temporary baseline.
  - Acceptance Criteria:
    - CI has a full-repo or baseline-enforced type-check job in addition to any changed-file fast path.
    - `python -m mypy src` passes, or a checked-in baseline tracks every remaining error with owner and expiry.
    - `ui_run_execution_orchestrator` branch variables are typed per run type instead of reusing incompatible variables across branches.
    - New Python changes cannot add unbaselined mypy errors.

- **Title:** Fix UI run worker payload coercion and generic failure classification [Impact: 4/5, Effort: 3/5]
  - Explanation: `src/orchestrators/ui_run_execution_orchestrator.py` directly coerces payload values such as `int(payload["limit"])` inside workflow branches. Invalid UI payloads fall through the broad `except Exception` path and are reported as `ui_run_worker_failed` instead of typed validation errors.
  - Pros: Clearer operator errors, safer UI run replay, better negative-path tests.
  - Cons: Requires per-run-type payload validation contracts and test updates.
  - Acceptance Criteria:
    - Each UI run type validates and normalizes its payload before invoking workflow logic.
    - Invalid numeric/string payloads raise typed `AppError` codes with field-level context.
    - The broad `except Exception` path no longer masks expected validation failures.
    - Tests cover invalid `limit`, missing required URL/path fields, and replay of failed UI runs.

- **Title:** Replace pass-only exception swallowing in production paths [Impact: 4/5, Effort: 3/5]
  - Explanation: Static scan found pass-only exception handlers in production modules including browser cleanup/shutdown, browser-download artifacts, PDF figure/table/text extraction, logging setup, and process termination. These paths can hide cleanup leaks, parser defects, or lost observability.
  - Pros: Makes latent failures visible and easier to triage.
  - Cons: Some cleanup paths need careful non-fatal logging to avoid noisy failures.
  - Acceptance Criteria:
    - Pass-only `except` handlers are removed or explicitly allowlisted with justification and expiry.
    - Non-fatal cleanup failures are logged with `run_id`, `task_id`, `span_id`, `role`, `module`, and `event`.
    - Parser/extraction failures either return typed degraded results with reason codes or raise typed `AppError`.
    - Tests assert logs or errors for representative browser cleanup, PDF extraction, and logging handler-close failures.

- **Title:** Normalize browser-download boolean signals before terminal-state decisions [Impact: 3/5, Effort: 2/5]
  - Explanation: Browser-download code compares model/result fields with exact identity checks such as `payload.get("email_submission_completed") is True`. If a model or worker emits `"true"`, `"yes"`, `1`, or other truthy serialized values, terminal-state and recovery decisions can be misclassified.
  - Pros: More robust browser form handling and fewer false recovery/skipped states.
  - Cons: Needs strict normalization so ambiguous values do not become false positives.
  - Acceptance Criteria:
    - Browser agent result adaptation normalizes boolean-like fields through one strict helper.
    - Terminal-state decisions use normalized booleans, not raw `is True`/`is False` checks.
    - Tests cover native booleans, string booleans, numeric booleans, missing fields, and ambiguous values.
    - Logs include the raw and normalized terminal-signal summary when values are ambiguous.

- **Title:** Stop PDF triage/extraction failures from silently changing candidate scope [Impact: 4/5, Effort: 3/5]
  - Explanation: PDF candidate planning currently catches triage/extraction exceptions and can continue by including pages or keeping stale text, which may silently broaden candidate scope or hide parser bugs. This can degrade speed and ranking quality without a visible failure reason.
  - Pros: More deterministic candidate extraction and easier PDF parser debugging.
  - Cons: Some malformed PDFs may need explicit degraded-mode policies.
  - Acceptance Criteria:
    - PDF triage failures are counted, logged, and reflected in typed extraction stats.
    - Degraded behavior is policy-driven: fail, include page with warning, or skip page with warning.
    - Candidate extraction tests cover triage exception, page text exception, and malformed PDF paths.
    - Ranking payloads include degraded-page reason codes when candidates come from degraded extraction.

- **Title:** Classify corrupt cache/state artifacts instead of silently degrading [Impact: 4/5, Effort: 3/5]
  - Explanation: Several cache and state readers return `None`, cache misses, or default values on JSON decode/type failures. Silent degradation can trigger unnecessary reruns, hide corrupted artifacts, and make reproduction from logs unreliable.
  - Pros: Better reproducibility, clearer rerun reasons, fewer hidden data-integrity failures.
  - Cons: Requires tuning which corrupt artifacts are fatal versus recoverable.
  - Acceptance Criteria:
    - Cache/state readers emit typed status codes for missing, invalid JSON, invalid schema, key mismatch, and expired artifacts.
    - Corrupt artifacts are logged with sanitized path, artifact kind, and recovery policy.
    - Orchestrators decide whether corrupt artifacts are retryable, recoverable, or fatal.
    - Tests cover corrupt sidecars, corrupt cache packs, corrupt cost rollups, and corrupt state JSON.

---

## Priority Launch Plan

### Phase 1: Highest-Leverage Foundations (2-4 weeks)

- Type-check gate blind spot and current full-repo mypy failures.
- UI run worker payload coercion and generic failure classification.
- Pass-only production exception swallowing.
- OCR confidence gating.
- Idempotency checksum per side-effecting orchestrator step.
- Real-time spend guardrails.
- Prompt dry-run validation.
- Performance/cost regression baseline.
- Repository artifact and secret hygiene gate.

### Phase 2: Speed and Recovery (4-8 weeks)

- Budget-aware model routing with deterministic context compaction.
- Page-level PDF triage.
- Durable checkpoint/restart.
- DOM-event quorum stabilization.
- Atomic artifact writes.
- Explicit SQLite migration ledgers.
- Canonical LLM model-call path.

### Phase 3: Resilience and Quality (8-16+ weeks)

- Provider failover contract.
- Ensemble validation and claim-span binding.
- Durable publish queue with transactional outbox.
- Canary release train.
- Dynamic concurrency and fairness controller.
- Shared HTTP acquisition executor.

### Phase 4: Simplicity and Maintainability (ongoing)

- Long-file hotspot splits by real capability boundary.
- Config service capability split.
- Streamlit workflow page decomposition.
- Contract module family split.
- Report-generation dependency-bundle split.
- Monthly quality ledger review.
