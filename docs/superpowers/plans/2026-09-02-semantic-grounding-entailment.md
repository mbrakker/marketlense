# Semantic Grounding Entailment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `report_vs/validate/grounding` accept materially entailed paraphrases while continuing to block unsupported and contradicted factual claims.

**Architecture:** The existing grounding prompt remains the report- and publisher-agnostic semantic decision boundary. It receives only retained artifact/evidence text, returns the existing `unsupported` failure list, and maps `contradicted` and factual `not_established` results to the existing hard validation failures. The model routing and fixed deterministic prompt fixture remain unchanged.

**Tech Stack:** Python, YAML prompt resources, JSON Schema, pytest.

## Global Constraints

- Use retained evidence only; add no publisher- or report-specific exception.
- Preserve existing release-blocking severities and output protocol compatibility.
- Keep the validation prompt’s fixed deterministic fixture configuration (`temperature: 0.0`).
- Add positive paraphrase and adversarial semantic-scope coverage before production changes.

---

### Task 1: Specify semantic grounding decisions

**Files:**
- Modify: `src/prompts/report_vs/validate/grounding/system.yaml`
- Modify: `src/prompts/report_vs/validate/grounding/user.yaml`
- Modify: `src/schemas/grounding_validation_output.schema.json`
- Test: `tests/test_prompt_dry_run_validation.py`

**Interfaces:**
- Consumes: retained `report_json` and `evidence_json` prompt variables.
- Produces: the existing `unsupported` list, with an optional `entailment_outcome` of `contradicted` or `not_established` for a failed entry.

- [x] **Step 1: Write the failing prompt-contract tests**

```python
def test_grounding_prompt_accepts_semantic_paraphrase_without_scope_change() -> None:
    prompt = _render_grounding_prompt()
    assert "synonyms" in prompt
    assert "active/passive" in prompt
    assert "canonical" in prompt

def test_grounding_prompt_rejects_material_scope_changes() -> None:
    prompt = _render_grounding_prompt()
    for dimension in ("timeframe", "causality", "attribution"):
        assert dimension in prompt
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest -q tests/test_prompt_dry_run_validation.py -k grounding`

Expected: FAIL because the current prompt does not define semantic-entailment decisions.

- [x] **Step 3: Add the smallest compatible prompt/schema change**

```yaml
# Prompt decision rule
# entailed: material meaning follows from linked retained evidence
# contradicted: linked evidence conflicts with the claim
# not_established: linked evidence does not establish the factual claim
```

Add `entailment_outcome` as an optional string field in the existing unsupported-entry schema. Keep successful `entailed` sentences omitted from `unsupported` and retain the existing fields.

- [x] **Step 4: Run prompt-contract tests to verify they pass**

Run: `python -m pytest -q tests/test_prompt_dry_run_validation.py -k grounding`

Expected: PASS.

### Task 2: Preserve hard-failure mapping and validate adversarial outcomes

**Files:**
- Modify: `src/generators/validation/grounding.py`
- Test: `tests/_test_validation_generator/cases_01_validation_flags_metric_and_quote.py`

**Interfaces:**
- Consumes: a schema-valid grounding unsupported entry with optional `entailment_outcome`.
- Produces: existing `ValidationIssue` severities and violation types.

- [x] **Step 1: Write failing outcome tests**

```python
def test_contradicted_outcome_is_a_hard_grounding_failure() -> None:
    issues = _run_grounding_with_outcome("contradicted")
    assert issues[0].severity == "error"
    assert "|contradicted]" in issues[0].message

def test_factual_not_established_outcome_is_an_existing_hard_failure() -> None:
    issues = _run_grounding_with_outcome("not_established")
    assert issues[0].severity == "error"
    assert "|unsupported_factual_claim]" in issues[0].message
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest -q tests/test_validation_generator.py -k grounding_semantic_outcome_preserves_hard_failure`

Expected: FAIL because `entailment_outcome` is not currently interpreted.

- [x] **Step 3: Map semantic outcomes without changing release policy**

```python
if outcome == "contradicted":
    violation_type = "contradicted"
elif outcome == "not_established" and classification == "factual_claim":
    violation_type = "unsupported_factual_claim"
```

Leave existing explicit violation types authoritative only when they are consistent with the model outcome; do not downgrade unsupported factual claims or contradictions.

- [x] **Step 4: Run the outcome tests to verify they pass**

Run: `python -m pytest -q tests/test_validation_generator.py -k grounding_semantic_outcome_preserves_hard_failure`

Expected: PASS.

### Task 3: Document and verify the changed validator contract

**Files:**
- Modify: `docs/workflows/validation-and-regeneration.md`
- Modify: `docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json` only if the intentional prompt-token delta requires an approved baseline update.
- Test: `tests/test_documentation_validation.py`

**Interfaces:**
- Consumes: validation workflow and prompt fixture baseline.
- Produces: current documentation of entailment-based grounding and a validated dry-run fixture budget.

- [x] **Step 1: Add the focused documentation coverage**

```python
def test_documentation_validation() -> None:
    assert check_documentation() == []
```

- [x] **Step 2: Run the documentation gate**

Run: `python -m pytest -q tests/test_documentation_validation.py`

Expected: PASS after the canonical workflow document is updated.

- [x] **Step 3: Update the canonical workflow text and fixture baseline as required**

Document that grounding accepts semantic paraphrase but blocks changed material proposition, quantities, scope, certainty, causality, and provenance. Do not describe the model as a release-policy bypass.

- [x] **Step 4: Run focused and static verification**

Run:

```powershell
python -m pytest -q tests/test_validation_generator.py tests/test_prompt_dry_run_validation.py tests/test_claim_validation_generator.py tests/test_llm_routing_policy.py tests/test_documentation_validation.py
python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3
python scripts/ci/check_ruff_lint.py
python scripts/ci/run_type_check.py
python scripts/ci/check_documentation.py --check-generated
```

Expected: all commands exit 0.

- [ ] **Step 5: Review, commit, push, and update the PR**

Run `git diff --check`, inspect `git diff --cached`, commit only the scoped files, push the current branch, and update the existing PR with the tested paraphrase and adversarial cases.
