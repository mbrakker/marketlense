# Public Key-Figure Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every public Key Figure contains one natural primary metric or is omitted, while retaining supporting numbers in its insight and evidence.

**Architecture:** Keep the existing artifact metric-spine boundary and its Editorial Plan ranking unchanged. Add a deterministic display normalizer at that boundary: it rejects semicolon-packed or multi-metric values/units, removes redundant unit tokens already expressed by a complete value, and canonicalizes the narrow `$ billion` unit form when it can be safely joined to a single numeric value. Prompt instructions prevent recurrence; no new model call, chart/table path, evidence ID, or ranking rule changes.

**Tech Stack:** Python 3, pytest, JSON/YAML prompt resources, existing public-render benchmark.

## Global Constraints

- Keep one primary public metric per insight metric object.
- Preserve valid coherent comparisons such as `$7.2T to $10.4T`.
- Preserve supporting numerical context in insight text/evidence; do not turn it into a second public display metric.
- Do not change Editorial Plan ranking, chart/table/crop logic, evidence IDs, or model-call count.
- Prefer omission to a malformed public Key Figure.

---

### Task 1: Define and test deterministic public-metric display normalization

**Files:**
- Modify: `src/generators/_artifact_generator/storage.py`
- Test: `tests/_test_artifact_generator/cases_04_advisory_metric_spine.py`

**Interfaces:**
- Consumes: an insight `metric` mapping with string `value` and `unit`.
- Produces: a retained metric-spine entry with a single public display, or no entry when the display is composite/malformed.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.parametrize(
    ("metric", "expected"),
    [
        ({"value": "70%", "unit": "percent"}, "70%"),
        ({"value": "$258.6", "unit": "billion"}, "$258.6 billion"),
        ({"value": "$7.2T to $10.4T", "unit": ""}, "$7.2T to $10.4T"),
    ],
)
def test_metric_spine_renders_one_clean_primary_metric(metric, expected):
    ...

def test_metric_spine_omits_semicolon_packed_metric():
    ...

def test_metric_spine_omits_unrecoverable_composite_unit():
    ...
```

- [ ] **Step 2: Run the focused tests and verify they fail because clean display normalization does not yet exist**

Run: `python -m pytest -q tests/test_artifact_generator.py -k "metric_spine"`

- [ ] **Step 3: Add the smallest deterministic normalizer at metric-spine construction**

```python
value, unit = normalize_public_metric_display(value=value, unit=unit)
if not value:
    continue
```

The normalizer must reject semicolon-separated values/units and multiple primary numeric displays, suppress unit repetition already embedded in `value`, normalize `258.6` plus `$ billion` to `$258.6 billion`, and retain valid single values and ranges.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `python -m pytest -q tests/test_artifact_generator.py -k "metric_spine"`

### Task 2: Prevent malformed model output in initial and repair prompts

**Files:**
- Modify: `src/prompts/report_vs/artifacts/insights_candidates/user.yaml`
- Modify: `src/prompts/report_vs/artifacts/insights_final/user.yaml`
- Modify: `src/prompts/report_vs/artifacts/regenerate/insights_candidates/user.yaml`
- Modify: `src/prompts/report_vs/artifacts/regenerate/insights_final/user.yaml`
- Test: `tests/test_prompt_dry_run_validation.py`
- Test: `tests/test_prompt_fixture_corpus_regression.py`

**Interfaces:**
- Consumes: the current artifact insight JSON schema and retained grounding context.
- Produces: candidate/final/repaired metric objects with exactly one primary display value and one non-redundant semantic unit.

- [ ] **Step 1: Add the requirement consistently to each prompt**

```text
metric.value must be one complete human-readable primary metric or one coherent comparison/range. Never put semicolon-separated metric lists in value. metric.unit must name one semantic unit and must not repeat currency symbols or magnitude words already in value. Keep supporting numbers in text/evidence.
```

- [ ] **Step 2: Run prompt materialization regression checks**

Run: `python -m pytest -q tests/test_prompt_service.py tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py`

### Task 3: Add the IAB regression fixture and document the public contract

**Files:**
- Modify: `tests/fixtures/editorial_temporal/iab_pwc_quarterly.json`
- Modify: `tests/_test_artifact_generator/cases_04_advisory_metric_spine.py`
- Modify: `docs/product/editorial-output.md`

**Interfaces:**
- Consumes: a retained IAB malformed/public metric display fixture.
- Produces: an artifact regression proving malformed values are omitted while insight source text and evidence ID remain intact.

- [ ] **Step 1: Extend the IAB fixture with literal clean and malformed key-figure inputs**

```json
{
  "malformed_key_figure_value": "19.2%; $62.1; $102.9; 39.8% growth",
  "malformed_key_figure_unit": "$ billion; $ billion; share",
  "clean_currency_key_figure": "$258.6 billion"
}
```

- [ ] **Step 2: Add a test that loads the fixture and asserts omission plus retained insight text/evidence ID**

```python
assert derive_metric_spine_from_insights([malformed_insight]) == []
assert malformed_insight["text"] == fixture["source_comparison"]
assert malformed_insight["evidence_id"] == fixture["report_id"]
```

- [ ] **Step 3: Document the exact public-display invariant and omission policy**

Add a concise paragraph to the existing metric-spine contract explaining one primary value/range, non-duplicated units, and fail-closed omission.

### Task 4: Validate rendered output and commit the scoped change

**Files:**
- Verify only: five retained P6 artifact reports and generated local benchmark output.

- [ ] **Step 1: Run artifact, schema, editorial-quality, and public-render test suites**

Run: `python -m pytest -q tests/test_artifact_generator.py tests/test_contract_schema_gate.py tests/test_public_editorial_quality_generator.py tests/test_render_service_public_advisory.py tests/test_public_advisory_render_benchmark.py`

- [ ] **Step 2: Run the public quality gate and render all five P6 artifacts to a new local output directory**

Run: `python scripts/ci/check_public_report_quality.py --minimum-reports 1`

Run: `python scripts/quality/public_advisory_render_benchmark.py <five retained artifacts> --output-dir out/public-key-figure-display-benchmark --json-output out/public-key-figure-display-benchmark.json`

- [ ] **Step 3: Manually inspect each rendered Key Figures section and record before/after examples**

Confirm no semicolon-packed display or `258.6 $ billion` output; confirm currency, percentage, and range displays remain natural.

- [ ] **Step 4: Inspect final diff and repository status, commit, and push**

Run: `git diff --check`, targeted status/diff inspection, `git commit`, then `git push`.
