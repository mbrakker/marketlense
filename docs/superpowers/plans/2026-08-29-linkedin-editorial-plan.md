# LinkedIn Editorial Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing LinkedIn artifact use the persisted editorial plan as its primary thematic authority while keeping it concise, source-grounded, and compatible with the existing artifact/reuse lifecycle.

**Architecture:** Retain the current eight-family artifact workflow and its two concurrent distribution calls. Add the already-generated normalized editorial-plan JSON to the LinkedIn initial and regeneration prompt variables; because per-family reuse identity hashes rendered variables, a changed plan will invalidate only that family without a new model stage. Express editorial and formatting requirements in the primary and repair prompt resources, keeping grounding validation and artifact schemas unchanged.

**Tech Stack:** Python, pytest, YAML prompt resources, existing structured-output/prompt-family reuse services.

## Global Constraints

- Do not add an LLM stage, post-generation rewrite, publish gate, dependency, or chart/table behavior change.
- Preserve the existing hard platform-safe maximum above the 180–280-word target and all grounding/evidence validation.
- The editorial plan is the primary thematic authority; final insights and metric spine are supporting evidence; Executive Summary is secondary context only.
- Broad reports select and explicitly frame one representative report-backed angle; narrow reports may express the overall thesis.
- Normal posts use at most four quantitative proof points, 0–3 relevant hashtags, no engagement bait, and no listed boilerplate phrases.
- Construct multiline bullets so every bullet is a complete line, a bullet block is surrounded by blank lines, and prose never follows on a bullet line.
- Preserve the user-owned untracked `docs/quality/p6-editorial-acceptance.md` and `src/config/app.p6_editorial_acceptance_batch_01.yaml` unchanged.

---

### Task 1: Extend the LinkedIn generation inputs and reuse identity

**Files:**
- Modify: `tests/_test_artifact_generator/cases_06_editorial_plan.py:65-118`
- Modify: `src/generators/_artifact_generator/generation.py:760-783`

**Interfaces:**
- Consumes: normalized `editorial_plan: dict[str, Any]` and its existing deterministic `editorial_plan_json: str`.
- Produces: `ArtifactRenderTask(namespace="report_vs/artifacts/linkedin_post").variables["editorial_plan_json"]` containing the exact normalized plan.
- Reuse contract: `resolve_or_render_family()` hashes the task variables in `relevant_input_hash`, so this field must remain in the LinkedIn task variables rather than being hidden outside prompt rendering.

- [ ] **Step 1: Write the failing initial-generation contract test**

  Extend the existing shared-basis test with the LinkedIn namespace and preserve the independent literal assertion:

  ```python
  for namespace in (
      "report_vs/artifacts/summary",
      "report_vs/artifacts/insights_final",
      "report_vs/artifacts/expert_comment",
      "report_vs/artifacts/linkedin_post",
  ):
      assert json.loads(
          prompt_client.variables_for_namespace(namespace)["editorial_plan_json"]
      ) == plan
  ```

  The production change this catches is removing the plan from the LinkedIn render task while leaving the other editorial families intact.

- [ ] **Step 2: Run the focused test to verify the expected failure**

  Run: `python -m pytest -q tests/test_artifact_generator.py -k shared_basis`

  Expected: FAIL with `KeyError: 'editorial_plan_json'` for `report_vs/artifacts/linkedin_post`.

- [ ] **Step 3: Add the existing serialized plan to the LinkedIn variables**

  Change only the existing variable mapping:

  ```python
  linkedin_vars = {
      "editorial_plan_json": editorial_plan_json,
      "summary_json": _dump_json(summary),
      "insights_final_json": _dump_json(insights_final),
      "metric_spine_json": metric_spine_json,
  }
  ```

  Do not change the task list, executor, namespace, schema, or call count.

- [ ] **Step 4: Run the focused test to verify it passes**

  Run: `python -m pytest -q tests/test_artifact_generator.py -k shared_basis`

  Expected: PASS.

- [ ] **Step 5: Commit the isolated wiring change**

  ```powershell
  git add tests/_test_artifact_generator/cases_06_editorial_plan.py src/generators/_artifact_generator/generation.py
  git commit -m "feat: pass editorial plan to linkedin artifacts"
  ```

### Task 2: Carry the plan through validation-driven LinkedIn regeneration

**Files:**
- Modify: `tests/test_report_regeneration_generator.py` (add to the existing LinkedIn-regeneration coverage)
- Modify: `src/generators/report_regeneration_generator.py:810-834`
- Modify: `src/prompts/report_vs/artifacts/regenerate/linkedin_post/user.yaml`
- Modify: `src/prompts/report_vs/artifacts/regenerate/linkedin_post/system.yaml`

**Interfaces:**
- Consumes: `execution.state.editorial_plan`, normalized during `_state_from_artifacts()`.
- Produces: regeneration variables with `editorial_plan_json: _dump_json(execution.state.editorial_plan)`.
- Preserves: the same repair namespace, one bounded repair call, supplied grounding package, and post-repair reference-ID stripping.

- [ ] **Step 1: Write the failing regeneration-variable test**

  Add a real regeneration-handler test using the repository’s existing injected prompt client and a literal plan. Assert the captured rendered variables, not a mock call count:

  ```python
  assert json.loads(
      prompt_client.variables_for_namespace(
          "report_vs/artifacts/regenerate/linkedin_post"
      )["editorial_plan_json"]
  ) == {
      "report_thesis": "Retention efficiency is replacing broad expansion.",
      "themes": [
          {"theme": "Retention", "priority": 1, "evidence_ids": ["f3"]},
          {"theme": "Margin", "priority": 2, "evidence_ids": ["f2"]},
      ],
  }
  ```

  The production change this catches is a repair prompt that regresses to summary-led framing after an otherwise correct initial generation.

- [ ] **Step 2: Run the focused test to verify the expected failure**

  Run: `python -m pytest -q tests/test_report_regeneration_generator.py -k linkedin_editorial_plan`

  Expected: FAIL because the regeneration variables contain no `editorial_plan_json` key.

- [ ] **Step 3: Add the serialized normalized plan to the existing repair variables**

  Add exactly one variable before the existing summary input:

  ```python
  "editorial_plan_json": _dump_json(execution.state.editorial_plan),
  ```

  Add the matching prompt context line and state that the plan selects the report angle; do not add another repair route.

- [ ] **Step 4: Run the focused test to verify it passes**

  Run: `python -m pytest -q tests/test_report_regeneration_generator.py -k linkedin_editorial_plan`

  Expected: PASS.

- [ ] **Step 5: Commit the regeneration parity change**

  ```powershell
  git add tests/test_report_regeneration_generator.py src/generators/report_regeneration_generator.py src/prompts/report_vs/artifacts/regenerate/linkedin_post
  git commit -m "fix: retain editorial plan during linkedin regeneration"
  ```

### Task 3: Replace the LinkedIn prompt contract and add deterministic prompt-fixture checks

**Files:**
- Modify: `src/prompts/report_vs/artifacts/linkedin_post/user.yaml`
- Modify: `src/prompts/report_vs/artifacts/linkedin_post/system.yaml`
- Modify: `src/prompts/report_vs/artifacts/regenerate/linkedin_post/user.yaml`
- Modify: `src/prompts/report_vs/artifacts/regenerate/linkedin_post/system.yaml`
- Modify: `src/prompts/_dry_run_fixtures.yaml:308-341,378-423`
- Modify: `tests/test_prompt_dry_run_validation.py` or its fixture-driven equivalent only if the current generic fixture validator cannot cover the new required variables
- Modify: `tests/test_prompt_fixture_corpus_regression.py` only if the rendered-corpus baseline changes under its documented workflow

**Interfaces:**
- Consumes: `editorial_plan_json`, `summary_json`, `insights_final_json`, `metric_spine_json`, and, for repair, the existing grounding package and failure checklist.
- Produces: valid JSON `{ "linkedin_post": "..." }`; no output-schema, validator, or model-routing change.
- Prompt behavior: source/publisher is named naturally near the opening when supplied; report breadth determines selected-angle versus whole-thesis framing from the plan/context, not a new heuristic in Python.

- [ ] **Step 1: Add failing dry-run fixture cases for broad and narrow inputs**

  Add two complete literal fixture contexts that include `editorial_plan_json`. The broad fixture must make the report-wide scope explicit and require a selected angle; the narrow fixture must permit the full thesis. Include a publisher in the DocMap/source context used by the prompt. Ensure fixture rendering fails before prompt changes because the LinkedIn prompt does not reference `editorial_plan_json`.

- [ ] **Step 2: Run prompt dry-run validation to verify the expected failure**

  Run: `python -m pytest -q tests/test_prompt_dry_run_validation.py -k linkedin`

  Expected: FAIL because the new required LinkedIn prompt input is not consumed by the primary prompt (or because the new fixture contract is incomplete).

- [ ] **Step 3: Encode the editorial contract in the primary and repair prompt resources**

  The primary prompt must include the following operational rules in its instructions, expressed as concise production copy:

  ```text
  Editorial plan JSON is the primary thematic authority. Select one central,
  source-supported insight, tension, or implication. For a broad report, say
  that the post examines one representative angle rather than summarising the
  entire report; for a narrow report, the post may express the full thesis.

  Target 180–280 words while retaining the existing hard 500-word limit.
  Use 2–4 quantitative proof points where available, never more than four
  unless the supplied artifacts explicitly make more necessary. Attribute the
  named publisher/source naturally near the beginning when it is known.

  Use a concrete opening, why-it-matters explanation, evidence, one distinct
  interpretation or decision implication, optional genuine closing question or
  implication, and zero to three relevant hashtags. Do not repeat Executive
  Summary wording or use the listed boilerplate or engagement bait.

  If bullets are used, surround the complete bullet block with blank lines,
  keep each bullet to one complete line, and never append prose to a bullet.
  ```

  The repair prompt must apply the same priorities and formatting rules while fixing only supplied validation failures. It must keep all claims limited to supplied artifacts and the grounding package.

- [ ] **Step 4: Run deterministic prompt validation and corpus regression**

  Run: `python -m pytest -q tests/test_prompt_service.py tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py`

  Expected: PASS. If the corpus baseline is intentionally changed, regenerate it only with its documented script and review the diff for unrelated prompt changes.

- [ ] **Step 5: Commit the prompt and fixture contract**

  ```powershell
  git add src/prompts/report_vs/artifacts/linkedin_post src/prompts/report_vs/artifacts/regenerate/linkedin_post src/prompts/_dry_run_fixtures.yaml tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py
  git commit -m "feat: ground linkedin posts in editorial plans"
  ```

### Task 4: Prove cache invalidation and post-formatting/content constraints

**Files:**
- Modify: `tests/_test_artifact_generator/cases_06_editorial_plan.py`
- Modify: `tests/test_report_regeneration_generator.py` only for repair-output formatting coverage if a deterministic normalizer already exists; otherwise do not add a new rewrite layer.

**Interfaces:**
- Consumes: `CapturingPromptClient`, `FakeOpenAI`, existing prompt-family reuse fixtures, and hand-authored LinkedIn output strings.
- Produces: evidence that a changed plan changes LinkedIn `relevant_input_hash`/cache decision and that the prompt contract is rendered with broad/narrow, numeric, boilerplate, and bullet constraints.

- [ ] **Step 1: Write failing identity-isolation and output-fixture tests**

  Add an initial-generation test that runs twice against retained compatible artifacts, changing only the plan’s thesis/theme, then asserts the LinkedIn family regenerates while unrelated compatible family reuse behavior is unchanged. Assert telemetry/output behavior rather than private hash implementation details.

  Add hand-authored fixture assertions for normal LinkedIn output. They must reject a fifth distinct numeric proof point, each prohibited boilerplate phrase, engagement bait, a generic opening, and a glued bullet such as:

  ```python
  malformed = "\n\n• Conversion: nearly 4x higher Welcome to the next point."
  assert is_well_formed_linkedin_post(malformed) is False
  ```

  Only introduce `is_well_formed_linkedin_post` if an existing deterministic public-editorial validation seam already owns LinkedIn structural checks; otherwise keep this as prompt-output fixture/corpus coverage and do not create a new publish gate.

- [ ] **Step 2: Run the focused tests to verify the expected failures**

  Run: `python -m pytest -q tests/test_artifact_generator.py -k 'linkedin and (reuse or editorial_plan)' tests/test_report_regeneration_generator.py -k linkedin`

  Expected: FAIL because the pre-change LinkedIn input identity is unaffected by the plan and the prior prompt contract permits the forbidden output shapes.

- [ ] **Step 3: Make only the minimal test-backed changes**

  Rely on Task 1’s `linkedin_vars["editorial_plan_json"]` for cache invalidation. If existing validation has an appropriate deterministic normalization seam, correct only newline construction there; otherwise make no production post-processor and keep multiline guarantees in the prompt contract plus its regression fixture. Do not count or rewrite generated numbers in Python, since that would introduce an unauthorized post-generation stage.

- [ ] **Step 4: Run focused artifact and regeneration suites**

  Run: `python -m pytest -q tests/test_artifact_generator.py tests/test_report_regeneration_generator.py`

  Expected: PASS.

- [ ] **Step 5: Commit the focused regression coverage**

  ```powershell
  git add tests/_test_artifact_generator/cases_06_editorial_plan.py tests/test_report_regeneration_generator.py
  git commit -m "test: cover linkedin editorial-plan regeneration"
  ```

### Task 5: Document and perform layered validation, then run the requested benchmark cohort

**Files:**
- Modify: `docs/workflows/report-processing.md` (the artifact-family paragraph describing editorial-plan consumers)
- Modify: `docs/product/editorial-output.md` (LinkedIn public-editorial output contract)
- Modify: `docs/quality/p6-editorial-acceptance.md` only if this untracked document is explicitly user-owned and its wording is intended to be part of this change; otherwise leave it untouched.

**Interfaces:**
- Documents: one existing LinkedIn family consumes the same persisted plan as summary, final insights, and expert view; no additional call or gate is introduced.
- Validates: prompt materialization, focused generator/regeneration behavior, report rendering, and safe discovery→acquisition→ingest→publish workflow.

- [ ] **Step 1: Update the canonical workflow and product documents**

  Add concise current-behavior text stating that LinkedIn uses the editorial plan to select one source-supported angle for broad reports, may cover a narrow report’s full thesis, treats final insights/metric spine as evidence, and retains current grounding/reuse safeguards. Do not describe unimplemented phrase detection as an enforced gate.

- [ ] **Step 2: Run all deterministic relevant suites**

  Run:

  ```powershell
  python -m pytest -q tests/test_artifact_generator.py tests/test_report_regeneration_generator.py tests/test_prompt_service.py tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py tests/test_render_service_artifacts.py tests/test_render_service_public_prose.py
  python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3
  ```

  Expected: every command exits `0`; record exact pass/skip counts.

- [ ] **Step 3: Run the required safe end-to-end workflow**

  Use the repository’s approved isolated configuration/profile to execute discovery, acquisition, ingest, and publish in that order with normal non-publication safeguards. Record the exact commands, report IDs, terminal states, and any unavailable credential-dependent stages. Investigate any attributable error and rerun that stage plus downstream stages before closure.

- [ ] **Step 4: Regenerate and assess the five benchmark reports**

  Use the existing safe regeneration/fixture workflow for Omnisend 2023 Email/SMS/Push, Activate 2025 eCommerce, Activate Technology & Media Outlook 2026, IAB/PwC Internet Advertising Revenue Report 2024, and YouGov Attitudes to AI in Media 2025. For each post, compare all material claims/numbers against its source PDF and retain before/after excerpts. Confirm the specified report-specific angle/tension expectations, absence of malformed bullets, and materially distinct language. Use a bounded marked live run only if local fixtures cannot generate these outputs; record provider/model metadata and costs without secrets.

- [ ] **Step 5: Inspect, commit, and push only after all validations pass**

  ```powershell
  git diff --check
  git status --short
  git diff -- src/generators/_artifact_generator/generation.py src/generators/report_regeneration_generator.py src/prompts/report_vs/artifacts docs/workflows/report-processing.md docs/product/editorial-output.md tests
  git add src/generators/_artifact_generator/generation.py src/generators/report_regeneration_generator.py src/prompts/report_vs/artifacts src/prompts/_dry_run_fixtures.yaml tests docs/workflows/report-processing.md docs/product/editorial-output.md
  git commit -m "feat: improve source-grounded linkedin generation"
  git push
  ```

  Report changed files, exact results, each benchmark’s before/after example and source check, before/after model-call count (expected unchanged: one initial LinkedIn call; only existing bounded regeneration calls when validation requires them), commit SHA, push result, and residual unavailable live verification.

## Plan review

- Spec coverage: Tasks 1–2 provide initial/regeneration editorial-plan parity; Task 3 provides the native LinkedIn contract and broad/narrow framing; Task 4 covers input-sensitive reuse plus formatting/content regression; Task 5 covers required documentation, deterministic validation, safe end-to-end validation, benchmark comparison, commit, and push.
- Scope control: The plan does not create a model call, output schema, chart/table path, post-generation rewriter, or new publication gate.
- Known decision: Quantitative-count and phrase requirements are prompt constraints and fixture evidence unless the repository already has a fitting deterministic LinkedIn validation seam. The implementation must not add an independent editing/gating system merely to enforce stylistic rules.
