# Verified Claims Step 2 Visual Claim Correction Shadow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an isolated, provider-backed shadow evaluator that corrects shortlisted insight claims from complete source-PDF pages and independently verifies each correction with bounded retry, without changing authoritative artifacts or publication.

**Architecture:** A typed generator receives shortlisted insight dictionaries plus the verified physical PDF page and uses the existing PDF page-render service and image-capable LLM boundary. Two prompt namespaces share the existing `report_vs/validate` high-reasoning policy: correction produces the analytical claim and verification independently checks it; deterministic adapters validate structured responses, preserve source identity/page/evidence metadata, and record terminal outcomes. The generator returns an evaluation artifact only; it does not write canonical claims, mutate input artifacts, regenerate downstream families, or publish.

**Tech Stack:** Python dataclasses, existing prompt service, existing model policy resolver, existing `OpenAIJSONImagePromptRequest`, PyMuPDF page rendering service, pytest, retained frozen-five artifacts.

## Global Constraints

- Use complete original PDF pages at the verified physical page number; never use a crop as visual authority.
- Use GPT-6 Luna with high reasoning through the existing execution policy; no new provider or service.
- Maximum two correction attempts and two independent verification attempts per claim.
- Preserve stable candidate IDs, canonical evidence IDs, physical pages, evidence spans, protected factual fields and source identity.
- Shadow mode only: no canonical verified-claim persistence, downstream regeneration, publication readiness changes, WordPress writes, or publication.
- Cache image model outputs through the existing semantic cache identity, including source PDF/page and claim/verification inputs.
- Fail closed on missing/invalid page bindings or malformed model output; continue independent claims after a failure.

---

### Task 1: Define the typed shadow-evaluation contract

**Files:**
- Create: `src/contracts/verified_claims.py`
- Test: `tests/test_verified_claims_visual_generator.py`

**Interfaces:**
- Consumes: one shortlisted insight mapping containing `stable_candidate_id` or `candidate_id`, text, `evidence_id`/`evidence_spans`, and a verified physical page.
- Produces: immutable request, per-attempt correction/verification records, per-claim terminal outcome, and a collection response whose input claim metadata remains unchanged.

- [ ] **Step 1: Write the failing contract tests**

```python
def test_shadow_result_preserves_source_binding_and_terminal_outcome():
    result = VisualClaimEvaluationResult(
        schema_version="1.0",
        candidate_id="candidate-1",
        original_claim="Original",
        source_identity="pdf-sha256",
        physical_page=5,
        evidence_ids=["f1"],
        evidence_spans=[{"evidence_id": "f1", "page": 5}],
        correction_attempts=[],
        verification_attempts=[],
        final_claim="",
        outcome="failed_verification",
        failure_reason="verification_failed_twice",
    )
    assert result.candidate_id == "candidate-1"
    assert result.physical_page == 5
    assert result.outcome == "failed_verification"
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest -q tests/test_verified_claims_visual_generator.py::test_shadow_result_preserves_source_binding_and_terminal_outcome`

Expected: FAIL because the contract module does not exist.

- [ ] **Step 3: Implement the minimal frozen dataclasses**

Define versioned dataclasses for the request, correction attempt, verification attempt, per-claim result, and batch result. Store evidence IDs/spans as copied immutable-compatible values at construction boundaries; do not add new factual fields or infer missing bindings.

- [ ] **Step 4: Run the contract test**

Run: `python -m pytest -q tests/test_verified_claims_visual_generator.py::test_shadow_result_preserves_source_binding_and_terminal_outcome`

Expected: PASS.

---

### Task 2: Add correction and independent-verification prompt contracts

**Files:**
- Create: `src/prompts/report_vs/validate/visual_claim_correction/system.yaml`
- Create: `src/prompts/report_vs/validate/visual_claim_correction/user.yaml`
- Create: `src/prompts/report_vs/validate/visual_claim_verification/system.yaml`
- Create: `src/prompts/report_vs/validate/visual_claim_verification/user.yaml`
- Test: `tests/test_verified_claims_visual_generator.py`

**Interfaces:**
- Consumes: JSON-rendered original claim, source identity, physical page, existing evidence binding, and retry diagnostics.
- Produces: structured correction object `{claim, status, issues}` and verification object `{outcome, diagnostics, source_truth_notes}`.

- [ ] **Step 1: Write failing prompt-render tests**

```python
def test_visual_prompts_require_complete_page_and_separate_source_authority():
    correction = load_prompt_set(PromptLoadRequest(schema_version="1.0", namespace="report_vs/validate/visual_claim_correction"), ctx)
    verification = load_prompt_set(PromptLoadRequest(schema_version="1.0", namespace="report_vs/validate/visual_claim_verification"), ctx)
    assert "complete original PDF page" in correction.system.text
    assert "independently" in verification.system.text.lower()
    assert "original claim" in correction.user.text.lower()
```

- [ ] **Step 2: Run the prompt test to verify it fails**

Run: `python -m pytest -q tests/test_verified_claims_visual_generator.py::test_visual_prompts_require_complete_page_and_separate_source_authority`

Expected: FAIL because the namespaces are absent.

- [ ] **Step 3: Add the minimal prompt resources**

The correction prompt must say that the claim is direction only, the complete page is authoritative, editorial interpretation is allowed only when source-grounded, and unresolved pages must abstain. The verification prompt must receive only corrected claim plus source page/binding context, check all protected dimensions and analytical value, and return structured JSON without relying on correction reasoning.

- [ ] **Step 4: Run prompt loading and dry-run validation**

Run: `python -m pytest -q tests/test_verified_claims_visual_generator.py::test_visual_prompts_require_complete_page_and_separate_source_authority tests/test_prompt_dry_run_validation.py`

Expected: PASS.

---

### Task 3: Implement bounded visual correction and independent verification

**Files:**
- Create: `src/generators/verified_claims_visual_generator.py`
- Modify: `src/contracts/openai.py` only if the existing image request cannot carry required provenance metadata without a compatibility-preserving optional field.
- Test: `tests/test_verified_claims_visual_generator.py`

**Interfaces:**
- Consumes: `VisualClaimEvaluationRequest`, `AppSettings`, `RunContext`, prompt/render/LLM dependencies, and shortlisted claim mappings.
- Produces: `VisualClaimEvaluationResult` values with `verified`, `verified_after_retry`, `failed_verification`, `unresolved`, or `skipped` outcomes.

- [ ] **Step 1: Write failing generator behavior tests**

```python
def test_first_verification_failure_is_repaired_once_and_then_verified():
    responses = iter([
        {"claim": "Corrected 61%/34%", "status": "corrected", "issues": []},
        {"outcome": "rejected", "diagnostics": ["wrong cohort"], "source_truth_notes": ""},
        {"claim": "Corrected 61%/34% for the stated cohort", "status": "corrected", "issues": ["added cohort"]},
        {"outcome": "verified", "diagnostics": [], "source_truth_notes": "source matches"},
    ])
    result = evaluate_shortlisted_claims(
        request=make_request_with_two_claims(),
        settings=test_settings,
        ctx=test_context,
        dependencies=make_dependencies(model_json=lambda request, ctx: next(responses)),
    )
    assert result.claims[0].outcome == "verified_after_retry"
    assert len(result.claims[0].correction_attempts) == 2
    assert len(result.claims[0].verification_attempts) == 2


def test_two_verification_failures_do_not_block_the_next_claim():
    result = evaluate_shortlisted_claims(
        request=make_request_with_two_claims(),
        settings=test_settings,
        ctx=test_context,
        dependencies=make_dependencies(model_json=continue_after_failure),
    )
    assert [item.outcome for item in result.claims] == ["failed_verification", "verified"]
```

- [ ] **Step 2: Run the new tests to verify the missing behavior**

Run: `python -m pytest -q tests/test_verified_claims_visual_generator.py -k 'retry or failure or binding'`

Expected: FAIL because the generator is absent.

- [ ] **Step 3: Implement the deterministic orchestration**

Resolve both namespaces through `prepare_prompt_bundle` and the existing settings policy. Require the resolved model to be GPT-6 Luna and reasoning effort to be high; otherwise fail closed before provider I/O. Render each distinct verified physical page once through `render_page_for_crop_refine` with a full-page request and reuse its path. Build one correction request per attempt and one independent verification request per attempt using `OpenAIJSONImagePromptRequest`, enabling the existing response cache. Validate dictionaries, required status/outcome values, non-empty accepted claims, and diagnostic lists. Preserve the original input binding in every result and never copy model-supplied evidence IDs/pages/spans into authoritative fields.

- [ ] **Step 4: Run the generator tests**

Run: `python -m pytest -q tests/test_verified_claims_visual_generator.py`

Expected: PASS, including missing-page abstention, malformed response failure, retry bounds, continuation, stable IDs, and no-input-mutation tests.

---

### Task 4: Add provider-free frozen-five replay evidence

**Files:**
- Create: `scripts/quality/replay_verified_claims_step2.py`
- Create: `docs/quality/verified-claims-step2-visual-shadow-20261018.md`
- Test: `tests/test_verified_claims_step2_replay.py`

**Interfaces:**
- Consumes: the exact Step 0 reference JSON and retained frozen-five artifacts/PDF paths.
- Produces: deterministic provider-free replay summary with explicit skipped-provider status; no publication or canonical writes.

- [ ] **Step 1: Write failing replay test**

```python
def test_step2_replay_reports_provider_unavailable_without_fabricated_claims():
    report = replay_frozen_step2(provider_available=False)
    assert report["provider_status"] == "skipped_unavailable"
    assert report["fabricated_fixture_substitution"] is False
    assert report["reports"] == ["Capgemini Research Institute", "Activate", "KPMG", "Reuters Institute", "Adjust"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest -q tests/test_verified_claims_step2_replay.py::test_step2_replay_reports_provider_unavailable_without_fabricated_claims`

Expected: FAIL because the replay module is absent.

- [ ] **Step 3: Implement provider-free replay and evidence report**

Read only retained artifacts and the 15-case/39-variant reference set. Verify source PDF hashes and claim/page binding availability, report which cases are evaluable, and explicitly separate live-provider results from deterministic input coverage. Do not invent corrected outputs when provider access is unavailable. Include the exact five reports, baseline SHA/manifest identity, cache/provenance fields, and recommendation for Step 3.

- [ ] **Step 4: Run replay and inspect output**

Run: `python scripts/quality/replay_verified_claims_step2.py --provider-free`

Expected: exit 0, report records all five reports and 15 cases, and states that actual GPT-6 Luna visual evaluation was unavailable if credentials/provider access are absent.

---

### Task 5: Update canonical status and run completion gates

**Files:**
- Modify: `docs/backlog/E-evidence.md`
- Modify: `CONSOLIDATED_TODO.md`
- Modify: `docs/quality/verified-claims-step2-visual-shadow-20261018.md`

- [ ] **Step 1: Add the evidence/status entry**

Record implementation SHA after commit, focused tests, exact replay command, provider availability, call/token/cost/latency/cache measurements when available, and the honest PASS/PARTIAL/FAIL verdict. Keep Step 3 unimplemented and do not close unrelated E18 work.

- [ ] **Step 2: Run the focused and downstream gates**

Run: `python -m pytest -q tests/test_verified_claims_visual_generator.py tests/test_verified_claims_step2_replay.py tests/test_prompt_dry_run_validation.py tests/test_llm_service.py tests/test_llm_routing_policy.py tests/test_pdf_crop_decomposition.py tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py`

Expected: all selected tests pass, with live-provider evaluation explicitly skipped when prerequisites are unavailable.

- [ ] **Step 3: Inspect final diff and commit**

Run: `git diff --check`, `git status --short`, then stage the scoped files with `git add` and commit them with `git commit -m "feat: add shadow visual verified-claims evaluation"`; push `codex/fix-retained-insight-evidence-validation`.

- [ ] **Step 4: Verify the pushed commit**

Run: `git rev-parse HEAD`, `git status --short --branch`, and `git log -1 --oneline`.

Expected: clean branch at the pushed commit; report the SHA and any unavailable live checks without claiming them as performed.

## Spec coverage review

- Complete-page rendering and physical-page provenance: Tasks 3–4.
- GPT-6 Luna high reasoning through existing policy: Task 3.
- Independent correction and verification: Tasks 2–3.
- Bounded retry and continuation: Task 3.
- Structured audit/caching and no authoritative mutation: Tasks 1–3.
- Frozen-five/15-case evaluation and honest provider limitation: Task 4.
- Backlog/status and completion evidence: Task 5.
- Step 3 remains out of scope throughout.
