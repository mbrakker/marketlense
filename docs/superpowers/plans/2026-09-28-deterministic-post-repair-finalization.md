# Deterministic Post-Repair Finalization Implementation Plan

> **For agentic workers:** Execute each task in this plan inline; the user authorized implementation and verification in the current request.

**Goal:** Keep deterministic projections and provenance current after atomic source repairs, and carry only promoted validation grounding into final materialization.

**Architecture:** Reuse the artifact root dependency graph, canonical projection builders, sentence-grid contract, report analysis store, and file service. Validate Summary claims from the same joined public surface used by provenance generation. Promote the candidate grounding package only after its artifact hash matches the candidate being promoted.

**Tech Stack:** Python, pytest, report analysis orchestration, existing artifact/provenance contracts and services.

## Global Constraints

- Keep atomic planner scope, direct-string repair values, protected-field derivation, cache fencing, and retry limits unchanged.
- Do not run the full 20-report cohort or publish.
- Reuse canonical builders and the existing `soft_copy_material_sentences` grid.
- Keep writes report-scoped, atomic, and idempotent.

---

### Task 1: Unify Summary claim inventory with provenance segmentation

**Files:**
- Modify: `src/generators/claim_validation_generator.py`
- Test: `tests/test_retained_claim_grounding.py`

**Interfaces:**
- Consumes: `soft_copy_public_text("summary", summary)` and `soft_copy_material_sentences`.
- Produces: one retained Summary claim per sentence in the joined canonical public surface, with a specific field section only when the sentence maps unambiguously to one field.

- [x] Add a regression with a sentence spanning `tldr` and `card_tldr_compact`; confirm current validation splits it into fragments and cannot find the retained claim.
- [x] Build the Summary retained-claim inventory from the same joined surface as provenance generation.
- [x] Run the focused Summary claim and finalization tests.

### Task 2: Carry forward only a matching promoted candidate grounding package

**Files:**
- Modify: `src/generators/_report_generation_dependencies/analysis.py`
- Modify: `src/orchestrators/_report_analysis_orchestrator/validation.py`
- Modify: `tests/_test_report_analysis_generator/cases_02_allows_abstained_quote_family.py`
- Modify: `tests/_test_report_analysis_generator/cases_03_rejects_unsupported_repair_target.py`

**Interfaces:**
- Consumes: the attempt-scoped candidate package, candidate artifact hash, canonical JSON reader, and report analysis store.
- Produces: a report-scoped current candidate package only after matching artifact promotion; rolled-back attempts leave it untouched.

- [x] Add tests for exact artifact binding, mismatch rejection, report-scoped atomic storage, and rollback followed by promotion.
- [x] Read and hash-check before artifact promotion; store atomically after the artifact write succeeds.
- [x] Report package read/store failures with typed terminal errors.
- [ ] Run report analysis and retained-grounding regressions.

### Task 3: Retain deterministic replay and cohort evidence

**Files:**
- Modify: `docs/workflows/validation-and-regeneration.md`
- Modify: `docs/quality/reliability-cohort-20260927-grounding/final-package-lifecycle-5/README.md`
- Create: `docs/quality/reliability-cohort-20260927-grounding/final-package-lifecycle-5/2026-09-28-postrepair-finalization-measurement.json`

- [ ] Replay available Mobile and DoubleVerify snapshots without model calls.
- [ ] Run focused projection, provenance, scope, package, and readiness tests.
- [ ] Rerun the unchanged E13 corpus, pinned five-report cohort, and isolated IAS canary with publication disabled.
- [ ] Review the final diff and push implementation, tests, and retained evidence to `main`.
