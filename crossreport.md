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
