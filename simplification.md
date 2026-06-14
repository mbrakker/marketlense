# Simplification Backlog

Last audited: 2026-06-14

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

- OpenAI/LLM/vector-store ownership remains the highest-leverage unresolved boundary decision.
- Model-client construction still occurs in multiple generators and requires an effort-4 dependency migration.
- Large orchestrators, publish workflow surfaces, PDF facade exports, and WordPress render-time intelligence remain broad behavior-preserving refactors.
- Contract fragmentation remains an architecture-level bounded-context review.

## Priority Order

1. Canonical service-boundary simplification.
2. Generator and orchestrator role-boundary cleanup.
3. Low-risk helper reuse and duplicate removal.
4. PDF/visual heuristics compatibility-surface reduction.
5. WordPress and CI/process simplification.

## 2026-06-14 Verification Evidence

- Affected regression suite: `241 passed`.
- Full functional suite: `3103 passed, 23 deselected`; the pre-existing long-test ownership gate remains excluded because two untouched test modules exceed 1,000 lines.
- Coverage: 83.09% global, 84.85% orchestrators, 87.27% generators, and 82.38% services.
- Mutation gate passed; changed `report_render_generator.py` and `publish_generator.py` targets each killed all four sampled mutants.
- Existing HTML cache loaded through the typed cache service; template-bundle hashing was deterministic.
- Existing 18,900,061-byte generated image was prepared as a 298,814-byte upload payload, a 98.4% reduction.
- Real PDF candidate extraction processed an existing 1,159,172-byte PDF, produced three candidates with zero degraded pages, and produced byte-identical JSON on consecutive warm runs.
- WordPress provisioning ran successfully against the configured site; canonical and compatibility CLI dry runs then passed after argument-forwarding and import-path regressions were fixed.
- Investigation-only items were closed with retained-path evidence in `docs/quality/simplification-audit-2026-06-14.md`.
- The quality-regression gate's code coverage, mutation, and candidate metrics passed. Its unrelated docpack schema check remains red because existing golden artifacts predate required `cover_semantics` and `card_tldr_compact` fields; those fixtures and schemas were not changed or synthesized.

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

## Near-Term Launch Plan

### Phase 1: Boundary Corrections

- Consolidate OpenAI/LLM/vector-store service ownership.
- Centralize model-client construction outside generators.

### Phase 2: Larger Workflow Simplification

- Consolidate publish orchestration surfaces.
- Clarify report pipeline entrypoints.
- Reduce PDF visual heuristics compatibility exports.
- Simplify WordPress shortcode surfaces.

## Closed or Removed From Simplification Intake

- Implemented items are removed from this file after verification and closure in the consolidated backlog.
