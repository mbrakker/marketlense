# Editorial Interpretation Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate factual claims, evidence-based interpretations, and MarketLense-authored recommendations distinctly across editorial report surfaces.

**Architecture:** Keep `report_vs/validate/grounding` as the generic retained-evidence decision boundary. Include final-insight implications in its payload, have the prompt classify every material sentence, and map only unsupported interpretation/recommendation failure modes to release-blocking grounding issues; factual claims remain subject to the existing protected-fact validator.

**Tech Stack:** Python, YAML prompt resources, JSON Schema, pytest.

## Global Constraints

- Use retained evidence only; add no publisher- or report-specific rule.
- Do not bypass factual grounding or downgrade existing factual failures.
- Interpretations and recommendations need not repeat source wording, but may not add facts, causal outcomes, certainty, operational/financial benefits, or false source attribution.

---

### Task 1: Cover editorial interpretation/recommendation outcomes

**Files:**
- Create: `tests/test_grounding_editorial_interpretation.py`
- Modify: `tests/test_prompt_dry_run_validation.py`

**Interfaces:**
- Consumes: `run_grounding_check` with schema-valid model results and `grounding_payload` artifacts.
- Produces: errors for unsafe material editorial assertions and no issue for evidence-traceable interpretation/recommendation.

- [x] **Step 1: Write failing prompt and grounding tests**

```python
@pytest.mark.parametrize("section", ("expert_comment", "linkedin_post", "insights_final[0].so_what", "insights_final[0].now_what"))
def test_grounding_blocks_unsupported_editorial_outcomes(section: str) -> None:
    issue = _issues(section=section, classification="analyst_interpretation", violation_type="unsupported_causal_outcome")[0]
    assert issue.severity == "error"
```

Also assert that `grounding_payload` retains `so_what` and `now_what`, a supported MarketLense-authored recommendation is accepted, report-directive misattribution fails, and an embedded factual sentence remains an error.

- [x] **Step 2: Run the focused tests and observe the expected failure**

Run: `python -m pytest -q tests/test_grounding_editorial_interpretation.py tests/test_prompt_dry_run_validation.py -k grounding`

Expected: FAIL because implication text is absent from the grounding payload and unsupported editorial outcomes are non-fatal.

### Task 2: Implement the generic three-class grounding policy

**Files:**
- Modify: `src/prompts/report_vs/validate/grounding/system.yaml`
- Modify: `src/prompts/report_vs/validate/grounding/user.yaml`
- Modify: `src/generators/validation/grounding.py`
- Modify: `src/generators/validation/shared.py`

**Interfaces:**
- Consumes: prompt output carrying `factual_claim`, `analyst_interpretation`, or `prescriptive_recommendation` and a generic violation type.
- Produces: existing hard factual failures plus hard errors for unsafe editorial interpretation/recommendation; evidence-traceable MarketLense advice stays valid.

- [x] **Step 1: Add the minimal policy and output vocabulary**

```python
EDITORIAL_GROUNDING_HARD_FAILURES = {
    "unsupported_causal_outcome",
    "unsupported_operational_or_financial_benefit",
    "unsupported_certainty",
}
```

Add these to the existing hard-failure set, normalize their model-returned names, and retain implication fields in `grounding_payload`. Prompt rules must require classification of every material sentence and make factual claims use the existing protected-fact checks.

- [x] **Step 2: Run focused tests to verify the implementation**

Run: `python -m pytest -q tests/test_grounding_editorial_interpretation.py tests/test_grounding_protected_facts.py tests/test_grounding_semantic_outcomes.py tests/test_prompt_dry_run_validation.py -k grounding`

Expected: PASS.

### Task 3: Document and verify the release decision

**Files:**
- Modify: `docs/workflows/validation-and-regeneration.md`
- Modify: `docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json` only if the approved prompt fixture budget changes.

**Interfaces:**
- Consumes: the revised grounding policy.
- Produces: current validation documentation and fresh test/static evidence.

- [x] **Step 1: Document the three sentence classes and the no-bypass rule**

Describe retained-evidence entailment for facts, evidence-traceable interpretation/recommendation, prohibited unsupported outcome/benefit/certainty/attribution claims, and the absence of publisher exceptions.

- [x] **Step 2: Run generation, grounding, editorial/readiness, fixture, and static checks**

```powershell
python -m pytest -q tests/test_grounding_editorial_interpretation.py tests/test_grounding_protected_facts.py tests/test_grounding_semantic_outcomes.py tests/test_validation_generator.py tests/test_claim_validation_generator.py tests/test_public_editorial_quality_generator.py tests/test_publish_readiness_gate.py tests/test_prompt_dry_run_validation.py
python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3
python scripts/ci/check_ruff_lint.py
python scripts/ci/run_type_check.py
python scripts/ci/check_documentation.py --check-generated
```

- [ ] **Step 3: Run the approved isolated discovery-to-publish workflow, inspect the diff, commit, and push**

Use the current safe validation profile without publication side effects. Run `git diff --check`, inspect the staged diff for scope/secrets, commit the scoped files, push the current branch, and report the branch, commit SHA, and PR state.

The isolated run on 2026-09-02 terminated correctly at admission with
`ingest_cohort_insufficient_eligible_reports`: all 152 discovered candidates
had insufficient extracted content. No source was admitted, so downstream
generation and publication readiness could not run. This external source-input
blocker does not alter the deterministic validation results above.
