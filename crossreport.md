# Cross-Report Analysis Generation Plan

Last compiled: 2026-05-19

This file is the implementation planning note for cross-report analysis generation and publication flow. It replaces the earlier broad roadmap in this file and intentionally mirrors the structure of `CONSOLIDATED_TODO.md`.

Scope: generate cross-report analysis artifacts from already-produced report projections and evidence packs, automatically choose publishable themes when requested, and route validated artifacts through the existing publication boundary. This phase does not normalize metrics, introduce a new deployable service, or build a global semantic search product.

Evidence used for this consolidation:

- `README.md` documents a mature single-report pipeline with contract-first services, generators, orchestrators, prompt namespaces, structured logs, typed errors, idempotency, and validation gates.
- `README.md` documents the analytics projection foundation: `report_sections`, `report_findings`, `report_metrics`, `report_quotes`, `report_claims`, `report_tags`, `report_categories`, `report_figures`, and `vector_projection_queue`.
- `README.md` states that `vector_projection_queue` stages future embedding work and does not implement global retrieval yet.
- `README.md` documents canonical boundaries that this feature should reuse: `src/services/analytics_store_service.py`, `src/services/prompt_service.py`, `src/services/llm_service.py`, `src/services/file_service.py`, `src/services/idempotency_service.py`, `src/generators/publish_generator.py`, `src/orchestrators/publish_orchestrator.py`, and existing config/publish/report orchestration patterns.
- `AGENTS.md` requires strict role separation, dataclass contracts, prompt text in prompt namespaces only, structured logs with `run_id`, `task_id`, `span_id`, `role`, `module`, typed `AppError` failures, orchestrator-owned retries, and no architectural drift.
- `CONSOLIDATED_TODO.md` requires backlog items to stay concise, measurable, and ordered by impact, effort, quality, speed, and cost.

How to use this planning note:

- Use this file as a scoped planning note for cross-report analysis generation, theme choice, and publication flow.
- Keep the first release small: deterministic projected-data retrieval, automatic theme choice inside the input-builder generator, one synthesis generator, one orchestrator, one CLI entrypoint, existing publication boundaries, and strong tests.
- Update or remove sections after implementation lands.
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
6. `7. Publication Flow`
7. `8. Quality, Speed, Cost & Documentation`

---

## 1. Architecture, Contracts & Scope Fence

---

## 2. Projection-Backed Source Selection

---

## 3. Automatic Theme Choice, Variety & Publishability

---

## 4. Evidence, Signals & Raw Metrics Handling

---

## 5. Prompt Namespace & Analysis Generator

---

## 7. Publication Flow

---

## 8. Quality, Speed, Cost & Documentation

- **Item:** Add cross-report fixture regression and anti-cheat tests [Impact: 5/5, Effort: 3/5]
  - Explanation: Cross-report generation is easy to fake with over-mocked tests. The test suite must prove real selection, evidence assembly, validation, idempotency, and log behavior.
  - Pros: Higher confidence, protects against empty/default artifacts, aligns with AGENTS.md.
  - Cons: Requires careful fixtures and mutation-aware assertions.
  - Completion criteria:
    - Contract round-trip tests cover all new dataclasses.
    - Analytics-store integration tests cover projected-data reads against SQLite fixtures.
    - Generator tests assert output semantics and fail if core selection/evidence/validation logic is replaced with empty defaults.
    - Orchestrator pipeline tests assert retry counts, state transitions, idempotency keys, and required logs.
    - Forbidden patching rules are respected: tests mock only service boundaries or true external boundaries.

- **Item:** Add cache and budget gates for cross-report generation [Impact: 5/5, Effort: 2/5]
  - Explanation: Speed and cost efficiency depend on avoiding repeated LLM calls when inputs have not changed and preventing oversized prompt construction before it happens.
  - Pros: Lower spend, faster reruns, fewer timeout risks.
  - Cons: Cache keys must include all behavior-changing inputs to avoid stale reuse.
  - Completion criteria:
    - Cache eligibility is based on selected report ids, projection content hashes, prompt hashes, model parameters, config fingerprint, and schema version.
    - Prompt input construction stops before model calls when evidence or character limits are exceeded.
    - Budget-cap breaches raise typed non-retryable `AppError` with clear operator context.
    - Tests prove unchanged reruns skip the model call and changed projection content invalidates the cache.

- **Item:** Document the feature in README and operational notes [Impact: 4/5, Effort: 1/5]
  - Explanation: AGENTS.md requires meaningful architecture, settings, setup, and behavior changes to be documented. Operators need to know what the feature does and what it intentionally does not do.
  - Pros: Easier handoff, fewer misuse cases, clearer metric-normalization boundary.
  - Cons: Documentation must stay updated with implementation changes.
  - Completion criteria:
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

## Launch Sequence

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
