# DocMap-Guided Findings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make findings extraction use the generated DocMap to cover supported major sections while retaining evidence IDs and grounding.

**Architecture:** `generate_evidence_packs` already generates and validates `doc_map` before the remaining evidence packs. Pass a compact, JSON-serialized list of DocMap section identifiers, titles, summaries, key points, and pages only to the existing findings prompt; retain the existing single findings model call and all other pack parallelism. Expand only the findings contract/normalizer with optional section linkage fields, so older retained packs remain valid.

**Tech Stack:** Python 3.12, dataclass contracts, JSON Schema, Jinja prompt rendering, pytest.

## Global Constraints

- Preserve evidence grounding, finding IDs, the existing structured-output recovery, cache/materialization behavior, and evidence-pack storage.
- Do not alter chart or table generation logic.
- Do not add an orchestration layer or additional model calls for narrow reports.
- Document the current Docpack behavior under `docs/docpacks/`.

---

### Task 1: Test the section-guided findings contract

**Files:**
- Modify: `tests/_test_evidence_pack_generator/_shared.py`
- Modify: `tests/_test_evidence_pack_generator/cases_01_success.py`
- Modify: `tests/test_schema_validator.py`

**Interfaces:**
- Consumes: `generate_evidence_packs(..., openai_client, prompt_client, analysis_store)`.
- Produces: a findings payload whose entries retain `id`, `text`, `evidence`, and optional `section_id`, `section_title`.

- [ ] **Step 1: Write the failing test**

```python
def test_generate_evidence_packs_passes_doc_map_sections_to_findings_and_retains_links(tmp_path):
    prompt_client = RecordingPromptClient()
    packs = generate_evidence_packs(
        report_id="r1", report_name="report", vector_store_id="vs_1",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        openai_client=RoutedOpenAIClient({"doc_map": two_section_doc_map(), "findings": linked_findings()}),
        prompt_client=prompt_client, analysis_store=FakeAnalysisStore(),
    )
    assert json.loads(prompt_client.findings_variables["doc_map_sections_json"])[1]["id"] == "outlook"
    assert packs["findings"]["findings"][1]["section_id"] == "outlook"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_evidence_pack_generator.py -k doc_map_sections_to_findings`

Expected: FAIL because the findings render has no `doc_map_sections_json` variable and section links are discarded.

- [ ] **Step 3: Write the minimal implementation**

```python
def _findings_prompt_variables(doc_map: dict[str, object]) -> dict[str, str]:
    return {"doc_map_sections_json": json.dumps(_major_doc_map_sections(doc_map), sort_keys=True)}
```

Call the existing `_generate_pack` for `findings` with those user variables after DocMap validation, add optional `section_id` and `section_title` to its schema and normalizer, and leave all other packs unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_evidence_pack_generator.py -k "doc_map_sections_to_findings or legacy_findings_shape" tests/test_schema_validator.py -k findings`

Expected: PASS; evidence IDs and evidence text remain unchanged.

### Task 2: Document and validate the changed report behavior

**Files:**
- Modify: `src/prompts/report_vs/evidence_packs/findings/system.yaml`
- Modify: `src/prompts/report_vs/evidence_packs/findings/user.yaml`
- Modify: `docs/docpacks/pack-specs.md`
- Modify: `docs/docpacks/prompt-authoring.md`

**Interfaces:**
- Consumes: `doc_map_sections_json` rendered by the findings prompt.
- Produces: one concise, evidence-grounded findings pack which may contain findings from multiple major DocMap sections.

- [ ] **Step 1: Update prompt and schema-aligned documentation**

```yaml
DocMap major sections (planning context only; retrieve support from file_search):
{{ doc_map_sections_json }}
```

Instruct the extractor to prefer distinct supported sections without padding sparse reports, echo section IDs/titles only from the supplied map, and preserve file-search grounding.

- [ ] **Step 2: Run focused and suite-level checks**

Run: `python -m pytest -q tests/test_evidence_pack_generator.py tests/test_schema_validator.py tests/test_prompt_service.py tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py`

Expected: PASS.

- [ ] **Step 3: Run bounded real-report validations**

Run the existing safe report-generation validation profile for one broad retained report and one narrow retained report. Confirm the broad findings payload contains linked findings from multiple DocMap sections, and the narrow payload remains concise without more findings provider calls than the baseline one-pack flow.

- [ ] **Step 4: Completion gate and commit**

Run the relevant report-generation suite and final diff/secret review. Commit the isolated change with a clear message and push the current branch.
