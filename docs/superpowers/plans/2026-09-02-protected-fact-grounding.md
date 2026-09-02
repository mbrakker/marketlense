# Protected Fact Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require semantic grounding to compare the material factual dimensions of every factual claim against its linked evidence without inventing absent dimensions.

**Architecture:** Add a small, domain-neutral protected-fact contract that defines the fixed dimensions and compatible/incompatible/unknown states. Grounding’s structured output will return one check per material factual claim; the generator will treat incompatible checks as existing hard grounding failures, while allowing compatible creative paraphrases. The contract carries literal values supplied by the semantic evaluator and never derives a missing value.

**Tech Stack:** Python dataclasses, JSON Schema, YAML prompts, pytest.

## Global Constraints

- Preserve the existing public-readiness and grounding hard-failure decision paths.
- Do not add publisher- or metric-specific definitions, regex catalogs, or inferred values.
- Keep the existing deterministic grounding prompt configuration and structured-output recovery flow.

---

### Task 1: Define and test the reusable protected-fact contract

**Files:**
- Create: `src/contracts/protected_facts.py`
- Test: `tests/contracts/test_protected_facts.py`

**Interfaces:**
- Produces: `PROTECTED_FACT_DIMENSIONS`, `ProtectedFactDimension`, and `ProtectedFactComparison` for domain-neutral dimension comparison.

- [x] **Step 1: Write failing contract tests**

```python
def test_comparison_keeps_missing_dimension_unknown() -> None:
    comparison = ProtectedFactComparison.from_payload({"value": "52%"})
    assert comparison.dimension("timeframe").status == "unknown"

def test_comparison_rejects_mismatched_scope() -> None:
    comparison = ProtectedFactComparison.from_payload({
        "population": {"claim": "companies", "evidence": "respondents", "status": "incompatible"}
    })
    assert comparison.incompatible_dimensions == ("population",)
```

- [x] **Step 2: Run the focused test and observe missing-contract failure**

Run: `python -m pytest -q tests/contracts/test_protected_facts.py`

- [x] **Step 3: Implement literal-only contract normalization**

Create immutable dataclasses that accept only named dimensions and preserve null values as `unknown`; do not parse or infer facts.

- [x] **Step 4: Rerun the focused contract test**

Run: `python -m pytest -q tests/contracts/test_protected_facts.py`

### Task 2: Make structured grounding consume the contract

**Files:**
- Modify: `src/schemas/grounding_validation_output.schema.json`
- Modify: `src/prompts/report_vs/validate/grounding/system.yaml`
- Modify: `src/prompts/report_vs/validate/grounding/user.yaml`
- Modify: `src/generators/validation/grounding.py`
- Test: `tests/test_grounding_protected_facts.py`

**Interfaces:**
- Consumes: a `checks` entry for every material factual claim, carrying the contract dimension payload and an entailment outcome.
- Produces: the unchanged grounding issue type and severity, with incompatible dimensions mapped to the existing `contradicted` hard failure.

- [x] **Step 1: Write failing grounding behavior tests**

```python
def test_grounding_accepts_compatible_creative_paraphrase() -> None:
    assert _grounding_issues(_check("entailed", compatible=True)) == []

def test_grounding_blocks_each_incompatible_protected_dimension(dimension: str) -> None:
    issue = _grounding_issues(_check("contradicted", incompatible=dimension))[0]
    assert issue.severity == "error"
    assert "contradicted" in issue.message
```

- [x] **Step 2: Run the focused test and observe schema/behavior failure**

Run: `python -m pytest -q tests/test_grounding_protected_facts.py`

- [x] **Step 3: Require factual checks and map incompatible comparisons**

Require one check per material factual claim in prompt output, including all named dimensions as literal claim/evidence values or `null`, and a compatible/incompatible/unknown status. Keep `unsupported` as the backward-compatible issue list; append a hard contradiction issue when any check is incompatible.

- [x] **Step 4: Rerun focused grounding tests**

Run: `python -m pytest -q tests/test_grounding_protected_facts.py tests/test_grounding_semantic_outcomes.py`

### Task 3: Document and validate the gate

**Files:**
- Modify: `docs/workflows/validation-and-regeneration.md`
- Modify: `docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json` only when intentional fixture-cost output requires it

- [x] **Step 1: Document the literal-only protected dimensions and existing hard-failure behavior**

- [x] **Step 2: Run focused unit, semantic/grounding, prompt-fixture, lint/static, and relevant regression checks**

```powershell
python -m pytest -q tests/contracts/test_protected_facts.py tests/test_grounding_protected_facts.py tests/test_grounding_semantic_outcomes.py tests/test_prompt_dry_run_validation.py tests/test_claim_validation_generator.py tests/test_publish_readiness_gate.py
python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3
python scripts/ci/check_ruff_lint.py
python scripts/ci/run_type_check.py
python scripts/ci/check_documentation.py --check-generated
```

- [x] **Step 3: Review the diff, run the safe discovery-to-publish validation workflow, then commit and push**

Use the documented isolated validation profile. Do not publish or perform uncontrolled external writes.
