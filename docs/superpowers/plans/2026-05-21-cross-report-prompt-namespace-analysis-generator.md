# Cross-Report Prompt Namespace And Analysis Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the cross-report synthesis prompt namespace, service-bound analysis generator, and deterministic validation gate from projected evidence inputs.

**Architecture:** Keep all external I/O inside existing services: `prompt_service` renders prompts and `llm_service` performs model calls. Keep synthesis and deterministic validation inside `src/generators/cross_report_analysis_generator.py`, using existing cross-report dataclass contracts and the input-generator outputs.

**Tech Stack:** Python dataclasses, YAML prompts, existing prompt dry-run fixtures, existing OpenAI JSON prompt contracts, pytest, schema snapshot and architecture gates.

---

### Task 1: Prompt Namespace

**Files:**
- Create: `src/prompts/cross_report_analysis/synthesis/system.yaml`
- Create: `src/prompts/cross_report_analysis/synthesis/user.yaml`
- Modify: `src/prompts/_dry_run_fixtures.yaml`
- Modify: `README.md`
- Modify: `crossreport.md`
- Test: `tests/test_cross_report_prompt_namespace.py`

- [ ] **Step 1: Write the failing test**

```python
def test_cross_report_synthesis_prompt_namespace_dry_run_logs_hashes(caplog):
    response = validate_prompt_dry_run(
        PromptDryRunRequest(
            schema_version="1.0",
            namespaces=["cross_report_analysis/synthesis"],
            force_reload=True,
        ),
        run_context,
    )
    assert response.results[0].namespace == "cross_report_analysis/synthesis"
    assert "selected_sources_json" in response.results[0].rendered_user_prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cross_report_prompt_namespace.py -q`

- [ ] **Step 3: Add prompt YAML and dry-run fixture**

Create prompt templates that accept bounded JSON strings for request, theme, selected sources, signal scores, evidence groups, evidence references, raw metrics, and generation policy.

- [ ] **Step 4: Run prompt dry-run and regression checks**

Run:
`pytest tests/test_cross_report_prompt_namespace.py -q`
`python -m src.services.prompt_service` is not used; use `validate_prompt_dry_run` through tests and `scripts/ci/check_prompt_fixture_regression.py`.

- [ ] **Step 5: Commit and PR**

Commit only prompt namespace files, fixture, docs, and tests.

### Task 2: Synthesis Generator

**Files:**
- Create: `src/generators/cross_report_analysis_generator.py`
- Modify: `README.md`
- Modify: `crossreport.md`
- Test: `tests/test_cross_report_analysis_generator.py`

- [ ] **Step 1: Write failing positive-path generator test**

Use fake prompt and LLM service boundaries, assert prompt namespace/hash logging, complete `CrossReportGeneratedAnalysisResult`, and evidence-mapped sections.

- [ ] **Step 2: Implement generator**

Load/render prompts via `prepare_prompt_bundle`, call `openai_chat_json`, normalize model JSON into contract sections, validate required evidence IDs, and log raw response plus post-processed output.

- [ ] **Step 3: Add negative-path tests**

Assert non-retryable `AppError` for missing JSON, empty sections, and unknown evidence references.

- [ ] **Step 4: Run live feature smoke**

Build real projected SQLite inputs, render the real prompt namespace, call the generator with a deterministic fake service-bound LLM response, and verify the output contract and logs.

- [ ] **Step 5: Commit and PR**

Commit only generator, docs, backlog cleanup, and tests.

### Task 3: Deterministic Artifact Validation

**Files:**
- Modify: `src/generators/cross_report_analysis_generator.py`
- Modify: `README.md`
- Modify: `crossreport.md`
- Test: `tests/test_cross_report_analysis_generator.py`

- [ ] **Step 1: Write failing validation tests**

Cover valid generated artifacts, missing evidence, unknown evidence IDs, empty required sections, and forbidden metric-normalization language.

- [ ] **Step 2: Implement deterministic validation**

Return `CrossReportValidationResult` with checked evidence IDs, missing evidence IDs, metric normalization violations, prompt budget chars, pass/fail status, and structured logs.

- [ ] **Step 3: Run live validation smoke**

Run the generated artifact through the validator with real prompt/evidence inputs and confirm pass/fail behavior.

- [ ] **Step 4: Commit and PR**

Commit only validation code, docs, backlog cleanup, and tests.
