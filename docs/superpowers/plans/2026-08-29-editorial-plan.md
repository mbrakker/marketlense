# Editorial Plan Implementation Plan

> **For agentic workers:** Execute this plan task-by-task with test-first changes and review each completed task.

**Goal:** Create one grounded editorial plan per report and use it as the common thematic basis for the summary, final insights, and expert comment.

**Architecture:** The existing artifact generator remains the owner of public-artifact sequencing. Add `report_vs/artifacts/editorial_plan` as a retained prompt family that is generated after DocMap/evidence packs and before public copy; retain the plan in `artifacts.json`. Pass its JSON to the three affected prompt families, and make deterministic final-insight selection consume its ordered themes instead of independently deriving theme coverage from DocMap.

**Tech Stack:** Python dataclasses/normalizers, JSON Schema, existing structured-output prompts, existing prompt-family materialization and artifact cache proofs, pytest.

## Global Constraints

- Keep the contract limited to `report_thesis` and ordered `themes` of `theme`, `priority`, and `evidence_ids`.
- Each referenced evidence ID must resolve in retained evidence packs or DocMap.
- Do not modify chart or table selection/rendering logic.
- Prompt or editorial-plan input changes must invalidate only the relevant retained families.

---

### Task 1: Specify and validate the editorial-plan contract

**Files:**

- Modify: `src/schemas/artifacts.schema.json`
- Modify: `src/generators/artifact_normalization.py`
- Test: `tests/_test_artifact_generator/cases_06_editorial_plan.py`

- [ ] Write a failing schema/unit test for one ordered thesis/themes plan and a plan containing an unknown evidence ID.
- [ ] Run the test and confirm it fails because `editorial_plan` is absent from the artifact contract.
- [ ] Add the minimal contract and normalization/validation that rejects blank thesis/theme/evidence IDs, duplicate themes, non-positive priorities, and unresolved evidence IDs.
- [ ] Run the focused test and confirm it passes.

### Task 2: Generate, retain, and reuse the plan before public artifacts

**Files:**

- Create: `src/prompts/report_vs/artifacts/editorial_plan/system.yaml`
- Create: `src/prompts/report_vs/artifacts/editorial_plan/user.yaml`
- Modify: `src/generators/_artifact_generator/generation.py`
- Modify: `src/generators/_artifact_generator/storage.py`
- Test: `tests/_test_artifact_generator/cases_06_editorial_plan.py`

- [ ] Write a failing generation test that expects exactly one editorial-plan prompt-family call and retained plan payload.
- [ ] Run the focused test and confirm it fails because the route is not registered.
- [ ] Register the family in existing prompt-family reuse/cache metadata, generate it before summary/candidates/quotes, and persist its normalized output in the assembled artifact payload.
- [ ] Run the focused test and confirm it passes.

### Task 3: Consume one plan across summary, insights, and expert synthesis

**Files:**

- Modify: `src/generators/_artifact_generator/generation.py`
- Modify: `src/generators/artifact_normalization.py`
- Modify: `src/generators/report_regeneration_generator.py`
- Modify: `src/prompts/report_vs/artifacts/{summary,insights_candidates,insights_final,expert_comment}/user.yaml`
- Test: `tests/_test_artifact_generator/cases_06_editorial_plan.py`

- [ ] Write a failing integration test that captures prompt variables and verifies all three public families receive byte-equivalent editorial-plan JSON, and final insights follow its priority/evidence order.
- [ ] Run the focused test and confirm it fails because those variables are not supplied.
- [ ] Supply the same serialized plan to summary, final insight selection, and expert synthesis; use plan evidence IDs/priority for deterministic final-insight filtering, including regeneration.
- [ ] Run the focused test and confirm it passes.

### Task 4: Prove cache behavior and document current workflow

**Files:**

- Modify: `tests/_test_artifact_generator/cases_03_artifact_cache_isolated_by_retrieval.py`
- Modify: `docs/workflows/report-processing.md`
- Test: `tests/_test_artifact_generator/cases_06_editorial_plan.py`

- [ ] Write a failing cache test proving a changed editorial-plan prompt/input prevents its own reuse and causes dependent summary/final-insight/expert families to regenerate.
- [ ] Run the focused test and confirm it fails because the editorial plan is not part of identity proofs.
- [ ] Extend existing cache metadata and explain the one-plan workflow/reuse semantics in the canonical report-processing document.
- [ ] Run artifact-generator and report-generation suites, then a bounded real report through the safe validation profile; inspect plan/thesis alignment and textual non-duplication before commit/push.
