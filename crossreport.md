# Cross-Report Analysis Generation TODO

Last compiled: 2026-05-19

This file is the active implementation backlog for cross-report analysis generation and publication flow. It replaces the earlier broad roadmap in this file and intentionally mirrors the structure of `CONSOLIDATED_TODO.md`.

Scope: generate cross-report analysis artifacts from already-produced report projections and evidence packs, automatically choose publishable themes when requested, and route validated artifacts through the existing publication boundary. This phase does not normalize metrics, introduce a new deployable service, or build a global semantic search product.

Evidence used for this consolidation:

- `README.md` documents a mature single-report pipeline with contract-first services, generators, orchestrators, prompt namespaces, structured logs, typed errors, idempotency, and validation gates.
- `README.md` documents the analytics projection foundation: `report_sections`, `report_findings`, `report_metrics`, `report_quotes`, `report_claims`, `report_tags`, `report_categories`, `report_figures`, and `vector_projection_queue`.
- `README.md` states that `vector_projection_queue` stages future embedding work and does not implement global retrieval yet.
- `README.md` documents canonical boundaries that this feature should reuse: `src/services/analytics_store_service.py`, `src/services/prompt_service.py`, `src/services/llm_service.py`, `src/services/file_service.py`, `src/services/idempotency_service.py`, `src/generators/publish_generator.py`, `src/orchestrators/publish_orchestrator.py`, and existing config/publish/report orchestration patterns.
- `AGENTS.md` requires strict role separation, dataclass contracts, prompt text in prompt namespaces only, structured logs with `run_id`, `task_id`, `span_id`, `role`, `module`, typed `AppError` failures, orchestrator-owned retries, and no architectural drift.
- `CONSOLIDATED_TODO.md` requires backlog items to stay concise, measurable, and ordered by impact, effort, quality, speed, and cost.

How to use this backlog:

- Treat this file as the only active plan for cross-report analysis generation, theme choice, and publication flow.
- Keep the first release small: deterministic projected-data retrieval, automatic theme choice inside the input-builder generator, one synthesis generator, one orchestrator, one CLI entrypoint, existing publication boundaries, and strong tests.
- Remove items once their acceptance criteria are fully met.
- Every implementation PR must update `README.md` when it changes code behavior, architecture, settings, commands, outputs, or setup.
- No metric normalization is allowed in this phase. Raw metric values may be cited only with original value, unit, report, evidence id, and source context.

Scoring rubric:

- `Impact`: `1` low leverage, `5` highest leverage across analysis quality, reliability, speed, cost, or architecture.
- `Effort`: `1` localized change, `5` broad refactor or cross-module coordination.

Suggested priority order:

1. `1. Architecture, Contracts & Scope Fence`
2. `2. Projection-Backed Source Selection`
3. `3. Automatic Theme Choice, Variety & Publishability`
4. `4. Evidence, Signals & Raw Metrics Handling`
5. `5. Prompt Namespace & Analysis Generator`
6. `6. Orchestration, Persistence & CLI`
7. `7. Publication Flow`
8. `8. Quality, Speed, Cost & Documentation`

---

## 1. Architecture, Contracts & Scope Fence

- **Title:** Lock cross-report analysis into the existing modular monolith [Impact: 5/5, Effort: 1/5]
  - Explanation: Cross-report analysis should be a bounded extension of the current analysis/projection/publishing system, not a separate service, worker, package, or parallel publishing subsystem. The implementation should reuse existing canonical boundaries and add only the smallest set of new role-specific modules needed to generate and publish validated artifacts.
  - Pros: Fast delivery, low operational burden, simpler testing, no duplicated external-system boundary.
  - Cons: First release depends on the quality and coverage of existing projected rows.
  - Acceptance Criteria:
    - Implementation plan names the exact contracts, service methods, generators, orchestrator, prompt namespace, CLI command, and tests before code changes start.
    - No new top-level `src/` package, standalone worker, deployable component, or second analytics database boundary is introduced.
    - SQLite access for projected report data stays behind `analytics_store_service` or its same-boundary internals.
    - Prompt loading stays behind `prompt_service`; model calls stay behind `llm_service`; artifact writes stay behind `file_service`.
    - Non-goals are documented in `README.md`: no metric normalization, no new WordPress plugin/post-type dependency, no global vector retrieval product in this release.

- **Title:** Add versioned cross-report analysis contracts [Impact: 5/5, Effort: 2/5]
  - Explanation: The feature needs explicit dataclass contracts before generators or orchestrators exist. Contracts should describe the request, theme candidates, selected theme, selected report set, evidence references, signal scores, raw metric references, generated analysis artifact, validation result, persisted artifact metadata, and publish outcome.
  - Pros: Clear boundaries, schema evolution discipline, easier test assertions, less room for ad-hoc dicts.
  - Cons: Requires careful field documentation and round-trip coverage before business logic can land.
  - Acceptance Criteria:
    - `src/contracts/cross_report_analysis.py` defines versioned dataclasses with documented fields and explicit types.
    - Required contract family includes request, theme candidate, selected theme, source report candidate, selected source report, evidence reference, signal score, raw metric reference, analysis section, generated analysis result, validation result, publish request summary, publish result summary, and orchestrator outcome.
    - Serialization round-trip tests cover every contract and fail on missing required fields.
    - Negative-path tests assert `AppError.code`, `retryable`, and `severity` for invalid contract input.

- **Title:** Add minimal YAML configuration for bounded generation [Impact: 4/5, Effort: 2/5]
  - Explanation: Quality, speed, and cost controls should be explicit from the start. The first release needs limits for source report count, evidence count, prompt input size, model parameters, cache eligibility, theme choice, publish readiness, and validation strictness.
  - Pros: Prevents runaway prompts, keeps costs predictable, makes tradeoffs visible.
  - Cons: Adds config surface that must be documented and tested.
  - Acceptance Criteria:
    - `src/config/app.yaml` gains a compact `cross_report_analysis` section.
    - Settings include `enabled`, `max_source_reports`, `max_evidence_items`, `max_prompt_chars`, `prompt_namespace`, `model`, `temperature`, `timeout_seconds`, `cache_enabled`, `auto_theme_enabled`, `theme_rotation_window_days`, `min_theme_source_publishers`, `publish_enabled`, and `publish_requires_validation_pass`.
    - Config loading validates invalid limits with typed non-retryable `AppError`.
    - README documents defaults, CLI overrides, and cost-control behavior.

---

## 2. Projection-Backed Source Selection

- **Title:** Add projected-data read methods to the canonical analytics store boundary [Impact: 5/5, Effort: 3/5]
  - Explanation: The existing analytics projection tables are the fastest low-cost foundation for cross-report analysis. The feature should query those tables directly through the existing analytics store boundary rather than building a new search service.
  - Pros: Reuses landed storage, avoids new infrastructure, keeps retrieval deterministic and cheap.
  - Cons: Retrieval quality is limited to projected fields until a later semantic retrieval phase exists.
  - Acceptance Criteria:
    - `analytics_store_service` exposes typed read methods for report inventory, projected claims/findings/quotes/metrics/tags/categories, and content hashes.
    - Methods return dataclass contracts, not raw SQLite rows.
    - Read methods support filters for publisher, report date range, category, tag, content class, and minimum projection status.
    - Integration tests use a local SQLite fixture and assert returned contracts plus required structured log fields.
    - No caller imports private analytics-store internals.

- **Title:** Build deterministic candidate report selection [Impact: 5/5, Effort: 2/5]
  - Explanation: Cross-report generation needs a small, explainable source set before any LLM call. Selection should prefer reports with projected findings/claims, relevant tags/categories, source diversity, recency, and enough evidence density.
  - Pros: Reduces prompt size, improves synthesis relevance, lowers model spend.
  - Cons: Deterministic selection can miss subtle semantic matches before vector retrieval exists.
  - Acceptance Criteria:
    - `src/generators/cross_report_analysis_input_generator.py` accepts typed context and projected inventory contracts.
    - The generator returns a ranked selected-source contract with selection reasons and rejected-candidate reasons.
    - Ranking is deterministic for fixed inputs and config.
    - Unit tests assert source diversity, max report cap, date/category/tag filters, and stable ordering.
    - Logs include input context, cleaned request filters, ranking decisions, and final selected report IDs.

- **Title:** Enforce projection readiness before synthesis [Impact: 4/5, Effort: 2/5]
  - Explanation: Synthesis should not silently operate on weak or missing projected data. Reports with failed or absent projection can be excluded, and an empty eligible set should fail explicitly.
  - Pros: Prevents low-quality output and hidden data gaps.
  - Cons: Some reports become unavailable for cross-report analysis until their projection issue is fixed.
  - Acceptance Criteria:
    - Selection requires `projection_status='projected'` unless the request explicitly enables a documented diagnostic mode.
    - Empty eligible source sets raise a typed non-retryable `AppError`.
    - Tests cover all-projected, partially projected, failed-projection, and empty-result cases.
    - Logs show excluded report counts grouped by reason.

---

## 3. Automatic Theme Choice, Variety & Publishability

- **Title:** Add deterministic automatic theme candidate generation [Impact: 5/5, Effort: 3/5]
  - Explanation: Operators should be able to request a cross-report analysis without hand-picking the exact theme. The first release should build theme candidates from projected categories, tags, findings, claims, contradictions, recency, and source coverage without requiring an extra model call.
  - Pros: Faster publishing cadence, lower editorial effort, lower model cost than LLM-led clustering.
  - Cons: Theme quality depends on projection and taxonomy quality until semantic retrieval exists.
  - Acceptance Criteria:
    - `src/generators/cross_report_analysis_input_generator.py` creates theme candidates when the request has `auto_theme=true` or no explicit topic.
    - Each theme candidate includes label, short rationale, matched tags/categories, source report ids, source publisher count, evidence count, recency signals, and rejection risks.
    - Candidate generation is deterministic for fixed projected rows and config.
    - Tests cover explicit topic mode, auto-theme mode, no eligible theme, and stable ranking.
    - Logs include candidate count, selected theme id, score components, and rejection reasons.

- **Title:** Enforce theme variety and anti-repetition policy [Impact: 4/5, Effort: 2/5]
  - Explanation: Automatic choice should not repeatedly select the same publisher, category, or narrow angle just because it has dense projections. Variety here means useful editorial rotation and source diversity, not metric normalization or clickbait scoring.
  - Pros: Better content mix, more resilient editorial calendar, less duplicated output.
  - Cons: A strict rotation policy can skip a high-quality recurring theme when the corpus is small.
  - Acceptance Criteria:
    - Theme scoring includes configurable source diversity, category diversity, recency, novelty against recent generated artifacts, and evidence density components.
    - Recent generated artifact metadata is read through the existing file/persistence service boundary, not directly from a generator.
    - Selection can reject or down-rank a theme when it repeats the same theme/category/publisher pattern inside `theme_rotation_window_days`.
    - Tests prove repeated-theme down-ranking, source-diversity preference, and deterministic tie-breaking.
    - Logs explain why the selected theme was chosen over higher-density but repetitive alternatives.

- **Title:** Add publishability gate before synthesis and publication [Impact: 5/5, Effort: 2/5]
  - Explanation: The selected theme should be strong enough to generate and publish. The gate should reject thin, duplicate, unsupported, or unsafe themes before spending on synthesis or attempting publication.
  - Pros: Saves cost, improves quality, prevents weak published cross reports.
  - Cons: Some valid niche themes may require operator override when the corpus is intentionally narrow.
  - Acceptance Criteria:
    - Publishability gate checks minimum source reports, minimum source publishers, minimum evidence items, no metric-normalization dependency, duplicate-theme risk, and validation prerequisites.
    - Failed publishability raises typed non-retryable `AppError` before model calls unless the request is explicitly `diagnostic`.
    - Operator override is allowed only through an explicit request flag and is logged with reason, run id, task id, and selected theme id.
    - Tests cover pass, thin coverage, duplicate theme, single-publisher-only, and override paths.
    - README documents theme auto-choice, variety policy, and publishability failure modes.

---

## 4. Evidence, Signals & Raw Metrics Handling

- **Title:** Assemble evidence-bearing analysis inputs from projected rows [Impact: 5/5, Effort: 3/5]
  - Explanation: The synthesis prompt should receive compact evidence objects, not full reports. Evidence should include claims, findings, quotes, tags/categories, selected figures when available, and raw metrics only as source-bound facts.
  - Pros: Smaller prompts, better grounding, clearer provenance, lower cost.
  - Cons: Requires strict referential integrity checks between generated claims and evidence ids.
  - Acceptance Criteria:
    - `src/generators/cross_report_analysis_input_generator.py` builds a bounded evidence set from selected reports.
    - Every evidence item includes report id, publisher/title when available, source table/entity uid, content class, text payload, and source metadata.
    - Raw metrics preserve original value/unit/context and are marked `raw_metric_reference`, not comparable normalized measures.
    - Evidence selection caps are enforced before prompt rendering.
    - Tests assert evidence completeness, cap behavior, duplicate suppression, and raw metric provenance.

- **Title:** Add lightweight signal scoring without metric normalization [Impact: 5/5, Effort: 3/5]
  - Explanation: Cross-report analysis needs a ranking signal, but it should not compare numeric metrics across publishers. The first scorer should use recurrence, source diversity, recency, category/tag fit, quote/finding support, and contradiction presence.
  - Pros: Better analysis focus without expensive or risky data harmonization.
  - Cons: Signal quality depends on projected text and taxonomy quality.
  - Acceptance Criteria:
    - `src/generators/cross_report_analysis_input_generator.py` produces documented signal-score contracts with component scores and reasons.
    - Score components are deterministic and configured by YAML weights.
    - Numeric metric magnitude is never used as a cross-source comparable score.
    - Tests prove that changing only a raw metric unit/value does not create normalized ranking behavior.
    - Logs include scored signal components and selected top signals.

- **Title:** Preserve disagreement and uncertainty as first-class output inputs [Impact: 4/5, Effort: 2/5]
  - Explanation: Cross-report analysis should not force consensus when projected claims conflict or when source coverage is thin. The input layer should label convergent, divergent, and under-supported evidence groups before synthesis.
  - Pros: More trustworthy analysis, fewer hallucinated conclusions, better editorial review.
  - Cons: Adds a small deterministic grouping step before synthesis.
  - Acceptance Criteria:
    - Evidence groups carry `agreement_type` values such as `convergent`, `divergent`, and `thin_coverage`.
    - Grouping logic is deterministic and based on source/evidence text, tags, categories, and contradiction pack rows when available.
    - Tests include at least one convergence case, one divergence case, and one thin-coverage case.
    - Generated prompt inputs expose uncertainty labels without asking the model to infer missing provenance.

---

## 5. Prompt Namespace & Analysis Generator

- **Title:** Create a dedicated cross-report analysis prompt namespace [Impact: 5/5, Effort: 2/5]
  - Explanation: AGENTS.md forbids inline prompt text and centralized prompts. Cross-report synthesis needs its own namespace with fixture-backed rendering before runtime use.
  - Pros: Reproducible prompts, CI dry-run coverage, clean prompt evolution.
  - Cons: Adds prompt fixture maintenance.
  - Acceptance Criteria:
    - Prompt files live under `src/prompts/cross_report_analysis/synthesis/`.
    - Prompt inputs are fully structured and do not include unbounded full-report text.
    - `_dry_run_fixtures.yaml` includes a cross-report synthesis fixture with realistic evidence, raw metrics, and disagreement labels.
    - Prompt hashes, rendered prompt text, model parameters, and request metadata are logged for every generation call.
    - Prompt fixture regression is updated only with documented expected token/cost impact.

- **Title:** Implement the cross-report analysis synthesis generator [Impact: 5/5, Effort: 4/5]
  - Explanation: The generator is the domain layer that turns selected sources, evidence groups, and signal scores into a structured cross-report analysis artifact. It should make one bounded LLM call by default and fail closed when evidence mapping is incomplete.
  - Pros: Delivers the core feature with controlled cost and traceable claims.
  - Cons: Requires strict validation around model output shape and citations.
  - Acceptance Criteria:
    - `src/generators/cross_report_analysis_generator.py` accepts typed context and calls `prompt_service` plus `llm_service` only through service boundaries.
    - Output includes title, executive summary, key cross-report signals, convergences, divergences, source notes, raw metric appendix, and evidence map.
    - Every generated claim references at least one selected evidence id.
    - Missing, unknown, or default-filled required fields raise typed non-retryable `AppError`.
    - Unit tests mock only service boundaries and assert contract completeness, evidence mapping, prompt namespace/hash logging, and negative-path error taxonomy.

- **Title:** Add deterministic artifact validation before persistence [Impact: 5/5, Effort: 2/5]
  - Explanation: The first release should prefer deterministic validation over additional model calls to protect cost and speed. Validation should check schema shape, evidence references, raw metric handling, prompt budget metadata, and required logs.
  - Pros: Fast, cheap, reliable guardrail before generated analysis is saved.
  - Cons: Does not fully judge editorial quality; fixture regression covers that separately.
  - Acceptance Criteria:
    - `src/generators/cross_report_analysis_generator.py` validates the generated artifact without external I/O before returning the final contract.
    - Validation rejects claims without known evidence ids.
    - Validation rejects metric language that implies normalized comparability unless explicitly framed as raw source-specific data.
    - Tests cover valid output, missing evidence, unknown evidence id, empty required sections, and forbidden metric-normalization language.
    - Validation results are logged with structured pass/fail reasons.

---

## 6. Orchestration, Persistence & CLI

- **Title:** Add an idempotent cross-report analysis orchestrator [Impact: 5/5, Effort: 3/5]
  - Explanation: The orchestrator should own sequencing, retries, state transitions, and idempotency. It should route through selection, evidence assembly, signal scoring, synthesis, validation, and persistence without embedding domain logic.
  - Pros: Reliable reruns, clear failure states, no generator-level retry drift.
  - Cons: Adds a new critical orchestrator that must be covered by pipeline tests.
  - Acceptance Criteria:
    - `src/orchestrators/cross_report_analysis_orchestrator.py` coordinates the workflow and owns retry/backoff decisions for retryable service errors.
    - Idempotency key includes request filters, selected report ids, projection content hashes, prompt hashes, config version, and schema version.
    - Duplicate runs with unchanged inputs reuse the persisted outcome instead of making another model call.
    - Pipeline tests assert stage order, retry counts, state transitions, idempotency reuse, and required structured log fields.
    - Retryable errors from services are propagated to the orchestrator and never swallowed by generators.

- **Title:** Persist generated cross-report analysis artifacts atomically [Impact: 4/5, Effort: 2/5]
  - Explanation: The feature needs a stable local artifact before live publication. Persistence should use existing atomic file service behavior and include enough metadata for replay.
  - Pros: Easy review, reproducibility, cheap local workflow, safe dry-run path before live publish.
  - Cons: Operators initially consume local artifacts or CLI output rather than a rich UI.
  - Acceptance Criteria:
    - Orchestrator writes `analysis.json` under `out/cross_report_analysis/<analysis_slug>/` through `file_service`.
    - Artifact metadata includes schema version, request fingerprint, selected report ids, projection content hashes, prompt hashes, config fingerprint, generated timestamp, and validation status.
    - Repeated identical runs produce the same artifact path and no duplicate side effects.
    - Tests assert persisted JSON schema validity and deterministic path behavior.

- **Title:** Add a focused CLI command for generation [Impact: 4/5, Effort: 2/5]
  - Explanation: A CLI entrypoint is the fastest operator path and avoids UI complexity until the generation contract is stable.
  - Pros: Quick delivery, simple automation, easier testability.
  - Cons: Less convenient than Streamlit for editorial review in the first release.
  - Acceptance Criteria:
    - `python -m src.cli generate-cross-report-analysis` accepts topic text, `--auto-theme`, category/tag filters, publisher filters, date range, max report count, publish mode, and output root override.
    - CLI prints the artifact path, selected report count, validation status, and cost summary when available.
    - CLI fails explicitly with typed error output for empty source sets, invalid filters, budget cap breach, and validation failure.
    - CLI tests cover successful generation with mocked service boundaries and negative-path argument validation.
    - README documents command examples and expected output layout.

---

## 7. Publication Flow

- **Title:** Add a validated cross-report publish package [Impact: 5/5, Effort: 3/5]
  - Explanation: Publication should be a narrow follow-on from a validated generated artifact. The publish package should adapt the cross-report analysis result into existing publish inputs without introducing a second WordPress service or a new plugin requirement.
  - Pros: Uses current publication reliability, keeps implementation small, preserves existing idempotency and WordPress configuration.
  - Cons: First release may use the existing post/card surface rather than a custom cross-report UX.
  - Acceptance Criteria:
    - `src/generators/cross_report_analysis_generator.py` emits a publish package with publish-ready title, slug, excerpt, HTML body, source metadata, category/tag metadata, and canonical artifact reference.
    - Publication is allowed only when deterministic validation passes and `publish_requires_validation_pass=true`.
    - Generated HTML includes source report map, evidence references, raw metric appendix, uncertainty/divergence notes, and machine-readable cross-report metadata.
    - Tests assert publish package completeness, source/evidence trace presence, validation gating, and no metric-normalization language.
    - No new WordPress service boundary is introduced.

- **Title:** Route publication through the existing publish orchestrator boundary [Impact: 5/5, Effort: 3/5]
  - Explanation: Publishing is an external side effect, so the cross-report flow should delegate to existing publish orchestration and WordPress service boundaries. The cross-report orchestrator owns when publication is requested; the publish stack owns how WordPress is called.
  - Pros: Avoids duplicated retry/idempotency behavior, keeps external I/O consolidated, lowers implementation risk.
  - Cons: Requires careful adaptation if current publish contracts assume single-report metadata.
  - Acceptance Criteria:
    - Cross-report publication calls the existing publish pathway with typed cross-report metadata instead of creating a peer WordPress client.
    - Publish idempotency key includes selected theme id, selected report ids, artifact hash, validation hash, prompt hashes, and target publish route.
    - Re-running a publish with unchanged inputs updates/reuses the same canonical post rather than creating duplicates.
    - Pipeline tests assert generate-only, validate-only, publish-dry-run, successful publish, duplicate publish reuse, and publish failure paths.
    - Retryable publish errors propagate to the orchestrator retry policy and are logged with retry decisions.

- **Title:** Add publication modes and operator safeguards [Impact: 4/5, Effort: 2/5]
  - Explanation: Operators need a fast safe path for generation, review, and publication. Publication should be opt-in and should support dry-run before live WordPress side effects.
  - Pros: Safer rollout, clearer operator control, fewer accidental posts.
  - Cons: Adds a small amount of CLI/config branching.
  - Acceptance Criteria:
    - Supported modes are `generate_only`, `validate_only`, `publish_dry_run`, and `publish_live`.
    - `publish_live` requires `cross_report_analysis.publish_enabled=true` and a passed validation result.
    - CLI output reports selected theme, publication mode, artifact path, target route, post id/url when available, and idempotency reuse status.
    - Structured logs include publication mode, publish decision, target route, validation status, and final publish result.
    - README documents safe rollout from dry-run to live publication.

---

## 8. Quality, Speed, Cost & Documentation

- **Title:** Add cross-report fixture regression and anti-cheat tests [Impact: 5/5, Effort: 3/5]
  - Explanation: Cross-report generation is easy to fake with over-mocked tests. The test suite must prove real selection, evidence assembly, validation, idempotency, and log behavior.
  - Pros: Higher confidence, protects against empty/default artifacts, aligns with AGENTS.md.
  - Cons: Requires careful fixtures and mutation-aware assertions.
  - Acceptance Criteria:
    - Contract round-trip tests cover all new dataclasses.
    - Analytics-store integration tests cover projected-data reads against SQLite fixtures.
    - Generator tests assert output semantics and fail if core selection/evidence/validation logic is replaced with empty defaults.
    - Orchestrator pipeline tests assert retry counts, state transitions, idempotency keys, and required logs.
    - Forbidden patching rules are respected: tests mock only service boundaries or true external boundaries.

- **Title:** Add cache and budget gates for cross-report generation [Impact: 5/5, Effort: 2/5]
  - Explanation: Speed and cost efficiency depend on avoiding repeated LLM calls when inputs have not changed and preventing oversized prompt construction before it happens.
  - Pros: Lower spend, faster reruns, fewer timeout risks.
  - Cons: Cache keys must include all behavior-changing inputs to avoid stale reuse.
  - Acceptance Criteria:
    - Cache eligibility is based on selected report ids, projection content hashes, prompt hashes, model parameters, config fingerprint, and schema version.
    - Prompt input construction stops before model calls when evidence or character limits are exceeded.
    - Budget-cap breaches raise typed non-retryable `AppError` with clear operator context.
    - Tests prove unchanged reruns skip the model call and changed projection content invalidates the cache.

- **Title:** Document the feature in README and operational notes [Impact: 4/5, Effort: 1/5]
  - Explanation: AGENTS.md requires meaningful architecture, settings, setup, and behavior changes to be documented. Operators need to know what the feature does and what it intentionally does not do.
  - Pros: Easier handoff, fewer misuse cases, clearer metric-normalization boundary.
  - Cons: Documentation must stay updated with implementation changes.
  - Acceptance Criteria:
    - README documents cross-report analysis scope, architecture, automatic theme choice, variety policy, publication modes, CLI usage, config keys, artifact layout, logs, cost controls, and failure modes.
    - README explicitly states that metric normalization, new WordPress plugin/post-type requirements, and global semantic retrieval are out of scope for the first release.
    - Documentation links the feature to the existing analytics projection foundation.
    - Troubleshooting notes include empty eligible report sets, projection failures, prompt budget caps, validation failures, and idempotency reuse.

---

## Explicit Non-Goals For This Phase

1. Metric normalization, unit conversion, or statistical harmonization across publishers.
2. Ranking evidence by normalized metric magnitude.
3. New WordPress plugin requirements, new post-type requirements, or portal UX changes.
4. A new deployable worker, microservice, package, external search service, or peer WordPress service.
5. Global semantic/vector retrieval over `vector_projection_queue`.
6. Heavy Streamlit curation workflows before CLI generation and publish dry-run are stable.

---

## Priority Launch Plan

### Phase 1: Minimal Shippable Analysis Generation

- Contracts and config for bounded cross-report generation.
- Analytics-store read methods for projected report data.
- Deterministic report selection, automatic theme choice, variety policy, and projection readiness gate.
- Evidence assembly, signal scoring, prompt namespace, synthesis generator, deterministic validation.
- Idempotent orchestrator and CLI command that writes `analysis.json` and supports `publish_dry_run`.

### Phase 2: Publication Flow, Quality, Speed, and Cost Hardening

- Validated publish package and reuse of the existing publish orchestrator boundary.
- Publication modes from `generate_only` through `publish_live`, guarded by config and validation.
- Fixture regression corpus for representative cross-report topics.
- Cache reuse keyed by projection content hashes, prompt hashes, config, model params, and schema version.
- Budget gates for max reports, evidence items, prompt chars, model calls, and timeout behavior.
- README and troubleshooting docs.

### Phase 3: Operator Polish After Artifact Stability

- Read-only Streamlit review surface for generated artifacts and evidence maps.
- Optional export/rendering convenience for editorial review.
- A separate architecture review before adding custom WordPress plugin/post-type work, semantic retrieval, or any new deployable boundary.
