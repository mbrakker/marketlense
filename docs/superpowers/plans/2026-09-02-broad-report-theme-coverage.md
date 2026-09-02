# Broad Report Theme Coverage Implementation Plan

> **For agentic workers:** Execute the focused test cycle before production edits.

**Goal:** Keep the existing single editorial-plan call and insight-count bounds while preventing very broad reports from concentrating public evidence in one source-section cluster.

**Architecture:** The existing DocMap, section-linked findings, and editorial plan remain the only inputs. A deterministic normalizer will identify a broad, materially sectioned report only when several supported section-linked findings exist across its early, middle, and late source areas; it will retain the editorial plan unless its selected themes are materially clustered, then replace only lowest-priority redundant coverage with supported, unrepresented major-section evidence. No new model request, schema field, or planning family is introduced.

**Tech Stack:** Python, existing artifact generator, YAML prompt resources, pytest.

## Global Constraints

- Preserve the existing two-to-seven editorial-plan and final-insight bounds.
- Preserve exactly one editorial-plan model request and the current artifact-family call count.
- Do not require a finding per chapter or add filler to narrow reports.
- Keep all replacement evidence IDs grounded in the existing findings pack and section links.

### Task 1: Specify broad-plan repair with synthetic evidence

**Files:**

- Modify: `tests/_test_artifact_generator/cases_05_docmap_insight_selection.py`

- [ ] Add a broad fixture with seven source sections and section-linked early, middle, and late findings; model-plan themes deliberately cluster in early sections.
- [ ] Assert plan normalization retains five themes, includes early/middle/late evidence, and does not change a two-theme narrow plan.
- [ ] Run `python -m pytest -q tests/test_artifact_generator.py -k "broad_plan or narrow_plan"` and confirm the new broad assertion fails before implementation.

### Task 2: Normalize clustered plans deterministically

**Files:**

- Modify: `src/generators/artifact_normalization.py`
- Modify: `src/generators/_artifact_generator/generation.py`
- Modify: `src/generators/report_regeneration_generator.py`

- [ ] Build the material-section/evidence mapping from existing DocMap and findings data.
- [ ] Repair only a detected broad-plan cluster by retaining nonredundant planned themes and replacing redundant lowest-priority themes with evidence-backed unrepresented major sections across source bands.
- [ ] Apply the same normalization at generation and targeted insight regeneration, retaining the one-call plan family and existing selectors.
- [ ] Re-run the focused tests and confirm they pass.

### Task 3: Improve plan instructions and document behavior

**Files:**

- Modify: `src/prompts/report_vs/artifacts/editorial_plan/user.yaml`
- Modify: `docs/workflows/report-processing.md`

- [ ] Tell the existing plan call how to recognize broad reports and to use early/middle/late signals only when they are materially distinct; expressly forbid chapter quotas and padding.
- [ ] Document deterministic fallback only for an over-clustered broad plan with supported unrepresented major sections.

### Task 4: Validate and hand off

- [ ] Run artifact/editorial-plan/prompt tests, prompt fixture regression, relevant public-quality tests, `git diff --check`, and a safe replay/coverage comparison for Outlook 2019, full Outlook 2025, Activate 2026, and Social Video.
- [ ] Inspect the final diff and call-count telemetry. Commit and push only if Outlook 2019 gains earlier-and-later coverage without increasing output count or model calls and the three comparison reports do not regress.
