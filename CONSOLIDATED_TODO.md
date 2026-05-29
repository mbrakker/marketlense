# Consolidated TODO

Last compiled: 2026-05-29

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
- Complexity audit on 2026-05-20 identified remaining performance hotspots in validation retrieval, PDF visual/table candidate filtering, Streamlit dashboard read models, and crop-refinement recovery paths. WordPress shortcode/theme-loop scanner hits were reviewed as lower-priority small-collection/template loops unless profiling proves otherwise.
- GitHub Codex Connector PR review comments from PRs #24-#37 were triaged on 2026-05-21 and resolved on 2026-05-22.

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
  - Explanation: Table extraction still performs nested candidate comparison in the final dedupe path, and the deeper heuristics module remains one of the largest first-party hotspots. The 2026-05-20 complexity audit reconfirmed `src/services/_pdf/table_heuristics.py::_dedupe_table_candidates` as a concrete O(n^2) candidate merge path. Replace it with a keyed or spatially indexed approach while preserving conservative merge behavior.
  - Pros: Faster processing on dense and wide PDFs.
  - Cons: Requires careful correctness tests to avoid false merges or missed duplicates.
  - Acceptance Criteria:
    - Dedupe logic is rewritten around an indexed candidate lookup instead of repeated full scans.
    - Benchmarks on large fixtures show lower runtime.
    - Correctness tests cover near-duplicate, overlapping, and distinct-table cases.
    - Candidate quality does not regress on existing fixture reports.

- **Title:** Precompute PDF visual candidate relationships per page [Impact: 4/5, Effort: 4/5]
  - Explanation: Visual extraction still calls sibling, wrapper, and panel-shadow helpers that rescan `page_ctx.rect_items` for many candidates in `src/services/_pdf/visual_candidates.py` and `src/services/_pdf/_visual_heuristics/panel_detection.py`. This creates repeated O(r^2)-style page work on visually dense PDFs.
  - Pros: Faster chart/image extraction on report pages with many raster, drawing, or panel candidates.
  - Cons: Spatial-index behavior is easy to get subtly wrong; false accepts/rejects would affect figure quality.
  - Acceptance Criteria:
    - Per-page visual relationships are precomputed once using a bounded spatial index or equivalent grouped lookup.
    - Existing helper semantics for side-by-side siblings, oversized wrappers, heading-shadowed panels, stacked panels, and caption clamping are preserved.
    - PDF visual/table fixture tests cover dense-panel, multi-chart, decorative-image, and wrapper-image pages.
    - Benchmarks on dense visual fixtures show lower per-page runtime without candidate-quality regression.

- **Title:** Remove repeated crop-refinement recovery scans [Impact: 3/5, Effort: 1/5]
  - Explanation: `src/generators/_report_selection_generator/crop_refine.py` recovers missing LLM decisions by sorting missing IDs and repeatedly scanning phase candidate lists to find matching indices. This is a recovery-only path, but it is a straightforward O(m*n) hotspot when a batch returns many incomplete decisions.
  - Pros: Localized speedup, simpler recovery code, low behavioral risk.
  - Cons: Limited impact unless model responses omit many decisions.
  - Acceptance Criteria:
    - Coarse and finalize recovery paths build `{candidate.id: index}` once per phase before processing missing IDs.
    - Existing recovery ordering and logged `missing_candidate_ids` remain deterministic.
    - `tests/test_candidate_refine_selection.py` covers multiple missing IDs in one batch.
    - Type check and candidate-refine tests pass.

---

## 4. Publisher Discovery Rollout & Precision

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

- **Title:** Precompute validation evidence vectors and use bounded retrieval [Impact: 4/5, Effort: 3/5]
  - Explanation: `src/generators/validation/evidence.py` recomputes character n-gram vectors for every claim/window comparison and sorts every scored window for each retrieval call. Metrics, quotes, numbers, and regeneration grounding all share this path, so large evidence packs and PDF text caches pay the cost repeatedly.
  - Pros: Faster validation and targeted regeneration, especially on long reports with many evidence windows.
  - Cons: Retrieval ranking is correctness-sensitive; precomputed vectors must preserve deterministic ordering and tie behavior.
  - Acceptance Criteria:
    - `EvidenceWindow` or an adjacent validation contract stores precomputed n-gram counts/norms without ad hoc sentinel fields.
    - `retrieve_evidence_windows` computes the claim vector once and selects top results with a bounded heap or equivalent top-k strategy instead of sorting every scored window.
    - Golden tests assert retrieved window order for ties, duplicate text, quantity-heavy claims, empty inputs, and long PDF text.
    - Benchmarks show lower validation runtime on a large evidence fixture with no validation issue regression.

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

- **Title:** Bound Streamlit dashboard log and directory read-model work [Impact: 3/5, Effort: 2/5]
  - Explanation: `src/generators/streamlit_dashboard_generator.py` currently reads full log files before slicing the last N lines and runs repeated recursive directory walks for dashboard count cards. The UI cache reduces repeated reruns, but cache misses can still scale with full log size and `checks * files`.
  - Pros: More predictable dashboard latency and memory use as logs and output directories grow.
  - Cons: Requires a service-boundary change so generators do not add direct filesystem optimizations.
  - Acceptance Criteria:
    - `file_service` exposes a bounded tail-read contract for text logs and the Streamlit generator uses it.
    - Directory count collection performs one grouped walk per root where possible, or a service-level multi-count operation with deterministic limits.
    - Tests cover large-log tail behavior, malformed log lines, overlapping directory patterns, and directory listing errors.
    - Dashboard read-model logs include bounded byte/line counts and grouped-walk metrics.

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

---

## 9. Appendix Feature Audit (2026-05-22)

Scope: first-party runtime code under `src/`, CLI/UI entrypoints, and connected operator flows. This audit treats dynamically launched subprocess modules as live when a runtime caller invokes them by module name. It does not classify tests, CI-only gates, or vendored `tools/browser-use` code as product-flow usage.

Findings summary:

- Keep `src/services/_browser_report_download/browser_worker.py`: it is not statically imported, but `browser.py` launches it with `python -m src.services._browser_report_download.browser_worker`.
- Keep prompt dry-run validation: `prompt_service.validate_prompt_dry_run` is CI/quality infrastructure used by `scripts/quality/prompt_fixture_corpus_metrics.py` and tests, not an abandoned product feature.
- Keep optional evidence-pack variety scaffolding: the `key_metrics`, `risk_register`, `recommendations`, and `contradictions` strategies are gated but wired through `evidence_pack_generator`, validation, artifacts, and analytics projection.

- **Title:** Decide whether unused browser helper surface functions are real acquisition tools [Impact: 3/5, Effort: 3/5]
  - Evidence: README describes `browser_helper_coordinate_fallback_click`, `browser_helper_wait_for_load`, `browser_helper_ensure_real_tab`, `browser_helper_http_get`, and `get_browser_helper_surface` as part of the Marketlense browser helper surface. Runtime browser download currently imports and uses page info, screenshot, JavaScript, and form autocomplete helpers, but not those additional helper functions.
  - Assessment: Reintroduce only where the acquisition flow can call them with bounded policy and typed results; otherwise remove the unused helpers and README claims. Coordinate fallback is especially sensitive and should not exist as a dormant helper.
  - Acceptance Criteria:
    - Reintroduce path: preflight, terminal recovery, or route execution calls the helper through the browser-download service boundary with structured logs, bounded timeouts, and tests proving no persisted coordinate route memory.
    - Delete path: remove unused helper functions, contracts, README claims, and tests that validate unused narratives.
    - Browser-download prompts and route evidence labels match the helper surface that is actually callable.

- **Title:** Convert publish queue snapshot into real publish jobs or rename it as an ops snapshot [Impact: 5/5, Effort: 5/5]
  - Evidence: `publish_queue_orchestrator.py` is live in the UI, but it builds a read-only snapshot from HTML files and publish state. It does not enqueue durable publish intents or drive the publish workflow.
  - Assessment: Reintroduce as durable jobs if the product needs a queue. If not, rename the API/UI language to "publish readiness snapshot" to avoid implying a queue exists.
  - Acceptance Criteria:
    - Covered by the existing Section 5 item: "Turn the publish queue into durable jobs with transactional outbox, retry, and idempotency."
    - If not implemented as a queue, contracts, UI labels, docs, and logs stop using queue terminology for the snapshot-only feature.

---

## 10. Full Codebase Interconnection Audit (2026-05-22)

- **Title:** Reclaim retry, rate-limit, and circuit-breaker ownership from `llm_service` into orchestrators [Impact: 5/5, Effort: 4/5]
  - Explanation: `src/services/llm_service.py::_execute_with_policy` currently owns retry loops, sleeps, rate limiting, and circuit-breaker state for external LLM calls. That makes model latency, attempt counts, and spend side effects partly hidden inside a service boundary even though retry/backoff decisions belong to orchestrators. The same boundary is also exposed through `openai_service`, `llm_service`, and `vector_store_service`, with `vector_store_service` calling `llm_service` for OpenAI vector-store operations.
  - Pros: More predictable failure handling, cleaner attempt-count tests, stronger spend controls, and one clearer provider boundary.
  - Cons: Requires coordinated changes across model callers and retry tests.
  - Acceptance Criteria:
    - One canonical LLM/OpenAI service boundary owns raw provider calls and returns typed `AppError` values with retryability metadata, but does not sleep or retry internally.
    - Orchestrators own retry count, backoff, rate-limit policy, circuit-breaker policy, and spend-threshold checks for LLM/vector-store work.
    - `vector_store_service` no longer aliases `llm_service` as an OpenAI boundary; vector-store calls route through the canonical boundary or an explicitly documented provider-agnostic contract.
    - Tests assert retry attempt counts and sleep/backoff decisions at orchestrator level, and assert services make exactly one provider attempt per invocation.

- **Title:** Reduce browser-download and publisher-discovery internal monolith risk without adding pass-through layers [Impact: 4/5, Effort: 4/5]
  - Explanation: The largest first-party modules remain concentrated in behavior-heavy internals: `src/services/_browser_report_download/artifact.py`, `src/services/_browser_report_download/browser.py`, `src/orchestrators/_report_download_orchestrator/workflow.py`, `src/services/_publisher_inventory_service/workflow.py`, and `src/orchestrators/publisher_inventory_orchestrator.py`. These files combine many route, recovery, evidence, and terminal-state paths, making defect containment and review difficult even though public facades already exist.
  - Pros: Easier reasoning about failure paths, lower review risk, better targeted tests.
  - Cons: Refactor risk is meaningful because these flows are integration-heavy and stateful.
  - Acceptance Criteria:
    - Split only by stable capability families such as terminal evidence, route memory, browser execution, artifact finalization, recovery cache, and snapshot/state recording.
    - Public service/orchestrator entrypoints remain singular; callers do not choose between competing routes.
    - Each extracted module has real behavior and tests, not pass-through forwarding.
    - Golden and failure-injection tests prove report download and publisher discovery outputs remain unchanged.

---

## 11. README, WordPress Design & Publish Entity Alignment Audit (2026-05-29)

Scope: gaps identified by comparing the README direction against the current `src/` implementation and the `Wordpress/wp-content` block theme/plugin. These items cover public information architecture, WordPress design, publish entities, and naming drift.

- **Title:** Align WordPress public navigation with the README entity model [Impact: 4/5, Effort: 2/5]
  - Explanation: README defines the primary public navigation as Reports, Topics, Signals, Briefings, and Publishers, with Figures, Regions, Time Periods, and Methodology as secondary surfaces. The current WordPress nav exposes Reports, Topics, Publishers, Methodology, and About, so Signals and Briefings are missing from the primary path while Methodology/About are promoted differently than documented.
  - Pros: Makes the public site match the documented product model and gives users stable destinations for canonical entities.
  - Cons: Requires coordinated theme/plugin/template updates and content migration decisions for any existing pages.
  - Acceptance Criteria:
    - WordPress primary navigation renders Reports, Topics, Signals, Briefings, and Publishers in that order unless README is explicitly changed.
    - Methodology is moved to the documented secondary surface or README is updated to define it as primary.
    - About is either documented as a public support page outside the canonical entity nav or removed from the primary nav.
    - Navigation tests or static checks verify required nav labels and destinations.

- **Title:** Add first-class WordPress destinations for Signals and cross-report Briefings [Impact: 5/5, Effort: 4/5]
  - Explanation: README treats Signal and Briefing as canonical public entities. Briefing generation already exists as cross-report analysis/publish packages, but WordPress does not expose those packages as a canonical Briefing archive/detail surface. Signals currently exist only as shortcode-driven, signal-like modules.
  - Pros: Closes the largest entity-model gap while reusing the existing cross-report analysis implementation for Briefings.
  - Cons: Requires contract, publish, plugin, theme, and migration work if old cross-report outputs need backfill.
  - Acceptance Criteria:
    - Signal has an explicit publish contract or documented projection with a schema version.
    - Briefing WordPress surfaces map to the existing cross-report analysis/publish package contract instead of introducing a duplicate briefing generator.
    - WordPress registers canonical destinations for Signals and Briefings through CPTs, taxonomies, pages, or a documented alternative with tests.
    - Theme templates or block patterns render Signal and Briefing archive/detail surfaces.
    - Publish pipeline can populate those surfaces without empty/default term contracts.
    - README documents the final WordPress entity implementation and naming.

- **Title:** Route cross-report HTML publication into the Briefings section [Impact: 5/5, Effort: 3/5]
  - Explanation: Cross-report HTML is already generated through `src/generators/cross_report_publish_html.py` and routed through `python -m src.cli generate-cross-report-analysis` plus `publish_orchestrator.publish_cross_report_package`. The remaining gap is making that path explicitly publish the generated cross-report HTML as a WordPress post in the Briefings section, not as a Report/digest or an unclassified WordPress post.
  - Pros: Turns the implemented cross-report analysis capability into the public Briefing workflow without creating a second publication subsystem.
  - Cons: Requires a clear WordPress routing choice for the Briefings section and migration handling for previously published cross-report posts.
  - Acceptance Criteria:
    - A documented command or script path publishes cross-report HTML to WordPress, starting from `python -m src.cli generate-cross-report-analysis --publish-mode publish_live` or a thin script that calls the same orchestrator.
    - `publish_cross_report_package` maps the package to the Briefings section deterministically, including post type, slug/permalink route, category/term assignment, and any required metadata.
    - Cross-report publications do not land in the Reports archive or use report/digest labels unless README explicitly redefines the sectioning model.
    - Dry-run output shows the target Briefings route and the exact WordPress payload classification without making side effects.
    - Tests cover live payload construction, dry-run payload classification, idempotent republish, and readback/URL placement for a Briefing post.

- **Title:** Build the grounded Signal-post generation and WordPress publish flow [Impact: 5/5, Effort: 5/5]
  - Explanation: Signals are a canonical README entity, but current WordPress signal modules are render-time heuristics over WP posts/categories rather than durable, approved Signal posts. The required flow is to derive grounded Signal entities from approved Python projections and evidence references, generate publish-ready Signal HTML/metadata, and publish them through the existing WordPress service boundary.
  - Pros: Makes Signals reproducible, evidence-backed, and independently publishable instead of homepage-only UI fragments.
  - Cons: Requires new contracts, generator/orchestrator work, WordPress routing, and migration/removal of current heuristic signal modules.
  - Acceptance Criteria:
    - Signal contracts define schema version, title, slug, summary/body HTML, evidence IDs, source report IDs, topic/category IDs, confidence/uncertainty fields, and validation status.
    - Signal generation reads only approved projections/Data Points through existing service boundaries such as `analytics_store_service`, reusing cross-report signal scoring where appropriate without making Briefing-specific contracts the public Signal contract.
    - A Signal generator validates grounding by requiring cited projected evidence, source reports, and topic/category relationships before any publish package is created.
    - A Signal orchestrator or documented CLI/script path creates Signal publish packages and routes them through the canonical publish/WordPress boundary without adding a peer WordPress client.
    - WordPress publishes Signal posts into the Signals section with deterministic post type or taxonomy route, slug/permalink, category/topic assignment, metadata, and readback verification.
    - Dry-run output shows the exact Signal WordPress payload classification and target route without side effects.
    - Tests cover positive grounded Signal creation, insufficient-evidence failure, dry-run payload construction, live payload construction, idempotent republish, and WordPress readback/URL placement.

- **Title:** Stop WordPress from synthesizing intelligence, freshness, and authority claims at render time [Impact: 5/5, Effort: 3/5]
  - Explanation: README says WordPress must not synthesize new intelligence, freshness, or quality judgments and should assemble approved projections/artifacts. Current plugin code computes weekly signals, strategic themes, freshness windows, and publisher authority from live WordPress counts and dates in `class-marketlense-core-intelligence-stats.php`.
  - Pros: Keeps analytical claims owned by the Python pipeline and makes published site content reproducible from approved artifacts.
  - Cons: Existing home-page modules need replacement data contracts and fallback behavior when projections are absent.
  - Acceptance Criteria:
    - WordPress intelligence modules read approved projection/artifact data instead of deriving claims from live WP queries.
    - Any missing projection fails closed with neutral UI or typed/admin-visible diagnostics, not invented metrics.
    - Tests prove no signal, freshness, strategic-theme, or publisher-authority claim is generated solely from WordPress post counts.
    - README documents the projection source used by each WordPress intelligence module.

- **Title:** Make Signals, cross-report Briefings, Figures, Regions, and Time Periods durable public entities [Impact: 5/5, Effort: 5/5]
  - Explanation: The analytics projection layer persists reports, sections, findings, metrics, quotes, claims, tags, categories, figures, and vector queue state. Cross-report analysis already implements the Briefing-generation capability, but that output is not consistently exposed as a durable public Briefing entity with WordPress taxonomy/route/readback semantics. Signals are still not durable public projection entities. Figures exist in storage but lack a public WordPress destination, and Regions/Time Periods are stored mostly as metadata rather than complete public surfaces.
  - Pros: Gives the publishing layer one typed source of truth for every README entity and reduces UI-specific inference.
  - Cons: Broad schema, migration, and publish workflow changes.
  - Acceptance Criteria:
    - Projection contracts/tables exist for public Signals with schema versions and round-trip tests.
    - Existing cross-report analysis outputs are explicitly versioned and mapped to the public Briefing entity contract.
    - Figures, Regions, and Time Periods have documented public projection contracts or explicit README-scoped exclusions.
    - WordPress publish code can map each public projection entity to a stable route/template/surface.
    - Integration tests cover report-to-entity projection and WordPress publish/readback for each implemented entity.

- **Title:** Resolve publish post-type and entity naming drift between README, config, and WordPress [Impact: 4/5, Effort: 2/5]
  - Explanation: README says publishing currently targets core `posts`, while `src/config/app.yaml` sets `publish.wp.post_type` to `ml_report`. The WordPress plugin supports both core `post` and `ml_report` as report-like types, and public copy mixes Report, Digest, Brief, and Latest brief labels.
  - Pros: Removes ambiguity from the publish path and prevents operators from publishing to the wrong content type.
  - Cons: Requires a deliberate migration choice and updates to screenshots/copy/tests.
  - Acceptance Criteria:
    - README, YAML config, WordPress plugin behavior, and publish tests agree on the canonical report post type.
    - Compatibility behavior for old core `post` digests is explicitly documented or removed.
    - Public UI copy consistently uses Report for report entities and Briefing only for briefing entities.
    - Tests verify configured post type, WP payload post type, and resulting WordPress content type.

- **Title:** Make WordPress categories the canonical Topic surface with full topic semantics [Impact: 4/5, Effort: 3/5]
  - Explanation: The current implementation already uses WordPress categories as the public Topic path, populated from `category-mappings.yaml`. The remaining gap is that categories currently publish mostly as labels, while README defines Topics as controlled taxonomy entries with definition, inclusion, and exclusion rules.
  - Pros: Reuses the existing category-based Topic implementation while making taxonomy governance visible on the public site.
  - Cons: Requires term contract expansion and careful migration/update behavior for existing categories.
  - Acceptance Criteria:
    - README explicitly states that WordPress categories are the canonical public implementation of Topics, or config/docs are updated to name a different canonical taxonomy.
    - Topic/category contract includes definition, inclusion rules, exclusion rules, and version metadata where required.
    - WordPress category creation/update writes approved topic descriptions or term meta through the service boundary.
    - Topic directory and category archive templates render approved topic semantics without ad hoc copy.
    - Tests assert term semantics survive publish and readback.

- **Title:** Add secondary public surfaces for Figures, Regions, and Time Periods or narrow the README contract [Impact: 3/5, Effort: 3/5]
  - Explanation: README lists Figures, Regions, and Time Periods as secondary public surfaces. Current WordPress templates include reports, topics, publishers, methodology, and support pages, but no figure, region, or time-period destination.
  - Pros: Completes the documented browsing model and improves report discoverability by artifact, geography, and period.
  - Cons: More templates and projection/read-model work; some surfaces may be low value until there is enough content.
  - Acceptance Criteria:
    - Figures, Regions, and Time Periods each have a WordPress route/template/surface, or README explicitly removes/defers them with rationale.
    - Publish/projection code provides stable data for each implemented surface.
    - Empty-state behavior is deterministic and does not invent content.
    - Static or integration tests cover route existence and representative rendering.

- **Title:** Replace publisher authority heuristics with approved publisher projections [Impact: 4/5, Effort: 3/5]
  - Explanation: Publisher surfaces are partly implemented, but current WordPress code derives authority-style rankings and labels from local post/category counts. README positions Publisher as a canonical entity and forbids WordPress from creating quality judgments outside approved artifacts.
  - Pros: Keeps publisher claims auditable and avoids misleading authority language from incomplete WordPress data.
  - Cons: Requires a publisher projection or metric artifact and revised homepage/publisher modules.
  - Acceptance Criteria:
    - Publisher authority/coverage modules consume approved pipeline projections, not WP count heuristics.
    - Public labels avoid authority/ranking language unless backed by a documented metric contract.
    - Publisher term metadata and templates expose only approved fields.
    - Tests prove missing publisher projections do not produce inferred authority claims.

- **Title:** Bring WordPress design tokens and CSS organization back in line with README [Impact: 3/5, Effort: 2/5]
  - Explanation: README documents the theme `wideSize` as `82rem`, while `theme.json` currently uses `84rem`. The block theme also includes inline CSS in `parts/header.html`, and the main theme CSS has grown large with repeated hooks, making the WordPress design contract harder to audit.
  - Pros: Reduces design drift and keeps styling centralized and testable.
  - Cons: Visual regressions are possible without screenshot review.
  - Acceptance Criteria:
    - README and `theme.json` agree on `wideSize` and other documented layout tokens.
    - Inline header CSS is moved into the theme stylesheet or an approved block/style asset.
    - Repeated CSS hooks are consolidated without changing intended rendering.
    - WordPress static checks and at least one visual/screenshot review pass for desktop and mobile.
