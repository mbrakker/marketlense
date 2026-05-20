# Consolidated TODO

Last compiled: 2026-05-20

This file is the single source of truth for open backlog items. It supersedes the remaining backlog plus the archived planning work from `docs/quality/deep-analysis-x10-plan-2026-04-15.md`.

Items below were re-based against the current repository state, not against earlier planning assumptions. Completed or materially landed capabilities are removed from the active backlog. Partially landed capabilities stay only when there is a clear remaining gap.

Deep-analysis evidence used for this consolidation:

- Architecture import gate passed on 2026-05-01: `python scripts/ci/check_architecture_imports.py`.
- Forbidden patching gate passed on 2026-05-01: `python scripts/ci/check_forbidden_patching.py`.
- CI already runs formatting, typing, architecture-import, forbidden-patching, repository-hygiene, quality-ledger, remediation-runbook, backlog-source, contract-schema, coverage, mutation, quality-regression, and prompt-fixture regression gates through `.github/workflows/ci.yml`.
- Prompt dry-run infrastructure and fixture-corpus regression are already landed through `src/contracts/prompts.py`, `src/services/prompt_service.py`, `scripts/ci/check_prompt_fixture_regression.py`, `tests/test_prompt_dry_run_validation.py`, and `tests/test_prompt_fixture_corpus_regression.py`.
- `docs/quality/initiative_ledger.yaml` now marks `ocr-confidence-gating` as completed. Native-text confidence thresholds and OCR fallback controls already exist in `src/config/app.yaml` and `src/generators/report_source_generator.py`.
- Publisher-discovery typed route traces, scenario summaries, deferred recovery recipes, recovery-cache persistence, direct-detail handling, default-on rollout flags, and KPI guardrail logs are already landed in code, tests, and docs.
- Targeted validation regeneration and claim/evidence binding are already landed through `src/generators/report_regeneration_generator.py`, `src/generators/validation/*`, and the current README validation sections.
- `src/services/idempotency_service.py` is already live and now backs the publish boundary plus the remaining side-effecting write steps in `report_download_orchestrator` and `publisher_inventory_orchestrator`, with checksum/outcome/artifact-reference persistence documented in `README.md`.
- Candidate extraction already performs binary page triage and shared page-artifact/fingerprint caching through `src/services/_pdf/figures.py`, `src/services/_pdf/page_artifacts.py`, and `src/services/_pdf/fingerprint_cache.py`.
- `src/services/llm_service.py` still logs `provider_decision="openai_primary"` and `budget_decision="not_configured"`, which is the strongest current signal that dynamic routing, provider failover, and spend-aware policy are still missing.
- `src/services/vector_store_service.py` supports create/upload/attach/status/update, but delete/prune lifecycle operations are still absent.
- Long-file concentration shifted after April refactors and the May facade work. Remaining first-party hotspots from `python scripts/count_long_files.py` are concentrated in deeper PDF/browser internals, publisher-discovery workflow internals, and large paired tests rather than the public `config_service`, `openai_service`, `artifact_generator`, `publisher_inventory_service`, and `report_download_orchestrator` boundaries.
- Recent facade splits establish the required shape for future hotspot work: keep one public boundary file and move semantic families into a same-name internal folder. Current reference examples are `src/services/report_store_service.py` over `src/services/_report_store_service/*`, `src/generators/report_generation_dependencies.py` over `src/generators/_report_generation_dependencies/*`, `src/services/config_service.py` over `src/services/_config_service/*`, `src/services/openai_service.py` over `src/services/_openai_service/*`, and `src/generators/artifact_generator.py` over `src/generators/_artifact_generator/*`.

Removed from the active backlog because the core capability already ships:

- OCR confidence gating and native-confidence-based OCR fallback controls.
- Prompt dry-run namespace validation scaffolding and prompt-fixture corpus regression baseline.
- Targeted artifact regeneration for mapped validation failures, including deterministic TOC repair.
- Claim/evidence span binding and validation-level evidence normalization.
- Core publisher-discovery memory/recovery/direct-detail implementation work.
- Report-store and report-generation dependency facade splits.
- UI-run dead-letter workflow, replay manifests, and operator triage surfaces.

How to use this backlog:

- Treat this file as the only active TODO source.
- Remove items once their acceptance criteria are fully met.
- Keep overlapping work merged into one item with explicit source notes in the explanation when needed.
- Every prioritized item must get an owner, baseline metric, target metric, and expiry/review date before implementation starts.

Scoring rubric:

- `Impact`: `1` low leverage, `5` highest leverage across reliability, quality, cost, speed, or architecture.
- `Effort`: `1` localized change, `5` broad refactor/migration with cross-module coordination.

Suggested priority order:

1. `1. Spend Guardrails, LLM Routing & Prompt Evaluation`
2. `4. Publisher Discovery Rollout & Precision`
3. `5. Idempotency, Checkpoints & Publish Durability`
4. `3. PDF Extraction, OCR & Candidate Ranking`
5. `7. Architecture Simplification, CI & Observability`

---

## 1. Spend Guardrails, LLM Routing & Prompt Evaluation

- **Title:** Extend the prompt fixture corpus into variant-aware promotion scorecards [Impact: 4/5, Effort: 4/5]
  - Explanation: The repo already validates active namespaces and measures the prompt fixture corpus, but only for the currently active template pair per namespace. The remaining gap is controlled prompt variants, deterministic selection, offline scorecards, and promotion policy.
  - Pros: Safer prompt iteration, measurable quality/cost tradeoffs, cleaner rollouts.
  - Cons: More benchmark maintenance and CI/runtime cost.
  - Acceptance Criteria:
    - Config supports multiple named variants per prompt namespace.
    - Prompt selection is deterministic and logged with namespace, variant, hashes, rendered prompts, model parameters, and cost data.
    - Corpus metrics are emitted per namespace plus variant, not only per namespace.
    - Promotion policy defines when a variant can replace the default.

- **Title:** Implement budget-aware model routing with deterministic context compaction [Impact: 5/5, Effort: 4/5]
  - Explanation: Model resolution is still mostly static through `openai_models` and namespace matching, while `llm_service` logs `budget_decision="not_configured"`. The next step is policy-driven model tiering, context budgeting, and deterministic compaction before requests exceed practical token or cost limits.
  - Pros: Material cost and latency reduction, fewer timeout risks, explicit quality/cost tradeoffs.
  - Cons: Requires careful evidence-retention tests and benchmark ownership.
  - Acceptance Criteria:
    - Policy table maps task families to model tier, max input budget, fallback tier, and quality threshold.
    - Routing decision, budget decision, compaction strategy, and reason are logged for each call.
    - Over-budget requests are compacted by deterministic policy rather than ad hoc trimming.
    - Regression tests protect key evidence retention.
    - Benchmarks show meaningful token/cost reduction without quality regression on a fixed corpus.

- **Title:** Add provider failover behind one LLM response contract [Impact: 5/5, Effort: 5/5]
  - Explanation: Production report generation still depends on one OpenAI-backed LLM path even though other repo areas know about OpenRouter/browser-provider settings. The missing piece is a provider-agnostic generator contract plus orchestrated primary/secondary failover for report-pipeline LLM work.
  - Pros: Higher availability during provider incidents and cleaner provider isolation.
  - Cons: More integration-test surface and normalized error-handling complexity.
  - Acceptance Criteria:
    - Primary and secondary provider policy is explicit and tested.
    - Provider responses and errors are normalized into one typed generator-facing contract.
    - Generators do not branch on provider-specific response shapes.
    - Failure-injection tests prove logged failover behavior and successful fallback.

- **Title:** Enforce real-time spend guardrails across run/day/publisher budgets [Impact: 5/5, Effort: 2/5]
  - Explanation: Cost ledger append and rollup paths exist, but they are post-hoc reporting only. There is still no pre-call policy that warns, pauses, or blocks expensive model/browser/OCR work based on live spend.
  - Pros: Prevents runaway spend and makes cost decisions operationally visible.
  - Cons: May block legitimate runs without a good override flow.
  - Acceptance Criteria:
    - YAML config defines thresholds for run, day, and publisher scopes.
    - Orchestrators check thresholds before model, browser, OCR, or other expensive calls.
    - Breaches emit typed events, structured logs, and explicit policy outcome (`warn`, `pause`, `stop`, `override`).
    - Tests cover warn, hard-stop, and operator-override paths.

---

## 2. Resource Lifecycle & Vector Stores

- **Title:** Add vector-store deletion, prune, and retention cleanup [Impact: 3/5, Effort: 3/5]
  - Explanation: The vector-store boundary currently covers create/upload/attach/status/update, but not retention cleanup. `analysis.vector_store_keep` can express intent, yet no canonical delete/prune path exists to clean up remote assets deterministically.
  - Pros: Avoids orphaned remote storage and repeated provider cost.
  - Cons: Risk of deleting useful assets if retention policy is wrong; requires strong idempotency.
  - Acceptance Criteria:
    - Delete and prune request/response dataclass contracts exist.
    - `vector_store_service` exposes canonical delete/prune operations with structured logging.
    - Orchestrators run cleanup when retention is disabled or expiry is reached.
    - Tests cover missing remote assets, duplicate cleanup calls, and retention-disabled runs.

---

## 3. PDF Extraction, OCR & Candidate Ranking

- **Title:** Upgrade binary page triage into scored, recall-calibrated page gating [Impact: 5/5, Effort: 4/5]
  - Explanation: Candidate extraction already skips obvious full-page-scan/no-text negatives and excludes contents pages. The remaining gap is richer page-value scoring before chart/table extraction and crop refinement so expensive PDF work is reduced with measurable recall protection.
  - Pros: Better throughput on large reports and fewer wasted extraction passes.
  - Cons: False negatives become dangerous if scoring is aggressive or poorly calibrated.
  - Acceptance Criteria:
    - Per-page triage reason and score are logged.
    - Thresholds and skip policy are configurable.
    - Evaluation fixtures define a recall floor that the triage gate must preserve.
    - Stage metrics show extraction work avoided without quality regression.

- **Title:** Fix the table dedupe hot path in `table_candidates.py` and `table_heuristics.py` [Impact: 4/5, Effort: 3/5]
  - Explanation: Table extraction still performs nested candidate comparison in the final dedupe path, and the deeper heuristics module remains one of the largest first-party hotspots. Replace the O(n^2)-style merge path with a keyed or spatially indexed approach while preserving conservative merge behavior.
  - Pros: Faster processing on dense and wide PDFs.
  - Cons: Requires careful correctness tests to avoid false merges or missed duplicates.
  - Acceptance Criteria:
    - Dedupe logic is rewritten around an indexed candidate lookup instead of repeated full scans.
    - Benchmarks on large fixtures show lower runtime.
    - Correctness tests cover near-duplicate, overlapping, and distinct-table cases.
    - Candidate quality does not regress on existing fixture reports.

---

## 4. Publisher Discovery Rollout & Precision

- **Title:** Wire verified route memory into reviewable browser/publisher playbook promotion [Impact: 4/5, Effort: 3/5]
  - Explanation: Browser-route playbook contracts, YAML loading, selection, and promotion helpers exist, but live report-download and publisher-discovery runs only persist route memory in SQLite. The missing gap is an orchestrated promotion path that turns verified, reusable route evidence into reviewable playbook files or explicit skip records.
  - Pros: Converts successful live runs into durable reusable guidance, reduces repeated browser exploration, and makes route learning reviewable in git.
  - Cons: Needs conservative promotion gates so one-off or noisy routes do not become misleading durable guidance.
  - Acceptance Criteria:
    - Report-download orchestration invokes playbook promotion, or records a typed skip reason, after verified/recovered successful routes with usable route steps.
    - Promotion is idempotent and writes reviewable YAML diffs under `src/playbooks/browser_routes/` without duplicating existing generic playbooks.
    - Publisher-inventory route traces/scenario summaries either get an equivalent playbook export path or an explicit documented decision to keep them as SQLite-only route memory.
    - Config controls promotion mode (`disabled`, `dry_run`, `write`) and logs selected policy, playbook path, version, and review diff metadata.
    - Pipeline tests prove eligible live-style route evidence creates/updates a playbook, while unverified, unsuccessful, or insufficient-history routes are skipped with typed reasons.

## 5. Idempotency, Checkpoints & Publish Durability

- **Title:** Introduce durable, checkpointed pipeline stages with semantic restart [Impact: 5/5, Effort: 5/5]
  - Explanation: Replay manifests exist for UI runs, but the report pipeline itself still resumes by rerunning whole stages rather than restarting from durable semantic checkpoints with artifact references.
  - Pros: Faster recovery, lower rerun cost, better operator control.
  - Cons: Requires checkpoint versioning, storage modeling, and migration discipline.
  - Acceptance Criteria:
    - Checkpoint contracts exist for major pipeline stages.
    - Stage checkpoints store artifact references plus schema versions.
    - Resume tooling supports restarting from a selected stage boundary.
    - Consistency tests compare full-run output with resumed-run output.

- **Title:** Turn the publish queue into durable jobs with transactional outbox, retry, and idempotency [Impact: 5/5, Effort: 5/5]
  - Explanation: The current `publish_queue_orchestrator.py` only builds a snapshot for UI and ops views. It does not persist publish intents as durable jobs or atomically couple publish-side effects to state transitions.
  - Pros: More reliable publishing and clearer recovery from partial failures.
  - Cons: Adds queue/outbox infrastructure and operational behavior.
  - Acceptance Criteria:
    - Publish jobs can be enqueued, persisted, retried, and dead-lettered.
    - Outbox records side-effect intents atomically with related state changes.
    - Delivery attempts are idempotent and logged.
    - Failure-injection tests cover restart, retry, duplicate dispatch, and partial WordPress failures.

---

## 6. Schema Compatibility & Repair

- **Title:** Build a backward/forward contract compatibility matrix [Impact: 4/5, Effort: 4/5]
  - Explanation: Contract round-trip tests and schema snapshots already exist, but the repo still lacks a first-class compatibility matrix for persisted artifacts and stored rows across schema versions.
  - Pros: Safer staged deploys and clearer breaking-change discipline.
  - Cons: Larger fixture surface and more adapter maintenance.
  - Acceptance Criteria:
    - Compatibility suites run in CI for representative current and previous contract versions.
    - Adapter or migration logic has positive and negative tests.
    - Breaking changes require explicit version-bump evidence.
    - Representative stored artifacts are covered by fixture snapshots.

- **Title:** Expand targeted regeneration beyond the current artifact-family repair map [Impact: 4/5, Effort: 4/5]
  - Explanation: Targeted regeneration already handles mapped artifact families and deterministic TOC repair. The remaining gap is broader pack-level or rule-specific repair routing so more validation failures can be fixed without broad reruns.
  - Pros: Fewer full reruns and clearer repair behavior.
  - Cons: Repair-taxonomy maintenance burden.
  - Acceptance Criteria:
    - Failure classes map to explicit repair actions beyond the current artifact-family set.
    - Repair attempts log before/after diffs and the exact regenerated artifacts or packs.
    - Benchmarks show lower full-regeneration volume on known failure fixtures.
    - Negative-path tests prove unsupported repair targets fail explicitly.

---

## 7. Architecture Simplification, CI & Observability

- **Title:** Extend CI gates from current quality coverage into role-mixing and monolith-growth enforcement [Impact: 4/5, Effort: 3/5]
  - Explanation: The repo already has strong CI coverage, so the remaining gap is not "add more generic checks." The useful next step is automation around role mixing, direct-I/O drift, service integration coverage waivers, and first-party long-file growth.
  - Pros: Prevents architectural drift earlier and keeps the current rule set enforceable.
  - Cons: Requires careful allowlist design for legitimate edge cases.
  - Acceptance Criteria:
    - New gate logic flags role mixing, direct I/O drift, or monolith-growth violations on first-party files.
    - Allowlist entries require owner plus expiry date.
    - Missing per-service integration coverage requires either a marked test or an explicit temporary waiver.
    - README documents how to add and retire waivers.

---

## Priority Launch Plan

### Phase 1: Highest-Leverage Controls (2-4 weeks)

- Real-time spend guardrails at run/day/publisher scopes with explicit override flow.
- Discovery rollout of structured memory, deferred recovery, and direct-detail routing with KPI gates.
- Prompt variant scorecards on top of the existing prompt-fixture corpus.

### Phase 2: Throughput and Durability (4-8 weeks)

- Budget-aware model routing with deterministic context compaction.
- Scored PDF page gating and table-dedupe rewrite.
- Vector-store cleanup and retention orchestration.

### Phase 3: Resilience and Compatibility (8-16+ weeks)

- Provider failover behind one LLM response contract.
- Durable checkpoint/restart for report pipeline stages.
- Durable publish jobs with transactional outbox.
- Contract compatibility matrix for persisted artifacts and stored rows.
- End-to-end tracing across orchestrator/generator/service boundaries.

---

## 8. Deep Codebase Audit (2026-05-06)

- **Title:** Tighten risk-policy scope so doc-only changes cannot hide repository-wide CI breakage [Impact: 4/5, Effort: 1/5]
  - Explanation: Current risk classification marks a `CONSOLIDATED_TODO.md`-only change as `docs` while the repository remains red on hard gates. This can create false confidence during maintenance updates.
  - Pros: Better signal to maintainers, fewer “green-looking” local checks when mainline is failing.
  - Cons: May mark more changes as higher risk and increase required local preflight work.
  - Acceptance Criteria:
    - Risk-policy output surfaces current repository CI health independently from changed-file classification.
    - For docs-only changes, policy clearly reports whether hard gates are presently failing on mainline baseline.
    - Operator docs include a “docs-only but repo-red” handling path.
