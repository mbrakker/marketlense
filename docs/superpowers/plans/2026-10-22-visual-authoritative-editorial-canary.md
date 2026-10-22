# Visual-Authoritative Editorial Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit, shadow-only visual-authority canary at the existing candidate-to-final editorial boundary, while preserving the default artifact workflow and fail-closed evidence protections.

**Architecture:** Reuse `evaluate_shortlisted_claims()` and the existing artifact evidence/span validators through a small generator-side admission adapter. `generate_artifacts()` receives an optional callback only in canary mode; admitted candidates become the sole factual pool for final insights and downstream families. The authority digest participates in family cache inputs, and the private admission record is carried through the existing `_cache` metadata for regeneration. No canonical verified-claim persistence or publication path is changed.

**Tech Stack:** Python, existing dataclass contracts, pytest, `sha256_json`, artifact normalization, visual verified-claims generator, regeneration generator.

## Global Constraints

- Keep the default `generate_artifacts()` and `run_report_analysis()` behavior unchanged when canary configuration is absent.
- Admit only terminal visual outcomes `verified` and `verified_after_retry` with exact source identity and valid physical/evidence bindings.
- Never promote materially changed claims with `corrected_source_binding_status="unbound"` or invent evidence IDs, pages, spans, or metric fields.
- Reuse `bind_artifact_evidence_spans()`, `artifact_evidence_span_index()`, `select_artifact_insights()`, and existing lineage validators.
- Keep the visual evaluator shadow-only; do not mutate canonical claims, publication state, WordPress, or Step 3 artifacts.
- Add focused tests before production changes and run the smallest affected suites after each task.

## Task 1: Build the admission adapter and its regressions

**Files:** `src/generators/verified_claims_canary.py`, `tests/test_verified_claims_visual_authority_canary.py`

- [x] Add regressions for unchanged verified admission, independently bound corrected admission, unbound correction quarantine, wrong source hash/identity, wrong page/span, duplicate stable IDs, non-terminal outcomes, and preservation of candidate protected fields.
- [x] Add a small typed internal admission result containing admitted candidates, digest, and redacted audit counts/reasons; keep it outside persisted/public contracts.
- [x] Validate response shape and `shadow_mode`; map results by stable candidate ID without allowing duplicate/conflicting candidates to resolve by score.
- [x] Validate source identity/hash presence and exact match, physical page consistency, canonical evidence IDs/spans, and complete corrected metric binding before admitting a material rewrite.
- [x] Preserve candidate wording for unchanged claims and replace protected fields only from a complete, independently bound corrected result.
- [x] Run the new tests and the existing visual and artifact evidence-binding suites.

## Task 2: Connect admission to artifact generation and cache identity

**Files:** `src/generators/_artifact_generator/generation.py`, `src/orchestrators/report_analysis_orchestrator.py`, `tests/test_verified_claims_visual_authority_canary.py`

- [x] Add an optional injected admission callback to `generate_artifacts()` and an explicit canary configuration seam to `run_report_analysis()`.
- [x] Apply admission immediately after the existing candidate selector and before final insight rendering; fail closed if canary mode produces no eligible candidate pool.
- [x] Pass the admitted pool to final insight selection and all downstream families so metric spine, key figures, expert commentary, and social output share the same facts.
- [x] Skip the overall artifact-cache read when admission must be evaluated, and include the resulting digest in affected family variables and private cache metadata.
- [x] Add tests showing default mode is unchanged, canary mode cannot reuse stale overall artifacts, family identity changes with the digest, and downstream variables use admitted facts.

## Task 3: Preserve authority through regeneration

**Files:** `src/generators/report_regeneration_generator.py`, `tests/test_verified_claims_visual_authority_canary.py`

- [x] Add scoped-regeneration regressions with private canary metadata in `_cache`, including a model attempt that introduces an unadmitted candidate.
- [x] Carry the admitted candidate pool/digest through the existing regeneration state without changing `ArtifactRegenerationRequest`.
- [x] Restrict regenerated candidate/final insight pools to admitted stable IDs and authoritative protected fields; fail closed rather than reintroducing source-order fallback candidates.
- [x] Preserve existing regeneration behavior when canary metadata is absent and keep downstream family regeneration on the same admitted facts.
- [x] Run focused regeneration, lineage, safe-removal, and publication-quality tests.

## Task 4: Provider-free canary replay and evidence documentation

**Files:** `docs/quality/verified-claims-step2-visual-shadow-20261018.md`, `CONSOLIDATED_TODO.md` only if supported by measured evidence, and focused replay/report tooling only if an existing entry point can carry the explicit canary configuration.

- [ ] Run provider-free replay using retained real-report artifacts and synthetic contract cases for the admission boundary; record unavailable live measurements honestly.
- [ ] If exact expected SHA-256 identities and isolated PDFs are available, run the opt-in visual canary with existing GPT-6 Luna High infrastructure; otherwise record the precise source-hash/configuration limitation and do not fabricate results.
- [ ] Compare fresh, cached, and scoped-regenerated outputs for the ten-report cohort where retained artifacts support comparison; record calls, tokens, cost, latency, factual/editorial outcomes, and cache reuse only when measured.
- [ ] Update the existing Step 2 shadow evidence report with the boundary, canary admission results, limitations, and Step 3 readiness verdict; do not claim live selection improvement from post-selection replay alone.
- [ ] Run focused suites, repository CI checks, inspect the final diff for scope/secrets, commit, push, and report exact results including any pre-existing environment failure.

