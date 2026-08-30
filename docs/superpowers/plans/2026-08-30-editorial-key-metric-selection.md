# Editorial Key-Metric Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the public metric spine prioritize metrics that evidence the report's highest-priority editorial themes.

**Architecture:** `assemble_artifacts_payload` already has the normalized editorial plan and source key-metrics pack. Pass the plan into the deterministic metric-spine builder, rank source metrics by matching selected theme priority, and use missing-context count only after editorial relevance. Keep the metric schema, evidence IDs, display labels, values, and bounded public output unchanged.

**Tech Stack:** Python, pytest, existing report-artifact schemas and evidence-reference validator.

## Global Constraints

- Change textual metric selection only; do not change chart, table, figure, or crop selection code.
- Preserve source-provided label/value/unit and valid evidence IDs.
- Keep the public metric spine capped at six entries.
- Preserve backward compatibility for existing callers that do not supply an editorial plan.

---

### Task 1: Define editorial metric-ranking behavior

**Files:**
- Modify: `tests/_test_artifact_generator/cases_04_advisory_metric_spine.py`
- Modify: `src/generators/_artifact_generator/storage.py`

**Interfaces:**
- Consumes: `derive_metric_spine(evidence_packs: Dict[str, Any], editorial_plan: Dict[str, Any] | None = None)`.
- Produces: a bounded `List[Dict[str, Any]]` whose metrics retain the existing public metric-spine contract.

- [x] **Step 1: Write the failing test**

```python
def test_metric_spine_prioritizes_high_priority_theme_over_context_and_id() -> None:
    spine = derive_metric_spine(
        evidence_packs_with_complete_secondary_metric_and_incomplete_headline_metric,
        editorial_plan_with_headline_metric_evidence_at_priority_one,
    )

    assert [item["metric_id"] for item in spine] == ["headline", "secondary"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_artifact_generator.py -k prioritizes_high_priority_theme`

Expected: FAIL because the old signature cannot accept the plan or returns the ID/context ordering.

- [x] **Step 3: Write minimal implementation**

```python
metric_spine = derive_metric_spine(evidence_packs, editorial_plan=editorial_plan)

return _rank_metric_spine(spine, editorial_plan=editorial_plan)
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_artifact_generator.py -k prioritizes_high_priority_theme`

Expected: PASS.

### Task 2: Preserve safe fallback behavior and document it

**Files:**
- Modify: `tests/_test_artifact_generator/cases_04_advisory_metric_spine.py`
- Modify: `docs/product/editorial-output.md`

**Interfaces:**
- Consumes: incomplete source metric context and no matching editorial-plan evidence ID.
- Produces: the existing metric object shape, valid evidence reference, and deterministic fallback ordering without rejecting a source-backed metric solely for missing optional context.

- [x] **Step 1: Write the failing test**

```python
def test_derive_metric_spine_keeps_incomplete_headline_metric_source_backed() -> None:
    spine = derive_metric_spine(
        headline_metric_without_geography,
        editorial_plan_that_selects_its_evidence_id,
    )

    assert spine[0]["evidence_id"] == "metric-headline"
    assert spine[0]["missing_context_notes"] == ["geography"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_artifact_generator.py -k incomplete_headline_metric`

Expected: FAIL because the old context-first ranking keeps a complete secondary metric first.

- [x] **Step 3: Write the documentation and minimal ranking integration**

```markdown
The public metric spine ranks metrics that directly support selected editorial-plan themes before secondary metrics. Missing contextual fields remain surfaced as caveats and only break ties among metrics with equal editorial relevance.
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_artifact_generator.py -k "prioritizes_high_priority_theme or incomplete_headline_metric"`

Expected: PASS.

### Task 3: Verify artifacts and a retained real report

**Files:**
- Inspect: retained `out/*/report_analysis/artifacts.json`

- [x] **Step 1: Run focused artifact tests**

Run: `python -m pytest -q tests/test_artifact_generator.py tests/test_schema_validator.py tests/test_render_service_public_advisory.py`

Expected: PASS with no evidence-reference regressions.

- [x] **Step 2: Run editorial public-output checks**

Run: `python -m pytest -q tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py tests/test_render_service_public_advisory.py tests/test_render_service_public_prose.py; python scripts/ci/check_public_report_quality.py`

Expected: PASS or explicitly record unrelated baseline failures.

- [x] **Step 3: Inspect a real report**

Run a read-only comparison of retained `artifacts.json` editorial-plan theme evidence IDs to its public metric spine and report whether the re-ranked metrics support the major themes.

- [x] **Step 4: Inspect final diff, commit, and push**

Run: `git diff --check; git diff --name-only; git status --short; git add <changed-files>; git commit -m "feat: prioritize editorial key metrics"; git push`

Expected: no whitespace or secret exposure; commit and push only after all validation is successful.
