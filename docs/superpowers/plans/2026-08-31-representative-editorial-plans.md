# Representative Editorial Plans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing single Editorial Plan and DocMap-aware findings prompts preserve material, source-backed breadth and counterbalancing themes without changing the artifact pipeline.

**Architecture:** Change only the two existing prompt resources. The Editorial Plan remains the sole shared planning call and receives the existing DocMap plus evidence packs; the findings extractor remains the existing file-search call and receives the existing normalized DocMap-section context. Regression tests render and inspect those prompt resources and exercise the existing findings-context handoff with a synthetic counterbalanced DocMap.

**Tech Stack:** YAML prompts, Python, pytest, existing prompt service and evidence-pack generator.

## Global Constraints

- Do not redesign the artifact pipeline, add an LLM call, add a synthesis model, or create an evidence-pack family.
- Preserve the existing Editorial Plan JSON contract and its two-to-seven theme bound; do not pad narrow reports.
- Include counterbalancing themes only when distinct major source sections and file-search evidence materially support them.
- Preserve representative themes for Omnisend, IAB, Activate 2025, and broad coverage for Activate 2026.

---

### Task 1: Lock the representative-breadth prompt contract with failing tests

**Files:**

- Modify: `tests/test_prompt_service.py`
- Modify: `tests/_test_evidence_pack_generator/_shared.py`
- Modify: `tests/_test_evidence_pack_generator/cases_01_success.py`

**Interfaces:**

- Consumes: `load_prompt_set(PromptLoadRequest, RunContext)` and `generate_evidence_packs(..., prompt_client=RecordingPromptClient)`.
- Produces: regression evidence that the two prompt namespaces contain the breadth and counterbalance constraints, and that existing DocMap-to-findings context retains both material sides of a synthetic report.

- [ ] **Step 1: Write the failing prompt-contract tests**

```python
def test_editorial_plan_and_findings_prompts_require_representative_counterbalance() -> None:
    editorial_plan = load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace="report_vs/artifacts/editorial_plan", force_reload=True),
        _ctx(),
    )
    findings = load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace="report_vs/evidence_packs/findings", force_reload=True),
        _ctx(),
    )

    assert "DocMap is the authority for report breadth" in editorial_plan.user.text
    assert "counterbalancing" in editorial_plan.user.text
    assert "executive-summary" in editorial_plan.user.text
    assert "counterbalancing" in findings.user.text
```

```python
def test_findings_context_retains_counterbalancing_major_docmap_sections(tmp_path) -> None:
    prompt_client = RecordingPromptClient()
    generate_evidence_packs(..., prompt_client=prompt_client, ...)

    sections = json.loads(prompt_client.findings_variables["doc_map_sections_json"])
    assert [section["id"] for section in sections] == [
        "efficiency-value", "cost-savings", "trust-governance",
    ]
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `python -m pytest -q tests/test_prompt_service.py tests/test_evidence_pack_generator.py -k "representative_counterbalance or counterbalancing_major"`

Expected: FAIL because neither existing prompt contains the new representative/counterbalancing instructions and the synthetic fixture does not yet exist.

- [ ] **Step 3: Add the synthetic DocMap test fixture**

```python
def counterbalanced_doc_map(doc_id="d1"):
    return {
        **substantive_doc_map(doc_id),
        "sections": [
            {"id": "efficiency-value", "title": "Efficiency and value", ...},
            {"id": "cost-savings", "title": "Cost savings", ...},
            {"id": "trust-governance", "title": "Trust, risk, and governance", ...},
        ],
    }
```

- [ ] **Step 4: Re-run the focused tests to confirm the fixture assertion still fails only on the prompt contract**

Run: `python -m pytest -q tests/test_prompt_service.py tests/test_evidence_pack_generator.py -k "representative_counterbalance or counterbalancing_major"`

Expected: FAIL because the prompts have not yet been changed; the test demonstrates that the existing context transports all three source sections.

### Task 2: Strengthen the existing prompts minimally

**Files:**

- Modify: `src/prompts/report_vs/artifacts/editorial_plan/user.yaml`
- Modify: `src/prompts/report_vs/evidence_packs/findings/user.yaml`
- Modify: `docs/product/editorial-output.md`

**Interfaces:**

- Consumes: existing `doc_map_json`, `evidence_json`, and `doc_map_sections_json` template variables.
- Produces: unchanged Editorial Plan and findings schemas with explicit selection/retrieval priorities.

- [ ] **Step 1: Add the Editorial Plan selection instruction**

```yaml
  Treat the DocMap as the authority for report breadth. For a broad report,
  choose themes from materially different major DocMap areas rather than
  variants of one cluster. When the source materially supports both sides of a
  decision-relevant tension, retain both; do not let related themes from one
  side crowd out the other. Do not over-weight executive-summary or takeaway
  sections when deeper major sections contain distinct evidence. Do not invent
  balance or pad a narrow report.
```

- [ ] **Step 2: Add the DocMap-aware findings retrieval instruction**

```yaml
  When materially different or counterbalancing major DocMap sections exist,
  retrieve file_search evidence from both sides. Treat multiple subtopics from
  one side as insufficient coverage when another material side is supported.
  Do not manufacture a counterpoint or pad a narrow report.
```

- [ ] **Step 3: Update the canonical editorial-output documentation**

```markdown
Editorial planning treats the DocMap as the breadth authority. Broad reports
retain materially distinct major sections and source-backed counterbalances;
narrow reports are not artificially balanced. Findings retrieval follows the
same rule only where file-search evidence supports both sides.
```

- [ ] **Step 4: Run the focused tests to verify the change is green**

Run: `python -m pytest -q tests/test_prompt_service.py tests/test_evidence_pack_generator.py -k "representative_counterbalance or counterbalancing_major"`

Expected: PASS.

### Task 3: Run prompt, artifact, schema, and public-editorial regression checks

**Files:**

- Verify only: `src/prompts/_dry_run_fixtures.yaml`, schemas, and retained benchmark fixtures.

**Interfaces:**

- Consumes: existing CLI validators and fixture corpus baseline.
- Produces: recorded focused regression evidence and a prompt-corpus comparison.

- [ ] **Step 1: Validate prompt loading and fixture corpus behavior**

Run:

```powershell
python -m pytest -q tests/test_prompt_service.py tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py
python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3
```

Expected: PASS with the intended prompt dependency/hash changes accepted by the corpus regression policy.

- [ ] **Step 2: Validate generator contracts and public editorial quality**

Run:

```powershell
python -m pytest -q tests/test_artifact_generator.py tests/test_evidence_pack_generator.py
python -m pytest -q tests/test_schema_validator_service.py tests/test_public_editorial_quality_generator.py
python -m scripts.ci.check_public_report_quality --minimum-reports 15
```

Expected: PASS.

- [ ] **Step 3: Inspect the final diff and whitespace**

Run: `git diff --check`

Expected: no output and exit code 0.

### Task 4: Run the required fresh YouGov and five-report live regression

**Files:**

- Create: isolated validation evidence directories under `out/` and `state/` only.
- Verify only: the immediately previous P6 batch evidence and all new retained plans/findings.

**Interfaces:**

- Consumes: the existing P6 safe profile pattern, source PDF provenance, cache/reuse controls, and normal pipeline validation/publish safeguards.
- Produces: two fresh YouGov retained artifact sets and one isolated five-report replay with call-ledger comparison.

- [ ] **Step 1: Record baseline thematic coverage and LLM-call counts from the immediately previous P6 batch**

```powershell
python -m src._cli.pipeline --help
```

Then use the supported existing pipeline command with a fresh isolated profile to retain baseline and current run metadata; do not alter sources, reuse editorial artifacts, or enable external publication.

- [ ] **Step 2: Generate YouGov twice with retained evidence and cache/reuse bypassed**

For each isolated run, verify the saved Editorial Plan has at least one trust/risk/governance theme and one opportunity/benefit or generational-acceptance theme, and verify final findings retain the matching source-backed counterweight.

- [ ] **Step 3: Replay all five reports once through the normal safe workflow**

Verify Activate 2026 remains broad, Omnisend/IAB/Activate 2025 retain representative themes, and no report has a broad-report completeness regression relative to the immediately preceding benchmark.

- [ ] **Step 4: Compare model-call count and finalize only if every live assertion passes**

Verify the plan remains one Editorial Plan call and that per-pipeline LLM-call topology is unchanged. If either fresh YouGov run collapses to a single risk/trust cluster, stop without committing or pushing.

### Task 5: Commit and push only after the live gate passes

**Files:**

- Commit only the prompt, test, documentation, and plan files from this change; do not include pre-existing dirty files.

- [ ] **Step 1: Re-inspect status and staged diff for scope and secrets**

Run:

```powershell
git status --short
git diff --check
git diff -- src/prompts/report_vs/artifacts/editorial_plan/user.yaml src/prompts/report_vs/evidence_packs/findings/user.yaml tests/test_prompt_service.py tests/_test_evidence_pack_generator/_shared.py tests/_test_evidence_pack_generator/cases_01_success.py docs/product/editorial-output.md docs/superpowers/plans/2026-08-31-representative-editorial-plans.md
```

- [ ] **Step 2: Commit and push**

```powershell
git add src/prompts/report_vs/artifacts/editorial_plan/user.yaml src/prompts/report_vs/evidence_packs/findings/user.yaml tests/test_prompt_service.py tests/_test_evidence_pack_generator/_shared.py tests/_test_evidence_pack_generator/cases_01_success.py docs/product/editorial-output.md docs/superpowers/plans/2026-08-31-representative-editorial-plans.md
git commit -m "fix: stabilize representative editorial plans"
git push
```
