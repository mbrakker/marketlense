# Regeneration Evidence Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make report regeneration preserve authoritative evidence identifiers and source pages so at least 95% of representative reports can reach publish readiness without weakening grounding or editorial-quality gates.

**Architecture:** The regeneration generator remains responsible for model-led prose repair. Deterministic normalization restores a missing final-insight binding only when a stable insight ID has an existing candidate or prior-final binding, while the artifact normalizer derives known evidence spans and pages from retained evidence rather than model-provided page metadata. Canonical validation still rejects unknown IDs and unsupported content.

**Tech Stack:** Python, dataclass contracts, JSON Schema, pytest, existing MarketLense prompt service and validation generators.

## Global Constraints

- Keep source admission, schema, grounding, semantic, chart/table, editorial, and publish-readiness gates enabled.
- Do not add report- or publisher-specific logic, waivers, or content edits.
- Keep model retry bounded and owned by the existing orchestrator.
- Preserve deterministic, retained source provenance and no-public-write validation profiles.

---

### Task 1: Preserve a stable final-insight evidence binding

**Files:**
- Modify: `src/generators/report_regeneration_generator.py:_handle_insights_bundle_regeneration`
- Modify: `tests/test_report_regeneration_generator.py`

**Interfaces:**
- Consumes: normalized `insights_final`, `insights_candidates`, and prior final insights.
- Produces: final insights whose blank evidence binding is restored only from a same-ID retained candidate or prior-final record.

- [ ] **Step 1: Write the failing test**

```python
def test_regeneration_restores_blank_final_insight_binding_from_same_id_candidate() -> None:
    restored = _restore_final_insight_evidence_bindings(
        final_insights=[{"id": "insight_a", "text": "Repaired", "evidence_id": "", "pages": []}],
        candidate_insights=[{"id": "insight_a", "evidence_id": "finding_1", "evidence": "42%", "pages": [3]}],
        prior_final_insights=[],
    )
    assert restored[0]["evidence_id"] == "finding_1"
    assert restored[0]["pages"] == [3]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_report_regeneration_generator.py::test_regeneration_restores_blank_final_insight_binding_from_same_id_candidate`

Expected: FAIL because `_restore_final_insight_evidence_bindings` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def _restore_final_insight_evidence_bindings(*, final_insights, candidate_insights, prior_final_insights):
    bindings = _insight_bindings(candidate_insights, prior_final_insights)
    for item in final_insights:
        if isinstance(item, dict) and not _s(item.get("evidence_id")).strip():
            binding = bindings.get(_s(item.get("id")).strip())
            if binding:
                item.update(binding)
    return final_insights
```

Copy only `evidence_id`, `evidence`, `evidence_spans`, and `pages`; never replace regenerated editorial prose or invent a binding for an unknown ID.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_report_regeneration_generator.py::test_regeneration_restores_blank_final_insight_binding_from_same_id_candidate`

Expected: PASS.

### Task 2: Canonicalize known evidence pages during artifact assembly

**Files:**
- Modify: `src/generators/artifact_normalization.py:bind_artifact_evidence_spans`
- Modify: `tests/test_artifact_normalization.py`

**Interfaces:**
- Consumes: an artifact item with a canonical known `evidence_id` and retained evidence packs.
- Produces: authoritative derived spans and pages for that ID; unknown or unbound IDs remain visible for the validation gate.

- [ ] **Step 1: Write the failing test**

```python
def test_bind_artifact_evidence_spans_replaces_model_pages_for_known_evidence() -> None:
    summary = {"claim_evidence_map": [{"claim": "A", "evidence_id": "finding_1", "pages": [21, 22]}]}
    bind_artifact_evidence_spans(...)
    assert summary["claim_evidence_map"][0]["pages"] == [21]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_artifact_normalization.py::test_bind_artifact_evidence_spans_replaces_model_pages_for_known_evidence`

Expected: FAIL because the current implementation retains model-provided pages and spans when present.

- [ ] **Step 3: Write minimal implementation**

Use the retained span index as the first choice whenever it has entries for a known `evidence_id`; write those derived spans and their deduplicated positive pages back to claims and insights. Retain the present fallback behavior only when no retained span exists.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_artifact_normalization.py tests/test_regeneration_candidate.py`

Expected: PASS; unknown evidence IDs and missing material evidence still fail.

### Task 3: Constrain model regeneration to evidence-exact output

**Files:**
- Modify: `src/prompts/report_vs/artifacts/regenerate/summary/user.yaml`
- Modify: `src/prompts/report_vs/artifacts/regenerate/insights_final/user.yaml`
- Modify: `tests/test_prompt_service.py`
- Modify: `docs/product/editorial-output.md`

**Interfaces:**
- Consumes: existing grounding package and current-section JSON.
- Produces: regenerated records that preserve existing IDs/pages or use only the exact evidence/page metadata supplied in the grounding package.

- [ ] **Step 1: Write failing prompt-integrity assertions**

```python
assert "copy its evidence_id and pages exactly" in summary_prompt
assert "must not be empty for a material insight" in insights_final_prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_prompt_service.py -k regeneration`

Expected: FAIL because the exact preservation requirements are absent.

- [ ] **Step 3: Add minimal prompt requirements and documentation**

Require exact retained evidence ID/page copying, prohibit numbers absent from selected evidence text, and require removal/abstention instead of an unbound material insight. Document that deterministic canonicalization follows model output and does not bypass validation.

- [ ] **Step 4: Run prompt tests and fixture regression**

Run: `python -m pytest -q tests/test_prompt_service.py tests/test_prompt_dry_run_validation.py`

Run: `python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3`

Expected: PASS.

### Task 4: Verify the repaired boundary and safe end-to-end behavior

**Files:**
- Modify: `docs/quality/evidence.md` only if a canonical evidence-entry format is required by the existing document.

- [ ] **Step 1: Run focused validation suites**

Run: `python -m pytest -q tests/test_report_regeneration_generator.py tests/test_regeneration_candidate.py tests/test_artifact_normalization.py tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py`

- [ ] **Step 2: Run static and quality gates**

Run: `python scripts/ci/check_public_report_quality.py`

Run: `git diff --check`

- [ ] **Step 3: Run a bounded isolated representative validation cohort**

Run the normal discovery, acquisition, ingest, and publication-readiness path under a no-Drive-write/no-WordPress-write profile. Record source identities, terminal gate outcomes, retries, provider calls/tokens/cost, and byte-identical retained HTML hashes.

- [ ] **Step 4: Record outcome**

Report the pass rate as `publish_ready / admitted canonical sources`. Treat any held source as part of the denominator; do not claim the 95% target until a representative enough denominator exists to measure it.

## Self-review

- Scope is limited to evidence-binding preservation, canonical source-page derivation, and matching prompt constraints.
- The plan does not weaken validators or add report/publisher-specific behavior.
- Tests precede each production behavior change and include both recovery and failure-preservation coverage.
