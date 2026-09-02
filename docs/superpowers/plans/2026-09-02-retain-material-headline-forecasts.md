# Retain Material Headline Forecasts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retain a publisher's substantively central, evidence-backed forecast alongside current-state evidence in the shared Editorial Plan without adding model calls.

**Architecture:** The Editorial Plan prompt remains the single selection decision that downstream Summary, findings, and Expert View receive. Its selection rule will prioritize a forecast only when evidence shows it is central to the report's argument or repeated opening synthesis, while requiring forecast attribution and rejecting page-position or promotional copy as sufficient evidence.

**Tech Stack:** Python, pytest, YAML prompt resources, retained P6 editorial acceptance artifacts.

## Global Constraints

- Do not add model calls.
- Do not present a publisher forecast as observed fact; retain explicit forecast attribution.
- Do not select a claim solely because it appears on page 1 or in promotional copy.
- Preserve the current 300M+ observed metric when the central 600M+ forecast is also selected.
- Update the product editorial-output documentation and use the Batch 3 safe isolated profile for replay.

---

### Task 1: Specify central-forecast selection in the Editorial Plan prompt

**Files:**
- Modify: `src/prompts/report_vs/artifacts/editorial_plan/user.yaml`
- Modify: `tests/test_prompt_service.py`
- Test: `tests/test_prompt_service.py::test_editorial_plan_prompt_retains_substantive_central_forecasts`

**Interfaces:**
- Consumes: `doc_map_json` and `evidence_json` supplied to `report_vs/artifacts/editorial_plan`.
- Produces: unchanged `editorial_plan` JSON with evidence IDs; no new schema fields or prompt family.

- [x] **Step 1: Write the failing prompt-contract test**

```python
assert "materially central" in editorial_plan_prompt.user.text
assert "page position" in editorial_plan_prompt.user.text
assert "promotional" in editorial_plan_prompt.user.text
assert "forecast" in editorial_plan_prompt.user.text
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_prompt_service.py::test_editorial_plan_prompt_retains_substantive_central_forecasts`

Expected: FAIL because the Editorial Plan prompt has no central-forecast selection rule.

- [x] **Step 3: Add the minimal selection rule**

```yaml
  Give additional importance to a source-backed publisher forecast when it is materially central to the report's stated argument and is repeated in the executive summary, opening takeaways, or another substantive synthesis. It may sit beside a current-state metric on the same theme. Page position, repetition alone, and promotional opening copy are not sufficient. Keep forecast language and source attribution explicit; do not recast it as observed fact.
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_prompt_service.py::test_editorial_plan_prompt_retains_substantive_central_forecasts`

Expected: PASS.

### Task 2: Add a representative shared-plan fixture regression

**Files:**
- Modify: `tests/_test_artifact_generator/cases_06_editorial_plan.py`
- Test: `tests/test_artifact_generator.py::test_editorial_plan_keeps_current_metric_and_central_publisher_forecast`

**Interfaces:**
- Consumes: `generate_artifacts` with the existing fake provider and an Editorial Plan containing observed and forecast evidence IDs.
- Produces: a shared plan forwarded unchanged to summary, insight-candidate, insight-final, and Expert View prompts, with exactly the existing eight fake model steps.

- [x] **Step 1: Write the failing fixture test**

```python
assert forecast_id in payload["editorial_plan"]["themes"][0]["evidence_ids"]
assert current_id in payload["editorial_plan"]["themes"][0]["evidence_ids"]
assert "Activate's forecast" in rendered_prompt_variables
assert len(openai_client.requests) == 8
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_artifact_generator.py::test_editorial_plan_keeps_current_metric_and_central_publisher_forecast`

Expected: FAIL because the fixture and explicit forecast-forwarding assertion do not exist.

- [x] **Step 3: Add one fixture with observed, central forecast, and secondary evidence**

```python
findings = [
    {"id": "current-users", "text": "300M+ active users ..."},
    {"id": "publisher-forecast", "text": "Activate forecasts 600M+ users by 2026 ..."},
    {"id": "secondary-1", "text": "A secondary statistic ..."},
]
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_artifact_generator.py::test_editorial_plan_keeps_current_metric_and_central_publisher_forecast`

Expected: PASS, and the request count remains eight.

### Task 3: Document and validate the behavioral change

**Files:**
- Modify: `docs/product/editorial-output.md`

**Interfaces:**
- Consumes: the retained Editorial Plan and source evidence.
- Produces: current product documentation describing the centrality threshold and forecast framing.

- [x] **Step 1: Document the selection boundary**

```markdown
A source-backed publisher forecast may be retained beside current-state evidence only when it is materially central to the report's stated argument and corroborated by substantive synthesis; page placement, repetition, and promotional copy alone do not qualify it. Public output identifies it as the publisher's forecast.
```

- [ ] **Step 2: Run focused prompt, artifact, findings, and public-quality tests**

Run: `python -m pytest -q tests/test_prompt_service.py tests/test_artifact_generator.py tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py tests/test_render_service_public_advisory.py tests/test_render_service_public_prose.py`

Expected: PASS.

- [ ] **Step 3: Replay the P6 Batch 3 cohort and inspect Metaverse output**

Run: `$env:MARKET_LENSE_CONFIG_PATH = 'src/config/app.yaml'; $env:MARKET_LENSE_CONFIG_PROFILE = 'p6_editorial_acceptance_batch_03_headline_forecasts_20260902'; python -m src.cli ingest --cohort-manifest out/p6_editorial_acceptance/batch_03_headline_forecasts_20260902/cohort_manifest.json`

Expected: five reports replay through the isolated safe profile, no external writes, and Metaverse Summary, Findings, and Expert View explicitly attribute the 600M+ by 2026 number as Activate's forecast.

- [ ] **Step 4: Run final hygiene checks**

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 5: Commit and push after explicit forecast-attribution inspection**

```powershell
git add src/prompts/report_vs/artifacts/editorial_plan/user.yaml tests/test_prompt_service.py tests/_test_artifact_generator/cases_06_editorial_plan.py docs/product/editorial-output.md docs/superpowers/plans/2026-09-02-retain-material-headline-forecasts.md
git commit -m "fix: retain material headline forecasts"
git push
```
