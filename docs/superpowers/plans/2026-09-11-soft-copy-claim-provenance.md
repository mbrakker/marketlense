# Soft-copy Claim Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retain typed, sentence-level evidence and production provenance for Expert View, LinkedIn, and useful summary/TLDR soft-copy without changing WordPress-visible fields.

**Architecture:** Add a versioned private `soft_copy_claim_provenance` artifact field backed by typed contracts and deterministic normalization. Model prompt responses declare bindings alongside public prose; the artifact generator persists them and regeneration replaces provenance only for regenerated families while preserving untouched entries.

**Tech Stack:** Python dataclasses, JSON Schema, existing artifact generation/checkpoint storage, pytest.

## Global Constraints

- Keep `expert_comment`, `linkedin_post`, and summary public fields unchanged.
- Reuse existing evidence IDs and retained artifact/cache provenance; introduce no evidence store or repair behavior.
- Never project private claim provenance into WordPress/public rendering.
- Preserve checkpoint/cache serialization and regeneration behavior.

---

### Task 1: Define and serialize the retained claim contract

**Files:**
- Create: `src/contracts/soft_copy_claim_provenance.py`
- Modify: `src/schemas/artifacts.schema.json`
- Test: `tests/test_soft_copy_claim_provenance.py`

**Interfaces:**
- Produces `SoftCopyClaimProvenance` and payload parsing/serialization helpers.
- Artifact field: `soft_copy_claim_provenance = {schema_version, claims}`.

- [ ] **Step 1: Write failing contract round-trip and invalid-classification tests.**
- [ ] **Step 2: Run the focused tests and observe the missing contract failure.**
- [ ] **Step 3: Implement the smallest typed contract and JSON-safe helpers.**
- [ ] **Step 4: Add the optional private field to the retained artifact schema.**
- [ ] **Step 5: Re-run focused tests.**

### Task 2: Capture declared bindings during initial generation

**Files:**
- Modify: `src/generators/_artifact_generator/rendering.py`
- Modify: `src/generators/_artifact_generator/generation.py`
- Modify: `src/generators/_artifact_generator/storage.py`
- Modify: `src/prompts/report_vs/artifacts/{summary,expert_comment,linkedin_post}/user.yaml`
- Test: `tests/test_soft_copy_claim_provenance.py`

**Interfaces:**
- Consumes declared `claim_provenance` returned with an artifact family response.
- Produces private claim rows containing family, stable ID, text hash, classification, evidence IDs, known source spans, prompt identity, and initial generation attempt.

- [ ] **Step 1: Write failing artifact-assembly tests for exact factual bindings and interpretive classification.**
- [ ] **Step 2: Run the tests and observe missing retained provenance.**
- [ ] **Step 3: Add output normalization that separates private bindings from public family values.**
- [ ] **Step 4: Build validated provenance from model-declared evidence IDs and existing evidence-span lookup.**
- [ ] **Step 5: Update prompts to return bindings without exposing them in the prose strings.**
- [ ] **Step 6: Re-run focused tests.**

### Task 3: Preserve provenance through regeneration and checkpoints

**Files:**
- Modify: `src/generators/report_regeneration_generator.py`
- Test: `tests/test_report_regeneration_generator.py`
- Test: `tests/test_soft_copy_claim_provenance.py`

**Interfaces:**
- Regenerated families receive the new prompt identity and regeneration attempt.
- Untouched family entries survive from existing artifacts unchanged.

- [ ] **Step 1: Write failing regeneration tests for replacement and retention of provenance.**
- [ ] **Step 2: Run them and observe missing/reused provenance behavior.**
- [ ] **Step 3: Carry private provenance in regeneration state and merge by artifact family.**
- [ ] **Step 4: Re-run regeneration and artifact serialization tests.**

### Task 4: Prove public projection exclusion and document behavior

**Files:**
- Modify: `src/generators/report_render_generator.py` only if the existing renderer passes retained artifacts through without an explicit public projection boundary.
- Modify: `docs/product/editorial-output.md`
- Test: `tests/test_soft_copy_claim_provenance.py`

**Interfaces:**
- Public render input excludes `soft_copy_claim_provenance` while retained `artifacts.json` and checkpoint payloads keep it.

- [ ] **Step 1: Write a failing public-projection test that detects internal provenance in rendered/public payload data.**
- [ ] **Step 2: Run the test and observe the boundary failure if one exists.**
- [ ] **Step 3: Apply the narrowest exclusion at the public projection boundary.**
- [ ] **Step 4: Document that the retained field is private, evidence-bound, and survives regeneration.**
- [ ] **Step 5: Run focused schema/type/lint checks and inspect the diff for unintended repair changes.**
