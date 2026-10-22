# Verified Facts Step 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Make independently verified visual facts the exclusive factual input to the opt-in editorial canary while preserving the existing default production path.

**Architecture:** Reuse the current visual correction and independent verification calls, adding a small \`VerifiedFact\` contract and a fact projection at the existing canary callback boundary. The canary will produce a sanitized verified-facts evidence pack and transformed planning aliases; generation, storage, cache, and regeneration will consume that pack rather than raw findings or original candidate bindings. No canonical persistence, publication, readiness promotion, or WordPress write is added.

**Tech Stack:** Python dataclasses, existing visual evaluator, prompt service, artifact generator, regeneration generator, pytest, mypy, Ruff, retained real-report replay artifacts.

## Global Constraints

- Keep the default \`generate_artifacts()\` and \`run_report_analysis()\` path unchanged when verified-facts canary configuration is absent.
- Treat DocMap claims, findings, original metrics, and original evidence bindings as discovery-only inputs.
- Admit only terminal independently verified facts with a non-empty statement, valid source hash, inspected supporting physical pages, unique candidate/fact identity, and no conflicting duplicate IDs.
- Do not add a second LLM call, persistence service, vector store, dependency, or deterministic semantic-equivalence verifier.
- Preserve bounded correction and verification attempts, source-PDF hash checks, physical-page checks, cache integrity, regeneration safety, and publication safeguards.
- Omit discovered quotes from verified-facts mode unless they are independently verified; do not promote quote candidates automatically.

---

### Task 1: Define and emit the verified-fact contract

**Files:**

- Modify: \`src/contracts/verified_claims.py\`
- Modify: \`src/generators/verified_claims_visual_generator.py\`
- Modify: \`src/prompts/report_vs/validate/visual_claim_verification/system.yaml\`
- Modify: \`src/prompts/report_vs/validate/visual_claim_verification/user.yaml\`
- Test: \`tests/_test_verified_claims_visual_generator/cases_01_visual.py\`
- Test: \`tests/_test_verified_claims_visual_generator/cases_02_visual.py\`
- Test: \`tests/_test_verified_claims_visual_generator/cases_03_visual.py\`

**Interfaces:**

- Add a versioned \`VerifiedFact\` dataclass with \`fact_id\`, \`statement\`, \`metric\`, \`source_identity\`, \`source_pdf_sha256\`, \`supporting_physical_pages\`, \`verification_outcome\`, \`provenance\`, and discovery trace fields that are not factual authority.
- Add \`verified_fact\` to the verification attempt/result contracts without removing the existing shadow audit fields.
- The verification response JSON will contain \`verified_fact.statement\`, \`verified_fact.metric\`, and \`verified_fact.qualifiers\`; the existing supporting-page and source-note fields remain the provenance authority.

- [ ] **Step 1: Write the failing tests.** Add a response fixture containing a materially different proposition and a complete source-supported metric, then assert the evaluator returns that statement and metric in \`verified_fact\` without copying the original candidate metric or evidence ID. Add failures for a missing statement, malformed metric, unsupported page, and missing substantive verification note.

- [ ] **Step 2: Run the focused visual suite and confirm the new assertions fail for the missing verified-fact fields.**

\`\`\`powershell
pytest -q tests/test_verified_claims_visual_generator.py
\`\`\`

- [ ] **Step 3: Implement the smallest contract and parser change.** Parse and validate the structured verified fact in the existing verification call, preserve qualitative facts with an empty metric object, carry the source hash from the verified request identity, and record only the verifier's supporting pages and notes as provenance. Do not use \`_claims_have_identical_proposition()\` to decide whether the result is authoritative.

- [ ] **Step 4: Update the verification prompt to require the structured fact.** State that the original claim, original metric, and original evidence IDs are discovery context only; require the model to return the source-supported statement and metric fields actually visible on the supplied pages, with empty fields for qualitative facts and no invented metadata.

- [ ] **Step 5: Run the focused visual and prompt tests until green.**

\`\`\`powershell
pytest -q tests/test_verified_claims_visual_generator.py tests/test_llm_routing_policy.py tests/test_prompt_service.py
\`\`\`

- [ ] **Step 6: Commit the contract/evaluator checkpoint.**

\`\`\`powershell
git add src/contracts/verified_claims.py src/generators/verified_claims_visual_generator.py src/prompts/report_vs/validate/visual_claim_verification tests/_test_verified_claims_visual_generator
git commit -m "feat: emit independently verified visual facts"
\`\`\`

### Task 2: Replace candidate-binding admission with verified-fact admission

**Files:**

- Modify: \`src/generators/verified_claims_canary.py\`
- Modify: \`tests/test_verified_claims_visual_authority_canary.py\`

**Interfaces:**

- \`admit_visual_authority_candidates()\` will return \`VisualAuthorityAdmission.verified_facts\` and a sanitized \`verified_evidence_packs\` projection. \`admitted_candidates\` remains only as a compatibility alias for private callers during this migration and is not used as factual authority.
- The adapter will require one unique evaluation per expected candidate, terminal verified outcome, valid fact statement, exact source identity/hash, supporting pages within inspected pages, and no conflicting duplicate IDs.

- [ ] **Step 1: Write failing admission tests.** Replace the current retained/unbound expectations with tests showing that a verified material replacement with different metric, proposition, and no original evidence binding is admitted; a missing verified fact, duplicate evaluation ID, conflicting duplicate candidate ID, wrong hash/page, or incomplete evaluation is quarantined.

- [ ] **Step 2: Run the canary test file and confirm the material replacement test fails because current admission still requires original bindings.**

\`\`\`powershell
pytest -q tests/test_verified_claims_visual_authority_canary.py
\`\`\`

- [ ] **Step 3: Implement one projection boundary.** Build the fact ID from the expected stable candidate ID, preserve the original candidate ID only under discovery provenance, generate a verified-fact evidence ID from that fact ID, and populate the sanitized findings pack from the verified statement, verified metric, supporting pages, and verifier notes. Do not copy original evidence text, original metric values, or original evidence IDs into the fact.

- [ ] **Step 4: Fix duplicate handling in one pass.** Track candidate IDs and result IDs in separate maps; reject a repeated ID unless the representations are byte-equivalent and the evaluation is unique. Never resolve duplicates by score, source order, or original binding.

- [ ] **Step 5: Run the canary suite and the source-binding regressions.**

\`\`\`powershell
pytest -q tests/test_verified_claims_visual_authority_canary.py tests/test_artifact_evidence_binding.py tests/test_artifact_normalization_source_fidelity.py
\`\`\`

- [ ] **Step 6: Commit the admission checkpoint.**

\`\`\`powershell
git add src/generators/verified_claims_canary.py tests/test_verified_claims_visual_authority_canary.py
git commit -m "refactor: admit verified facts without original bindings"
\`\`\`

### Task 3: Make verified facts the only factual input to generation

**Files:**

- Modify: \`src/generators/_artifact_generator/generation.py\`
- Modify: \`src/generators/_artifact_generator/storage.py\`
- Modify: \`src/generators/artifact_normalization.py\`
- Modify: \`src/services/schema_validator_service.py\`
- Modify: \`tests/test_verified_claims_visual_authority_canary.py\`

**Interfaces:**

- Add a private verified-facts mode payload containing a sanitized evidence pack, sanitized source-context map, and verified-fact digest.
- In that mode, final insights, summary, metric spine, key figures, expert synthesis, and distribution prompts receive only the sanitized pack plus non-factual plan/layout context.
- \`quotes_final\` is empty in verified-facts mode unless a future independently verified quote path is explicitly supplied; raw quote candidates are never passed through.

- [ ] **Step 1: Write failing downstream tests.** Add a raw-finding candidate whose claim conflicts with the verified fact and assert that final-insight, summary, metric-spine, key-figure, expert, and LinkedIn prompt variables contain the verified fact only. Assert that quotes are empty, raw DocMap/finding text is absent from factual variables, and the verified fact's page/metric survives normalization.

- [ ] **Step 2: Run the generation tests and confirm raw evidence still appears in the canary prompt variables.**

\`\`\`powershell
pytest -q tests/test_verified_claims_visual_authority_canary.py
\`\`\`

- [ ] **Step 3: Implement the earliest shared input boundary.** After canary admission, construct a sanitized evidence pack and transformed editorial-plan evidence aliases from verified facts; rebuild \`base_vars\`, summary evidence, quote plan, expert context, and distribution variables from that pack. Retain only report structure, theme names, categories, and period/region metadata from the original planning context.

- [ ] **Step 4: Keep deterministic normalization structural.** In verified-facts mode, bypass \`preserve_public_source_displays()\` and any original-evidence metric repair, while retaining sign formatting, schema normalization, exact reference handling, and required artifact-family validation against the verified-facts pack.

- [ ] **Step 5: Run the focused generation, public-quality, and schema tests.**

\`\`\`powershell
pytest -q tests/test_verified_claims_visual_authority_canary.py tests/test_artifact_normalization.py tests/test_artifact_public_projections.py tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py
\`\`\`

- [ ] **Step 6: Commit the exclusive-input checkpoint.**

\`\`\`powershell
git add src/generators/_artifact_generator/generation.py src/generators/_artifact_generator/storage.py src/generators/artifact_normalization.py src/services/schema_validator_service.py tests/test_verified_claims_visual_authority_canary.py
git commit -m "feat: generate editorial output from verified facts"
\`\`\`

### Task 4: Align cache, lineage, and scoped regeneration

**Files:**

- Modify: \`src/generators/report_regeneration_generator.py\`
- Modify: \`tests/test_verified_claims_visual_authority_canary.py\`
- Modify: relevant regeneration regression tests only when a verified-facts contract assertion requires it

**Interfaces:**

- Private cache metadata stores the verified-facts digest and sanitized fact snapshot, not the original candidate factual fields.
- Regeneration restores only the same verified-fact IDs and factual fields; it cannot append raw findings, DocMap claims, original metrics, or quote candidates.

- [ ] **Step 1: Write failing cache/regeneration tests.** Assert that a changed verified-facts digest bypasses cached family output, scoped regeneration preserves the same fact snapshot, an attempted raw-finding fallback is rejected, and final validation accepts a changed verified proposition when it accurately preserves the verified fact.

- [ ] **Step 2: Run the focused regeneration suite and confirm the new assertions fail under candidate-pool restoration.**

\`\`\`powershell
pytest -q tests/test_verified_claims_visual_authority_canary.py tests/test_report_regeneration_generator.py tests/test_regeneration_finalization.py tests/test_regeneration_candidate.py
\`\`\`

- [ ] **Step 3: Replace candidate-pool restoration with verified-fact snapshot restoration.** Preserve stable fact IDs, protected verified metric fields, source hash, supporting pages, and verifier notes; reject stale or conflicting snapshots with the existing typed error path.

- [ ] **Step 4: Run the full affected regeneration and cache suites.**

\`\`\`powershell
pytest -q tests/test_verified_claims_visual_authority_canary.py tests/test_report_regeneration_generator.py tests/test_regeneration_finalization.py tests/test_regeneration_candidate.py tests/test_regeneration_contracts.py tests/test_atomic_regeneration_contract.py
\`\`\`

- [ ] **Step 5: Commit the lineage checkpoint.**

\`\`\`powershell
git add src/generators/report_regeneration_generator.py tests/test_verified_claims_visual_authority_canary.py tests/test_report_regeneration_generator.py tests/test_regeneration_finalization.py tests/test_regeneration_candidate.py tests/test_regeneration_contracts.py tests/test_atomic_regeneration_contract.py
git commit -m "fix: retain verified facts through regeneration"
\`\`\`

### Task 5: Replay focused real reports and document readiness

**Files:**

- Modify: \`docs/quality/verified-claims-step2-visual-shadow-20261018.md\`
- Modify: \`docs/superpowers/plans/2026-10-22-verified-facts-step3.md\`
- Modify: \`CONSOLIDATED_TODO.md\` only when the measured evidence changes authoritative status

- [ ] **Step 1: Run provider-free replay for Criteo, Adjust, DoubleVerify, and Algolia.** Confirm that retained visual results project into verified facts without original-binding requirements, and record hash/page/fact counts.

- [ ] **Step 2: Run bounded actual final editorial generation for those four reports using GPT-6 Luna High and the opt-in verified-facts mode.** Use isolated output/cache directories, no publication writes, and inspect final insights, summary, key figures, expert commentary, and LinkedIn output against the original PDF pages.

- [ ] **Step 3: Compare against the retained editorial path.** Record factual errors, unsupported promotions, important-finding coverage, validation failures, provider calls, tokens, cost, latency, cache reuse, and regeneration consistency. Do not claim improvement from evaluator-only replay.

- [ ] **Step 4: Run the focused public/editorial quality and repository checks.**

\`\`\`powershell
pytest -q tests/test_verified_claims_visual_authority_canary.py tests/test_verified_claims_visual_generator.py tests/test_verified_claims_step2_provenance.py tests/test_verified_claims_step2_replay.py tests/test_artifact_evidence_binding.py tests/test_artifact_insight_shortlisting.py tests/test_artifact_normalization.py tests/test_artifact_normalization_source_fidelity.py tests/test_artifact_public_projections.py tests/test_report_regeneration_generator.py tests/test_regeneration_finalization.py tests/test_regeneration_candidate.py tests/test_regeneration_contracts.py tests/test_atomic_regeneration_contract.py tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py
python scripts/ci/check_public_report_quality.py
\`\`\`

- [ ] **Step 5: Update the evidence report with the exact focused results and a PASS/PARTIAL/FAIL Step 3 verdict.** Keep the canary shadow-only and explicitly list unavailable full-cohort or hosted-CI checks.

- [ ] **Step 6: Inspect the final diff, run \`git diff --check\`, commit, and push each verified checkpoint.**

\`\`\`powershell
git diff --check
git status --short
git push origin codex/fix-retained-insight-evidence-validation
\`\`\`

## Execution evidence — 2026-10-22

Tasks 1–4 are implemented in the current worktree and covered by the
verified-fact contract, admission, downstream-input, cache, and regeneration
regressions. The focused suite passed 498 tests; compileall, the contract
schema snapshot gate, and `git diff --check` passed. The provider-free
snapshot audit passed for the three admitted focused reports and correctly
reported no Algolia snapshot after fail-closed incomplete coverage. Actual
GPT-6 Luna High downstream generation produced PDF-reviewed artifacts for
Criteo, Adjust, and DoubleVerify; Algolia abstained. Task 5 is therefore
partially complete: the evidence report is updated, but full-ten downstream
Step 3 replay and fresh retained-cohort verified-fact snapshots remain open.
The implementation verdict is **PARTIAL**, and Step 3 is not closed.

